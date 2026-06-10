import type { Plugin } from "@opencode-ai/plugin"
import { spawn } from "child_process"
import { appendFileSync, existsSync, mkdirSync } from "fs"
import { resolve, join } from "path"
import { homedir } from "os"

const HOME = homedir()
const SCRIPTS_DIR = resolve(HOME, ".config/opencode/scripts")
const LOG_SCRIPT = join(SCRIPTS_DIR, "log_hook.py")
const PYRUN = join(SCRIPTS_DIR, "_pyrun.sh")
const DEBUG_FILE = resolve(HOME, ".config/opencode/ai-log-debug.log")

function debug(msg: string) {
  try {
    mkdirSync(resolve(DEBUG_FILE, ".."), { recursive: true })
    appendFileSync(DEBUG_FILE, `[${new Date().toISOString()}] ${msg}\n`)
  } catch {}
}

function logToHook(data: Record<string, unknown>) {
  if (!existsSync(LOG_SCRIPT)) {
    debug(`LOG_SCRIPT not found: ${LOG_SCRIPT}`)
    return
  }

  const isWin = process.platform === "win32"
  try {
    let child: ReturnType<typeof spawn>
    if (isWin) {
      // Windows: use PowerShell to run _pyrun.ps1 (handles python discovery)
      const psRun = join(SCRIPTS_DIR, "_pyrun.ps1")
      child = spawn("powershell.exe", [
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", psRun, LOG_SCRIPT, "--tool=opencode",
      ], {
        stdio: ["pipe", "ignore", "ignore"],
        cwd: process.cwd(),
      })
    } else {
      child = spawn("bash", [PYRUN, LOG_SCRIPT, "--tool=opencode"], {
        stdio: ["pipe", "ignore", "ignore"],
        cwd: process.cwd(),
      })
    }
    child.stdin.write(JSON.stringify(data))
    child.stdin.end()
    child.on("error", (err) => debug(`spawn error: ${err.message}`))
    debug("spawned successfully")
  } catch (err: any) {
    debug(`spawn exception: ${err.message}`)
  }
}

debug("AI-log global plugin loaded")

const AiLogPlugin: Plugin = async (input) => {
  debug(`Plugin init, directory=${input?.directory}`)
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

      debug(`chat.message: role=${role}, len=${content.length}`)
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
