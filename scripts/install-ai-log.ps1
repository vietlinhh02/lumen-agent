# ──────────────────────────────────────────────────────────────────────────
# install-ai-log.ps1 — Global installer for AI session logger (Windows)
# Works on: Windows 10/11, PowerShell 5.1+, PowerShell 7+
# Usage:   .\install-ai-log.ps1          (from repo → also installs local)
#          .\install-ai-log.ps1 -Global  (global only, no project files)
# ──────────────────────────────────────────────────────────────────────────
param(
    [switch]$Global
)

$ErrorActionPreference = "Stop"

# ── Paths ────────────────────────────────────────────────────────────────
$OpenCodeDir = if ($env:OPENCODE_CONFIG_DIR) { $env:OPENCODE_CONFIG_DIR } else { Join-Path $HOME ".config\opencode" }
$PluginDir   = Join-Path $OpenCodeDir "plugins"
$ScriptsDir  = Join-Path $OpenCodeDir "scripts"
$RepoRoot    = Get-Location

Write-Host ""
Write-Host "┌──────────────────────────────────────────────┐" -ForegroundColor Cyan
Write-Host "│       AI Session Logger — Installer           │" -ForegroundColor Cyan
Write-Host "└──────────────────────────────────────────────┘" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Global dir : $OpenCodeDir"
Write-Host "  Platform   : Windows ($env:PROCESSOR_ARCHITECTURE)"
Write-Host ""

# ── Helper: find Python ─────────────────────────────────────────────────
function Find-Python {
    foreach ($cmd in @("python3", "python", "py")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    # Probe standard install locations
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
        "$env:ProgramFiles\Python*\python.exe",
        "${env:ProgramFiles(x86)}\Python*\python.exe"
    )
    foreach ($pattern in $candidates) {
        $match = Get-Item $pattern -ErrorAction SilentlyContinue | Sort-Object -Descending | Select-Object -First 1
        if ($match) { return $match.FullName }
    }
    return $null
}

# ── 1. Create directories ───────────────────────────────────────────────
Write-Host "[1/5] Creating directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path $PluginDir -Force | Out-Null
New-Item -ItemType Directory -Path $ScriptsDir -Force | Out-Null

# ── 2. Copy plugin ──────────────────────────────────────────────────────
Write-Host "[2/5] Installing plugin → $PluginDir\ai-log.ts" -ForegroundColor Yellow
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginSrc = Join-Path $ScriptDir "ai-log.ts"

if (Test-Path $PluginSrc) {
    Copy-Item $PluginSrc (Join-Path $PluginDir "ai-log.ts") -Force
} else {
    Write-Host "  ERROR: ai-log.ts not found next to this script." -ForegroundColor Red
    exit 1
}

# ── 3. Copy logger scripts ──────────────────────────────────────────────
Write-Host "[3/5] Installing scripts → $ScriptsDir\" -ForegroundColor Yellow
$HookSrc = Join-Path $ScriptDir "log_hook.py"

if (Test-Path $HookSrc) {
    Copy-Item $HookSrc (Join-Path $ScriptsDir "log_hook.py") -Force
} else {
    Write-Host "  ERROR: log_hook.py not found." -ForegroundColor Red
    exit 1
}

# Write _pyrun.ps1 (Windows-native Python launcher)
$PyrunContent = @'
# Python launcher for Windows — tries python3, python, py, then common paths.
$py = $null
foreach ($cmd in @("python3", "python", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) { $py = $found.Source; break }
}
if (-not $py) {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
        "$env:ProgramFiles\Python*\python.exe"
    )
    foreach ($pattern in $candidates) {
        $match = Get-Item $pattern -ErrorAction SilentlyContinue | Sort-Object -Descending | Select-Object -First 1
        if ($match) { $py = $match.FullName; break }
    }
}
if (-not $py) { exit 0 }
& $py $args
'@
Set-Content -Path (Join-Path $ScriptsDir "_pyrun.ps1") -Value $PyrunContent -Encoding UTF8

# Also write _pyrun.sh for Git Bash / WSL fallback
$PyrunSh = @'
#!/usr/bin/env bash
set -u
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
elif command -v py >/dev/null 2>&1; then PY="py -3"
else exit 0; fi
exec $PY "$@"
'@
Set-Content -Path (Join-Path $ScriptsDir "_pyrun.sh") -Value $PyrunSh -Encoding UTF8

# ── 4. Update opencode.json ─────────────────────────────────────────────
Write-Host "[4/5] Updating opencode.json..." -ForegroundColor Yellow
$ConfigFile = Join-Path $OpenCodeDir "opencode.json"
$PluginEntry = Join-Path $PluginDir "ai-log.ts"

if (Test-Path $ConfigFile) {
    $config = Get-Content $ConfigFile -Raw | ConvertFrom-Json
    if (-not $config.plugin) { $config | Add-Member -NotePropertyName "plugin" -NotePropertyValue @() }
    if ($config.plugin -contains $PluginEntry) {
        Write-Host "  Plugin already registered, skipping."
    } else {
        $config.plugin += $PluginEntry
        $config | ConvertTo-Json -Depth 10 | Set-Content $ConfigFile -Encoding UTF8
        Write-Host "  Added ai-log.ts to plugin list."
    }
} else {
    $minimal = @{
        '$schema' = "https://opencode.ai/config.json"
        plugin = @($PluginEntry)
    } | ConvertTo-Json -Depth 10
    Set-Content -Path $ConfigFile -Value $minimal -Encoding UTF8
    Write-Host "  Created new opencode.json with ai-log plugin."
}

# ── 5. Install npm dependency ───────────────────────────────────────────
Write-Host "[5/5] Installing @opencode-ai/plugin..." -ForegroundColor Yellow
$GlobalPkg = Join-Path $OpenCodeDir "package.json"
if (-not (Test-Path $GlobalPkg)) {
    Set-Content -Path $GlobalPkg -Value '{"dependencies":{"@opencode-ai/plugin":"latest"}}' -Encoding UTF8
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($npm) {
    Push-Location $OpenCodeDir
    try {
        & npm install --silent 2>$null
    } catch {
        Write-Host "  WARN: npm install failed. Run manually: cd $OpenCodeDir; npm install" -ForegroundColor DarkYellow
    }
    Pop-Location
} else {
    Write-Host "  WARN: npm not found. Install Node.js, then: cd $OpenCodeDir; npm install" -ForegroundColor DarkYellow
}

# ── 6. Install project-level files (unless -Global) ─────────────────────
if (-not $Global -and (Test-Path (Join-Path $RepoRoot ".git"))) {
    Write-Host ""
    Write-Host "[+] Also installing project files in $RepoRoot ..." -ForegroundColor Yellow

    New-Item -ItemType Directory -Path (Join-Path $RepoRoot ".ai-log") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $RepoRoot "scripts") -Force | Out-Null
    Set-Content -Path (Join-Path $RepoRoot ".ai-log\.gitkeep") -Value "" -NoNewline

    Copy-Item (Join-Path $ScriptsDir "log_hook.py") (Join-Path $RepoRoot "scripts\log_hook.py") -Force
    Copy-Item (Join-Path $ScriptsDir "_pyrun.sh") (Join-Path $RepoRoot "scripts\_pyrun.sh") -Force
    Copy-Item (Join-Path $ScriptsDir "_pyrun.ps1") (Join-Path $RepoRoot "scripts\_pyrun.ps1") -Force

    $Gitignore = Join-Path $RepoRoot ".gitignore"
    if (Test-Path $Gitignore) {
        $content = Get-Content $Gitignore -Raw
        if ($content -notmatch "^\.ai-log/") {
            Add-Content -Path $Gitignore -Value "`n.ai-log/"
        }
    } else {
        Set-Content -Path $Gitignore -Value ".ai-log/"
    }
    Write-Host "  Project files installed."
}

# ── Done ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "┌──────────────────────────────────────────────┐" -ForegroundColor Green
Write-Host "│  Done! Restart opencode to activate.         │" -ForegroundColor Green
Write-Host "└──────────────────────────────────────────────┘" -ForegroundColor Green
Write-Host ""
Write-Host "  Installed:"
Write-Host "    $PluginDir\ai-log.ts"
Write-Host "    $ScriptsDir\log_hook.py"
Write-Host "    $ScriptsDir\_pyrun.ps1"
Write-Host ""
Write-Host "  Logs go to: <project>\.ai-log\session.jsonl"
Write-Host ""
