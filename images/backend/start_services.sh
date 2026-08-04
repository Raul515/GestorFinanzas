#!/bin/bash
export PYTHONPATH=/app/src:/app

term_handler() {
    echo "Termination signal received"
    kill -TERM "$BACKEND_PID" 2>/dev/null
}

trap 'term_handler' SIGTERM SIGINT

python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

wait -n
exit $?
