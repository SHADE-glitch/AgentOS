/**
 * AOS Adapter Bridge
 * 
 * Convenience module for calling the AOS Host Adapter from Node.js.
 * This is used by the OpenCode plugin to communicate with AOS.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const AOS_ROOT = process.env.AGENT_OS_ROOT || "/home/shade/.agents";
const ADAPTER_PATH = `${AOS_ROOT}/runtime/hosts/opencode/aos_host_adapter.py`;
const PYTHON = process.env.PYTHON || "python3";

/**
 * Call the AOS Host Adapter to get decision context for a task.
 * 
 * @param task - Task description
 * @param options - Optional parameters
 * @returns Decision context or null if AOS is unavailable
 */
export async function getDecisionContext(task, options = {}) {
  const args = [ADAPTER_PATH, task, "--json"];

  if (options.sessionId) args.push("--session", options.sessionId);
  if (options.cwd) args.push("--cwd", options.cwd);
  if (options.model) args.push("--model", options.model);
  if (options.provider) args.push("--provider", options.provider);
  if (options.memoryMode) args.push("--memory", options.memoryMode);

  try {
    const { stdout } = await execFileAsync(PYTHON, args, {
      timeout: 30_000,
    });
    return JSON.parse(stdout.trim());
  } catch {
    return null;
  }
}
