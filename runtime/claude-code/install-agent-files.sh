#!/usr/bin/env bash
# runtime/claude-code/install-agent-files.sh
#
# Install THIS account's capability-class agent files,
# ~/.claude/agents/{code-low,code-medium,code-high,code-review}.md, from
# runtime/claude-code/agents/, with the review pin applied — and, on a
# language-culture login, the locale worker (below).
#
#   runtime/claude-code/install-agent-files.sh [--provider openrouter|anthropic] [--dry-run]
#
# The launcher calls this for its provider before every exec; bootstrap.sh
# at provisioning (anthropic, the unlaunched default); bin/fabric-model
# after a change to the review pin. The pin it applies is per agent and
# per provider: `routing.py pins --me --provider P` merges the column with
# the login's role and its model-profile.local.json.
#
# WHY A FILE CARRIES THE PIN. The review class rides the same tier alias
# as code-plan (fable): the Agent tool's `model` takes only the four
# aliases, and one alias carries one export, so through the export the
# reviewer would follow code-plan (as it once followed code-high on opus,
# 2026-09-13). The one route left (verified live on plain claude,
# 2026-09-15): the agent file's `model:` line decides when the dispatch
# leaves `model` unset, and the dispatch guard drops the dispatch's alias
# under a fabric launch after checking it was `fable`. The coding classes
# ride the exported aliases and keep the repo file's alias line; the pin
# here is the review class's alone, from routing, so there is one source.
# One file serves one launch at a time: two sessions of one account on
# different providers would rewrite it in turn, which the guard catches.
set -euo pipefail

FABRIC_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DRY_RUN=0; PROVIDER="${AGENT_FABRIC_LAUNCH_PROVIDER:-anthropic}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --provider) PROVIDER="$2"; shift 2 ;;
        --provider=*) PROVIDER="${1#--provider=}"; shift ;;
        *) echo "install-agent-files: unknown argument $1" >&2; exit 2 ;;
    esac
done

changed=0; same=0
put() {  # put <dest> <content-file>
    local dest="$1" src="$2"
    if [[ -f "$dest" ]] && cmp -s "$src" "$dest"; then
        same=$((same+1)); echo "  =  $dest"; return
    fi
    if (( DRY_RUN )); then echo "  +  $dest (would write)"; return; fi
    mkdir -p "$(dirname "$dest")"
    # Only ONCE, and only for a file the fabric did not write: the marker
    # test alone re-made this backup on every run, so the second run
    # replaced the user's original with the fabric's own previous file and
    # the thing the backup exists for was gone. Found when effort: started
    # rewriting files that were already the fabric's.
    if [[ -f "$dest" && ! -e "$dest.before-agent-fabric" ]] && ! grep -q "agent-fabric" "$dest" 2>/dev/null; then
        cp "$dest" "$dest.before-agent-fabric"
        echo "     (kept the previous file as $dest.before-agent-fabric)"
    fi
    install -m 644 "$src" "$dest"
    changed=$((changed+1)); echo "  +  $dest"
}

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
# Captured into a variable, NOT read from a process substitution: a
# substitution's exit status is invisible even under `set -e`, so a
# routing.py that raised left the map empty, every class lost its pin or
# its level, and the script still printed "N written" and exited 0
# (review of 2026-09-23, F8; the pins loop had the same hole since long
# before effort existed). bootstrap.sh calls this without the launcher's
# prior validation, so it is the first thing a bad local layer reaches.
# The value is captured in THIS shell before the loop reads it. A
# `while read < <(cmd)` cannot fail the script however cmd exits, and
# neither can an `exit` inside the substitution — it ends that subshell
# only. So each call is its own assignment, checked here.
route() {  # route <subcommand> — stdout of one routing.py call; non-zero on failure
    AGENT_FABRIC_ROOT="$FABRIC_ROOT" python3 "$FABRIC_ROOT/tools/fabric/routing.py" "$@" --me --provider "$PROVIDER"
}
ROUTED_PINS="$(route pins)" ||
    { echo "install-agent-files: routing.py pins failed; refusing to write agent files with no routing." >&2; exit 1; }
ROUTED_EFFORTS="$(route efforts)" ||
    { echo "install-agent-files: routing.py efforts failed; refusing to write agent files with no routing." >&2; exit 1; }
declare -A PIN_BY_CLASS=()
while read -r klass alias model; do
    [[ -n "$klass" ]] && PIN_BY_CLASS["$klass"]="$model"
done <<< "$ROUTED_PINS"
# ONE LAUNCH OF AN ACCOUNT AT A TIME, now for every class. Before effort,
# only code-review.md differed between providers, and agent-dispatch-guard.sh
# catches that one by comparing its `model:` with the launch's resolution.
# Effort is written into ALL five files per provider, so an openrouter
# launch leaves GLM's clamp in code-medium.md and an anthropic session
# dispatching afterwards runs at a level nothing chose for it — and no
# guard compares that. Extending the guard per dispatched class is the
# real fix and is deliberately NOT done here: it means buffering the hook's
# stdin so the class's file can be read before jq sees the call, and a
# half-made change to that fence is worse than a documented constraint
# (review of 2026-09-23, F7). Until then: run one launch of an account at a
# time, or re-run `bin/fabric-model apply` from the session you are in.
#
# The agent file is the ONLY per-class channel for effort: the Agent tool
# takes no effort on a dispatch (2.1.280, read back), and the environment
# variable would reach every subagent at once and flatten the per-class
# decision. So the level routing resolves for each class is written into
# its frontmatter here, exactly as the review class's model is.
# A class whose model expresses no effort gets NO line — absent is not the
# same as a default, and writing one would claim a decision nobody made.
declare -A EFFORT_BY_CLASS=()
while read -r klass level outcome; do
    [[ -n "$klass" && "$level" != "-" ]] && EFFORT_BY_CLASS["$klass"]="$level"
done <<< "$ROUTED_EFFORTS"
for f in code-low.md code-medium.md code-high.md code-plan.md code-review.md; do
    klass="${f%.md}"
    pin="${PIN_BY_CLASS[$klass]:-}"; effort="${EFFORT_BY_CLASS[$klass]:-}"
    src="$FABRIC_ROOT/runtime/claude-code/agents/$f"
    if [[ -n "$pin" || -n "$effort" ]]; then
        cp "$src" "$TMP/$f"
        [[ -n "$pin" ]] && sed -i "0,/^model: .*/s||model: $pin|" "$TMP/$f"
        # After `model:`, so the two routed values sit together; the
        # committed sources carry no effort: line, and lint refuses one.
        [[ -n "$effort" ]] && sed -i "0,/^model: .*/s||&\neffort: $effort|" "$TMP/$f"
        src="$TMP/$f"
    fi
    put "$CLAUDE_HOME/agents/$f" "$src"
done
# The locale worker: the language-culture role's subagent, one inert tool, whose
# system prompt is the locale's language (docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md).
# Installed as ~/.claude/agents/locale-worker.md on a login of that role
# whose name ends in a locale the fabric authored
# (identities/roles/language-culture/locale/<suffix>/worker.md); removed —
# by the `agent-fabric` marker in its description, as blind-reviewer.md
# below — from any other login, and from one whose locale has no worker,
# so a rebind never serves another locale's worker. No per-provider pin:
# the worker shares no alias with another class, so its model line rides
# as authored (the reviewer's file pin exists only because fable is
# code-plan's too). No routed EFFORT either, for the same reason — it is
# not a capability class, so routing/effort.json has nothing to say about
# it and it runs at whatever its model does by itself. Lint refuses a
# hand-written `effort:` in its source (one writer, as for the classes),
# so a level here would need a routed home first: the absence is a
# decision, not an oversight (re-review of 2026-09-23).
ROLE="$(AGENT_FABRIC_ROOT="$FABRIC_ROOT" python3 "$FABRIC_ROOT/runtime/identity.py" --role 2>/dev/null || true)"
LOGIN_NAME="$(id -un)"; LOCALE_SUFFIX="${LOGIN_NAME##*-}"
WORKER_SRC="$FABRIC_ROOT/identities/roles/language-culture/locale/$LOCALE_SUFFIX/worker.md"
WORKER_DEST="$CLAUDE_HOME/agents/locale-worker.md"
if [[ "$ROLE" == "language-culture" && -f "$WORKER_SRC" ]]; then
    put "$WORKER_DEST" "$WORKER_SRC"
elif [[ -f "$WORKER_DEST" ]] && grep -q "agent-fabric" "$WORKER_DEST" 2>/dev/null; then
    if (( DRY_RUN )); then echo "  -  $WORKER_DEST (would remove: role is ${ROLE:-unbound}, or no worker authored for locale $LOCALE_SUFFIX)"
    else rm -f "$WORKER_DEST"; echo "  -  $WORKER_DEST (removed: role is ${ROLE:-unbound}, or no worker authored for locale $LOCALE_SUFFIX)"; changed=$((changed+1)); fi
fi
# The locale search tools: an MCP server with one tool per engine the
# locale file configures — Google's results through SerpAPI, located in
# the locale, and Brave as a second index (runtime/mcp/websearch-locale), in the login's user-scope
# configuration (~/.claude.json, or $CLAUDE_CONFIG_DIR/.claude.json) on a
# language-culture login whose locale has a locale.json; removed — by the
# server path in its args — from any other. The key it needs is synced,
# never written here (docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md §5 rule 13).
LOCALE_FILE="$FABRIC_ROOT/identities/roles/language-culture/locale/$LOCALE_SUFFIX/locale.json"
CLAUDE_JSON="${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json"
MCP_INSTALL="$FABRIC_ROOT/runtime/mcp/websearch-locale/install.py"
mcp_flags=(); (( DRY_RUN )) && mcp_flags=(--dry-run)
# …and, on that login, the harness's own WebSearch denied in the user
# settings (the launcher removes it at exec; this is the fence for a
# session launched otherwise): a login that searches through its locale
# searches through that alone (the CEO, 2026-09-17).
USER_SETTINGS="$CLAUDE_HOME/settings.json"
if [[ "$ROLE" == "language-culture" && -f "$LOCALE_FILE" ]]; then
    out="$(python3 "$MCP_INSTALL" "$CLAUDE_JSON" set "$FABRIC_ROOT/runtime/mcp/websearch-locale/server.mjs" "$LOCALE_FILE" "${mcp_flags[@]}")"
    out+="${out:+$'\n'}$(python3 "$MCP_INSTALL" "$USER_SETTINGS" deny-websearch "${mcp_flags[@]}")"
else
    out="$(python3 "$MCP_INSTALL" "$CLAUDE_JSON" remove "${mcp_flags[@]}")"
    out+="${out:+$'\n'}$(python3 "$MCP_INSTALL" "$USER_SETTINGS" allow-websearch "${mcp_flags[@]}")"
fi
out="$(printf '%s' "$out" | sed '/^$/d')"
if [[ -n "$out" ]]; then echo "$out"; while IFS= read -r line; do [[ "$line" == "  +  "* && "$line" != *"would write"* ]] && changed=$((changed+1)); [[ "$line" == "  =  "* ]] && same=$((same+1)); done <<<"$out"; fi
# The review class was installed as blind-reviewer.md until 2026-09-15; a
# copy of ours left there would offer the retired type beside the new one.
old="$CLAUDE_HOME/agents/blind-reviewer.md"
if [[ -f "$old" ]] && grep -q "agent-fabric" "$old" 2>/dev/null; then
    if (( DRY_RUN )); then echo "  -  $old (would remove: retired name of code-review)"
    else rm -f "$old"; echo "  -  $old (retired name of code-review)"; changed=$((changed+1)); fi
fi
echo "agent files ($PROVIDER): $changed written, $same already current."
