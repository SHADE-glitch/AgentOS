/**
 * opencode-aos-host — OpenCode Host Integration for Agent OS
 * 
 * Phase 6.0.7
 * 
 * This plugin integrates Agent OS with OpenCode as a Host.
 * It does NOT start a new OpenCode instance. It provides context to the current one.
 * 
 * Pipeline:
 *   OpenCode Plugin (this file)
 *     ↓ (calls adapter)
 *   AOS Host Adapter (Python)
 *     ↓ (calls existing AOS components)
 *   Router / Memory / Orchestrator
 *     ↓ (returns decision context)
 *   OpenCode Plugin
 *     ↓ (injects into system prompt)
 *   OpenCode Model (continues execution)
 * 
 * CRITICAL: No recursion. No new OpenCode instances.
 * 
 * Evidence Types:
 *   - host_integration: Events from Host Plugin → AOS Adapter → Router/Memory/Orchestrator
 *   - runtime_execution: Events from AOS → Runtime Adapter → Agent/Model (NOT USED HERE)
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { appendFileSync, mkdirSync, existsSync } from "node:fs";
import { join } from "node:path";

const execFileAsync = promisify(execFile);

// ── Configuration ────────────────────────────────────────────────
const AOS_ROOT = process.env.AGENT_OS_ROOT || "/home/shade/.agents";
const ADAPTER_PATH = `${AOS_ROOT}/runtime/hosts/opencode/aos_host_adapter.py`;
const PYTHON = process.env.PYTHON || "python3";
const TELEMETRY_DIR = join(AOS_ROOT, "runtime", "telemetry");
const HOST_EVENTS_FILE = join(TELEMETRY_DIR, "host-events.yaml");

// Ensure telemetry directory exists
if (!existsSync(TELEMETRY_DIR)) {
  mkdirSync(TELEMETRY_DIR, { recursive: true });
}

// Recursion guard environment variable
const RECURSION_ENV = "AOS_HOST_PLUGIN_ACTIVE";

// ── Telemetry ───────────────────────────────────────────────────
function generateId() {
  return Math.random().toString(36).substring(2, 10).toUpperCase();
}

function emitTelemetry(event) {
  const timestamp = new Date().toISOString();
  const eventWithMeta = {
    event_id: `EVT-${generateId()}`,
    timestamp,
    evidence_type: "host_integration",
    ...event
  };

  try {
    const yamlLine = [
      `  - event_id: "${eventWithMeta.event_id}"`,
      `    event_type: "${eventWithMeta.event_type}"`,
      `    timestamp: "${eventWithMeta.timestamp}"`,
      `    evidence_type: "${eventWithMeta.evidence_type}"`,
      ...Object.entries(eventWithMeta)
        .filter(([k]) => !['event_id', 'event_type', 'timestamp', 'evidence_type'].includes(k))
        .map(([k, v]) => {
          if (typeof v === 'string') return `    ${k}: "${v}"`;
          if (typeof v === 'number') return `    ${k}: ${v}`;
          if (typeof v === 'boolean') return `    ${k}: ${v ? 'true' : 'false'}`;
          if (Array.isArray(v)) return `    ${k}:\n${v.map(i => `      - "${i}"`).join('\n')}`;
          return `    ${k}: "${v}"`;
        })
    ].join('\n') + '\n';

    appendFileSync(HOST_EVENTS_FILE, yamlLine);
  } catch (err) {
    console.error("[aos-host] Telemetry write failed:", err.message);
  }

  return eventWithMeta;
}

// ── Adapter Call ─────────────────────────────────────────────────
async function callAOSAdapter(task, options = {}) {
  // Recursion guard
  if (process.env[RECURSION_ENV]) {
    console.error("[aos-host] Recursion detected, skipping AOS call");
    emitTelemetry({
      event_type: "host_recursion_detected",
      status: "skipped",
      reason: "recursion_detected"
    });
    return null;
  }

  const taskId = `HOST-${generateId()}`;
  const startTime = Date.now();

  try {
    process.env[RECURSION_ENV] = "1";

    emitTelemetry({
      event_type: "host_adapter_called",
      task_id: taskId,
      prompt_summary: task.slice(0, 200),
      session_id: options.sessionId || "",
      cwd: options.cwd || ""
    });

    const args = [
      ADAPTER_PATH,
      task,
      "--json",
      "--task-id", taskId,
    ];

    if (options.sessionId) args.push("--session", options.sessionId);
    if (options.cwd) args.push("--cwd", options.cwd);
    if (options.model) args.push("--model", options.model);
    if (options.provider) args.push("--provider", options.provider);
    if (options.memoryMode) args.push("--memory", options.memoryMode);

    const { stdout, stderr } = await execFileAsync(PYTHON, args, {
      timeout: 30_000,
      env: {
        ...process.env,
        AOS_HOST_PLUGIN_ACTIVE: "1",
      },
    });

    if (stderr) {
      console.error("[aos-host] Adapter stderr:", stderr.slice(0, 200));
    }

    const context = JSON.parse(stdout.trim());
    const latencyMs = Date.now() - startTime;

    emitTelemetry({
      event_type: "host_adapter_completed",
      task_id: taskId,
      aos_status: context.aos_status || "unknown",
      lead_agent: context.orchestration?.lead_agent || "general",
      memory_count: context.memory?.retrieved || 0,
      latency_ms: latencyMs,
      session_id: options.sessionId || "",
      cwd: options.cwd || ""
    });

    return context;
  } catch (err) {
    console.error("[aos-host] Adapter call failed:", err);
    const latencyMs = Date.now() - startTime;

    emitTelemetry({
      event_type: "host_fallback_triggered",
      task_id: taskId,
      fallback_reason: err.message || "adapter_error",
      latency_ms: latencyMs,
      session_id: options.sessionId || "",
      cwd: options.cwd || ""
    });

    return null;
  } finally {
    delete process.env[RECURSION_ENV];
  }
}

// ── System Prompt Builder ────────────────────────────────────────
function buildSystemInjection(context) {
  const lines = [];

  lines.push("");
  lines.push("## Agent OS Decision Context");
  lines.push("");

  const cls = context.decision?.classification;
  if (cls) {
    lines.push(`**Task Category**: ${cls.category}`);
    lines.push(`**Difficulty**: ${cls.difficulty}`);
    if (cls.roles?.length > 0) {
      lines.push(`**Recommended Role**: ${cls.roles[0]}`);
    }
  }

  if (context.memory?.retrieved > 0) {
    lines.push("");
    lines.push(`**Relevant Memories**: ${context.memory.retrieved} retrieved`);
    for (const mem of (context.memory.memories || []).slice(0, 3)) {
      lines.push(`- ${mem.memory_id}: ${(mem.content || "no content").slice(0, 100)}`);
    }
  }

  if (context.orchestration?.lead_agent && context.orchestration.lead_agent !== "general") {
    lines.push("");
    lines.push(`**Lead Agent Role**: ${context.orchestration.lead_agent}`);
  }

  if (context.warnings?.length > 0) {
    lines.push("");
    lines.push("**Warnings**:");
    for (const w of context.warnings) {
      lines.push(`- ⚠ ${w}`);
    }
  }

  if (context.instructions?.length > 0) {
    lines.push("");
    lines.push("**AOS Recommendations**:");
    for (const i of context.instructions) {
      lines.push(`- ${i}`);
    }
  }

  lines.push("");
  lines.push("Use this context to inform your approach. AOS does not execute tasks — it provides decision support.");
  lines.push("");

  return lines.join("\n");
}

// ── Plugin Export ────────────────────────────────────────────────
export const AosHostPlugin = async (ctx) => {
  emitTelemetry({
    event_type: "host_plugin_loaded",
    plugin_name: "opencode-aos-host",
    plugin_version: "0.2.0",
    pid: process.pid,
    cwd: ctx.directory || process.cwd(),
    session_id: ctx.sessionID || ""
  });

  console.log("[aos-host] Plugin loaded successfully");

  let lastContext = null;
  let lastPrompt = "";
  let lastSessionId = "";

  return {
    "chat.message": async (input, output) => {
      const userParts = output.parts.filter(
        (p) => p.type === "text" && p.text?.trim()
      );

      if (userParts.length === 0) return;

      const userText = userParts[0]?.text || "";
      if (!userText.trim()) return;

      if (process.env[RECURSION_ENV]) return;

      emitTelemetry({
        event_type: "host_prompt_received",
        prompt_summary: userText.slice(0, 200),
        prompt_length: userText.length,
        session_id: input.sessionID || "",
        cwd: ctx.directory || ""
      });

      const context = await callAOSAdapter(userText, {
        sessionId: input.sessionID,
        cwd: ctx.directory,
      });

      if (context) {
        lastContext = context;
        lastPrompt = userText;
        lastSessionId = input.sessionID || "";
        console.log(
          `[aos-host] Task ${context.task_id}: status=${context.aos_status}, role=${context.orchestration?.lead_agent}`
        );
      }
    },

    "experimental.chat.system.transform": async (input, output) => {
      if (!lastContext) return;
      if (!lastContext.aos_status || lastContext.aos_status === "fallback") return;

      const injection = buildSystemInjection(lastContext);

      if (output.system.length > 0) {
        output.system[output.system.length - 1] += injection;
      } else {
        output.system.push(injection);
      }

      emitTelemetry({
        event_type: "host_context_injected",
        task_id: lastContext.task_id || "",
        session_id: lastSessionId || "",
        injection_status: "success",
        aos_status: lastContext.aos_status,
        lead_agent: lastContext.orchestration?.lead_agent || "general"
      });

      lastContext = null;
      lastPrompt = "";
    },

    event: async ({ event }) => {
      if (event.type === "session.created") {
        console.log(`[aos-host] Session created: ${event.properties?.sessionID}`);
      }
    },

    dispose: async () => {
      lastContext = null;
      lastPrompt = "";
      lastSessionId = "";
    },
  };
};

export default AosHostPlugin;
