#!/usr/bin/env bash
# runtime/github/trial-merge.sh
#
# >>> help
# Do these branches combine? Merge them, in the order given, onto the
# base in a throwaway worktree, optionally run the project's own check
# on the result, say what happened, and remove the worktree.
#
# THE QUESTION IT ANSWERS. A change that depends on another agent's
# branch has to know the two combine before it is armed, or before "the
# code is on a branch" is taken as enough of a dependency. CI and the
# merge queue test a PR against main only, never with a sibling it
# depends on, and folding the sibling into one's own clone froze that
# clone for twenty minutes or left a hand-made worktree behind
# (2026-09-26). This answers from the side, and touches nothing of the
# caller's: its HEAD, index, working tree and branches are as they were.
#
# WHAT IT SAYS
#   combines           every ref merged; the resulting tree hash is given
#   conflicts          <ref> did not merge, and the conflicted paths
#   could not merge    <ref> failed for another reason (git's line is given):
#                      unrelated histories, a missing object — never read
#                      as a conflict. The clone's hooks are not run: this
#                      merge is never committed anywhere.
#   check passed       (--check) the project's check passed on the result
#   check failed       (--check) it ran and failed; its last lines are shown
#   check unavailable  (--check) it could not say: timed out, not found,
#                      its lease still held, or its verdict line missing —
#                      never read as a pass
#   check not run      the refs did not combine, so there is nothing to check
#   The shas tried are printed: a result is true for those shas only, and
#   says nothing of branches not named or of the base after it moves.
#   It reserves, pushes and decides nothing.
#
# THE CHECK is the project's: projects/<id>/integration/gh/trial.json in
# agent-fabric, found from this clone's remote —
#   {"check": ["make", "trial-check"], "timeout_s": 600,
#    "verdict": "^trial-check: (PASS|FAIL|UNAVAILABLE)", "lease": "..."}
# check is an argv run in the worktree (never through a shell). verdict,
# when set, is read from the output's last matching line and wins over the
# exit code (make exits 2 for every kind of failure); a declared verdict
# that never appears is unavailable, whatever the exit code. lease, when
# set, runs it under that host lease (fabric-lease), so two agents' builds
# queue instead of overloading the host — leave it unset when the check
# takes a lease itself. A project that declares none gets merge-only
# results, and --check says so. A fresh worktree has no build cache, so a
# compiled check starts cold.
#
# Usage:
#   runtime/github/trial-merge.sh <PR number | branch>... [--base <ref>] [--check] [--json]
#
# Exit codes:
#   0  combines (and, with --check, the check passed)
#   1  conflicts, or the check failed
#   2  could not try (a failed fetch, a ref not on origin, no room, bad
#      usage, a merge that failed without a conflict), or the check was
#      unavailable
#
# Environment (the self-test):
#   AGENT_FABRIC_TRIAL_CONFIG   path of the trial.json to use instead of the project's
#   AGENT_FABRIC_TRIAL_MIN_FREE_KB   free space the worktree needs beyond its size (default 1 GiB)
# <<< help

set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fabric="${AGENT_FABRIC_ROOT:-$here/../..}"
JSON=0; CHECK=0; BASE=""; REFS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json) JSON=1; shift ;;
        --check) CHECK=1; shift ;;
        --base) [[ $# -ge 2 && -n "$2" ]] || { echo "trial-merge: --base takes a ref" >&2; exit 2; }; BASE="$2"; shift 2 ;;
        -h|--help) sed -n '/^# >>> help/,/^# <<< help/p' "$0" | sed '1d;$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) echo "trial-merge: unknown option '$1' (try --help)" >&2; exit 2 ;;
        *) REFS+=("$1"); shift ;;
    esac
done
(( ${#REFS[@]} > 0 )) || { echo "trial-merge: name at least one PR number or branch (try --help)" >&2; exit 2; }
for t in git jq; do command -v "$t" >/dev/null 2>&1 || { echo "trial-merge: $t is required" >&2; exit 2; }; done
top="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "trial-merge: not inside a git working copy" >&2; exit 2; }
cd "$top" || exit 2

git fetch -q --prune origin 2>/dev/null || { echo "trial-merge: git fetch origin failed; nothing tried" >&2; exit 2; }
if [[ -z "$BASE" ]]; then
    BASE="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)"; [[ -n "$BASE" ]] || BASE="origin/main"
fi
base_sha="$(git rev-parse -q --verify "$BASE^{commit}")" || { echo "trial-merge: the base $BASE is not in this clone; nothing tried" >&2; exit 2; }

# Each ref as the sha on origin: a PR by its head branch, a branch by name.
names=(); shas=()
for r in "${REFS[@]}"; do
    b="$r"
    if [[ "$r" =~ ^[0-9]+$ ]]; then
        command -v gh >/dev/null 2>&1 || { echo "trial-merge: #$r needs gh to find its branch; nothing tried" >&2; exit 2; }
        b="$(gh pr view "$r" --json headRefName --jq .headRefName 2>/dev/null)" || b=""
        [[ -n "$b" ]] || { echo "trial-merge: #$r is not a pull request gh can read; nothing tried" >&2; exit 2; }
    fi
    b="${b#origin/}"
    s="$(git rev-parse -q --verify "refs/remotes/origin/$b^{commit}")" || { echo "trial-merge: $b is not a branch on origin; nothing tried" >&2; exit 2; }
    names+=("$b"); shas+=("$s")
done

# The project's check, when asked for.
check_argv=(); check_timeout=1800; check_lease=""; check_verdict=""; check_state="not asked"
if (( CHECK )); then
    cfg="${AGENT_FABRIC_TRIAL_CONFIG:-}"
    if [[ -z "$cfg" ]]; then
        pid="$(python3 "$fabric/tools/fabric/workingcopy.py" "$top" 2>/dev/null | jq -r '.project // empty' 2>/dev/null)"
        [[ -n "$pid" ]] && cfg="$fabric/projects/$pid/integration/gh/trial.json"
    fi
    if [[ -n "$cfg" && -f "$cfg" ]]; then
        mapfile -t check_argv < <(jq -r '.check // [] | .[]' "$cfg" 2>/dev/null)
        check_timeout="$(jq -r '.timeout_s // 1800' "$cfg")"
        check_lease="$(jq -r '.lease // empty' "$cfg")"
        check_verdict="$(jq -r '.verdict // empty' "$cfg")"
    fi
    if (( ${#check_argv[@]} > 0 )); then check_state="pending"; else check_state="none declared"; fi
fi

# Room for a checkout of the base, plus a margin.
need_kb=$(( $(git ls-tree -r -l "$base_sha" | awk '$4 != "-" {s += $4} END {print int(s / 1024)}') + ${AGENT_FABRIC_TRIAL_MIN_FREE_KB:-1048576} ))
scratch="${TMPDIR:-/tmp}"
free_kb="$(df -Pk "$scratch" | awk 'NR == 2 {print $4}')"
(( free_kb >= need_kb )) || { echo "trial-merge: $scratch has ${free_kb} KB free, the worktree needs ${need_kb}; nothing tried" >&2; exit 2; }

# A worktree of a run that died is this tool's to clear, and only when its
# owner is gone: a concurrent run's is left alone.
# A run writes its pid right after making its worktree, so a worktree
# with none is from a run killed in that gap: dead within seconds. The
# hour is a generous margin, not a bound on how long a check may run.
for d in "$scratch"/trial-merge.*; do
    [[ -d "$d" ]] || continue
    if [[ -f "$d.pid" ]]; then kill -0 "$(cat "$d.pid" 2>/dev/null)" 2>/dev/null && continue
    else [[ -n "$(find "$d" -maxdepth 0 -mmin +60 2>/dev/null)" ]] || continue; fi
    git worktree remove --force "$d" >/dev/null 2>&1; rm -rf "$d" "$d.pid" "$d.pid.tmp" "$d.out"
done
git worktree prune 2>/dev/null

wt="$(mktemp -d "$scratch/trial-merge.XXXXXX")" || { echo "trial-merge: cannot make a worktree directory under $scratch" >&2; exit 2; }
# Written whole under another name, then moved: a concurrent run's sweep
# never reads an empty pid and takes this live worktree for a dead one.
echo $$ > "$wt.pid.tmp" && mv -f "$wt.pid.tmp" "$wt.pid"
# The check runs in its own process group so that a killed run takes the
# whole check with it; an orphaned build would outlive the worktree.
# The group is killed at the end even when the check exited on its own:
# whatever it started in the background (a server, a build daemon) would
# otherwise outlive the worktree it runs in.
# The group is not always the whole check: a declared lease runs it in a
# process group of its own (fabric-lease's set -m). It stays in the
# SESSION setsid gave the check, though, wherever it moves, so every
# process of that session is the check's and is ended with it; anything
# of this login still working inside the worktree is too, as a backstop
# (a process can leave the session only by making its own, as a daemon
# does on purpose).
worktree_procs() {
    local p cwd sid me; me="$(id -u)"
    for p in /proc/[0-9]*; do
        [[ "$(stat -c %u "$p" 2>/dev/null)" == "$me" ]] || continue
        if [[ -n "$cpid" ]]; then
            sid="$(sed 's/^.*) //' "$p/stat" 2>/dev/null | awk '{print $4}')"
            [[ "$sid" == "$cpid" ]] && { echo "${p#/proc/}"; continue; }
        fi
        cwd="$(readlink "$p/cwd" 2>/dev/null)" || continue
        [[ "$cwd" == "$wt" || "$cwd" == "$wt"/* ]] && echo "${p#/proc/}"
    done
}
end_worktree_procs() { local pids; pids="$(worktree_procs)"; [[ -n "$pids" ]] && kill -TERM $pids 2>/dev/null; return 0; }
cpid=""
cleanup() { [[ -n "$cpid" ]] && kill -TERM -- "-$cpid" 2>/dev/null; end_worktree_procs; git -C "$top" worktree remove --force "$wt" >/dev/null 2>&1; rm -rf "$wt" "$wt.pid" "$wt.out"; git -C "$top" worktree prune 2>/dev/null; }
trap cleanup EXIT
trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP
# Two runs at once in one repository can make an add fail for a moment
# (another run's prune, git's config lock): one add lost that race in CI.
# A few tries, each clearing only its own half-made entry, then git's own
# last line if it still fails.
add_err=""
for pause in 0.2 0.5 1 2; do
    add_err="$(git worktree add -q --detach "$wt" "$base_sha" 2>&1)" && { add_err=""; break; }
    git worktree remove --force "$wt" >/dev/null 2>&1; mkdir -p "$wt"; sleep "$pause"
done
[[ -z "$add_err" ]] || { echo "trial-merge: git worktree add failed (${add_err##*$'\n'}); nothing tried" >&2; exit 2; }

result="combines"; failed_ref=""; conflicted=(); tree=""; merge_err=""
start=$SECONDS
for i in "${!names[@]}"; do
    if ! merge_err="$(git -C "$wt" -c user.name=trial-merge -c user.email=trial-merge@invalid -c commit.gpgsign=false \
            merge -q --no-ff --no-edit --no-verify "${shas[$i]}" 2>&1 >/dev/null)"; then
        failed_ref="${names[$i]}"
        mapfile -t conflicted < <(git -C "$wt" diff --name-only --diff-filter=U)
        if (( ${#conflicted[@]} > 0 )); then result="conflicts"; else result="could not merge"; fi
        git -C "$wt" merge --abort >/dev/null 2>&1
        break
    fi
done
[[ "$result" == combines ]] && tree="$(git -C "$wt" rev-parse 'HEAD^{tree}')"

check_rc=""; check_tail=""
[[ "$result" != combines && "$check_state" == pending ]] && check_state="not run: did not combine"
if [[ "$result" == combines && "$check_state" == pending ]]; then
    runner=(timeout --kill-after=30 "$check_timeout")
    if [[ -n "$check_lease" ]]; then
        lease_bin="$(command -v fabric-lease || echo "$fabric/bin/fabric-lease")"
        runner=("$lease_bin" "$check_lease" -- "${runner[@]}")
    fi
    (cd "$wt" && exec setsid "${runner[@]}" "${check_argv[@]}") > "$wt.out" 2>&1 &
    cpid=$!
    wait "$cpid"; check_rc=$?
    out="$(cat "$wt.out")"
    check_tail="$(tail -n 20 <<<"$out")"
    # Only a pass reads as a pass: a timeout, a command that is not there,
    # or a declared verdict line that never came is unavailable.
    # 124/137 timed out, 125 timeout itself failed, 126/127 no such command,
    # 75 the lease stayed held (fabric-lease's EX_TEMPFAIL).
    if (( check_rc == 124 || check_rc == 125 || check_rc == 137 || check_rc == 126 || check_rc == 127 || check_rc == 75 )); then check_state="unavailable"
    elif [[ -n "$check_verdict" ]]; then
        v="$(grep -oE "$check_verdict" <<<"$out" | tail -n 1 | grep -oE 'PASS|FAIL|UNAVAILABLE' | tail -n 1)"
        case "$v" in PASS) check_state="passed" ;; FAIL) check_state="failed" ;; *) check_state="unavailable" ;; esac
    elif (( check_rc == 0 )); then check_state="passed"
    else check_state="failed"; fi
fi
elapsed=$(( SECONDS - start ))

rc=0
[[ "$result" == conflicts ]] && rc=1
[[ "$result" == "could not merge" ]] && rc=2
[[ "$check_state" == failed ]] && rc=1
[[ "$check_state" == unavailable && $rc -eq 0 ]] && rc=2

if (( JSON )); then
    refs_json="$(for i in "${!names[@]}"; do jq -cn --arg b "${names[$i]}" --arg s "${shas[$i]}" '{branch:$b, sha:$s}'; done | jq -s .)"
    jq -n --arg base "$BASE" --arg base_sha "$base_sha" --argjson refs "$refs_json" --arg result "$result" \
          --arg failed "$failed_ref" --argjson conflicted "$(printf '%s\n' "${conflicted[@]}" | jq -R . | jq -s 'map(select(length > 0))')" \
          --arg tree "$tree" --arg merr "$(tail -n 3 <<<"$merge_err")" --arg check "$check_state" --arg check_rc "$check_rc" --arg tail "$check_tail" --argjson secs "$elapsed" \
          '{base:$base, base_sha:$base_sha, refs:$refs, result:$result}
           + (if $result == "combines" then {tree:$tree} else {failed_ref:$failed, conflicted:$conflicted, git:$merr} end)
           + {check:$check} + (if $check_rc != "" then {check_exit:($check_rc|tonumber), check_tail:$tail} else {} end)
           + {seconds:$secs}'
else
    echo "trial-merge onto $BASE (${base_sha:0:8}):"
    for i in "${!names[@]}"; do echo "  ${names[$i]} @ ${shas[$i]:0:8}"; done
    if [[ "$result" == combines ]]; then echo "combines — tree ${tree:0:12}"
    elif [[ "$result" == conflicts ]]; then echo "conflicts — ${failed_ref} did not merge:"; printf '    %s\n' "${conflicted[@]}"
    else echo "could not merge ${failed_ref} (not a conflict):"; tail -n 3 <<<"$merge_err" | sed 's/^/    /'; fi
    case "$check_state" in
        "not asked") ;;
        "not run: did not combine") echo "check: not run — the refs did not combine" ;;
        "none declared") echo "check: none declared for this project (projects/<id>/integration/gh/trial.json); merge only" ;;
        *) echo "check ${check_state} (exit ${check_rc})"; [[ "$check_state" == passed ]] || sed 's/^/    /' <<<"$check_tail" ;;
    esac
fi
exit $rc
