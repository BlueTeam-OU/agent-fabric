#!/usr/bin/env bash
# runtime/github/pr-review-status.sh (lifted from the first managed project's tools/gh/ on 2026-09-19 — the commit names it; general to every managed project, whose own tools/gh/ copy is a forwarder through projects/<id>/integration/gh/)
#
# >>> help
# Has THE HEAD of this PR been reviewed — by a reviewer other than the
# author, or by the review class's blind review? A raw `gh pr view`
# cannot answer that.
#
# Two GitHub behaviours make the obvious reading wrong, and both bit
# this repo:
#
#   1. Replying to a review thread (addPullRequestReviewThreadReply)
#      creates a REVIEW object with an empty body, authored by you.
#      Three self-replies look like three new reviews. On one PR that
#      made a self-authored thread look like independent coverage.
#
#   2. A review comment's `commit_id` is re-anchored to the CURRENT
#      head whenever the file it points at has not changed. A finding
#      written against an old commit therefore DISPLAYS as though it
#      were evaluated against code that did not exist when it was
#      written. `original_commit_id` is the honest field.
#
# So: classify by MARKER then by AUTHOR, and compare each counted
# review's commit against headRefOid. Everything else is noise.
#
# WHAT COUNTS. Three buckets, reported on their own lines:
#   independent reviews — review objects by an account other than the
#                         PR author that the repository trusts: its
#                         owner, an organisation member or a collaborator
#                         (GitHub's author_association), or a login named
#                         in AGENT_FABRIC_VERDICT_AUTHORS (an App's review
#                         carries the association NONE). Every session
#                         pushes as one account, so this is a person, not
#                         another session; anyone else's review is listed
#                         as "not trusted" and is not coverage;
#   blind reviews       — the review class's reviews, posted by
#                         post-review.sh as review objects whose FIRST
#                         LINE is REVIEW_MARKER (below), BY the account
#                         the sessions push as — the PR author, or one
#                         named in AGENT_FABRIC_REVIEW_POSTERS: the
#                         fabric's review of every PR, dispatched by the
#                         session that owns it and judged before it is
#                         answered. A marked review by any other account
#                         is reported, with its login, and is NOT
#                         coverage: the marker is published in every
#                         tree, and on a public repository anyone can
#                         post it;
#   self reviews        — the author's own thread replies; not coverage.
# A head is reviewed when an independent or a blind review targets it.
#
# An AUTOMATED REVIEWER is not assumed. A project that runs one names
# its accounts in AGENT_FABRIC_VERDICT_AUTHORS (a JSON array); then a
# review object from one of them is independent coverage whatever its
# association, a comment from one of them naming `Reviewed commit: <sha>` counts as a
# verdict on that sha, the phrases in AGENT_FABRIC_REVIEWER_REFUSAL_RE
# read as that reviewer declining (exit 5, the cause named), and a
# comment matching AGENT_FABRIC_REVIEW_REQUEST_RE reads as a pending
# request. All three are empty by default: no verdicts, no refusals, no
# requests — the review class is the review.
#
# WAITING (--wait). Nothing reviews a push by itself: a session
# dispatches the review class and posts its review. So `--wait` is for
# a review known to be in flight (another session's, a person's), and
# there are two "no review yet" states:
#
#   * never reviewed          — wait, up to the timeout.
#   * reviewed, then pushed   — nothing will arrive on its own; a
#                               re-review of the new range is owed.
#                               Exits 5 IMMEDIATELY with the cause,
#                               rather than burning the timeout.
#
# ...on an OPEN pr. A MERGED pr keeps waiting (a review can still land
# on it); a pr CLOSED without merging ends the wait at 1.
#
# Usage:
#   pr-review-status.sh <pr-number> [owner/repo] [options]
#
# Options:
#   --wait <duration>      poll until the head is reviewed (default 0 =
#                          answer once and exit)
#   --interval <duration>  between polls (default 30; the API is rate
#                          limited and reviewers are slow)
#   -q, --quiet            no progress lines on stderr
#   --json                 the final answer as one JSON object on stdout
#                          instead of the report (the exit code is the
#                          same): state, merge_state, head,
#                          head_reviewed, the three buckets as
#                          {count, rows}, marked_by_others, not_trusted,
#                          no_review_coming ({cause, reason} or null),
#                          verdicts, unresolved_threads (null when the
#                          lookup failed), checks {pass, other}
#   -h, --help             this text
#
# Durations take an optional unit — 90, 90s, 10m, 2h. A bare number is
# SECONDS.
#
# Exit codes:
#   0  the current head has at least one counted review — ANY of them,
#      not merely the most recent, which can be older by commit than
#      one submitted before it — or a configured reviewer's verdict
#      comment naming it
#   1  it does not — nothing yet, --wait expired still waiting, or the
#      pr was closed without merging
#   2  invocation problem (no gh, not authenticated, unknown PR), or the
#      pr could not be read — including a reviews or comments lookup that
#      FAILED, which is never reported as "no reviews"
#   5  no review is COMING on its own, on an OPEN pr: the head advanced
#      past every counted review with none requested — a re-review is
#      owed — or a configured automated reviewer declined (the `decline
#      reason` line says which phrase). Never returned for a merged pr.
# <<< help

set -uo pipefail

PR=""
REPO=""
WAIT=0
INTERVAL=30
QUIET=0
JSON=0

die() { echo "pr-review-status: $*" >&2; exit 2; }

need_operand() {
    [[ $# -ge 2 ]] || die "$1 needs a value (try --help)."
}

# Durations take an optional unit: 90, 90s, 10m, 2h. A BARE NUMBER IS
# SECONDS — which is what every existing invocation already meant, so
# nothing changes for a caller that passed one.
#
# The table stands alone, pinned by this script's own suite. A project
# that keeps a waiter of its own with the same units asserts its copy in
# its own suite; the fabric's suite cannot see it, so nothing here claims
# the two agree.
as_seconds() {
    local flag="$1" raw="$2" n
    case "$raw" in
        ''|*[!0-9smh]*) die "$flag needs a duration like 90, 90s, 10m or 2h, got '$raw'." ;;
    esac
    n="${raw%[smh]}"
    [[ "$n" =~ ^[0-9]+$ ]] \
        || die "$flag needs a duration like 90, 90s, 10m or 2h, got '$raw'."
    case "$raw" in
        *h) echo $(( n * 3600 )) ;;
        *m) echo $(( n * 60 )) ;;
        *)  echo "$n" ;;
    esac
}

want_positive() {
    [[ "$2" =~ ^[1-9][0-9]*$ ]] \
        || die "$1 must be greater than zero, got '$3'."
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        # `as_seconds` dies inside a command substitution, which only
        # kills the SUBSHELL — without propagating the status here the
        # script would sail on with an empty value.
        --wait)
            need_operand "$@"; WAIT="$(as_seconds "$1" "$2")" || exit 2; shift 2 ;;
        --interval)
            need_operand "$@"; INTERVAL="$(as_seconds "$1" "$2")" || exit 2
            want_positive "$1" "$INTERVAL" "$2"; shift 2 ;;
        -q|--quiet) QUIET=1; shift ;;
        --json) JSON=1; shift ;;
        -h|--help)
            sed -n '/^# >>> help$/,/^# <<< help$/p' "$0" \
                | sed 's/^# \{0,1\}//; 1d; $d'
            exit 0 ;;
        -*) die "unknown option '$1' (try --help)" ;;
        *)
            if   [[ -z "$PR"   ]]; then PR="$1"
            elif [[ -z "$REPO" ]]; then REPO="$1"
            else die "unexpected argument '$1' (try --help)"
            fi
            shift ;;
    esac
done

[[ -n "$PR" ]] || die "a PR number is required (try --help)"

command -v gh >/dev/null 2>&1 || die "gh is required but not installed."

if [[ -z "$REPO" ]]; then
    REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" || \
        die "could not determine the repository; pass owner/repo."
fi

note() { (( QUIET )) || echo "pr-review-status: $*" >&2; }

# ── One probe ────────────────────────────────────────────────────────
#
# Sets the globals the loop branches on. Kept separate from rendering so
# a poll costs three API calls, not the whole report: the thread and
# check queries below are for the human reading the final answer, and
# running them every 30 seconds would be rude to the rate limiter for
# output nobody sees.

# The marker post-review.sh writes as the first line of every review the
# review class posts. Must stay byte-identical to the constant in that
# script; both self-tests pin it, so a one-sided change is caught.
REVIEW_MARKER='<!-- agent-fabric-review v1 -->'
# Reviews posted under earlier markers keep counting: the fabric's own
# previous marker is built in, and a project's integration forwarder
# (projects/<id>/integration/gh/) may add its own through
# AGENT_FABRIC_LEGACY_REVIEW_MARKERS, one per line. The project's name
# never appears here — the fabric's lint refuses it in a generic file.
# The built-in one goes when no open PR anywhere carries a review posted
# before 2026-09-20 (docs/adr/ADR-020-the-review-class-is-the-review.md §5 rule 8).
LEGACY_MARKERS="$(printf '%s\n%s' '<!-- agent-fabric-substitute-review v1 -->' "${AGENT_FABRIC_LEGACY_REVIEW_MARKERS:-}")"

# AN AUTOMATED REVIEWER, if a project runs one — none by default.
# Accounts whose verdict COMMENT counts as a review of the sha it names:
# a LIST, because the alternative is a negation and a negation lets
# anybody in ("not the PR author" is right for a review OBJECT, which
# only a reviewer can create, and wrong for a comment, which anyone with
# access may leave). Empty means no comment is ever a verdict.
VERDICT_AUTHORS="${AGENT_FABRIC_VERDICT_AUTHORS:-[]}"
# Who may post a blind review, besides the PR author: a JSON array of
# logins. Empty by default, because every session pushes AND posts as one
# account, which is the author of every PR a session opens.
REVIEW_POSTERS="${AGENT_FABRIC_REVIEW_POSTERS:-[]}"
# The reviewer's own refusal wording (a regex over the comment body) and
# the phrase a request for it takes; both empty by default, so nothing
# reads as a decline and nothing as a pending request. A request never
# marks a head reviewed — it can only turn "nothing is coming" into "not
# yet" — which is why it needs no allow-list.
REVIEWER_REFUSAL_RE="${AGENT_FABRIC_REVIEWER_REFUSAL_RE:-}"
REVIEW_REQUEST_RE="${AGENT_FABRIC_REVIEW_REQUEST_RE:-}"

# A CONFIGURED value that cannot be applied fails HERE, not silently
# below. Every jq call over these runs with stderr discarded and a
# fall-back to "none", so a list that is not JSON, or a pattern jq's
# regex engine rejects, would read as no verdicts, no decline, no ask —
# and the no-ask reading turns a pending request into a confident
# "NO REVIEW COMING" (exit 5), the wrong answer this script exists to
# avoid. Exit 2 is the invocation-problem code; a bad configuration is
# one.
jq -e 'type == "array" and all(.[]; type == "string")' <<<"$VERDICT_AUTHORS" >/dev/null 2>&1 \
    || die "AGENT_FABRIC_VERDICT_AUTHORS must be a JSON array of logins, got '$VERDICT_AUTHORS'."
jq -e 'type == "array" and all(.[]; type == "string")' <<<"$REVIEW_POSTERS" >/dev/null 2>&1 \
    || die "AGENT_FABRIC_REVIEW_POSTERS must be a JSON array of logins, got '$REVIEW_POSTERS'."
for _re_name in REVIEWER_REFUSAL_RE REVIEW_REQUEST_RE; do
    [[ -z "${!_re_name}" ]] && continue
    # Compiled with the same "i" flag the consumers use, so what passes
    # here is exactly what runs below.
    jq -n --arg re "${!_re_name}" '"" | test($re; "i")' >/dev/null 2>&1 \
        || die "AGENT_FABRIC_$_re_name is not a regex jq accepts: '${!_re_name}'."
done

probe_ok=0
qualifying='[]'
qual_count=0
verdicts='[]'
verdict_count=0
independent='[]'; blind='[]'; marked_others='[]'; others_count=0; self_count=0
outsiders='[]'; outsiders_count=0
# Why no review is coming, when that is the answer (exit 5): carried as a
# field under --json, where stdout must stay one object.
no_coming_cause=""; no_coming_reason=""
refusal_at=""
refusal_current=no
pending_others=0
request_at=""
request_pending=no
probe() {
    # RESET, not just set on success. A probe that overwrites `head` from
    # the metadata call and then fails on reviews would otherwise leave
    # the flag standing from an EARLIER successful probe, and the report
    # would pair the new head with the old review data — a mismatch that
    # reads as authoritative.
    probe_ok=0
    local meta reviews
    meta="$(gh pr view "$PR" --repo "$REPO" \
        --json state,mergeStateStatus,headRefOid,headRefName,author,isDraft,reviewRequests \
        2>/dev/null)" || return 1

    head="$(jq -r '.headRefOid'          <<<"$meta")"
    head_ref="$(jq -r '.headRefName // ""' <<<"$meta")"
    state="$(jq -r '.state'              <<<"$meta")"
    mergest="$(jq -r '.mergeStateStatus'  <<<"$meta")"
    author="$(jq -r '.author.login'      <<<"$meta")"
    requested="$(jq '.reviewRequests | length' <<<"$meta")"
    # Everyone still on the request list who is NOT a configured automated
    # reviewer. A decline answers the reviewer who made it and nobody
    # else, and any of these would satisfy the question — so their
    # pending requests have to survive it.
    pending_others="$(jq --argjson allowed "$VERDICT_AUTHORS" \
        '[.reviewRequests[]?
          | select((((.login // .slug // "") as $l | $allowed | index($l)) | not))]
         | length' <<<"$meta")"

    # PAGINATED, and a failure here reads UNREADABLE — never empty. This
    # script's whole job is answering "was this really reviewed", so
    # turning a rate limit, a permission gap or a transient 5xx into `[]`
    # produces the confident wrong answer "no reviews" and lets a caller
    # conclude a reviewed pr was never looked at. Returning 1 feeds the
    # consecutive-failure counter instead, which is what the exit-2
    # contract already promises for an unreadable pr.
    #
    # Unpaginated, a pr with more review objects than one REST page
    # silently lost the rest — plausible here precisely because this
    # script documents that thread replies create review objects, so the
    # count climbs with correspondence rather than with coverage.
    #
    # `local` is on its own line deliberately: `local x="$(cmd)"` takes
    # local's exit status, not the command's, which would make the
    # failure branch below unreachable.
    local reviews_raw
    reviews_raw="$(gh api --paginate "repos/$REPO/pulls/$PR/reviews" 2>/dev/null)" || return 1
    reviews="$(jq -s 'add // []' <<<"$reviews_raw" 2>/dev/null)" || return 1

    # Independent = not authored by the PR author. The empty-body test is
    # NOT used to classify: a genuine reviewer may leave an empty-bodied
    # review carrying only inline comments. Authorship is the honest axis.
    # MARKED FIRST, then authorship. A blind review is authored by the
    # same account as everything else, so classifying by author first
    # loses it; and a marked review is never an independent one — gating
    # the marker test on authorship made a marked review from another
    # login count as genuine independent coverage, silently, in the
    # dangerous direction. It is blind only from the author or a named
    # poster (below), and otherwise counts as nothing.
    #
    # startswith, NOT contains. The emitter guarantees the marker is the
    # FIRST LINE; a substring test counted any review whose body merely
    # QUOTED the marker — reviewing this mechanism is enough to do it —
    # and subtracted that review from `self` at the same time. A false
    # "this was reviewed" is worse than the under-counting this whole
    # change exists to fix.
    # The current marker and every legacy one the forwarder names: a
    # review starts with one of them or it is unmarked.
    markers_json="$(printf '%s\n%s' "$REVIEW_MARKER" "$LEGACY_MARKERS" | jq -R . | jq -s '[.[] | select(length > 0)]')"
    marked="$(jq --argjson ms "$markers_json" \
        '[.[] | select((.body // "") as $b | ($ms | map(. as $m | $b | startswith($m)) | any))]' <<<"$reviews")"
    unmarked="$(jq --argjson ms "$markers_json" \
        '[.[] | select((.body // "") as $b | ($ms | map(. as $m | $b | startswith($m)) | any) | not)]' <<<"$reviews")"

    # AN INDEPENDENT REVIEWER IS SOMEONE THE REPOSITORY TRUSTS: its owner,
    # a member of its organisation, or a collaborator, as GitHub's own
    # `author_association` says. On a public repository anyone can review;
    # binding only the MARKED review to its poster left a stranger's
    # unmarked review counting as coverage (the review of #41, 2026-09-26).
    # Any other account's review is reported as not coverage.
    # A configured reviewer (AGENT_FABRIC_VERDICT_AUTHORS) is trusted by
    # name: a GitHub App's review carries the association NONE.
    trusted='(.author_association as $r | ["OWNER","MEMBER","COLLABORATOR"] | index($r)) or (.user.login as $l | $bots | index($l))'
    independent="$(jq --arg a "$author" --argjson bots "$VERDICT_AUTHORS" "[.[] | select(.user.login != \$a) | select($trusted)]" <<<"$unmarked")"
    outsiders="$(jq --arg a "$author" --argjson bots "$VERDICT_AUTHORS" "[.[] | select(.user.login != \$a) | select(($trusted) | not)]" <<<"$unmarked")"

    # BLIND REVIEWS ARE COVERAGE, and authorship cannot see them. Every
    # session pushes as the SAME account, so the review class's review,
    # posted by the session that owns the PR, is authored by the PR author
    # and would fall into `self` — the bucket labelled "thread replies …
    # not coverage". The marker is what tells them apart: an exact string
    # post-review.sh emits and nothing else produces by accident.
    # AND THE POSTER IS BOUND. The marker is published in every tree that
    # carries post-review.sh, so on a public repository any account can
    # post a review whose first line is the marker; counting it made a
    # stranger's review the head's coverage, indistinguishable in the
    # report (a blind review of a managed project, 2026-09-25). A marked
    # review counts only from the PR author or a named poster; any other
    # is reported, login and all, as not coverage.
    blind="$(jq --arg a "$author" --argjson p "$REVIEW_POSTERS" \
        '[.[] | select(.user.login == $a or (.user.login as $l | $p | index($l)))]' <<<"$marked")"
    marked_others="$(jq --arg a "$author" --argjson p "$REVIEW_POSTERS" \
        '[.[] | select(.user.login != $a and ((.user.login as $l | $p | index($l)) | not))]' <<<"$marked")"
    self="$(jq --arg a "$author" '[.[] | select(.user.login == $a)]' <<<"$unmarked")"

    # WHAT COUNTS AS COVERAGE: every independent review, and every blind
    # review — reported on its own line, so provenance survives.
    qualifying="$(jq -s 'add' <<<"$independent $blind")"

    ind_count="$(jq 'length' <<<"$independent")"
    qual_count="$(jq 'length' <<<"$qualifying")"
    self_count="$(jq 'length' <<<"$self")"
    blind_count="$(jq 'length' <<<"$blind")"
    others_count="$(jq 'length' <<<"$marked_others")"
    outsiders_count="$(jq 'length' <<<"$outsiders")"

    # VERDICT COMMENTS. Unreadable rather than empty, for the same reason
    # the reviews call is: a swallowed failure here would report a clean
    # review as no review, which is the whole defect this fetch fixes.
    local comments_raw comments
    comments_raw="$(gh api --paginate "repos/$REPO/issues/$PR/comments" 2>/dev/null)" || return 1
    comments="$(jq -s 'add // []' <<<"$comments_raw" 2>/dev/null)" || return 1

    # A comment from a CONFIGURED automated reviewer that names the commit it
    # reviewed. The sha in the body is abbreviated, so match on prefix in
    # BOTH directions — neither string is reliably the longer one.
    #
    # The sha is READ, never inferred from "a comment arrived after the
    # push": a verdict can arrive after a push and still describe the
    # commit before it, and a confident wrong answer there is exactly
    # what this script exists to avoid.
    verdicts="$(jq --arg a "$author" --argjson allowed "$VERDICT_AUTHORS" '
        [ .[]
          | select(.user.login as $l | $allowed | index($l))
          | select(.user.login != $a)
          | (.body // "") as $b
          | ($b | capture("Reviewed commit:[^`]*`(?<sha>[0-9a-f]{7,40})`"; "i") // empty) as $m
          | {login: .user.login, at: .created_at, sha: $m.sha}
        ]' <<<"$comments" 2>/dev/null)" || verdicts='[]'
    verdict_count="$(jq 'length' <<<"$verdicts")"

    # REFUSALS. A configured automated reviewer may decline in the same
    # comment stream and from the same account. That is not slowness, it
    # is a review that will not happen — exactly the state exit 5 exists
    # to name — but nothing in the review objects says so, so a wait would
    # otherwise sit out its whole timeout. Matched on the reviewer's own
    # wording (AGENT_FABRIC_REVIEWER_REFUSAL_RE), never on a "sounds
    # negative" heuristic: a wrong positive abandons a review that was
    # merely slow, the more expensive mistake. Empty pattern: no refusals.
    refusal_at=""
    if [[ -n "$REVIEWER_REFUSAL_RE" ]]; then
        refusal_at="$(jq -r --argjson allowed "$VERDICT_AUTHORS" --arg re "$REVIEWER_REFUSAL_RE" '
            [ .[]
              | select(.user.login as $l | $allowed | index($l))
              | select((.body // "") | test($re; "i"))
              | .created_at ]
            | sort | last // ""' <<<"$comments" 2>/dev/null)" || refusal_at=""
    fi
    # THE REASON, read off the same comment: the first line of the
    # reviewer's own words, so the status line says what the reviewer
    # said and never reads as a refusal of THIS diff when it was not.
    refusal_reason=""
    if [[ -n "$refusal_at" ]]; then
        refusal_reason="$(jq -r --argjson allowed "$VERDICT_AUTHORS" --arg at "$refusal_at" '
            [ .[] | select(.user.login as $l | $allowed | index($l)) | select(.created_at == $at)
              | (.body // "") ] | first // ""
            | gsub("\r"; "") | split("\n") | map(select(length > 0)) | first // "" | .[0:160]' \
            <<<"$comments" 2>/dev/null)" || refusal_reason=""
    fi

    # A PENDING REQUEST, read from the same comment stream when a project
    # asks its automated reviewer with a phrase (AGENT_FABRIC_REVIEW_REQUEST_RE)
    # rather than a GitHub review request. NO allow-list here,
    # deliberately: this signal can only turn 5 ("nothing is coming")
    # into 1 ("not yet") — it never marks a head reviewed, so the worst a
    # forged request can do is make the tool wait longer. Empty pattern:
    # no requests.
    request_at=""
    if [[ -n "$REVIEW_REQUEST_RE" ]]; then
        request_at="$(jq -r --arg re "$REVIEW_REQUEST_RE" '
            [ .[] | select((.body // "") | test($re; "i"))
              | .created_at ]
            | sort | last // ""' <<<"$comments" 2>/dev/null)" || request_at=""
    fi

    head_reviewed=no
    newest_ind_commit=""

    # Either kind of evidence counts, and a verdict comment is checked
    # even when there are no review objects at all — a PR whose only
    # review came back CLEAN has none.
    if [[ "$(jq -r --arg h "$head" \
          'any(.[]; (.sha as $s | ($h | startswith($s)) or ($s | startswith($h))))' \
          <<<"$verdicts")" == "true" ]]; then
        head_reviewed=yes
    fi

    if (( qual_count > 0 )); then
        newest_ind_commit="$(jq -r 'sort_by(.submitted_at) | last | .commit_id' <<<"$qualifying")"
        # COVERAGE IS "ANY review targets head", NOT "the newest one
        # does". A review opened before the last push but SUBMITTED after
        # a fresh one is newer by timestamp and older by commit, so
        # selecting by recency lets a stale review mask a real one — and
        # this script would then call the head unreviewed while the
        # review it wanted was already sitting there. The newest is kept
        # for REPORTING only.
        if [[ "$(jq -r --arg h "$head" 'any(.[]; .commit_id == $h)' <<<"$qualifying")" == "true" ]]; then
            head_reviewed=yes
        fi
    fi

    # A refusal only speaks for the CURRENT state. The reviewer recovers
    # — whatever made it decline passes — and a
    # verdict or review arriving afterwards supersedes it. So the
    # refusal counts only when nothing newer has landed; otherwise a
    # refusal from last week would end every wait on this PR
    # forever.
    refusal_current=no
    if [[ -n "$refusal_at" ]]; then
        local newest_evidence
        newest_evidence="$(printf '%s\n%s\n' "$qualifying" "$verdicts" | jq -rs '
            (.[0] | map(.submitted_at)) + (.[1] | map(.at))
            | sort | last // ""' 2>/dev/null)" || newest_evidence=""
        # ...and to a request made AFTER it. The cause passes and
        # the environment gets created, so asking again once the cause
        # is gone is the normal recovery — a decline that predates the
        # re-ask is spent, not standing.
        if [[ "$refusal_at" > "$newest_evidence" ]] \
           && [[ -z "$request_at" || ! "$request_at" > "$refusal_at" ]]; then
            refusal_current=yes
        fi
    fi

    # A FORMAL re-request also supersedes it — but only one made AFTER
    # the refusal.
    #
    # `requested` is a COUNT and carries no ordering. A request that was
    # already pending when the reviewer declined stays in reviewRequests
    # afterwards, so clearing the refusal on the count alone marks it
    # superseded by the very request it answered, and the command then
    # waits out its whole timeout instead of reporting the decline.
    #
    # That is the same mistake the comment path does NOT make — it
    # compares request_at against refusal_at — reintroduced one line
    # away while fixing the asymmetry between the two ask mechanisms.
    # The ordering has to come from the timeline, because the count
    # cannot supply it.
    #
    # Fetched only when there IS a refusal to supersede AND a request
    # that might do it, so the common path pays nothing.
    if [[ -n "$refusal_at" ]] && (( requested > 0 )); then
        # MATCHED TO A REVIEWER STILL BEING AWAITED, not merely the
        # latest event on the pr.
        #
        # Discarding requestedReviewer made any later request for anyone
        # clear the configured reviewer's refusal, because a person had
        # since been asked. The identity has to be read.
        #
        # And the event has to name someone STILL ON THE REQUEST LIST.
        # The timeline keeps a REVIEW_REQUESTED_EVENT after the request
        # is withdrawn, so a human asked after the decline and then
        # removed without reviewing leaves a later event and no pending
        # request. `pending_others` (below) correctly sees nobody
        # waiting; an unrestricted filter here still took that stale
        # event as a supersession, cleared the refusal, and the command
        # waited out its timeout instead of reporting the decline it had
        # in hand. Requiring the reviewer to be currently pending is
        # what ties the event to a request that can still be answered.
        local formal_at reviewer_filter pending_logins
        pending_logins="$(jq -c '[.reviewRequests[]? | (.login // .slug // "")]' <<<"$meta")"
        reviewer_filter="select(.login as \$l | \$pending | index(\$l))"
        # jq RUNS HERE, not inside gh. `--argjson` is a jq option and
        # `gh api` does not accept it: the call failed with "unknown
        # flag" on every real invocation, stderr was suppressed, and
        # formal_at came back empty — so a genuine later request never
        # superseded a refusal. The self-test mock had invented the flag
        # and hidden it completely.
        local formal_raw
        formal_raw="$(gh api graphql -f query="
          { repository(owner: \"${REPO%%/*}\", name: \"${REPO##*/}\") {
              pullRequest(number: $PR) {
                timelineItems(last: 50, itemTypes: [REVIEW_REQUESTED_EVENT]) {
                  nodes { ... on ReviewRequestedEvent { createdAt
                    requestedReviewer {
                      ... on User { login }
                      ... on Bot  { login }
                      ... on Team { login: slug } } } } } } } }" \
          2>/dev/null)" || formal_raw=""
        formal_at="$(jq -r --argjson allowed "$VERDICT_AUTHORS" \
                        --argjson pending "$pending_logins" \
          "[.data.repository.pullRequest.timelineItems.nodes[]
            | {createdAt, login: (.requestedReviewer.login // \"\")}
            | $reviewer_filter | .createdAt] | sort | last // empty" \
          <<<"$formal_raw" 2>/dev/null)" || formal_at=""
        # Unreadable, or no event found: leave the refusal standing. The
        # decline is the thing we actually observed; discarding it on
        # evidence we could not read would trade a fact for a guess.
        [[ -n "$formal_at" && "$formal_at" > "$refusal_at" ]] && refusal_current=no
    fi

    # A DECLINE ANSWERS THE REVIEWER WHO MADE IT, AND NOBODY ELSE.
    #
    # The question is "did anyone independent look", so a person's
    # review is coverage. A configured reviewer saying it will not
    # review is not an answer about a person who is still on the
    # request list — and the refusal exit fires ahead of
    # `no_review_coming`, which would have kept waiting on that pending
    # request. Without this the command reports "no review is coming"
    # while one is: the confidently-wrong direction again.
    #
    # The result is a longer wait, not a verdict: with a request still
    # pending, `no_review_coming` cannot fire either, so the command
    # keeps polling until the review lands or the window closes.
    if (( pending_others > 0 )); then
        refusal_current=no
    fi

    # A request newer than every review, verdict and refusal means one
    # is in flight.
    # AN ASK IS FOR A PARTICULAR HEAD, and the test is whether it
    # postdates that head — NOT whether some review happens to be newer
    # than it.
    #
    # Timestamps alone got this wrong in both directions. A review of an
    # EARLIER commit can land after a newer head was pushed and asked
    # about; counting it as the answer returned "no review is coming"
    # while the real one was still in flight. That is recency mistaken
    # for coverage, the same confusion 8c678d79 fixed for the
    # head-reviewed test itself.
    #
    # Requiring a HEAD-MATCHING review to answer the ask — the obvious
    # repair — breaks the other direction: asked, reviewed, then pushed
    # again without asking. No review will ever match the new head, so
    # the ask would stay pending forever and exit 5 could never fire,
    # which is the one thing it exists to say. The head's own commit
    # date separates the two cleanly, so that is what is compared.
    #
    # Fetched only when there IS an ask, so the common path keeps its
    # three calls.
    request_pending=no
    if [[ -n "$request_at" ]]; then
        # WHEN THE HEAD BECAME THE HEAD, which is not when its commit was
        # written.
        #
        # `.commit.committer.date` is metadata carried inside the commit,
        # so it says nothing about the ref. A cherry-picked, rebased or
        # amended commit keeps a date that can long predate the ask, and
        # even an ordinary one drifts: ba20a29e on #501 was committed at
        # 11:48:37 and pushed at 12:06 — eighteen minutes in which an ask
        # would have been misattributed to a head that did not yet exist
        # on the remote.
        #
        # The check suite is created BY the push, so its timestamp tracks
        # the ref update rather than the commit. `pushedDate` would be
        # the direct answer and GitHub returns null for it (verified on
        # this repo), so this is the closest signal that actually exists.
        #
        # It lands a beat AFTER the true push — CI takes a moment to
        # register — so an ask made in those seconds reads as predating
        # the head and can produce a premature exit 5. That is
        # self-correcting: the answer says to ask again, and the next ask
        # is past the window. The alternative bound, the committer date,
        # fails in the direction that matters more — it makes exit 5
        # unreachable on any rebased head.
        # SCOPED TO THIS PR'S REF, because a check suite belongs to a
        # commit and a commit can appear in more than one place. Both
        # terms are load-bearing.
        #
        # The unfiltered lookup returns every suite the SHA ever had —
        # another branch, an earlier PR, an earlier appearance on this
        # same ref — and taking the oldest then reaches back before this
        # PR's ref update. An ask made in between reads as newer than
        # the head, stays falsely in flight, and the exit-5 callback
        # never fires.
        #
        # `pull_requests` alone is not enough to fix that, because how
        # GitHub populates it is UNDOCUMENTED: the REST reference
        # describes the field's shape and never states the match rule,
        # so "same sha, same repo" cannot be ruled out. Under that rule
        # a suite raised by any branch sharing this sha would carry this
        # PR number, and since a sha really can hold several suites
        # minutes apart — 2d4e1844 here has one at 12:19:33 from the
        # merge-queue ref and one at 12:31:52 from main — the latest of
        # them would date the head from a push this PR never had. That
        # overshoots, and an ask in between then reads as stale: a
        # premature exit 5, the confidently-wrong direction.
        #
        # `head_branch` is the term that does not depend on the unknown
        # rule. A suite raised by a push to this PR's ref carries this
        # PR's branch by construction, and one raised anywhere else
        # cannot, whatever `pull_requests` says. The PR number then
        # still earns its place: a branch can outlive the PR opened from
        # it, so the same ref can carry suites belonging to an earlier
        # one.
        #
        # EARLIEST of this PR's suites, and the direction is the whole
        # point. A sha can acquire a later suite on this same ref, under
        # this same PR number, from something that never moved the ref:
        # a manual `workflow_dispatch` against the branch (this repo has
        # dispatch-only workflows), a schedule, a re-run, or a
        # close/reopen — `reopened` is a default `pull_request` activity
        # type and the bare trigger in ci.yml fires on it. Taking the
        # LATEST dates the head from whichever of those happened last,
        # an ask made before it reads as stale, and a review sitting on
        # an earlier commit turns that into "no review is coming" while
        # the one asked for is in flight. That is the confidently-wrong
        # direction and it is NOT self-correcting: nothing prompts a
        # re-ask.
        #
        # Filtering by what RAISED the suite cannot fix this. The
        # workflow-run listing exposes `.event`, which is
        # `pull_request` for `opened`, `synchronize` AND `reopened`
        # alike — the activity type is not in the API (checked: no
        # `action` field on a run) — so a reopen is indistinguishable
        # from a push by event name. Ordering is the term that does not
        # depend on telling them apart: whatever a later suite was
        # raised by, it is not the push that created the head.
        #
        # Taking the earliest fails only in the safe direction. It can
        # date the head EARLIER than the true ref update (a branch
        # pushed before its PR existed carries no PR number until the PR
        # opens), which makes an ask read as newer than the head and
        # stay in flight — a longer wait, the trade this whole block is
        # written around. It can never date the head later than a
        # candidate suite, which is the failure that produces a false
        # exit 5.
        #
        # This REPLACES the earlier preference for the latest suite,
        # which existed for one case: a sha pushed, replaced, then
        # restored by force-push, where the oldest suite dates the head
        # from the first appearance and an ask made while the
        # intervening head was current stays falsely in flight. That
        # case is rarer than the ones above (no PR in this repo has ever
        # been force-pushed OR reopened; §Always forbids force-pushing
        # without an explicit request), and its failure is the SAFE
        # direction — "stays in flight" is a longer wait, not a verdict.
        # The old choice traded the safe failure for the unsafe one.
        #
        # Suites from `merge_group` or a push to main carry another ref
        # and drop out, which is right. So do ALL of them once the PR
        # is merged and its branch deleted: GitHub empties
        # `pull_requests` then, so
        # a merged PR — which this command deliberately keeps polling —
        # falls through to the commit date below. That is a degradation,
        # not a failure, and it is why the fallback is not optional.
        #
        # The ref is spliced in as a jq-ESCAPED literal, not between
        # bare quotes. `gh api --jq` takes no `--arg`, so the value has
        # to travel inside the filter text, and a branch name is
        # attacker-adjacent input: git permits a `"` in a ref, which
        # would close the string early and leave the rest of the name
        # parsed as jq.
        local head_born head_ref_lit
        head_ref_lit="$(jq -n --arg b "$head_ref" '$b')"
        # PAGINATED, and reduced ACROSS pages. `per_page` defaults to 30
        # on this endpoint and the response is a page, not the set — so
        # `first` over a single request is the earliest of page ONE.
        # Suites are returned oldest-first today, which would make page
        # one the right page by luck; that ordering is not documented,
        # and this block already refuses to depend on an undocumented
        # property of this same endpoint (see the PR-number term above).
        #
        # `gh api --paginate` applies `--jq` to EACH page and prints one
        # result per page, so the filter yields one candidate per page
        # and the reduction has to happen here rather than inside jq.
        #
        # NOT `filter=all`: this endpoint takes no `filter` parameter —
        # its documented query parameters are app_id, check_name,
        # per_page and page, and passing filter=latest, filter=all or a
        # bogus value returns byte-identical results. The per-app
        # collapse `latest` performs belongs to the check-RUNS endpoint;
        # here the bare request returns several suites from the same app.
        head_born="$(gh api --paginate "repos/$REPO/commits/$head/check-suites" \
            --jq "[.check_suites[]
                   | select(.head_branch == $head_ref_lit)
                   | select([.pull_requests[]?.number] | index($PR))
                   | .created_at] | sort | first // empty" \
            2>/dev/null | sort | head -1)" || head_born=""
        # No suite ran, or the lookup failed: fall back to the commit's
        # own date, then to "pending". Both cost a longer wait rather
        # than a false "nothing is coming".
        if [[ -z "$head_born" ]]; then
            head_born="$(gh api "repos/$REPO/commits/$head" \
                --jq '.commit.committer.date' 2>/dev/null)" || head_born=""
        fi
        if [[ -z "$head_born" || "$request_at" > "$head_born" ]]; then
            request_pending=yes
        fi
        # A refusal that arrived after the ask still answers it.
        [[ -n "$refusal_at" && "$refusal_at" > "$request_at" ]] && request_pending=no
        # ...and so does the review it asked for. The exit paths never
        # reach here with a covered head — head_reviewed wins first — so
        # this changes no decision. It changes what the REPORT says, and
        # a line reading "nothing has answered it yet" beside
        # "head reviewed? yes" is simply false. Observed on #501.
        [[ "$head_reviewed" == "yes" ]] && request_pending=no
    fi

    # Only a COMPLETE probe counts. `head` is set before the reviews
    # lookup that may be the thing that fails, so it cannot stand in for
    # "we have readable data" — the fall-out path would otherwise render
    # a zero-coverage report from review globals that were never set, and
    # crash on an unset variable under `set -u`.
    probe_ok=1
    return 0
}

# Nothing is coming. Requires ALL of: a previous counted review (so this
# is not a fresh PR the owning session has yet to review), a head that
# has moved past it, and no pending request. Any one of those missing
# and waiting is still the right move.
no_review_coming() {
    # A prior VERDICT comment is equally evidence that this PR is one the
    # reviewer answers, so it satisfies the "not a fresh PR" term just as
    # a review object does.
    [[ "$head_reviewed" == "no" ]] \
        && (( qual_count + verdict_count > 0 )) \
        && (( requested == 0 )) \
        && [[ "$request_pending" != "yes" ]]
}

# ── The full report, rendered once ───────────────────────────────────
fetch_extras() {
    # Unresolved threads no longer gate the merge (the ruleset dropped
    # required_review_thread_resolution on 2026-08-06), so they belong in
    # this glance more than ever — nothing else will raise them.
    # A FAILED LOOKUP IS "unknown", never 0: a caller that arms on
    # "no unresolved threads" read a query error as a clean PR (a
    # project's arm tool, found 2026-09-25). JSON says null.
    if threads="$(gh api graphql -f query='
      query($owner:String!,$name:String!,$pr:Int!){
        repository(owner:$owner,name:$name){
          pullRequest(number:$pr){
            reviewThreads(first:100){nodes{isResolved isOutdated path}}}}}' \
      -F owner="${REPO%%/*}" -F name="${REPO##*/}" -F pr="$PR" \
      --jq '[.data.repository.pullRequest.reviewThreads.nodes[]|select(.isResolved==false)]' 2>/dev/null)" \
      && jq -e 'type == "array"' <<<"$threads" >/dev/null 2>&1; then
        unresolved="$(jq 'length' <<<"$threads")"
    else
        threads='[]'; unresolved="unknown"
    fi

    checks_pass="$(gh pr checks "$PR" --repo "$REPO" 2>/dev/null | grep -cE '\spass\s' || true)"
    checks_other="$(gh pr checks "$PR" --repo "$REPO" 2>/dev/null | grep -vcE '\spass\s' || true)"
}

render() {
    local threads unresolved checks_pass checks_other
    fetch_extras
    if (( JSON )); then render_json; else render_text; fi
}

# THE --json CONTRACT. Built with jq from the same values the report
# prints, so the two cannot disagree; a caller reads fields, never the
# report's prose, whose wording is free to change.
render_json() {
    jq -n --arg pr "$PR" --arg state "$state" --arg mergest "$mergest" --arg head "$head" \
          --arg head_reviewed "$head_reviewed" --arg unresolved "$unresolved" \
          --argjson independent "$independent" --argjson blind "$blind" \
          --argjson others "$marked_others" --argjson verdicts "$verdicts" \
          --argjson outsiders "$outsiders" --arg ncause "$no_coming_cause" --arg nreason "$no_coming_reason" \
          --argjson self_count "$self_count" --argjson threads "$threads" \
          --arg cpass "$checks_pass" --arg cother "$checks_other" '{
        pr: ($pr | tonumber), state: $state, merge_state: $mergest, head: $head,
        head_reviewed: $head_reviewed,
        independent: {count: ($independent | length),
                      rows: [$independent[] | {login: .user.login, state, commit_sha8: .commit_id[0:8], at: .submitted_at}]},
        blind: {count: ($blind | length),
                rows: [$blind[] | {login: .user.login, commit_sha8: .commit_id[0:8], at: .submitted_at}]},
        not_trusted: {count: ($outsiders | length),
                      rows: [$outsiders[] | {login: .user.login, association: .author_association, commit_sha8: .commit_id[0:8], at: .submitted_at}]},
        no_review_coming: (if $ncause == "" then null else {cause: $ncause, reason: (if $nreason == "" then null else $nreason end)} end),
        marked_by_others: {count: ($others | length),
                           rows: [$others[] | {login: .user.login, commit_sha8: .commit_id[0:8], at: .submitted_at}]},
        verdicts: {count: ($verdicts | length),
                   rows: [$verdicts[] | {login, commit_sha8: .sha[0:8], at}]},
        self: {count: $self_count},
        unresolved_threads: (if $unresolved == "unknown" then null else ($unresolved | tonumber) end),
        unresolved_paths: [$threads[] | .path],
        checks: {pass: ($cpass | tonumber? // 0), other: ($cother | tonumber? // 0)}
    }'
}

# " — <what covers the head>", or nothing when it is not reviewed. The
# blind review says that it is the review class under the shared account,
# so "independent reviews : 0" above it is not read as no review at all.
head_evidence() {
    [[ "$head_reviewed" == yes ]] || return 0
    local row
    row="$(jq -r --arg h "$head" '[.[] | select(.commit_id == $h)] | sort_by(.submitted_at) | last
          | select(. != null) | "\(.commit_id[0:8]), \(.submitted_at)"' <<<"$blind")"
    if [[ -n "$row" ]]; then
        printf ' — the review class'"'"'s blind review of %s (posted under the account every session pushes as)' "$row"
        return 0
    fi
    row="$(jq -r --arg h "$head" '[.[] | select(.commit_id == $h)] | sort_by(.submitted_at) | last
          | select(. != null) | "\(.user.login), \(.commit_id[0:8]), \(.submitted_at)"' <<<"$independent")"
    if [[ -n "$row" ]]; then printf ' — an independent review (%s)' "$row"; return 0; fi
    printf ' — a verdict comment on this head'
}

render_text() {
    printf 'PR #%s  state=%s  mergeState=%s  head=%s\n' \
        "$PR" "$state" "$mergest" "${head:0:8}"
    printf '  independent reviews : %s' "$ind_count"
    if (( qual_count > 0 )); then
        printf '   (newest against %s)' "${newest_ind_commit:0:8}"
    fi
    printf '\n'
    if (( ind_count > 0 )); then
        jq -r '.[] | "      - \(.user.login)  \(.state)  commit=\(.commit_id[0:8])  \(.submitted_at)"' \
            <<<"$independent"
    fi
    printf '  verdict comments    : %s' "$verdict_count"
    if (( verdict_count > 0 )); then
        printf '   (a clean review leaves no review object)'
    fi
    printf '\n'
    if (( verdict_count > 0 )); then
        jq -r '.[] | "      - \(.login)  commit=\(.sha[0:8])  \(.at)"' <<<"$verdicts"
    fi
    printf '  blind reviews       : %s%s\n' "$blind_count" \
        "$( (( blind_count > 0 )) \
              && echo '   (the review class — coverage)' \
              || echo '' )"
    if (( blind_count > 0 )); then
        jq -r '.[] | "      - \(.user.login)  commit=\(.commit_id[0:8])  \(.submitted_at)"' <<<"$blind"
    fi
    if (( outsiders_count > 0 )); then
        printf '  not trusted         : %s   (NOT coverage — not the owner, a member, a collaborator or a configured reviewer)\n' "$outsiders_count"
        jq -r '.[] | "      - \(.user.login)  \(.author_association)  commit=\(.commit_id[0:8])  \(.submitted_at)"' <<<"$outsiders"
    fi
    if (( others_count > 0 )); then
        printf '  marked, other login : %s   (NOT coverage — the marker is public; only the\n' "$others_count"
        printf '                        account the sessions push as may post a blind review)\n'
        jq -r '.[] | "      - \(.user.login)  commit=\(.commit_id[0:8])  \(.submitted_at)"' <<<"$marked_others"
    fi
    printf '  self reviews        : %s   (thread replies etc. — not coverage)\n' "$self_count"
    printf '  review requested?   : %s\n' "$( (( requested > 0 )) && echo yes || echo no )"
    if [[ -n "$request_at" ]]; then
        printf '  review asked        : %s%s\n' "$request_at" \
            "$( [[ "$request_pending" == "yes" ]] \
                  && echo '   (in flight — nothing has answered it yet)' \
                  || echo '   (already answered)' )"
    fi
    if [[ -n "$refusal_at" ]]; then
        printf '  reviewer declined   : %s%s\n' "$refusal_at" \
            "$( [[ "$refusal_current" == "yes" ]] \
                  && echo "   (nothing has superseded it)" \
                  || echo "   (superseded by later coverage)" )"
        [[ -z "$refusal_reason" ]] || printf '  decline reason      : %s\n' "$refusal_reason"
    fi
    # The line names what covers the head, because it is the one a
    # reader keeps: agents trim this report with `tail`, and a verdict
    # whose evidence sits at the top reads, trimmed, as "NOT coverage"
    # twice and a bare yes. That is what a permission check saw before
    # refusing an owner-approved arm as a merge without review (a managed
    # project's PR). The parsers read only the first word after the colon.
    printf '  head reviewed?      : %s%s\n' "$head_reviewed" "$(head_evidence)"
    if [[ "$head_reviewed" == "no" && "$qual_count" -gt 0 ]]; then
        printf '                        ^ reviewed, but an EARLIER commit. Nothing reviews a\n'
        printf '                          push by itself — dispatch a re-review of the new range.\n'
    fi
    printf '  unresolved threads  : %s\n' "$unresolved"
    if [[ "$unresolved" != unknown ]] && (( unresolved > 0 )); then
        jq -r '.[] | "      - \(.path)  outdated=\(.isOutdated)"' <<<"$threads"
    fi
    printf '  checks              : %s pass, %s other\n' "$checks_pass" "$checks_other"
}

# ── Poll ─────────────────────────────────────────────────────────────
#
# A single failed lookup is a blip, not a verdict; only a run of them
# means the PR is genuinely unreadable. Same tolerance as wait-merged.sh.
consecutive_failures=0
deadline=$(( SECONDS + WAIT ))

while :; do
    if probe; then
        consecutive_failures=0

        if [[ "$head_reviewed" == "yes" ]]; then
            render; exit 0
        fi

        # TERMINAL STATE FIRST. A PR closed without merging will receive
        # nothing further. A MERGED one still can, and routinely does
        # here — that is the whole reason the post-merge sweep exists —
        # so it keeps waiting.
        if [[ "$state" == "CLOSED" ]]; then
            render; exit 1
        fi

        # ...which is why exit 5 is restricted to an OPEN pr. Run before
        # the state check, no_review_coming fires on a MERGED pr whose
        # only review predates the last push, and tells the caller to go
        # request one — contradicting the merged-pr exception written
        # directly above it, and sending them away from the sweep that
        # was about to deliver a review.
        #
        # Not hypothetical: a review asked on a merged pr has been
        # answered within a minute here, so a merged pr is a perfectly
        # ordinary thing to be waiting on.
        # A REFUSAL is the same verdict from a different cause, so it
        # takes the same exit — which is exactly why it must be tested
        # FIRST. Both conditions are true together whenever an older
        # review sits on a previous head and the reviewer has since
        # declined: no_review_coming fires on the stale review, and the
        # caller is told to request another one. That advice cannot work
        # while the reviewer is refusing, and naming the real cause is
        # the whole point of this branch.
        #
        # Still after the coverage and terminal tests above: a covered
        # head reports 0, and a refusal a later review superseded is
        # already excluded by refusal_current.
        #
        # Gated on OPEN for the same reason the test below is: a merged
        # pr keeps waiting, and the sweep that reviews it runs long
        # after whatever made it decline has passed.
        if [[ "$state" == "OPEN" && "$refusal_current" == "yes" ]]; then
            note "the reviewer declined this PR — no review will arrive without a change"
            no_coming_cause="reviewer-declined"; no_coming_reason="$refusal_reason"
            render
            (( JSON )) || printf 'PR #%s NO REVIEW COMING — the reviewer declined%s (exit 5)\n' "$PR" \
                "$( [[ -z "$refusal_reason" ]] || printf ': %s' "$refusal_reason" )"
            exit 5
        fi

        if [[ "$state" == "OPEN" ]] && no_review_coming; then
            note "head has advanced past the newest review and none is requested"
            no_coming_cause="head-moved"
            render
            (( JSON )) || printf 'PR #%s NO REVIEW COMING — the head moved past every review; dispatch a re-review (exit 5)\n' "$PR"
            exit 5
        fi
    else
        consecutive_failures=$(( consecutive_failures + 1 ))
        (( consecutive_failures >= 3 )) && die "could not read PR #$PR in $REPO."
        note "could not read PR #$PR (attempt $consecutive_failures); retrying"
    fi

    (( WAIT > 0 )) || break
    # Clamp the nap to what is left, exactly as wait-merged.sh does.
    # Breaking whenever a WHOLE interval no longer fits made `--wait`
    # mean "the last deadline a full interval lands on": `--wait 10s`
    # against the default 30s interval polled once and exited on the
    # spot, and any wait that is not a multiple of the interval ended up
    # to one interval early. The deadline is the deadline.
    remaining=$(( deadline - SECONDS ))
    (( remaining > 0 )) || break
    nap=$(( INTERVAL < remaining ? INTERVAL : remaining ))
    note "no independent review of ${head:0:8} yet; next check in ${nap}s"
    sleep "$nap"
done

# Fell out: either one-shot, or the wait expired with nothing. Requires a
# probe that COMPLETED — `head` alone is not enough, because it is set
# before the reviews lookup that may be the thing that failed.
if (( probe_ok == 0 )) || [[ -z "${head:-}" ]]; then
    die "could not read PR #$PR in $REPO."
fi
render
exit 1
