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
