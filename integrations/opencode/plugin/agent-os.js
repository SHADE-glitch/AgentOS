// Agent OS plugin for OpenCode — the advisory seam, nothing more.
//
// Four hooks that do work, plus the event switch that closes the loop:
//   chat.message                          ask the engine for context (preflight)
//   experimental.chat.system.transform    append our own system element
//   tool.execute.after                    keep an ordered account of what was tried
//   event (session.idle / session.error)  report the run back (postflight)
//   dispose                               forget the sessions we were watching
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

// The engine's postflight is not on the turn's critical path, and it can legitimately run long:
// its `validate` stage may execute the project's own build, which the engine budgets up to 300 s
// for (`aos/core/validation/code_validator.py`). Killing it at this plugin's much smaller budget
// loses the entire loop — `_run_postflight` saves only at the end — so a postflight that outlives
// the budget is *released* rather than killed: it is detached into its own process group, its
// pipes are drained so a chatty engine cannot block on a full buffer, and the host stops waiting.
// The engine finishes and saves on its own; `aos pending` and `doctor` remain the place a genuinely
// dead engine shows up. Preflight is the opposite case — it is on the critical path, so `run()`
// still abandons (and kills) a slow one to unblock the turn.
function dispatch(bin, args, input, timeoutMs) {
  return new Promise((resolve) => {
    const child = spawn(bin, args, { stdio: ["pipe", "pipe", "pipe"], detached: true });
    let stdout = "";
    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      // Keep draining so a chatty engine cannot block on a full pipe, but unref the pipes as
      // well as the process: a resumed stream is itself an active handle, so without this the
      // released engine would pin the host's event loop until it exits — the opposite of
      // releasing it.
      child.stdout.resume();
      child.stderr.resume();
      if (typeof child.stdout.unref === "function") child.stdout.unref();
      if (typeof child.stderr.unref === "function") child.stderr.unref();
      child.unref();
      resolve({ released: true, stdout, code: null });
    }, timeoutMs);

    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", () => {});
    child.on("error", (error) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve({ released: false, error, stdout, code: null });
    });
    child.on("close", (code) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve({ released: false, stdout, code });
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

// The postflight answer, if it came back within the budget. `released` means the engine is still
// working and the host has stopped waiting for it — not a failure, and never a reason to call
// again (a retry would race an engine that is still running).
async function sendPostflight(cfg, payload) {
  const outcome = await dispatch(
    cfg.bin,
    ["postflight", "--payload-stdin"],
    JSON.stringify(payload),
    cfg.timeoutMs,
  );
  if (outcome.released) return { released: true };
  if (outcome.error) return { error: outcome.error };
  const text = (outcome.stdout || "").trim();
  if (!text) return { answered: false };
  try {
    return { answered: true, doc: JSON.parse(text) };
  } catch {
    return { answered: false };
  }
}

// A part the host marked as not the user's own text is not a task. `@tarquinen/opencode-dcp`
// sends its `▣ DCP | …` compression banner as a real user-role message whose text part carries
// `ignored: true`, and opencode fires `chat.message` for it like any other message; filtering
// only on `type === "text"` filed that banner as the task (39 of 75 loops in the live store
// routed on DCP's own status output). `synthetic` is the host's marker for its own injections,
// so both are skipped — a prompt the user actually typed carries neither.
function userText(output) {
  const parts = (output && output.parts) || [];
  return parts
    .filter(
      (part) =>
        part &&
        part.type === "text" &&
        typeof part.text === "string" &&
        part.ignored !== true &&
        part.synthetic !== true,
    )
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

// A method label: what the run *tried*, with everything that could name a person, a project
// or a secret removed. It exists because "tried A, A failed, switched to B, B worked" is the
// one lesson worth keeping, and a command line is where that lesson lives — wrapped around a
// `--token`, an absolute path and somebody's data.
//
// So the command is normalised here, inside the host process, and thrown away here: the seam
// carries at most three words. A token is kept only if it looks like a name and not like a
// value — no slash, no `=`, no leading `-` (except the module flag, kept only for an
// interpreter that takes one), no leading dot, no non-ASCII, capped at 24 characters. If
// nothing survives, the step has no method and the trace says so rather than guessing.
const RUNNERS = new Set([
  "python", "python2", "python3", "node", "deno", "bun", "php", "ruby", "go", "cargo",
  "rustc", "make", "cmake", "npm", "npx", "yarn", "pnpm", "pip", "pip3", "uv", "poetry",
  "docker", "git", "mvn", "gradle", "dotnet", "mix", "pytest", "jest", "vitest", "mocha",
  "karma", "rspec", "ctest", "babel", "tsc", "eslint", "prettier", "webpack", "vite",
]);
// Words that introduce a command rather than being one.
const NOISE = new Set(["cd", "export", "env", "sudo", "time", "nohup", "source", "set", "echo", "then", "do"]);
// A flag that changes *which* program runs, so it is part of the method's name.
const MODULE_RUNNERS = new Set(["python", "python2", "python3", "node", "deno", "bun", "php", "ruby"]);
const NAME_TOKEN = /^[A-Za-z][A-Za-z0-9_-]{0,23}$/;
const SEGMENT = /&&|\|\||[;|\n]/;
const MAX_LABEL_TOKENS = 3;

function methodOf(command) {
  if (typeof command !== "string" || !command.trim()) return undefined;
  for (const segment of command.split(SEGMENT)) {
    const kept = [];
    for (const token of segment.trim().split(/\s+/)) {
      if (!token || NOISE.has(token)) continue;
      // A quote opens a value: a commit message, a search pattern, somebody's text. Where it
      // starts, the method's name stops — `git commit -m "fix: login crash"` names `git commit`
      // and nothing of the message. Splitting on whitespace alone cannot see this, and the words
      // after the quote are the ones worth keeping out.
      if (token.startsWith('"') || token.startsWith("'") || token.includes('"') || token.includes("'")) break;
      if (token === "-m" && kept.length && MODULE_RUNNERS.has(kept[0])) {
        kept.push("-m");
        continue;
      }
      if (NAME_TOKEN.test(token)) kept.push(token);
      if (kept.filter((entry) => entry !== "-m").length >= MAX_LABEL_TOKENS) break;
    }
    if (kept.length) return kept.join(" ");
  }
  return undefined;
}

// One tool call, in order. `ok` is stated only when something stated it: an exit number is
// the one unambiguous signal a host can give (the engine says the same about test exit codes),
// and an error the host named is a failure. Everything else is left absent — a step that
// reported nothing must not arrive looking like a step that went well.
const TRACE_MAX_STEPS = 16;
const TRACE_KEEP_HEAD = 8;

function recordStep(entry, hookInput, output) {
  entry.toolCalls = (entry.toolCalls || 0) + 1;
  const step = { n: entry.toolCalls, tool: String((hookInput && hookInput.tool) || "-") };
  const args = hookInput && hookInput.args;
  const command = args && (typeof args.command === "string" ? args.command : typeof args.cmd === "string" ? args.cmd : "");
  const method = methodOf(command);
  if (method) step.method = method;
  const metadata = output && output.metadata;
  const exit = metadata && Number.isInteger(metadata.exit) ? metadata.exit : undefined;
  if (exit !== undefined) {
    step.exit = exit;
    step.ok = exit === 0;
  }
  entry.trace = entry.trace || [];
  entry.trace.push(step);
  // The middle goes and both ends stay, because the first attempts show what was tried and
  // the last ones show what it came to. The `n` values then carry the gaps themselves, so a
  // reader can see that steps are missing rather than being shown a smooth sequence.
  if (entry.trace.length > TRACE_MAX_STEPS) entry.trace.splice(TRACE_KEEP_HEAD, 1);
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
          // A turn is a loop, and the trajectory belongs to the loop: starting a new turn
          // starts a new account. Carrying the previous turn's steps into this one would
          // credit a later question with an earlier run's failures.
          trace: [],
          toolCalls: 0,
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
        // The ordered account of the same call. The count above says how many times
        // something went wrong; this says what was tried, in what order, and what the
        // host's own exit number said about each one.
        recordStep(entry, hookInput, output);
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
          // Nothing was observed for the part of this session the plugin did not see, and
          // the account starts empty rather than invented.
          trace: [],
          toolCalls: 0,
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
      // A turn that used no tool has no trajectory, and sends none: an empty list would read
      // as "the run made attempts and none of them failed".
      if (entry.trace && entry.trace.length) {
        signals.tool_trace = entry.trace;
        signals.tool_calls = entry.toolCalls || entry.trace.length;
      }

      const outcome = await sendPostflight(cfg, {
        schema_version: "1.2",
        phase: "postflight",
        task_id: entry.taskId,
        loop_id: entry.loopId,
        session_id: entry.sessionKey || sessionID,
        cwd: entry.cwd || directory,
        provider: "host_delegate",
        signals,
      });
      if (outcome.released) {
        // The engine outlived the budget — its `validate` stage can legitimately run the
        // project's own build — so it was detached to finish and save on its own. This is
        // not silence and not a failure: the loop will close once the engine writes it.
        // Calling again would race an engine that is still working, so this is the end of
        // the account either way; `aos pending` and `doctor` remain where a genuinely dead
        // engine shows up.
        entry.reported = true;
        note(
          `postflight released loop=${entry.loopId} after ${entry.attempts} attempt(s); ` +
            "engine still running detached and will save its own result",
        );
        state.sessions.delete(sessionID);
        return;
      }
      if (outcome.error || !outcome.answered) {
        // Silence from the engine is not "reported". The run ends here or later, and
        // another event costs the host nothing — but a dead engine must not turn this
        // into an endless retry, so the attempts are bounded and the last one is said
        // out loud. Either way the pending record stays behind, which is the trace
        // `aos pending` and `doctor` exist to surface.
        const why = outcome.error ? `error=${outcome.error.message}` : "unanswered";
        note(`postflight ${why} loop=${entry.loopId} attempt=${entry.attempts}`);
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
