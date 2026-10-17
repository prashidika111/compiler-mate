import * as cp from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  InvestigationRequest,
  InvestigationResult,
  InteractionRequest,
  InteractionResponse,
  VerificationIPCRequest,
  VerificationIPCResponse
} from "./types";

export class EngineBridge {
  private outputChannel: vscode.OutputChannel;

  constructor(outputChannel: vscode.OutputChannel) {
    this.outputChannel = outputChannel;
  }

  /**
   * Resolves the Python executable path.
   */
  public async getPythonPath(): Promise<string> {
    const configPath = vscode.workspace
      .getConfiguration("compilermate")
      .get<string>("pythonPath");
    if (configPath && configPath.trim()) {
      return configPath.trim();
    }

    // Try ms-python extension API if installed
    try {
      const pythonExtension = vscode.extensions.getExtension("ms-python.python");
      if (pythonExtension) {
        if (!pythonExtension.isActive) {
          await pythonExtension.activate();
        }
        const api = pythonExtension.exports;
        if (api && api.environments) {
          const env = await api.environments.getActiveEnvironmentPath();
          if (env && env.path) {
            return env.path;
          }
        }
      }
    } catch (e) {
      this.outputChannel.appendLine(`[EngineBridge] Note: Could not query ms-python extension: ${e}`);
    }

    return process.platform === "win32" ? "python" : "python3";
  }

  /**
   * Resolves the directory path containing the compilermate_engine Python package.
   */
  public getEngineDirectory(extensionContext: vscode.ExtensionContext): string {
    // 1. Bundled inside extension (packaged VSIX installation)
    const bundledEngine = path.join(extensionContext.extensionPath, "engine");
    if (fs.existsSync(path.join(bundledEngine, "compilermate_engine", "__init__.py"))) {
      return bundledEngine;
    }

    // 2. Relative to extension development path (phase3/extension -> phase3/engine)
    const devEngine = path.resolve(extensionContext.extensionPath, "..", "engine");
    if (fs.existsSync(path.join(devEngine, "compilermate_engine", "__init__.py"))) {
      return devEngine;
    }

    // 3. Relative to workspace folders
    if (vscode.workspace.workspaceFolders) {
      for (const folder of vscode.workspace.workspaceFolders) {
        const wsEngine = path.join(folder.uri.fsPath, "phase3", "engine");
        if (fs.existsSync(path.join(wsEngine, "compilermate_engine", "__init__.py"))) {
          return wsEngine;
        }
      }
    }

    // Fallback to devEngine path
    return devEngine;
  }

  /**
   * Sends an investigation request to the Python engine over stdio IPC.
   */
  public async investigate(
    context: vscode.ExtensionContext,
    request: InvestigationRequest
  ): Promise<InvestigationResult> {
    const pythonPath = await this.getPythonPath();
    const engineDir = this.getEngineDirectory(context);
    const timeoutMs = vscode.workspace
      .getConfiguration("compilermate")
      .get<number>("timeoutMs", 8000);

    const payload = JSON.stringify(request);
    this.outputChannel.appendLine(
      `[EngineBridge] Dispatching diagnostic to Python engine (cmd: ${request.command}, diag: "${request.diagnostic.message}")`
    );

    return new Promise<InvestigationResult>((resolve) => {
      let isSettled = false;
      let stdoutData = "";
      let stderrData = "";

      const child = cp.spawn(
        pythonPath,
        ["-m", "compilermate_engine.cli", "investigate", "--json"],
        {
          cwd: engineDir,
          env: {
            ...process.env,
            PYTHONPATH: engineDir + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
            PYTHONIOENCODING: "utf-8",
            PYTHONUNBUFFERED: "1",
          },
        }
      );

      const timer = setTimeout(() => {
        if (!isSettled) {
          isSettled = true;
          try {
            child.kill();
          } catch {}
          this.outputChannel.appendLine(
            `[EngineBridge] Error: Engine process timed out after ${timeoutMs}ms.`
          );
          resolve({
            status: "error",
            category: "TIMEOUT",
            diagnostic: request.diagnostic,
            evidence: [],
            candidate_fixes: [],
            metadata: {},
            error_message: `Python engine timed out after ${timeoutMs}ms. Check compilermate.pythonPath in settings.`,
          });
        }
      }, timeoutMs);

      child.stdout.on("data", (chunk: Buffer) => {
        stdoutData += chunk.toString("utf-8");
      });

      child.stderr.on("data", (chunk: Buffer) => {
        const text = chunk.toString("utf-8");
        stderrData += text;
        this.outputChannel.append(`[Engine stderr] ${text}`);
      });

      child.on("error", (err: Error) => {
        if (!isSettled) {
          isSettled = true;
          clearTimeout(timer);
          this.outputChannel.appendLine(
            `[EngineBridge] Failed to launch Python engine: ${err.message}`
          );
          resolve({
            status: "error",
            category: "SPAWN_ERROR",
            diagnostic: request.diagnostic,
            evidence: [],
            candidate_fixes: [],
            metadata: { pythonPath, engineDir },
            error_message: `Failed to launch Python (${pythonPath}): ${err.message}. Ensure Python is installed and configured in compilermate.pythonPath.`,
          });
        }
      });

      child.on("close", (code: number | null) => {
        if (!isSettled) {
          isSettled = true;
          clearTimeout(timer);

          if (!stdoutData.trim()) {
            this.outputChannel.appendLine(
              `[EngineBridge] Process exited with code ${code} and empty stdout. stderr: ${stderrData}`
            );
            resolve({
              status: "error",
              category: "EMPTY_RESPONSE",
              diagnostic: request.diagnostic,
              evidence: [],
              candidate_fixes: [],
              metadata: { exitCode: code },
              error_message: `Python engine produced empty response (exit code ${code}). Stderr: ${stderrData || "none"}`,
            });
            return;
          }

          try {
            const parsed = JSON.parse(stdoutData) as InvestigationResult;
            this.outputChannel.appendLine(
              `[EngineBridge] Received status: ${parsed.status}, category: ${parsed.category}, fixes: ${parsed.candidate_fixes?.length || 0}`
            );
            resolve(parsed);
          } catch (jsonErr) {
            this.outputChannel.appendLine(
              `[EngineBridge] Malformed JSON from engine: ${jsonErr}\nRaw: ${stdoutData}`
            );
            resolve({
              status: "error",
              category: "MALFORMED_RESPONSE",
              diagnostic: request.diagnostic,
              evidence: [],
              candidate_fixes: [],
              metadata: { rawOutput: stdoutData },
              error_message: `Failed to parse Python engine output as JSON: ${jsonErr}`,
            });
          }
        }
      });

      try {
        child.stdin.write(payload, "utf-8");
        child.stdin.end();
      } catch (writeErr) {
        if (!isSettled) {
          isSettled = true;
          clearTimeout(timer);
          resolve({
            status: "error",
            category: "IPC_WRITE_ERROR",
            diagnostic: request.diagnostic,
            evidence: [],
            candidate_fixes: [],
            metadata: {},
            error_message: `Failed to write request to engine stdin: ${writeErr}`,
          });
        }
      }
    });
  }

  /**
   * Sends a two-way conversational interaction turn to the Python engine over stdio IPC.
   */
  public async interact(
    context: vscode.ExtensionContext,
    request: InteractionRequest
  ): Promise<InteractionResponse> {
    const pythonPath = await this.getPythonPath();
    const engineDir = this.getEngineDirectory(context);
    const timeoutMs = vscode.workspace
      .getConfiguration("compilermate")
      .get<number>("timeoutMs", 8000);

    const payload = JSON.stringify(request);
    this.outputChannel.appendLine(
      `[EngineBridge] Dispatching conversation turn to Python engine (user: "${request.user_message.slice(0, 60)}")`
    );

    return new Promise<InteractionResponse>((resolve) => {
      let isSettled = false;
      let stdoutData = "";
      let stderrData = "";

      const child = cp.spawn(
        pythonPath,
        ["-m", "compilermate_engine.cli", "interact", "--json"],
        {
          cwd: engineDir,
          env: {
            ...process.env,
            PYTHONPATH: engineDir + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
            PYTHONIOENCODING: "utf-8",
            PYTHONUNBUFFERED: "1",
          },
        }
      );

      const timer = setTimeout(() => {
        if (!isSettled) {
          isSettled = true;
          try {
            child.kill();
          } catch {}
          this.outputChannel.appendLine(
            `[EngineBridge] Error: Interaction process timed out after ${timeoutMs}ms.`
          );
          resolve({
            status: "error",
            message: `CompilerMate interaction timed out after ${timeoutMs}ms.`,
            error_message: `Timed out after ${timeoutMs}ms.`,
          });
        }
      }, timeoutMs);

      child.stdout.on("data", (chunk: Buffer) => {
        stdoutData += chunk.toString("utf-8");
      });

      child.stderr.on("data", (chunk: Buffer) => {
        const text = chunk.toString("utf-8");
        stderrData += text;
        this.outputChannel.append(`[Engine stderr] ${text}`);
      });

      child.on("error", (err: Error) => {
        if (!isSettled) {
          isSettled = true;
          clearTimeout(timer);
          this.outputChannel.appendLine(
            `[EngineBridge] Failed to launch interaction process: ${err.message}`
          );
          resolve({
            status: "error",
            message: `Failed to launch Python engine: ${err.message}`,
            error_message: err.message,
          });
        }
      });

      child.on("close", (code: number | null) => {
        if (!isSettled) {
          isSettled = true;
          clearTimeout(timer);

          if (!stdoutData.trim()) {
            this.outputChannel.appendLine(
              `[EngineBridge] Interaction exited with code ${code} and empty stdout. stderr: ${stderrData}`
            );
            resolve({
              status: "error",
              message: "Python engine produced an empty response.",
              error_message: `Exit code ${code}. Stderr: ${stderrData || "none"}`,
            });
            return;
          }

          try {
            const parsed = JSON.parse(stdoutData) as InteractionResponse;
            this.outputChannel.appendLine(
              `[EngineBridge] Interaction response received: status=${parsed.status}, action=${parsed.action || "none"}`
            );
            resolve(parsed);
          } catch (jsonErr) {
            this.outputChannel.appendLine(
              `[EngineBridge] Malformed interaction JSON from engine: ${jsonErr}\nRaw: ${stdoutData}`
            );
            resolve({
              status: "error",
              message: "Failed to parse Python engine response as JSON.",
              error_message: String(jsonErr),
            });
          }
        }
      });

      try {
        child.stdin.write(payload, "utf-8");
        child.stdin.end();
      } catch (writeErr) {
        if (!isSettled) {
          isSettled = true;
          clearTimeout(timer);
          resolve({
            status: "error",
            message: `Failed to write interaction request: ${writeErr}`,
            error_message: String(writeErr),
          });
        }
      }
    });
  }

  /**
   * Sends a deterministic multi-stage verification request to the Python engine over stdio IPC.
   */
  public async verify(
    context: vscode.ExtensionContext,
    request: VerificationIPCRequest
  ): Promise<VerificationIPCResponse> {
    const pythonPath = await this.getPythonPath();
    const engineDir = this.getEngineDirectory(context);
    const timeoutMs = vscode.workspace
      .getConfiguration("compilermate")
      .get<number>("timeoutMs", 8000);

    const payload = JSON.stringify(request);
    this.outputChannel.appendLine(
      `[EngineBridge] Dispatching verification request to Python engine (diag: "${request.diagnostic.message}", edits: ${request.edits.length})`
    );

    return new Promise<VerificationIPCResponse>((resolve) => {
      let isSettled = false;
      let stdoutData = "";
      let stderrData = "";

      const child = cp.spawn(
        pythonPath,
        ["-m", "compilermate_engine.cli", "verify", "--json"],
        {
          cwd: engineDir,
          env: {
            ...process.env,
            PYTHONPATH: engineDir + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
            PYTHONIOENCODING: "utf-8",
            PYTHONUNBUFFERED: "1",
          },
        }
      );

      const timer = setTimeout(() => {
        if (!isSettled) {
          isSettled = true;
          try {
            child.kill();
          } catch {}
          this.outputChannel.appendLine(
            `[EngineBridge] Error: Verification process timed out after ${timeoutMs}ms.`
          );
          resolve({
            status: "error",
            error_message: `Python verification engine timed out after ${timeoutMs}ms.`,
          });
        }
      }, timeoutMs);

      child.stdout.on("data", (chunk: Buffer) => {
        stdoutData += chunk.toString("utf-8");
      });

      child.stderr.on("data", (chunk: Buffer) => {
        const text = chunk.toString("utf-8");
        stderrData += text;
        this.outputChannel.append(`[Engine stderr] ${text}`);
      });

      child.on("error", (err: Error) => {
        if (!isSettled) {
          isSettled = true;
          clearTimeout(timer);
          this.outputChannel.appendLine(
            `[EngineBridge] Failed to launch verification process: ${err.message}`
          );
          resolve({
            status: "error",
            error_message: `Failed to launch Python (${pythonPath}): ${err.message}`,
          });
        }
      });

      child.on("close", (code: number | null) => {
        if (!isSettled) {
          isSettled = true;
          clearTimeout(timer);

          if (!stdoutData.trim()) {
            this.outputChannel.appendLine(
              `[EngineBridge] Verification process exited with code ${code} and empty stdout. stderr: ${stderrData}`
            );
            resolve({
              status: "error",
              error_message: `Python verification engine produced empty response (exit code ${code}). Stderr: ${stderrData || "none"}`,
            });
            return;
          }

          try {
            const parsed = JSON.parse(stdoutData) as VerificationIPCResponse;
            this.outputChannel.appendLine(
              `[EngineBridge] Verification response received: status=${parsed.status}, verif_status=${parsed.verification_report?.status || "unknown"}`
            );
            resolve(parsed);
          } catch (jsonErr) {
            this.outputChannel.appendLine(
              `[EngineBridge] Malformed verification JSON from engine: ${jsonErr}\nRaw: ${stdoutData}`
            );
            resolve({
              status: "error",
              error_message: `Failed to parse Python verification engine output as JSON: ${jsonErr}`,
            });
          }
        }
      });

      try {
        child.stdin.write(payload, "utf-8");
        child.stdin.end();
      } catch (writeErr) {
        if (!isSettled) {
          isSettled = true;
          clearTimeout(timer);
          resolve({
            status: "error",
            error_message: `Failed to write verification request to engine stdin: ${writeErr}`,
          });
        }
      }
    });
  }
}
