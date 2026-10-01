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
