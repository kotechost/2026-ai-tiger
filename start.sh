docker compose down

rm -rf /mnt/hdd22t2/solihost/llm-system/llm-system-bsk/gpu_log/*

docker compose build rag-api-bsk

docker compose up -d

docker logs -f rag-api-bsk  > /mnt/hdd22t2/solihost/llm-system/llm-system-bsk/rag_vllm.log
