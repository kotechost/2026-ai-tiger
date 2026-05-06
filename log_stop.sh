#!/bin/bash

if [ -f log_pid.txt ]; then
    PID=$(cat log_pid.txt)
    if kill "$PID" 2>/dev/null; then
        echo "Stopped logging process $PID"
    else
        echo "Regular kill failed, forcing stop $PID"
        kill -9 "$PID" 2>/dev/null || true
    fi
    rm -f log_pid.txt
else
    echo "No PID file found, stopping any matching logging process"
    pkill -f "docker logs -f rag-api-bsk" 2>/dev/null || true
fi

# Stop the containers
if [ -x ./stop.sh ]; then
    ./stop.sh
else
    bash ./stop.sh
fi