#!/bin/bash
# vllm 프로세스 종료 (PID 파일 기반)

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PKG_DIR/vllm_logs"
PID_FILE="$LOG_DIR/vllm.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "PID 파일이 없습니다: $PID_FILE"
    echo "실행 중인 vllm 이 없거나, run_vllm.sh 로 띄우지 않은 프로세스입니다."
    echo ""
    REMAINING=$(pgrep -af "vllm serve" || true)
    if [ -n "$REMAINING" ]; then
        echo "아래 vllm 프로세스가 감지됩니다:"
        echo "$REMAINING"
        echo ""
        echo "강제 종료: pkill -f 'vllm serve'"
    fi
    exit 1
fi

PID=$(cat "$PID_FILE")

if ! kill -0 "$PID" 2>/dev/null; then
    echo "PID=$PID 프로세스가 이미 죽어있습니다. PID 파일 정리."
    rm -f "$PID_FILE"
    exit 0
fi

echo "종료 신호(SIGTERM) 전송: PID=$PID"
kill "$PID"

# 최대 20초 대기
for i in $(seq 1 20); do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "종료 완료."
        rm -f "$PID_FILE"

        # 자식 프로세스(워커) 남아있는지 확인
        REMAINING=$(pgrep -af "vllm serve" || true)
        if [ -n "$REMAINING" ]; then
            echo ""
            echo "경고: 하위 vllm 프로세스가 남아있습니다:"
            echo "$REMAINING"
            echo "강제 종료: pkill -9 -f 'vllm serve'"
        fi
        exit 0
    fi
    sleep 1
done

echo "20초 대기해도 종료 안 됨. SIGKILL 전송."
kill -9 "$PID" 2>/dev/null || true
pkill -9 -f "vllm serve" 2>/dev/null || true
rm -f "$PID_FILE"
echo "강제 종료 완료."
