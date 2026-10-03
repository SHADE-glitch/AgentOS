#!/usr/bin/env bash
# One live host run, bracketed by two read-only snapshots.
#
# `--auto` is opt-in per run and is recorded in the log when used: the owner authorised
# auto-approval for the exp-v1 experiment (2026-10-01) precisely because headless runs die
# otherwise — `permission.bash=ask` with no TTY means a model that reaches for a tool fails
# that turn, and Stage 0 needs the tool path. What is *not* bypassed is the owner's shell
# alias (it injects `--auto` and an inlined AGENT_OS_ROOT, so you can never tell which env won),
# and yargs does not treat `opencode help <x>` as help — it starts an agent.
set -euo pipefail

RIG="${AOS_RIG:-/tmp/aos-rig}"
STORE="${AOS_STORE_DIR:-$RIG/store}"
DB="${AOS_DB_PATH:-$STORE/aos.db}"
ROOT="${AGENT_OS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

label="${1:?usage: run.sh <label> <cwd> [--pure] [--auto] [-s <sessionID>] <prompt>}"
cwd="${2:?usage: run.sh <label> <cwd> [--pure] [--auto] [-s <sessionID>] <prompt>}"
shift 2

extra=()
while [[ $# -gt 1 ]]; do
  case "$1" in
    --pure) extra+=(--pure); shift ;;
    --auto) extra+=(--auto); shift ;;
    -s) extra+=(-s "$2"); shift 2 ;;
    *) break ;;
  esac done
prompt="${1:?usage: run.sh <label> <cwd> [--pure] [--auto] [-s <sessionID>] <prompt>}"

# Placement guards, before anything can cost a model call. LGD-06-R2 was voided because the rig
# kept its tickets, logs, manifest and a captured previous answer *inside* the measured project:
# the agent listed the workspace, read `.gitignore`, found `.arms/`, and read the last attempt's
# diff before writing its own. An instrument must not sit inside what it measures.
if [[ -e "$cwd/.arms" ]]; then
  echo "refusing: experiment scaffolding .arms/ found in $cwd — move the rig out of the measured project" >&2
  exit 1
fi
for placed in "$RIG" "$STORE"; do
  case "$placed" in
    "$cwd"/*)
      echo "refusing: rig or store sits inside the measured project ($cwd)" >&2
      exit 1 ;;
  esac
done

# The log directory is created before anything writes to the log: the real-store notice
# below used to `tee` here while `mkdir -p` lived 10 lines further down, so the first run
# against a fresh AOS_RIG died inside `set -e` before producing anything (defect AF).
log="$RIG/logs/$label.txt"
mkdir -p "$RIG/logs"

# Without this the plugin loads and does nothing, and the symptom is identical to
# "the plugin is broken" — so the rig states the switch out loud rather than
# inheriting it from an alias this script deliberately does not use.
export AGENT_OS_ROOT="$ROOT"
export AOS_PLUGIN_DEBUG=1

# The plugin spawns `bin/aos`, which inherits this environment. Without pinning the
# store here, experiment runs would write the real store and inflate stop-criterion 1
# with tasks that are not the owner's own work.
export AOS_STORE_DIR="${AOS_STORE_DIR:-$STORE}"
export AOS_DB_PATH="${AOS_DB_PATH:-$AOS_STORE_DIR/aos.db}"
if [[ "$AOS_STORE_DIR" == "$AGENT_OS_ROOT/store" && "${AOS_RIG_ALLOW_REAL_STORE:-}" != "1" ]]; then
  echo "refusing: would write the real store ($AOS_STORE_DIR)" >&2
  exit 1
fi
if [[ "${AOS_RIG_ALLOW_REAL_STORE:-}" == "1" ]]; then
  echo "REAL-STORE RUN: these observations land in the development store; stop-criterion 1" \
    | tee -a "$log"
  echo "  still counts only the owner's interactive sessions, so report them separately" \
    | tee -a "$log"
fi
if [[ " ${extra[*]-} " == *" --auto "* ]]; then
  echo "auto-approved permissions for this run (owner authorisation 2026-10-01, exp-v1)" \
    | tee -a "$log"
fi

"$ROOT/integrations/opencode/live/selfcheck.sh"

"$ROOT/integrations/opencode/live/snapshot.sh" "before-$label"

# `--pure` is not a control for us: it drops every external plugin, so the delta it
# shows is DCP and the notifier and the tracker, not our block. The clean arm is the
# same plugin stack with our seam inert (AGENT_OS_ROOT unset), which is also exactly
# the disable-clean case the fixture claims.
#
# `command` is a shell builtin, so an inert arm has to exec the resolved path — a
# bare `env … command opencode` exits 127 and runs nothing at all.
host="${AOS_HOST_BIN:-$(command -v opencode)}"
runner=()
if [[ "${AOS_RIG_INERT:-}" == "1" ]]; then
  runner=(env -u AGENT_OS_ROOT -u AOS_PLUGIN_DEBUG)
  echo "inert arm: AGENT_OS_ROOT unset for this run only" | tee -a "$log"
fi
set +e
( cd "$cwd" && "${runner[@]}" "$host" run -m opencode/space-bunny-free \
    --print-logs --log-level DEBUG "${extra[@]}" "$prompt" ) >> "$log" 2>&1
rc=$?
set -e
echo "run exit=$rc  log=$log" | tee -a "$log"

# Measurement only, and only after the host finished: the friction oracle reads the
# host's own session database so "did this task really fail and recover" can be answered
# without asking Agent OS about itself. It never writes the host db, never touches the
# store, and its output is never put in front of the model — see live/README.md.
set +e
oracle_out="$(python3 "$ROOT/integrations/opencode/live/friction_oracle.py" \
  --from-log "$log" --project "$cwd" --out "$RIG/oracle/$label.json" 2>&1)"
oracle_rc=$?
set -e
printf '%s\n' "$oracle_out" | tee -a "$log"
echo "oracle exit=$oracle_rc  report=$RIG/oracle/$label.json" | tee -a "$log"

"$ROOT/integrations/opencode/live/snapshot.sh" "after-$label"
