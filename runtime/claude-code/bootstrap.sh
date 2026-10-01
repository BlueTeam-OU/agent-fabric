#!/usr/bin/env bash
# runtime/claude-code/bootstrap.sh
#
# Make agent-fabric's workspace instructions available to a Claude Code
# session launched from the parent projects/ directory, for THIS account.
#
#   runtime/claude-code/bootstrap.sh [--projects DIR] [--dry-run]
#
# Writes, idempotently, and only machine-local files:
#   <projects>/CLAUDE.md               3 lines; imports agent-fabric/CLAUDE.md
#   <projects>/.claude/settings.json   hooks + status line pointing at agent-fabric
#   (removes ~/.claude/commands/role.md if an earlier bootstrap installed it:
#    /role is retired — a role is bound from the shell, bin/fabric-role)
#   ~/.claude/agents/{code-*,code-review}.md
#                                      the capability-class agent files, from runtime/claude-code/agents/,
#                                      via install-agent-files.sh (the review pin, merged for this login)
#   ~/.claude/hooks/review-bash-guard.sh
#                                      the review class's Bash fence; the code-review agent file
#                                      looks here when the launch project has no .claude/ copy
#   ~/.claude/settings.json            the fabric's user-scope keys (runtime/claude-code/user-settings.py):
#                                      attribution commit "", pr "", sessionUrl false — the harness's
#                                      Co-Authored-By/Generated-with reminder off at its source —
#                                      showThinkingSummaries and verbose on, tui default, the
#                                      memory-write check hook (PostToolUse), env DISABLE_AUTOUPDATER,
#                                      permissions (the fabric's commands allowed, auto mode), autoMode
#                                      from policies/auto-mode.json and the auto-mode wizard off;
#                                      every other key kept
#   ~/.claude/skills/subagent-dispatch/SKILL.md
#   ~/.claude/skills/fabric-decisions/SKILL.md
#   ~/.claude/skills/branch-hygiene/SKILL.md
#   ~/.claude/skills/agent-jobs/SKILL.md
#   ~/.claude/skills/gzcoord-send/SKILL.md, gzcoord-receive/SKILL.md
#                                      the dispatch policy as a loadable skill, from policies/
#   ~/.local/bin/<name>                every command a session runs, by name
#                                      (runtime/claude-code/commands.json)
#   ~/.config/systemd/user/agent-fabric-agentd.service
#                                      the control agent (runtime/control/), enabled and started
#                                      in this account's user manager when one is running
#   ~/.config/systemd/user/gzcoord-relay.service
#                                      ONLY on the account whose workspace hosts the relay
#                                      ($PROJECTS/.gzcoord/venv exists): the relay as a unit
#   ~/.cache/agent-fabric/langid/venv/  the language detector (pycld2) for the control agent's
#                                      script op (runtime/langid/), best effort
#   (removes ~/.doppler, ~/.local/bin/doppler and ~/.config/agent-fabric/secrets-source:
#    Doppler is retired, ADR-038)
#
# Nothing here names an agent: the hooks ask the OS who is running at
# session start. Nothing here makes projects/ a git repository. A managed
# project keeps its own CLAUDE.md and .claude/ for sessions launched inside
# it. Re-running refreshes only what differs.
#
# The projects directory defaults to the parent of this checkout — the
# layout agent-fabric assumes is projects/agent-fabric beside the working
# copies it manages.
set -euo pipefail

FABRIC_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
PROJECTS="$(dirname "$FABRIC_ROOT")"
DRY_RUN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --projects) PROJECTS="$(cd "$2" && pwd)"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        *) echo "bootstrap: unknown argument $1" >&2; exit 2 ;;
    esac
done
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

changed=0; same=0; failed=0
put() {  # put <dest> <content-file>
    local dest="$1" src="$2"
    if [[ -f "$dest" ]] && cmp -s "$src" "$dest"; then
        same=$((same+1)); echo "  =  $dest"; return
    fi
    if (( DRY_RUN )); then echo "  +  $dest (would write)"; return; fi
    mkdir -p "$(dirname "$dest")"
    if [[ -f "$dest" ]] && ! grep -q "agent-fabric" "$dest" 2>/dev/null; then
        cp "$dest" "$dest.before-agent-fabric"
        echo "     (kept the previous file as $dest.before-agent-fabric)"
    fi
    install -m 644 "$src" "$dest"
    changed=$((changed+1)); echo "  +  $dest"
}

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

echo "agent-fabric bootstrap for agent $(python3 "$FABRIC_ROOT/runtime/identity.py") — projects: $PROJECTS"

# 1. The workspace CLAUDE.md: three lines, an import, no instructions of its own.
put "$PROJECTS/CLAUDE.md" "$FABRIC_ROOT/runtime/claude-code/workspace/CLAUDE.md"

# 2. The workspace settings: hooks and status line, with the root substituted.
python3 - "$FABRIC_ROOT/runtime/claude-code/workspace/settings.json" "$FABRIC_ROOT" "$PROJECTS/.claude/settings.json" "$TMP/settings.json" <<'PY'
import json, os, sys
template, root, existing_path, out = sys.argv[1:5]
tpl = json.load(open(template))
tpl.pop("_comment", None)
def sub(v):
    if isinstance(v, str): return v.replace("$AGENT_FABRIC_ROOT", root)
    if isinstance(v, list): return [sub(x) for x in v]
    if isinstance(v, dict): return {k: sub(x) for k, x in v.items()}
    return v
tpl = sub(tpl)
# Merge over an existing workspace settings file: keep everything it has,
# add or refresh only the entries agent-fabric owns. Ownership is by the
# hook path SHAPE (…/runtime/claude-code/hooks/…, and the GZCoord inbox
# under communication/), not by the current root: an entry written by an
# earlier bootstrap from another checkout (a shared path, before an
# account got its own clone) must be replaced, not kept beside the new one.
OWNED = ("/runtime/claude-code/hooks/", "/communication/gzcoord/scripts/inbox.mjs")
doc = {}
if os.path.exists(existing_path):
    try: doc = json.load(open(existing_path)) or {}
    except ValueError: doc = {}
doc["statusLine"] = tpl["statusLine"]
# env: the template's keys are set, an existing file's other keys kept.
if tpl.get("env"):
    env = doc.get("env") if isinstance(doc.get("env"), dict) else {}
    env.update(tpl["env"]); doc["env"] = env
hooks = doc.setdefault("hooks", {})
for event, groups in tpl["hooks"].items():
    kept = [g for g in hooks.get(event, []) if not any(o in json.dumps(g) for o in OWNED)]
    hooks[event] = kept + groups
json.dump(doc, open(out, "w"), indent=2)
open(out, "a").write("\n")
PY
put "$PROJECTS/.claude/settings.json" "$TMP/settings.json"

# 3. The /role command is retired (owner, 2026-09-15): a role is bound from
#    a login shell with bin/fabric-role and reaches the session in its
#    system prompt at launch; nothing inside a session changes it. An
#    earlier bootstrap installed ~/.claude/commands/role.md — remove OUR
#    copy (it names agent-fabric, the test put() uses), never a file the
#    human wrote; a .before-agent-fabric sibling is theirs and stays.
retired="$CLAUDE_HOME/commands/role.md"
if [[ -f "$retired" ]] && grep -q "agent-fabric" "$retired" 2>/dev/null; then
    if (( DRY_RUN )); then echo "  -  $retired (would remove: /role is retired, use bin/fabric-role)"
    else rm -f "$retired"; changed=$((changed+1)); echo "  -  $retired (removed: /role is retired, use bin/fabric-role)"; fi
fi
# The capability-class agent files, with the review pin applied for this
# account: runtime/claude-code/install-agent-files.sh (bin/fabric-model
# re-runs it when the account's local layer changes the pin).
if (( DRY_RUN )); then
    bash "$FABRIC_ROOT/runtime/claude-code/install-agent-files.sh" --dry-run
else
    bash "$FABRIC_ROOT/runtime/claude-code/install-agent-files.sh"
fi
# The review class's Bash fence rides with its agent file: the agent runs
# unisolated in the session's clone, and a review dispatched from
# projects/ (no .claude/ of its own) found no guard and lost Bash entirely
# (docs/live-checks/2026-09-13-openrouter-routing.md).
put "$CLAUDE_HOME/hooks/review-bash-guard.sh" "$FABRIC_ROOT/runtime/claude-code/hooks/review-bash-guard.sh"
# Every command a session is told to run, on PATH under its own name
# (runtime/claude-code/commands.json): a skill says `gzcoord-send <file>`,
# never `node "$AGENT_FABRIC_ROOT/…"`, because the harness asks before any
# command carrying a shell expansion (the owner, 2026-09-26). A link this
# fabric made — to this checkout or another one's same path — is
# refreshed; anything else at that name is the account's and is refused,
# never replaced.
LOCAL_BIN="${AGENT_FABRIC_LOCAL_BIN:-$HOME/.local/bin}"
# Read first, then loop: a list that cannot be read inside a process
# substitution linked nothing and reported success (review of #42).
if ! commands="$(python3 -c 'import json,sys; [print(f"{k}\t{v}") for k, v in json.load(open(sys.argv[1]))["commands"].items()]' \
                   "$FABRIC_ROOT/runtime/claude-code/commands.json")"; then
    echo "  !  runtime/claude-code/commands.json unreadable — no command linked" >&2; failed=$((failed+1)); commands=""
fi
while IFS=$'\t' read -r name rel; do
    [[ -n "$name" ]] || continue
    target="$FABRIC_ROOT/$rel"; link="$LOCAL_BIN/$name"
    if [[ -L "$link" && "$(readlink "$link")" == "$target" ]]; then
        echo "  =  $link"; same=$((same+1)); continue
    fi
    if [[ -e "$link" || -L "$link" ]] && ! { [[ -L "$link" ]] && [[ "$(readlink "$link")" == */"$rel" ]]; }; then
        echo "  !  $link is not a link this fabric made — left alone; $name is not on PATH" >&2
        failed=$((failed+1)); continue
    fi
    if (( DRY_RUN )); then echo "  +  $link -> $target (would link)"; continue; fi
    mkdir -p "$LOCAL_BIN" && ln -sfn "$target" "$link" && { echo "  +  $link -> $target"; changed=$((changed+1)); } \
        || { echo "  !  $link: could not link" >&2; failed=$((failed+1)); }
done <<<"$commands"
# Linked BEFORE the settings are written: an allow rule is granted only for
# a name whose link is the fabric's script (user-settings.py).
# The login's user settings carry what the fabric wants in every session
# of the account whatever directory it launches from: the harness's
# attribution reminder — a system reminder asking for a Co-Authored-By
# trailer and a "Generated with" footer, sent on the first turn and after
# every model switch, outside any launch prompt — switched off where it
# is built (an empty attribution text hides it, and the harness then says
# the opposite; docs/live-checks/2026-09-18-attribution-reminder-off.md;
# the guard policies/ban_generated_by_attribution.sh stays as the fence),
# and the thinking summaries and verbose tool output the operator reads a
# session by. The writer's docstring has each key's reason.
# The dry run reports the refusal the same way and goes on, so both
# paths reach the same summary line.
if (( DRY_RUN )); then python3 "$FABRIC_ROOT/runtime/claude-code/user-settings.py" "$CLAUDE_HOME/settings.json" --dry-run || failed=$((failed+1))
else
    if out="$(python3 "$FABRIC_ROOT/runtime/claude-code/user-settings.py" "$CLAUDE_HOME/settings.json")"; then
        echo "$out"
        [[ "$out" == "  +  "* ]] && changed=$((changed+1)) || same=$((same+1))
    else
        # The writer said why on stderr; an unreadable settings file is
        # the account's to fix, and the run must not report it settled.
        failed=$((failed+1))
    fi
fi
# The dispatch policy is a skill the project CLAUDE.md files tell a session
# to load (`subagent-dispatch`); user-scope, so no project needs a copy.
put "$CLAUDE_HOME/skills/subagent-dispatch/SKILL.md" "$FABRIC_ROOT/policies/subagent-dispatch/SKILL.md"
put "$CLAUDE_HOME/skills/fabric-decisions/SKILL.md" "$FABRIC_ROOT/policies/fabric-decisions/SKILL.md"
put "$CLAUDE_HOME/skills/branch-hygiene/SKILL.md" "$FABRIC_ROOT/policies/branch-hygiene/SKILL.md"
put "$CLAUDE_HOME/skills/agent-jobs/SKILL.md" "$FABRIC_ROOT/policies/agent-jobs/SKILL.md"
# Talking to other agents is two procedures, each a skill: composing and
# sending a message, and receiving one (the watch, and what a delivery is).
put "$CLAUDE_HOME/skills/gzcoord-send/SKILL.md" "$FABRIC_ROOT/communication/gzcoord/skills/gzcoord-send/SKILL.md"
put "$CLAUDE_HOME/skills/gzcoord-receive/SKILL.md" "$FABRIC_ROOT/communication/gzcoord/skills/gzcoord-receive/SKILL.md"

# 4. The agent-fabric checkout this runs from enforces its own git
#    discipline at commit time (policies/githooks/commit-msg). A repo
#    config, so it is per checkout and never committed.
if [[ "$(git -C "$FABRIC_ROOT" config --get core.hooksPath 2>/dev/null)" != "policies/githooks" ]]; then
    (( DRY_RUN )) || git -C "$FABRIC_ROOT" config core.hooksPath policies/githooks
    echo "  +  $FABRIC_ROOT: core.hooksPath = policies/githooks"
else
    echo "  =  $FABRIC_ROOT: core.hooksPath = policies/githooks"
fi

# 5. The same hooks in every registered working copy beside this checkout:
#    they carry the attribution ban and the .agent-fabric/ fence (only a
#    session holding fabric-coordinator commits under .agent-fabric/, and
#    the commit records the role). A repo config per working copy, never
#    committed; a directory that is not a registered project is left alone.
HOOKS_ABS="$FABRIC_ROOT/policies/githooks"
trusted=("$PROJECTS" "$FABRIC_ROOT")
for wc in "$PROJECTS"/*/; do
    wc="${wc%/}"
    # git's own answer, not a test for a .git DIRECTORY: a linked worktree
    # carries a .git file and is a working copy like any other.
    [[ "$wc" != "$FABRIC_ROOT" ]] && [[ "$(git -C "$wc" rev-parse --is-inside-work-tree 2>/dev/null)" == true ]] || continue
    pid="$(AGENT_FABRIC_ROOT="$FABRIC_ROOT" python3 "$FABRIC_ROOT/tools/fabric/workingcopy.py" "$wc" 2>/dev/null \
        | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("project") or "")
except Exception: print("")')"
    [[ -n "$pid" ]] || continue
    trusted+=("$wc")
    if [[ "$(git -C "$wc" config --get core.hooksPath 2>/dev/null)" != "$HOOKS_ABS" ]]; then
        (( DRY_RUN )) || git -C "$wc" config core.hooksPath "$HOOKS_ABS"
        echo "  +  $wc ($pid): core.hooksPath = $HOOKS_ABS"; changed=$((changed+1))
    else
        echo "  =  $wc ($pid): core.hooksPath"; same=$((same+1))
    fi
done
# 5b. Those same folders trusted in Claude Code — the workspace, this
#     checkout and each registered working copy, which the fabric cloned
#     from the registry's remotes — so a new account's first session asks
#     no trust question (tools/fabric/workspace_trust.py says why).
python3 "$FABRIC_ROOT/tools/fabric/workspace_trust.py" $( (( DRY_RUN )) && echo --dry-run ) "${trusted[@]}" \
    || echo "  !  workspace trust not recorded (above); a first session asks for it"

# 6. The control agent: a systemd user unit that answers the coordinator's
#    fabric-ctl over the relay (runtime/control/). Enabled and started in
#    this account's user manager — the one that exists because the account
#    lingers (persist-accounts.sh); with no manager (a bare `sudo -u`, a
#    scratch HOME in a test) the unit is only installed, and starts at the
#    next login. Restarted only when the unit file itself changed: a pull
#    that changes the daemon's code is the daemon's own business (it exits,
#    Restart= brings it back).
UNIT_NAME=agent-fabric-agentd
before=$changed
put "$HOME/.config/systemd/user/$UNIT_NAME.service" "$FABRIC_ROOT/runtime/control/$UNIT_NAME.service"
if (( ! DRY_RUN )); then
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    if [[ -S "$XDG_RUNTIME_DIR/bus" ]] && command -v systemctl >/dev/null 2>&1 \
       && systemctl --user daemon-reload >/dev/null 2>&1; then
        systemctl --user enable --now "$UNIT_NAME" >/dev/null 2>&1 || true
        # Run BY the daemon (`fabric-ctl upgrade fabric`), a restart here would
        # kill the process waiting on this script: it restarts itself after
        # replying instead (runtime/control/upgrade.mjs).
        if (( changed > before )); then
            if [[ -n "${AGENT_FABRIC_DEFER_AGENTD_RESTART:-}" ]]; then echo "  *  $UNIT_NAME: unit changed; restart left to the caller"
            else systemctl --user restart "$UNIT_NAME" >/dev/null 2>&1 || true; fi
        fi
        echo "  *  $UNIT_NAME: $(systemctl --user is-active "$UNIT_NAME" 2>/dev/null || true) (systemctl --user status $UNIT_NAME)"
    else
        echo "  !  $UNIT_NAME: installed, not started — no user manager at $XDG_RUNTIME_DIR/bus (loginctl enable-linger $(id -un), or the next login starts it)"
    fi
fi

# 6b. The GZCoord relay as a user unit — ONLY on the account that hosts
#     it: the one whose workspace runtime dir ($PROJECTS/.gzcoord/) holds
#     the relay's venv. Every other account is a client and gets nothing
#     here (BRIDGE-RELAY-SETUP.md §Hosting). Same mechanics as the control
#     agent above; the unit's own ConditionPathExists is the second fence.
#     The unit hard-codes %h/projects/.gzcoord (static, like the control
#     agent's), so it is installed only where $PROJECTS is that path.
if [[ -x "$PROJECTS/.gzcoord/venv/bin/claude-bridge" ]]; then
    RELAY_UNIT=gzcoord-relay
    if [[ "$PROJECTS" != "$(readlink -f "$HOME/projects" 2>/dev/null)" ]]; then
        echo "  !  $RELAY_UNIT: not installed — the unit expects the workspace at \$HOME/projects, this one is $PROJECTS"
    else
    before=$changed
    put "$HOME/.config/systemd/user/$RELAY_UNIT.service" "$FABRIC_ROOT/communication/gzcoord/runtime/$RELAY_UNIT.service"
    if (( ! DRY_RUN )); then
        export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
        if [[ -S "$XDG_RUNTIME_DIR/bus" ]] && command -v systemctl >/dev/null 2>&1 \
           && systemctl --user daemon-reload >/dev/null 2>&1; then
            # A relay that is not the unit's — hand-started, or an older session's
            # detached spawn — holds the port: starting the unit against it would
            # crash-loop every three seconds while is-active said "active". Enable
            # for the next boot, say who holds the port, and leave the start to a
            # person who has stopped it.
            relay_state="$(systemctl --user is-active "$RELAY_UNIT" 2>/dev/null || true)"
            if [[ "$relay_state" != active ]] && curl -sf -m 1 http://127.0.0.1:8765/status >/dev/null 2>&1; then
                # ss is not in the host contract (iproute2 is absent on a minimal image): fall back to the process name.
                holder="$(ss -Hltnp 'sport = :8765' 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)"
                [[ -n "$holder" ]] || holder="$(pgrep -u "$(id -u)" -x claude-bridge 2>/dev/null | head -1)"
                systemctl --user enable "$RELAY_UNIT" >/dev/null 2>&1 || true
                if [[ "$relay_state" == activating ]]; then
                    echo "  !  $RELAY_UNIT: RESTARTING against a relay outside the unit that holds 127.0.0.1:8765 (pid ${holder:-unknown}); stop that relay and the unit takes the port (systemctl --user status $RELAY_UNIT)"
                else
                    echo "  !  $RELAY_UNIT: enabled, NOT started — a relay outside the unit holds 127.0.0.1:8765 (pid ${holder:-unknown}); stop it, then: systemctl --user start $RELAY_UNIT"
                fi
            else
                systemctl --user enable --now "$RELAY_UNIT" >/dev/null 2>&1 || true
                (( changed > before )) && systemctl --user restart "$RELAY_UNIT" >/dev/null 2>&1 || true
                echo "  *  $RELAY_UNIT (this workspace hosts the relay): $(systemctl --user is-active "$RELAY_UNIT" 2>/dev/null || true)"
            fi
        else
            echo "  !  $RELAY_UNIT: installed, not started — no user manager at $XDG_RUNTIME_DIR/bus"
        fi
    fi
    fi
fi

# 7. The language detector for the control agent's `script` op
#    (runtime/langid/, pycld2 in its own venv), best effort — offline or
#    without a C++ compiler, the op reports `language` as unavailable and
#    nothing else changes.
if (( DRY_RUN )); then bash "$FABRIC_ROOT/runtime/langid/install.sh" --dry-run || true
else bash "$FABRIC_ROOT/runtime/langid/install.sh" || echo "  !  langid: not installed (above); fabric-ctl <login> script reports language unavailable until it is"; fi

# 8. Doppler, retired (ADR-038): what it left in this account goes on the
#    upgrade that brings the fabric without it (retire-doppler.py).
dry_arg=(); (( DRY_RUN )) && dry_arg=(--dry-run)
python3 "$FABRIC_ROOT/runtime/claude-code/retire-doppler.py" "${dry_arg[@]}" || failed=$((failed+1))

if (( failed )); then echo "bootstrap: $changed written, $same already current, $failed NOT written (above)."
else echo "bootstrap: $changed written, $same already current."; fi
echo "Launch from $PROJECTS: cd \"$PROJECTS\" && claude   — the session starts as $(python3 "$FABRIC_ROOT/runtime/identity.py")."
