#!/bin/bash
# 가장 최근 vllm 로그를 실시간 팔로우
# 인자 없이 실행:  latest.log → 없으면 가장 최근 vllm_*.log
# 인자로 파일명:   특정 로그 파일을 tail -f

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PKG_DIR/vllm_logs"

if [ -n "$1" ]; then
    LOG="$1"
elif [ -e "$LOG_DIR/latest.log" ]; then
    LOG="$LOG_DIR/latest.log"
else
    # latest.log 없으면 가장 최근 vllm_*.log 로 폴백
    LOG=$(ls -t "$LOG_DIR"/vllm_*.log 2>/dev/null | head -1)
    if [ -n "$LOG" ]; then
        echo "latest.log 없음 → 최근 로그로 폴백: $LOG"
        # 다음부터 편하게 쓰도록 심볼릭 링크도 걸어둠
        ln -sfn "$LOG" "$LOG_DIR/latest.log"
    fi
fi

if [ -z "$LOG" ] || [ ! -e "$LOG" ]; then
    echo "로그 파일이 없습니다."
    echo ""
    echo "존재하는 로그 목록:"
    ls -lht "$LOG_DIR"/vllm_*.log 2>/dev/null | head -10
    exit 1
fi

echo "=== 팔로우 중: $(readlink -f "$LOG") ==="
echo "(중지: Ctrl+C)"
echo ""

tail -n 200 -f "$LOG"
