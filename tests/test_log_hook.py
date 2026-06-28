import json
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def run_log_hook(payload: dict[str, str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    # Inherit the parent environment so shared-library paths (e.g. LD_LIBRARY_PATH)
    # and other runner-specific variables are available to the subprocess.
    env = os.environ.copy()
    env["AI_LOG_DIR"] = str(tmp_path)
    
    # Resolve sys.executable to its real path to bypass dynamic linker $ORIGIN issues
    # that occur in CI when executing a python symlink created by uv.
    python_exe = os.path.realpath(sys.executable)
    
    return subprocess.run(
        [python_exe, "scripts/log_hook.py", "--tool=codex"],
        cwd=ROOT_DIR,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_codex_stop_hook_does_not_write_stdout(tmp_path: Path) -> None:
    result = run_log_hook(
        {
            "hook_event_name": "Stop",
            "session_id": "debug-session",
            "transcript_path": "/tmp/transcript.jsonl",
        },
        tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_codex_prompt_hook_logs_without_stdout(tmp_path: Path) -> None:
    result = run_log_hook(
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "debug-session",
            "prompt": "Set up the backend.",
        },
        tmp_path,
    )

    log_file = tmp_path / "session.jsonl"

    assert result.returncode == 0
    assert result.stdout == ""
    assert log_file.exists()
