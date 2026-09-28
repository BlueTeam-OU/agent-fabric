#!/usr/bin/env bash
# runtime/github/pr-reply.sh
#
# >>> help
# Reply to ONE review thread and resolve it, in a single call.
#
# The body arrives on STDIN and is never interpolated into a command
# line. That is the point of this script, not a detail: replies quote
# code, and a body pasted into a double-quoted `gh api -f body="..."`
# gets `backticks` command-substituted and `$vars` expanded by the shell
# before gh ever sees it. That has already happened here — a reply
# posted with the name of the guard it was describing silently removed,
# because the shell ran it. Reading stdin into a variable and handing
# that variable to `gh -f` closes the whole class.
#
# It also enforces the two rules that are easy to break by hand:
#
#   * ANOTHER SESSION'S PR IS REFUSED. Ownership is the branch prefix,
#     not the PR author (every session pushes as the same GitHub user).
#     The repo-root CLAUDE.md is explicit: never answer reviews on
#     another session's branch. A wrong reply cannot be unsent, and that
#     session is mid-flight on a fix you cannot see.
#
#     A BRANCH THAT NAMES NO SESSION IS NOT "ANOTHER SESSION'S". The
#     guard used to take the first two segments of anything and compare
#     — so dependabot's `dependabot/pub`, a pre-convention `feat/x`, and
#     `add-claude-github-actions-178…` each read as a rival session, and
#     the refusal told you it was "mid-flight on a fix you cannot see"
#     about a session that does not exist. Nobody could answer those
#     threads through this script, and nobody owned them either: four
#     such PRs held seven unresolved P1/P2 findings for a month. The
#     shape is checked now, and an unowned PR is allowed with a warning
#     — the reply still needs the owning SURFACE's role to have verified
#     the claim, which is what the warning says.
#   * RESOLVING IS A CLAIM. --no-resolve exists for the case where the
#     reply is a question, or the finding is real and not yet fixed.
#     Resolution stopped gating merges on 2026-08-06, so a resolve now
#     signals only "handled" and nothing downstream catches a false one.
#
# Usage:
#   runtime/github/pr-reply.sh <thread-id> [options]   # body on stdin
#
#   runtime/github/pr-reply.sh PRRT_xxx <<'EOF'
#   Fixed in #123 — the guard now anchors the filter.
#   EOF
#
#   runtime/github/pr-reply.sh PRRT_xxx --no-resolve <<'EOF'
#   Real, but the fix needs the contract change first — leaving open.
#   EOF
#
# Options:
#   --no-resolve   post the reply, leave the thread open
#   --resolve      resolve even on a branch that names no session, where
#                  the default is to leave it open (see below)
#   --dry-run      show what would be posted, touch nothing
#   -h, --help     this text
#
# Thread ids come from the queue: `/comments`, or the GraphQL in the
# pr-review-backlog skill. They look like PRRT_kwDOS6OPLs6XAV3d.
#
# A quoted heredoc (<<'EOF') is the recommended way to pass the body:
# unquoted, the SHELL expands it before this script is reached, and no
# amount of care in here can undo that.
#
# Exit codes:
#   0  replied (and resolved, unless --no-resolve)
#   2  invocation problem — bad id, empty body, not your PR, gh failure
# <<< help

set -uo pipefail

THREAD=""
RESOLVE=1
# Tracks whether the caller SAID so, as against the default. Only the
# unowned-branch path below needs the distinction: it flips the default
# to "leave open", and must not silently override an explicit --resolve.
RESOLVE_EXPLICIT=0
DRY_RUN=0

die() { echo "pr-reply: $*" >&2; exit 2; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-resolve) RESOLVE=0; RESOLVE_EXPLICIT=1; shift ;;
        --resolve)    RESOLVE=1; RESOLVE_EXPLICIT=1; shift ;;
        --dry-run)    DRY_RUN=1; shift ;;
        -h|--help)
            sed -n '/^# >>> help$/,/^# <<< help$/p' "$0" \
                | sed '1d;$d' | sed 's/^# \{0,1\}//'
            exit 0 ;;
        -*) die "unknown option '$1' (try --help)" ;;
        *)
            [[ -z "$THREAD" ]] || die "one thread id at a time (got '$THREAD' and '$1')"
            THREAD="$1"; shift ;;
    esac
done

[[ -n "$THREAD" ]] || die "a review-thread id is required (try --help)"

# Fail on the id shape rather than on a confusing API error. Review
# THREAD ids start PRRT_; a review COMMENT id (PRRC_) is the other thing
# in the same output and cannot be replied to this way.
[[ "$THREAD" =~ ^PRRT_[A-Za-z0-9_-]+$ ]] \
    || die "'$THREAD' is not a review-thread id (expected PRRT_…; PRRC_ is a comment, not a thread)"

# git and hostname are as required as gh and jq: the ownership guard below
# derives this clone's identity from both, and a missing git would surface
# as "not inside a git worktree" — sending the operator to look for a clone
# they are already standing in.
for bin in gh jq git hostname; do
    command -v "$bin" >/dev/null 2>&1 || die "$bin is required but not installed."
done

# STDIN, never a command-line argument. See the header.
if [[ -t 0 ]]; then
    die "the reply body is read from stdin — pipe it, or use <<'EOF' … EOF"
fi
# The sentinel preserves trailing newlines. Command substitution strips
# ALL of them, so `BODY="$(cat)"` silently dropped the blank line a
# documented heredoc ends with — and this script's whole promise is that
# the body reaches GitHub byte-for-byte, which is why it takes stdin
# instead of an argument in the first place.
BODY="$(cat; printf x)"
BODY="${BODY%x}"
[[ -n "${BODY//[$' \t\n']/}" ]] || die "the reply body is empty."

# ── who owns this thread's PR ───────────────────────────────────────
THREAD_JSON="$(gh api graphql -f query='
    query($id: ID!) {
      node(id: $id) {
        ... on PullRequestReviewThread {
          isResolved path line
          pullRequest { number state headRefName
                        repository { nameWithOwner } }
          comments(last: 1) { nodes { author { login } } }
        }
      }
    }' -f id="$THREAD" --jq '.data.node' 2>/dev/null)" \
    || die "could not read thread $THREAD (gh not authenticated, or no access)."

[[ -n "$THREAD_JSON" && "$THREAD_JSON" != "null" ]] \
    || die "thread $THREAD does not exist, or this token cannot see it."

# SCOPE THE THREAD TO THIS REPOSITORY, EXPLICITLY.
#
# `node(id:)` is a GLOBAL lookup: a node id resolves wherever it lives,
# and nothing in the query above constrains it to this repo. The message
# below used to read "thread not found in this repository" and fired only
# when the node was absent -- asserting a guarantee the query never
# provided. A thread in ANOTHER repository resolved fine, and the only
# remaining gate was the branch-prefix ownership check further down,
# which passes for any branch named `<host>/<clone>/...` anywhere. That
# is enough to reply to, and RESOLVE, a stranger's review thread.
THREAD_REPO="$(printf '%s' "$THREAD_JSON" | jq -r '.pullRequest.repository.nameWithOwner // ""')"
HERE_REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
[[ -n "$HERE_REPO" ]] \
    || die "cannot determine the current repository (run inside a checkout)."
[[ "$THREAD_REPO" == "$HERE_REPO" ]] \
    || die "thread $THREAD belongs to $THREAD_REPO, not $HERE_REPO."

PR_NUMBER="$(printf '%s' "$THREAD_JSON" | jq -r '.pullRequest.number')"
PR_BRANCH="$(printf '%s' "$THREAD_JSON" | jq -r '.pullRequest.headRefName')"
PR_STATE="$(printf '%s' "$THREAD_JSON" | jq -r '.pullRequest.state')"
IS_RESOLVED="$(printf '%s' "$THREAD_JSON" | jq -r '.isResolved')"
LOCATION="$(printf '%s' "$THREAD_JSON" | jq -r '"\(.path):\(.line // "?")"')"

# The session that owns a branch is its first two segments — the same
# rule pr-sessions.sh marks rows with. Derived here, not passed in, so
# it cannot be talked out of.
#
# FAILS CLOSED. pr-sessions.sh treats an unresolvable identity as "no
# default scope" and shows everything, which is harmless for a listing.
# Here the same shape would have disabled the only protection this
# script offers: run by absolute path from outside a worktree, `git
# rev-parse` fails, ME is empty, and an `[[ -n "$ME" && ... ]]` guard
# skips straight past — posting to any thread handed to it. Not knowing
# whose PR this is has to mean stop, not proceed.
root="$(git rev-parse --show-toplevel 2>/dev/null)" \
    || die "not inside a git worktree, so the session's working-copy identity is unknown — refusing to reply (run it from the working copy that owns the PR)."
# The session is the AGENT — the Linux login, as agent-fabric resolves it —
# on this host. Branches are named <host>/<agent>/<type>/<desc>; older
# branches carry the working-copy name in the second segment, so that is
# accepted as the session too while they last (ME_LEGACY, below).
FABRIC_ROOT="${AGENT_FABRIC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
AGENT="$(python3 "$FABRIC_ROOT/runtime/identity.py" 2>/dev/null || id -un)"
ME="$(hostname -s)/$AGENT"
# A working copy named after its repository (~/projects/<repo>) is
# every login's default clone since the per-login clones were
# renamed, so its name is no session's: taken for one, it made the
# pre-rename clone's branches "mine" in every session (a managed
# project's review). Only a clone with a name of its own carries a
# legacy prefix.
ME_LEGACY=""
repo_name="$(git -C "$root" remote get-url origin 2>/dev/null | sed -E 's#\.git$##; s#.*[/:]##')"
wc_name="$(basename "$root")"
[[ -n "$repo_name" && "${wc_name,,}" == "${repo_name,,}" ]] || ME_LEGACY="$(hostname -s)/$wc_name"
# The ROLE this session holds: some PRs are a role's, not a session's
# (below, bot_owner_role), and only the session holding that role may
# answer on them. No binding, no role.
ROLE="$(python3 "$FABRIC_ROOT/runtime/identity.py" --role 2>/dev/null || true)"
OWNER="$(printf '%s' "$PR_BRANCH" | cut -d/ -f1,2)"

# Does the branch name a SESSION at all? Same structural test
# pr-sessions.sh applies — <host>/<clone>/<type>/<desc>, a deny-list of
# automation vendors, and no vocabulary imposed on <type> — because the
# two scripts must agree about who owns what. Duplicated rather than
# shared: these scripts are deliberately standalone, and the rule is
# short enough that a copy is cheaper than a library. If it changes in
# one, change it in the other; test_pr-reply.sh and test_pr-sessions.sh
# both pin it.
branch_names_a_session() {
    local b="$1" IFS=/
    local -a p
    read -r -a p <<< "$b"
    [[ "${#p[@]}" -ge 4 ]]                || return 1
    # Parity with pr-sessions.sh, and NOT separately testable: git's own
    # ref-format rules reject an empty path component, so `//feat/x` and
    # `host//feat/x` cannot be branch names and no fixture can reach this
    # line. Kept so the two predicates read alike rather than diverging
    # on a case one of them silently drops.
    [[ -n "${p[0]}" && -n "${p[1]}" ]]    || return 1
    case "${p[0]}" in
        dependabot|renovate|github-actions|weblate|imgbot|\
        allcontributors|pre-commit-ci|snyk-bot) return 1 ;;
    esac
    # NO TEST ON <type>, deliberately. CLAUDE.md imposes no vocabulary on
    # it, so a shape test here is a permission decision resting on an
    # open-ended set. In a LISTING a wrong "not a session" is fail-safe —
    # the row is hidden and the NOTE counts it. HERE it inverts: a wrong
    # "not a session" means POST AND RESOLVE on somebody else's PR, and a
    # reply cannot be unsent. `Fix/`, `chore(gh)/`, `WIP/`, `2fix/` are
    # all real parallel-session branches that a lowercase shape test
    # calls unowned. It also bought nothing: every branch this change
    # exists to answer is already unowned by segment count or by the
    # vendor deny-list above.
    return 0
}

# BOT BRANCHES HAVE AN OWNER TOO -- a ROLE. Same map as pr-sessions.sh
# (a Dependabot pull request is devex-tooling's: architect-cto decision,
# 2026-09-14), duplicated for the same reason the predicate above is.
# Prints the owning role for a bot prefix, or nothing.
bot_owner_role() {
    case "${1%%/*}" in
        dependabot) printf '%s' "devex-tooling" ;;
        *) ;;
    esac
}

# OLDER BRANCHES. Before the login identity model, branch prefixes carried
# the working-copy directory name; such a branch named for THIS working
# copy is this agent's own and is treated so. Any other older prefix is
# some session's, or nobody's, and reads as that session's: refused, like
# any branch that is not ours. No record of retired clones is kept.

# The unowned path's one enforced rule: resolving is a claim, and a PR no
# session owns is the path with the least standing to make it, so the
# default flips to leave-open and --resolve is the opt-in. Shared by the
# no-session case below.
leave_open_unless_explicit() {
    if [[ "$RESOLVE" -eq 1 && "$RESOLVE_EXPLICIT" -eq 0 ]]; then
        RESOLVE=0
        echo "  The finding may still be another SURFACE's (backend, flutter, web)," >&2
        echo "  so the thread is left OPEN. Pass --resolve once it is verified." >&2
    fi
}

BOT_ROLE="$(bot_owner_role "$PR_BRANCH")"
if [[ -n "$BOT_ROLE" && "$ROLE" == "$BOT_ROLE" ]]; then
    # A bot PR, and this session holds the role that owns bot PRs: it is
    # ours to answer, findings and resolves alike, as a session's own
    # branch would be.
    echo "pr-reply: #$PR_NUMBER is on '$PR_BRANCH' — a bot branch, owned by the $BOT_ROLE role, which this session holds." >&2
elif [[ -n "$BOT_ROLE" ]]; then
    # A bot PR that a ROLE owns, and this session does not hold it. The
    # same refusal as for another session's branch: the owner is
    # mid-flight on it, and a reply cannot be unsent.
    echo "pr-reply: #$PR_NUMBER is on '$PR_BRANCH', which the $BOT_ROLE role owns; this session holds '${ROLE:-no role}'." >&2
    echo "  Not replying. Hand the finding to that role (GZCoord), or raise it in the PR." >&2
    exit 2
elif ! branch_names_a_session "$PR_BRANCH"; then
    # Unowned, NOT someone else's. Refusing here is what kept these
    # threads unanswerable; claiming a rival session owns them would be
    # a statement the branch cannot support.
    echo "pr-reply: #$PR_NUMBER is on '$PR_BRANCH', which names no session." >&2
    echo "  No session owns it, so there is nobody to defer to — replying." >&2
    # THE ADVICE HAS TO BE ENFORCED, NOT PRINTED. This block used to say
    # "resolve only what you actually verified" and then resolve in the
    # same run, so the operator read the precondition after it had been
    # violated. Resolving is a CLAIM (see the header), and this is the
    # path with the least standing to make it: the script has just said
    # the finding may belong to a surface whose role has verified
    # nothing. So the default inverts here and --resolve is the opt-in.
    leave_open_unless_explicit
elif [[ "$OWNER" == "$ME_LEGACY" && "$OWNER" != "$ME" ]]; then
    # The branch carries this WORKING COPY's name where newer branches
    # carry the agent's login. It is this agent's own branch under the
    # older convention; treat it as owned, and say so once.
    echo "pr-reply: #$PR_NUMBER is on '$PR_BRANCH', named for this working copy; this agent ($ME) owns it." >&2
elif [[ "$OWNER" != "$ME" ]]; then
    echo "pr-reply: #$PR_NUMBER belongs to '$OWNER', and this session is '$ME'." >&2
    echo "  Not replying. That session is mid-flight on a fix you cannot see," >&2
    echo "  and a review reply cannot be unsent. Raise it in the PR instead." >&2
    exit 2
fi

if [[ "$IS_RESOLVED" == "true" ]]; then
    echo "pr-reply: thread is already resolved — replying anyway, leaving it resolved." >&2
    RESOLVE=0
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "would reply to #$PR_NUMBER ($PR_STATE) $LOCATION — thread $THREAD"
    echo "would resolve: $([[ "$RESOLVE" -eq 1 ]] && echo yes || echo no)"
    echo "--- body ---"
    printf '%s\n' "$BODY"
    exit 0
fi

# ── reply ───────────────────────────────────────────────────────────
URL="$(gh api graphql -f query='
    mutation($id: ID!, $body: String!) {
      addPullRequestReviewThreadReply(
        input: {pullRequestReviewThreadId: $id, body: $body}) {
        comment { url }
      }
    }' -f id="$THREAD" -f body="$BODY" \
    --jq '.data.addPullRequestReviewThreadReply.comment.url' 2>/dev/null)" \
    || die "the reply was rejected (thread $THREAD on #$PR_NUMBER)."

[[ -n "$URL" ]] || die "the reply returned no URL — assume it did not post."

echo "replied: $URL"

# ── resolve ─────────────────────────────────────────────────────────
#
# Only after the reply landed. A resolved thread with no reply is the
# worst outcome available: it reads as answered and shows nothing.
if [[ "$RESOLVE" -eq 1 ]]; then
    RESOLVED="$(gh api graphql -f query='
        mutation($id: ID!) {
          resolveReviewThread(input: {threadId: $id}) {
            thread { isResolved }
          }
        }' -f id="$THREAD" \
        --jq '.data.resolveReviewThread.thread.isResolved' 2>/dev/null)" \
        || die "replied, but the resolve failed — thread $THREAD is still open."
    [[ "$RESOLVED" == "true" ]] \
        || die "replied, but the thread did not resolve (got '$RESOLVED')."
    echo "resolved: #$PR_NUMBER $LOCATION"
else
    echo "left open: #$PR_NUMBER $LOCATION"
fi
