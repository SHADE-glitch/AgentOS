/**
 * opencode-aos-host — OpenCode Host Integration for Agent OS
 *
 * Phase 15 — Runtime Integration Repair
 *
 * This plugin integrates Agent OS with OpenCode as a Host.
 * It does NOT start a new OpenCode instance. It provides governance context
 * and delegates execution to the OpenCode model.
 *
 * Pipeline (REPAIRED):
 *   OpenCode user message
 *     ↓
 *   Host Plugin (this file)
 *     ↓ (governance_bridge.py --preflight)
 *   Agent OS Runtime (session, loop_id, retrieval, HybridRouter, skill, evidence_before)
 *     ↓ (governance context)
 *   Host Plugin
 *     ↓ (injects into system prompt)
 *   OpenCode Model (executes task with governance context)
 *     ↓
 *   Host Plugin (next message)
 *     ↓ (governance_bridge.py --postflight)
 *   Agent OS Runtime (evidence_after, failure detection, recovery, loop finalize)
 *
 * CRITICAL: No recursion. No new OpenCode instances.
 * Runtime stage is HOST_DELEGATED — OpenCode itself is the executor.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import {
  appendFileSync,
  mkdirSync,
  existsSync,
  writeFileSync,
  readFileSync,
  readdirSync,
  renameSync,
} from "node:fs";
import { join } from "node:path";
import type { Plugin } from "@opencode-ai/plugin";

const execFileAsync = promisify(execFile);

// ── Configuration ────────────────────────────────────────────────
const AOS_ROOT = process.env.AGENT_OS_ROOT || "/home/shade/.agents";
const GOVERNANCE_BRIDGE = `${AOS_ROOT}/runtime/hosts/opencode/governance_bridge.py`;
const FALLBACK_ADAPTER = `${AOS_ROOT}/runtime/hosts/opencode/aos_host_adapter.py`;
const PYTHON = process.env.PYTHON || "python3";
const TELEMETRY_DIR = join(AOS_ROOT, "runtime", "telemetry");
const HOST_EVENTS_FILE = join(TELEMETRY_DIR, "host-events.yaml");
const PENDING_POSTFLIGHT_DIR = join(AOS_ROOT, "runtime", "state", "pending-postflight");

// Ensure telemetry directory exists
if (!existsSync(TELEMETRY_DIR)) {
  mkdirSync(TELEMETRY_DIR, { recursive: true });
}

// Recursion guard environment variable
const RECURSION_ENV = "AOS_HOST_PLUGIN_ACTIVE";

// ── Telemetry ───────────────────────────────────────────────────
function generateId(): string {
  return Math.random().toString(36).substring(2, 10).toUpperCase();
}

function emitTelemetry(event: Record<string, any>): Record<string, any> {
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
  } catch (err: any) {
    console.error("[aos-host] Telemetry write failed:", err.message);
  }

  return eventWithMeta;
}

// ── Types ────────────────────────────────────────────────────────
interface AOSGovernanceContext {
  task_id: string;
  loop_id: string;
  session_id: string;
  aos_status: string;
  classification: {
    category: string;
    domains: string[];
    roles: string[];
    keywords: string[];
    difficulty: string;
  };
  router: {
    intent: string;
    lead_skill: string;
    support_skills: string[];
    confidence: string;
  };
  memory: {
    retrieved: number;
    memories: any[];
    hypotheses: any[];
  };
  skill: {
    lead_skill: string;
    support_skills: string[];
    skills_loaded: string[];
  };
  warnings: string[];
  artifacts: {
    loop_state: string;
  };
}

interface AOSPostflightContext {
  task_id: string;
  loop_id: string;
  session_id: string;
  aos_status: string;
  evidence_path: string;
  recovery: {
    failures_detected: number;
    final_status: string;
    plan: any;
  };
  final_status: string;
}

// ── Governance Bridge Call (Preflight) ───────────────────────────
async function callGovernancePreflight(
  task: string,
  options: {
    sessionId?: string;
    cwd?: string;
  } = {}
): Promise<AOSGovernanceContext | null> {
  if (process.env[RECURSION_ENV]) {
    console.error("[aos-host] Recursion detected, skipping AOS call");
    emitTelemetry({
      event_type: "host_recursion_detected",
      status: "skipped",
      reason: "recursion_detected"
    });
    return null;
  }

  const startTime = Date.now();

  try {
    process.env[RECURSION_ENV] = "1";

    const payload = JSON.stringify({
      task: task,
      session_id: options.sessionId || "",
      cwd: options.cwd || "",
    });

    emitTelemetry({
      event_type: "governance_preflight_called",
      prompt_summary: task.slice(0, 200),
      session_id: options.sessionId || "",
      cwd: options.cwd || ""
    });

    const { stdout, stderr } = await execFileAsync(PYTHON, [
      GOVERNANCE_BRIDGE,
      "--preflight",
      "--payload", payload,
    ], {
      timeout: 30_000,
      env: {
        ...process.env,
        AOS_HOST_PLUGIN_ACTIVE: "1",
      },
    });

    if (stderr) {
      console.error("[aos-host] Governance bridge stderr:", stderr.slice(0, 200));
    }

    const context = JSON.parse(stdout.trim()) as AOSGovernanceContext;
    const latencyMs = Date.now() - startTime;

    emitTelemetry({
      event_type: "governance_preflight_completed",
      task_id: context.task_id || "",
      loop_id: context.loop_id || "",
      session_id: context.session_id || "",
      aos_status: context.aos_status || "unknown",
      router_intent: context.router?.intent || "",
      lead_skill: context.router?.lead_skill || "general",
      memory_count: context.memory?.retrieved || 0,
      latency_ms: latencyMs,
      cwd: options.cwd || ""
    });

    return context;
  } catch (err) {
    console.error("[aos-host] Governance preflight failed:", err);
    const latencyMs = Date.now() - startTime;

    emitTelemetry({
      event_type: "governance_preflight_failed",
      fallback_reason: (err as Error).message || "preflight_error",
      latency_ms: latencyMs,
      session_id: options.sessionId || "",
      cwd: options.cwd || ""
    });

    return null;
  } finally {
    delete process.env[RECURSION_ENV];
  }
}

// ── Governance Bridge Call (Postflight) ──────────────────────────
async function callGovernancePostflight(
  taskId: string,
  loopId: string,
  options: {
    sessionId?: string;
    cwd?: string;
  } = {}
): Promise<AOSPostflightContext | null> {
  if (process.env[RECURSION_ENV]) {
    return null;
  }

  const startTime = Date.now();

  try {
    process.env[RECURSION_ENV] = "1";

    const payload = JSON.stringify({
      task_id: taskId,
      loop_id: loopId,
      session_id: options.sessionId || "",
      cwd: options.cwd || "",
    });

    emitTelemetry({
      event_type: "governance_postflight_called",
      task_id: taskId,
      loop_id: loopId,
      session_id: options.sessionId || "",
      cwd: options.cwd || ""
    });

    const { stdout, stderr } = await execFileAsync(PYTHON, [
      GOVERNANCE_BRIDGE,
      "--postflight",
      "--payload", payload,
    ], {
      timeout: 30_000,
      env: {
        ...process.env,
        AOS_HOST_PLUGIN_ACTIVE: "1",
      },
    });

    if (stderr) {
      console.error("[aos-host] Postflight stderr:", stderr.slice(0, 200));
    }

    const context = JSON.parse(stdout.trim()) as AOSPostflightContext;
    const latencyMs = Date.now() - startTime;

    emitTelemetry({
      event_type: "governance_postflight_completed",
      task_id: context.task_id || "",
      loop_id: context.loop_id || "",
      session_id: context.session_id || "",
      final_status: context.final_status || "",
      failures_detected: context.recovery?.failures_detected || 0,
      evidence_path: context.evidence_path || "",
      latency_ms: latencyMs,
    });

    return context;
  } catch (err) {
    console.error("[aos-host] Governance postflight failed:", err);
    const latencyMs = Date.now() - startTime;

    emitTelemetry({
      event_type: "governance_postflight_failed",
      task_id: taskId,
      loop_id: loopId,
      fallback_reason: (err as Error).message || "postflight_error",
      latency_ms: latencyMs,
    });

    return null;
  } finally {
    delete process.env[RECURSION_ENV];
  }
}

// ── Durable pending postflight (survives process death) ─────────
// Written BEFORE the postflight bridge is spawned so that a process killed
// mid-postflight leaves a durable record that the NEXT plugin load resumes.
function ensurePendingDir(): void {
  if (!existsSync(PENDING_POSTFLIGHT_DIR)) {
    mkdirSync(PENDING_POSTFLIGHT_DIR, { recursive: true });
  }
}

function pendingMarkerPath(loopId: string): string {
  return join(PENDING_POSTFLIGHT_DIR, `${loopId}.json`);
}

function writeJsonAtomic(loopId: string, data: Record<string, any>): void {
  ensurePendingDir();
  const tmp = `${pendingMarkerPath(loopId)}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(data, null, 2));
  renameSync(tmp, pendingMarkerPath(loopId));
}

function writePendingMarker(
  taskId: string,
  loopId: string,
  sessionId: string,
  cwd: string
): void {
  const now = new Date().toISOString();
  // Claimed as "running" by THIS process (pid recorded) before the bridge is
  // spawned. A concurrent process's resume skips markers owned by a live pid;
  // if this process dies mid-postflight the marker survives and the next
  // plugin load resumes it.
  const marker = {
    task_id: taskId,
    loop_id: loopId,
    session_id: sessionId,
    cwd,
    status: "running",
    attempts: 0,
    created_at: now,
    updated_at: now,
    last_error: null,
    final_status: null,
    evidence_path: null,
    pid: process.pid,
    started_at: now,
  };
  writeJsonAtomic(loopId, marker);
}

function readPendingMarkers(): Record<string, any>[] {
  ensurePendingDir();
  const markers: Record<string, any>[] = [];
  for (const fname of readdirSync(PENDING_POSTFLIGHT_DIR)) {
    if (!fname.endsWith(".json") || fname.includes(".tmp")) continue;
    try {
      const raw = readFileSync(join(PENDING_POSTFLIGHT_DIR, fname), "utf-8");
      const parsed = JSON.parse(raw);
      if (parsed && parsed.loop_id) markers.push(parsed);
    } catch {
      // skip unreadable marker
    }
  }
  return markers;
}

function updatePendingMarker(loopId: string, patch: Record<string, any>): void {
  const path = pendingMarkerPath(loopId);
  if (!existsSync(path)) return;
  try {
    const current = JSON.parse(readFileSync(path, "utf-8"));
    writeJsonAtomic(loopId, { ...current, ...patch, updated_at: new Date().toISOString() });
  } catch {
    // ignore update failures; the python side also owns the marker lifecycle
  }
}

// In-process guard so duplicate triggers (session.idle + dispose + next
// message) never spawn concurrent postflight bridges for the same loop.
const inflightPostflights = new Set<string>();

async function runPostflightDurable(
  taskId: string,
  loopId: string,
  sessionId: string,
  cwd: string
): Promise<Record<string, any> | null> {
  if (!taskId || !loopId) return null;
  if (inflightPostflights.has(loopId)) return null; // idempotent in-process guard
  inflightPostflights.add(loopId);
  try {
    // 1. Durable marker written BEFORE the bridge spawn. If this process dies
    //    while the bridge is running, the marker survives and the next plugin
    //    load (--postflight-resume) completes the finalization.
    writePendingMarker(taskId, loopId, sessionId, cwd);

    // 2. Bridge call. The bridge (governance_bridge.py) is itself idempotent:
    //    an already-finalized loop is never finalized twice.
    const result = await callGovernancePostflight(taskId, loopId, { sessionId, cwd });
    if (result) {
      updatePendingMarker(loopId, {
        status: "completed",
        final_status: result.final_status || "",
        evidence_path: result.evidence_path || "",
      });
    } else {
      updatePendingMarker(loopId, {
        status: "failed",
        last_error: "governance_bridge returned no result",
      });
    }
    return result;
  } catch (err) {
    updatePendingMarker(loopId, {
      status: "failed",
      last_error: (err as Error)?.message || "postflight_error",
    });
    return null;
  } finally {
    inflightPostflights.delete(loopId);
  }
}

function pidAlive(pid: number | null | undefined): boolean {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err: any) {
    return err?.code === "EPERM"; // exists but owned by another user
  }
}

async function resumePendingPostflights(): Promise<void> {
  // Called once on plugin load. Completes postflights that a previous process
  // left pending (crash / terminal closed mid-postflight). Markers owned by a
  // LIVE pid are skipped (that process is still finalizing them).
  let markers: Record<string, any>[] = [];
  try {
    markers = readPendingMarkers();
  } catch {
    return;
  }
  for (const m of markers) {
    if (m.status === "completed") continue;
    if (m.status === "running" && pidAlive(m.pid)) continue; // still in flight
    console.log(`[aos-host] Resuming pending postflight: ${m.loop_id}`);
    try {
      await runPostflightDurable(m.task_id, m.loop_id, m.session_id, m.cwd);
    } catch (err) {
      console.error(`[aos-host] Resume failed for ${m.loop_id}:`, err);
    }
  }
}

let resumeScheduledForProcess = false;

function scheduleResumePendingPostflights(): void {
  if (resumeScheduledForProcess) return;
  resumeScheduledForProcess = true;
  // Give the session a moment to settle before claiming orphaned loops; the
  // python-side finalization guard keeps this safe even if a live loop exists.
  setTimeout(() => {
    resumePendingPostflights().catch((err) => {
      console.error("[aos-host] Pending-postflight resume failed:", err);
    });
  }, 3000);
}

// ── System Prompt Builder ────────────────────────────────────────
function buildSystemInjection(context: AOSGovernanceContext): string {
  const lines: string[] = [];

  lines.push("");
  lines.push("## Agent OS Runtime Context");
  lines.push("");

  // Session identity
  lines.push(`Session: ${context.session_id || "N/A"} | Loop: ${context.loop_id || "N/A"}`);
  lines.push("");

  // Task classification
  const cls = context.classification;
  if (cls) {
    lines.push(`**Task Category**: ${cls.category || "unknown"}`);
    lines.push(`**Difficulty**: ${cls.difficulty || "medium"}`);
    if (cls.roles && cls.roles.length > 0) {
      lines.push(`**Recommended Roles**: ${cls.roles.join(", ")}`);
    }
  }

  // Router decision
  const router = context.router;
  if (router) {
    if (router.lead_skill && router.lead_skill !== "general") {
      lines.push(`**Lead Role**: ${router.lead_skill}`);
    }
    if (router.support_skills && router.support_skills.length > 0) {
      lines.push(`**Support Roles**: ${router.support_skills.join(", ")}`);
    }
    if (router.intent) {
      lines.push(`**Intent**: ${router.intent}`);
    }
    if (router.confidence) {
      lines.push(`**Confidence**: ${router.confidence}`);
    }
  }

  // Memory
  if (context.memory && context.memory.retrieved > 0) {
    lines.push("");
    lines.push(`**Relevant Memories**: ${context.memory.retrieved} retrieved`);
    for (const mem of (context.memory.memories || []).slice(0, 3)) {
      lines.push(`- ${mem.memory_id}: ${(mem.content || "").slice(0, 100) || "no content"}`);
    }
  }

  // Skills loaded
  if (context.skill && context.skill.skills_loaded && context.skill.skills_loaded.length > 0) {
    lines.push("");
    lines.push(`**Skills Loaded**: ${context.skill.skills_loaded.join(", ")}`);
  }

  // Warnings
  if (context.warnings && context.warnings.length > 0) {
    lines.push("");
    lines.push("**Warnings**:");
    for (const w of context.warnings) {
      lines.push(`- ${w}`);
    }
  }

  lines.push("");
  lines.push("Agent OS runs as a governance/runtime layer. You remain the single tool executor (Read/Edit/Grep/Shell). Use the routing, memory, and role context above to inform your approach.");
  lines.push("");

  return lines.join("\n");
}

// ── Plugin Export ────────────────────────────────────────────────
export const AosHostPlugin: Plugin = async (ctx) => {
  emitTelemetry({
    event_type: "host_plugin_loaded",
    plugin_name: "opencode-aos-host",
    plugin_version: "0.3.0",
    pid: process.pid,
    cwd: ctx.directory || process.cwd(),
    session_id: ctx.sessionID || ""
  });

  console.log("[aos-host] Plugin loaded (Phase 15 — governance bridge)");

  let lastContext: AOSGovernanceContext | null = null;
  let lastTaskId: string = "";
  let lastLoopId: string = "";
  let lastSessionId: string = "";

  // The task whose postflight is still pending (set at preflight, cleared
  // once finalization has run or been durably queued).
  let prevTaskId: string = "";
  let prevLoopId: string = "";
  let prevSessionId: string = "";

  // Finalize the current task's loop through the durable runner. Idempotent:
  // duplicate triggers (session.idle + dispose + next message) are collapsed
  // by the in-process inflight guard and by the python-side finalization guard.
  const finalizeCurrentTask = async (eventSessionId?: string): Promise<void> => {
    if (!prevTaskId || !prevLoopId) return;
    // Only finalize when the event belongs to the task's own session.
    if (eventSessionId && prevSessionId && eventSessionId !== prevSessionId) return;
    const taskId = prevTaskId;
    const loopId = prevLoopId;
    const sessionId = prevSessionId;
    // Clear bookkeeping immediately so repeated events cannot double-fire;
    // the durable marker + python guard prevent any duplicate finalization.
    prevTaskId = "";
    prevLoopId = "";
    prevSessionId = "";
    console.log(`[aos-host] Finalizing task ${taskId} (loop ${loopId})`);
    await runPostflightDurable(taskId, loopId, sessionId, ctx.directory);
  };

  // Resume postflights left pending by a crashed/interrupted process. Runs
  // once per process shortly after the plugin loads.
  scheduleResumePendingPostflights();

  return {
    "chat.message": async (input, output) => {
      // Postflight for the previous task (this user message means the previous
      // task's turn has ended). Falls back when session.idle was not observed.
      await finalizeCurrentTask(input.sessionID);

      const userParts = output.parts.filter(
        (p) => p.type === "text" && (p as any).text?.trim()
      );

      if (userParts.length === 0) return;

      const userText = (userParts[0] as any).text || "";
      if (!userText.trim()) return;

      if (process.env[RECURSION_ENV]) return;

      emitTelemetry({
        event_type: "host_prompt_received",
        prompt_summary: userText.slice(0, 200),
        prompt_length: userText.length,
        session_id: input.sessionID || "",
        cwd: ctx.directory || ""
      });

      // ── Preflight: Governance Bridge ──
      const context = await callGovernancePreflight(userText, {
        sessionId: input.sessionID,
        cwd: ctx.directory,
      });

      if (context) {
        lastContext = context;
        lastTaskId = context.task_id || "";
        lastLoopId = context.loop_id || "";
        lastSessionId = context.session_id || "";

        // Postflight is finalized when this task's turn completes.
        prevTaskId = lastTaskId;
        prevLoopId = lastLoopId;
        prevSessionId = lastSessionId;

        console.log(
          `[aos-host] Preflight: task=${context.task_id}, loop=${context.loop_id}, ` +
          `session=${context.session_id}, status=${context.aos_status}, ` +
          `router=${context.router?.intent || "?"}, ` +
          `lead=${context.router?.lead_skill || "?"}, ` +
          `memory=${context.memory?.retrieved || 0}`
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
        loop_id: lastContext.loop_id || "",
        session_id: lastContext.session_id || "",
        injection_status: "success",
        aos_status: lastContext.aos_status,
        router_intent: lastContext.router?.intent || "",
        lead_skill: lastContext.router?.lead_skill || "general",
        memory_count: lastContext.memory?.retrieved || 0,
      });

      lastContext = null;
    },

    event: async ({ event }) => {
      if (event.type === "session.created") {
        console.log(`[aos-host] Session created: ${event.properties?.sessionID}`);
      }
      // Task completion signal: the session finished processing the user's
      // message (model turn done). Runs postflight immediately — it no longer
      // waits for a future chat.message.
      if (event.type === "session.idle") {
        await finalizeCurrentTask(event.properties?.sessionID);
      }
    },

    dispose: async () => {
      // Last chance: finalize the current task before the process exits.
      await finalizeCurrentTask();
      lastContext = null;
      prevTaskId = "";
      prevLoopId = "";
      prevSessionId = "";
    },
  };
};

export default AosHostPlugin;