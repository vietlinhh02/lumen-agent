#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# install-ai-log.sh — Global installer for AI session logger
# Works on: macOS, Linux, WSL
# Usage:   bash install-ai-log.sh          (from repo → also installs local)
#          bash install-ai-log.sh --global  (global only, no project files)
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

GLOBAL_ONLY=false
[[ "${1:-}" == "--global" ]] && GLOBAL_ONLY=true

# ── Paths ────────────────────────────────────────────────────────────────
OPENCODE_DIR="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"
PLUGIN_DIR="$OPENCODE_DIR/plugins"
SCRIPTS_DIR="$OPENCODE_DIR/scripts"
REPO_ROOT="$(pwd)"

echo "┌──────────────────────────────────────────────┐"
echo "│       AI Session Logger — Installer           │"
echo "└──────────────────────────────────────────────┘"
echo ""
echo "  Global dir : $OPENCODE_DIR"
echo "  Platform   : $(uname -s) ($(uname -m))"
echo ""

# ── 1. Create global directories ────────────────────────────────────────
echo "[1/5] Creating directories..."
mkdir -p "$PLUGIN_DIR" "$SCRIPTS_DIR"

# ── 2. Copy plugin ──────────────────────────────────────────────────────
echo "[2/5] Installing plugin → $PLUGIN_DIR/ai-log.ts"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/ai-log.ts" ]; then
  cp "$SCRIPT_DIR/ai-log.ts" "$PLUGIN_DIR/ai-log.ts"
else
  echo "  ERROR: ai-log.ts not found next to this script."
  echo "  Make sure scripts/ai-log.ts exists in the repo."
  exit 1
fi

# ── 3. Copy logger scripts ──────────────────────────────────────────────
echo "[3/5] Installing scripts → $SCRIPTS_DIR/"
if [ -f "$SCRIPT_DIR/log_hook.py" ]; then
  cp "$SCRIPT_DIR/log_hook.py" "$SCRIPTS_DIR/log_hook.py"
else
  echo "  ERROR: log_hook.py not found."
  exit 1
fi

cat > "$SCRIPTS_DIR/_pyrun.sh" << 'PYRUN_EOF'
#!/usr/bin/env bash
set -u
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
elif command -v py >/dev/null 2>&1; then PY="py -3"
else
  PY=""
  shopt -s nullglob 2>/dev/null || true
  for cand in /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    [ -x "$cand" ] && { PY="$cand"; break; }
  done
  shopt -u nullglob 2>/dev/null || true
  [ -n "$PY" ] || exit 0
fi
exec $PY "$@"
PYRUN_EOF
chmod +x "$SCRIPTS_DIR/_pyrun.sh"

# ── 4. Update opencode.json ─────────────────────────────────────────────
echo "[4/5] Updating opencode.json..."
CONFIG_FILE="$OPENCODE_DIR/opencode.json"
PLUGIN_ENTRY="$PLUGIN_DIR/ai-log.ts"

if [ -f "$CONFIG_FILE" ]; then
  # Check if plugin already registered
  if grep -q "ai-log.ts" "$CONFIG_FILE" 2>/dev/null; then
    echo "  Plugin already registered, skipping."
  else
    # Add plugin entry to the "plugin" array
    if command -v node >/dev/null 2>&1; then
      node -e "
        const fs = require('fs');
        const cfg = JSON.parse(fs.readFileSync('$CONFIG_FILE', 'utf8'));
        if (!Array.isArray(cfg.plugin)) cfg.plugin = [];
        cfg.plugin.push('$PLUGIN_ENTRY');
        fs.writeFileSync('$CONFIG_FILE', JSON.stringify(cfg, null, 2) + '\n');
      "
      echo "  Added ai-log.ts to plugin list."
    else
      echo "  WARN: node not found. Add this to opencode.json → plugin array:"
      echo "    \"$PLUGIN_ENTRY\""
    fi
  fi
else
  # Create minimal config
  cat > "$CONFIG_FILE" << CFGEOF
{
  "\$schema": "https://opencode.ai/config.json",
  "plugin": [
    "$PLUGIN_ENTRY"
  ]
}
CFGEOF
  echo "  Created new opencode.json with ai-log plugin."
fi

# ── 5. Install npm dependency ───────────────────────────────────────────
echo "[5/5] Installing @opencode-ai/plugin..."
GLOBAL_PKG="$OPENCODE_DIR/package.json"
if [ ! -f "$GLOBAL_PKG" ]; then
  echo '{"dependencies":{"@opencode-ai/plugin":"latest"}}' > "$GLOBAL_PKG"
fi

if command -v npm >/dev/null 2>&1; then
  (cd "$OPENCODE_DIR" && timeout 60 npm install --silent 2>/dev/null) || {
    echo "  WARN: npm install failed. Run manually: cd $OPENCODE_DIR && npm install"
  }
else
  echo "  WARN: npm not found. Install Node.js, then: cd $OPENCODE_DIR && npm install"
fi

# ── 6. Install project-level files (unless --global) ────────────────────
if [ "$GLOBAL_ONLY" = false ] && [ -d "$REPO_ROOT/.git" ]; then
  echo ""
  echo "[+] Also installing project files in $REPO_ROOT ..."
  mkdir -p "$REPO_ROOT/.ai-log" "$REPO_ROOT/scripts"
  touch "$REPO_ROOT/.ai-log/.gitkeep"

  # Copy log_hook.py to project for backward compat with project-level plugin
  cp "$SCRIPTS_DIR/log_hook.py" "$REPO_ROOT/scripts/log_hook.py"
  cp "$SCRIPTS_DIR/_pyrun.sh" "$REPO_ROOT/scripts/_pyrun.sh"
  chmod +x "$REPO_ROOT/scripts/_pyrun.sh"

  # Update .gitignore
  GITIGNORE="$REPO_ROOT/.gitignore"
  if [ -f "$GITIGNORE" ]; then
    grep -q "^\.ai-log/" "$GITIGNORE" 2>/dev/null || echo ".ai-log/" >> "$GITIGNORE"
  else
    echo ".ai-log/" > "$GITIGNORE"
  fi
  echo "  Project files installed."
fi

# ── Done ─────────────────────────────────────────────────────────────────
echo ""
echo "┌──────────────────────────────────────────────┐"
echo "│  Done! Restart opencode to activate.         │"
echo "└──────────────────────────────────────────────┘"
echo ""
echo "  Installed:"
echo "    $PLUGIN_DIR/ai-log.ts"
echo "    $SCRIPTS_DIR/log_hook.py"
echo "    $SCRIPTS_DIR/_pyrun.sh"
echo ""
echo "  Logs go to: <project>/.ai-log/session.jsonl"
echo ""
