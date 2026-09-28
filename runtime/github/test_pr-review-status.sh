#!/usr/bin/env bash
# runtime/github/test_pr-review-status.sh (lifted from the first managed project's tools/gh/ on 2026-09-19 — the commit names it; general to every managed project, whose own tools/gh/ copy is a forwarder through projects/<id>/integration/gh/)
#
# Behavioural tests for pr-review-status.sh.
#
# The script exists because two GitHub behaviours make the obvious
# reading wrong — a self-reply registers as a REVIEW, and a comment's
# commit_id is re-anchored to the current head. Both produce the SAME
# dangerous answer: "this was reviewed" when it was not. So the tests
# that matter most are the ones asserting a NON-zero exit on input that
# superficially looks reviewed.
#
# The waiting half adds a second dangerous silence: a PR that was
# reviewed and then pushed to will never be reviewed again unless asked,
# and a tool that waits out its timeout there reports "not yet" for a
# state that is permanent. That must exit 5, immediately, without
# sleeping.
#
# The mock serves one scripted poll per `gh pr view` call, so a case can
# say "unreviewed, unreviewed, reviewed" and assert where the loop
# stopped.
#
# Exit codes:
#   0  all assertions passed
#   1  one or more assertions failed

set -uo pipefail

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/pr-review-status.sh"

[[ -f "$UNDER_TEST" ]] || { echo "test: $UNDER_TEST not found" >&2; exit 1; }

failures=0
SANDBOX=""
cleanup() { [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"; }
trap cleanup EXIT

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
# Nothing at all on stderr. `-q` documents "no progress lines on
# stderr", so under it stderr is a CONTRACT, not merely tidy.
assert_err_empty() {
    if [[ -n "$RUN_ERR" ]]; then
        echo "  ✗ $1 — stderr was not empty:"
        printf '%s\n' "$RUN_ERR" | sed 's/^/      /'
        failures=$(( failures + 1 ))
    else
        echo "  ✓ $1"
    fi
}

assert_lacks() {
    if [[ "$RUN_OUT" != *"$2"* ]]; then pass "$1"
    else fail "$1 — output unexpectedly contained '$2'" "$RUN_OUT"; fi
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
    echo "      the assertion helpers here are assert_rc / assert_contains / assert_lacks" >&2
    return 127
}

SANDBOX="$(mktemp -d)"
mkdir -p "$SANDBOX/bin" "$SANDBOX/state"

# ── The gh mock ──────────────────────────────────────────────────────
#
# state/polls holds one line per scripted `gh pr view` call:
#   <state>:<headRefOid>:<reviewRequestCount>
# state/reviews holds the reviews array served for EVERY call, as
#   <login>,<commit_id>,<submitted_at> per line.
# The line consumed is tracked in state/n so a poll loop advances.
cat > "$SANDBOX/bin/gh" <<'MOCK'
#!/usr/bin/env bash
S="$GH_MOCK_STATE"

case "$1 ${2:-}" in
  "pr view")
    if [[ "$*" == *"nameWithOwner"* ]]; then
      echo '{"nameWithOwner":"o/r"}'; exit 0
    fi
    n=$(cat "$S/n" 2>/dev/null || echo 0)
    line=$(sed -n "$((n+1))p" "$S/polls")
    [[ -z "$line" ]] && line=$(tail -1 "$S/polls")
    echo $((n+1)) > "$S/n"
    IFS=: read -r st head req <<<"$line"
    [[ "$st" == "FAIL" ]] && exit 1
    # reviewRequests carry a login, because a decline answers only the
    # reviewer who made it. A bare count still works: `<state>:<head>:<n>`
    # fills n slots with the fixture's configured reviewer, `:<n>@login`
    # fills them with that account instead, and `:<n>@a+b` lists a and b
    # — one request each, n ignored — for the cases where WHO is still
    # pending is the whole question.
    who="${req##*@}"; n="${req%%@*}"
    [[ "$who" == "$req" ]] && who="reviewer[bot]"
    if [[ "$who" == *+* ]]; then
      printf '{"state":"%s","mergeStateStatus":"CLEAN","headRefOid":"%s","headRefName":%s,"author":{"login":"me"},"isDraft":false,"reviewRequests":%s}\n' \
        "$st" "$head" \
        "$(jq -n --arg b "$(cat "$S/headref" 2>/dev/null || echo mine/branch)" '$b')" \
        "$(jq -Rn --arg w "$who" '$w | split("+") | map({__typename:"User", login:.})')"
      exit 0
    fi
    # The ref is JSON-ESCAPED, not spliced bare: git permits a `"` in a
    # branch name, and a mock that emits invalid JSON for one would fail
    # the case for its own reason rather than the script's.
    printf '{"state":"%s","mergeStateStatus":"CLEAN","headRefOid":"%s","headRefName":%s,"author":{"login":"me"},"isDraft":false,"reviewRequests":%s}\n' \
      "$st" "$head" "$(jq -n --arg b "$(cat "$S/headref" 2>/dev/null || echo mine/branch)" '$b')" "$(python3 -c "
import json,sys
print(json.dumps([{'__typename':'User','login':sys.argv[1]}]*int(sys.argv[2])))" "$who" "$n")"
    exit 0 ;;
  "repo view")
    echo '{"nameWithOwner":"o/r"}'; exit 0 ;;
  "pr checks")
    echo "some / Check	pass	1s"; exit 0 ;;
  "api graphql")
    # REVIEW_REQUESTED_EVENT timestamps, so the refusal override has the
    # ordering the request COUNT cannot supply. state/formaldate empty
    # means the lookup found nothing.
    if [[ "$*" == *REVIEW_REQUESTED_EVENT* ]]; then
      # RAW JSON ONLY. This mock previously accepted `--argjson` and ran
      # the caller's filter itself — a flag `gh api` does not have. The
      # real command failed with "unknown flag" on every invocation while
      # the suite stayed green, because the mock implemented an interface
      # that does not exist. A mock may only serve what the real thing
      # serves; the caller's jq is the caller's business.
      #
      # state/formaldate holds "<date>" or "<date>,<login>" per line
      # (login defaults to the fixture's configured reviewer).
      raw="$(cat "$S/formaldate" 2>/dev/null || true)"
      printf '{"data":{"repository":{"pullRequest":{"timelineItems":{"nodes":['
      first=1
      while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        d="${line%%,*}"; who="${line#*,}"
        [[ "$who" == "$line" ]] && who="reviewer[bot]"
        (( first )) || printf ','
        first=0
        printf '{"createdAt":"%s","requestedReviewer":{"login":"%s"}}' "$d" "$who"
      done <<< "$raw"
      # Five objects opened above, five closed here.
      printf ']}}}}}\n'
      exit 0
    fi
    # The unresolved-threads lookup (already filtered: the script passes
    # --jq). state/threads_fail makes it FAIL, which must read as unknown.
    if [[ "$*" == *reviewThreads* ]]; then
      [[ -f "$S/threads_fail" ]] && exit 1
      [[ -s "$S/threads" ]] && { cat "$S/threads"; exit 0; }
    fi
    echo '[]'; exit 0 ;;
esac

# gh api [--paginate] repos/o/r/pulls/N/reviews
#
# Matched across ALL arguments, not positionally: the script passes
# --paginate, which shifts the URL out of $2 and made a positional match
# fall through to the catch-all `exit 0` — an empty body that reads as
# zero reviews, i.e. the suite would have gone green on a script that
# fetched nothing at all.
if [[ "$1" == "api" && "$*" == *"/reviews"* ]]; then
  # A lookup that FAILS, for the fail-closed case. Distinct from a lookup
  # that succeeds with no reviews, which is an empty state/reviews file.
  [[ -f "$S/reviews_fail" ]] && exit 1
  # ...and one that fails only AFTER a given poll, so a case can script
  # "probe 1 read everything, probe 2 died halfway". The pr view call of
  # this same probe has already advanced state/n, so n IS the poll number.
  if [[ -f "$S/reviews_fail_after" ]]; then
    (( $(cat "$S/n" 2>/dev/null || echo 0) > $(cat "$S/reviews_fail_after") )) && exit 1
  fi
  {
    printf '['
    first=1
    # A fifth field is the reviewer's author_association; an account
    # other than the author defaults to MEMBER (a trusted reviewer), the
    # author to OWNER.
    while IFS=, read -r login commit at kind assoc; do
      [[ -n "$assoc" ]] || { [[ "$login" == me ]] && assoc=OWNER || assoc=MEMBER; }
      [[ -z "$login" ]] && continue
      (( first )) || printf ','
      first=0
      # A 4th CSV field of MARKED gives the review the review class's
      # marker as its body. A SENTINEL rather than a literal body,
      # because the body is the thing under test and embedding it in a
      # comma-separated fixture would let a stray comma silently change
      # what the case asserts.
      body=""
      case "$kind" in
        MARKED) body='<!-- agent-fabric-review v1 -->\nfindings…' ;;
        # The fabric's own earlier marker, from when the review class was
        # called a substitute: built in, counts with nothing configured.
        BUILTIN) body='<!-- agent-fabric-substitute-review v1 -->\nfindings…' ;;
        # A project's earlier marker, named by its forwarder through
        # AGENT_FABRIC_LEGACY_REVIEW_MARKERS: counts. One nobody named: not.
        LEGACY) body='<!-- legacy-project-review v1 -->\nfindings…' ;;
        STRANGER) body='<!-- somebody-else-review v1 -->\nfindings…' ;;
        # The marker QUOTED mid-body, not leading it. A review discussing
        # the marker — reviewing this very mechanism does it — must not
        # be counted as a blind review.
        QUOTES) body='I think the marker <!-- agent-fabric-review v1 --> should move.' ;;
      esac
      printf '{"user":{"login":"%s"},"author_association":"%s","state":"COMMENTED","commit_id":"%s","submitted_at":"%s","body":"%s"}' \
        "$login" "$assoc" "$commit" "$at" "$body"
    done < "$S/reviews"
    printf ']\n'
  }
  exit 0
fi

# gh api repos/o/r/commits/<sha>  — when the head commit was pushed.
# gh api repos/o/r/commits/<sha>/check-suites — created BY the push, so
# its timestamp tracks the ref update rather than the commit metadata.
# state/suitedate empty means "no suite ran", which exercises the
# committer-date fallback.
if [[ "$1" == "api" && "$*" == *"/check-suites"* ]]; then
  # Serves the RAW envelope and lets the caller's --jq do the work, so
  # the PR-scoping filter is actually exercised. A mock that pre-answers
  # the question cannot test the query that asks it.
  #
  # Every suite carries a head_branch, because the real ones do and the
  # filter reads it. state/headref is this PR's ref.
  #
  # state/suitedate  — this PR's own suite: this ref, this PR.
  # state/foreignsuitedate — an OLDER suite for the same sha on another
  #   ref, belonging to another PR. Neither term matches.
  # state/claimsuitedate — a LATER suite for the same sha on another
  #   ref that nonetheless CLAIMS this PR number. How GitHub populates
  #   `pull_requests` is undocumented, so a sha-only match rule would
  #   produce exactly this; the ref term is what has to reject it.
  # state/unownedsuitedate — a LATER suite on THIS ref that belongs to
  #   no PR: something other than a push to the head raised it. The ref
  #   term cannot reject that one; the PR term is what has to.
  # state/latersuitedate — a LATER suite on THIS ref, owned by THIS pr,
  #   raised by something that never moved the ref: a manual
  #   workflow_dispatch, a schedule, a re-run, or a close/reopen. Both
  #   the ref and the PR term admit it, and its event name cannot tell
  #   it from a push (`reopened` reports as `pull_request`), so ORDER is
  #   what rejects it.
  ref="$(jq -n --arg b "$(cat "$S/headref" 2>/dev/null || echo mine/branch)" '$b')"
  sd="$(cat "$S/suitedate" 2>/dev/null || true)"
  fd="$(cat "$S/foreignsuitedate" 2>/dev/null || true)"
  cd_="$(cat "$S/claimsuitedate" 2>/dev/null || true)"
  ud="$(cat "$S/unownedsuitedate" 2>/dev/null || true)"
  ld="$(cat "$S/latersuitedate" 2>/dev/null || true)"
  {
    printf '{"check_suites":['
    first=1
    if [[ -n "$fd" ]]; then
      printf '{"id":1,"created_at":"%s","head_branch":"someone/else","pull_requests":[{"number":999}]}' "$fd"; first=0
    fi
    if [[ -n "$cd_" ]]; then
      (( first )) || printf ','
      printf '{"id":2,"created_at":"%s","head_branch":"someone/else","pull_requests":[{"number":77}]}' "$cd_"; first=0
    fi
    if [[ -n "$ud" ]]; then
      (( first )) || printf ','
      printf '{"id":3,"created_at":"%s","head_branch":%s,"pull_requests":[]}' "$ud" "$ref"; first=0
    fi
    if [[ -n "$sd" ]]; then
      (( first )) || printf ','
      printf '{"id":4,"created_at":"%s","head_branch":%s,"pull_requests":[{"number":77}]}' "$sd" "$ref"; first=0
    fi
    if [[ -n "$ld" ]]; then
      (( first )) || printf ','
      printf '{"id":5,"created_at":"%s","head_branch":%s,"pull_requests":[{"number":77}]}' "$ld" "$ref"; first=0
    fi
    # An EARLIER suite for this same pr on this same ref: the sha was
    # this pr's head before, was replaced, and came back.
    ed="$(cat "$S/earliersuitedate" 2>/dev/null || true)"
    if [[ -n "$ed" ]]; then
      (( first )) || printf ','
      printf '{"id":6,"created_at":"%s","head_branch":%s,"pull_requests":[{"number":77}]}' "$ed" "$ref"
    fi
    printf ']}\n'
  } > "$S/.suites.json"
  jqf=""
  prev=""
  for a in "$@"; do [[ "$prev" == "--jq" ]] && jqf="$a"; prev="$a"; done
  if [[ -n "$jqf" ]]; then jq -r "$jqf" "$S/.suites.json"; else cat "$S/.suites.json"; fi
  # A SECOND PAGE. `gh api --paginate` applies --jq to each page and
  # prints one result per page, so a paginated response reaches the
  # caller as several lines — this emits page two's candidate as its own
  # line, and dates it EARLIER than page one's so that taking page one
  # (or taking the last line) picks the wrong one.
  p2="$(cat "$S/page2suitedate" 2>/dev/null || true)"
  if [[ -n "$p2" && "$*" == *--paginate* ]]; then printf '%s\n' "$p2"; fi
  exit 0
fi

if [[ "$1" == "api" && "$*" == *"/commits/"* ]]; then
  # Honours --jq, because the caller passes one and reads the EXTRACTED
  # value. A mock that dumps the envelope regardless hands back a JSON
  # blob where a date was expected, and the comparison silently goes the
  # wrong way rather than failing.
  d="$(cat "$S/headdate" 2>/dev/null || echo 2026-08-10T00:00:00Z)"
  if [[ "$*" == *"--jq"* ]]; then printf '%s\n' "$d"
  else printf '{"commit":{"committer":{"date":"%s"}}}\n' "$d"; fi
  exit 0
fi

# gh api [--paginate] repos/o/r/issues/N/comments
#
# The verdict comments a project's CONFIGURED automated reviewer leaves
# instead of a review object when it finds nothing. state/verdicts holds
# <login>,<sha> per line; empty by default, so every case written before
# verdict comments existed keeps its exact meaning. The wording is the
# fixture's, matched by the regexes run() configures below — nothing in
# the script under test knows these phrases.
if [[ "$1" == "api" && "$*" == *"/comments"* ]]; then
  [[ -f "$S/verdicts_fail" ]] && exit 1
  {
    printf '['
    first=1
    # <login>,<sha>[,<created_at>]. A sha of REFUSED serves the
    # reviewer's decline wording instead of a verdict.
    while IFS=, read -r login sha at; do
      [[ -z "$login" ]] && continue
      (( first )) || printf ','
      first=0
      [[ -z "$at" ]] && at="2026-08-25T10:00:00Z"
      if [[ "$sha" == "REQUEST" ]]; then
        printf '{"user":{"login":"%s"},"created_at":"%s","body":"@reviewer review\\n\\nplease look again"}' \
          "$login" "$at"
      elif [[ "$sha" == "REFUSED" ]]; then
        printf '{"user":{"login":"%s"},"created_at":"%s","body":"Usage limit reached for reviews; none will run."}' \
          "$login" "$at"
      elif [[ "$sha" == "REFUSED_DASH" ]]; then
        printf '{"user":{"login":"%s"},"created_at":"%s","body":"\\r\\nCannot review this PR — usage limit reached for reviews.\\r\\nTry later."}' \
          "$login" "$at"
      elif [[ "$sha" == "NOENV" ]]; then
        printf '{"user":{"login":"%s"},"created_at":"%s","body":"No environment for this repo; none will run."}' \
          "$login" "$at"
      else
        printf '{"user":{"login":"%s"},"created_at":"%s","body":"### Review\\n\\n**Reviewed commit:** `%s`\\n"}' \
          "$login" "$at" "$sha"
      fi
    done < "$S/verdicts" 2>/dev/null
    printf ']\n'
  }
  exit 0
fi
exit 0
MOCK
chmod +x "$SANDBOX/bin/gh"

# NOTE the trailing newline on both writes. `read` returns false on a
# final line that lacks one, so `printf '%s'` here silently dropped the
# last review — three became two, one became none, and every exit-5 case
# degraded into an infinite wait. The bug was in this harness, not the
# script, and it presented as the script being broken.
#
# Every run is bounded. A regression in the "exits immediately" cases
# would otherwise sleep for the full --wait and hang the suite; 20s is
# far above any real path here (the mock never blocks) and far below the
# waits under test.
# REVIEWS_FAIL=1 run ... makes the reviews lookup FAIL for that case (a
# rate limit, a permission gap, a transient 5xx) as distinct from
# succeeding with no reviews. Cleared every run so it cannot leak.
run() {
    : > "$SANDBOX/state/n"
    rm -f "$SANDBOX/state/reviews_fail" "$SANDBOX/state/reviews_fail_after" \
          "$SANDBOX/state/verdicts_fail" "$SANDBOX/state/threads_fail"
    [[ "${THREADS_FAIL:-0}" == 1 ]] && touch "$SANDBOX/state/threads_fail"
    printf '%s\n' "${THREADS:-}" > "$SANDBOX/state/threads"
    [[ "${REVIEWS_FAIL:-0}" == 1 ]] && touch "$SANDBOX/state/reviews_fail"
    [[ "${VERDICTS_FAIL:-0}" == 1 ]] && touch "$SANDBOX/state/verdicts_fail"
    [[ -n "${REVIEWS_FAIL_AFTER:-}" ]] \
        && printf '%s\n' "$REVIEWS_FAIL_AFTER" > "$SANDBOX/state/reviews_fail_after"
    printf '%s\n' "$1" > "$SANDBOX/state/polls"
    printf '%s\n' "$2" > "$SANDBOX/state/reviews"
    # EMPTY BY DEFAULT. Every case predating verdict comments must keep
    # its exact meaning, so a run that does not opt in serves none.
    printf '%s\n' "${VERDICTS:-}" > "$SANDBOX/state/verdicts"
    printf '%s\n' "${HEAD_DATE:-2026-08-10T00:00:00Z}" > "$SANDBOX/state/headdate"
    # Default: the head arrived when its commit says. A case that sets
    # SUITE_DATE separates the two, which is the whole point.
    printf '%s\n' "${SUITE_DATE-${HEAD_DATE:-2026-08-10T00:00:00Z}}" > "$SANDBOX/state/suitedate"
    printf '%s\n' "${FORMAL_DATE:-}" > "$SANDBOX/state/formaldate"
    printf '%s\n' "${HEAD_REF:-mine/branch}" > "$SANDBOX/state/headref"
    printf '%s\n' "${FOREIGN_SUITE_DATE:-}" > "$SANDBOX/state/foreignsuitedate"
    printf '%s\n' "${CLAIMING_SUITE_DATE:-}" > "$SANDBOX/state/claimsuitedate"
    printf '%s\n' "${UNOWNED_SUITE_DATE:-}" > "$SANDBOX/state/unownedsuitedate"
    printf '%s\n' "${EARLIER_SUITE_DATE:-}" > "$SANDBOX/state/earliersuitedate"
    printf '%s\n' "${LATER_SUITE_DATE:-}" > "$SANDBOX/state/latersuitedate"
    printf '%s\n' "${PAGE2_SUITE_DATE:-}" > "$SANDBOX/state/page2suitedate"
    shift 2
    # Passed through EXPLICITLY. `run` builds its own env prefix, so a
    # `VAR=… run …` assignment is not reliably visible to the script it
    # spawns; a case asserting on the override would then be asserting
    # on the default.
    # STDOUT AND STDERR ARE CAPTURED SEPARATELY, then concatenated into
    # RUN_OUT so every existing `assert_contains`/`assert_lacks` keeps
    # its exact meaning (they ask what appeared, never in what order).
    # RUN_ERR is what makes a stderr-only regression assertable at all: a
    # stray diagnostic printf shipped to main because the suite folded
    # stderr into one stream and no case ever asked what was in it.
    local __o __e
    __o="$(mktemp)"; __e="$(mktemp)"
    # THE FIXTURE CONFIGURES AN AUTOMATED REVIEWER; the script ships with
    # none (empty list, empty patterns — the review class is the review).
    # `${VAR-default}`, not `:-`: an override set to the EMPTY string
    # reaches the script as empty and exercises its own default, which is
    # how the no-reviewer cases are written.
    PATH="$SANDBOX/bin:$PATH" GH_MOCK_STATE="$SANDBOX/state" \
        AGENT_FABRIC_VERDICT_AUTHORS="${VERDICT_AUTHORS_OVERRIDE-[\"reviewer[bot]\"]}" \
        AGENT_FABRIC_REVIEWER_REFUSAL_RE="${REFUSAL_RE_OVERRIDE-usage limit reached|no environment for this repo}" \
        AGENT_FABRIC_REVIEW_REQUEST_RE="${REQUEST_RE_OVERRIDE-@reviewer[[:space:]]+review}" \
        AGENT_FABRIC_REVIEW_POSTERS="${REVIEW_POSTERS_OVERRIDE-[]}" \
        timeout 20 bash "$UNDER_TEST" 77 o/r "$@" >"$__o" 2>"$__e"
    RUN_RC=$?
    RUN_ERR="$(cat "$__e")"
    RUN_OUT="$(cat "$__o" "$__e")"
    rm -f "$__o" "$__e"
    (( RUN_RC == 124 )) && RUN_OUT="TIMED OUT — the run did not return"$'\n'"$RUN_OUT"
}

# Same as `run`, plus verdict comments as a third argument. A separate
# helper rather than a fourth positional on `run`: every existing call
# site passes two, and threading an optional third through them would
# touch every case to add one. `local VERDICTS` is visible to `run`
# under bash's dynamic scoping, and unset again the moment this returns
# — so it cannot leak into the next case.
run_with_verdicts() {
    local VERDICTS="$3" polls="$1" reviews="$2"
    shift 3
    run "$polls" "$reviews" "$@"
}

echo "pr-review-status.sh — the head-reviewed verdict"

run "OPEN:abc123:0" "bot,abc123,2026-08-07T10:00:00Z"
assert_rc "independent review AT the head exits 0" 0
assert_contains "  and says so" "head reviewed?      : yes"
assert_contains "  naming the review" "yes — an independent review (bot, abc123, 2026-08-07T10:00:00Z)"

run "OPEN:abc123:0" ""
assert_rc "no reviews at all exits 1" 1

# The PR #363 case: three self-replies are REVIEW objects authored by
# the PR author. They must not read as coverage.
run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z
me,abc123,2026-08-07T10:01:00Z
me,abc123,2026-08-07T10:02:00Z"
assert_rc "self-authored reviews are NOT coverage" 1
assert_contains "  counted as self" "self reviews        : 3"
assert_contains "  and not as independent" "independent reviews : 0"

# The review class's BLIND review is coverage, and authorship cannot see
# it. Every session pushes as the same account, so the review posted by
# the session that owns the PR is authored by the PR author and used to
# land in the "self reviews … not coverage" bucket — once reported as 0
# reviews on 29 PRs, five of which had a real blind review sitting on
# them. The marker is what separates the two, and it is an exact string
# rather than prose: three sessions wrote three different sentences, and
# a coverage claim guessed from prose is worse than no claim.
run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,MARKED"
assert_rc       "a blind review at the head IS coverage" 0
assert_contains "a marked review counts as a blind review" "blind reviews       : 1"
assert_contains "  and NOT as a self review"               "self reviews        : 0"
assert_contains "  and says what it is" "the review class — coverage"
# The verdict line names its evidence: agents trim this report with
# `tail`, and the evidence above it was cut off before a permission check
# read the trimmed report as no review (a managed project's PR).
assert_contains "  and the head line names it, trimmed or not" \
    "head reviewed?      : yes — the review class's blind review of abc123, 2026-08-07T10:00:00Z"

# The marker the review class posted under before it was THE review is
# built in: a review from that time keeps counting with nothing set.
run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,BUILTIN"
assert_rc       "the fabric's earlier marker still counts, unconfigured" 0
assert_contains "  as a blind review" "blind reviews       : 1"

# THE INVERSE RISK, and the worse one. `contains` counted any review whose
# body merely QUOTED the marker, and subtracted it from `self` at the same
# time — a false "this was reviewed", on the one line whose whole job is
# answering that question.
run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,QUOTES"
assert_rc       "a review that only QUOTES the marker is not coverage" 1
assert_contains "  not counted as a blind review" "blind reviews       : 0"
assert_contains "  still counted as a self review" "self reviews        : 1"

# A LEGACY marker — the one a project posted under before the tool became
# the fabric's — counts only when that project's forwarder names it in
# AGENT_FABRIC_LEGACY_REVIEW_MARKERS; a marker nobody named is not coverage.
AGENT_FABRIC_LEGACY_REVIEW_MARKERS='<!-- legacy-project-review v1 -->' \
run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,LEGACY"
assert_rc       "a legacy marker the forwarder names IS coverage" 0
assert_contains "  counted as a blind review" "blind reviews       : 1"
run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,LEGACY"
assert_rc       "the same marker, not named by the environment: not coverage" 1
assert_contains "  counted as a self review" "self reviews        : 1"
AGENT_FABRIC_LEGACY_REVIEW_MARKERS='<!-- legacy-project-review v1 -->' \
run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,STRANGER"
assert_rc       "a marker nobody named is not coverage even with a legacy one set" 1

# A marked review from ANOTHER account is neither a blind review nor an
# independent reviewer. Gating the marker test on authorship once let it
# through as independent coverage; counting it as blind let any account
# on a public repository cover a head by pasting the published marker
# (a blind review of a managed project, 2026-09-25). It is reported by
# login, and it is not coverage.
run "OPEN:abc123:0" "somebodyelse,abc123,2026-08-07T10:00:00Z,MARKED"
assert_rc       "a marked review from another account is NOT coverage" 1
assert_contains "  not a blind review"                        "blind reviews       : 0"
assert_contains "  and NOT an independent review"             "independent reviews : 0"
assert_contains "  reported under its own line"               "marked, other login : 1"
assert_contains "  with its login"                            "- somebodyelse  commit=abc123"
REVIEW_POSTERS_OVERRIDE='["somebodyelse"]' \
run "OPEN:abc123:0" "somebodyelse,abc123,2026-08-07T10:00:00Z,MARKED"
assert_rc       "a poster named in AGENT_FABRIC_REVIEW_POSTERS IS coverage" 0
assert_contains "  as a blind review, login shown"            "- somebodyelse  commit=abc123"
run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,MARKED"
assert_contains "the author's own marked review is blind, login shown" "- me  commit=abc123"

# AN INDEPENDENT REVIEWER IS ONE THE REPOSITORY TRUSTS. On a public
# repository a stranger's UNMARKED review counted as independent coverage,
# which the poster binding of marked reviews did not close (the review of
# #41, 2026-09-26).
run "OPEN:abc123:0" "stranger,abc123,2026-08-07T10:00:00Z,,NONE"
assert_rc       "a stranger's review is NOT coverage" 1
assert_contains "  not an independent review"                 "independent reviews : 0"
assert_contains "  listed as not trusted, with its association" "- stranger  NONE  commit=abc123"
run "OPEN:abc123:0" "helper,abc123,2026-08-07T10:00:00Z,,COLLABORATOR"
assert_rc       "a collaborator's review IS coverage" 0
# A configured reviewer (an App, which GitHub lists as NONE) is trusted by
# name: AGENT_FABRIC_VERDICT_AUTHORS already says the project trusts it.
run "OPEN:abc123:0" "reviewer[bot],abc123,2026-08-07T10:00:00Z,,NONE"
assert_rc       "a configured reviewer's review IS coverage whatever its association" 0

# A FAILED THREADS LOOKUP IS "unknown", never 0: a caller that arms on
# zero unresolved threads read a query error as a clean PR.
THREADS_FAIL=1 run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,MARKED"
assert_contains "a failed threads lookup reads unknown" "unresolved threads  : unknown"
THREADS='[{"isResolved":false,"isOutdated":false,"path":"a.sh"}]' run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,MARKED"
assert_contains "a real unresolved thread is counted" "unresolved threads  : 1"

# THE --json CONTRACT: the same answer as fields, the same exit code.
THREADS_FAIL=1 run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,MARKED
somebodyelse,abc123,2026-08-07T10:01:00Z,MARKED" --json
assert_rc "--json keeps the exit code" 0
if jq -e '.head_reviewed == "yes" and .blind.count == 1 and .blind.rows[0].login == "me"
          and .blind.rows[0].commit_sha8 == "abc123" and .marked_by_others.count == 1
          and .unresolved_threads == null and .independent.count == 0 and (.checks.pass | type) == "number"' \
     <<<"$(cat <<<"$RUN_OUT" | sed -n '/^{/,/^}/p')" >/dev/null 2>&1; then pass "--json carries the buckets, the login, and null for an unknown thread count"
else fail "--json shape" "$RUN_OUT"; fi
THREADS='[]' run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,MARKED" --json -q
if [[ "$(jq -r '.unresolved_threads' <<<"$RUN_OUT" 2>/dev/null)" == 0 ]]; then pass "--json: a successful lookup with none is 0, not null"
else fail "--json zero threads" "$RUN_OUT"; fi

# The two must not blur: an unmarked self-authored review is still a
# thread reply, and marking must not turn every same-account review into
# coverage.
run "OPEN:abc123:0" "me,abc123,2026-08-07T10:00:00Z,MARKED
me,abc123,2026-08-07T10:01:00Z
me,abc123,2026-08-07T10:02:00Z"
assert_contains "marked and unmarked are separated (blind)" "blind reviews       : 1"
assert_contains "marked and unmarked are separated (self)"  "self reviews        : 2"

# Reviewed at an EARLIER commit, with a review still requested: a review
# is pending, so this is "not yet" (1), not "never coming" (5).
run "OPEN:newhead:1" "bot,oldhead,2026-08-07T10:00:00Z"
assert_rc "stale review WITH a request pending is 'not yet'" 1
assert_contains "  flags the earlier commit" "an EARLIER commit"

echo
echo "pr-review-status.sh — no review is coming (exit 5)"

run "OPEN:newhead:0" "bot,oldhead,2026-08-07T10:00:00Z"
assert_rc "reviewed then pushed, nothing requested, exits 5" 5
assert_contains "  names the cause" "NO REVIEW COMING"
# Under --json stdout stays ONE object on this path too, the cause a field
# rather than a prose line after it (the review of #41, 2026-09-26).
run "OPEN:newhead:0" "bot,oldhead,2026-08-07T10:00:00Z" --json -q
assert_rc "--json keeps exit 5" 5
# ONE object: -s slurps every value on stdout, so a prose line after the
# object fails the parse (the re-review of #41: a first-value read passed it).
if jq -e -s 'length == 1 and .[0].no_review_coming.cause == "head-moved"' <<<"$RUN_OUT" >/dev/null 2>&1; then pass "  stdout is one object, the cause in no_review_coming"
else fail "  --json exit-5 output" "$RUN_OUT"; fi

# The distinction that makes 5 worth having: a FRESH PR has had no
# review, and the one that owns it has yet to dispatch one — so it must
# NOT be 5.
run "OPEN:abc123:0" ""
assert_rc "a never-reviewed PR is 1, not 5" 1
assert_lacks "  and claims nothing about the cause" "NO REVIEW COMING"

echo
echo "pr-review-status.sh — waiting"

# Poll 1 unreviewed, poll 2 reviewed: the loop must keep going and win.
run "OPEN:abc123:1
OPEN:abc123:1" "" --wait 2 --interval 1 -q
# reviews are static in the mock, so instead assert the loop RAN:
assert_rc "wait expires with nothing and exits 1" 1

run "OPEN:abc123:1" "bot,abc123,2026-08-07T10:00:00Z" --wait 60 --interval 1 -q
assert_rc "wait returns immediately once the head is reviewed" 0

# Exit 5 must not sleep: --wait 3600 with a permanent state has to come
# back at once. If it ever regresses to waiting, this test hangs the
# suite rather than failing quietly — which is the correct alarm.
start=$SECONDS
run "OPEN:newhead:0" "bot,oldhead,2026-08-07T10:00:00Z" --wait 3600 --interval 1 -q
elapsed=$(( SECONDS - start ))
assert_rc "a permanent no-review state exits 5 under a long --wait" 5
if (( elapsed < 5 )); then pass "  and does not sleep first (${elapsed}s)"
else fail "  and does not sleep first" "took ${elapsed}s"; fi

# CLOSED-without-merge: nothing further will arrive, so stop waiting.
run "CLOSED:abc123:1" "" --wait 3600 --interval 1 -q
assert_rc "a CLOSED PR stops the wait and exits 1" 1

# --wait SHORTER than --interval used to answer once and exit on the
# spot: the loop only slept when a WHOLE interval still fitted before
# the deadline, so `--wait 4 --interval 60` waited zero seconds while
# reporting a 4-second wait. The nap is clamped to what is left, as
# wait-merged.sh has always done, so the deadline is the deadline.
start=$SECONDS
run "OPEN:abc123:1" "" --wait 4 --interval 60 -q
elapsed=$(( SECONDS - start ))
assert_rc "a --wait shorter than --interval still exits 1" 1
if (( elapsed >= 3 )); then pass "  and waits the requested time (${elapsed}s)"
else fail "  and waits the requested time" "returned after ${elapsed}s"; fi
if [[ "$(cat "$SANDBOX/state/n")" -ge 2 ]]; then pass "  polling again at the deadline"
else fail "  polling again at the deadline" "only $(cat "$SANDBOX/state/n") poll(s)"; fi

echo
echo "pr-review-status.sh — invocation"

RUN_OUT="$(PATH="$SANDBOX/bin:$PATH" GH_MOCK_STATE="$SANDBOX/state" \
    bash "$UNDER_TEST" 2>&1)"; RUN_RC=$?
assert_rc "no PR number exits 2" 2

RUN_OUT="$(PATH="$SANDBOX/bin:$PATH" GH_MOCK_STATE="$SANDBOX/state" \
    bash "$UNDER_TEST" 77 o/r --interval 0 2>&1)"; RUN_RC=$?
assert_rc "zero --interval exits 2" 2

# The duration table, asserted here alone: this suite is what stops
# as_seconds accepting something a caller did not mean.
for bad in "" "10sm" "m" "-1" "1x" "10 m"; do
    RUN_OUT="$(PATH="$SANDBOX/bin:$PATH" GH_MOCK_STATE="$SANDBOX/state" \
        bash "$UNDER_TEST" 77 o/r --wait "$bad" 2>&1)"; RUN_RC=$?
    assert_rc "rejects --wait '$bad'" 2
done

# A bare number is seconds; a unit converts. --wait 0 stays the one-shot,
# so a unit form that resolves to a real wait must NOT short-circuit: a
# reviewed head returns 0 immediately either way, which is what makes
# this assertable without sleeping.
run "OPEN:abc123:0" "bot,abc123,2026-08-07T10:00:00Z" --wait 5m --interval 1s -q
assert_rc "accepts --wait 5m --interval 1s" 0
run "OPEN:abc123:0" "bot,abc123,2026-08-07T10:00:00Z" --wait 2h --interval 30s -q
assert_rc "accepts --wait 2h --interval 30s" 0
run "OPEN:abc123:0" "bot,abc123,2026-08-07T10:00:00Z" --wait 300 --interval 1 -q
assert_rc "  and bare seconds still work" 0

RUN_OUT="$(PATH="$SANDBOX/bin:$PATH" GH_MOCK_STATE="$SANDBOX/state" \
    bash "$UNDER_TEST" 77 o/r --nope 2>&1)"; RUN_RC=$?
assert_rc "unknown option exits 2" 2

RUN_OUT="$(PATH="$SANDBOX/bin:$PATH" GH_MOCK_STATE="$SANDBOX/state" \
    bash "$UNDER_TEST" --help 2>&1)"; RUN_RC=$?
assert_rc "--help exits 0" 0
assert_contains "  and documents exit 5" "no review is COMING"

# Three consecutive unreadable polls is unreadable; fewer is a blip.
run "FAIL
FAIL
FAIL" ""
assert_rc "three failed lookups exit 2" 2

echo
echo "pr-review-status.sh — an unreadable reviews lookup is not 'no reviews'"

# The dangerous shape: PR metadata reads fine, the REVIEWS call fails.
# Converting that to `[]` answers "nobody reviewed this" — the confident
# wrong answer for the one question this script exists to answer. It must
# reach the exit-2 unreadable contract instead.
REVIEWS_FAIL=1 run "OPEN:abc123:0" "" --wait 10 --interval 1 -q
assert_rc "a failing reviews lookup exits 2, not 1" 2
assert_lacks "  and renders no verdict from data it never had" "head reviewed?"

echo
echo "pr-review-status.sh — coverage is ANY review at the head"

# A review opened before the last push but SUBMITTED after a fresh one is
# newer by timestamp and older by commit. Picking the newest therefore
# lets the stale one mask real coverage that is right there.
run "OPEN:head1:0" "reviewer-a,head1,2026-08-12T10:00:00Z
reviewer-b,oldsha,2026-08-12T11:00:00Z"
assert_rc "a stale review submitted LAST cannot mask head coverage" 0
assert_contains "  head reads reviewed" "head reviewed?      : yes"

# A partial probe must not be mistaken for readable data. Poll 1 reads
# everything, poll 2 overwrites head and then dies on reviews; without
# resetting the completeness flag the report would pair the NEW head with
# poll 1's review data and present it as authoritative.
# THE NUMBERS ARE LOAD-BEARING IN BOTH DIRECTIONS, and were at zero
# margin until 2026-08-25.
#
# This case must reach the FALL-OUT path — wait expired, probe
# incomplete — because that is where probe_ok decides between rendering
# stale data (exit 1) and refusing (exit 2). The other route to exit 2,
# three consecutive failures, would pass even with the reset deleted, so
# a wait long enough to reach it makes this assertion vacuous.
#
# Fall-out therefore requires the wait to expire BEFORE three failures
# accumulate, i.e. wait < 3 x interval. Within that ceiling the wait
# must still comfortably fit two probes — and `--wait 2 --interval 1`
# left none: measured at 2s of a 2s budget once the verdict-comment and
# head-date lookups were added, so the first probe alone could consume
# the window on a loaded runner and flip the result to exit 1. A red
# required check here blocks the merge queue for every session.
#
# 4 and 3 keep the fall-out path (two failures, not three) with roughly
# four seconds of headroom for the first probe instead of none.
REVIEWS_FAIL_AFTER=1 run "OPEN:sha-one:0
OPEN:sha-two:0" "" --wait 4 --interval 3 -q
assert_rc "a probe that dies halfway does not render stale data" 2

echo "pr-review-status.sh — a merged pr is never told that no review is coming"

# Review lands on MERGED prs routinely — that is why a post-merge sweep
# exists, and a review asked on a merged pr has been acknowledged in
# 40 seconds. Firing exit 5 on one sends the caller off to request a
# review instead of awaiting the sweep that was about to deliver it, and
# contradicts the merged-pr exception in the same loop.
run "MERGED:newsha:0" "reviewer-a,oldsha1,2026-08-12T10:00:00Z"
if [[ "$RUN_RC" != "5" ]]; then
    pass "a merged pr with a stale review does not claim exit 5"
else
    fail "a merged pr must not claim no review is coming" "$RUN_OUT"
fi

# The same input on an OPEN pr still MUST exit 5 — the state gate must
# narrow the case, not delete it.
run "OPEN:newsha:0" "reviewer-a,oldsha1,2026-08-12T10:00:00Z"
assert_rc "an open pr past its newest review still exits 5" 5

echo "pr-review-status.sh — a configured reviewer's clean verdict is a review"
# An automated reviewer a project runs creates NO review object when it
# finds nothing; it posts an ordinary issue comment naming the commit.
# Counting review objects alone reported 'head reviewed? no' on exactly
# the prs that PASSED, and then exit 5 — "no review is coming" — about a
# review that had already happened and succeeded.
run_with_verdicts "OPEN:e7eb89d90cabc:0" "" "reviewer[bot],e7eb89d90c"
assert_rc       "a verdict comment at the head exits 0, with zero reviews" 0
assert_contains "  and says the head is reviewed" "head reviewed?      : yes"
assert_contains "  and shows where the coverage came from" "verdict comments    : 1"
assert_contains "  and names it as a clean review" "a clean review leaves no review object"

echo "pr-review-status.sh — the verdict's sha is READ, never assumed"
# A verdict comment can arrive after a push and still describe the
# commit before it, so 'a comment exists' is not coverage of the head.
run_with_verdicts "OPEN:bbbbbbbbbb:0" "" "reviewer[bot],aaaaaaaaaa"
assert_rc       "a verdict naming an older commit is not coverage" 5
assert_contains "  the verdict was READ, not ignored" "verdict comments    : 1"
assert_contains "  head stays unreviewed" "head reviewed?      : no"
# 5, not 1: a prior verdict is equally evidence that this pr is one the
# reviewer answers, so the head has ADVANCED past a review rather than
# never having had one. Waiting is futile; ask for another.
assert_contains "  and names the cause, as a stale review object would" "NO REVIEW COMING"

echo "pr-review-status.sh — abbreviated shas match by prefix, both ways"
# The body carries a 10-char sha and headRefOid is 40. Neither string is
# reliably the longer one, so the match cannot assume a direction.
run_with_verdicts "OPEN:2756062690aaaabbbbccccddddeeeeffff00001111:0" "" \
    "reviewer[bot],2756062690"
assert_rc "a short verdict sha covers a full head" 0

echo "pr-review-status.sh — only a RECOGNISED reviewer's verdict counts"
# "Not the pr author" is the right filter for a review OBJECT, which
# only a reviewer can create. It is the wrong filter for a comment,
# which anyone with access may leave: a negation would let a stranger
# mark a head reviewed by typing the phrase, satisfying the
# wait-for-review prerequisite without the reviewer ever having run.
run_with_verdicts "OPEN:cccccccccc:0" "" "some-stranger,cccccccccc"
assert_rc       "a stranger's forged verdict is NOT coverage" 1
assert_contains "  head stays unreviewed" "head reviewed?      : no"
assert_contains "  and none is counted"   "verdict comments    : 0"

echo "pr-review-status.sh — a self-authored verdict is not coverage"
# Same authorship rule the review objects already follow. `me` is the
# pr author in this mock.
run_with_verdicts "OPEN:dddddddddd:0" "" "me,dddddddddd"
assert_rc "the pr author cannot certify their own head" 1

echo "pr-review-status.sh — the allow-list is the project's, and empty by default"
# A project that runs an automated reviewer names it; the script assumes
# none, so with nothing configured no comment from anyone is a verdict.
VERDICT_AUTHORS_OVERRIDE='["some-other-bot"]' \
    run_with_verdicts "OPEN:eeeeeeeeee:0" "" "some-other-bot,eeeeeeeeee"
assert_rc "AGENT_FABRIC_VERDICT_AUTHORS names the reviewer" 0
# ...and the fixture's list is what applied elsewhere, so the previous
# assertion is about the override rather than about a list that accepts
# everybody.
run_with_verdicts "OPEN:eeeeeeeeee:0" "" "some-other-bot,eeeeeeeeee"
assert_rc "  an account the list does not name is not recognised" 1
# The script's OWN default is the empty list: the review class is the
# review, and no automated reviewer is presumed to exist.
VERDICT_AUTHORS_OVERRIDE= \
    run_with_verdicts "OPEN:eeeeeeeeee:0" "" "reviewer[bot],eeeeeeeeee"
assert_rc       "unconfigured, no comment is a verdict" 1
assert_contains "  and none is counted" "verdict comments    : 0"

echo "pr-review-status.sh — an unreadable comments lookup is not 'no verdicts'"
# Swallowing this failure would report a CLEAN review as no review,
# which is the entire defect the verdict fetch exists to fix.
VERDICTS_FAIL=1 run "OPEN:newsha:0" "reviewer-a,newsha,2026-08-12T10:00:00Z"
assert_rc           "a failing comments lookup exits 2, not 0" 2
assert_lacks        "  and renders no verdict from data it never had" "head reviewed?"

echo "pr-review-status.sh — a configured reviewer that DECLINED ends the wait"
# The reviewer says so in the same comment stream — a spent usage limit,
# a repository it cannot open. Neither is slowness, and nothing in the
# review objects says it — so a --wait sat out the full timeout and then
# reported "not yet" about something permanent. The wording that counts
# as a decline is the project's (AGENT_FABRIC_REVIEWER_REFUSAL_RE), and
# the reason reported is the reviewer's own first line.
run_with_verdicts "OPEN:ffffffffff:0" "" "reviewer[bot],REFUSED" \
    --wait 10m --interval 1s
assert_rc       "a decline exits 5 immediately, not after 10m" 5
assert_contains "  names the cause"          "the reviewer declined"
assert_contains "  and reports the decline"  "reviewer declined   :"
assert_contains "  and says WHICH decline it is, in the reviewer's words" "decline reason      : Usage limit reached for reviews"
assert_contains "  in the verdict line too" "the reviewer declined: Usage limit reached for reviews; none will run. (exit 5)"

echo "pr-review-status.sh — every configured phrase is the same verdict"
run_with_verdicts "OPEN:ffffffffff:0" "" "reviewer[bot],NOENV"
assert_rc "the second phrase exits 5 too" 5
assert_contains "  and names its reason" "decline reason      : No environment for this repo"

echo "pr-review-status.sh — with no refusal wording configured, nothing is a decline"
# The script's default. A decline is read only in a reviewer's own
# configured words — never from a "sounds negative" guess, and never
# when no reviewer is configured to begin with.
REFUSAL_RE_OVERRIDE= run_with_verdicts "OPEN:ffffffffff:0" "" "reviewer[bot],REFUSED"
assert_rc    "unconfigured, the comment is just a comment" 1
assert_lacks "  and nothing is reported as declined" "reviewer declined   :"

echo "pr-review-status.sh — a refusal a later review superseded is stale"
# Whatever made the reviewer decline passes. A decline from before the
# coverage that followed it must not end every later wait on this pr.
run_with_verdicts "OPEN:ffffffffff:0" "" \
    "reviewer[bot],REFUSED,2026-08-01T10:00:00Z
reviewer[bot],ffffffffff,2026-08-20T10:00:00Z"
assert_rc       "the later verdict wins" 0
assert_contains "  and the decline is marked superseded" "superseded by later coverage"

echo "pr-review-status.sh — a stranger cannot fake a refusal either"
# Same allow-list as the verdicts: otherwise anyone could end another
# session's wait by quoting the reviewer's wording.
run_with_verdicts "OPEN:ffffffffff:0" "" "some-stranger,REFUSED"
assert_rc    "a forged refusal is ignored" 1
assert_lacks "  and nothing is reported as declined" "reviewer declined   :"

echo "pr-review-status.sh — a configured review ask in flight is not 'nothing coming'"
# A project that asks its automated reviewer with a phrase
# (AGENT_FABRIC_REVIEW_REQUEST_RE) is NOT making a GitHub review request,
# so `requested` stays 0 and the stale-review branch fired "no review is
# coming" seconds after the ask — breaking the exact request-then-wait
# sequence such a project prescribes. Hit live: asked at 10:58:31, told
# nothing was coming at 10:59.
run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-01T10:00:00Z" \
    "someone,REQUEST,2026-08-20T10:00:00Z"
assert_rc       "reports 'not yet', not 'nothing is coming'" 1
assert_lacks    "  and claims nothing about the cause" "NO REVIEW COMING"
assert_contains "  and says the ask is in flight" "in flight"

echo "pr-review-status.sh — with no ask phrase configured, nothing is an ask"
# The script's default: the review class is dispatched, not asked for in
# a comment, so no comment holds a wait open.
REQUEST_RE_OVERRIDE= \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-01T10:00:00Z" \
    "someone,REQUEST,2026-08-20T10:00:00Z"
assert_rc    "unconfigured, the stale review is 'nothing is coming'" 5
assert_lacks "  and no ask is reported" "review asked        :"

echo "pr-review-status.sh — the review it asked for answers the ask"
# Decides nothing — head_reviewed wins the exit first — but a report
# saying "nothing has answered it yet" beside "head reviewed? yes" is
# false, and this file exists to stop confident wrong statements.
HEAD_DATE=2026-08-10T00:00:00Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer[bot],ffffffffff,2026-08-20T10:00:00Z" \
    "someone,REQUEST,2026-08-15T10:00:00Z"
assert_rc       "the head is covered" 0
assert_contains "  and the ask reads answered" "already answered"
assert_lacks    "  not in flight"              "in flight"

echo "pr-review-status.sh — head birth comes from the PUSH, not the commit date"
# ba20a29e on #501 was committed at 11:48:37 and pushed at 12:06 —
# eighteen minutes. An ask inside that gap is for the PREVIOUS head: the
# commit existed locally and the ref had not moved. Judging by commit
# metadata calls it current and makes exit 5 unreachable.
HEAD_DATE=2026-08-25T11:48:37Z SUITE_DATE=2026-08-25T12:06:07Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T11:55:00Z"
assert_rc       "an ask between commit and push is for the older head" 5
assert_contains "  names the cause" "NO REVIEW COMING"

echo "pr-review-status.sh — ...and an ask after the push is current"
HEAD_DATE=2026-08-25T11:48:37Z SUITE_DATE=2026-08-25T12:06:07Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T12:10:00Z"
assert_rc "an ask after the ref moved is in flight" 1

echo "pr-review-status.sh — a REBASED head still expires an older ask"
# The case the commit date cannot get right: a cherry-picked or rebased
# commit carries an ancient date, so every ask looks newer than it and
# exit 5 becomes unreachable. The push time is unaffected.
HEAD_DATE=2026-01-01T00:00:00Z SUITE_DATE=2026-08-25T12:06:07Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T11:55:00Z"
assert_rc "an ancient commit date does not make the ask current" 5

echo "pr-review-status.sh — a RESTORED sha keeps the ask in flight rather than expiring it"
# The one case the LATEST-suite rule existed for: a sha pushed,
# replaced, then restored by force-push leaves suites at both
# appearances, and dating from the first makes an ask sent while the
# intervening head was current read as newer than the head. That ask
# then stays in flight — a LONGER WAIT, which is the safe direction and
# the trade this script makes everywhere else. Dating from the latest
# instead bought exit 5 here and paid for it with a false exit 5 on
# every dispatch, schedule, re-run and reopen. No pr in this repo has
# ever been force-pushed; §Always forbids it without an explicit ask.
EARLIER_SUITE_DATE=2026-08-25T09:00:00Z SUITE_DATE=2026-08-25T12:06:07Z \
    HEAD_DATE=2026-08-25T08:00:00Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T11:00:00Z"
assert_rc    "the restored sha costs a wait, not a verdict" 1
assert_lacks "  and nothing declares the review dead" "NO REVIEW COMING"

echo "pr-review-status.sh — a suite from ANOTHER pr does not date this head"
# A check suite belongs to a COMMIT, and a commit can appear on another
# branch, in an earlier pr, or earlier on this same ref. Taking the
# oldest suite unfiltered reaches back before this pr's ref update, so
# an ask made in between reads as newer than the head, stays falsely in
# flight, and the exit-5 callback never fires.
FOREIGN_SUITE_DATE=2026-01-01T00:00:00Z SUITE_DATE=2026-08-25T12:06:07Z \
    HEAD_DATE=2026-08-25T11:48:37Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T11:55:00Z"
assert_rc       "the other pr's suite is ignored" 5
assert_contains "  names the cause" "NO REVIEW COMING"

echo "pr-review-status.sh — an EARLIER suite on ANOTHER ref cannot date this head"
# Only the ref term rejects this one, which is why it is dated EARLY: a
# later suite is rejected by ordering alone and would prove nothing. How
# GitHub populates a suite's `pull_requests` is undocumented — the REST
# reference gives the field's shape and never states the match rule — so
# a sha-only rule, under which every branch sharing this sha lists this
# pr, is not excluded. A sha really does carry several suites minutes
# apart on different refs. Taking the earliest without the ref term
# would then reach back to a push this pr never had, and the ask that
# followed the real push would read as newer than the head and stay
# falsely in flight, so the exit-5 callback never fires.
CLAIMING_SUITE_DATE=2026-01-01T00:00:00Z SUITE_DATE=2026-08-25T12:06:07Z \
    HEAD_DATE=2026-08-25T11:48:37Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T11:55:00Z"
assert_rc       "the other ref's suite is ignored" 5
assert_contains "  names the cause" "NO REVIEW COMING"

echo "pr-review-status.sh — an EARLIER suite this pr does not own cannot date its head"
# Only the pr term rejects this one, so it too is dated EARLY. The ref
# term does not subsume it: a branch outlives the pr opened from it and
# exists before that pr is opened, so this same ref carries suites
# belonging to no pr at all. Taking the earliest without the pr term
# dates the head from one of those, and the ask that followed the real
# push stays falsely in flight.
UNOWNED_SUITE_DATE=2026-01-01T00:00:00Z SUITE_DATE=2026-08-25T12:06:07Z \
    HEAD_DATE=2026-08-25T11:48:37Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T11:55:00Z"
assert_rc       "a suite belonging to no pr is ignored" 5
assert_contains "  names the cause" "NO REVIEW COMING"

echo "pr-review-status.sh — a LATER suite on this ref cannot date this head"
# Neither the ref term nor the pr term rejects this one, and neither can
# the run's event name: a workflow_dispatch against the PR branch, a
# schedule, a re-run and a close/reopen all raise a suite for the
# unchanged sha carrying this ref AND this pr number, and `reopened`
# reports as `pull_request` exactly like a synchronize (the activity
# type is not in the runs API at all). Taken as the head's birthday any
# of them makes the preceding ask read as stale, and with a review on an
# earlier commit that is exit 5 — "no review is coming" while the one
# asked for is in flight. Ordering is what rejects the whole class.
LATER_SUITE_DATE=2026-08-25T13:00:00Z SUITE_DATE=2026-08-25T12:06:07Z \
    HEAD_DATE=2026-08-25T11:48:37Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T12:10:00Z"
assert_rc    "a later suite does not move the head's birthday" 1
assert_lacks "  and nothing declares the review dead" "NO REVIEW COMING"

echo "pr-review-status.sh — the earliest suite is found ACROSS pages, not on page one"
# `per_page` defaults to 30 on the check-suites endpoint, so one request
# is a page rather than the set, and `first` inside jq is the earliest of
# THAT page. gh applies --jq per page and prints one line each, so the
# reduction happens in the shell. Page two here is dated earlier than
# page one: taking page one, or taking the last line, picks 12:06 and
# makes the 11:55 ask read as predating the head — a false exit 5.
# HEAD_DATE is deliberately set LATER than the ask, so the committer-date
# fallback yields exit 5. Without that, every way of getting this wrong
# still reached exit 1 and the case passed vacuously: dropping `sort`
# leaves `head -1` closing the pipe on the first line, the mock dies of
# SIGPIPE, `set -o pipefail` fails the pipeline, and `|| head_born=""`
# hands the head to the fallback — which, dated before the ask, agreed
# with the right answer by accident.
PAGE2_SUITE_DATE=2026-08-25T11:00:00Z SUITE_DATE=2026-08-25T12:06:07Z \
    HEAD_DATE=2026-08-25T12:30:00Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T11:55:00Z"
assert_rc    "a later page's earlier suite wins" 1
assert_lacks "  and nothing declares the review dead" "NO REVIEW COMING"

echo "pr-review-status.sh — a quote in the branch name does not break the lookup"
# `gh api --jq` takes no `--arg`, so the ref travels inside the filter
# TEXT, and git permits a `"` in a ref name. Spliced between bare quotes
# it closes the string early and jq rejects the filter, which is silent:
# the lookup returns nothing and the head falls back to its commit date.
# Here that date is ancient, so the fallback would call an old ask
# current and leave it in flight — the answer flips.
HEAD_REF='mine/we"ird' HEAD_DATE=2026-01-01T00:00:00Z SUITE_DATE=2026-08-25T12:06:07Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T11:55:00Z"
assert_rc       "the suite date is still found" 5
assert_contains "  names the cause" "NO REVIEW COMING"

echo "pr-review-status.sh — no check suite falls back to the commit date"
# A push that triggered no CI at all. Falling back keeps the previous
# behaviour rather than treating the head as unborn.
# The ask must fall BEFORE the commit date, or the assertion cannot tell
# the fallback from having no head birth at all: both leave the ask
# pending and exit 1. It has to be a case where the fallback CHANGES the
# answer — first written the other way round, and it passed with the
# fallback deleted.
HEAD_DATE=2026-08-20T00:00:00Z SUITE_DATE= \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T10:00:00Z" \
    "someone,REQUEST,2026-08-15T10:00:00Z"
assert_rc       "the commit date still decides when nothing else can" 5
assert_contains "  names the cause" "NO REVIEW COMING"

echo "pr-review-status.sh — a STALE review does not answer a later ask"
# An H1 review can land AFTER H2 was pushed and asked about. Judging the
# ask by timestamp alone let that stale review count as the answer, so
# the command returned exit 5 while H2's review was still in flight —
# recency is not coverage, the same confusion 8c678d79 fixed for the
# head-reviewed test itself.
HEAD_DATE=2026-08-10T00:00:00Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-20T10:00:00Z" \
    "someone,REQUEST,2026-08-15T10:00:00Z"
assert_rc    "the ask still counts as in flight" 1
assert_lacks "  and nothing claims the review is not coming" "NO REVIEW COMING"

echo "pr-review-status.sh — ...but an ask made BEFORE this head still expires"
# The guard against fixing the above by making the ask permanent. Asked,
# reviewed, THEN pushed without asking again: nothing is coming, and
# saying so is what exit 5 is for. The discriminator is whether the ask
# postdates the head it would be waiting for — not whether some review
# happens to be newer than it.
HEAD_DATE=2026-08-10T00:00:00Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-07T10:00:00Z" \
    "someone,REQUEST,2026-08-05T10:00:00Z"
assert_rc       "an ask for an older head does not suppress the verdict" 5
assert_contains "  names the cause" "NO REVIEW COMING"

echo "pr-review-status.sh — an ask ALREADY ANSWERED does not suppress the verdict"
# Otherwise one old ask would mask the stale-review state forever, and
# --wait would never return an answer again.
run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-20T10:00:00Z" \
    "someone,REQUEST,2026-08-01T10:00:00Z"
assert_rc       "the answer that followed it wins" 5
assert_contains "  and the ask is marked answered" "already answered"

echo "pr-review-status.sh — a re-ask after a refusal supersedes it"
# Whatever made the reviewer decline passes. Asking again once the cause
# is gone is the normal recovery, so a decline that predates the re-ask
# is spent rather than standing.
run_with_verdicts "OPEN:ffffffffff:0" "" \
    "reviewer[bot],REFUSED,2026-08-01T10:00:00Z
someone,REQUEST,2026-08-20T10:00:00Z"
assert_rc    "the re-ask reopens the wait" 1
assert_lacks "  and the decline no longer ends it" "the reviewer declined"

echo "pr-review-status.sh — a refusal AFTER the ask still ends the wait"
# The direction that matters: asking and then being refused is the
# refusal answering the ask, not the ask outliving it.
run_with_verdicts "OPEN:ffffffffff:0" "" \
    "someone,REQUEST,2026-08-01T10:00:00Z
reviewer[bot],REFUSED,2026-08-20T10:00:00Z"
assert_rc       "the decline wins" 5
assert_contains "  and names itself"  "the reviewer declined"

echo "pr-review-status.sh — a pending request from ANYONE suppresses the verdict"
# The question is "did anyone independent look"; a person still on the
# request list can still answer it.
run "OPEN:ffffffffff:1@a-human" "reviewer-a,aaaaaaaaaa,2026-08-01T10:00:00Z"
assert_rc "a pending request means a review may be coming" 1

# The case that stood here asserted a pending request count alone
# reopens the wait. That was the defect, not the behaviour: it is
# superseded by the three cases above, which assert the same recovery
# WITH the ordering evidence that makes it correct, plus the two
# directions the count could not distinguish.

echo "pr-review-status.sh — a formal request PREDATING the refusal does not supersede it"
# `requested` is a count and carries no ordering. A request already
# pending when the reviewer declined stays in reviewRequests afterwards,
# so clearing the refusal on the count alone marks it superseded by the
# very request it answered — and the command waits out its timeout
# instead of reporting the decline.
FORMAL_DATE=2026-08-01T10:00:00Z \
    run_with_verdicts "OPEN:ffffffffff:1" "" \
    "reviewer[bot],REFUSED,2026-08-20T10:00:00Z"
assert_rc       "the refusal answered that request, and still stands" 5
assert_contains "  names the decline" "the reviewer declined"

echo "pr-review-status.sh — ...and one made AFTER it does supersede it"
FORMAL_DATE=2026-08-25T10:00:00Z \
    run_with_verdicts "OPEN:ffffffffff:1" "" \
    "reviewer[bot],REFUSED,2026-08-20T10:00:00Z"
assert_rc    "a genuine re-request reopens the wait" 1
assert_lacks "  and the decline no longer ends it" "the reviewer declined"

echo "pr-review-status.sh — a request since WITHDRAWN cannot supersede the refusal"
# The timeline keeps a REVIEW_REQUESTED_EVENT after the request is
# withdrawn. So: bot asked, bot declines, a human is asked, the human
# request is removed without a review. reviewRequests holds the bot
# alone — pending_others rightly sees nobody waiting — yet the later
# human event is still on the timeline, and a filter that admits any
# reviewer in default mode took it as a supersession. The refusal was
# cleared on a request nobody can answer any more, and the wait timed
# out instead of reporting the decline in hand. The event has to name
# a reviewer who is STILL pending.
FORMAL_DATE="2026-08-25T10:00:00Z,a-human" \
    run_with_verdicts "OPEN:ffffffffff:1" "" \
    "reviewer[bot],REFUSED,2026-08-20T10:00:00Z"
assert_rc       "a withdrawn request does not reopen the wait" 5
assert_contains "  the decline still stands" "the reviewer declined"

echo "pr-review-status.sh — a decline does not answer a PENDING HUMAN request"
# The question is "did anyone independent look", so a human review is
# coverage. The configured reviewer saying it will not review says
# nothing about a human still on the request list — and the refusal exit
# fires ahead of `no_review_coming`, which would have kept waiting on
# that request. The result was "no review is coming" while one was.
run_with_verdicts "OPEN:ffffffffff:2@a-human+reviewer[bot]" "" \
    "someone,REQUEST,2026-08-01T10:00:00Z
reviewer[bot],REFUSED,2026-08-20T10:00:00Z"
assert_rc    "the human request outlives the reviewer's decline" 1
assert_lacks "  and nothing declares the review dead" "the reviewer declined"

echo "pr-review-status.sh — no gh api call invents a flag gh does not have"
# The mock cannot catch this, by construction: it was the mock that was
# wrong. `--argjson` is a jq option and `gh api` has none, so the
# timeline lookup failed with "unknown flag" on every real invocation
# while this suite stayed green, because the mock implemented the
# fictitious interface.
#
# Line continuations are folded first, so a flag on the second line of a
# `gh api ... \` call is still seen as part of that call. Only gh api
# invocations are examined — jq itself takes these flags legitimately,
# and the point is which command they were handed to.
# The scan runs from each `gh api` to the end of its command
# substitution, because the GraphQL query is a multi-line string with no
# backslash continuations — folding those joined nothing, so a flag on a
# later line was not seen as part of the call. Verified by putting the
# defect back: it fails this case.
offenders="$(awk '
  /gh api/            { inside = 1 }
  inside && /--(argjson|slurp|null-input|raw-input)/ {
      match($0, /--(argjson|slurp|null-input|raw-input)/)
      print substr($0, RSTART, RLENGTH)
  }
  inside && /\)"/     { inside = 0 }
' "$UNDER_TEST" | sort -u | tr '\n' ' ')"
if [[ -z "${offenders// /}" ]]; then
    pass "gh api is never handed a jq-only flag"
else
    fail "gh api does not accept: $offenders" \
         "these are jq options — pipe the response into jq instead"
fi

echo "pr-review-status.sh — a request event for someone NOT pending does not clear the refusal"
# Taking the globally latest request event let any later ask for anyone
# supersede the decline, so the command went on waiting for a reviewer
# that had already refused because a human had since been requested and
# withdrawn. THE REVIEWER MUST BE THE ONE STILL REQUESTED, or this proves
# nothing: it has to be a pr where the configured reviewer IS pending
# (count 1, filled with it) and a human was asked LATER and is not — that
# later event is what an unfiltered query would wrongly take as
# superseding the decline.
FORMAL_DATE="2026-08-19T10:00:00Z,reviewer[bot]
2026-08-25T10:00:00Z,a-human" \
    run_with_verdicts "OPEN:ffffffffff:1" "" \
    "reviewer[bot],REFUSED,2026-08-20T10:00:00Z"
assert_rc       "the reviewer's decline still stands" 5
assert_contains "  names the decline" "the reviewer declined"

echo "pr-review-status.sh — ...and a request of the reviewer itself after it clears it"
FORMAL_DATE="2026-08-25T10:00:00Z,reviewer[bot]" \
    run_with_verdicts "OPEN:ffffffffff:1" "" \
    "reviewer[bot],REFUSED,2026-08-20T10:00:00Z"
assert_rc "a re-request of the configured reviewer reopens the wait" 1

echo "pr-review-status.sh — unreadable timeline leaves the refusal standing"
# The decline is the thing actually observed. Discarding it on evidence
# that could not be read trades a fact for a guess.
FORMAL_DATE= \
    run_with_verdicts "OPEN:ffffffffff:1" "" \
    "reviewer[bot],REFUSED,2026-08-20T10:00:00Z"
assert_rc "no ordering evidence means the refusal is not superseded" 5

echo "pr-review-status.sh — a CURRENT refusal outranks the stale-review message"
# Both causes exit 5, so the code alone cannot tell them apart — and
# naming the cause is the entire point of the refusal branch. With an
# older review on a previous head AND a decline newer than it,
# no_review_coming is also true, so whichever test runs first owns the
# message. The permanent, actionable one has to win: "request another
# review" is advice that cannot work while the reviewer is declining.
run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-01T10:00:00Z" \
    "reviewer[bot],REFUSED,2026-08-20T10:00:00Z"
assert_rc       "still exits 5" 5
assert_contains "names the DECLINE, not the stale review" "the reviewer declined"
assert_lacks    "  and does not send the caller to re-review" "dispatch a re-review (exit 5)"

echo "pr-review-status.sh — a configuration that cannot be applied is refused, never read as 'none'"
# jq rejects the pattern; with stderr discarded and a fall-back to "no
# ask", the pending request below vanished and the stale review became a
# confident exit 5. A bad configuration is an invocation problem: exit 2.
REQUEST_RE_OVERRIDE='@reviewer review(' \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-01T10:00:00Z" \
    "someone,REQUEST,2026-08-20T10:00:00Z"
assert_rc       "an invalid ask regex exits 2" 2
assert_contains "  and names the variable" "AGENT_FABRIC_REVIEW_REQUEST_RE"
REFUSAL_RE_OVERRIDE='[unclosed' run_with_verdicts "OPEN:ffffffffff:0" "" "reviewer[bot],REFUSED"
assert_rc       "an invalid refusal regex exits 2" 2
assert_contains "  and names the variable" "AGENT_FABRIC_REVIEWER_REFUSAL_RE"
VERDICT_AUTHORS_OVERRIDE='reviewer[bot]' run_with_verdicts "OPEN:ffffffffff:0" "" "reviewer[bot],ffffffffff"
assert_rc       "a verdict-author list that is not a JSON array exits 2" 2
assert_contains "  and names the variable" "AGENT_FABRIC_VERDICT_AUTHORS"

echo "pr-review-status.sh — the decline reason is the reviewer's first line, whole"
# A web-UI comment arrives with CRLF and may open with a blank line; a
# reason with an em dash in it was cut at the dash by a consumer written
# for the old fixed-format strings, and read as a refusal of the diff.
run_with_verdicts "OPEN:ffffffffff:0" "" "reviewer[bot],REFUSED_DASH"
assert_rc       "still a decline" 5
assert_contains "  the reason is the first non-empty line, CR stripped" "decline reason      : Cannot review this PR — usage limit reached for reviews."
assert_contains "  and the verdict line carries it whole" "the reviewer declined: Cannot review this PR — usage limit reached for reviews. (exit 5)"

echo "pr-review-status.sh — a MERGED pr is not ended by a refusal"
# Same exception the exit-5 path already carries: a post-merge sweep
# runs long after whatever made the reviewer decline has passed.
run_with_verdicts "MERGED:ffffffffff:0" "" "reviewer[bot],REFUSED"
assert_rc "a merged pr keeps waiting despite a decline" 1

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

echo "pr-review-status.sh — -q writes NOTHING to stderr"
# `-q` documents "no progress lines on stderr", and a background watcher
# runs for half an hour, so anything unconditional here is emitted on
# every poll. This case exists because a diagnostic `printf ... >&2`
# added while chasing a head_born value was committed and pushed: the
# suite folded stderr into stdout and no case ever asked what stderr
# held, so nothing failed. It was caught in review, not by the tests.
#
# The head-birth path is deliberately exercised (there is an ask to
# date), because that is where the leak was.
HEAD_DATE=2026-08-25T11:48:37Z SUITE_DATE=2026-08-25T12:06:07Z \
    run_with_verdicts "OPEN:ffffffffff:0" "reviewer-a,aaaaaaaaaa,2026-08-25T11:50:00Z" \
    "someone,REQUEST,2026-08-25T12:10:00Z" -q
assert_err_empty "no diagnostic output escapes under -q"

if (( failures )); then
    echo "FAILED: $failures assertion(s)" >&2
    exit 1
fi
echo "all assertions passed"
