#!/usr/bin/env bash
# policies/check_repo_settings_carry_no_model_pins.sh
#
# The repo's COMMITTED Claude Code settings scopes must not pin models or
# provider routing.
#
# WHY. The dual-path model decision (architect-cto-01-0060, Shape D) puts
# model choice in TWO places and nowhere else: a managed repository pins
# harness ALIASES in policy text, and agent-fabric's broker launcher
# (runtime/openrouter/launch) exports the concrete ANTHROPIC_DEFAULT_*_MODEL
# pins per agent from routing/capabilities.json and routing/profiles.json. A model pin in a repo settings file would silently
# outrank the launcher's process-env pins (documented resolution order:
# user-scope env block beats process env), or — for modelOverrides — bind
# BOTH paths, because it is taken as the whole map from the highest
# precedence scope that sets it. Either way the dual path breaks without
# anything failing, which is why this is a guard.
#
# WHAT IS CHECKED: .claude/settings.json (the committed scope) carries
#   - no top-level "model" or "modelOverrides" key;
#   - no "effortLevel", "maxEffortLevel" or "modelSettings" key: effort is
#     the second routed dimension (routing/effort.json), and maxEffortLevel
#     especially, because the LOWEST value across scopes wins and a
#     committed cap cannot be raised back by a launch;
#   - no env entry naming ANTHROPIC_*, CLAUDE_CODE_SUBAGENT_MODEL or
#     CLAUDE_CODE_EFFORT_LEVEL;
#   - .mcp.json carries no model field either (it is committed and feeds
#     every clone).
#
# NOT CHECKED: .claude/settings.local.json (gitignored, per-session) and
# the user scopes (~/.claude/settings.json, ~/.claude/settings.local.json,
# $CLAUDE_CONFIG_DIR/settings.json) — the launcher fences ALL of them,
# this file included, refusing a launch when any carries a pin. This guard
# is about what is COMMITTED; the launcher is about what is LIVE.
#
# guards: .claude/settings.json
set -euo pipefail

# The managed repository to check: the working copy this runs in, or the
# one named. AGENT_FABRIC_SETTINGS_FILE names a file
# directly (the latter is the name gzapp's CI still uses).
REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
FILE="${AGENT_FABRIC_SETTINGS_FILE:-${AGENT_FABRIC_SETTINGS_FILE:-$REPO_ROOT/.claude/settings.json}}"

[[ -f "$FILE" ]] || { echo "check_repo_settings_carry_no_model_pins: OK — $FILE does not exist."; exit 0; }

# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "check_repo_settings_carry_no_model_pins.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
"$py" - "$FILE" <<'PY'
import json, sys

path = sys.argv[1]
try:
    d = json.load(open(path))
except Exception as exc:
    print(f"FAIL: {path} is not readable JSON ({exc}); a broken settings file")
    print("      silently disables every setting it carries.")
    sys.exit(1)

fails = []

if "model" in d:
    fails.append('top-level "model" is set — it pins the session model for '
                 'every session on this repo, both paths.')
if "modelOverrides" in d:
    fails.append('"modelOverrides" present: taken as the WHOLE MAP from the '
                 'highest-precedence scope that sets it, so it binds the '
                 'claude path too — model choice belongs to the launcher.')
# Effort is the second routed dimension (routing/effort.json) and its
# settings keys outrank the launcher the same way a model pin does:
# effortLevel sets the session's, modelSettings carries a per-model one,
# and maxEffortLevel is a CAP whose LOWEST value across scopes wins — so a
# committed cap silently lowers every class on every clone, which is the
# silent re-tuning the dimension exists to prevent.
# All four stay refused HERE even though the launcher's live scan now
# refuses only maxEffortLevel: a committed scope is read on every clone,
# nothing should pin anything in it, and no harness writes to it — unlike
# the user scope, where `/effort` persists modelSettings itself.
for key, why in (("effortLevel", "pins the session's thinking for every session on this repo"),
                 ("maxEffortLevel", "caps it — the lowest value across all scopes wins, so this one "
                                    "cannot be raised back by a launch"),
                 ("modelSettings", "carries per-model settings, effort included")):
    if key in d:
        fails.append(f'"{key}" present: it {why}. Effort is routed in routing/effort.json.')
env = d.get("env") or {}
bad_env = sorted(k for k in env
                 if k.startswith("ANTHROPIC_") or k in ("CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL"))
for k in bad_env:
    fails.append(f'env.{k} present — provider/routing env in a committed scope '
                 'would outrank the launcher pins.')

if fails:
    print(f"FAIL: {path} carries model pins ({len(fails)}):")
    for f in fails:
        print(f"      {fails.index(f)+1}. {f}")
    print("      Shape D puts model choice in the launcher + routing files;")
    print("      remove these from the committed settings file.")
    sys.exit(1)

print(f"check_repo_settings_carry_no_model_pins: OK — {path} carries no model pins.")
PY
