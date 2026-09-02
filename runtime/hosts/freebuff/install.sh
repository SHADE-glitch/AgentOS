#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# AOS Host Adapter — Freebuff Installation
#
# Installs the AOS hook into Freebuff's settings.json.
# Freebuff CLI reads from ~/.config/manicode/settings.json
# (the binary is at ~/.config/manicode/freebuff, launched by launcher.js)
#
# Usage:
#   bash install.sh          # Install globally (recommended)
#   bash install.sh --uninstall  # Remove AOS hook
# ──────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AOS_ROOT="${AGENT_OS_ROOT:-$HOME/.agents}"
HOOK_SRC="$SCRIPT_DIR/hooks/prompt_submit.sh"
BOOTSTRAP_SRC="$SCRIPT_DIR/aos_bootstrap.py"

# Freebuff's REAL config location (per launcher.js: configDir = ~/.config/manicode)
SETTINGS_FILE="$HOME/.config/manicode/settings.json"

# Fixed install location for scripts
HOOKS_DIR="$AOS_ROOT/runtime/hosts/freebuff/hooks"
HOOK_INSTALLED="$HOOKS_DIR/prompt_submit.sh"
BOOTSTRAP_INSTALLED="$AOS_ROOT/runtime/hosts/freebuff/aos_bootstrap.py"

HOOK_CMD="bash $HOOK_INSTALLED"

# ── Uninstall ────────────────────────────────────────────────────
if [ "${1:-}" = "--uninstall" ]; then
    echo "Removing AOS hook from Freebuff settings..."
    python3 -c "
import json, sys

f = '$SETTINGS_FILE'
try:
    with open(f) as fh:
        settings = json.load(fh)
except FileNotFoundError:
    print('Settings file not found, nothing to remove.')
    sys.exit(0)

changed = False
if 'hooks' in settings and 'UserPromptSubmit' in settings['hooks']:
    entries = settings['hooks']['UserPromptSubmit']
    new_entries = []
    for entry in entries:
        is_aos = False
        for hook in entry.get('hooks', []):
            if 'prompt_submit.sh' in hook.get('command', ''):
                is_aos = True
                break
        if not is_aos:
            new_entries.append(entry)
    if new_entries:
        settings['hooks']['UserPromptSubmit'] = new_entries
    else:
        del settings['hooks']['UserPromptSubmit']
    changed = True

if 'env' in settings and 'AGENT_OS_ROOT' in settings['env']:
    del settings['env']['AGENT_OS_ROOT']
    changed = True

if changed:
    with open(f, 'w') as fh:
        json.dump(settings, fh, indent=2)
    print('✓ AOS hook removed from', f)
else:
    print('No AOS hook found in', f)
"
    echo "✓ Uninstall complete"
    exit 0
fi

# ── Install ──────────────────────────────────────────────────────
echo "Installing AOS hook for Freebuff..."

# Check settings file exists
if [ ! -f "$SETTINGS_FILE" ]; then
    echo "ERROR: Freebuff settings not found at $SETTINGS_FILE"
    echo "Please run 'freebuff' at least once to create the config."
    exit 1
fi

# Copy scripts to fixed location
mkdir -p "$HOOKS_DIR"
cp "$HOOK_SRC" "$HOOK_INSTALLED"
cp "$BOOTSTRAP_SRC" "$BOOTSTRAP_INSTALLED"
chmod +x "$HOOK_INSTALLED"
chmod +x "$BOOTSTRAP_INSTALLED"
echo "✓ Installed scripts to $AOS_ROOT/runtime/hosts/freebuff/"

# Merge hook into settings.json (preserve existing settings)
python3 -c "
import json

settings_file = '$SETTINGS_FILE'
hook_command = '$HOOK_CMD'

with open(settings_file) as f:
    settings = json.load(f)

# Ensure hooks structure
if 'hooks' not in settings:
    settings['hooks'] = {}
if 'UserPromptSubmit' not in settings['hooks']:
    settings['hooks']['UserPromptSubmit'] = []

# Check if AOS hook already exists
aos_exists = False
for entry in settings['hooks']['UserPromptSubmit']:
    for hook in entry.get('hooks', []):
        if 'prompt_submit.sh' in hook.get('command', ''):
            hook['command'] = hook_command
            hook['timeout'] = 20
            aos_exists = True
            break

if not aos_exists:
    settings['hooks']['UserPromptSubmit'].append({
        'hooks': [{
            'type': 'command',
            'command': hook_command,
            'timeout': 20
        }]
    })

# Add env
if 'env' not in settings:
    settings['env'] = {}
settings['env']['AGENT_OS_ROOT'] = '$AOS_ROOT'

# Write back (preserves existing fields like mode, adsEnabled, etc.)
with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

if aos_exists:
    print('✓ Updated existing AOS hook')
else:
    print('✓ Added AOS hook')
"

# Clean up old wrong-location configs
[ -f "$HOME/.freebuff/settings.json" ] && rm -f "$HOME/.freebuff/settings.json" && echo "✓ Removed stale ~/.freebuff/settings.json"

echo ""
echo "=== AOS Host Adapter for Freebuff ==="
echo ""
echo "Installation complete!"
echo ""
echo "Config file:  $SETTINGS_FILE"
echo "Hook script:  $HOOK_INSTALLED"
echo "Bootstrap:    $BOOTSTRAP_INSTALLED"
echo ""
echo "To verify: send a prompt in freebuff CLI, then check /tmp/aos_hook_log.txt"
echo "To uninstall: bash $0 --uninstall"
