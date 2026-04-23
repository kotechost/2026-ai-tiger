#!/bin/bash
LOG_DIR="/mnt/hdd22t2/solihost/llm-system/llm-system-bsk/rag_log/$(date +%Y%m%d)"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d_%H).log"
./start.sh 2>&1 | tee -a "$LOG_FILE"
