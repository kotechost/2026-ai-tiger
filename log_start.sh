#!/bin/bash

# Start the containers
./start.sh

BASE_LOG_DIR="/mnt/hdd22t2/solihost/llm-system/llm-system-bsk/rag_log"
mkdir -p "$BASE_LOG_DIR"

nohup bash -c '
    BASE_LOG_DIR="'"$BASE_LOG_DIR"'"
    docker logs -f rag-api-bsk 2>&1 | while IFS= read -r line; do
        printf -v d "%(%Y%m%d)T" -1
        printf -v h "%(%H)T" -1
        dir="$BASE_LOG_DIR/$d"
        [ -d "$dir" ] || mkdir -p "$dir"
        printf "%s\n" "$line" >> "$dir/${d}_${h}.log"
    done
' >/dev/null 2>&1 &
echo $! > log_pid.txt
