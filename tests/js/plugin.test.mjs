// Non-interference is tested as a property, not asserted as an intention.
//
// Run with:  node --test tests/js/
// The plugin is driven exactly the way opencode drives it — call `server(input)`,
// then invoke the returned hooks — against a fake `aos` binary that records what
// it was asked for. Nothing here touches a real configuration directory, and the
// three cases that matter most are: the plugin absent-in-effect, the plugin
// present, and the plugin failing.

import { test, before, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const REPO = path.resolve(new URL(".", import.meta.url).pathname, "..", "..");
const PLUGIN = path.join(REPO, "integrations", "opencode", "plugin", "agent-os.js");
const FAKE = path.join(REPO, "tests", "js", "fake-aos.cjs");

let root; // a fixture Agent OS root: <root>/bin/aos
let log;

before(() => {
  root = mkdtempSync(path.join(tmpdir(), "aos-plugin-"));
  const bin = path.join(root, "bin");
  mkdirSync(bin, { recursive: true });
  // A wrapper rather than a copy, so the fake's own path is what runs and the
  // fixture root still looks like a real Agent OS checkout (bin/aos present).
  writeFileSync(
    path.join(bin, "aos"),
    `#!/bin/sh\nexec node ${JSON.stringify(FAKE)} "$@"\n`,
    { mode: 0o755 },
  );
  chmodSync(path.join(bin, "aos"), 0o755);
});

beforeEach(() => {
  log = path.join(root, "calls.jsonl");
  writeFileSync(log, "");
  process.env.AGENT_OS_ROOT = root;
  process.env.AOS_BIN = path.join(root, "bin", "aos");
  process.env.AOS_TIMEOUT_MS = "600";
  delete process.env.AOS_FAKE_MODE;
  process.env.AOS_FAKE_LOG = log;
});

const calls = () =>
  readFileSync(log, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));

async function hooks() {
  const module = await import(pathToFileURL(PLUGIN).href + `?t=${Math.random()}`);
  assert.deepEqual(Object.keys(module).sort(), ["default"], "only a default export may be present");
  const plugin = module.default;
  assert.equal(typeof plugin.server, "function", "the module is { id, server }");
  assert.equal(plugin.tui, undefined);
  const server = await plugin.server({ directory: "/fixture/project", project: { directory: "/fixture/project" } });
  return { plugin, server };
}

const openTurn = async (server, text = "修复 cache key 碰撞") =>
  server["chat.message"](
    { sessionID: "ses-1", model: { providerID: "p", modelID: "m" } },
    { message: {}, parts: [{ type: "text", text }] },
  );

const systemFor = async (server, base = ["你是一个编码助手。", "DCP 压缩后的上下文。"]) => {
  const output = { system: [...base] };
  await server["experimental.chat.system.transform"](
    { sessionID: "ses-1", model: { providerID: "p", modelID: "m" } },
    output,
  );
  return output.system;
};

test("the module shape cannot silently kill the load", async () => {
  const { plugin } = await hooks();
  assert.equal(plugin.id, "agent-os");
});

test("disable-clean: with no root configured the host's system array is untouched", async () => {
  delete process.env.AGENT_OS_ROOT;
  const { server } = await hooks();
  const base = ["你是一个编码助手。", "DCP 压缩后的上下文。"];

  await openTurn(server);
  const system = await systemFor(server, base);

  assert.deepEqual(system, base, "byte-for-byte what it was without Agent OS");
  assert.deepEqual(calls(), [], "nothing was invoked at all");
});

test("additive-only: our element is appended, and nobody else's is edited", async () => {
  const { server } = await hooks();
  const base = ["你是一个编码助手。", "DCP 压缩后的上下文。"];
  await openTurn(server);

  const system = await systemFor(server, base);

  assert.equal(system.length, base.length + 1);
  assert.deepEqual(system.slice(0, base.length), base, "existing elements are unchanged, in place");
  assert.notEqual(system[0], system.at(-1), "we never take index 0 — DCP probes it to skip its own work");
  assert.match(system.at(-1), /^<agent_os>/);
  assert.match(system.at(-1), /<\/agent_os>$/);
});

test("one block per turn: a repeated transform replaces rather than stacks", async () => {
  const { server } = await hooks();
  const base = ["你是一个编码助手。"];
  await openTurn(server);

  const twice = await systemFor(server, await systemFor(server, base));

  assert.equal(twice.filter((block) => block.includes("<agent_os>")).length, 1);
  assert.equal(twice[0], base[0]);
});

test("a turn with nothing to say adds nothing", async () => {
  process.env.AOS_FAKE_MODE = "noinject";
  const { server } = await hooks();
  const base = ["你是一个编码助手。"];
  await openTurn(server);

  assert.deepEqual(await systemFor(server, base), base);
});

test("fail-open: a broken engine answer changes nothing and throws nothing", async () => {
  process.env.AOS_FAKE_MODE = "garbage";
  const { server } = await hooks();
  const base = ["你是一个编码助手。"];

  await openTurn(server);
  const system = await systemFor(server, base);

  assert.deepEqual(system, base);
});

test("fail-open: a slow engine is abandoned, not awaited", async () => {
  process.env.AOS_FAKE_MODE = "hang";
  const { server } = await hooks();
  const base = ["你是一个编码助手。"];
  const started = Date.now();

  await openTurn(server);
  assert.ok(Date.now() - started < 3000, "the hook gave up on its own timeout");
  assert.deepEqual(await systemFor(server, base), base);
});

test("the preflight request carries the contract's own fields", async () => {
  const { server } = await hooks();
  await openTurn(server, "重命名变量");

  const [call] = calls(); // the fake logs its own argv, already past node + script
  assert.deepEqual(call.argv, ["preflight", "--payload-stdin"]);
  assert.equal(call.payload.schema_version, "1.2");
  assert.equal(call.payload.task, "重命名变量");
  assert.equal(call.payload.session_id, "ses-1");
  assert.equal(call.payload.cwd, "/fixture/project");
  assert.equal(call.payload.provider, "host_delegate", "the host runs the work; we advise");
  assert.equal(
    call.payload.model,
    "p/m",
    "the model that will do the work is observable here, and the engine keeps it as provenance",
  );
});

test("a message the host marked as not the user's is not a task", async () => {
  // `@tarquinen/opencode-dcp` sends its `▣ DCP | …` compression banner as a real user-role
  // message whose text part carries `ignored: true` (lib/ui/notification.ts:308-347, via
  // session.prompt with noReply), and opencode fires `chat.message` for it like any other.
  // Filtering only on type === "text" filed that banner as the task — 39 of the 75 loops in
  // the live store routed on DCP's own status output. `synthetic` is the host's marker for
  // its own injections, so both are skipped; a real prompt carries neither.
  const marked = { type: "text", text: "▣ DCP | -593.7K removed, +67.3K summary", ignored: true };

  const { server } = await hooks();
  await server["chat.message"](
    { sessionID: "ses-1", model: { providerID: "p", modelID: "m" } },
    { message: {}, parts: [marked] },
  );
  assert.deepEqual(calls(), [], "a message with nothing the user wrote opens no loop");

  const { server: mixed } = await hooks();
  await mixed["chat.message"](
    { sessionID: "ses-1", model: { providerID: "p", modelID: "m" } },
    { message: {}, parts: [marked, { type: "text", text: "修复 cache key 碰撞" }] },
  );
  const [call] = calls();
  assert.equal(call.payload.task, "修复 cache key 碰撞", "only the marked part is dropped");

  const { server: injected } = await hooks();
  await injected["chat.message"](
    { sessionID: "ses-1", model: { providerID: "p", modelID: "m" } },
    { message: {}, parts: [{ type: "text", text: "host-injected context", synthetic: true }] },
  );
  assert.equal(calls().length, 1, "a synthetic part is not the user's task either");
});

test("session.idle reports the run back with signals it actually saw", async () => {
  const { server } = await hooks();
  await openTurn(server);
  await server["tool.execute.after"](
    { sessionID: "ses-1", tool: "bash", callID: "c1" },
    { title: "t", output: "boom", metadata: { error: true } },
  );
  await server["event"]({ event: { type: "session.error", properties: { sessionID: "ses-1", error: "模型超时" } } });

  await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });

  const post = calls().find((call) => call.argv[0] === "postflight");
  assert.ok(post, "the run was reported");
  assert.equal(post.payload.loop_id, "LOOP-FAKE");
  assert.equal(post.payload.signals.tool_errors, 1);
  assert.equal(post.payload.signals.session_error, "模型超时");
  assert.equal(post.payload.outcome, undefined, "we never send a verdict");
  assert.equal(post.payload.quality_score, undefined);
});

test("an unobserved tool count stays absent instead of becoming a zero", async () => {
  const { server } = await hooks();
  await openTurn(server);

  await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });

  const post = calls().find((call) => call.argv[0] === "postflight");
  assert.deepEqual(post.payload.signals, {}, "no evidence, so no claim that nothing went wrong");
});

const textPart = (messageID, text) => ({
  event: { type: "message.part.updated", properties: { sessionID: "ses-1", part: { type: "text", messageID, text } } },
});
const messageInfo = (messageID, role) => ({
  event: { type: "message.updated", properties: { sessionID: "ses-1", info: { id: messageID, role } } },
});

test("the answer the run gave is reported as material", async () => {
  // Defect AG: no signal carried a cause, so a proposal could only echo the question. The answer is
  // the one text a run produces — it goes up for the reviewer to read, and it is weighted 0.00 in the
  // verdict (pinned engine-side), so reporting it cannot make a run look more confident than it is.
  const { server } = await hooks();
  await openTurn(server);
  await server["event"](messageInfo("msg_a", "assistant"));
  await server["event"](textPart("msg_a", "我会改用 p95 作为首指标，均值放附注。"));

  await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });

  const post = calls().find((call) => call.argv[0] === "postflight");
  assert.equal(post.payload.signals.response_summary, "我会改用 p95 作为首指标，均值放附注。");
});

test("text nobody has identified as the assistant's is not sent as an answer", async () => {
  // A text part with no `message.updated` telling us whose it is could be the user's own prompt.
  // Sending that back as `response_summary` would file the question as the answer — the exact shape
  // AG is about. Absence is the correct report; a guess is not.
  const { server } = await hooks();
  await openTurn(server);
  await server["event"](textPart("msg_unknown", "这可能是用户的话"));

  await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });

  const post = calls().find((call) => call.argv[0] === "postflight");
  assert.equal(post.payload.signals.response_summary, undefined);
  assert.deepEqual(post.payload.signals, {}, "and nothing else is invented alongside it");
});

test("the user's message is never reported as the run's answer", async () => {
  const { server } = await hooks();
  await openTurn(server);
  await server["event"](messageInfo("msg_u", "user"));
  await server["event"](messageInfo("msg_a", "assistant"));
  await server["event"](textPart("msg_u", "修复缓存键碰撞导致的命中率下降"));
  await server["event"](textPart("msg_a", "按解析后的真实路径取键。"));

  await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });

  const post = calls().find((call) => call.argv[0] === "postflight");
  assert.equal(post.payload.signals.response_summary, "按解析后的真实路径取键。");
});

test("the reported answer is capped and never appears in a debug record", async () => {
  process.env.AOS_PLUGIN_DEBUG = "1";
  const written = [];
  const original = process.stderr.write.bind(process.stderr);
  process.stderr.write = (chunk) => {
    written.push(String(chunk));
    return true;
  };
  const long = "长".repeat(1200);
  try {
    const { server } = await hooks();
    await openTurn(server);
    await server["event"](messageInfo("msg_a", "assistant"));
    await server["event"](textPart("msg_a", long));
    await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });
  } finally {
    process.stderr.write = original;
    delete process.env.AOS_PLUGIN_DEBUG;
  }

  const post = calls().find((call) => call.argv[0] === "postflight");
  assert.ok(post.payload.signals.response_summary.length <= 500, "a cap, not the whole transcript");
  const out = written.join("");
  assert.match(out, /response_summary chars=\d+/, "the record says a size, which is the useful part");
  assert.doesNotMatch(out, /长长长/, "no payload value is ever logged");
});

test("after a restart the loop is recovered through the engine, not its files", async () => {
  const { server } = await hooks();
  // No chat.message this session: the plugin came up after the loop opened.
  process.env.AOS_FAKE_MODE = "pending";

  await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-restarted" } } });

  const asked = calls().map((call) => call.argv[0]);
  assert.ok(asked.includes("pending"), "asked the engine to resolve the session");
  const post = calls().find((call) => call.argv[0] === "postflight");
  assert.equal(post.payload.loop_id, "LOOP-FROM-STORE");
});

test("an unknown session is left alone", async () => {
  const { server } = await hooks();
  process.env.AOS_FAKE_MODE = "empty";

  await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-unknown" } } });

  assert.equal(calls().find((call) => call.argv[0] === "postflight"), undefined);
});

test("the plugin has no way to write to the filesystem", () => {
  // Zero writes is a property of the code, so it is checked against the code: an
  // earlier version of this test only proved the *fixture* stayed in its own
  // directory, which said nothing about the plugin.
  const source = readFileSync(PLUGIN, "utf8");
  const writers =
    /\b(writeFileSync|writeFile|appendFileSync|appendFile|mkdirSync|mkdir|rmSync|rm|unlinkSync|unlink|renameSync|rename|copyFileSync|copyFile|createWriteStream|trunc)\b/;

  assert.doesNotMatch(source, writers, "no write API is even imported, let alone called");
  assert.match(
    source,
    /import \{ existsSync \} from "node:fs"/,
    "the only filesystem use is the one that decides whether the engine is there",
  );
});

test("another plugin's text appended to our element survives us", async () => {
  // `@tarquinen/opencode-dcp` does not push its own element: it writes into the last
  // one (`output.system[len - 1] += "\n\n" + newPrompt`). A replace-in-place that
  // assumed the last element is entirely ours would delete its prompt on the second
  // LLM call of the same session — and we would be the plugin that broke a neighbour.
  const { server } = await hooks();
  const base = ["你是一个编码助手。"];
  await openTurn(server);

  const first = await systemFor(server, base);
  const foreignSuffix = "\n\n[DCP] 压缩后的历史上下文";
  first[first.length - 1] += foreignSuffix;

  const second = await systemFor(server, first);

  assert.equal(second.length, base.length + 1, "one element for us, always one, no matter how many calls");
  assert.ok(second.at(-1).startsWith("<agent_os>"), "our block is still the head of that element");
  assert.ok(
    second.at(-1).endsWith(foreignSuffix),
    "the neighbour's text is still there, byte for byte, after our close tag",
  );
  assert.equal(second[0], base[0], "and we still never touch anyone else's element");
});

async function captureStderr(fn) {
  const written = [];
  const original = process.stderr.write.bind(process.stderr);
  process.stderr.write = (chunk) => {
    written.push(String(chunk));
    return true;
  };
  try {
    await fn();
  } finally {
    process.stderr.write = original;
  }
  return written.join("");
}

test("why the plugin said nothing is itself said", async () => {
  // Three silences used to look the same from outside: the engine answered but
  // opened no loop, the message carried no text at all, and the engine recalled
  // nothing for a real task. Each is a different diagnosis, so each gets its own
  // record — otherwise the operator is left guessing which of the three broke.
  process.env.AOS_PLUGIN_DEBUG = "1";
  try {
    process.env.AOS_FAKE_MODE = "fallback";
    const degraded = await captureStderr(async () => {
      const { server } = await hooks();
      await openTurn(server);
    });
    assert.match(degraded, /preflight degraded status=fallback/, "an opened-but-dead loop is named");
    assert.match(degraded, /warnings=1/, "and says the engine carried a reason");

    process.env.AOS_FAKE_MODE = "ok";
    const noText = await captureStderr(async () => {
      const { server } = await hooks();
      await server["chat.message"](
        { sessionID: "ses-1", model: { providerID: "p", modelID: "m" } },
        { message: {}, parts: [{ type: "file", url: "file:///tmp/x", filename: "x" }] },
      );
    });
    assert.match(noText, /chat\.message skipped: no text part/, "a non-text first message is not silence");

    const emptyRecall = await captureStderr(async () => {
      process.env.AOS_FAKE_MODE = "noinject";
      const { server } = await hooks();
      await openTurn(server);
    });
    assert.match(emptyRecall, /preflight ok loop=LOOP-FAKE chars=0/, "nothing recalled is a working call that said zero");
  } finally {
    delete process.env.AOS_PLUGIN_DEBUG;
    delete process.env.AOS_FAKE_MODE;
  }
});

test("the tool hook names the shape it was given, never its contents", async () => {
  // Whether a real error is visible here is the open question behind `tool_errors`:
  // the plugin only counts an error it can actually see, and an unconfirmable guess
  // about the payload shape is how a probe fires on nothing forever. Keys and counts
  // in the record, values nowhere.
  process.env.AOS_PLUGIN_DEBUG = "1";
  try {
    const { server } = await hooks();
    await openTurn(server);
    const out = await captureStderr(async () => {
      await server["tool.execute.after"](
        { sessionID: "ses-1", tool: "bash", callID: "c1" },
        { title: "t", output: "客户的手机号是 13800000000", metadata: { truncated: false } },
      );
    });
    assert.match(
      out,
      /tool seen tool=bash keys=\[[a-z,]+\] metadata_keys=\[[a-z,]+\]/,
      "the shape is recorded",
    );
    assert.doesNotMatch(out, /13800000000|手机号/, "and the record carries no tool output");
  } finally {
    delete process.env.AOS_PLUGIN_DEBUG;
  }
});

// The trajectory: what a run actually did, in order. A count of errors cannot tell
// "one clean run" from "five failures then a fix", and that difference is the whole
// lesson. The method label is the risk here — a command line is full of paths, tokens
// and somebody's data — so the label is a normalisation computed inside this process,
// and nothing else about the command is allowed to leave it.
test("a step names its method and carries nothing but the method", async () => {
  const cases = [
    ["python -m pytest tests/x.py -q", "python -m pytest"],
    ["go test ./...", "go test"],
    ["git rebase origin/main", "git rebase"],
    ['git commit -m "fix: login crash"', "git commit"],
    ["npm test -- --token=SECRET", "npm test"],
    ["docker compose up -d", "docker compose up"],
    ["cd /home/u/app && pytest -q", "pytest"],
    ["export TOKEN=abc; make build", "make build"],
    ["./scripts/run.sh --env=prod", null],
    ['echo "客户手机号 13800000000"', null],
    ["cat /home/u/.env", "cat"],
  ];
  for (const [command, expected] of cases) {
    const { server } = await hooks();
    await openTurn(server);
    await server["tool.execute.after"](
      { sessionID: "ses-1", tool: "bash", callID: "c1", args: { command } },
      { title: "t", output: "…", metadata: { exit: expected ? 1 : 0 } },
    );
    await server.event({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });
    const post = calls().filter((call) => call.argv[0] === "postflight").at(-1);
    const step = post.payload.signals.tool_trace?.[0];
    assert.equal(step?.method, expected ?? undefined, `fingerprint of ${JSON.stringify(command)}`);
    const travelled = JSON.stringify(post.payload.signals.tool_trace ?? "");
    for (const leak of [/SECRET/, /abc/, /home\/u/, /\.env/, /origin\/main/, /tests\/x\.py/, /--/, /=/, /手机号/, /13800000000/, /login/, /crash/]) {
      assert.doesNotMatch(travelled, leak, `${leak} must not travel from ${JSON.stringify(command)}`);
    }
  }
});

test("the trace is ordered, bounded, and the bound is honest about its gaps", async () => {
  const { server } = await hooks();
  await openTurn(server);
  for (let index = 1; index <= 20; index += 1) {
    await server["tool.execute.after"](
      { sessionID: "ses-1", tool: "bash", callID: `c${index}`, args: { command: `pytest -q case${index}` } },
      { title: "t", output: "…", metadata: { exit: index < 19 ? 1 : 0 } },
    );
  }
  await server.event({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });
  const signals = calls().filter((call) => call.argv[0] === "postflight").at(-1).payload.signals;
  assert.equal(signals.tool_calls, 20, "the denominator is the truth about how many calls happened");
  assert.equal(signals.tool_trace.length, 16, "bounded: the middle goes, both ends stay");
  assert.deepEqual(
    signals.tool_trace.map((step) => step.n),
    [1, 2, 3, 4, 5, 6, 7, 8, 13, 14, 15, 16, 17, 18, 19, 20],
    "gaps in the numbering say out loud which steps were dropped",
  );
  assert.equal(signals.tool_trace.at(-1).ok, true, "the last attempt is the one that worked");
  assert.equal(signals.tool_trace.at(-2).ok, true, "…and so is the one before it (19 and 20 both passed)");
  assert.deepEqual(
    signals.tool_trace.slice(0, 8).map((step) => step.ok),
    [false, false, false, false, false, false, false, false],
    "the window opens on failures and closes on a success: 先败后成 is visible without reading a count",
  );
});

test("a non-shell step is recorded with no method and no argument read", async () => {
  const { server } = await hooks();
  await openTurn(server);
  await server["tool.execute.after"](
    { sessionID: "ses-1", tool: "glob", callID: "g1", args: { path: "/home/u/private", pattern: "**/*.env" } },
    { title: "t", output: "3 files", metadata: { count: 3, truncated: false } },
  );
  await server.event({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });
  const step = calls().find((call) => call.argv[0] === "postflight").payload.signals.tool_trace[0];
  assert.equal(step.tool, "glob");
  assert.equal(step.method, undefined, "an argument is not a method, and its value is not ours to send");
  assert.equal(step.exit, undefined, "no exit number, no claim about one");
  assert.equal(step.ok, undefined, "absence stays absence: unknown is not success");
});

test("an unanswered postflight is retried, then given up on out loud", async () => {
  // The run ended and the engine did not answer. Marking the session as reported
  // before the call meant that was the end of it: the loop stayed open in the
  // store, and the plugin — which had promised to report — said nothing more.
  // A retry costs the host nothing, and a bounded one cannot loop forever.
  process.env.AOS_FAKE_MODE = "postdead";
  const { server } = await hooks();
  await openTurn(server);

  for (let turn = 0; turn < 4; turn += 1) {
    await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });
  }

  const posts = calls().filter((call) => call.argv[0] === "postflight");
  assert.equal(posts.length, 3, "two retries, then it stops asking");
  assert.equal(new Set(posts.map((call) => call.payload.loop_id)).size, 1, "always the same loop");
});

test("a postflight that outlives the budget is released, not killed and not retried", async () => {
  // The engine's validate stage may run the project's own build, budgeted up to 300 s
  // engine-side (`aos/core/validation/code_validator.py`) while this plugin waits 600 ms.
  // Killing it at the plugin's budget lost the whole loop — `_run_postflight` saves only at
  // the end — so a postflight past the budget is detached and left to finish on its own.
  // That is not silence, so it is not retried: asking again would race an engine still running.
  process.env.AOS_FAKE_MODE = "posthang";
  const { server } = await hooks();
  await openTurn(server);

  const started = Date.now();
  await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });
  assert.ok(Date.now() - started < 3000, "the host stopped waiting on its own budget");

  // A second idle must not call the still-running engine again.
  await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });
  const posts = calls().filter((call) => call.argv[0] === "postflight");
  assert.equal(posts.length, 1, "released once, never asked a second time");
});

test("a hook that works says so, when debugging is on", async () => {
  // The plugin fails open everywhere, which is right for a prompt and fatal for a
  // diagnosis: "the engine had nothing to say" and "the hook threw" and "the plugin
  // was inert" all leave the same silence. Success has to be as visible as failure,
  // or the first live run teaches us nothing.
  process.env.AOS_PLUGIN_DEBUG = "1";
  const written = [];
  const original = process.stderr.write.bind(process.stderr);
  process.stderr.write = (chunk) => {
    written.push(String(chunk));
    return true;
  };
  try {
    const { server } = await hooks();
    await openTurn(server);
    await systemFor(server);
    await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });
  } finally {
    process.stderr.write = original;
    delete process.env.AOS_PLUGIN_DEBUG;
  }

  const out = written.join("");
  assert.match(out, /preflight ok loop=LOOP-FAKE/, "the preflight reached the engine");
  assert.match(out, /system (appended|replaced) index=\d+ len=\d+/, "the block was placed");
  assert.match(out, /postflight sent loop=LOOP-FAKE signals=\d+ answered=true/, "the run was reported back");
  // Records name keys, indices and counts. Never a task, never a memory body.
  assert.doesNotMatch(out, /修复 cache key/, "the record carries no conversation text");
});

test("an inert plugin says it is inert", async () => {
  process.env.AOS_PLUGIN_DEBUG = "1";
  delete process.env.AGENT_OS_ROOT;
  const written = [];
  const original = process.stderr.write.bind(process.stderr);
  process.stderr.write = (chunk) => {
    written.push(String(chunk));
    return true;
  };
  try {
    const { server } = await hooks();
    await openTurn(server);
    await systemFor(server);
  } finally {
    process.stderr.write = original;
    delete process.env.AOS_PLUGIN_DEBUG;
    process.env.AGENT_OS_ROOT = root;
  }

  assert.match(written.join(""), /disabled: AGENT_OS_ROOT unset/, "inert is not silent");
});

test("the fixture never writes outside its own directory", async () => {
  const config = path.join(root, "should-not-exist");
  process.env.AOS_FAKE_HOME = config;
  const { server } = await hooks();
  await openTurn(server);
  await server["event"]({ event: { type: "session.idle", properties: { sessionID: "ses-1" } } });

  let exists = true;
  try {
    readFileSync(config);
  } catch {
    exists = false;
  }
  assert.equal(exists, false, "the plugin created no files of its own");
  rmSync(path.join(root, "pending-postflight"), { recursive: true, force: true });
});
