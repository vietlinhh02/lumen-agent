#!/usr/bin/env bash
# Install AI session logger for opencode (and Claude Code / Gemini CLI / Codex / Cursor / Copilot).
# Usage: bash scripts/install-ai-log.sh
#   or:  curl -sSL <raw-url> | bash
set -euo pipefail

REPO_ROOT="$(pwd)"
OPENCODE_DIR="$REPO_ROOT/.opencode"
PLUGIN_DIR="$OPENCODE_DIR/plugin"
SCRIPTS_DIR="$REPO_ROOT/scripts"
AI_LOG_DIR="$REPO_ROOT/.ai-log"

echo "==> Installing AI log hooks in $REPO_ROOT"

# ── 1. Create directories ───────────────────────────────────────────────
mkdir -p "$PLUGIN_DIR" "$SCRIPTS_DIR" "$AI_LOG_DIR"

# ── 2. Write opencode plugin ────────────────────────────────────────────
cat > "$PLUGIN_DIR/ai-log.ts" << 'PLUGIN_EOF'
import type { Plugin } from "@opencode-ai/plugin"
import { spawn } from "child_process"
import { appendFileSync, existsSync, mkdirSync } from "fs"
import { resolve, join } from "path"

const PROJECT_ROOT = resolve(import.meta.dirname, "../..")
const LOG_SCRIPT = join(PROJECT_ROOT, "scripts/log_hook.py")
const PYRUN = join(PROJECT_ROOT, "scripts/_pyrun.sh")
const DEBUG_FILE = join(PROJECT_ROOT, ".ai-log/plugin-debug.log")

function debug(msg: string) {
  try {
    mkdirSync(resolve(DEBUG_FILE, ".."), { recursive: true })
    appendFileSync(DEBUG_FILE, `[${new Date().toISOString()}] ${msg}\n`)
  } catch {}
}

function logToHook(data: Record<string, unknown>) {
  debug(`logToHook called: script=${LOG_SCRIPT} exists=${existsSync(LOG_SCRIPT)}`)
  if (!existsSync(LOG_SCRIPT)) {
    debug(`LOG_SCRIPT not found: ${LOG_SCRIPT}`)
    return
  }
  try {
    const child = spawn("bash", [PYRUN, LOG_SCRIPT, "--tool=opencode"], {
      stdio: ["pipe", "ignore", "ignore"],
      cwd: PROJECT_ROOT,
    })
    child.stdin.write(JSON.stringify(data))
    child.stdin.end()
    child.on("error", (err) => debug(`spawn error: ${err.message}`))
    debug("spawned successfully")
  } catch (err: any) {
    debug(`spawn exception: ${err.message}`)
  }
}

debug("Plugin module loaded")

const AiLogPlugin: Plugin = async (input) => {
  debug(`Plugin init called, directory=${input?.directory}`)
  return {
    "chat.message": async (input, output) => {
      debug(`chat.message fired`)
      const msg = output?.message
      if (!msg) return
      const role = msg.role

      let content = ""
      if (Array.isArray(output?.parts)) {
        content = output.parts
          .filter((p: any) => p.type === "text" && !p.synthetic)
          .map((p: any) => p.text)
          .join("")
      } else if (typeof msg.content === "string") {
        content = msg.content
      } else if (Array.isArray(msg.content)) {
        content = msg.content
          .filter((p: any) => p.type === "text")
          .map((p: any) => p.text)
          .join("")
      }

      debug(`chat.message: role=${role}, content length=${content.length}`)
      if (!content) return

      logToHook({
        hook_event_name: role === "user" ? "UserPromptSubmit" : "Stop",
        prompt: content.slice(0, 1000),
        model: input?.model?.modelID || "",
        session_id: input?.sessionID || "",
      })
    },

    "tool.execute.before": async (input, output) => {
      const filePath = output?.args?.filePath || ""
      const command = output?.args?.command || ""
      if (input.tool === "read" && filePath.includes(".env")) {
        throw new Error("Blocked: Do not read .env files")
      }
      if (input.tool === "bash" && command.includes(".env")) {
        throw new Error("Blocked: Do not access .env files via bash")
      }
    },
  }
}

export default AiLogPlugin
PLUGIN_EOF

# ── 3. Write opencode package.json ──────────────────────────────────────
cat > "$OPENCODE_DIR/package.json" << 'PKG_EOF'
{
  "dependencies": {
    "@opencode-ai/plugin": "1.15.12"
  }
}
PKG_EOF

# ── 4. Write log_hook.py ────────────────────────────────────────────────
cat > "$SCRIPTS_DIR/log_hook.py" << 'HOOK_EOF'
#!/usr/bin/env python3
"""
Shared AI hook logger — works with Claude Code, Gemini CLI, Codex, Cursor, Copilot.
Reads JSON from stdin, normalizes to common format, appends to .ai-log/session.jsonl
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))


def git(cmd):
    try:
        return subprocess.check_output(
            cmd, shell=True, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


def detect_tool(data: dict) -> str:
    for arg in sys.argv[1:]:
        if arg.startswith("--tool="):
            return arg.split("=", 1)[1].lower()
    tool_env = os.environ.get("AI_TOOL_NAME", "").lower()
    if tool_env:
        return tool_env
    if "transcript_path" in data:
        return "codex"
    if data.get("hook_event_name", "").startswith(
        ("Before", "After", "Session", "Pre", "Notification")
    ):
        return "gemini"
    if data.get("hook_event_name", "")[0:1].islower():
        if "workspace_roots" in data:
            return "cursor"
        if "toolName" in data:
            return "copilot"
    if "hook_event_name" in data:
        return "claude"
    return "unknown"


def normalize(data: dict, tool: str) -> dict | None:
    event = data.get("hook_event_name") or data.get("event", "")
    ts = datetime.now(VN_TZ).isoformat()

    origin = git("git remote get-url origin")
    if not origin:
        return None
    repo = origin.rstrip("/").split("/")[-1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    base = {
        "ts": ts,
        "tool": tool,
        "event": event,
        "session_id": (
            data.get("session_id") or data.get("conversation_id") or data.get("generation_id") or ""
        ),
        "model": data.get("model", ""),
        "repo": repo,
        "branch": git("git rev-parse --abbrev-ref HEAD"),
        "commit": git("git rev-parse --short HEAD"),
        "student": git("git config user.email"),
    }

    if tool == "claude":
        prompt = ""
        if event == "UserPromptSubmit":
            prompt = data.get("prompt", "")[:1000]
        elif isinstance(data.get("tool_input"), dict):
            prompt = data["tool_input"].get("prompt") or data["tool_input"].get("content") or ""
        base.update(
            {
                "prompt": prompt,
                "tool_name": data.get("tool_name", ""),
                "tool_input": data.get("tool_input") if event != "UserPromptSubmit" else None,
                "tool_response": str(data.get("tool_response", ""))[:500],
            }
        )

    elif tool == "gemini":
        if event == "BeforeAgent":
            prompt = data.get("prompt", "")[:1000]
            base.update({"prompt": prompt})
        else:
            req = data.get("request", {})
            contents = req.get("contents", [])
            prompt = ""
            for c in reversed(contents):
                for part in c.get("parts", []):
                    if part.get("text"):
                        prompt = part["text"][:1000]
                        break
                if prompt:
                    break
            resp = data.get("response", {})
            answer = ""
            try:
                answer = resp["candidates"][0]["content"]["parts"][0]["text"][:500]
            except Exception:
                pass
            base.update({"prompt": prompt, "response_summary": answer})

    elif tool == "codex":
        base.update(
            {
                "prompt": data.get("prompt", "")[:1000],
                "turn_id": data.get("turn_id", ""),
                "transcript_path": data.get("transcript_path", ""),
            }
        )

    elif tool == "cursor":
        base.update(
            {
                "prompt": data.get("prompt", "")[:1000],
                "files_context": data.get("attachments", []),
            }
        )

    elif tool == "copilot":
        base.update(
            {
                "prompt": data.get("prompt", "")[:1000],
                "tool_name": data.get("toolName", ""),
                "tool_args": data.get("toolArgs"),
            }
        )

    elif tool == "opencode":
        base.update(
            {
                "prompt": data.get("prompt", "")[:1000],
            }
        )

    _PAYLOAD_KEYS = (
        "prompt",
        "tool_input",
        "response_summary",
        "tool_response",
        "tool_args",
        "files_context",
    )
    _LIFECYCLE_EVENTS = ("Stop", "stop", "SessionEnd", "sessionEnd", "AfterModel")
    has_payload = any(base.get(k) for k in _PAYLOAD_KEYS)
    if not has_payload and event not in _LIFECYCLE_EVENTS:
        return None

    return base


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace").strip()
    if not raw:
        sys.exit(0)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool = detect_tool(data)
    entry = normalize(data, tool)
    if not entry:
        sys.exit(0)

    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "session.jsonl"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if tool != "codex":
        print(json.dumps({"status": "logged"}))


if __name__ == "__main__":
    main()
HOOK_EOF

# ── 5. Write _pyrun.sh ──────────────────────────────────────────────────
cat > "$SCRIPTS_DIR/_pyrun.sh" << 'PYRUN_EOF'
#!/usr/bin/env bash
set -u

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
elif command -v py >/dev/null 2>&1; then
  PY="py -3"
else
  PY=""
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ]; then PY="$cand"; break; fi
  done
  shopt -u nullglob 2>/dev/null || true
  [ -n "$PY" ] || exit 0
fi

exec $PY "$@"
PYRUN_EOF
chmod +x "$SCRIPTS_DIR/_pyrun.sh"

# ── 6. Add .ai-log/.gitkeep ─────────────────────────────────────────────
touch "$AI_LOG_DIR/.gitkeep"

# ── 7. Install npm dependency ───────────────────────────────────────────
echo "==> Installing @opencode-ai/plugin..."
if command -v npm >/dev/null 2>&1; then
  (cd "$OPENCODE_DIR" && timeout 30 npm install --silent 2>/dev/null) || {
    echo "    WARN: npm install failed or timed out. Run manually: cd .opencode && npm install"
  }
else
  echo "    WARN: npm not found. Install Node.js, then run: cd .opencode && npm install"
fi

# ── 8. Add .ai-log to .gitignore if missing ─────────────────────────────
GITIGNORE="$REPO_ROOT/.gitignore"
if [ -f "$GITIGNORE" ]; then
  if ! grep -q "^\.ai-log/" "$GITIGNORE" 2>/dev/null; then
    echo ".ai-log/" >> "$GITIGNORE"
    echo "==> Added .ai-log/ to .gitignore"
  fi
else
  echo ".ai-log/" > "$GITIGNORE"
  echo "==> Created .gitignore with .ai-log/"
fi

# ── Done ─────────────────────────────────────────────────────────────────
echo ""
echo "==> Done! Files installed:"
echo "    .opencode/plugin/ai-log.ts   (opencode plugin)"
echo "    .opencode/package.json       (plugin dependency)"
echo "    scripts/log_hook.py          (shared logger)"
echo "    scripts/_pyrun.sh            (Python launcher)"
echo "    .ai-log/session.jsonl        (log output)"
echo ""
echo "    Restart opencode to activate the plugin."
