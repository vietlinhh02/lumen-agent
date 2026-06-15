"""Sandbox HTTP server — runs inside the lumen-sandbox container.

Exposes a small set of endpoints for the Lumen assistant agent to use
for ad-hoc computation, file I/O, shell access, and PDF inspection.

Endpoints:
    GET  /health                 — liveness probe
    POST /python                 — run Python code in a subprocess
    POST /shell                  — run a whitelisted shell command
    POST /file/read              — read a file (workspace-only)
    POST /file/write             — write a file (workspace-only)
    POST /file/list              — list workspace files
    POST /pdf/page               — extract a single page from a PDF
    POST /pdf/grep               — regex search across a PDF
    POST /package/install        — pip install into the sandbox

All endpoints return JSON: {"ok": bool, "stdout"/"content"/...: str,
"stderr": str, "exit_code": int}.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ── Constants ──────────────────────────────────────────────────────────────

WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "/workspace"))
WORKSPACE.mkdir(parents=True, exist_ok=True)

# Whitelisted shell commands. Anything not matched is rejected. This is
# the most important security boundary in the sandbox.
SHELL_WHITELIST: set[str] = {
    "ls", "cat", "head", "tail", "wc", "grep", "find", "sort", "uniq",
    "cut", "tr", "sed", "awk", "jq", "file", "du", "df", "stat", "echo",
    "pwd", "date", "which", "env", "whoami", "hostname", "uname", "ps",
    "tree", "xxd", "od", "diff", "tee", "xargs", "base64", "md5sum",
    "sha256sum", "nl", "tac", "rev", "fold", "paste", "join", "comm",
    "printf", "true", "false", "test",
}

# Cap file sizes to avoid the agent OOM-ing the sandbox.
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MiB
MAX_CODE_BYTES = 200_000  # 200 KB of Python source
MAX_OUTPUT_BYTES = 1 * 1024 * 1024  # 1 MiB of stdout
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 600

_START_TIME = time.time()

app = FastAPI(title="lumen-sandbox", version="1.0.0")


# ── Schemas ────────────────────────────────────────────────────────────────


class RunCode(BaseModel):
    code: str = Field(..., max_length=MAX_CODE_BYTES)
    timeout: int = Field(DEFAULT_TIMEOUT, ge=1, le=MAX_TIMEOUT)


class RunShell(BaseModel):
    command: str = Field(..., max_length=2000)
    timeout: int = Field(DEFAULT_TIMEOUT, ge=1, le=MAX_TIMEOUT)


class FileReadReq(BaseModel):
    path: str
    max_bytes: int = Field(200_000, ge=1, le=MAX_FILE_BYTES)


class FileWriteReq(BaseModel):
    path: str
    content: str
    mode: str = Field("w", pattern=r"^(w|a)$")


class FileListReq(BaseModel):
    path: str = "/workspace"
    pattern: str | None = None


class PdfPageReq(BaseModel):
    path: str
    page: int = Field(..., ge=1)
    max_chars: int = Field(20_000, ge=100, le=200_000)


class PdfGrepReq(BaseModel):
    path: str
    pattern: str
    context: int = Field(120, ge=0, le=1000)
    max_matches: int = Field(20, ge=1, le=200)


class PipInstallReq(BaseModel):
    packages: list[str] = Field(..., max_length=20)
    timeout: int = Field(120, ge=1, le=MAX_TIMEOUT)


# ── Helpers ────────────────────────────────────────────────────────────────


def _workspace_path(rel: str) -> Path:
    """Resolve *rel* to an absolute path inside /workspace.

    Reject any path that escapes the workspace (no parent traversal).
    """
    if not rel:
        return WORKSPACE
    candidate = (WORKSPACE / rel.lstrip("/")).resolve()
    if not str(candidate).startswith(str(WORKSPACE.resolve())):
        raise HTTPException(400, f"path escapes workspace: {rel}")
    return candidate


def _truncate(text: str, limit: int = MAX_OUTPUT_BYTES) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[truncated {len(text) - limit} bytes]"


def _is_whitelisted(command: str) -> tuple[bool, str]:
    """Check the first token of *command* is in the shell whitelist."""
    head = command.strip().split(maxsplit=1)
    if not head:
        return False, "empty command"
    return (head[0] in SHELL_WHITELIST, head[0])


# ── Endpoints ──────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "workspace": str(WORKSPACE),
        "free_bytes": shutil.disk_usage(WORKSPACE).free,
        "uptime_sec": int(time.time() - _START_TIME),
    }


@app.post("/python")
def run_python(req: RunCode) -> dict[str, Any]:
    """Run arbitrary Python in a subprocess.

    The agent provides *code*; we write it to a temp file and execute it
    in a clean temporary directory so user code can't clobber /workspace
    accidentally. Files in /workspace are still readable from user code.
    """
    with tempfile.TemporaryDirectory(prefix="lumen-sb-") as tmp:
        script = Path(tmp) / "user_script.py"
        script.write_text(req.code)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": tmp,
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        start = time.time()
        try:
            proc = subprocess.run(
                ["python", str(script)],
                capture_output=True,
                text=True,
                timeout=min(req.timeout, MAX_TIMEOUT),
                cwd=tmp,
                env=env,
            )
            return {
                "ok": proc.returncode == 0,
                "stdout": _truncate(proc.stdout),
                "stderr": _truncate(proc.stderr),
                "exit_code": proc.returncode,
                "duration_ms": int((time.time() - start) * 1000),
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "stdout": _truncate(exc.stdout or ""),
                "stderr": _truncate(
                    (exc.stderr or "") + f"\n[Timeout after {req.timeout}s]"
                ),
                "exit_code": -1,
                "timed_out": True,
                "duration_ms": int((time.time() - start) * 1000),
            }


@app.post("/shell")
def run_shell(req: RunShell) -> dict[str, Any]:
    """Run a whitelisted shell command. Anything else is rejected."""
    allowed, head = _is_whitelisted(req.command)
    if not allowed:
        raise HTTPException(
            403,
            f"command '{head}' not in whitelist. Allowed: {sorted(SHELL_WHITELIST)}",
        )
    start = time.time()
    try:
        proc = subprocess.run(
            req.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=min(req.timeout, MAX_TIMEOUT),
            cwd=str(WORKSPACE),
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": _truncate(proc.stdout),
            "stderr": _truncate(proc.stderr),
            "exit_code": proc.returncode,
            "duration_ms": int((time.time() - start) * 1000),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "stdout": _truncate(exc.stdout or ""),
            "stderr": _truncate(
                (exc.stderr or "") + f"\n[Timeout after {req.timeout}s]"
            ),
            "exit_code": -1,
            "timed_out": True,
            "duration_ms": int((time.time() - start) * 1000),
        }


@app.post("/file/read")
def file_read(req: FileReadReq) -> dict[str, Any]:
    target = _workspace_path(req.path)
    if not target.exists():
        raise HTTPException(404, f"not found: {req.path}")
    if target.is_dir():
        raise HTTPException(400, "is a directory; use /file/list")
    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        return {"ok": False, "error": f"file too large ({size} bytes)"}
    if size > req.max_bytes:
        with target.open("rb") as f:
            data = f.read(req.max_bytes)
        return {
            "ok": True,
            "content": data.decode("utf-8", errors="replace"),
            "truncated": True,
            "size_bytes": size,
            "read_bytes": req.max_bytes,
        }
    return {
        "ok": True,
        "content": target.read_text(errors="replace"),
        "truncated": False,
        "size_bytes": size,
    }


@app.post("/file/write")
def file_write(req: FileWriteReq) -> dict[str, Any]:
    target = _workspace_path(req.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size + len(req.content) > MAX_FILE_BYTES:
        return {"ok": False, "error": "file would exceed max size"}
    mode = "a" if req.mode == "a" else "w"
    with target.open(mode, encoding="utf-8") as f:
        f.write(req.content)
    return {
        "ok": True,
        "path": str(target.relative_to(WORKSPACE)),
        "size_bytes": target.stat().st_size,
    }


@app.post("/file/list")
def file_list(req: FileListReq) -> dict[str, Any]:
    target = _workspace_path(req.path)
    if not target.exists():
        raise HTTPException(404, f"not found: {req.path}")
    if not target.is_dir():
        raise HTTPException(400, "not a directory")
    if req.pattern:
        items = list(target.glob(req.pattern))
    else:
        items = list(target.iterdir())
    out = []
    for item in sorted(items)[:500]:
        try:
            st = item.stat()
            out.append(
                {
                    "name": item.name,
                    "path": str(item.relative_to(WORKSPACE)),
                    "is_dir": item.is_dir(),
                    "size_bytes": st.st_size if not item.is_dir() else None,
                    "modified_ts": int(st.st_mtime),
                }
            )
        except OSError:
            continue
    return {"ok": True, "items": out, "count": len(out)}


# ── PDF endpoints (lazy import pypdf to keep base image small) ───────────


def _lazy_import_pypdf():
    try:
        from pypdf import PdfReader
        return PdfReader
    except ImportError:
        return None


@app.post("/pdf/page")
def pdf_page(req: PdfPageReq) -> dict[str, Any]:
    target = _workspace_path(req.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, f"PDF not found: {req.path}")
    PdfReader = _lazy_import_pypdf()
    if PdfReader is None:
        return {"ok": False, "error": "pypdf not installed; install with /package/install"}
    try:
        reader = PdfReader(str(target))
        if req.page > len(reader.pages):
            return {"ok": False, "error": f"only {len(reader.pages)} pages"}
        page = reader.pages[req.page - 1]
        text = page.extract_text() or ""
        return {
            "ok": True,
            "page": req.page,
            "total_pages": len(reader.pages),
            "content": _truncate(text, req.max_chars),
            "truncated": len(text) > req.max_chars,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


@app.post("/pdf/grep")
def pdf_grep(req: PdfGrepReq) -> dict[str, Any]:
    target = _workspace_path(req.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, f"PDF not found: {req.path}")
    PdfReader = _lazy_import_pypdf()
    if PdfReader is None:
        return {"ok": False, "error": "pypdf not installed"}
    try:
        reader = PdfReader(str(target))
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    try:
        pattern = re.compile(req.pattern, re.IGNORECASE)
    except re.error as exc:
        return {"ok": False, "error": f"bad regex: {exc}"}
    matches: list[dict] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for m in pattern.finditer(text):
            start = max(0, m.start() - req.context)
            end = min(len(text), m.end() + req.context)
            matches.append(
                {
                    "page": page_idx,
                    "match": m.group(0),
                    "context": text[start:end],
                }
            )
            if len(matches) >= req.max_matches:
                return {
                    "ok": True,
                    "matches": matches,
                    "truncated": True,
                    "total_pages": len(reader.pages),
                }
    return {
        "ok": True,
        "matches": matches,
        "truncated": False,
        "total_pages": len(reader.pages),
    }


@app.post("/package/install")
def pip_install(req: PipInstallReq) -> dict[str, Any]:
    """Install Python packages inside the sandbox."""
    if not req.packages:
        return {"ok": True, "stdout": "", "stderr": "", "exit_code": 0}
    cmd = [
        "pip",
        "install",
        "--quiet",
        "--disable-pip-version-check",
        "--no-input",
        *req.packages,
    ]
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=min(req.timeout, MAX_TIMEOUT),
            env={**os.environ, "PIP_NO_CACHE_DIR": "1"},
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": _truncate(proc.stdout, 20_000),
            "stderr": _truncate(proc.stderr, 20_000),
            "exit_code": proc.returncode,
            "duration_ms": int((time.time() - start) * 1000),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"pip install timeout after {req.timeout}s",
            "duration_ms": int((time.time() - start) * 1000),
        }


def main() -> None:
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=9090, log_level="warning")


if __name__ == "__main__":
    main()
