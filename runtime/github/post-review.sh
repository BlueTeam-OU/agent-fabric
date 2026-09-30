#!/usr/bin/env bash
# runtime/github/post-review.sh (lifted from the first managed project's tools/gh/ on 2026-09-19 — the commit names it; general to every managed project, whose own tools/gh/ copy is a forwarder through projects/<id>/integration/gh/)
#
# >>> help
# Post THE review of a PR — the review class's blind review — as a
# review object, marked so the tooling counts it as coverage of the head.
#
# WHY THIS EXISTS. Every session pushes as the SAME GitHub account, so a
# review the review class wrote is indistinguishable from the author's
# own thread reply by account alone, and pr-review-status.sh used to
# bucket both as "self reviews … not coverage". Prose attribution drifts
# — three sessions wrote three different sentences — and a coverage
# claim guessed from prose is worse than none. So every review this
# script posts is a REVIEW OBJECT (never an issue comment, which is not
# a review) and carries REVIEW_MARKER (below) as its first line, the
# exact string pr-review-status.sh tests for.
#
# The review class is the review. There is no automated reviewer it
# stands in for: the fabric dispatches a blind reviewer for every PR
# (runtime/claude-code/agents/code-review.md, briefed by bin/fabric-review),
# and this is how that review reaches the PR and the gate.
#
# Usage:
#   post-review.sh <pr> [options]   # body on stdin
#
#   post-review.sh 552 <<'EOF'
#   Found a P1 in the ownership guard: a four-segment branch typed
#   `Fix/` was classified unowned, so pr-reply.sh would post to it.
#   EOF
#
# Options:
#   --model <name>   record which model produced the review (default: unset)
#   --dry-run        show what would be posted, send nothing
#   -h, --help
#
# The body arrives on STDIN and is never interpolated into a command
# line — the same rule, and the same reason, as pr-reply.sh: a body
# quoting `backticks` or $vars passed through `-f body="…"` is expanded
# by the shell before gh sees it, and that has already posted a mangled
# comment in this repo.
#
# Exit codes:
#   0  posted
#   2  invocation problem, or the PR belongs to another session
# <<< help

set -uo pipefail

die() { echo "post-review: $*" >&2; exit 2; }

# THE CONTRACT, in one string. pr-review-status.sh greps for exactly
# this; test_post-review.sh and test_pr-review-status.sh both
# pin it, so changing it here without changing the reader is caught.
# Versioned because a later field addition must not silently reclassify
# older reviews.
REVIEW_MARKER='<!-- agent-fabric-review v1 -->'

PR=""
MODEL=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)   [[ $# -ge 2 ]] || die "--model needs a value"; MODEL="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help)
            sed -n '/^# >>> help$/,/^# <<< help$/p' "$0" \
                | sed '1d;$d' | sed 's/^# \{0,1\}//'
            exit 0 ;;
        -*) die "unknown option '$1' (try --help)" ;;
        *)  [[ -z "$PR" ]] || die "only one PR number, got '$PR' and '$1'"
            PR="$1"; shift ;;
    esac
done

[[ -n "$PR" ]] || die "a PR number is required (try --help)"
[[ "$PR" =~ ^[1-9][0-9]*$ ]] || die "'$PR' is not a PR number"

for bin in gh jq git hostname; do
    command -v "$bin" >/dev/null 2>&1 || die "$bin is required but not installed."
done

# STDIN, never an argument. See the header.
[[ -t 0 ]] && die "the review body is read from stdin — pipe it, or use <<'EOF' … EOF"
BODY="$(cat; printf x)"
BODY="${BODY%x}"
[[ -n "${BODY//[$' \t\n']/}" ]] || die "the review body is empty."

REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" \
    || die "could not resolve the repository (gh not authenticated?)."

PR_JSON="$(gh pr view "$PR" --json number,state,headRefName,headRefOid 2>/dev/null)" \
    || die "could not read PR #$PR."
PR_BRANCH="$(jq -r '.headRefName' <<<"$PR_JSON")"
PR_HEAD="$(jq -r '.headRefOid' <<<"$PR_JSON")"
PR_STATE="$(jq -r '.state' <<<"$PR_JSON")"

# FAILS CLOSED, and this is the line that makes the comment below true.
# `jq -r '.headRefName' <<<""` exits 0 printing nothing, and a payload
# missing the field prints the literal "null" — either then splits into
# fewer than four segments, so branch_names_a_session returns "names no
# session" and the guard takes the POSTING path. A `gh` that exits 0 with
# truncated output, or any future change to the --json field set, would
# have turned the ownership guard off entirely rather than stopping.
# pr-reply.sh has this check; this copy dropped it.
[[ -n "$PR_BRANCH" && "$PR_BRANCH" != "null" ]] \
    || die "could not read the head branch of PR #$PR — refusing, because ownership is unknown."
[[ -n "$PR_HEAD" && "$PR_HEAD" != "null" ]] \
    || die "could not read the head commit of PR #$PR — refusing."

# ── lane guard ──────────────────────────────────────────────────────
#
# Same rule as pr-reply.sh, and the same reason: a review cannot be
# unsent, and another session is mid-flight on work you cannot see.
# FAILS CLOSED — not knowing whose PR this is has to mean stop.
root="$(git rev-parse --show-toplevel 2>/dev/null)" \
    || die "not inside a git worktree, so the session's working-copy identity is unknown — refusing."
# The session is the AGENT — the Linux login, as agent-fabric resolves it —
# on this host; branches are named <host>/<agent>/<type>/<desc>. Older
# branches carry the working-copy name in the second segment, so that is
# accepted as this session too while they last (as pr-reply.sh does).
FABRIC_ROOT="${AGENT_FABRIC_ROOT:-$root/../agent-fabric}"
AGENT="$(python3 "$FABRIC_ROOT/runtime/identity.py" 2>/dev/null || id -un)"
ME="$(hostname -s)/$AGENT"
ME_LEGACY="$(hostname -s)/$(basename "$root")"
OWNER="$(cut -d/ -f1,2 <<<"$PR_BRANCH")"

# Kept identical to pr-reply.sh's predicate, including the deliberate
# absence of any test on <type>: a shape test there is a permission
# decision resting on an open-ended set, and a wrong "names no session"
# means writing to somebody else's PR.
branch_names_a_session() {
    local b="$1" IFS=/
    local -a p
    read -r -a p <<< "$b"
    [[ "${#p[@]}" -ge 4 ]]             || return 1
    [[ -n "${p[0]}" && -n "${p[1]}" ]] || return 1
    case "${p[0]}" in
        dependabot|renovate|github-actions|weblate|imgbot|\
        allcontributors|pre-commit-ci|snyk-bot) return 1 ;;
    esac
    return 0
}

if ! branch_names_a_session "$PR_BRANCH"; then
    echo "post-review: #$PR is on '$PR_BRANCH', which names no session." >&2
    echo "  No session owns it, so there is nobody to defer to — posting." >&2
elif [[ "$OWNER" != "$ME" && "$OWNER" != "$ME_LEGACY" ]]; then
    # The one exception: a locale's translations are committed by that
    # locale's holder and merged by fabric-coordinator (agent-fabric's
    # CLAUDE.md, the locale carve-out), so the merger must post the review
    # its gate counts. Only a PR that touches nothing but
    # identities/roles/<role>/locale/<suffix>/, and only from a session
    # bound to fabric-coordinator. FAILS CLOSED: an unreadable role or file
    # list, or gh's 100-file cap reached, is another session's PR.
    ROLE="$(python3 "$FABRIC_ROOT/runtime/identity.py" --role 2>/dev/null || true)"
    FILES_JSON="$(gh pr view "$PR" --json files 2>/dev/null || true)"
    NFILES="$(jq -r '(.files // null) | if type == "array" then length else -1 end' <<<"$FILES_JSON" 2>/dev/null || echo -1)"
    OUTSIDE="$(jq -r '.files[]?.path // empty' <<<"$FILES_JSON" 2>/dev/null \
        | grep -Evc '^identities/roles/[^/]+/locale/[^/]+/[^/]+$' || true)"
    if [[ "$ROLE" == "fabric-coordinator" && "$NFILES" -ge 1 && "$NFILES" -lt 100 && "$OUTSIDE" == 0 ]]; then
        echo "post-review: #$PR belongs to '$OWNER' and touches only locale translations;" >&2
        echo "  posting as the locale carve-out's merger (fabric-coordinator)." >&2
        CARVE_OUT=1
    else
        echo "post-review: #$PR belongs to '$OWNER', and this session is '$ME'." >&2
        echo "  Not posting. That session is mid-flight on work you cannot see," >&2
        echo "  and a review cannot be unsent. Raise it in the PR instead." >&2
        exit 2
    fi
fi

# ── assemble ────────────────────────────────────────────────────────
#
# The marker goes FIRST so it survives any truncation a reader applies,
# and so `head -1` identifies the review without fetching the whole body.
header="$REVIEW_MARKER"
[[ -n "$MODEL" ]] && header+=$'\n'"<!-- model: $MODEL -->"
[[ "${CARVE_OUT:-0}" -eq 1 ]] && header+=$'\n'"<!-- posted by the locale carve-out's merger -->"

FULL_BODY="$header
**Blind review** — the review class, dispatched against this head with a
brief of facts and none of the author's session context. Its findings
are judged before they are answered; the judgement follows in the PR.

$BODY"

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "would post a review to #$PR ($PR_STATE) at $PR_HEAD"
    echo "--- body ---"
    printf '%s\n' "$FULL_BODY"
    exit 0
fi

# --input with a real file, never -f body="…". A review body quotes code
# by definition, and the shell would expand it first.
payload="$(mktemp)" || die "could not create a temporary file."
trap 'rm -f "$payload"' EXIT INT TERM
jq -n --arg b "$FULL_BODY" --arg c "$PR_HEAD" \
   '{body: $b, event: "COMMENT", commit_id: $c}' > "$payload" \
    || die "could not build the request payload."

# GitHub's own reason, not a bare "rejected": the first transient failure
# on #69 said nothing, and a hand-made retry to learn why posted an
# unmarked review. No automatic retry: a timeout may have posted it, and a
# second post is a duplicate review on the PR.
errf="$(mktemp)" || die "could not create a temporary file."
trap 'rm -f "$payload" "$errf"' EXIT INT TERM
url="$(gh api "repos/$REPO/pulls/$PR/reviews" --input "$payload" \
        --jq '.html_url' 2>"$errf")" \
    || die "the review was rejected by GitHub (PR #$PR): $(grep -v '^\s*$' "$errf" | tail -1). Look at the PR before re-running — a timeout may have posted it; never post it by hand, unmarked."

[[ -n "$url" ]] || die "GitHub accepted the request but returned no review URL — treat as NOT posted."
echo "posted review: $url"
echo "  marked so pr-review-status.sh counts it as the review of this head."
