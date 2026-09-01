#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# AOS Host Adapter — Freebuff Installation
#
# Installs the AOS hook into Freebuff's settings.json.
# Freebuff (based on Codebuff/Claude Code) reads from ~/.claude/settings.json
#
# Usage:
#   bash install.sh          # Install globally (~/.claude/settings.json)
#   bash install.sh --local  # Install for current project only (.freebuff/settings.json)
# ──────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AOS_ROOT="${AGENT_OS_ROOT:-$HOME/.agents}"
HOOK_SRC="$SCRIPT_DIR/hooks/prompt_submit.sh"
BOOTSTRAP_SRC="$SCRIPT_DIR/aos_bootstrap.py"

# Fixed install location for hooks
HOOKS_DIR="$AOS_ROOT/runtime/hosts/freebuff/hooks"
HOOK_INSTALLED="$HOOKS_DIR/prompt_submit.sh"
BOOTSTRAP_INSTALLED="$AOS_ROOT/runtime/hosts/freebuff/aos_bootstrap.py"

# ── Determine settings location ───────────────────────────────────
# Freebuff (Codebuff/Claude Code) reads from ~/.claude/settings.json
if [ "${1:-}" = "--local" ]; then
    SETTINGS_FILE=".freebuff/settings.json"
    mkdir -p .freebuff
    echo "Installing AOS hook to project-local settings..."
else
    SETTINGS_FILE="$HOME/.claude/settings.json"
    echo "Installing AOS hook to global settings (~/.claude/settings.json)..."
fi

# ── Copy scripts to fixed location ────────────────────────────────
mkdir -p "$HOOKS_DIR"
cp "$HOOK_SRC" "$HOOK_INSTALLED"
cp "$BOOTSTRAP_SRC" "$BOOTSTRAP_INSTALLED"
chmod +x "$HOOK_INSTALLED"
chmod +x "$BOOTSTRAP_INSTALLED"
echo "✓ Installed scripts to $AOS_ROOT/runtime/hosts/freebuff/"

# ── Merge hook into settings.json ─────────────────────────────────
HOOK_CMD="bash $HOOK_INSTALLED"

if [ -f "$SETTINGS_FILE" ]; then
    echo "Found existing settings.json, merging hooks..."
    
    python3 -c "
import json
import sys

settings_file = '$SETTINGS_FILE'
hook_command = '$HOOK_CMD'

# Read existing settings
with open(settings_file) as f:
    settings = json.load(f)

# Ensure hooks structure exists
if 'hooks' not in settings:
    settings['hooks'] = {}
if 'UserPromptSubmit' not in settings['hooks']:
    settings['hooks']['UserPromptSubmit'] = []

# Check if AOS hook already exists
aos_hook_exists = False
for hook_group in settings['hooks']['UserPromptSubmit']:
    for hook in hook_group.get('hooks', []):
        if 'aos' in hook.get('command', '').lower():
            aos_hook_exists = True
            hook['command'] = hook_command
            break

if not aos_hook_exists:
    settings['hooks']['UserPromptSubmit'].append({
        'hooks': [{
            'type': 'command',
            'command': hook_command,
            'timeout': 20
        }]
    })
    print('✓ Added AOS hook to existing settings')
else:
    print('✓ Updated existing AOS hook')

# Set environment variable
if 'env' not in settings:
    settings['env'] = {}
settings['env']['AGENT_OS_ROOT'] = '$AOS_ROOT'

# Write back
with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

print('✓ Settings updated')
"
else
    echo "Creating new settings.json..."
    
    cat > "$SETTINGS_FILE" << SETTINGS_EOF
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOOK_CMD",
            "timeout": 20
          }
        ]
      }
    ]
  },
  "env": {
    "AGENT_OS_ROOT": "$AOS_ROOT"
  }
}
SETTINGS_EOF

    echo "✓ Created settings.json"
fi

# ── Verify installation ───────────────────────────────────────────
echo ""
echo "=== AOS Host Adapter for Freebuff ==="
echo ""
echo "Installation complete!"
echo ""
echo "Hook script: $HOOK_INSTALLED"
echo "Bootstrap:   $BOOTSTRAP_INSTALLED"
echo "Settings:    $SETTINGS_FILE"
echo ""
echo "How it works:"
echo "  1. User submits prompt in Freebuff"
echo "  2. UserPromptSubmit hook fires"
echo "  3. Hook calls aos_bootstrap.py"
echo "  4. aos_bootstrap.py calls aos_host_adapter.py"
echo "  5. Decision context is prepended to the prompt"
echo "  6. Freebuff agent executes with AOS context"
echo ""
echo "To verify: check /tmp/aos_hook_log.txt after sending a prompt"
echo "To uninstall: remove the hook from $SETTINGS_FILE"
