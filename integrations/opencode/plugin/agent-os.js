// Agent OS plugin for OpenCode — the advisory seam, nothing more.
//
// Three hooks, and each one has exactly one job:
//   chat.message                          ask the engine for context (preflight)
//   experimental.chat.system.transform    append our own system element
//   event (session.idle / session.error) report the run back (postflight)
//
// What it deliberately never does: it does not edit another plugin's system
// element, never writes to index 0 (DCP reads that slot to decide whether a call
// is internal and skips its whole pruning pass if it is), never drops text that
// another plugin appended after our close tag, does not touch
// ~/.config/opencode/**, does not read the skill tracker's database, and does not
// block the prompt. Anything it cannot answer in time says nothing instead.
//
// Non-interference here is a property of the code, not of the install: with
// AGENT_OS_ROOT unset the plugin loads, does nothing, and the system array is
// byte-for-byte what it would be without it. That is the case tests/js/plugin.test.mjs pins.

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

// One transport for every engine call. `execFile`'s `input` option is *not* used:
// it was measured hanging in this environment — the child never saw EOF and the
// call only ended at the timeout, which for an advisor means "say nothing,
// forever, silently". spawn + explicit write/end is unambiguous about who closes
// the pipe, and the kill on timeout is ours rather than implicit.
function run(bin, args, input, timeoutMs) {
  return new Promise((resolve, reject) => {
    const child = spawn(bin, args, { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      child.kill("SIGKILL");
      const error = new Error("timeout");
      error.code = "ETIMEDOUT";
      reject(error);
    }, timeoutMs);

    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("error", (error) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      // The engine answers exit code 3 for a request it refuses, and still
      // prints a document it expects the host to read. So a non-zero code is not
      // a reason to throw away the answer.
      resolve({ stdout, stderr, code });
    });
    child.stdin.write(input ?? "");
    child.stdin.end();
  });
}

const ID = "agent-os";
const OPEN = "<agent_os>";
const CLOSE = "</agent_os>";

function settings() {
  const root = (process.env.AGENT_OS_ROOT || "").trim();
  return {
    root,
    bin: (process.env.AOS_BIN || path.join(root, "bin", "aos")).trim(),
    timeoutMs: Number(process.env.AOS_TIMEOUT_MS || 1200) || 1200,
    enabled: root !== "" && existsSync(path.join(root, "bin", "aos")),
  };
}

// The engine is the only thing this plugin talks to, and only through the same
// stdin/stdout contract a human uses. No file formats are guessed at: the session
// to loop lookup goes through `aos pending`, not through the store's internals.
async function ask(cfg, phase, payload) {
  const child = await run(cfg.bin, [phase, "--payload-stdin"], JSON.stringify(payload), cfg.timeoutMs);
  const text = (child.stdout || "").trim();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    // A document we cannot parse is a reason to say nothing, never a crash: the
    // host still has to finish the turn.
    return null;
  }
}

function userText(output) {
  const parts = (output && output.parts) || [];
  return parts
    .filter((part) => part && part.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n")
    .trim();
}

// The run's own answer, if the host told us whose text it was. Role resolution comes
// from `message.updated`; without it a text part could be the user's prompt, and filing
// the question as the answer is the exact failure defect AG describes. So: unknown owner
// means nothing is reported, rather than a guess dressed up as evidence.
//
// This is material for the human reading the proposal, never a verdict input — the engine
// weights `response_summary` at 0.00 (pinned by tests/test_outcome.py), and the value is
// capped here so a long answer cannot ride into the store whole.
function assistantText(entry) {
  const roles = entry && entry.msgRoles;
  const texts = entry && entry.texts;
  if (!(roles instanceof Map) || !(texts instanceof Map)) return "";
  const said = [];
  for (const [messageID, role] of roles) {
    if (role === "assistant" && texts.get(messageID)) said.push(texts.get(messageID));
  }
  return said.join("\n").trim().slice(0, 500);
}

// One hook that throws takes the turn down with it. Fail-open is the whole point
// of an advisor: the host's own work must never depend on us agreeing.
function safe(name, cfg, state, fn) {
  return async function guarded(...args) {
    try {
      await fn(...args);
    } catch (err) {
      const why = err && err.code === "ETIMEDOUT" ? "timeout" : "error";
      state.failures = (state.failures || 0) + 1;
      if (process.env.AOS_PLUGIN_DEBUG) {
        process.stderr.write(`${ID}: ${name} ${why}: ${err && err.message}\n`);
      }
    }
  };
}

// Failure is only half of what an operator needs. With every path failing open,
// "the engine had nothing", "the hook threw" and "the plugin was inert" are all
// the same silence — so success is recorded too, in the same place, under the same
// switch. Keys, indices and counts only: a task or a memory body has no business in
// a log line, and the plugin is not permitted to write one anywhere else.
function note(text) {
  if (process.env.AOS_PLUGIN_DEBUG) process.stderr.write(`${ID}: ${text}\n`);
}

export default {
  id: ID,
  server: async (input) => {
    const cfg = settings();
    const state = { sessions: new Map(), failures: 0 };
    const directory =
      (input && (input.directory || (input.project && input.project.directory))) || "";
    if (!cfg.enabled) note("disabled: AGENT_OS_ROOT unset, every hook will no-op");

    const remember = (sessionID, patch) => {
      const current = state.sessions.get(sessionID) || {};
      state.sessions.set(sessionID, { ...current, ...patch });
      return state.sessions.get(sessionID);
    };

    return {
      "chat.message": safe("chat.message", cfg, state, async (hookInput, output) => {
        if (!cfg.enabled) return;
        const sessionID = hookInput && hookInput.sessionID;
        if (!sessionID) return;
        const task = userText(output);
        if (!task) {
          // A message of only file parts is a real case, and it is not the same
          // thing as the engine having nothing to say.
          note("chat.message skipped: no text part in this message");
          return;
        }

        const model = hookInput && hookInput.model;
        const doc = await ask(cfg, "preflight", {
          schema_version: "1.2",
          phase: "preflight",
          task,
          session_id: sessionID,
          cwd: directory,
          provider: "host_delegate",
          // Which model is about to do the work. The engine keeps it as provenance,
          // and a lesson learned under one model is evidence about that run — not a
          // fact that transfers untouched to another.
          model: model && model.modelID ? `${model.providerID || ""}/${model.modelID}` : "",
        });
        if (!doc) {
          note("preflight returned no document: the engine said nothing or said it in no JSON");
          return;
        }
        if (!doc.loop_id) {
          // Degraded is not empty. There is no loop to close, which is a different
          // fact from "the loop opened and recalled nothing" — and only the operator
          // can tell them apart unless someone writes it down.
          note(`preflight degraded status=${doc.aos_status || "-"} warnings=${(doc.warnings || []).length}`);
          return;
        }

        const text = (doc.memory && doc.memory.injection && doc.memory.injection.text) || "";
        remember(sessionID, {
          loopId: doc.loop_id,
          taskId: doc.task_id,
          sessionKey: doc.session_id || sessionID,
          task,
          cwd: directory,
          text,
          // Counts stay unknown until something actually reports them. A zero
          // here would be a claim that nothing went wrong, and the engine would
          // read that as evidence.
          toolErrors: null,
          sessionError: null,
          interrupted: null,
          reported: false,
        });
        note(`preflight ok loop=${doc.loop_id} chars=${text.length}`);
      }),

      "experimental.chat.system.transform": safe("system.transform", cfg, state, async (hookInput, output) => {
        if (!cfg.enabled) return;
        const sessionID = hookInput && hookInput.sessionID;
        const entry = sessionID ? state.sessions.get(sessionID) : null;
        if (!entry || !entry.text) return;

        // Additive only: our element goes on the end, and no existing element is
        // read, reordered, joined or removed. If a block is already in place
        // (retry, or a re-run of the same turn) it is replaced in place rather
        // than duplicated.
        //
        // "In place" has to mean *our part of it*. Another plugin may have appended
        // into the same element — `@tarquinen/opencode-dcp` writes into
        // `system[len - 1]` rather than pushing its own — so the replacement keeps
        // whatever sits after our close tag. Dropping that suffix would make us the
        // plugin that silently deletes a neighbour's prompt.
        const ours = output.system.findIndex(
          (block) => typeof block === "string" && block.startsWith(OPEN),
        );
        if (ours >= 0 && output.system[ours].includes(CLOSE)) {
          const block = output.system[ours];
          const suffix = block.slice(block.indexOf(CLOSE) + CLOSE.length);
          const next = entry.text + suffix;
          if (block === next) {
            note(`system already in place index=${ours} len=${entry.text.length} suffix=${suffix.length}`);
            return;
          }
          output.system[ours] = next;
          note(`system replaced index=${ours} len=${entry.text.length} suffix=${suffix.length}`);
          return;
        }
        output.system.push(entry.text);
        note(`system appended index=${output.system.length - 1} len=${entry.text.length}`);
      }),

      "tool.execute.after": safe("tool.execute.after", cfg, state, async (hookInput, output) => {
        if (!cfg.enabled) return;
        const sessionID = hookInput && hookInput.sessionID;
        const entry = sessionID ? state.sessions.get(sessionID) : null;
        if (!entry) return;
        // Only a stated error counts. The shape of a tool result is opencode's
        // business, and guessing at it is how a probe ends up firing forever on
        // nothing — so an unrecognised shape leaves the count unknown instead of
        // reporting a clean run.
        const failed = Boolean(
          (output && (output.error || (output.metadata && output.metadata.error))) ||
            (hookInput && hookInput.error),
        );
        if (failed) entry.toolErrors = (entry.toolErrors || 0) + 1;
        // Which shape the host actually hands us here is not something a fixture can
        // settle, and an error detector that silently never fires is worse than no
        // detector. Record the field *names* — never the tool's output, which is
        // somebody's work and somebody else's secrets — so a live run answers the
        // question once, in the log, instead of in speculation.
        note(
          `tool seen tool=${(hookInput && hookInput.tool) || "-"} keys=[${
            output ? Object.keys(output).sort().join(",") : ""
          }] metadata_keys=[${output && output.metadata ? Object.keys(output.metadata).sort().join(",") : ""}] failed=${failed}`,
        );
      }),

      event: safe("event", cfg, state, async (hookInput) => {
        if (!cfg.enabled) return;
        const event = (hookInput && hookInput.event) || {};
        const sessionID = event.properties && event.properties.sessionID;
        if (!sessionID) return;

        if (event.type === "session.error") {
          const message = (event.properties && event.properties.error) || "session error";
          remember(sessionID, { sessionError: String(message).slice(0, 500) });
          return;
        }
        if (event.type === "message.updated") {
          // Whose text is this? Without the answer, a text part is indistinguishable from the
          // user's own prompt, and the prompt must never be filed as the run's response.
          const info = event.properties && event.properties.info;
          if (!info || !info.id) return;
          const current = state.sessions.get(sessionID) || {};
          const roles = current.msgRoles instanceof Map ? current.msgRoles : new Map();
          roles.set(String(info.id), String(info.role || ""));
          while (roles.size > 32) roles.delete(roles.keys().next().value);
          remember(sessionID, { msgRoles: roles });
          return;
        }
        if (event.type === "message.part.updated") {
          const part = event.properties && event.properties.part;
          if (!part || part.type !== "text" || !part.messageID) return;
          const text = typeof part.text === "string" ? part.text : "";
          if (!text.trim()) return;
          const current = state.sessions.get(sessionID) || {};
          const texts = current.texts instanceof Map ? current.texts : new Map();
          const seen = texts.get(part.messageID) || "";
          texts.set(part.messageID, (seen + text).slice(0, 4000));
          while (texts.size > 16) texts.delete(texts.keys().next().value);
          remember(sessionID, { texts });
          return;
        }
        if (event.type === "session.idle") await report(sessionID);
      }),

      dispose: async () => {
        state.sessions.clear();
      },
    };

    // The run ended. Everything known about it goes back through the same
    // contract; the engine decides what the outcome was, and a run nobody
    // described lands in the human queue instead of being called a success.
    async function report(sessionID) {
      let entry = state.sessions.get(sessionID);

      if (!entry || !entry.loopId) {
        // The plugin restarted, or the session opened while it was down. The
        // engine can still name the loop for that session — and it is asked
        // through its own command line rather than by reading the store's files,
        // because guessing another component's format is how a probe ends up
        // firing on nothing forever.
        const found = await lookup(cfg, sessionID);
        if (!found || !found.loop) return;
        entry = remember(sessionID, {
          loopId: found.loop.loop_id,
          taskId: found.loop.task_id,
          sessionKey: found.loop.session_id || sessionID,
          cwd: found.loop.cwd || directory,
          toolErrors: null,
          sessionError: null,
          interrupted: null,
          reported: false,
        });
      }
      if (!entry || entry.reported) return;
      entry.attempts = (entry.attempts || 0) + 1;

      const signals = {};
      if (entry.toolErrors !== null && entry.toolErrors !== undefined) signals.tool_errors = entry.toolErrors;
      if (entry.sessionError) signals.session_error = entry.sessionError;
      if (entry.interrupted !== null && entry.interrupted !== undefined) signals.user_interrupted = entry.interrupted;
      const answer = assistantText(entry);
      if (answer) signals.response_summary = answer;

      const answered = await ask(cfg, "postflight", {
        schema_version: "1.2",
        phase: "postflight",
        task_id: entry.taskId,
        loop_id: entry.loopId,
        session_id: entry.sessionKey || sessionID,
        cwd: entry.cwd || directory,
        provider: "host_delegate",
        signals,
      });
      if (!answered) {
        // Silence from the engine is not "reported". The run ends here or later, and
        // another event costs the host nothing — but a dead engine must not turn this
        // into an endless retry, so the attempts are bounded and the last one is said
        // out loud. Either way the pending record stays behind, which is the trace
        // `aos pending` and `doctor` exist to surface.
        note(`postflight unanswered loop=${entry.loopId} attempt=${entry.attempts}`);
        if (entry.attempts >= 3) {
          entry.reported = true;
          note(
            `postflight abandoned loop=${entry.loopId} after ${entry.attempts} attempts; ` +
              "the loop stays open in the store and `aos pending` will show it",
          );
        }
        return;
      }
      entry.reported = true;
      note(
        `postflight sent loop=${entry.loopId} signals=${Object.keys(signals).length}` +
          ` answered=true` + (answer ? ` response_summary chars=${answer.length}` : ""),
      );
      state.sessions.delete(sessionID);
    }
  },
};

// `aos pending --session <id> --json` is the only way this plugin resolves a
// session back to a loop after a restart. Flags rather than a payload on purpose:
// the shape of that answer is asserted by the Python suite, so it cannot drift
// out from under this call without a test failing.
async function lookup(cfg, sessionID) {
  const child = await run(
    cfg.bin,
    ["pending", "--session", String(sessionID), "--json"],
    "",
    cfg.timeoutMs,
  ).catch(() => null);
  if (!child || !child.stdout) return null;
  try {
    const doc = JSON.parse(child.stdout);
    return doc && doc.found ? doc : null;
  } catch {
    return null;
  }
}
