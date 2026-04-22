#!/bin/bash
# vllm serve 를 nohup 으로 백그라운드 실행
# 로그: <이 스크립트 위치>/vllm_logs/vllm_<timestamp>.log
# PID:  <이 스크립트 위치>/vllm_logs/vllm.pid

set -e

# 스크립트가 위치한 디렉터리 (vllm-package)
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VENV=/home/solihost/vllm-package/uv-vllm
MODEL=/home/solihost/exaone_models/EXAONE-4.5-33B
LOG_DIR="$PKG_DIR/vllm_logs"
PID_FILE="$LOG_DIR/vllm.pid"

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/vllm_$(date +%Y%m%d_%H%M%S).log"

# 이미 실행 중이면 경고
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "이미 vllm 이 실행 중입니다 (PID=$OLD_PID)."
        echo "종료하려면: $PKG_DIR/stop_vllm.sh"
        echo "로그 보기:  $PKG_DIR/tail_vllm.sh"
        exit 1
    else
        echo "stale PID 파일 제거: $PID_FILE (PID=$OLD_PID 가 살아있지 않음)"
        rm -f "$PID_FILE"
    fi
fi

# venv 의 vllm 바이너리 직접 호출 → activate 불필요
nohup "$VENV/bin/vllm" serve "$MODEL" \
  --served-model-name EXAONE-4.5-33B \
  --port 8005 \
  --tensor-parallel-size 4 \
  --max-model-len 262144 \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --gpu-memory-utilization 0.65 \
  --limit-mm-per-prompt '{"image":64}' \
  --speculative_config '{"method":"mtp","num_speculative_tokens":3}' \
  > "$LOG" 2>&1 &

PID=$!
echo "$PID" > "$PID_FILE"

# 최신 로그 경로를 심볼릭 링크로 고정 (tail_vllm.sh 에서 사용)
ln -sfn "$LOG" "$LOG_DIR/latest.log"

echo "PID:          $PID"
echo "log file:     $LOG"
echo "latest link:  $LOG_DIR/latest.log"
echo "pid file:     $PID_FILE"
echo ""
echo "실시간 로그:  $PKG_DIR/tail_vllm.sh"
echo "종료:         $PKG_DIR/stop_vllm.sh"
