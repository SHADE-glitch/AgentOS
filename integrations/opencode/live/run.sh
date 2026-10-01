#!/usr/bin/env bash
# One live host run, bracketed by two read-only snapshots.
#
# `command opencode` is deliberate: the owner's shell aliases opencode with
# `--auto`, which auto-approves tool permissions, and yargs does not treat
# `opencode help <x>` as help — it starts an agent. Nothing in this rig may run
# unattended, so the alias is bypassed and `--auto` is never passed. Prompts are
# chosen to need no write or exec permission; if the host asks for one, `run`
# stops that turn, which is itself a piece of evidence.
set -euo pipefail

RIG="${AOS_RIG:-/tmp/aos-rig}"
STORE="${AOS_STORE_DIR:-$RIG/store}"
DB="${AOS_DB_PATH:-$STORE/aos.db}"
ROOT="${AGENT_OS_ROOT:-/home/shade/Public/AgentOS}"

label="${1:?usage: run.sh <label> <cwd> [--pure] [-s <sessionID>] <prompt>}"
cwd="${2:?usage: run.sh <label> <cwd> [--pure] [-s <sessionID>] <prompt>}"
shift 2

extra=()
while [[ $# -gt 1 ]]; do
  case "$1" in
    --pure) extra+=(--pure); shift ;;
    -s) extra+=(-s "$2"); shift 2 ;;
    *) break ;;
  esac
done
prompt="${1:?usage: run.sh <label> <cwd> [--pure] [-s <sessionID>] <prompt>}"

# Without this the plugin loads and does nothing, and the symptom is identical to
# "the plugin is broken" — so the rig states the switch out loud rather than
# inheriting it from an alias this script deliberately does not use.
export AGENT_OS_ROOT="$ROOT"
export AOS_PLUGIN_DEBUG=1

# The plugin spawns `bin/aos`, which inherits this environment. Without pinning the
# store here, R1-R4 would write the real store and silently feed stop-criterion 1
# with test runs.
export AOS_STORE_DIR="${AOS_STORE_DIR:-$STORE}"
export AOS_DB_PATH="${AOS_DB_PATH:-$AOS_STORE_DIR/aos.db}"
if [[ "$AOS_STORE_DIR" == "$AGENT_OS_ROOT/store" ]]; then
  echo "refusing: would write the real store ($AOS_STORE_DIR)" >&2
  exit 1
fi

"$ROOT/integrations/opencode/live/selfcheck.sh"

"$ROOT/integrations/opencode/live/snapshot.sh" "before-$label"

log="$RIG/logs/$label.txt"
mkdir -p "$RIG/logs"
set +e
( cd "$cwd" && command opencode run -m opencode/space-bunny-free \
    --print-logs --log-level DEBUG "${extra[@]}" "$prompt" ) > "$log" 2>&1
rc=$?
set -e
echo "run exit=$rc  log=$log" | tee -a "$log"

"$ROOT/integrations/opencode/live/snapshot.sh" "after-$label"
