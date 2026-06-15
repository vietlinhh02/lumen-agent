FROM python:3.12-slim

WORKDIR /app

# Minimal system deps. Network is allowed so agents can fetch URLs.
# We rely on Docker run flags (--cap-drop, --read-only, --tmpfs) for
# additional isolation; this image only needs to be functional.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server.py /app/server.py

# Workspace is the per-project scratch dir (bind-mounted from host).
RUN mkdir -p /workspace
ENV WORKSPACE_DIR=/workspace \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 9090

# tini reaps zombies; uvicorn is the sandbox API.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9090", "--log-level", "warning"]
