#!/usr/bin/env bash
# tools/gh/test_pr-sessions.sh
#
# Behavioural tests for pr-sessions.sh.
#
# The script shipped across five PRs (#393, #394, #396, #397, #398)
# with no automated coverage, and review found four defects that a test
# would have caught on the way in — the author comparison that always
# rendered "!", the `/unresolved` filter that reported "none" after a
# FAILED lookup, an argument parser that spun forever on a missing
# operand, and bot branches attributed to a session named after the
# bot. Everything here is driven through the real script with a mocked
# `gh` on PATH, so the assertions are about observable output, not
# internals.
#
# The mock is faithful where it matters: `gh api graphql --jq FILTER`
# applies FILTER with real jq to a fixture GraphQL response, so the
# aggregation the script actually depends on is exercised rather than
# stubbed past.
#
# Run from anywhere:
#   bash tools/gh/test_pr-sessions.sh
#
# Exit codes:
#   0  all assertions passed
#   1  one or more assertions failed

set -uo pipefail

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/pr-sessions.sh"

if [[ ! -f "$UNDER_TEST" ]]; then
    echo "test: script under test not found at $UNDER_TEST" >&2
    exit 1
fi

command -v jq >/dev/null 2>&1 || {
    echo "test: jq is required to run these tests." >&2; exit 1; }

failures=0
SANDBOX=""

cleanup() { [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"; }
trap cleanup EXIT

# ── sandbox ─────────────────────────────────────────────────────────
#
# The script derives "this clone" from `hostname -s` + the git toplevel
# basename, so the sandbox is a real git repo with a known directory
# name and the fixtures are written against that same identity.
CLONE_NAME="legacy-testclone"
HOST="$(hostname -s)"
ME="$HOST/$CLONE_NAME"
OTHER="$HOST/legacy-otherclone"

setup_sandbox() {
    SANDBOX="$(mktemp -d)"
    mkdir -p "$SANDBOX/$CLONE_NAME" "$SANDBOX/bin" "$SANDBOX/fixtures"
    git -C "$SANDBOX/$CLONE_NAME" init -q 2>/dev/null

    cat > "$SANDBOX/bin/gh" <<'MOCK'
#!/usr/bin/env bash
# Mock gh. Behaviour is steered entirely by GH_MOCK_* environment
# variables so each case can pick its own failure mode.
set -uo pipefail

case "${1:-}" in
  pr)
    [[ -n "${GH_MOCK_PRLIST_FAIL:-}" ]] && exit 1
    # Record the --limit actually requested, so a case can assert about
    # the fetch that went out rather than the rendered page. Recorded
    # UNCONDITIONALLY, which is what lets this one mock serve every
    # case: a second mock installed mid-file to add one behaviour also
    # silently drops the others, and every case after it runs blind.
    args=("$@")
    for ((i = 0; i < ${#args[@]}; i++)); do
      [[ "${args[i]}" == "--limit" ]] && \
        printf '%s\n' "${args[i+1]:-}" > "$GH_MOCK_DIR/last-limit"
    done
    cat "$GH_MOCK_DIR/pr-list.json"
    ;;
  repo)
    [[ -n "${GH_MOCK_REPOVIEW_FAIL:-}" ]] && exit 1
    printf '%s\n' "${GH_MOCK_REPO:-gzapi-org/gzapp}"
    ;;
  api)
    [[ -n "${GH_MOCK_GRAPHQL_FAIL:-}" ]] && exit 1
    # Apply the caller's --jq filter to the fixture, exactly as gh does.
    filter=""; query=""; json=0
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --jq) filter="$2"; shift 2 ;;
        -f) [[ "$2" == query=* ]] && query="${2#query=}"; shift 2 ;;
        # The same call with its query and variables as JSON on stdin
        # (tools/fabric/gh.py, ADR-040 §5 rule 6); answered in GraphQL's
        # own shape — the fixture as it stands, `data` and all — where the
        # -f form is answered through the caller's --jq.
        --input) json=1; shift 2 ;;
        *) shift ;;
      esac
    done
    [[ "$json" == 1 ]] && query="$(jq -r '.query' < /dev/stdin)"
    # GRAPHQL RETURNS ONLY WHAT THE QUERY ASKED FOR, and the mock has to
    # honour that or it hides missing selections. A fixture that
    # volunteers pageInfo the query never requested lets the script pass
    # while asking the real API for a field it then reads as absent — the
    # test goes green on a query that would answer "not truncated" to
    # everything.
    src="$GH_MOCK_DIR/graphql.json"
    if [[ "$query" != *hasNextPage* ]]; then
      jq '(.data.repository // {}) |= with_entries(
            .value |= (if has("reviewThreads")
                       then .reviewThreads |= del(.pageInfo) else . end))' \
         "$GH_MOCK_DIR/graphql.json" > "$GH_MOCK_DIR/.served.json"
      src="$GH_MOCK_DIR/.served.json"
    fi
    if [[ -n "$filter" ]]; then
      jq -r "$filter" "$src"
    else
      cat "$src"
    fi
    ;;
  *)
    echo "mock gh: unhandled '${1:-}'" >&2; exit 1 ;;
esac
MOCK
    chmod +x "$SANDBOX/bin/gh"
}

# Runs the script inside the sandbox clone with the mock on PATH.
# Captures stdout+stderr; sets RUN_OUT and RUN_RC.
run() {
    RUN_OUT="$(cd "$SANDBOX/$CLONE_NAME" && \
        PATH="$SANDBOX/bin:$PATH" GH_MOCK_DIR="$SANDBOX/fixtures" \
        timeout 20 bash "$UNDER_TEST" "$@" 2>&1)"
    RUN_RC=$?
}

# Same, with extra environment (KEY=VALUE ...) before the script args,
# separated by `--`.
run_env() {
    local env=()
    while [[ $# -gt 0 && "$1" != "--" ]]; do env+=("$1"); shift; done
    shift
    RUN_OUT="$(cd "$SANDBOX/$CLONE_NAME" && \
        PATH="$SANDBOX/bin:$PATH" GH_MOCK_DIR="$SANDBOX/fixtures" \
        env "${env[@]}" timeout 20 bash "$UNDER_TEST" "$@" 2>&1)"
    RUN_RC=$?
}

# ── assertions ──────────────────────────────────────────────────────

pass() { echo "  ✓ $1"; }
fail() {
    echo "  ✗ $1" >&2
    printf '%s\n' "${2:-}" | sed 's/^/      /' >&2
    failures=$((failures + 1))
}

assert_rc() {
    local label="$1" want="$2"
    if [[ "$RUN_RC" -eq "$want" ]]; then pass "$label"
    else fail "$label — expected exit $want, got $RUN_RC" "$RUN_OUT"; fi
}

assert_contains() {
    local label="$1" needle="$2"
    if [[ "$RUN_OUT" == *"$needle"* ]]; then pass "$label"
    else fail "$label — output did not contain '$needle'" "$RUN_OUT"; fi
}

assert_not_contains() {
    local label="$1" needle="$2"
    if [[ "$RUN_OUT" != *"$needle"* ]]; then pass "$label"
    else fail "$label — output unexpectedly contained '$needle'" "$RUN_OUT"; fi
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

# ── fixtures ────────────────────────────────────────────────────────

# Fixture timestamps are RELATIVE to now, never literal dates.
#
# `pr-sessions.sh` derives a /lastDate cutoff from the real wall clock,
# and nothing here mocks `date`. Pinned fixtures therefore age: the
# original 2026-08-06 rows sat inside `/lastDate:99d` when they were
# written and would have fallen outside it on 2026-11-13, failing a
# required check that also runs on merge_group — i.e. blocking every
# queued PR in the repo, on a date certain, with nothing in the diff to
# explain why. Relative fixtures cannot expire.
ago() { date -u -d "$1 ago" +%Y-%m-%dT%H:%M:%SZ; }

write_pr_list() { printf '%s\n' "$1" > "$SANDBOX/fixtures/pr-list.json"; }
write_graphql() { printf '%s\n' "$1" > "$SANDBOX/fixtures/graphql.json"; }

# Three PRs: two this session's, one another session's.
default_pr_list() {
    write_pr_list "$(jq -n --arg me "$ME" --arg other "$OTHER" \
      --arg t30 "$(ago '1 hour')" --arg t29 "$(ago '2 hours')" \
      --arg t28 "$(ago '3 hours')" '[
      {number: 30, state: "OPEN",   headRefName: ($me    + "/feat/alpha"),
       title: "alpha", updatedAt: $t30, isDraft: false, mergedAt: null},
      {number: 29, state: "MERGED", headRefName: ($other + "/fix/beta"),
       title: "beta",  updatedAt: $t29, isDraft: false,
       mergedAt: $t29},
      {number: 28, state: "MERGED", headRefName: ($me    + "/docs/gamma"),
       title: "gamma", updatedAt: $t28, isDraft: false,
       mergedAt: $t28}
    ]')"
}

# #30 — one unresolved thread, reviewer spoke last  → "1!"
# #29 — one unresolved thread, PR AUTHOR spoke last → "1"  (no bang)
# #28 — threads exist but all resolved              → "-"
default_graphql() {
    write_graphql "$(jq -n '{
      data: {repository: {
        p30: {number: 30, author: {login: "andreabenetton"},
              reviewThreads: {nodes: [
                {isResolved: false, comments: {nodes: [{author: {login: "some-reviewer"}}]}}
              ]}},
        p29: {number: 29, author: {login: "andreabenetton"},
              reviewThreads: {nodes: [
                {isResolved: false, comments: {nodes: [{author: {login: "andreabenetton"}}]}}
              ]}},
        p28: {number: 28, author: {login: "andreabenetton"},
              reviewThreads: {nodes: [
                {isResolved: true, comments: {nodes: [{author: {login: "some-reviewer"}}]}}
              ]}}
      }}
    }')"
}

# ── cases ───────────────────────────────────────────────────────────

setup_sandbox

echo "pr-sessions: default scope"
default_pr_list; default_graphql
run
assert_rc        "exits 0" 0
assert_contains  "shows this session's PR"          "#30"
assert_contains  "shows this session's other PR"    "#28"
assert_not_contains "hides another session's PR"  "#29"
assert_contains  "says it defaulted to this session" "Scoped to this session"

echo "pr-sessions: /all"
run /all
assert_rc       "exits 0" 0
assert_contains "includes the other session's PR" "#29"
assert_contains "still includes this session's"     "#30"

echo "pr-sessions: explicit session filter"
run --session legacy-otherclone
assert_rc           "exits 0" 0
assert_contains     "matches the named session"     "#29"
assert_not_contains "excludes the other session"    "#30"

echo "pr-sessions: state filter is chosen at fetch time"
run /OPEN
assert_rc       "exits 0" 0

echo "pr-sessions: conflicting state flags are refused"
run /OPEN /MERGED
assert_rc       "exits 2" 2
assert_contains "names the conflict" "conflict"

echo "pr-sessions: grouped output"
run /all --by-session
assert_rc       "exits 0" 0
assert_contains "groups under this session" "$ME"
assert_contains "marks this session"      "this session"

echo "pr-sessions: empty result is a clean exit, not an error"
write_pr_list '[]'
run
assert_rc       "exits 0" 0
assert_contains "says nothing matched" "no PRs"
default_pr_list

echo "pr-sessions: THR column reflects the thread lookup"
run /all
assert_rc       "exits 0" 0
# "1!" — a reviewer spoke last on #30, so a reply is owed.
assert_contains "flags a thread awaiting a reply" "1!"
# #29's unresolved thread was last answered by the PR AUTHOR, so the
# count stands alone: answered, merely not resolved. This is the case
# the broken comparison could not express — `.author` was read off the
# thread node, which has no such field, so every unresolved thread
# compared against null and every row wore a bang.
row_29="$(printf '%s\n' "$RUN_OUT" | grep -- '#29')"
if [[ "$row_29" == *"1!"* ]]; then
    fail "no bang when the author answered last" "$row_29"
else
    pass "no bang when the author answered last"
fi
# #28's threads are all resolved → "-"; if the resolved filter broke,
# this would read "1".
assert_contains "shows resolved-only PRs as a dash" "-"

echo "pr-sessions: --no-threads skips the lookup"
run /all --no-threads
assert_rc           "exits 0" 0
assert_not_contains "no bang without the lookup" "1!"

echo "pr-sessions: /unresolved needs the lookup"
run /unresolved --no-threads
assert_rc       "exits 2" 2
assert_contains "explains the conflict" "drop --no-threads"

echo "pr-sessions: /unresolved keeps only PRs with open threads"
run /all /unresolved
assert_rc           "exits 0" 0
assert_contains     "keeps #30"            "#30"
assert_contains     "keeps #29"            "#29"
assert_not_contains "drops the resolved-only PR" "#28"

echo "pr-sessions: a truncated thread page reads UNKNOWN, not zero"
# Only the first 100 threads arrive. A pr whose early threads are all
# resolved and whose open one sits on page two therefore looks clean —
# "-" in the column, dropped from /unresolved — which hides precisely the
# outstanding work this command exists to surface. #28's visible thread
# is resolved, so without the hasNextPage read it renders "-".
# #30 and #29 keep their ordinary counts so the "?" below can only have
# come from the truncated pr — otherwise a pr simply MISSING from the
# response would satisfy the same assertion.
write_graphql "$(jq -n '{
  data: {repository: {
    p30: {number: 30, author: {login: "andreabenetton"},
          reviewThreads: {pageInfo: {hasNextPage: false}, nodes: [
            {isResolved: false, comments: {nodes: [{author: {login: "some-reviewer"}}]}}
          ]}},
    p29: {number: 29, author: {login: "andreabenetton"},
          reviewThreads: {pageInfo: {hasNextPage: false}, nodes: [
            {isResolved: false, comments: {nodes: [{author: {login: "andreabenetton"}}]}}
          ]}},
    p28: {number: 28, author: {login: "andreabenetton"},
          reviewThreads: {pageInfo: {hasNextPage: true}, nodes: [
            {isResolved: true, comments: {nodes: [{author: {login: "some-reviewer"}}]}}
          ]}}
  }}
}')"
run /all
assert_rc           "exits 0" 0
assert_contains     "renders the truncated count as unknown" "?"
assert_not_contains "does not claim zero open threads" " -  "

run /all /unresolved
assert_rc       "exits 0" 0
assert_contains "keeps the pr rather than dropping it" "#28"

default_graphql

echo "pr-sessions: an older branch named for this working copy is this agent's own"
write_pr_list "$(jq -n --arg old "$HOST/$CLONE_NAME" --arg t "$(ago '1 hour')" '[
  {number: 731, state: "OPEN", isDraft: false, headRefName: ($old + "/fix/mine-under-the-old-name"), updatedAt: $t}
]')"
run --no-threads
assert_rc       "exits 0" 0
assert_contains "the legacy-named row is in the default (mine) scope" "#731"
assert_contains "and marked as this session's" "* #731"
write_pr_list "$(jq -n --arg other "$HOST/legacy-old" --arg t "$(ago '1 hour')" '[
  {number: 732, state: "OPEN", isDraft: false, headRefName: ($other + "/fix/theirs"), updatedAt: $t}
]')"
run --no-threads
assert_not_contains "another working copy's older branch is not in the mine scope" "#732"
run /unattributed --no-threads
assert_not_contains "nor is it unattributed: it names a session" "#732"
run /all --no-threads
assert_contains "it is listed under /all, as that session's" "#732"
# A clone named after its repository is every login's default clone: its
# name is no session's, and an older branch under it is not "mine".
git -C "$SANDBOX/$CLONE_NAME" remote add origin "git@example.com:org/$CLONE_NAME.git"
write_pr_list "$(jq -n --arg old "$HOST/$CLONE_NAME" --arg t "$(ago '1 hour')" '[
  {number: 733, state: "OPEN", isDraft: false, headRefName: ($old + "/fix/under-the-repo-name"), updatedAt: $t}
]')"
run --no-threads
assert_not_contains "a branch named for the repository is no session's" "#733"
git -C "$SANDBOX/$CLONE_NAME" remote remove origin
default_pr_list

echo "pr-sessions: pool filters"
run /all /lastItem:1
assert_rc           "exits 0" 0
assert_contains     "keeps the newest PR"     "#30"
assert_not_contains "drops everything older"  "#29"

run /all /lastDate:99d
assert_rc       "/lastDate accepts <N>d" 0
assert_contains "keeps PRs in the window" "#30"

# A TIGHT window, which is what keeps the fixtures honest.
#
# /lastDate:99d passes for ~99 days after any pinned fixture is written,
# so it cannot tell a relative fixture from one that is quietly ageing
# out — the original rows sat inside it for three months before they
# would have started failing a required check on merge_group. A one-day
# window is outside a pinned fixture's reach almost immediately, so this
# fails within a day of anyone reintroducing a literal date.
run /all /lastDate:1d
assert_rc       "/lastDate:1d exits 0" 0
assert_contains "fixtures are recent enough for a tight window" "#30"

echo "pr-sessions: /unresolved honours an explicit /lastItem"
# The candidate cap of 100 was applied as the FINAL slice, after
# /lastItem had already narrowed the pool — so `/lastItem:150 /unresolved`
# queried the newest 100 and never asked about rows 101-150. The caller
# named a number and silently got a different one.
#
# 150 rows; every one has a RESOLVED thread except the oldest, #151. If
# the cap still won, #151 is never queried and never reported.
write_pr_list "$(jq -n --arg me "$ME" --arg t "$(ago '1 hour')" '[range(150) | {
  number: (300 - .), state: "MERGED", headRefName: ($me + "/feat/p" + (. | tostring)),
  title: "p", updatedAt: $t, isDraft: false, mergedAt: $t}]')"
write_graphql "$(jq -n '{data: {repository: (
  [range(150) | {key: ("p" + ((300 - .) | tostring)),
                 value: {number: (300 - .), author: {login: "andreabenetton"},
                         reviewThreads: {pageInfo: {hasNextPage: false}, nodes: [
                           {isResolved: ((300 - .) != 151),
                            comments: {nodes: [{author: {login: "some-reviewer"}}]}}
                         ]}}}] | from_entries)}}')"
run /all -n 200 /lastItem:150 /unresolved
assert_rc           "exits 0" 0
assert_contains     "queries past the 100-row cap" "#151"
assert_not_contains "and still drops the resolved ones" "#300"

default_pr_list; default_graphql

echo "pr-sessions: malformed pool filters are refused"
run /lastItem:0
assert_rc       "/lastItem:0 exits 2" 2
assert_contains "names the expectation" "positive integer"

run /lastItem:
assert_rc       "empty /lastItem exits 2" 2

run /lastDate:5
assert_rc       "unit-less /lastDate exits 2" 2
assert_contains "names the accepted units" "<N>d"

run /lastDate:
assert_rc       "empty /lastDate exits 2" 2

echo "pr-sessions: unknown options are refused"
run --nope
assert_rc       "exits 2" 2
assert_contains "points at --help" "--help"

echo "pr-sessions: --help lists every documented flag"
run --help
assert_rc       "exits 0" 0
assert_contains "documents /all"        "/all"
assert_contains "documents --by-session" "--by-session"
# These live below the old hard-coded line-36 cut-off. Their absence was
# the discoverability regression review flagged on #394 and #398.
assert_contains "documents /lastItem"   "/lastItem"
assert_contains "documents /lastDate"   "/lastDate"
assert_contains "documents /unresolved" "/unresolved"

echo "pr-sessions: a missing operand is refused, not looped on"
# `-n` last: `shift 2` cannot consume two arguments, and with `set -e`
# off the parser used to spin forever. `timeout` in run() turns a
# regression here into exit 124 rather than a hung suite.
run -n
assert_rc       "bare -n exits 2" 2
assert_contains "names the flag" "-n"

run --session
assert_rc       "bare --session exits 2" 2

echo "pr-sessions: a non-numeric limit is refused before arithmetic"
# `$(( LIMIT * 20 ))` re-evaluates the variable's CONTENT as an
# arithmetic expression, and bash evaluates command substitution inside
# an array subscript — so an unvalidated limit is code execution, not
# just a bad number.
run -n 'x[$(touch "'"$SANDBOX"'/pwned")]'
assert_rc "injected limit exits 2" 2
if [[ -e "$SANDBOX/pwned" ]]; then
    fail "arithmetic injection executed the payload" "$RUN_OUT"
    rm -f "$SANDBOX/pwned"
else
    pass "arithmetic injection did not execute"
fi

run -n abc
assert_rc       "non-numeric limit exits 2" 2
assert_contains "names the expectation" "positive integer"

echo "pr-sessions: a Dependabot branch is not a session — it is the devex-tooling ROLE's"
# The vendor deny-list still says a bot branch names no session. It used
# to end there: every bot row read "(unconventional)", fell outside every
# scope, and 28 of 31 unreachable rows on gzapp were Dependabot's — their
# review findings routed to nobody. A Dependabot row now resolves to
# role:devex-tooling (architect-cto, 2026-09-14). A bot with no owner in
# the map stays unattributed, visibly, exactly as before.
write_pr_list "$(jq -n --arg me "$ME" \
  --arg t1 "$(ago '1 hour')" --arg t2 "$(ago '2 hours')" \
  --arg t3 "$(ago '3 hours')" --arg t4 "$(ago '4 hours')" '[
  {number: 40, state: "OPEN", headRefName: "dependabot/github_actions/actions-minor-patch-5c7bcdc794",
   title: "bump", updatedAt: $t1, isDraft: false, mergedAt: null},
  {number: 41, state: "OPEN", headRefName: "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2",
   title: "bump", updatedAt: $t2, isDraft: false, mergedAt: null},
  {number: 42, state: "OPEN", headRefName: ($me + "/feat/real"),
   title: "real", updatedAt: $t3, isDraft: false, mergedAt: null},
  {number: 43, state: "OPEN", headRefName: "renovate/npm/vite-6.x",
   title: "bump", updatedAt: $t4, isDraft: false, mergedAt: null}
]')"
write_graphql "$(jq -n '{data: {repository: {
  p40: {number: 40, author: {login: "app/dependabot"}, reviewThreads: {nodes: []}},
  p41: {number: 41, author: {login: "app/dependabot"}, reviewThreads: {nodes: [{isResolved: false, comments: {nodes: [{author: {login: "reviewer[bot]"}}]}}]}},
  p42: {number: 42, author: {login: "andreabenetton"}, reviewThreads: {nodes: []}},
  p43: {number: 43, author: {login: "app/renovate"}, reviewThreads: {nodes: []}}
}}}')"
run /all
assert_rc       "exits 0" 0
# The branch name itself still shows in the WORK column, so the claim
# has to be about the SESSION column of each row specifically.
for n in 40 41; do
    row="$(printf '%s\n' "$RUN_OUT" | grep -- "#$n")"
    if [[ "$row" == *"role:devex-tooling"* && "$row" != *"(unconventional)"* ]]; then
        pass "#$n is the devex-tooling role's"
    else
        fail "#$n did not resolve to role:devex-tooling" "$row"
    fi
done
row="$(printf '%s\n' "$RUN_OUT" | grep -- "#43")"
if [[ "$row" == *"(unconventional)"* ]]; then pass "#43 (a bot with no owner in the map) stays unattributed"
else fail "#43 was attributed" "$row"; fi
assert_contains "a real session branch still resolves" "$ME"

# ROLE SCOPE. A session whose binding holds devex-tooling sees the
# Dependabot rows in its DEFAULT scope and in /unresolved; a session
# bound to any other role does not, and neither counts them as
# unattributed. The binding is what identity.py --role reads, planted
# under a private state dir, keyed by this login as identity.py demands.
plant_role() {  # <role> -> AGENT_FABRIC_STATE_DIR holding a binding for this login
    local role="$1" login; login="$(id -un)"
    local d="$SANDBOX/state-$role"; mkdir -p "$d/agents/$login"
    jq -n --arg a "$login" --arg r "$role" '{agent:$a, role:$r}' > "$d/agents/$login/binding.json"
    printf '%s' "$d"
}
run_env AGENT_FABRIC_STATE_DIR="$(plant_role devex-tooling)" --
assert_rc       "devex-tooling default scope: exits 0" 0
assert_contains "devex-tooling default scope lists the Dependabot row #40" "#40"
assert_contains "devex-tooling default scope lists the Dependabot row #41" "#41"
assert_not_contains "devex-tooling default scope does not list the renovate row" "#43"
row="$(printf '%s\n' "$RUN_OUT" | grep -- "#41")"
if [[ "$row" == "*"* ]]; then pass "the Dependabot row is marked mine (*)"; else fail "the Dependabot row is not marked mine" "$row"; fi
run_env AGENT_FABRIC_STATE_DIR="$(plant_role devex-tooling)" -- /unresolved
assert_rc       "devex-tooling /unresolved: exits 0" 0
assert_contains "devex-tooling /unresolved surfaces the Dependabot thread" "#41"
assert_not_contains "devex-tooling /unresolved does not surface a resolved bot row" "#40"
run_env AGENT_FABRIC_STATE_DIR="$(plant_role backend-dev)" --
assert_rc       "backend-dev default scope: exits 0" 0
assert_not_contains "backend-dev default scope does not list #40" "#40"
assert_not_contains "backend-dev default scope does not list #41" "#41"
assert_contains "the NOTE counts only the unowned bot row" "1 PR(s) name no live session"
default_pr_list; default_graphql

echo "pr-sessions: a session branch is attributed by SHAPE, not a type vocabulary"
# The predicate used to require one of thirteen conventional-commit
# words in the <type> segment, so `spike-3/`, `hotfix/` and `stage-4/`
# branches were classified unconventional and then SILENTLY DROPPED by
# the default clone scope — the command whose job is surfacing
# outstanding work answering "none". CLAUDE.md puts no vocabulary on
# <type>; only the shape is specified, so only the shape is checked.
write_pr_list "$(jq -n --arg me "$ME" \
  --arg t1 "$(ago '1 hour')" --arg t2 "$(ago '2 hours')" \
  --arg t3 "$(ago '3 hours')" '[
  {number: 50, state: "OPEN", headRefName: ($me + "/spike-3/beacon-parse"),
   title: "spike", updatedAt: $t1, isDraft: false, mergedAt: null},
  {number: 51, state: "OPEN", headRefName: ($me + "/hotfix/regime-strip"),
   title: "hotfix", updatedAt: $t2, isDraft: false, mergedAt: null},
  {number: 52, state: "OPEN", headRefName: ($me + "/feat/known-type"),
   title: "feat", updatedAt: $t3, isDraft: false, mergedAt: null}
]')"
write_graphql "$(jq -n '{data: {repository: {
  p50: {number: 50, author: {login: "andreabenetton"}, reviewThreads: {nodes: []}},
  p51: {number: 51, author: {login: "andreabenetton"}, reviewThreads: {nodes: []}},
  p52: {number: 52, author: {login: "andreabenetton"}, reviewThreads: {nodes: []}}
}}}')"
# DEFAULT scope, not /all: the drop this guards against happens in the
# scope filter, so a run that scopes to nothing proves nothing.
run
assert_rc       "exits 0" 0
assert_contains "an unlisted <type> is still this session's work" "#50"
assert_contains "  and so is another one"                       "#51"
assert_contains "a conventional type is unaffected"             "#52"
assert_not_contains "none of them read as unattributed" "(unconventional)"

echo "pr-sessions: a branch with too few segments is still unattributed"
# Shape-matching is not "anything goes" — <host>/<clone>/<type>/<desc>
# needs four segments before $p[0]/$p[1] means a session at all.
write_pr_list "$(jq -n --arg me "$ME" --arg t1 "$(ago '1 hour')" '[
  {number: 53, state: "OPEN", headRefName: "agent/global-event-identity",
   title: "agent", updatedAt: $t1, isDraft: false, mergedAt: null}
]')"
write_graphql "$(jq -n '{data: {repository: {
  p53: {number: 53, author: {login: "andreabenetton"}, reviewThreads: {nodes: []}}
}}}')"
run /all
assert_rc       "exits 0" 0
row="$(printf '%s\n' "$RUN_OUT" | grep -- '#53')"
if [[ "$row" == *"(unconventional)"* ]]; then
    pass "#53 is not attributed to a session"
else
    fail "#53 was attributed to a session" "$row"
fi
default_pr_list; default_graphql

echo "pr-sessions: PRs no scope filter can attribute are disclosed, not dropped"
# A row that does not parse as <host>/<clone>/<type>/<desc> is removed by
# any scope filter. Removing it SILENTLY is how a listing looks complete
# when it is not, so the count is stated on every path that can exit.
unscopable_list() {
    write_pr_list "$(jq -n --arg me "$ME" \
      --arg t1 "$(ago '1 hour')" --arg t2 "$(ago '2 hours')" '[
      {number: 60, state: "OPEN", headRefName: "add-claude-github-actions-1785994932117",
       title: "hand-made", updatedAt: $t1, isDraft: false, mergedAt: null},
      {number: 61, state: "OPEN", headRefName: ($me + "/feat/real"),
       title: "real", updatedAt: $t2, isDraft: false, mergedAt: null}
    ]')"
    write_graphql "$(jq -n '{data: {repository: {
      p60: {number: 60, author: {login: "andreabenetton"}, reviewThreads: {nodes: []}},
      p61: {number: 61, author: {login: "andreabenetton"}, reviewThreads: {nodes: []}}
    }}}')"
}
unscopable_list
run
assert_rc       "exits 0" 0
assert_contains "the footer path discloses the omission" "cannot be scoped to a"
assert_contains "  and counts them"                      "1 PR(s) name no live session"

echo "pr-sessions: /all reports nothing omitted, because nothing was scoped away"
run /all
assert_rc           "exits 0" 0
assert_not_contains "no disclosure when no filter acted" "cannot be scoped to a"

echo "pr-sessions: the disclosure survives the no-rows early exit"
# The reassuring "no PRs" answer is exactly the one a reader acts on, so
# it is the path where a footer-only disclosure would be missing.
write_pr_list "$(jq -n --arg t1 "$(ago '1 hour')" '[
  {number: 62, state: "OPEN", headRefName: "add-claude-github-actions-1785994932117",
   title: "hand-made", updatedAt: $t1, isDraft: false, mergedAt: null}
]')"
write_graphql "$(jq -n '{data: {repository: {}}}')"
run
assert_rc       "exits 0" 0
assert_contains "says there are no PRs for this session" "no PRs for this session"
assert_contains "  and still discloses the omission"   "cannot be scoped to a"

echo "pr-sessions: the disclosure survives the /unresolved-empty early exit"
unscopable_list
run /unresolved
assert_rc       "exits 0" 0
assert_contains "says nothing is unresolved"         "no PRs with unresolved"
assert_contains "  and still discloses the omission" "cannot be scoped to a"

echo "pr-sessions: /unattributed lists exactly the rows no scope can reach"
# The count in the NOTE told you how many were hidden, and no invocation
# could show them: /all stops filtering rather than selecting, so an
# unowned row still competes with every recent PR for the page. This is
# the scope that asks for them directly.
unscopable_list
run /unattributed
assert_rc           "exits 0" 0
assert_contains     "lists the unscopable PR"        "#60"
assert_not_contains "excludes an owned PR"           "#61"

echo "pr-sessions: /unattributed does not warn about omitting what it just listed"
# The disclosure counts what SCOPE dropped. Under this scope nothing is
# dropped, so counting here would print "1 PR(s) ... are not listed"
# directly above the one row it names — a footer contradicting its page.
assert_not_contains "no self-contradicting disclosure" "cannot be scoped to a"

echo "pr-sessions: /unattributed does not claim any row is this session's"
# Every row here failed to parse as a session, so the "*" legend cannot
# apply and "leave other sessions alone" is the wrong instruction — it
# is the reading that left these unanswered.
assert_not_contains "drops the ownership legend" "* = "
assert_contains     "says the findings are unowned" "no session"

echo "pr-sessions: the NOTE points at the flag that can actually list them"
# "Pass /all to see every PR regardless" was the advice, and /all does
# not select these — it merely stops filtering, so they still fall off
# the page. Naming a flag that cannot answer is worse than naming none.
unscopable_list
run
assert_rc       "exits 0" 0
assert_contains "names the listing flag" "/unattributed"

echo "pr-sessions: two different scope flags are refused, not last-wins"
# `/unattributed /all` printed every PR and `/all /unattributed` printed
# only the unowned ones — silently, in both directions.
run /unattributed /all
assert_rc       "exits 2" 2
assert_contains "names the conflict" "different scopes"
run /all /unattributed
assert_rc       "exits 2 the other way round too" 2
run /unattributed /unattributed
assert_rc       "the same scope twice is fine" 0

echo "pr-sessions: --session unconventional is the same scope, not a second one"
# It already selected these rows (the session string is a literal), but
# printed the omission NOTE above the rows it had just listed.
unscopable_list
run --session unconventional
assert_rc           "exits 0" 0
assert_contains     "lists the unscopable PR" "#60"
assert_not_contains "no self-contradicting disclosure" "cannot be scoped to a"
assert_not_contains "drops the ownership legend"       "* = "
default_pr_list; default_graphql

echo "pr-sessions: /unattributed narrows BEFORE the thread lookup"
# Scope is applied before the candidate slice, which is the whole reason
# this pairing works: an unowned row is by definition an older one, so
# under /all it loses the slice to recent PRs and its threads are never
# queried at all. Here it is the only row, so it must carry a real count.
# THE POOL MUST EXCEED THE CANDIDATE SLICE (100) or the claim is not
# falsifiable: with two rows, applying the scope AFTER the slice would
# leave this case green. So 150 owned rows are numbered ABOVE the one
# unowned row, putting it at position 151 — outside the slice unless the
# scope really is applied first.
write_pr_list "$(jq -n --arg me "$ME" \
  --arg t1 "$(ago '1 hour')" --arg t2 "$(ago '2 hours')" '
  [{number: 70, state: "MERGED", headRefName: "agent/global-event-identity",
    title: "unowned", updatedAt: $t1, isDraft: false, mergedAt: $t1}]
  + [range(150) | {number: (200 + .), state: "OPEN",
     headRefName: ($me + "/feat/w\(.)"), title: "w",
     updatedAt: $t2, isDraft: false, mergedAt: null}]')"
write_graphql "$(jq -n '{data: {repository: {
  p70: {number: 70, author: {login: "andreabenetton"},
        reviewThreads: {pageInfo: {hasNextPage: false}, nodes: [
          {isResolved: false, comments: {nodes: [{author: {login: "reviewer[bot]"}}]}},
          {isResolved: false, comments: {nodes: [{author: {login: "reviewer[bot]"}}]}}
        ]}}
}}}')"
run /unattributed /unresolved
assert_rc       "exits 0" 0
assert_contains "surfaces the unowned PR"          "#70"
assert_contains "with a real awaiting-reply count" "2!"

echo "pr-sessions: /unattributed with nothing to show is a clean, named exit"
default_pr_list; default_graphql
run /unattributed
assert_rc           "exits 0" 0
assert_contains     "names this scope, not another" "without a parsable session branch"
assert_not_contains "does not claim it scoped to the session" "PRs for this session"

echo "pr-sessions: /unattributed and /unresolved with nothing to show names the scope"
# Reaching the /unresolved-empty exit needs a row that EXISTS under this
# scope and simply has nothing open — with no unattributed row at all the
# earlier rows-empty exit fires instead, and this case would assert
# against a message it never reaches.
write_pr_list "$(jq -n --arg me "$ME" --arg t1 "$(ago '1 hour')" '[
  {number: 72, state: "MERGED", headRefName: "agent/common-api-idempotency",
   title: "unowned", updatedAt: $t1, isDraft: false, mergedAt: $t1}
]')"
write_graphql "$(jq -n '{data: {repository: {
  p72: {number: 72, author: {login: "andreabenetton"},
        reviewThreads: {pageInfo: {hasNextPage: false}, nodes: [
          {isResolved: true, comments: {nodes: [{author: {login: "reviewer[bot]"}}]}}
        ]}}
}}}')"
run /unattributed /unresolved
assert_rc           "exits 0" 0
assert_contains     "names the unowned scope" "branches no session owns"
assert_not_contains "not the session scope"   "for this session"
default_pr_list; default_graphql

echo "pr-sessions: the count describes the NARROWED pool, not everything fetched"
# /lastItem fixes the pool before scope. Counting before that narrowing
# announces a PR the caller never asked about and that nothing omitted:
# #60 is outside a one-item pool, so there is nothing to disclose.
unscopable_list
run /lastItem:1
assert_rc           "exits 0" 0
assert_not_contains "does not announce a PR outside the pool" "cannot be scoped to a"
default_pr_list; default_graphql

echo "pr-sessions: an invalid --session regex is an invocation error"
# `test()` with a bad pattern kills jq. Swallowing that printed "no
# matching PRs" and exited 0 — the same reassuring answer a genuinely
# empty result gives.
run --session '['
assert_rc       "exits 2" 2
assert_contains "says the filter was rejected" "session"
assert_not_contains "does not claim an empty result" "no PRs for a session"

echo "pr-sessions: a failed thread lookup reads as unknown, never zero"
run_env GH_MOCK_GRAPHQL_FAIL=1 -- /all
assert_rc       "listing still succeeds" 0
assert_contains "THR shows unknown" "?"

run_env GH_MOCK_GRAPHQL_FAIL=1 -- /all /unresolved
assert_rc           "/unresolved refuses to guess" 2
assert_contains     "says the lookup failed"       "could not"
assert_not_contains "never claims there are none"  "no PRs with unresolved review threads"

run_env GH_MOCK_REPOVIEW_FAIL=1 -- /all /unresolved
assert_rc       "/unresolved refuses to guess without a repo" 2

echo "pr-sessions: a failed pr list is an invocation error"
run_env GH_MOCK_PRLIST_FAIL=1 -- /all
assert_rc       "exits 2" 2
assert_contains "names the likely cause" "could not list PRs"

echo "pr-sessions: /lastItem beyond the derived cap is honoured, not clamped"
# The faithful mock records the --limit it was handed, so the claim is
# about the fetch that actually went out rather than the rendered page.
run /all /lastItem:600 --no-threads
assert_rc "exits 0" 0
requested="$(cat "$SANDBOX/fixtures/last-limit" 2>/dev/null || echo missing)"
if [[ "$requested" == "600" ]]; then
    pass "fetches the full 600-PR pool"
else
    fail "silently clamped the pool" "gh pr list --limit was '$requested', wanted 600"
fi

echo "pr-sessions: a full /lastDate page warns that the window may be short"
# The warning fires when the fetch came back full, so the fixture has to
# fill the derived 200-row page.
write_pr_list "$(jq -n --arg me "$ME" --arg t "$(ago '1 hour')" '[range(200) | {
  number: (500 - .), state: "OPEN", headRefName: ($me + "/feat/w\(.)"),
  title: "w", updatedAt: $t, isDraft: false, mergedAt: null}]')"
# -n 10 puts the derived fetch at its 200 floor, which the fixture fills
# exactly.
run /all -n 10 /lastDate:99d --no-threads
assert_rc       "exits 0" 0
assert_contains "warns that the window may be truncated" "may be"
default_pr_list

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
    echo "test_pr-sessions: OK — all assertions passed."
    exit 0
fi
echo "test_pr-sessions: FAILED — $failures assertion(s) failed." >&2
exit 1
