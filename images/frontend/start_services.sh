#!/bin/bash
export PYTHONPATH=/app/src:/app

term_handler() {
    echo "Termination signal received"
    kill -TERM "$FRONTEND_PID" 2>/dev/null
}

trap 'term_handler' SIGTERM SIGINT

streamlit run src/frontend/app.py --server.port=8501 --server.address=0.0.0.0 &
FRONTEND_PID=$!

wait -n
exit $?
