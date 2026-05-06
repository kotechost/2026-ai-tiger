docker compose down

# 14일 초과 로그 폴더 정리 (gpu_log, rag_log)

BASE_DIR="/mnt/hdd22t2/solihost/llm-system/llm-system-bsk"
CUTOFF=$(date -d "14 days ago" +%Y%m%d)
for log_root in "$BASE_DIR/gpu_log" "$BASE_DIR/rag_log"; do
    [ -d "$log_root" ] || continue
    for day_dir in "$log_root"/*/; do
        name=$(basename "$day_dir")
        if [[ "$name" =~ ^[0-9]{8}$ ]] && [[ "$name" < "$CUTOFF" ]]; then
            echo "[log-cleanup] remove $day_dir"
            rm -rf "$day_dir"
        fi
    done
done

docker compose build rag-api-bsk

docker compose up -d

# Note: log_start.sh handles streaming docker logs into rag_log files.
