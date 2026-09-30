#!/usr/bin/env node
// A stand-in for `bin/aos` used by the plugin's tests.
//
// It records every invocation to $AOS_FAKE_LOG as one JSON line and replies with
// whatever $AOS_FAKE_MODE asks for, so the tests can assert both directions: what
// the plugin sent, and what it did with an answer it did not like.
//
// CommonJS with a synchronous stdin read on purpose: the shape of "read the whole
// pipe, then answer" is not what this fixture is testing, and an event-driven
// version spent its time hanging under execFile.

const { appendFileSync, readFileSync } = require("node:fs");

const mode = process.env.AOS_FAKE_MODE || "ok";
const log = process.env.AOS_FAKE_LOG;
const argv = process.argv.slice(2);

let raw = "";
try {
  raw = readFileSync(0, "utf8");
} catch (error) {
  if (error.code !== "EAGAIN" && error.code !== "EOF" && error.code !== "EBADF") throw error;
}

if (log) {
  appendFileSync(log, JSON.stringify({ argv, payload: raw.trim() ? JSON.parse(raw) : null }) + "\n");
}

const sleep = (ms) => {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    /* busy wait: this fixture must be able to be late on purpose */
  }
};

function emit(document) {
  process.stdout.write(typeof document === "string" ? document : JSON.stringify(document) + "\n");
}

if (mode === "hang") sleep(5000);
if (mode === "garbage") {
  emit("this is not a json document");
  process.exit(3);
}
if (mode === "empty") emit("");

if (mode === "pending") {
  emit({
    session_id: "ses-restarted",
    found: true,
    loop: {
      loop_id: "LOOP-FROM-STORE",
      task_id: "T-FROM-STORE",
      session_id: "ses-restarted",
      cwd: "/fixture/project",
    },
  });
  process.exit(0);
}

const doc = {
  schema_version: "1.2",
  phase: argv[0] === "postflight" ? "postflight" : "preflight",
  aos_status: "ok",
  task_id: "T-FAKE",
  loop_id: "LOOP-FAKE",
  session_id: "ses-1",
  memory: {
    retrieved: 1,
    memories: [],
    status: "ok",
    injection: {
      text: "<agent_os>\n- [M-1 · failure] 不要直接拼 cache key\n</agent_os>",
      structured: [],
      char_count: 48,
      truncated: false,
      memory_ids: ["M-1"],
      dropped: [],
    },
  },
  skill: { lead_skill: "bugfix", support_skills: [] },
  warnings: [],
  artifacts: {},
};
if (mode === "noinject") {
  doc.memory.injection = {
    text: "",
    structured: [],
    char_count: 0,
    truncated: false,
    memory_ids: [],
    dropped: [],
  };
}
emit(doc);
