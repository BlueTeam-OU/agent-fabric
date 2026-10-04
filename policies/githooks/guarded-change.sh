#!/usr/bin/env bash
# policies/githooks/guarded-change.sh — does the commit being made carry a
# change of ITS OWN to what the fabric-coordinator role guards? Sourced by
# pre-commit and commit-msg; sets `guarded_what` (a label) and `guarded`
# (the staged paths under guard, empty when nothing is).
#
# In agent-fabric itself every path is guarded; in a managed project only
# .agent-fabric/. A MERGE changes only what differs from the clean
# three-way merge of its parents (git merge-tree --write-tree): a fold of
# main brings landed commits and changes nothing itself, even when both
# sides moved the guarded tree — a branch carrying a supplied fabric-ref
# folding main after a drain (devex-tooling, 2026-10-04; it once had to
# equal one parent's, devex-tooling, 2026-09-14). What a conflict
# resolution or a hand edit changes is the merge's own change, and the
# same rule as any commit applies to it. CI's tripwire
# (tools/fabric/guards/agent_fabric_dir_authority.py) reads merges the
# same way; the two must agree, or a fold needs --no-verify, which
# teaches sessions the wrong reflex.
guarded_change() {
    local fabric_root="$1" toplevel prefix staged_tree
    toplevel="$(git rev-parse --show-toplevel 2>/dev/null)"
    if [[ "$(readlink -f "$toplevel")" == "$(readlink -f "$fabric_root")" ]]; then
        guarded_what="agent-fabric itself"; prefix=""
    else
        guarded_what=".agent-fabric/"; prefix=".agent-fabric/"
    fi
    if [[ -n "$prefix" ]]; then
        mapfile -t guarded < <(git diff --cached --no-renames --name-only --diff-filter=ACDMRT -- "$prefix" 2>/dev/null)
    else
        mapfile -t guarded < <(git diff --cached --no-renames --name-only --diff-filter=ACDMRT 2>/dev/null)
    fi
    local merge_head; merge_head="$(git rev-parse -q --verify MERGE_HEAD 2>/dev/null)" || merge_head=""
    if [[ -z "$merge_head" ]]; then
        # Nothing staged against HEAD: an --amend (the index equals the
        # commit being rewritten) or an empty commit. In agent-fabric
        # itself every commit is the coordinator's, an amend included —
        # it rewrites a guarded commit and must carry the trailer.
        (( ${#guarded[@]} == 0 )) && [[ -z "$prefix" ]] && guarded=("(amend or empty commit: the whole repository)")
        return 0
    fi
    # A merge in progress: its own change is what the staged tree differs
    # by from the clean merge of HEAD and MERGE_HEAD — judged even when
    # nothing differs from HEAD, since keeping HEAD's guarded tree while
    # the other side moved it drops landed changes. Without that clean
    # merge (an octopus merge, a git older than 2.38) the merge is judged
    # against EVERY parent: whatever differs from any of them counts, so
    # an `-s ours` merge is not waved through (review of #96). Renames are
    # off, so a move out of a guarded path shows its source.
    staged_tree="$(git write-tree 2>/dev/null)" || return 0
    local -a against=()
    local clean rc
    if [[ "$(grep -c . "$(git rev-parse --git-path MERGE_HEAD)" 2>/dev/null)" -eq 1 ]]; then
        clean="$(git merge-tree --write-tree HEAD "$merge_head" 2>/dev/null)"; rc=$?
        clean="${clean%%$'\n'*}"
        (( rc == 0 || rc == 1 )) && [[ "$clean" =~ ^[0-9a-f]{40,64}$ ]] && against=("$clean")
    fi
    if (( ${#against[@]} == 0 )); then
        mapfile -t against < <(git rev-parse HEAD 2>/dev/null; git rev-parse $(cat "$(git rev-parse --git-path MERGE_HEAD)" 2>/dev/null) 2>/dev/null)
    fi
    local -a scope=(); [[ -n "$prefix" ]] && scope=(-- "$prefix")
    mapfile -t guarded < <(for a in "${against[@]}"; do
        git diff --no-renames --name-only "$a" "$staged_tree" "${scope[@]}" 2>/dev/null
    done | sort -u)
}
