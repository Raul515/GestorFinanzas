# Use a slim Python base image
FROM python:3.11-slim-bookworm

# Install uv globally
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

COPY requirements/frontend.txt /app/requirements.txt

# Install dependencies
RUN uv venv
RUN uv pip install -r requirements.txt

# Copy the frontend needed files and backend shared utilities
COPY src/frontend /app/src/frontend
COPY src/backend /app/src/backend
COPY images/frontend/start_services.sh /app/docker/start_services.sh

# Make the wrapper script executable
RUN chmod +x /app/docker/start_services.sh

# Expose the frontend port
EXPOSE 8501

# Set the entrypoint to the start script
CMD [ "/app/docker/start_services.sh" ]
