"""Local subprocess stub for the sandbox.

When ``LUMEN_SANDBOX_MODE=stub`` we run the same Python code in a
local subprocess (in a temp directory with workspace bind-mount) so
the agent works end-to-end without needing Docker. This is also what
unit tests use.

The stub is a faithful re-implementation of the FastAPI endpoints
shipped in ``sandbox_image/server.py``, so behavior matches except
for resource limits and network policy.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

SHELL_WHITELIST: set[str] = {
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "find",
    "sort",
    "uniq",
    "cut",
    "tr",
    "sed",
    "awk",
    "jq",
    "file",
    "du",
    "df",
    "stat",
    "echo",
    "pwd",
    "date",
    "which",
    "env",
    "whoami",
    "hostname",
    "uname",
    "ps",
    "tree",
    "xxd",
    "od",
    "diff",
    "tee",
    "xargs",
    "base64",
    "md5sum",
    "sha256sum",
    "nl",
    "tac",
    "rev",
    "fold",
    "paste",
    "join",
    "comm",
    "printf",
    "true",
    "false",
    "test",
}

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_CODE_BYTES = 200_000
MAX_OUTPUT_BYTES = 1 * 1024 * 1024
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 600


def _truncate(text: str | None, limit: int = MAX_OUTPUT_BYTES) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[truncated {len(text) - limit} bytes]"


def _workspace_path(workspace_root: Path, rel: str) -> Path:
    """Resolve *rel* to a path inside *workspace_root*.

    Accepts both the Docker-canonical "/workspace/..." and host-relative
    paths. Reject any attempt to escape the workspace — including
    absolute paths that point outside (e.g. /etc/passwd).
    """
    if not rel or rel == "/workspace":
        return workspace_root
    # Docker-canonical /workspace/<x> → <workspace_root>/<x>
    if rel == "/workspace" or rel.startswith("/workspace/"):
        rel = rel[len("/workspace") :]
        # Already validated to be inside workspace_root via the join below
    elif rel.startswith("/"):
        # Any other absolute path is outside /workspace by definition.
        # Even if the file doesn't exist on the host, we don't want the
        # agent to be able to scribble on /etc, /var, etc.
        raise ValueError(f"path outside workspace: {rel}")
    candidate = (workspace_root / rel.lstrip("/")).resolve()
    if not str(candidate).startswith(str(workspace_root.resolve())):
        raise ValueError(f"path escapes workspace: {rel}")
    return candidate


async def health(workspace_root: Path) -> dict[str, Any]:
    return {
        "ok": True,
        "workspace": str(workspace_root),
        "free_bytes": shutil.disk_usage(workspace_root).free,
        "uptime_sec": int(time.time()),
        "stub": True,
    }


async def run_python(workspace_root: Path, code: str, timeout: int) -> dict[str, Any]:
    if len(code) > MAX_CODE_BYTES:
        return {"ok": False, "error": f"code too large ({len(code)} bytes)"}
    timeout = max(1, min(timeout, MAX_TIMEOUT))
    with tempfile.TemporaryDirectory(prefix="lumen-sb-") as tmp:
        script = Path(tmp) / "user_script.py"
        script.write_text(code)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": tmp,
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        start = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                "python",
                str(script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmp,
                env=env,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "ok": False,
                    "stdout": "",
                    "stderr": f"[Timeout after {timeout}s]",
                    "exit_code": -1,
                    "timed_out": True,
                    "duration_ms": int((time.time() - start) * 1000),
                }
            return {
                "ok": proc.returncode == 0,
                "stdout": _truncate(stdout_b.decode("utf-8", errors="replace")),
                "stderr": _truncate(stderr_b.decode("utf-8", errors="replace")),
                "exit_code": proc.returncode,
                "duration_ms": int((time.time() - start) * 1000),
            }
        except FileNotFoundError:
            return {"ok": False, "error": "python interpreter not found"}


async def run_shell(workspace_root: Path, command: str, timeout: int) -> dict[str, Any]:
    head = command.strip().split(maxsplit=1)
    if not head or head[0] not in SHELL_WHITELIST:
        return {
            "ok": False,
            "error": f"command '{head[0] if head else ''}' not in whitelist",
        }
    timeout = max(1, min(timeout, MAX_TIMEOUT))
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace_root),
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "ok": False,
                "stdout": "",
                "stderr": f"[Timeout after {timeout}s]",
                "exit_code": -1,
                "timed_out": True,
            }
        return {
            "ok": proc.returncode == 0,
            "stdout": _truncate(stdout_b.decode("utf-8", errors="replace")),
            "stderr": _truncate(stderr_b.decode("utf-8", errors="replace")),
            "exit_code": proc.returncode,
            "duration_ms": int((time.time() - start) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}


async def file_read(workspace_root: Path, path: str, max_bytes: int) -> dict[str, Any]:
    try:
        target = _workspace_path(workspace_root, path)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not target.exists():
        return {"ok": False, "error": f"not found: {path}"}
    if target.is_dir():
        return {"ok": False, "error": "is a directory; use /file/list"}
    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        return {"ok": False, "error": f"file too large ({size} bytes)"}
    if size > max_bytes:
        with target.open("rb") as f:
            data = f.read(max_bytes)
        return {
            "ok": True,
            "content": data.decode("utf-8", errors="replace"),
            "truncated": True,
            "size_bytes": size,
            "read_bytes": max_bytes,
        }
    return {
        "ok": True,
        "content": target.read_text(errors="replace"),
        "truncated": False,
        "size_bytes": size,
    }


async def file_write(workspace_root: Path, path: str, content: str, mode: str) -> dict[str, Any]:
    try:
        target = _workspace_path(workspace_root, path)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size + len(content) > MAX_FILE_BYTES:
        return {"ok": False, "error": "file would exceed max size"}
    with target.open(mode, encoding="utf-8") as f:
        f.write(content)
    return {
        "ok": True,
        "path": str(target.relative_to(workspace_root)),
        "size_bytes": target.stat().st_size,
    }


async def file_list(workspace_root: Path, path: str, pattern: str | None) -> dict[str, Any]:
    try:
        target = _workspace_path(workspace_root, path)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not target.exists():
        return {"ok": False, "error": f"not found: {path}"}
    if not target.is_dir():
        return {"ok": False, "error": "not a directory"}
    items = list(target.glob(pattern) if pattern else target.iterdir())
    out = []
    for item in sorted(items)[:500]:
        try:
            st = item.stat()
            out.append(
                {
                    "name": item.name,
                    "path": str(item.relative_to(workspace_root)),
                    "is_dir": item.is_dir(),
                    "size_bytes": st.st_size if not item.is_dir() else None,
                    "modified_ts": int(st.st_mtime),
                }
            )
        except OSError:
            continue
    return {"ok": True, "items": out, "count": len(out)}


async def pdf_page(workspace_root: Path, path: str, page: int, max_chars: int) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"ok": False, "error": "pypdf not installed"}
    try:
        target = _workspace_path(workspace_root, path)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": f"PDF not found: {path}"}
    try:
        reader = PdfReader(str(target))
        if page > len(reader.pages):
            return {"ok": False, "error": f"only {len(reader.pages)} pages"}
        text = reader.pages[page - 1].extract_text() or ""
        return {
            "ok": True,
            "page": page,
            "total_pages": len(reader.pages),
            "content": _truncate(text, max_chars),
            "truncated": len(text) > max_chars,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}


async def pdf_grep(
    workspace_root: Path,
    path: str,
    pattern: str,
    context: int,
    max_matches: int,
) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"ok": False, "error": "pypdf not installed"}
    try:
        target = _workspace_path(workspace_root, path)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": f"PDF not found: {path}"}
    try:
        reader = PdfReader(str(target))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return {"ok": False, "error": f"bad regex: {exc}"}
    matches: list[dict] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for m in compiled.finditer(text):
            start = max(0, m.start() - context)
            end = min(len(text), m.end() + context)
            matches.append(
                {
                    "page": page_idx,
                    "match": m.group(0),
                    "context": text[start:end],
                }
            )
            if len(matches) >= max_matches:
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


async def pip_install(packages: list[str], timeout: int) -> dict[str, Any]:
    if not packages:
        return {"ok": True, "stdout": "", "stderr": "", "exit_code": 0}
    timeout = max(1, min(timeout, MAX_TIMEOUT))
    cmd = [
        "pip",
        "install",
        "--quiet",
        "--disable-pip-version-check",
        "--no-input",
        *packages,
    ]
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "ok": False,
                "error": f"pip install timeout after {timeout}s",
                "duration_ms": int((time.time() - start) * 1000),
            }
        return {
            "ok": proc.returncode == 0,
            "stdout": _truncate(stdout_b.decode("utf-8", errors="replace"), 20_000),
            "stderr": _truncate(stderr_b.decode("utf-8", errors="replace"), 20_000),
            "exit_code": proc.returncode,
            "duration_ms": int((time.time() - start) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}
