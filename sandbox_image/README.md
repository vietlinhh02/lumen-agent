# Lumen Sandbox

Per-project isolated execution environment for the Lumen assistant.

## What's in here

- `Dockerfile` — slim Python 3.12 image with FastAPI + uvicorn + pypdf
- `server.py` — the FastAPI app the Lumen backend talks to over HTTP
- `requirements.txt` — pinned deps

## Build

```bash
cd sandbox_image
docker build -t lumen-sandbox:latest .
```

## Run a one-off for debugging

```bash
docker run -d --rm --name lumen-sb-test -p 9090:9090 lumen-sandbox:latest
curl http://localhost:9090/health
# {"ok":true,"workspace":"/workspace","free_bytes":...,"uptime_sec":0}

# Run some Python
curl -X POST http://localhost:9090/python -H 'Content-Type: application/json' \
    -d '{"code": "print(2+2)"}'
# {"ok":true,"stdout":"4\n","stderr":"","exit_code":0,"duration_ms":12}

# Read a whitelisted shell command
curl -X POST http://localhost:9090/shell -H 'Content-Type: application/json' \
    -d '{"command": "ls /workspace"}'

# Anything outside the whitelist is rejected with HTTP 403
curl -X POST http://localhost:9090/shell -H 'Content-Type: application/json' \
    -d '{"command": "rm -rf /"}'
# {"detail":"command 'rm' not in whitelist. Allowed: [...]"}
```

## API

| Endpoint          | Method | Purpose                                | Notes |
|-------------------|--------|----------------------------------------|-------|
| `/health`         | GET    | Liveness probe                         | Used by the Lumen backend to wait for ready |
| `/python`         | POST   | Run Python in a subprocess             | body: `{code, timeout}` |
| `/shell`          | POST   | Run a whitelisted shell command        | body: `{command, timeout}` |
| `/file/read`      | POST   | Read a file under `/workspace`         | body: `{path, max_bytes}` |
| `/file/write`     | POST   | Write/append a file under `/workspace` | body: `{path, content, mode}` |
| `/file/list`      | POST   | List `/workspace` (optional glob)      | body: `{path, pattern}` |
| `/pdf/page`       | POST   | Extract text from a single PDF page    | body: `{path, page, max_chars}` |
| `/pdf/grep`       | POST   | Regex search across a PDF              | body: `{path, pattern, context, max_matches}` |
| `/package/install`| POST   | pip-install packages in the sandbox    | body: `{packages, timeout}` |

All POST endpoints return JSON: `{ok, ...}`. Errors return `{ok: false, error}`
or HTTP 4xx with `{detail: ...}`.

## Security model

- **No network by default** — set `LUMEN_SANDBOX_NETWORK=bridge` to allow
  the agent to fetch URLs via `run_python`/`run_shell`.
- **Workspace is bind-mounted** from the Lumen host (per-project dir).
- **Shell command whitelist** — only `ls, cat, head, tail, grep, wc, find,
  sort, uniq, awk, sed, jq, file, du, stat, ...` are allowed. Dangerous
  commands (`rm`, `mv`, `cp`, `chmod`, `sudo`, `curl`, `wget`, `ssh`,
  `bash`, `sh`, `>`, `|`) are rejected before execution.
- **Filesystem scoped to /workspace** — paths that escape are rejected
  with HTTP 400.
- **Resource limits** — set via `LUMEN_SANDBOX_MEMORY` (default 512m)
  and `LUMEN_SANDBOX_CPUS` (default 1.0).
- **Auto-cleanup** — containers are `--rm`, so they die on teardown.
  The Lumen manager also runs a background reaper that kills containers
  idle longer than `LUMEN_SANDBOX_IDLE_TTL` (default 30 min).

For even stricter isolation, run the container with extra flags:

```bash
docker run -d --rm \
  --name lumen-sb-X \
  --read-only \
  --tmpfs /tmp:size=64m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  -m 512m --cpus 1.0 \
  -v $PWD/data/sandboxes/X:/workspace:rw \
  -P lumen-sandbox:latest
```

You'll need to add these flags to `SandboxManager._spawn_docker` if
you want the manager to apply them.
