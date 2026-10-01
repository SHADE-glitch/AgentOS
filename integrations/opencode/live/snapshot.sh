#!/usr/bin/env bash
# Read-only snapshot of everything the live rig cares about, so that "what did this
# run actually do" is answered by a diff and not by reading code and hoping.
#
# It opens the store `mode=ro`: a diagnostic that mutates the thing it measures is
# how a test run quietly becomes a real run.
set -euo pipefail

RIG="${AOS_RIG:-/tmp/aos-rig}"
STORE="${AOS_STORE_DIR:-$RIG/store}"
DB="${AOS_DB_PATH:-$STORE/aos.db}"
ROOT="${AGENT_OS_ROOT:-/home/shade/Public/AgentOS}"
label="${1:?usage: snapshot.sh <label>}"

mkdir -p "$RIG/snap"
out="$RIG/snap/$label.txt"
q() { sqlite3 "file:$DB?mode=ro" "$1"; }

{
  echo "# snapshot $label  $(date -u +%FT%TZ)"
  echo "# db=$DB"

  echo "## counts"
  echo "observations_total|$(q 'SELECT COUNT(*) FROM observations')"
  echo "observations_hot|$(q "SELECT COUNT(*) FROM observations WHERE source='hot'")"
  echo "observations_backfill|$(q "SELECT COUNT(*) FROM observations WHERE source='backfill'")"
  echo "retrieval_log|$(q 'SELECT COUNT(*) FROM retrieval_log')"
  echo "candidates|$(q 'SELECT COUNT(*) FROM candidates')"
  echo "learning_reviews|$(q 'SELECT COUNT(*) FROM learning_reviews')"

  echo "## hot runs, grouped by session"
  # Stop-criterion 1 counts source='hot' globally, and the owner's daily TUI sessions
  # write that same counter. A bare total would let ordinary use hide whether the rig
  # actually closed the loop, so the per-session view is printed next to it.
  q "SELECT COALESCE(session_id,'-')||' loops='||COUNT(DISTINCT loop_id)
       ||' reviews_pending='||SUM(needs_review)
     FROM observations WHERE source='hot' AND memory_id IS NULL
     GROUP BY session_id ORDER BY session_id"

  echo "## loop-level observations (the hot-run evidence)"
  q "SELECT loop_id||' sess='||session_id||' src='||source||' outcome='||outcome
       ||' nr='||needs_review||' conf='||confidence||' skill='||skill_used
       ||' signals='||substr(signals_json,1,220)
     FROM observations WHERE memory_id IS NULL ORDER BY observation_id"

  echo "## linkage (retrieval_log, per loop)"
  q "SELECT loop_id||' rank='||rank||' '||memory_id||' score='||round(score,3)
     FROM retrieval_log ORDER BY id DESC LIMIT 20"

  echo "## gate"
  q "SELECT 'review #'||review_id||' kind='||kind||' status='||status
       ||' loop='||COALESCE(loop_id,'-')||' memory='||COALESCE(memory_id,'-')
     FROM learning_reviews ORDER BY review_id"
  q "SELECT 'candidate '||candidate_id||' '||candidate_type||' -> '
       ||COALESCE(target_memory,'-')||' consumed='||COALESCE(consumed_at,'no')
     FROM candidates ORDER BY candidate_id LIMIT 20"

  echo "## engine diagnosis"
  ( cd "$ROOT" && AOS_STORE_DIR="$STORE" AOS_DB_PATH="$DB" ./bin/aos doctor --json )
  ( cd "$ROOT" && AOS_STORE_DIR="$STORE" AOS_DB_PATH="$DB" ./bin/aos pending --json )
  ( cd "$ROOT" && AOS_STORE_DIR="$STORE" AOS_DB_PATH="$DB" ./bin/aos review list )

  echo "## files"
  echo "loops:";    ls -1 "$STORE/loops" 2>/dev/null | sed 's/^/  /' || true
  echo "pending:";  ls -1 "$STORE/pending-postflight" 2>/dev/null | sed 's/^/  /' || true
  echo "evidence:"; ls -1 "$STORE/evidence" 2>/dev/null | sed 's/^/  /' || true
} > "$out" 2>&1

echo "snapshot -> $out"
