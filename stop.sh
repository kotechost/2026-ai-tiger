#!/bin/bash

# Stop the Docker containers
if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
        docker compose down
    elif command -v docker-compose >/dev/null 2>&1; then
        docker-compose down
    else
        echo "Error: docker compose command not found." >&2
        exit 1
    fi
else
    echo "Error: docker is not installed or not in PATH." >&2
    exit 1
fi

echo "Containers stopped."