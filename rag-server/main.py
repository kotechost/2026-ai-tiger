import re
import time
import psutil
import subprocess
import traceback
import os
import json
import random
import httpx
import asyncio  # 큐 및 타임아웃 관리를 위해 추가
import time
from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from db.config.database import init_db_pool, close_db_pool
from rag.rewrite_query import rewrite_query

# RAG 관련 모듈
from rag.search import search_context, match_source, parse_title, get_surrounding_docs, get_source_url, build_doc_sources
from rag.gpu_monitor import GpuMonitor

# 전역 상태
from state import state

# API 라우터
from api.bible_info import router as bible_info_router
from api.bible_crawl import router as bible_crawl_router
from api.bible_vector import router as bible_vector_router
from api.bible_vector_stitle import router as bible_vector_stitle_router
from api.bible_vector_doc import router as bible_vector_doc_router
print("🚀 API Server Loading...", flush=True)

DEBUG_STREAM = os.getenv("DEBUG_STREAM", "1") == "1"
DEBUG_FULL_CHUNK = os.getenv("DEBUG_FULL_CHUNK", "1") == "1"

# ✅ 백엔드 분기
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "exaone")  # "exaone" or "qwen"

# exaone → vLLM
# VLLM_URL   = "http://host.docker.internal:8005/v1/chat/completions"
# VLLM_MODEL = os.getenv("VLLM_MODEL_NAME", "/app/models/EXAONE-4.5-33B")

VLLM_URL   = os.getenv("VLLM_URL", "http://host.docker.internal:8005/v1/chat/completions")
VLLM_MODEL = os.getenv("VLLM_MODEL_NAME", "EXAONE-4.5-33B")

# qwen → Ollama (라운드 로빈)
OLLAMA_SERVERS = [
    "http://host.docker.internal:11434/v1/chat/completions",
]
OLLAMA_MODEL = "qwen2.5:7b"

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 API Server Loading...", flush=True)
    state.client = httpx.AsyncClient(
        timeout=httpx.Timeout(300.0, connect=10.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    )
    state.bible_lock = asyncio.Lock()
    print("✅ RAG API Server Started", flush=True)

    yield

    if state.db_pool:
        await close_db_pool()
    await state.client.aclose()
    print("🛑 RAG API Server Stopped")

app = FastAPI(lifespan=lifespan)
app.include_router(bible_info_router)
app.include_router(bible_crawl_router)
app.include_router(bible_vector_router)
app.include_router(bible_vector_stitle_router)
app.include_router(bible_vector_doc_router)
app.mount("/pdfs", StaticFiles(directory="./pdfs"), name="pdf")

class EvalMetrics:
	def __init__(self, questionStr):
		self.question = questionStr
		self.startTime = time.time()
		self.endTime = None
		self.responseTime = None
		self.gpuUsage = None
		self.answerText = ""
		self.reasoningText = ""

	def finish(self):
		self.endTime = time.time()
		self.responseTime = round(self.endTime - self.startTime, 3)
	

# 2️⃣ 라운드 로빈
server_index = 0

def print_eval(metrics):
	print("\n===== EVAL RESULT =====")
	print(f"| 질문 | 응답속도")
	print(f"|------|----------|-----------|")
	print(f"| {metrics.question[:10]} | {metrics.responseTime}s|")
	print("========================\n")

class Message(BaseModel):
	role: str
	content: str

class ChatRequest(BaseModel):
	model: str
	messages: list[Message]
	think: bool | str | None = None

@app.get("/v1/models")
async def get_models():
	return {
		"object": "list",
		"data": [{"id": "rag-qwen", "object": "model", "owned_by": "rag-api"}]
	}

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
	acquired = False
	try:
		await asyncio.wait_for(state.semaphore.acquire(), timeout=10)
		acquired = True
	except asyncio.TimeoutError:
		async def error_stream():
			yield 'data: {"choices":[{"delta":{"content":"⚠️ 서버가 바쁩니다. 잠시 후 다시 시도해주세요."}}]}\n\n'
			yield "data: [DONE]\n\n"
		return StreamingResponse(error_stream(), media_type="text/event-stream")

	# ✅ 1. 대화 처리
	messages = req.messages
	user_question = messages[-1].content

	metrics = EvalMetrics(user_question)

	# 최근 대화 5개만 유지
	recent_messages = messages[-6:]

	history_text = "\n".join([
		f"{m.role}: {m.content}" for m in recent_messages[:-1]
	])

	summary = history_text[-500:]

	# follow-up 필터 유지
	if any(keyword in user_question.lower() for keyword in ["follow-up", "suggest", "generate a concise", "generate 1-3 broad tags", "chat history"]):
		if acquired:
			state.semaphore.release()
		return {
			"id": "chatcmpl-followup",
			"object": "chat.completion",
			"choices": [{"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}]
		}

	# 이전 질문을 포함한 질문을 llm을 통해서 재생성
	# user_question = await rewrite_query(user_question, summary, VLLM_URL, VLLM_MODEL)

	print("\n" + "=" * 150, flush=True)
	print("=" * 150, flush=True)
	print(f"🔎 [NEW SEARCH {time.strftime('%Y-%m-%d %H:%M:%S')}] {user_question}", flush=True)
	print("=" * 150, flush=True)
	print("=" * 150, flush=True)

	t_rag = time.time()
	# RAG 검색 — VectorDB에서 관련 성경 구절 검색
	context, topDocs, topScored  = search_context(user_question)

	# 앞뒤 5절 문맥 추가
	surrounding_context = ""
	# if topDocs:
	# 	seen_keys = set()
	# 	surrounding_texts = []

	# 	for doc in topDocs:
	# 		parsed = parse_title(doc.get("title", ""))
	# 		if not parsed:
	# 			continue
	# 		version, book, chap, sec = parsed
	# 		surrounding = get_surrounding_docs(version, book, chap, sec)

	# 		for s_doc in surrounding:
	# 			key = s_doc.get("title", "")
	# 			if key not in seen_keys:
	# 				seen_keys.add(key)
	# 				surrounding_texts.append(s_doc.get("text", ""))

	# 	surrounding_context = "\n".join(surrounding_texts)

	print(f"[PERF] RAG 검색: {time.time()-t_rag:.3f}s", flush=True)

	# 프롬프트 구성 — 검색 결과가 있을 때만 성경 구절 섹션 포함
	#    context 없으면 rag_section = "" → LLM이 학습 데이터로만 답변
	rag_section = ""
	# if context:
	# 	rag_section = f"[참고 성경 구절]\n{context}\n"
		# 전후 문맥 추가
		# if surrounding_context:
		# 	rag_section += f"\n[전후 문맥]\n{surrounding_context}\n"


	# ✅ 프롬프트 (절대 유지)
	prompt_text = f"""반드시 한국어로만 답변하세요. 절대 중국어나 영어를 사용하지 마세요.
출처나 참고 표시는 절대 답변에 포함하지 마세요.
단, 답변 맨 마지막 줄에 반드시 <<SRC:번호,번호>> 형식으로 [참고 성경 구절]에서 실제 사용한 번호만 콤마로 나열하세요.
아무것도 사용하지 않았다면 <<SRC:>>로 남기세요.

[추가 규칙]
[참고 성경 구절]에 포함된 표현이 아니면 과장된 표현을 사용하지 마세요.

{rag_section}
[이전 대화 요약]
{summary}

[현재 질문]
{user_question}

답변:
"""
	print(f"[rag 결과]:\n{rag_section}", flush=True)
	print(f"[이전 대화 요약]:\n{summary}", flush=True)
	print(f"[PERF] 프롬프트 길이: {len(prompt_text)}자", flush=True)

	# ✅ 백엔드에 따라 URL·모델·페이로드 선택
	if MODEL_BACKEND == "qwen":
		async with state.index_lock:
			idx = state.ollama_index
			state.ollama_index = (state.ollama_index + 1) % len(OLLAMA_SERVERS)
		target_url = OLLAMA_SERVERS[idx]
		payload = {
			"model": OLLAMA_MODEL,
			"messages": [{"role": "user", "content": prompt_text}],
			"stream": True,
			"temperature": 0.3,
			"top_p": 0.9,
			"max_tokens": 1024,
		}
		print(f"[BACKEND] qwen → Ollama: {target_url}", flush=True)
	else:
		# OpenWebUI Th-On/Off 버튼 → req.think
		#   True  → On
		#   False/None → Off
		#   "false" 문자열 → Off, 그 외 문자열("medium" 등) → On
		enable_thinking = bool(req.think) and req.think != "false"

		target_url = VLLM_URL
		payload = {
			"model": VLLM_MODEL,
			"messages": [{"role": "user", "content": prompt_text}],
			"stream": True,
			"temperature": 0.1,
			"top_p": 0.9,
			"max_tokens": 8192,
			"chat_template_kwargs": {
				"enable_thinking": enable_thinking
			},
		}
		print(f"[BACKEND] exaone → vLLM: {target_url} (thinking={enable_thinking}, raw={req.think!r})", flush=True)

	# LLM 호출 구간 동안 1초 단위로 GPU 사용률 기록 (follow-up 필터 이후, 실제 LLM 호출 직전에 시작)
	gpu_monitor = GpuMonitor(interval=1.0, question=user_question)
	gpu_monitor.start()
	print(f"[GPU_MONITOR] logging to {gpu_monitor.log_path}", flush=True)

	async def generate_stream():
		full_content = []
		full_reasoning = []
		marker_buffer = ""       # 마커 후보 누적
		in_marker = False        # 마커 감지 상태
		src_indices = None       # 파싱된 번호 리스트
		t_stream = time.time()
		first_token = True
		gpu_monitor.mark_llm_start()
		try:
			async with state.client.stream("POST", target_url, json=payload) as response:
				if response.status_code != 200:
					err_body = await response.aread()
					print(f"[LLM ERROR {response.status_code}] {err_body.decode(errors='ignore')}", flush=True)
					raise Exception(f"Backend error: {response.status_code}")

				async for line in response.aiter_lines():
					if not line:
						continue
					line = line.strip()
					if not line.startswith("data: "):
						continue
					line = line[6:]

					if line == "[DONE]":
						print(f"\n[LLM REASONING]\n{''.join(full_reasoning)}", flush=True)
						print(f"\n[LLM CONTENT]\n{''.join(full_content)}", flush=True)

						# 남은 marker_buffer 처리 (미완성 마커면 버림)
						if marker_buffer and not re.search(r'<<SRC:([\d,\s]*)>>', marker_buffer):
							print(f"[SRC 미완성 버퍼 버림]: {marker_buffer!r}", flush=True)
							marker_buffer = ""
							in_marker = False

						if topDocs:
							print(f"[SRC 파싱]: {src_indices}", flush=True)
							sourceUrls = []

							# ===== 출처 URL 선정 =====
							# 1) 번호 기반 선택 (최우선)
							if src_indices:
								for idx in src_indices:
									if 1 <= idx <= len(topScored):
										_, doc = topScored[idx - 1]
										url = get_source_url(doc)
										if url and url not in sourceUrls:
											sourceUrls.append(url)
							
							# 2) 번호 없거나 파싱 실패 시 → match_source fallback
							if not sourceUrls:
								full_answer = "".join(full_content)
								sourceUrls = match_source(full_answer, topDocs)

							# ===== 출처 렌더링 =====					
							# bible / pdf 분리
							bible_scored = [(s, d) for s, d in topScored if d.get("source_type") != "file"]
							pdf_scored   = [(s, d) for s, d in topScored if d.get("source_type") == "file"]

							# 1) 성경 문서: 텍스트 출처 링크
							bible_lines = []
							seen = set()
							for _, doc in bible_scored:
								url = get_source_url(doc)
								if url in sourceUrls and url not in seen:
									bible_lines.append(f"- [{doc.get('title', '')}]({url})")
									seen.add(url)

							if bible_lines:
								sourceLinks = "\n\n**출처:**\n" + "\n".join(bible_lines) + "\n"
								chunk = {
									"id": "chatcmpl-rag",
									"object": "chat.completion.chunk",
									"choices": [{"index": 0, "delta": {"content": sourceLinks}, "finish_reason": None}]
								}
								yield f"data: {json.dumps(chunk)}\n\n"

							# 2) PDF sources (OpenWebUI 형식)
							if pdf_scored and sourceUrls:
								pdf_matched = [
									(s, d) for s, d in pdf_scored
									if get_source_url(d) in sourceUrls
								]
								if pdf_matched:
									docSources = build_doc_sources(pdf_matched)
									yield f'data: {json.dumps({"sources": docSources})}\n\n'

						yield "data: [DONE]\n\n"
						break


					chunk = json.loads(line)
			
					delta = (chunk.get("choices") or [{}])[0].get("delta", {})
					content   = delta.get("content", "")
					reasoning = delta.get("reasoning")

					if reasoning:
						full_reasoning.append(reasoning)

					if content:
						if first_token:
							gpu_monitor.mark_first_token()
							print(f"[PERF] 첫 토큰까지: {time.time()-t_stream:.3f}s", flush=True)
							first_token = False
						emit_buf = ""  # 사용자에게 보낼 조각

						for ch in content:
							if in_marker:
								marker_buffer += ch
								# 마커 완성
								if marker_buffer.endswith(">>"):
									m = re.search(r'<<SRC:([\d,\s]*)>>', marker_buffer)
									if m:
										nums = [n.strip() for n in m.group(1).split(",") if n.strip()]
										src_indices = [int(n) for n in nums if n.isdigit()]
									else:
										# 오탐 → 버퍼 내용 flush
										emit_buf += marker_buffer
									marker_buffer = ""
									in_marker = False
								# 마커 초반 prefix 검증 (오탐 조기 탈출)
								elif len(marker_buffer) <= 6:
									if not "<<SRC:".startswith(marker_buffer):
										emit_buf += marker_buffer
										marker_buffer = ""
										in_marker = False
							elif ch == "<":
								marker_buffer = "<"
								in_marker = True
							else:
								emit_buf += ch

						if emit_buf:
							full_content.append(emit_buf)
							yield f"data: {json.dumps({'id':'chatcmpl-rag','object':'chat.completion.chunk','choices':[{'index':0,'delta':{'content':emit_buf},'finish_reason':None}]})}\n\n"

		finally:
			if acquired:
				state.semaphore.release()
			metrics.finish()
			gpu_monitor.set_response("".join(full_content))
			await gpu_monitor.stop()
			print_eval(metrics)


	return StreamingResponse(generate_stream(), media_type="text/event-stream")
