docker compose -p llm-system-jsy down

docker compose -p llm-system-jsy build rag-api-jsy

docker compose -p llm-system-jsy up -d

docker logs -f llm-system-jsy-rag-api-jsy-1