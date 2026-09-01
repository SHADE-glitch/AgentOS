#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# AOS UserPromptSubmit Hook for Freebuff
#
# Called by Freebuff on every prompt submission.
# Calls AOS bootstrap → gets decision context → prepends to prompt.
#
# Pipeline (same as OpenCode plugin):
#   User submits prompt → This hook → aos_bootstrap.py → aos_host_adapter.py
#   → Router/Memory → decision context → prepended to prompt
#   → Freebuff agent executes with AOS context
#
# Exit codes: 0 = success, 1 = error (pass-through)
# ──────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────
# Find bootstrap relative to this script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AOS_ROOT="${AGENT_OS_ROOT:-$HOME/.agents}"
BOOTSTRAP_SCRIPT="$SCRIPT_DIR/../aos_bootstrap.py"

# Fallback to AOS_ROOT if not found relative
if [ ! -f "$BOOTSTRAP_SCRIPT" ]; then
    BOOTSTRAP_SCRIPT="$AOS_ROOT/runtime/hosts/freebuff/aos_bootstrap.py"
fi

TIMEOUT_SECONDS=15

# ── Logging ──────────────────────────────────────────────────────
AOS_LOG="/tmp/aos_hook_log.txt"
log_hook() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$AOS_LOG"
}

# ── Read input from Freebuff ──────────────────────────────────────
INPUT=$(cat)
log_hook "HOOK_TRIGGERED: ${INPUT:0:80}"

# ── Skip recursion guard ──────────────────────────────────────────
if [ "${AOS_HOST_PLUGIN_ACTIVE:-}" = "1" ]; then
    echo "$INPUT"
    exit 0
fi

# ── Check if bootstrap script exists ──────────────────────────────
if [ ! -f "$BOOTSTRAP_SCRIPT" ]; then
    echo "$INPUT"
    exit 0
fi

# ── Extract prompt from JSON ──────────────────────────────────────
if command -v jq &>/dev/null; then
    PROMPT=$(echo "$INPUT" | jq -r '.prompt // .task // empty' 2>/dev/null)
    CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
else
    PROMPT=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('prompt',d.get('task','')))" 2>/dev/null)
    CWD=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('cwd',''))" 2>/dev/null)
fi

if [ -z "$PROMPT" ]; then
    echo "$INPUT"
    exit 0
fi

# ── Build bootstrap input ─────────────────────────────────────────
BOOTSTRAP_INPUT=$(python3 -c "
import json, sys
print(json.dumps({
    'task': sys.argv[1],
    'cwd': sys.argv[2],
    'session_id': ''
}))
" "$PROMPT" "$CWD" 2>/dev/null || echo "{}")

# ── Call AOS Bootstrap ────────────────────────────────────────────
AOS_CONTEXT=$(echo "$BOOTSTRAP_INPUT" | timeout "$TIMEOUT_SECONDS" python3 "$BOOTSTRAP_SCRIPT" 2>/dev/null || echo "")

# ── Build output ──────────────────────────────────────────────────
if [ -n "$AOS_CONTEXT" ]; then
    # Prepend AOS context to prompt, then rebuild JSON
    MODIFIED_PROMPT="${AOS_CONTEXT}${PROMPT}"
    log_hook "AOS_CONTEXT_INJECTED: len=${#AOS_CONTEXT}"
    
    if command -v jq &>/dev/null; then
        # Use python for safe JSON construction (jq --arg breaks with multi-line)
        OUTPUT=$(python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
data['prompt'] = sys.argv[1]
print(json.dumps(data, ensure_ascii=False))
" <<< "$INPUT" "$MODIFIED_PROMPT" 2>/dev/null)
        
        if [ -n "$OUTPUT" ]; then
            echo "$OUTPUT"
        else
            echo "$MODIFIED_PROMPT"
        fi
    else
        echo "$MODIFIED_PROMPT"
    fi
else
    log_hook "AOS_UNAVAILABLE: passing through"
    echo "$INPUT"
fi

exit 0
