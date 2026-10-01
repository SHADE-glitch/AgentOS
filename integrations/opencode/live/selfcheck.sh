#!/usr/bin/env bash
# R0.5 — the zero-cost load self-check. Run it before spending any model call.
#
# Two ways the whole exercise produces nothing while looking like a defect: the
# plugin is inert because `AGENT_OS_ROOT` did not reach it, or the host binary is
# not runnable at all. Both are cheap to check and both are indistinguishable from
# "the seam is broken" from the outside, so they are checked first, on purpose.
set -euo pipefail

ROOT="${AGENT_OS_ROOT:?AGENT_OS_ROOT must be set: an inert plugin and a broken plugin look identical}"
BIN="${AOS_BIN:-$ROOT/bin/aos}"

# Mirrors agent-os.js settings().enabled — the same predicate the plugin evaluates.
if [[ ! -x "$BIN" ]]; then
  echo "INERT: plugin would no-op (no executable engine binary at $BIN)" >&2
  exit 1
fi
echo "engine binary ok: $BIN"

# `command` bypasses the shell alias, which carries --auto (auto-approve tool
# permissions). This must never start a session.
version="$(command opencode --version 2>&1 | tail -1)"
echo "host ok: opencode $version"

if [[ -n "${AOS_STORE_DIR:-}" ]]; then
  echo "store under test: $AOS_STORE_DIR"
elif [[ "${AOS_RIG_ALLOW_REAL_STORE:-}" == "1" ]]; then
  # Only the final acceptance run (R5) earns this: its observations count toward
  # stop-criterion 1, and everything before it must not.
  echo "store under test: the REAL store (AOS_RIG_ALLOW_REAL_STORE=1)"
else
  echo "AOS_STORE_DIR unset — this rig would write the REAL store" >&2
  exit 1
fi

echo "selfcheck pass"
