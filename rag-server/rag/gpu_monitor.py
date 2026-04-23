import asyncio
import os
import subprocess
from collections import defaultdict
from datetime import datetime

GPU_LOG_DIR = os.getenv("GPU_LOG_DIR", "/app/gpu_log")


class GpuMonitor:
	"""
	백그라운드로 nvidia-smi를 polling 해 GPU 사용률을 파일에 기록.

	LLM 추론(특히 디코딩)은 메모리 바운드라 SM 만 보면 "GPU 가 노는 것처럼" 보인다.
	그래서 세 축을 동시에 수집하고, 전력 기반 사용률을 주 지표로 사용:
	  - sm_pct:  SM(연산 유닛) 점유율  ← 커널 갭 사이에선 낮게 찍힘
	  - mem_pct: 메모리 컨트롤러 점유율 ← LLM 디코딩의 진짜 병목
	  - pwr_pct: power.draw / power.limit ← 물리적으로 smooth, 주 사용률

	stop() 시 GPU별 평균/최고 (세 축 모두) 를 로그 마지막에 붙인다.
	"""

	def __init__(self, interval: float = 1.0, question: str = ""):
		self.interval = interval
		self.question = question
		# per-GPU 누적: {idx: {"sm": [...], "mem": [...], "pwr_pct": [...], "pwr_w": [...]}}
		self.samples: dict[int, dict[str, list[float]]] = defaultdict(
			lambda: {"sm": [], "mem": [], "pwr_pct": [], "pwr_w": []}
		)
		self._task: asyncio.Task | None = None
		self._stop = asyncio.Event()
		self._log_file = None

		now = datetime.now()
		date_dir = os.path.join(GPU_LOG_DIR, now.strftime("%Y%m%d"))
		os.makedirs(date_dir, exist_ok=True)
		ts = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]
		self.log_path = os.path.join(date_dir, f"{ts}.log")

	def _sample_once(self) -> list[tuple[int, int, int, float, float, float]]:
		"""
		한 번 샘플링 → [(gpu_idx, sm%, mem%, pwr_w, pwr_limit_w, pwr_pct), ...]

		두 명령 조합:
		  1) nvidia-smi dmon -s u -c 1   → SM, MEM 점유율
		  2) nvidia-smi --query-gpu ...  → 전력/전력한계
		utilization.gpu (--query-gpu) 는 1초 뻥튀기 값이라 쓰지 않음.
		"""
		# 1) SM / MEM via dmon
		dmon_out = subprocess.check_output(
			["nvidia-smi", "dmon", "-s", "u", "-c", "1"]
		)
		sm_mem: dict[int, tuple[int, int]] = {}
		for line in dmon_out.decode().splitlines():
			line = line.strip()
			if not line or line.startswith("#"):
				continue
			parts = line.split()
			if len(parts) < 3:
				continue
			try:
				idx = int(parts[0])
				sm = int(parts[1])
				mem = int(parts[2])
				sm_mem[idx] = (sm, mem)
			except ValueError:
				continue

		# 2) 전력
		pwr_out = subprocess.check_output(
			[
				"nvidia-smi",
				"--query-gpu=index,power.draw,power.limit",
				"--format=csv,noheader,nounits",
			]
		)
		pwr: dict[int, tuple[float, float]] = {}
		for line in pwr_out.decode().strip().splitlines():
			parts = [p.strip() for p in line.split(",")]
			if len(parts) < 3:
				continue
			try:
				idx = int(parts[0])
				draw = float(parts[1])
				limit = float(parts[2])
				pwr[idx] = (draw, limit)
			except ValueError:
				continue

		rows = []
		for idx in sorted(sm_mem.keys()):
			sm, mem = sm_mem[idx]
			draw, limit = pwr.get(idx, (0.0, 0.0))
			pwr_pct = (draw / limit * 100.0) if limit > 0 else 0.0
			rows.append((idx, sm, mem, draw, limit, pwr_pct))
		return rows

	async def _loop(self):
		self._log_file = open(self.log_path, "w", encoding="utf-8", buffering=1)
		self._log_file.write(f"# question: {self.question[:200]}\n")
		self._log_file.write(f"# start: {datetime.now().isoformat()}\n")
		self._log_file.write(f"# interval_sec: {self.interval}\n")
		self._log_file.write(
			"# metrics: sm_pct=SM점유율, mem_pct=메모리컨트롤러점유율, "
			"pwr_w=현재전력, pwr_limit_w=전력한계, "
			"utilization_percent=pwr_w/pwr_limit_w*100 (주 사용률)\n"
		)
		self._log_file.write(
			"timestamp,gpu_index,utilization_percent,sm_pct,mem_pct,pwr_w,pwr_limit_w\n"
		)

		try:
			while not self._stop.is_set():
				now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
				try:
					rows = await asyncio.to_thread(self._sample_once)
					for idx, sm, mem, pwr_w, pwr_limit, pwr_pct in rows:
						buckets = self.samples[idx]
						buckets["sm"].append(float(sm))
						buckets["mem"].append(float(mem))
						buckets["pwr_pct"].append(pwr_pct)
						buckets["pwr_w"].append(pwr_w)
						self._log_file.write(
							f"{now},{idx},{pwr_pct:.2f},{sm},{mem},"
							f"{pwr_w:.2f},{pwr_limit:.2f}\n"
						)
				except Exception as e:
					self._log_file.write(f"# sample_error: {e}\n")

				try:
					await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
				except asyncio.TimeoutError:
					pass
		finally:
			self._write_summary()
			if self._log_file:
				self._log_file.close()
				self._log_file = None

	@staticmethod
	def _steady_indices(pwr_pct_values: list[float], ratio: float = 0.7) -> tuple[int, int]:
		"""
		피크(pwr_pct) 기준 `ratio` 이상인 구간의 [start, end) 를 반환.
		앞쪽 램프업 / 뒤쪽 테일오프 자동 제거. 샘플이 너무 적으면 전체 유지.
		"""
		n = len(pwr_pct_values)
		if n < 3:
			return 0, n
		peak = max(pwr_pct_values)
		if peak <= 0:
			return 0, n
		threshold = peak * ratio
		# 앞쪽 램프업 skip
		start = 0
		while start < n and pwr_pct_values[start] < threshold:
			start += 1
		# 뒤쪽 테일오프 skip
		end = n
		while end > start and pwr_pct_values[end - 1] < threshold:
			end -= 1
		# 너무 적게 남으면 전체 반환 (신뢰할 만한 피크가 없는 경우)
		if end - start < max(2, n // 3):
			return 0, n
		return start, end

	def _write_summary(self):
		if not self._log_file:
			return
		f = self._log_file
		f.write(f"# end: {datetime.now().isoformat()}\n")
		f.write("# ===== SUMMARY =====\n")

		overall = {"sm": [], "mem": [], "pwr_pct": [], "pwr_w": []}
		steady_overall = {"sm": [], "mem": [], "pwr_pct": [], "pwr_w": []}

		for idx in sorted(self.samples.keys()):
			b = self.samples[idx]
			n = len(b["sm"])
			if n == 0:
				continue

			# 전체
			sm_avg = sum(b["sm"]) / n
			sm_max = max(b["sm"])
			mem_avg = sum(b["mem"]) / n
			mem_max = max(b["mem"])
			pwr_avg = sum(b["pwr_pct"]) / n
			pwr_max = max(b["pwr_pct"])
			pwr_w_avg = sum(b["pwr_w"]) / n

			# 정상 구간 (램프업/테일오프 제거)
			s, e = self._steady_indices(b["pwr_pct"])
			n_steady = e - s
			if n_steady > 0:
				sm_ss = sum(b["sm"][s:e]) / n_steady
				mem_ss = sum(b["mem"][s:e]) / n_steady
				pwr_ss = sum(b["pwr_pct"][s:e]) / n_steady
				pwr_w_ss = sum(b["pwr_w"][s:e]) / n_steady
				for key in steady_overall:
					steady_overall[key].extend(b[key][s:e])
			else:
				sm_ss = mem_ss = pwr_ss = pwr_w_ss = 0.0

			for key in overall:
				overall[key].extend(b[key])

			f.write(
				f"# GPU {idx}: "
				f"util(pwr)={pwr_avg:.1f}% avg / {pwr_max:.1f}% max, "
				f"sm={sm_avg:.1f}% avg / {sm_max:.0f}% max, "
				f"mem={mem_avg:.1f}% avg / {mem_max:.0f}% max, "
				f"pwr={pwr_w_avg:.1f}W avg, "
				f"samples={n}\n"
			)
			if n_steady > 0 and n_steady != n:
				f.write(
					f"#   └ steady[{s}:{e}] ({n_steady}/{n}): "
					f"util(pwr)={pwr_ss:.1f}%, "
					f"sm={sm_ss:.1f}%, mem={mem_ss:.1f}%, "
					f"pwr={pwr_w_ss:.1f}W\n"
				)

		if overall["pwr_pct"]:
			n = len(overall["pwr_pct"])
			pwr_avg = sum(overall["pwr_pct"]) / n
			pwr_max = max(overall["pwr_pct"])
			sm_avg = sum(overall["sm"]) / n
			mem_avg = sum(overall["mem"]) / n
			f.write(
				f"# OVERALL: util(pwr)={pwr_avg:.1f}% avg / {pwr_max:.1f}% max, "
				f"sm={sm_avg:.1f}% avg, mem={mem_avg:.1f}% avg, "
				f"total_samples={n}\n"
			)

			# 정상 구간 전체 평균 (= 결론)
			if steady_overall["pwr_pct"]:
				ns = len(steady_overall["pwr_pct"])
				pwr_ss = sum(steady_overall["pwr_pct"]) / ns
				sm_ss = sum(steady_overall["sm"]) / ns
				mem_ss = sum(steady_overall["mem"]) / ns
				f.write(
					f"# STEADY (램프업/테일오프 제외, {ns}/{n} samples): "
					f"util(pwr)={pwr_ss:.1f}%, "
					f"sm={sm_ss:.1f}%, mem={mem_ss:.1f}%\n"
				)
				f.write(
					f"# ===> GPU 평균 사용률: 약 {round(pwr_ss)}% (정상 구간 전력 기반)\n"
				)
				f.write(
					f"# ===> 메모리 평균 사용률 : 약 {round(mem_ss)}%\n"
				)
		else:
			f.write("# OVERALL: no samples collected\n")

	def start(self):
		if self._task is not None:
			return
		self._task = asyncio.create_task(self._loop())

	async def stop(self):
		if self._task is None:
			return
		self._stop.set()
		try:
			await self._task
		except Exception as e:
			print(f"[GPU_MONITOR] stop error: {e}", flush=True)
		finally:
			self._task = None
