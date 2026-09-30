#!/usr/bin/env bash
# tools/gh/test_pr-reply.sh
#
# Behavioural tests for pr-reply.sh.
#
# Three things this script promises, each of which is unrecoverable if
# it is wrong — a posted reply cannot be unsent:
#
#   1. the body reaches GitHub byte-for-byte, with no shell expansion
#      (the defect the script exists to remove: a reply lost the name of
#      the guard it described because a backtick was command-substituted
#      on its way through a double-quoted argument)
#   2. another session's PR is refused
#   3. a thread is never resolved unless the reply actually landed
#
# The mock `gh` records the exact argv it was handed, so assertion 1 is
# about what would have been transmitted rather than about what the
# script believed it sent.
#
# Exit codes:
#   0  all assertions passed
#   1  one or more assertions failed

set -uo pipefail

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/pr-reply.sh"

[[ -f "$UNDER_TEST" ]] || { echo "test: $UNDER_TEST not found" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "test: jq required" >&2; exit 1; }

failures=0
SANDBOX=""
NOGIT=""
STRIP=""
cleanup() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
    [[ -n "$NOGIT"   && -d "$NOGIT"   ]] && rm -rf "$NOGIT"
    [[ -n "$STRIP"   && -d "$STRIP"   ]] && rm -rf "$STRIP"
    [[ -n "${GUARD_MARKER:-}" ]] && rm -f "$GUARD_MARKER"
    return 0
}
trap cleanup EXIT

CLONE_NAME="legacy-testclone"
ME="$(hostname -s)/$CLONE_NAME"
OTHER="$(hostname -s)/legacy-otherclone"

pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1" >&2; printf '%s\n' "${2:-}" | sed 's/^/      /' >&2
         failures=$((failures + 1)); }

assert_rc() {
    local label="$1" want="$2"
    if [[ "$RUN_RC" -eq "$want" ]]; then pass "$label"
    else fail "$label — expected exit $want, got $RUN_RC" "$RUN_OUT"; fi
}
assert_contains() {
    if [[ "$RUN_OUT" == *"$2"* ]]; then pass "$1"
    else fail "$1 — output lacked '$2'" "$RUN_OUT"; fi
}
assert_not_contains() {
    if [[ "$RUN_OUT" != *"$2"* ]]; then pass "$1"
    else fail "$1 — output unexpectedly had '$2'" "$RUN_OUT"; fi
}

# A MISTYPED HELPER MUST FAIL THE SUITE, not vanish into stderr.
#
# An assertion calling a function nobody defined prints "command not
# found", never touches the failure counter, and leaves the suite
# reporting success with that case vacuous — a guard claiming coverage
# it does not have, in a file whose whole job is stopping exactly that.
# It has happened twice here: test_pr-review-status.sh's merged-pr case
# called `ok`/`bad` and ran for weeks doing nothing, and its verdict
# cases were written with `assert_not_contains` where this file's
# helpers are named otherwise.
#
# Every suite needs this, not just the one that was bitten: the helpers
# are NOT named alike across these files — two spell it `assert_lacks`,
# two `assert_not_contains` — so anyone moving between them types the
# wrong name eventually.
#
# THE MARKER FILE IS THE MECHANISM, and a counter is not. Bash runs
# `command_not_found_handle` in a SUBSHELL, so `failures=$((failures+1))`
# inside it is discarded when that subshell exits: the handler prints its
# complaint and the suite still reports "all assertions passed" and exits
# 0. The first version of this guard did exactly that — a vacuous guard
# against vacuous guards. A file written in the subshell survives it.
#
# The script under test runs as a separate `bash` process, so none of
# this reaches it or masks a genuine missing-command path there.
GUARD_MARKER="$(mktemp)"
command_not_found_handle() {
    printf '%s\n' "$1" >> "$GUARD_MARKER"
    echo "  ✗ self-test bug: called '$1', which is not defined here" >&2
    echo "      the assertion helpers here are assert_rc / assert_contains / assert_not_contains" >&2
    return 127
}

setup_sandbox() {
    SANDBOX="$(mktemp -d)"
    mkdir -p "$SANDBOX/$CLONE_NAME" "$SANDBOX/bin" "$SANDBOX/state"
    git -C "$SANDBOX/$CLONE_NAME" init -q 2>/dev/null

    cat > "$SANDBOX/bin/gh" <<'MOCK'
#!/usr/bin/env bash
# Mock gh: records each graphql call's operation and body, and answers
# from the fixtures the case set up.
set -uo pipefail

# `gh repo view` — what the script asks to learn which repo it is in.
# Answered before the graphql parsing below, because it takes no -f flags.
if [[ "${1:-}" == "repo" && "${2:-}" == "view" ]]; then
  echo "REPOVIEW" >> "$GH_MOCK_STATE/calls"
  [[ -n "${GH_MOCK_REPO_FAIL:-}" ]] && exit 1
  echo "${GH_MOCK_HERE_REPO:-gzapi-org/gzapp}"
  exit 0
fi

query=""; id=""; body=""; json=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -f) case "$2" in
          query=*) query="${2#query=}" ;;
          id=*)    id="${2#id=}" ;;
          body=*)  body="${2#body=}" ;;
        esac
        shift 2 ;;
    # The same call with its query and variables as JSON on stdin (tools/
    # fabric/gh.py, ADR-040 §5 rule 6: a body never in argv); answered in
    # GraphQL's own shape, where the -f form was answered through --jq.
    --input) json=1; shift 2 ;;
    *) shift ;;
  esac
done
if [[ "$json" == 1 ]]; then
  req="$(cat)"
  query="$(jq -r '.query' <<<"$req")"
  id="$(jq -r '.variables.id // ""' <<<"$req")"
  body="$(jq -r '.variables.body // empty' <<<"$req"; printf x)"; body="${body%x}"; body="${body%$'\n'}"
fi
wrap() {  # wrap <jq path> : put stdin at that path of a {"data": …} answer, as GitHub does
  if [[ "$json" == 1 ]]; then jq -c --slurpfile v /dev/stdin -n "{data: {}} | $1 = \$v[0]"; else cat; fi
}

if [[ "$query" == *"PullRequestReviewThread"* && "$query" != *mutation* ]]; then
  echo "READ $id" >> "$GH_MOCK_STATE/calls"
  [[ -n "${GH_MOCK_READ_FAIL:-}" ]] && exit 1
  wrap '.data.node' < "$GH_MOCK_STATE/thread.json"
  exit 0
fi

if [[ "$query" == *addPullRequestReviewThreadReply* ]]; then
  echo "REPLY $id" >> "$GH_MOCK_STATE/calls"
  printf '%s' "$body" > "$GH_MOCK_STATE/body.txt"
  [[ -n "${GH_MOCK_REPLY_FAIL:-}" ]] && exit 1
  [[ -n "${GH_MOCK_REPLY_EMPTY:-}" ]] && { if [[ "$json" == 1 ]]; then echo '""' | wrap '.data.addPullRequestReviewThreadReply.comment.url'; else echo ""; fi; exit 0; }
  if [[ "$json" == 1 ]]; then echo '"https://github.com/o/r/pull/1#discussion_r1"' | wrap '.data.addPullRequestReviewThreadReply.comment.url'
  else echo "https://github.com/o/r/pull/1#discussion_r1"; fi
  exit 0
fi

if [[ "$query" == *resolveReviewThread* ]]; then
  echo "RESOLVE $id" >> "$GH_MOCK_STATE/calls"
  [[ -n "${GH_MOCK_RESOLVE_FAIL:-}" ]] && exit 1
  if [[ "$json" == 1 ]]; then echo 'true' | wrap '.data.resolveReviewThread.thread.isResolved'; else echo "true"; fi
  exit 0
fi

echo "mock gh: unhandled query" >&2; exit 1
MOCK
    chmod +x "$SANDBOX/bin/gh"
}

# Writes the thread fixture. $1 = branch, $2 = isResolved.
# Writes the thread fixture. $1 = branch, $2 = isResolved, $3 = the repo
# the thread belongs to (defaults to the one the mock says we are in).
thread_fixture() {
    jq -n --arg branch "$1" --argjson resolved "$2" \
          --arg repo "${3:-gzapi-org/gzapp}" '{
      isResolved: $resolved, path: "lib/x.dart", line: 12,
      pullRequest: {number: 77, state: "MERGED", headRefName: $branch,
                    repository: {nameWithOwner: $repo}},
      comments: {nodes: [{author: {login: "some-reviewer"}}]}
    }' > "$SANDBOX/state/thread.json"
    : > "$SANDBOX/state/calls"
    rm -f "$SANDBOX/state/body.txt"
}

# Runs the script with the given stdin body and arguments.
# THE ROLE IS PART OF EVERY FIXTURE. Bot branches are owned by a role, so
# whoever runs this suite must not decide a case through their own
# binding: every run reads its binding from a private state dir — empty
# (no role) unless a case plants one with `with_role`, for this login, in
# the shape identity.py reads.
ROLE_STATE_DIR=""
with_role() {  # <role> | -   (- = no binding)
    local role="$1" login; login="$(id -un)"
    ROLE_STATE_DIR="$SANDBOX/state-role"; rm -rf "$ROLE_STATE_DIR"; mkdir -p "$ROLE_STATE_DIR/agents/$login"
    [[ "$role" == "-" ]] || jq -n --arg a "$login" --arg r "$role" '{agent:$a, role:$r}' > "$ROLE_STATE_DIR/agents/$login/binding.json"
}
invoke() {
    local body="$1"; shift
    [[ -n "$ROLE_STATE_DIR" ]] || with_role -
    RUN_OUT="$(cd "$SANDBOX/$CLONE_NAME" && printf '%s' "$body" | \
        env -u AGENT_FABRIC_LAUNCH_ROLE PATH="$SANDBOX/bin:$PATH" GH_MOCK_STATE="$SANDBOX/state" \
        AGENT_FABRIC_STATE_DIR="$ROLE_STATE_DIR" \
        "${MOCK_ENV[@]}" bash "$UNDER_TEST" "$@" 2>&1)"
    RUN_RC=$?
}

MOCK_ENV=(env)

calls() { cat "$SANDBOX/state/calls" 2>/dev/null; }

setup_sandbox
THREAD_ID="PRRT_kwDOtest123"

echo "pr-reply: the happy path"
thread_fixture "$ME/feat/thing" false
invoke "Fixed in #123." "$THREAD_ID"
assert_rc       "exits 0" 0
assert_contains "reports the reply URL" "discussion_r1"
assert_contains "reports the resolve"   "resolved: #77"
# REPOVIEW sits between the read and the reply: the repository check runs
# on the thread it just read, and must happen BEFORE anything is written.
if [[ "$(calls)" == "READ $THREAD_ID
REPOVIEW
REPLY $THREAD_ID
RESOLVE $THREAD_ID" ]]; then
    pass "read, check the repo, then reply, then resolve — in that order"
else
    fail "call order wrong" "$(calls)"
fi

echo "pr-reply: a trailing blank line survives to GitHub"
# `BODY="$(cat)"` strips ALL trailing newlines, so the blank line a
# documented heredoc ends with was silently dropped — while this script
# exists precisely to deliver the body byte-for-byte, which is why it reads
# stdin instead of taking an argument.
#
# Compared with cmp, never `$( )`: reading the capture back through command
# substitution would strip the exact bytes under test, which is how the
# suite stayed green over this. The existing helper pipes with
# `printf '%s'`, so it never had a trailing newline to lose either.
printf 'line one\n\n' > "$SANDBOX/state/expected.txt"
thread_fixture "$ME/feat/thing" false
RUN_OUT="$(cd "$SANDBOX/$CLONE_NAME" && \
    env PATH="$SANDBOX/bin:$PATH" GH_MOCK_STATE="$SANDBOX/state" \
    "${MOCK_ENV[@]}" bash "$UNDER_TEST" "$THREAD_ID" \
    < "$SANDBOX/state/expected.txt" 2>&1)"
RUN_RC=$?
assert_rc "exits 0" 0
if cmp -s "$SANDBOX/state/body.txt" "$SANDBOX/state/expected.txt"; then
    pass "the trailing blank line reached GitHub intact"
else
    fail "trailing bytes were lost in transit" \
        "sent:$(od -c "$SANDBOX/state/body.txt" 2>/dev/null | tail -2)
want:$(od -c "$SANDBOX/state/expected.txt" | tail -2)"
fi

echo "pr-reply: the body is transmitted verbatim"
# The defect this script exists to remove. Every one of these is
# something the shell would have eaten from a double-quoted argument.
BODY='Fixed: the `need_operand` guard and $LIMIT — see $(date) and "quotes" \back.'
thread_fixture "$ME/feat/thing" false
invoke "$BODY" "$THREAD_ID"
assert_rc "exits 0" 0
sent="$(cat "$SANDBOX/state/body.txt" 2>/dev/null || echo MISSING)"
if [[ "$sent" == "$BODY" ]]; then
    pass "backticks, \$vars, \$( ), quotes and backslashes survive intact"
else
    fail "the body was mangled in transit" "sent: $sent
want: $BODY"
fi

echo "pr-reply: --no-resolve replies without claiming the finding is handled"
thread_fixture "$ME/feat/thing" false
invoke "Real, but the contract has to change first." "$THREAD_ID" --no-resolve
assert_rc           "exits 0" 0
assert_contains     "says it left the thread open" "left open"
assert_not_contains "did not resolve"              "resolved: #77"
if [[ "$(calls)" != *RESOLVE* ]]; then
    pass "no resolve mutation was sent"
else
    fail "resolved despite --no-resolve" "$(calls)"
fi

echo "pr-reply: another session's PR is refused"
thread_fixture "$OTHER/fix/theirs" false
invoke "I would like to answer this." "$THREAD_ID"
assert_rc       "exits 2" 2
assert_contains "names the owning session" "$OTHER"
assert_contains "explains why not"         "cannot be unsent"
if [[ "$(calls)" != *REPLY* ]]; then
    pass "nothing was posted"
else
    fail "posted to another session's PR" "$(calls)"
fi

echo "pr-reply: a branch naming no session is answered, not refused as a rival's"
# The guard took the first two segments of ANY branch and compared, so
# `dependabot/pub`, `agent/global-event-identity` and a slashless
# `add-claude-github-actions-178...` each read as another session — and
# the refusal claimed that session was "mid-flight on a fix you cannot
# see" about something that does not exist. Nobody owned those PRs and
# nobody could answer them: four held seven unresolved findings for a
# month.
for branch in "renovate/pub/apps/driver_flutter/flutter-minor-patch-7a91" \
              "agent/global-event-identity" \
              "add-claude-github-actions-1785994932117" \
              "feat/brand-logos"; do
    thread_fixture "$branch" false
    invoke "Obsolete — the file was deleted before this landed." "$THREAD_ID"
    if [[ "$RUN_RC" -eq 0 && "$(calls)" == *REPLY* ]]; then
        pass "answers '$branch'"
    else
        fail "refused an unowned branch: '$branch'" "rc=$RUN_RC $(calls)"
    fi
done

echo "pr-reply: an older branch named for this working copy is this agent's own"
# Before the login model, prefixes carried the working-copy directory name.
HOST="$(hostname -s)"
thread_fixture "$HOST/$CLONE_NAME/fix/mine-under-the-old-name" false
invoke "Verified against main; obsolete." "$THREAD_ID"
assert_rc       "exits 0" 0
assert_contains "says it is this agent's under the older convention" "named for this working copy"
[[ "$(calls)" == *REPLY* ]] && pass "replied on the legacy-named branch" || fail "did not reply on the legacy-named branch" "$(calls)"

echo "pr-reply: a clone named after its repository names no session"
# ~/projects/<repo> is every login's default clone: its name taken for a
# session made an older branch under it "mine" in every session.
git -C "$SANDBOX/$CLONE_NAME" remote add origin "git@example.com:org/$CLONE_NAME.git"
thread_fixture "$HOST/$CLONE_NAME/fix/mine-under-the-old-name" false
invoke "Verified against main; obsolete." "$THREAD_ID"
assert_rc "refused: the repository's own name is no session's" 2
[[ "$(calls)" != *REPLY* ]] && pass "nothing posted on the old branch" || fail "posted on a branch named for the repository" "$(calls)"
git -C "$SANDBOX/$CLONE_NAME" remote remove origin

echo "pr-reply: an older branch named for another working copy is another session's"
thread_fixture "$HOST/legacy-old/fix/theirs" false
invoke "Verified against main; obsolete." "$THREAD_ID"
assert_rc "refused: no record of retired clones exists, so it is someone's" 2
[[ "$(calls)" != *REPLY* ]] && pass "nothing posted" || fail "posted on another session's legacy branch" "$(calls)"

echo "pr-reply: an unowned PR still warns before it replies"
# Allowed is not the same as unremarkable — the finding may belong to a
# surface whose role has verified nothing.
thread_fixture "agent/global-event-identity" false
invoke "Verified fixed." "$THREAD_ID"
assert_rc       "exits 0" 0
assert_contains "says the branch names no session" "names no session"
assert_contains "warns about the owning surface"   "another SURFACE's"
assert_contains "  and bounds what may be resolved" "left OPEN"
assert_not_contains "does not invent a rival session" "mid-flight"

echo "pr-reply: a bot branch is never a session called after the bot"
# `renovate/pub` has the right SHAPE for a session prefix, so only the
# vendor deny-list separates it from a real one. Without that this case
# would refuse, naming "renovate/pub" as the session to defer to.
thread_fixture "renovate/pub/apps/driver_flutter/flutter-minor-patch-7a91" false
invoke "Answered." "$THREAD_ID"
assert_rc           "exits 0" 0
assert_not_contains "never names the bot as a session" "belongs to 'renovate"

echo "pr-reply: a Dependabot PR is the devex-tooling role's — that role answers, others do not"
# Bot branches name no session, but a Dependabot PR has an OWNER: the
# devex-tooling role (architect-cto, 2026-09-14). The session holding it
# answers and may resolve as on its own branch; any other session is
# refused as on another session's branch; with no role bound the PR is
# still somebody's, so refused too.
thread_fixture "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2" false
with_role devex-tooling
MOCK_ENV=(env AGENT_FABRIC_LAUNCH_ROLE=devex-tooling)   # launched with the role, as well as bound
invoke "Superseded by #694; rebased there." "$THREAD_ID"
MOCK_ENV=(env)
assert_rc       "devex-tooling: exits 0" 0
assert_contains "devex-tooling: says the role owns it" "owned by the devex-tooling role"
[[ "$(calls)" == *REPLY* ]] && pass "devex-tooling: replied" || fail "devex-tooling: did not reply" "$(calls)"
[[ "$(calls)" == *RESOLVE* ]] && pass "devex-tooling: resolved by default, as on its own branch" || fail "devex-tooling: did not resolve" "$(calls)"
thread_fixture "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2" false
with_role backend-dev
invoke "Let me answer this one." "$THREAD_ID"
assert_rc       "backend-dev: refused" 2
assert_contains "backend-dev: names the owning role" "devex-tooling role owns"
[[ "$(calls)" != *REPLY* ]] && pass "backend-dev: nothing posted" || fail "backend-dev: posted on a role-owned PR" "$(calls)"
# Bound devex-tooling, but launched as another role: the launched role
# is the session's (review of #68), so it is not the owner.
thread_fixture "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2" false
with_role devex-tooling
MOCK_ENV=(env AGENT_FABRIC_LAUNCH_ROLE=backend-dev)
invoke "Answering as the binding says." "$THREAD_ID"
MOCK_ENV=(env)
assert_rc       "bound devex-tooling, launched backend-dev: refused" 2
[[ "$(calls)" != *REPLY* ]] && pass "…nothing posted" || fail "posted with a drifted role" "$(calls)"
# Bound devex-tooling, but not started by the launcher: no stamp, no role
# (review of #70).
thread_fixture "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2" false
with_role devex-tooling
invoke "Answering without a launch." "$THREAD_ID"
assert_rc       "bound devex-tooling, no launch stamp: refused" 2
[[ "$(calls)" != *REPLY* ]] && pass "…nothing posted" || fail "posted without a launch stamp" "$(calls)"
thread_fixture "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2" false
with_role -
invoke "No role here." "$THREAD_ID"
assert_rc       "no role bound: refused" 2
[[ "$(calls)" != *REPLY* ]] && pass "no role bound: nothing posted" || fail "no role bound: posted" "$(calls)"

echo "pr-reply: a real session's PR is STILL refused"
# The whole point of relaxing the guard is that it must not relax for
# the case it exists for. A four-segment, non-bot, well-typed branch
# belonging to someone else stays refused.
thread_fixture "$OTHER/fix/theirs" false
invoke "I would like to answer this." "$THREAD_ID"
assert_rc       "exits 2" 2
assert_contains "still names the owning session" "$OTHER"
if [[ "$(calls)" != *REPLY* ]]; then
    pass "still posts nothing"
else
    fail "relaxation leaked into the owned case" "$(calls)"
fi

echo "pr-reply: an odd <type> segment is a session, not an unowned branch"
# pr-sessions.sh imposes no vocabulary on <type> — `spike-3`, `hotfix`
# and `stage-4` are sessions. If this script disagreed, another
# session's PR on such a branch would read as unowned and be ANSWERED,
# which is the failure the guard exists to prevent, reached from the
# other side.
for t in spike-3 hotfix stage-4; do
    thread_fixture "$OTHER/$t/theirs" false
    invoke "no" "$THREAD_ID"
    if [[ "$RUN_RC" -eq 2 && "$(calls)" != *REPLY* ]]; then
        pass "refuses another session's '$t/' branch"
    else
        fail "answered another session's '$t/' branch" "rc=$RUN_RC $(calls)"
    fi
done

echo "pr-reply: an unowned branch is answered but NOT resolved by default"
# The warning used to say "resolve only what you actually verified" and
# then resolve in the same run — the operator read the precondition after
# it had already been violated. Resolving is a claim, and this is the
# path with the least standing to make it.
thread_fixture "agent/global-event-identity" false
invoke "Looks addressed, but I have not verified it." "$THREAD_ID"
assert_rc       "still replies" 0
if [[ "$(calls)" == *REPLY* ]]; then pass "the reply was posted"
else fail "no reply posted" "$(calls)"; fi
if [[ "$(calls)" != *RESOLVE* ]]; then pass "the thread was left OPEN"
else fail "resolved an unowned thread by default" "$(calls)"; fi
assert_contains "says it is leaving it open" "left OPEN"
assert_contains "names the opt-in flag"      "--resolve"

echo "pr-reply: --resolve is the opt-in on an unowned branch"
thread_fixture "agent/global-event-identity" false
invoke "Verified fixed in abc1234." "$THREAD_ID" --resolve
assert_rc "exits 0" 0
if [[ "$(calls)" == *RESOLVE* ]]; then pass "resolves when explicitly asked"
else fail "--resolve was ignored" "$(calls)"; fi

echo "pr-reply: an OWNED branch still resolves by default"
# The inversion above must be scoped to the unowned path only.
thread_fixture "$ME/feat/mine" false
invoke "Fixed." "$THREAD_ID"
assert_rc "exits 0" 0
if [[ "$(calls)" == *RESOLVE* ]]; then pass "own PR still resolves by default"
else fail "the unowned default leaked into an owned PR" "$(calls)"; fi

echo "pr-reply: an UNUSUAL <type> is still another session's branch"
# This case previously asserted the opposite, and the opposite was a
# hole. CLAUDE.md imposes no vocabulary on <type>, so a lowercase shape
# test is a permission decision resting on an open-ended set: every
# branch below belongs to a real parallel session, and a shape test
# calls each of them unowned — i.e. POST AND RESOLVE on somebody else's
# PR, which cannot be undone. The guard must refuse on the SPECIFIED
# shape (four segments, non-empty host/clone, non-vendor) and nothing
# more.
for t in "Fix" "chore(gh)" "WIP" "2fix" "-lead" "FEAT" "spike-3" "hotfix"; do
    thread_fixture "$OTHER/$t/x" false
    invoke "I must not be able to post this." "$THREAD_ID"
    if [[ "$RUN_RC" -eq 2 && "$(calls)" != *REPLY* ]]; then
        pass "refuses another session's '$t/' branch"
    else
        fail "WROTE to another session's '$t/' branch" "rc=$RUN_RC $(calls)"
    fi
done

echo "pr-reply: removing the type test did not make the orphans unreachable"
# The shape test bought nothing it was credited with: every branch this
# relaxation exists to answer is unowned by segment count or by the
# vendor deny-list, never by <type>. If that stops being true the four
# cases below start failing rather than silently narrowing. (The bot here
# is one with no owner in bot_owner_role — a Dependabot branch is no
# longer an orphan, it is the devex-tooling role's; that case is above.)
for branch in "renovate/pub/apps/driver_flutter/flutter-minor-patch-7a91" \
              "add-claude-github-actions-1785994932117" \
              "agent/global-event-identity" \
              "agent/common-api-idempotency"; do
    thread_fixture "$branch" false
    invoke "Obsolete." "$THREAD_ID"
    if [[ "$RUN_RC" -eq 0 && "$(calls)" == *REPLY* ]]; then
        pass "still answers '$branch'"
    else
        fail "orphan became unanswerable: '$branch'" "rc=$RUN_RC $(calls)"
    fi
done

echo "pr-reply: a failed reply never resolves the thread"
# The worst available outcome is a resolved thread with no reply: it
# reads as answered and shows nothing.
thread_fixture "$ME/feat/thing" false
MOCK_ENV=(env GH_MOCK_REPLY_FAIL=1)
invoke "…" "$THREAD_ID"
MOCK_ENV=(env)
assert_rc       "exits 2" 2
assert_contains "says the reply was rejected" "rejected"
if [[ "$(calls)" != *RESOLVE* ]]; then
    pass "the thread was left open"
else
    fail "resolved after a failed reply" "$(calls)"
fi

echo "pr-reply: a reply with no URL is treated as not posted"
thread_fixture "$ME/feat/thing" false
MOCK_ENV=(env GH_MOCK_REPLY_EMPTY=1)
invoke "…" "$THREAD_ID"
MOCK_ENV=(env)
assert_rc       "exits 2" 2
assert_contains "says so plainly" "did not post"

echo "pr-reply: a failed resolve is reported, not swallowed"
thread_fixture "$ME/feat/thing" false
MOCK_ENV=(env GH_MOCK_RESOLVE_FAIL=1)
invoke "Fixed." "$THREAD_ID"
MOCK_ENV=(env)
assert_rc       "exits 2" 2
assert_contains "says the reply landed"      "replied:"
assert_contains "and that the thread is open" "still open"

echo "pr-reply: an already-resolved thread is not re-resolved"
thread_fixture "$ME/feat/thing" true
invoke "One more note." "$THREAD_ID"
assert_rc       "exits 0" 0
assert_contains "says it is already resolved" "already resolved"
if [[ "$(calls)" != *RESOLVE* ]]; then
    pass "no resolve mutation was sent"
else
    fail "re-resolved" "$(calls)"
fi

echo "pr-reply: invocation errors"
thread_fixture "$ME/feat/thing" false
invoke "body" "PRRC_notathread"
assert_rc       "a comment id is refused" 2
assert_contains "explains the difference" "PRRC_ is a comment"

invoke "body" "not-an-id"
assert_rc       "a malformed id is refused" 2

invoke "" "$THREAD_ID"
assert_rc       "an empty body is refused" 2
assert_contains "says the body is empty" "empty"

invoke "   " "$THREAD_ID"
assert_rc       "a whitespace-only body is refused" 2

invoke "body"
assert_rc       "a missing thread id is refused" 2

invoke "body" "$THREAD_ID" "PRRT_second"
assert_rc       "two thread ids are refused" 2

invoke "body" "$THREAD_ID" --nope
assert_rc       "an unknown option is refused" 2

echo "pr-reply: outside a worktree it refuses rather than trusting itself"
# The ownership check is the only protection this script offers, and an
# unresolvable clone identity used to SKIP it: the guard read
# `[[ -n "$ME" && ... ]]`, so running the script by absolute path from
# outside any worktree posted AND resolved on whatever thread it was
# handed. Not knowing whose PR this is has to mean stop, not proceed.
thread_fixture "$ME/feat/thing" false
NOGIT="$(mktemp -d)"
RUN_OUT="$(cd "$NOGIT" && printf '%s' "would post anywhere" | \
    env PATH="$SANDBOX/bin:$PATH" GH_MOCK_STATE="$SANDBOX/state" \
    "${MOCK_ENV[@]}" bash "$UNDER_TEST" "$THREAD_ID" 2>&1)"
RUN_RC=$?
rm -rf "$NOGIT"; NOGIT=""
assert_rc       "exits 2" 2
assert_contains "says the identity is unknown" "identity is unknown"
if [[ "$(calls)" != *REPLY* ]]; then
    pass "nothing was posted"
else
    fail "posted without knowing whose PR it is" "$(calls)"
fi

echo "pr-reply: a missing hard dependency is named, not guessed at"
# git and hostname became hard dependencies when a failed rev-parse was
# made fatal. Without them in the preflight, a missing git surfaces as
# "not inside a git worktree ... run it from the clone that owns the PR"
# — at an operator standing in exactly that clone. Both directions exit
# 2, so this is diagnostic quality, not a bypass; it still needs a test,
# because reverting the preflight leaves every other assertion green.
thread_fixture "$ME/feat/thing" false
STRIP="$(mktemp -d)"
for b in bash env cat cut basename sed grep mktemp rm; do
    src="$(command -v "$b")" && ln -sf "$src" "$STRIP/$b"
done
ln -sf "$SANDBOX/bin/gh" "$STRIP/gh"
ln -sf "$(command -v jq)" "$STRIP/jq"
# deliberately NOT git and NOT hostname
RUN_OUT="$(cd "$SANDBOX/$CLONE_NAME" && printf '%s' "body" | \
    env -i PATH="$STRIP" GH_MOCK_STATE="$SANDBOX/state" \
    "$STRIP/bash" "$UNDER_TEST" "$THREAD_ID" 2>&1)"
RUN_RC=$?
assert_rc       "exits 2" 2
assert_contains "names git rather than blaming the cwd" "git is required"
ln -sf "$(command -v git)" "$STRIP/git"
RUN_OUT="$(cd "$SANDBOX/$CLONE_NAME" && printf '%s' "body" | \
    env -i PATH="$STRIP" GH_MOCK_STATE="$SANDBOX/state" \
    "$STRIP/bash" "$UNDER_TEST" "$THREAD_ID" 2>&1)"
RUN_RC=$?
assert_rc       "exits 2 for hostname too" 2
assert_contains "names hostname" "hostname is required"
rm -rf "$STRIP"; STRIP=""

echo "pr-reply: a failed thread read stops before posting"
thread_fixture "$ME/feat/thing" false
MOCK_ENV=(env GH_MOCK_READ_FAIL=1)
invoke "body" "$THREAD_ID"
MOCK_ENV=(env)
assert_rc "exits 2" 2
if [[ "$(calls)" != *REPLY* ]]; then
    pass "nothing was posted"
else
    fail "posted without knowing the owner" "$(calls)"
fi

echo "pr-reply: a thread in ANOTHER repository is refused"
# `node(id:)` is a GLOBAL lookup, so a foreign thread resolves fine. The
# only thing that used to stand between it and a reply was the
# branch-prefix ownership check -- which passes for any branch named
# `<host>/<clone>/...` in any repo on GitHub. The branch here is
# deliberately one this session OWNS, so the case can only pass if the
# repository check is what stops it.
thread_fixture "$ME/feat/thing" false "someone-else/other-repo"
invoke "body" "$THREAD_ID"
assert_rc "exits 2" 2
assert_contains "names both repositories" "someone-else/other-repo"
if [[ "$(calls)" != *REPLY* && "$(calls)" != *RESOLVE* ]]; then
    pass "neither replied nor resolved"
else
    fail "wrote to a thread in another repository" "$(calls)"
fi

echo "pr-reply: an unknowable current repository is refused, not assumed"
# Failing open here would restore the whole hole: with no local repo to
# compare against, every foreign thread would match nothing and pass.
thread_fixture "$ME/feat/thing" false
MOCK_ENV=(env GH_MOCK_REPO_FAIL=1)
invoke "body" "$THREAD_ID"
MOCK_ENV=(env)
assert_rc "exits 2" 2
assert_contains "says it cannot tell" "cannot determine the current repository"
if [[ "$(calls)" != *REPLY* ]]; then
    pass "nothing was posted"
else
    fail "posted without knowing which repo it is in" "$(calls)"
fi

echo "pr-reply: --dry-run touches nothing"
thread_fixture "$ME/feat/thing" false
invoke "Would say this." "$THREAD_ID" --dry-run
assert_rc       "exits 0" 0
assert_contains "shows the target"  "#77"
assert_contains "shows the body"    "Would say this."
if [[ "$(calls)" != *REPLY* && "$(calls)" != *RESOLVE* ]]; then
    pass "no mutation was sent"
else
    fail "--dry-run mutated something" "$(calls)"
fi

echo "pr-reply: --help lists the flags"
invoke "" --help
assert_rc       "exits 0" 0
assert_contains "documents --no-resolve" "--no-resolve"
assert_contains "documents --dry-run"    "--dry-run"

echo
# A helper that does not exist fails the suite, whatever the counter
# says — see command_not_found_handle above for why this cannot be a
# counter.
if [[ -s "$GUARD_MARKER" ]]; then
    echo "SELF-TEST BUG — undefined helper(s) called: $(sort -u "$GUARD_MARKER" | tr '\n' ' ')" >&2
    echo "  assertions using them never ran. Fix the names before trusting this suite." >&2
    rm -f "$GUARD_MARKER"
    exit 1
fi
rm -f "$GUARD_MARKER"
if [[ "$failures" -eq 0 ]]; then
    echo "test_pr-reply: OK — all assertions passed."
    exit 0
fi
echo "test_pr-reply: FAILED — $failures assertion(s) failed." >&2
exit 1
