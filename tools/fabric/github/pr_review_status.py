#!/usr/bin/env python3
"""tools/fabric/github/pr_review_status.py — has THE HEAD of this PR been
reviewed, by a reviewer other than the author or by the review class's
blind review? (ADR-040 Wave 1; runtime/github/pr-review-status.sh is its
shim, and the managed projects' tools/gh/pr-review-status.sh forward to that
path. Lifted from the first managed project's tools/gh/ on 2026-09-19; it is
general to every managed project.)

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      <pr-number> [owner/repo] [--wait <duration>] [--interval
            <duration>] [-q|--quiet] [--json] [-h|--help]
            Parsed left to right, each error at the argument that causes it;
            a value option takes the NEXT argument whatever it is; -h/--help
            prints and exits 0 at once, so an earlier bad argument wins.
            The first two non-option words are the PR and the repository
            (an EMPTY word is skipped, as the bash skipped it); a third is
            refused. Any other word starting with `-` is refused.
            Durations: 90, 90s, 10m, 2h; a bare number is SECONDS. --wait
            defaults to 0 (answer once), --interval to 30 and must be above
            zero. Without owner/repo, the repository is the working copy's.
  env       AGENT_FABRIC_VERDICT_AUTHORS    JSON array of logins, default []
            AGENT_FABRIC_REVIEW_POSTERS     JSON array of logins, default []
            AGENT_FABRIC_REVIEWER_REFUSAL_RE  regex, default empty
            AGENT_FABRIC_REVIEW_REQUEST_RE    regex, default empty
            AGENT_FABRIC_LEGACY_REVIEW_MARKERS  earlier markers, one per line
            An unset or EMPTY variable is its default. A list that is not a
            JSON array of strings, or a pattern the regex engine refuses, is
            exit 2 naming the variable, never read as "none".
  stdin     not read
  stdout    the report (or, with --json, ONE object, also on exit 5), then
            for exit 5 without --json the `NO REVIEW COMING` line
  stderr    every refusal, prefixed `pr-review-status: `, and progress notes
            with the same prefix unless -q
  exit      0  the current head has at least one counted review — ANY of
               them, not merely the most recent — or a configured
               reviewer's verdict comment naming it
            1  it does not: nothing yet, --wait expired, or the PR was
               closed without merging
            2  invocation problem (no gh, not authenticated, unknown PR,
               a bad configuration), or the PR could not be read — including
               a reviews or comments lookup that FAILED, never reported as
               "no reviews"
            5  no review is COMING, on an OPEN pr: permanent, do not wait.
               The head advanced past every counted review with none
               requested, or a configured automated reviewer declined
  help      HELP below, byte for byte what the bash printed from its own
            header
  lines     stdout and stderr are flushed in program order, so a caller that
            merges the two (2>&1) sees the order the bash printed in

WHAT IS NOT THE BASH'S (ADR-040 §5 rule 6): jq is gone, so a regex in
AGENT_FABRIC_REVIEWER_REFUSAL_RE / _REQUEST_RE is Python's `re`, not jq's
Oniguruma. POSIX classes ([[:space:]]) and (?<name>...) are translated
(onig_to_py); the rest of the two dialects agree on what a reviewer's
wording needs. A bash integer with a leading zero is octal, so `--wait 010`
waited 8 seconds; `--wait 08` polled once, like no --wait, after bash's
arithmetic error on stderr, and `--wait 08m` was exit 2; all kept
(bash_int). So is the bash's abort (exit 1, `head: unbound variable`) when
the first poll cannot read the PR and a wait follows. The two messages of
bash's own carry no script path or line number here. `gh` calls are bounded (gh.py's 60 s) where the bash was
not, and the checks are asked once where the bash asked twice.

WHY (carried from the bash header): two GitHub behaviours make the obvious
reading wrong, and both bit this repo.
  1. Replying to a review thread (addPullRequestReviewThreadReply) creates
     a REVIEW object with an empty body, authored by you. Three
     self-replies look like three new reviews. On one PR that made a
     self-authored thread look like independent coverage.
  2. A review comment's `commit_id` is re-anchored to the CURRENT head
     whenever the file it points at has not changed. A finding written
     against an old commit therefore DISPLAYS as though it were evaluated
     against code that did not exist when it was written.
     `original_commit_id` is the honest field.
So: classify by MARKER then by AUTHOR, and compare each counted review's
commit against headRefOid. Everything else is noise.

WHAT COUNTS. Three buckets, reported on their own lines:
  independent reviews — review objects by an account other than the PR
      author that the repository trusts: its owner, an organisation member
      or a collaborator (GitHub's author_association), or a login named in
      AGENT_FABRIC_VERDICT_AUTHORS (an App's review carries the
      association NONE). Every session pushes as one account, so this is a
      person, not another session; anyone else's review is listed as "not
      trusted" and is not coverage;
  blind reviews — the review class's reviews, posted by post-review.sh as
      review objects whose FIRST LINE is REVIEW_MARKER, BY the account the
      sessions push as — the PR author, or one named in
      AGENT_FABRIC_REVIEW_POSTERS: the fabric's review of every PR,
      dispatched by the session that owns it and judged before it is
      answered. A marked review by any other account is reported, with its
      login, and is NOT coverage: the marker is published in every tree,
      and on a public repository anyone can post it;
  self reviews — the author's own thread replies; not coverage.
A head is reviewed when an independent or a blind review targets it.

AN AUTOMATED REVIEWER is not assumed. A project that runs one names its
accounts in AGENT_FABRIC_VERDICT_AUTHORS; then a review object from one of
them is independent coverage whatever its association, a comment from one
of them naming `Reviewed commit: <sha>` counts as a verdict on that sha,
the phrases in AGENT_FABRIC_REVIEWER_REFUSAL_RE read as that reviewer
declining (exit 5, the cause named), and a comment matching
AGENT_FABRIC_REVIEW_REQUEST_RE reads as a pending request. All three are
empty by default: no verdicts, no refusals, no requests — the review class
is the review.

WAITING (--wait). Nothing reviews a push by itself: a session dispatches
the review class and posts its review. So `--wait` is for a review known to
be in flight (another session's, a person's), and there are two "no review
yet" states: never reviewed — wait, up to the timeout; reviewed, then
pushed — nothing will arrive on its own, a re-review of the new range is
owed, and it exits 5 IMMEDIATELY with the cause rather than burning the
timeout, on an OPEN pr. A MERGED pr keeps waiting (a review can still
land on it); a pr CLOSED without merging ends the wait at 1.

ONE PROBE sets the state the loop branches on. It is kept apart from
rendering so a poll costs three API calls, not the whole report: the thread
and check queries are for the human reading the final answer, and running
them every 30 seconds would be rude to the rate limiter for output nobody
sees.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
# Every name the parts define, from here as before: callers and tests reach
# them as pr_review_status.<name> (pr_gate, post_review, tests/test_pr_review_status.py).
from github.review_status.base import PROG, Die, out, err, jstr, sha8, jkey, login_of  # noqa: E402, F401
from github.review_status.cli import HELP, OctalError, bash_int, as_seconds, Args, parse  # noqa: E402, F401
from github.review_status.config import REVIEW_MARKER, BUILTIN_LEGACY_MARKER  # noqa: E402, F401
from github.review_status.config import TRUSTED_ASSOCIATIONS, POSIX_CLASSES, onig_to_py  # noqa: E402, F401
from github.review_status.config import compile_re, logins, Config, read_config  # noqa: E402, F401
from github.review_status.verdicts import VERDICT_SHA, PASS_LINE, Buckets, classify  # noqa: E402, F401
from github.review_status.verdicts import verdicts_of, newest, refusal_of, request_of  # noqa: E402, F401
from github.review_status.verdicts import head_covered  # noqa: E402, F401


PR_FIELDS = ["state", "mergeStateStatus", "headRefOid", "headRefName", "author", "isDraft", "reviewRequests"]


# `${owner}`/`${name}`/`${pr}` are GraphQL VARIABLES: the bash spliced them
# into the query text, the port never does (ADR-040 §5 rule 6).
TIMELINE_QUERY = """query($owner: String!, $name: String!, $pr: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr) {
      timelineItems(last: 50, itemTypes: [REVIEW_REQUESTED_EVENT]) {
        nodes { ... on ReviewRequestedEvent { createdAt
          requestedReviewer {
            ... on User { login }
            ... on Bot  { login }
            ... on Team { login: slug } } } } } } } }"""


THREADS_QUERY = """query($owner:String!,$name:String!,$pr:Int!,$after:String){
  repository(owner:$owner,name:$name){
    pullRequest(number:$pr){
      reviewThreads(first:100,after:$after){nodes{isResolved isOutdated path}
        pageInfo{hasNextPage endCursor}}}}}"""


# A page is 100 threads: past it the count was short and read as whole
# (review of #71). Pages are followed to the end; a PR with more than
# THREAD_PAGES of them is "unknown", never a count of the first ones.
THREAD_PAGES = 50


def review_threads(owner: str, name: str, pr: int, after: str | None = None) -> list[dict]:
    """Every review thread of the PR from `after` on, page by page. Raises
    gh.GhError (or a lookup error on a malformed answer) when any page
    cannot be read, and ValueError past THREAD_PAGES pages."""
    nodes: list[dict] = []
    for _ in range(THREAD_PAGES):
        data = gh.graphql(THREADS_QUERY, owner=owner, name=name, pr=pr, after=after)
        page = data["repository"]["pullRequest"]["reviewThreads"]
        nodes += page["nodes"]
        info = page.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            return nodes
        after = info.get("endCursor")
        if not after:
            raise ValueError("a next page of review threads with no cursor")
    raise ValueError(f"more than {THREAD_PAGES * 100} review threads")


# ── One probe ───────────────────────────────────────────────────────────

@dataclass
class Probe:
    head: str = ""
    state: str = ""
    mergest: str = ""
    requested: int = 0
    buckets: Buckets = field(default_factory=Buckets)
    verdicts: list = field(default_factory=list)
    refusal_at: str = ""
    refusal_reason: str = ""
    refusal_current: bool = False
    request_at: str = ""
    request_pending: bool = False
    head_reviewed: bool = False
    newest_ind_commit: str = ""

    @property
    def qual_count(self) -> int:
        return len(self.buckets.qualifying)


def head_born(repo: str, pr: str, head: str, head_ref: str) -> str:
    """WHEN THE HEAD BECAME THE HEAD, which is not when its commit was
    written.

    `.commit.committer.date` is metadata carried inside the commit, so it
    says nothing about the ref. A cherry-picked, rebased or amended commit
    keeps a date that can long predate the ask, and even an ordinary one
    drifts: ba20a29e on #501 was committed at 11:48:37 and pushed at 12:06 —
    eighteen minutes in which an ask would have been misattributed to a head
    that did not yet exist on the remote.

    The check suite is created BY the push, so its timestamp tracks the ref
    update rather than the commit. `pushedDate` would be the direct answer
    and GitHub returns null for it (verified on this repo), so this is the
    closest signal that actually exists.

    It lands a beat AFTER the true push — CI takes a moment to register — so
    an ask made in those seconds reads as predating the head and can
    produce a premature exit 5. That is self-correcting: the answer says to
    ask again, and the next ask is past the window. The alternative bound,
    the committer date, fails in the direction that matters more — it makes
    exit 5 unreachable on any rebased head.

    SCOPED TO THIS PR'S REF, because a check suite belongs to a commit and a
    commit can appear in more than one place. Both terms are load-bearing.

    The unfiltered lookup returns every suite the SHA ever had — another
    branch, an earlier PR, an earlier appearance on this same ref — and
    taking the oldest then reaches back before this PR's ref update. An ask
    made in between reads as newer than the head, stays falsely in flight,
    and the exit-5 callback never fires.

    `pull_requests` alone is not enough to fix that, because how GitHub
    populates it is UNDOCUMENTED: the REST reference describes the field's
    shape and never states the match rule, so "same sha, same repo" cannot
    be ruled out. Under that rule a suite raised by any branch sharing this
    sha would carry this PR number, and since a sha really can hold several
    suites minutes apart — 2d4e1844 here has one at 12:19:33 from the
    merge-queue ref and one at 12:31:52 from main — the latest of them would
    date the head from a push this PR never had. That overshoots, and an ask
    in between then reads as stale: a premature exit 5, the
    confidently-wrong direction.

    `head_branch` is the term that does not depend on the unknown rule. A
    suite raised by a push to this PR's ref carries this PR's branch by
    construction, and one raised anywhere else cannot, whatever
    `pull_requests` says. The PR number then still earns its place: a branch
    can outlive the PR opened from it, so the same ref can carry suites
    belonging to an earlier one.

    EARLIEST of this PR's suites, and the direction is the whole point. A
    sha can acquire a later suite on this same ref, under this same PR
    number, from something that never moved the ref: a manual
    `workflow_dispatch` against the branch (this repo has dispatch-only
    workflows), a schedule, a re-run, or a close/reopen — `reopened` is a
    default `pull_request` activity type and the bare trigger in ci.yml
    fires on it. Taking the LATEST dates the head from whichever of those
    happened last, an ask made before it reads as stale, and a review
    sitting on an earlier commit turns that into "no review is coming" while
    the one asked for is in flight. That is the confidently-wrong direction
    and it is NOT self-correcting: nothing prompts a re-ask.

    Filtering by what RAISED the suite cannot fix this. The workflow-run
    listing exposes `.event`, which is `pull_request` for `opened`,
    `synchronize` AND `reopened` alike — the activity type is not in the API
    (checked: no `action` field on a run) — so a reopen is indistinguishable
    from a push by event name. Ordering is the term that does not depend on
    telling them apart: whatever a later suite was raised by, it is not the
    push that created the head.

    Taking the earliest fails only in the safe direction. It can date the
    head EARLIER than the true ref update (a branch pushed before its PR
    existed carries no PR number until the PR opens), which makes an ask
    read as newer than the head and stay in flight — a longer wait, the
    trade this whole block is written around. It can never date the head
    later than a candidate suite, which is the failure that produces a false
    exit 5.

    This REPLACES the earlier preference for the latest suite, which existed
    for one case: a sha pushed, replaced, then restored by force-push, where
    the oldest suite dates the head from the first appearance and an ask
    made while the intervening head was current stays falsely in flight.
    That case is rarer than the ones above (no PR in this repo has ever been
    force-pushed OR reopened; §Always forbids force-pushing without an
    explicit request), and its failure is the SAFE direction — "stays in
    flight" is a longer wait, not a verdict. The old choice traded the safe
    failure for the unsafe one.

    Suites from `merge_group` or a push to main carry another ref and drop
    out, which is right. So do ALL of them once the PR is merged and its
    branch deleted: GitHub empties `pull_requests` then, so a merged PR —
    which this command deliberately keeps polling — falls through to the
    commit date below. That is a degradation, not a failure, and it is why
    the fallback is not optional.

    The ref is compared as a value. The bash spliced it into a jq filter as
    an escaped literal because `gh api --jq` takes no `--arg` and a branch
    name is attacker-adjacent input (git permits a `"` in a ref, which would
    close the string early and leave the rest of the name parsed as jq);
    here it never becomes program text.

    PAGINATED, and reduced ACROSS pages. `per_page` defaults to 30 on this
    endpoint and the response is a page, not the set — so the earliest of a
    single request is the earliest of page ONE. Suites are returned
    oldest-first today, which would make page one the right page by luck;
    that ordering is not documented, and this block already refuses to
    depend on an undocumented property of this same endpoint (see the
    PR-number term above).

    NOT `filter=all`: this endpoint takes no `filter` parameter — its
    documented query parameters are app_id, check_name, per_page and page,
    and passing filter=latest, filter=all or a bogus value returns
    byte-identical results. The per-app collapse `latest` performs belongs
    to the check-RUNS endpoint; here the bare request returns several
    suites from the same app.

    No suite ran, or the lookup failed: fall back to the commit's own date,
    then to "" (pending). Both cost a longer wait rather than a false
    "nothing is coming"."""
    born = ""
    try:
        suites = gh.api(f"repos/{repo}/commits/{head}/check-suites", paginate=True, items_key="check_suites") or []
        dates = [s.get("created_at") for s in suites
                 if s.get("head_branch") == head_ref
                 and int(pr) in [p.get("number") for p in (s.get("pull_requests") or [])]
                 and s.get("created_at") is not None]
        born = min(dates) if dates else ""
    except (gh.GhError, ValueError, TypeError, AttributeError):
        born = ""
    if not born:
        try:
            born = gh.api(f"repos/{repo}/commits/{head}")["commit"]["committer"]["date"] or ""
        except (gh.GhError, ValueError, TypeError, KeyError):
            born = ""
    return born


def formal_request_at(repo: str, pr: str, pending_logins: list[str]) -> str:
    """When the newest FORMAL request for a reviewer still pending was made.

    `requested` is a COUNT and carries no ordering. A request that was
    already pending when the reviewer declined stays in reviewRequests
    afterwards, so clearing the refusal on the count alone marks it
    superseded by the very request it answered, and the command then waits
    out its whole timeout instead of reporting the decline. That is the same
    mistake the comment path does NOT make — it compares request_at against
    refusal_at — reintroduced one line away while fixing the asymmetry
    between the two ask mechanisms. The ordering has to come from the
    timeline, because the count cannot supply it.

    MATCHED TO A REVIEWER STILL BEING AWAITED, not merely the latest event on
    the pr. Discarding requestedReviewer made any later request for anyone
    clear the configured reviewer's refusal, because a person had since been
    asked. The identity has to be read. And the event has to name someone
    STILL ON THE REQUEST LIST. The timeline keeps a REVIEW_REQUESTED_EVENT
    after the request is withdrawn, so a human asked after the decline and
    then removed without reviewing leaves a later event and no pending
    request. `pending_others` correctly sees nobody waiting; an unrestricted
    filter here still took that stale event as a supersession, cleared the
    refusal, and the command waited out its timeout instead of reporting the
    decline it had in hand. Requiring the reviewer to be currently pending
    is what ties the event to a request that can still be answered.

    Unreadable, or no event found: "" — the refusal stands. The decline is
    the thing we actually observed; discarding it on evidence we could not
    read would trade a fact for a guess."""
    owner, name = repo.split("/", 1)[0], repo.rsplit("/", 1)[-1]
    try:
        data = gh.graphql(TIMELINE_QUERY, owner=owner, name=name, pr=int(pr))
        nodes = data["repository"]["pullRequest"]["timelineItems"]["nodes"]
        return newest(n.get("createdAt") for n in nodes
                      if ((n.get("requestedReviewer") or {}).get("login") or "") in pending_logins)
    except (gh.GhError, ValueError, TypeError, KeyError, AttributeError):
        return ""


def probe(ctx: "Ctx") -> Probe | None:
    """None is an UNREADABLE pr: a failed call, never an empty answer.
    Only a COMPLETE probe is returned — `head` is set before the reviews
    lookup that may be the thing that fails, so it cannot stand in for "we
    have readable data"; the bash reset its flag on entry for the same
    reason (a probe that overwrote `head` and then failed on reviews would
    otherwise leave the flag standing from an EARLIER successful probe, and
    the report would pair the new head with the old review data — a
    mismatch that reads as authoritative). A fresh Probe per call cannot
    carry that."""
    cfg = ctx.cfg
    p = Probe()
    try:
        meta = gh.pr_view(ctx.pr, PR_FIELDS, repo=ctx.repo)
        p.head = ctx.head = jstr(meta.get("headRefOid"))
        head_ref = meta.get("headRefName") or ""
        p.state = jstr(meta.get("state"))
        p.mergest = jstr(meta.get("mergeStateStatus"))
        ctx.author = jstr((meta.get("author") or {}).get("login"))
        requests = meta.get("reviewRequests") or []
        p.requested = len(requests)
        # Everyone still on the request list who is NOT a configured
        # automated reviewer. A decline answers the reviewer who made it and
        # nobody else, and any of these would satisfy the question — so
        # their pending requests have to survive it.
        pending_logins = [r.get("login") or r.get("slug") or "" for r in requests]
        pending_others = sum(1 for l in pending_logins if l not in cfg.verdict_authors)

        # PAGINATED, and a failure here reads UNREADABLE — never empty. This
        # script's whole job is answering "was this really reviewed", so
        # turning a rate limit, a permission gap or a transient 5xx into `[]`
        # produces the confident wrong answer "no reviews" and lets a caller
        # conclude a reviewed pr was never looked at. Returning None feeds
        # the consecutive-failure counter instead, which is what the exit-2
        # contract already promises for an unreadable pr.
        #
        # Unpaginated, a pr with more review objects than one REST page
        # silently lost the rest — plausible here precisely because this
        # script documents that thread replies create review objects, so the
        # count climbs with correspondence rather than with coverage.
        reviews = gh.api(f"repos/{ctx.repo}/pulls/{ctx.pr}/reviews", paginate=True) or []
        p.buckets = classify(reviews, ctx.author, cfg)

        # VERDICT COMMENTS. Unreadable rather than empty, for the same reason
        # the reviews call is: a swallowed failure here would report a clean
        # review as no review, which is the whole defect this fetch fixes.
        comments = gh.api(f"repos/{ctx.repo}/issues/{ctx.pr}/comments", paginate=True) or []
    except (gh.GhError, ValueError, TypeError, AttributeError):
        return None

    p.verdicts = verdicts_of(comments, ctx.author, cfg)
    p.refusal_at, p.refusal_reason = refusal_of(comments, cfg)
    p.request_at = request_of(comments, cfg)

    qualifying = p.buckets.qualifying
    p.head_reviewed = head_covered(p.head, p.verdicts, qualifying)
    if qualifying:
        p.newest_ind_commit = jstr(sorted(qualifying, key=lambda r: jkey(r.get("submitted_at")))[-1].get("commit_id"))

    # A refusal only speaks for the CURRENT state. The reviewer recovers —
    # whatever made it decline passes — and a verdict or review arriving
    # afterwards supersedes it. So the refusal counts only when nothing newer
    # has landed; otherwise a refusal from last week would end every wait on
    # this PR forever.
    if p.refusal_at:
        evidence = newest([r.get("submitted_at") for r in qualifying] + [v["at"] for v in p.verdicts])
        # ...and to a request made AFTER it. The cause passes and the
        # environment gets created, so asking again once the cause is gone
        # is the normal recovery — a decline that predates the re-ask is
        # spent, not standing.
        if p.refusal_at > evidence and (not p.request_at or not p.request_at > p.refusal_at):
            p.refusal_current = True

    # A FORMAL re-request also supersedes it — but only one made AFTER the
    # refusal. Fetched only when there IS a refusal to supersede AND a
    # request that might do it, so the common path pays nothing.
    if p.refusal_at and p.requested > 0:
        formal_at = formal_request_at(ctx.repo, ctx.pr, pending_logins)
        if formal_at and formal_at > p.refusal_at:
            p.refusal_current = False

    # A DECLINE ANSWERS THE REVIEWER WHO MADE IT, AND NOBODY ELSE.
    #
    # The question is "did anyone independent look", so a person's review is
    # coverage. A configured reviewer saying it will not review is not an
    # answer about a person who is still on the request list — and the
    # refusal exit fires ahead of `no_review_coming`, which would have kept
    # waiting on that pending request. Without this the command reports "no
    # review is coming" while one is: the confidently-wrong direction again.
    #
    # The result is a longer wait, not a verdict: with a request still
    # pending, `no_review_coming` cannot fire either, so the command keeps
    # polling until the review lands or the window closes.
    if pending_others > 0:
        p.refusal_current = False

    # A request newer than every review, verdict and refusal means one is in
    # flight. AN ASK IS FOR A PARTICULAR HEAD, and the test is whether it
    # postdates that head — NOT whether some review happens to be newer than
    # it.
    #
    # Timestamps alone got this wrong in both directions. A review of an
    # EARLIER commit can land after a newer head was pushed and asked about;
    # counting it as the answer returned "no review is coming" while the real
    # one was still in flight. That is recency mistaken for coverage, the
    # same confusion 8c678d79 fixed for the head-reviewed test itself.
    #
    # Requiring a HEAD-MATCHING review to answer the ask — the obvious
    # repair — breaks the other direction: asked, reviewed, then pushed again
    # without asking. No review will ever match the new head, so the ask
    # would stay pending forever and exit 5 could never fire, which is the
    # one thing it exists to say. The head's own birth separates the two
    # cleanly, so that is what is compared.
    #
    # Fetched only when there IS an ask, so the common path keeps its three
    # calls.
    if p.request_at:
        born = head_born(ctx.repo, ctx.pr, p.head, head_ref)
        if not born or p.request_at > born:
            p.request_pending = True
        # A refusal that arrived after the ask still answers it.
        if p.refusal_at and p.refusal_at > p.request_at:
            p.request_pending = False
        # ...and so does the review it asked for. The exit paths never reach
        # here with a covered head — head_reviewed wins first — so this
        # changes no decision. It changes what the REPORT says, and a line
        # reading "nothing has answered it yet" beside "head reviewed? yes"
        # is simply false. Observed on #501.
        if p.head_reviewed:
            p.request_pending = False
    return p


def no_review_coming(p: Probe) -> bool:
    """Nothing is coming. Requires ALL of: a previous counted review (so this
    is not a fresh PR the owning session has yet to review), a head that has
    moved past it, and no pending request. Any one of those missing and
    waiting is still the right move. A prior VERDICT comment is equally
    evidence that this PR is one the reviewer answers, so it satisfies the
    "not a fresh PR" term just as a review object does."""
    return (not p.head_reviewed and p.qual_count + len(p.verdicts) > 0
            and p.requested == 0 and not p.request_pending)


# ── The full report, rendered once ──────────────────────────────────────

@dataclass
class Extras:
    threads: list
    unresolved: int | None
    checks_pass: int
    checks_other: int


def fetch_extras(ctx: "Ctx") -> Extras:
    """Unresolved threads no longer gate the merge (the ruleset dropped
    required_review_thread_resolution on 2026-08-06), so they belong in this
    glance more than ever — nothing else will raise them. A FAILED LOOKUP IS
    "unknown" (None), never 0: a caller that arms on "no unresolved threads"
    read a query error as a clean PR (a project's arm tool, found
    2026-09-25). JSON says null."""
    owner, name = ctx.repo.split("/", 1)[0], ctx.repo.rsplit("/", 1)[-1]
    try:
        nodes = review_threads(owner, name, int(ctx.pr))
        threads = [n for n in nodes if n.get("isResolved") is False]
        unresolved = len(threads)
    except (gh.GhError, ValueError, TypeError, KeyError, AttributeError):
        threads, unresolved = [], None
    # `gh pr checks` exits 8 while a check is pending and 1 while one fails,
    # and prints its table either way: the count reads what it printed.
    try:
        table = gh.run(["pr", "checks", ctx.pr, "--repo", ctx.repo], what=f"gh pr checks {ctx.pr}")
    except gh.GhError as e:
        table = e.stdout
    rows = table.split("\n")
    if rows and rows[-1] == "":
        rows.pop()
    passed = sum(1 for r in rows if PASS_LINE.search(r))
    return Extras(threads, unresolved, passed, len(rows) - passed)


def render_json(ctx: "Ctx", p: Probe, x: Extras, cause: str, reason: str) -> str:
    """THE --json CONTRACT. Built from the same values the report prints, so
    the two cannot disagree; a caller reads fields, never the report's prose,
    whose wording is free to change."""
    b = p.buckets

    def rows(reviews, *keys):
        shape = {"login": lambda r: login_of(r), "state": lambda r: r.get("state"),
                 "association": lambda r: r.get("author_association"),
                 "commit_sha8": lambda r: sha8(r.get("commit_id")), "at": lambda r: r.get("submitted_at")}
        return [{k: shape[k](r) for k in keys} for r in reviews]

    try:
        pr_number = int(ctx.pr)
    except ValueError:
        pr_number = float(ctx.pr)
    doc = {
        "pr": pr_number, "state": p.state, "merge_state": p.mergest, "head": p.head,
        "head_reviewed": "yes" if p.head_reviewed else "no",
        "independent": {"count": len(b.independent), "rows": rows(b.independent, "login", "state", "commit_sha8", "at")},
        "blind": {"count": len(b.blind), "rows": rows(b.blind, "login", "commit_sha8", "at")},
        "not_trusted": {"count": len(b.outsiders), "rows": rows(b.outsiders, "login", "association", "commit_sha8", "at")},
        "no_review_coming": None if not cause else {"cause": cause, "reason": reason or None},
        "marked_by_others": {"count": len(b.marked_others), "rows": rows(b.marked_others, "login", "commit_sha8", "at")},
        "verdicts": {"count": len(p.verdicts),
                     "rows": [{"login": v["login"], "commit_sha8": sha8(v["sha"]), "at": v["at"]} for v in p.verdicts]},
        "self": {"count": len(b.self_)},
        "unresolved_threads": x.unresolved,
        "unresolved_paths": [t.get("path") for t in x.threads],
        "checks": {"pass": x.checks_pass, "other": x.checks_other},
    }
    return json.dumps(doc, indent=2, ensure_ascii=False)


def head_evidence(p: Probe) -> str:
    """" — <what covers the head>", or nothing when it is not reviewed. The
    blind review says that it is the review class under the shared account,
    so "independent reviews : 0" above it is not read as no review at all."""
    if not p.head_reviewed:
        return ""

    def at_head(rows):
        hit = sorted((r for r in rows if r.get("commit_id") == p.head), key=lambda r: jkey(r.get("submitted_at")))
        return hit[-1] if hit else None

    r = at_head(p.buckets.blind)
    if r:
        return (f" — the review class's blind review of {jstr(sha8(r.get('commit_id')))}, {jstr(r.get('submitted_at'))}"
                " (posted under the account every session pushes as)")
    r = at_head(p.buckets.independent)
    if r:
        return f" — an independent review ({jstr(login_of(r))}, {jstr(sha8(r.get('commit_id')))}, {jstr(r.get('submitted_at'))})"
    return " — a verdict comment on this head"


def render_text(ctx: "Ctx", p: Probe, x: Extras) -> None:
    b = p.buckets
    out(f"PR #{ctx.pr}  state={p.state}  mergeState={p.mergest}  head={p.head[:8]}")
    line = f"  independent reviews : {len(b.independent)}"
    if p.qual_count > 0:
        line += f"   (newest against {p.newest_ind_commit[:8]})"
    out(line)
    for r in b.independent:
        out(f"      - {jstr(login_of(r))}  {jstr(r.get('state'))}  commit={jstr(sha8(r.get('commit_id')))}  {jstr(r.get('submitted_at'))}")
    line = f"  verdict comments    : {len(p.verdicts)}"
    if p.verdicts:
        line += "   (a clean review leaves no review object)"
    out(line)
    for v in p.verdicts:
        out(f"      - {jstr(v['login'])}  commit={jstr(sha8(v['sha']))}  {jstr(v['at'])}")
    out(f"  blind reviews       : {len(b.blind)}" + ("   (the review class — coverage)" if b.blind else ""))
    for r in b.blind:
        out(f"      - {jstr(login_of(r))}  commit={jstr(sha8(r.get('commit_id')))}  {jstr(r.get('submitted_at'))}")
    if b.outsiders:
        out(f"  not trusted         : {len(b.outsiders)}   (NOT coverage — not the owner, a member, a collaborator or a configured reviewer)")
        for r in b.outsiders:
            out(f"      - {jstr(login_of(r))}  {jstr(r.get('author_association'))}  commit={jstr(sha8(r.get('commit_id')))}  {jstr(r.get('submitted_at'))}")
    if b.marked_others:
        out(f"  marked, other login : {len(b.marked_others)}   (NOT coverage — the marker is public; only the")
        out("                        account the sessions push as may post a blind review)")
        for r in b.marked_others:
            out(f"      - {jstr(login_of(r))}  commit={jstr(sha8(r.get('commit_id')))}  {jstr(r.get('submitted_at'))}")
    out(f"  self reviews        : {len(b.self_)}   (thread replies etc. — not coverage)")
    out(f"  review requested?   : {'yes' if p.requested > 0 else 'no'}")
    if p.request_at:
        out(f"  review asked        : {p.request_at}"
            + ("   (in flight — nothing has answered it yet)" if p.request_pending else "   (already answered)"))
    if p.refusal_at:
        out(f"  reviewer declined   : {p.refusal_at}"
            + ("   (nothing has superseded it)" if p.refusal_current else "   (superseded by later coverage)"))
        if p.refusal_reason:
            out(f"  decline reason      : {p.refusal_reason}")
    # The line names what covers the head, because it is the one a reader
    # keeps: agents trim this report with `tail`, and a verdict whose
    # evidence sits at the top reads, trimmed, as "NOT coverage" twice and a
    # bare yes. That is what a permission check saw before refusing an
    # owner-approved arm as a merge without review (a managed project's PR).
    # The parsers read only the first word after the colon.
    out(f"  head reviewed?      : {'yes' if p.head_reviewed else 'no'}{head_evidence(p)}")
    if not p.head_reviewed and p.qual_count > 0:
        out("                        ^ reviewed, but an EARLIER commit. Nothing reviews a")
        out("                          push by itself — dispatch a re-review of the new range.")
    out(f"  unresolved threads  : {'unknown' if x.unresolved is None else x.unresolved}")
    if x.unresolved:
        for t in x.threads:
            out(f"      - {jstr(t.get('path'))}  outdated={jstr(t.get('isOutdated'))}")
    out(f"  checks              : {x.checks_pass} pass, {x.checks_other} other")


# ── Poll ────────────────────────────────────────────────────────────────

@dataclass
class Ctx:
    pr: str
    repo: str
    cfg: Config
    args: Args
    author: str = ""
    # Whole wall-clock seconds, like bash's $SECONDS (a difference of
    # time(), so it ticks on the clock's second boundary, not a full second
    # after the start): the deadline arithmetic below was written against it.
    t0: int = field(default_factory=lambda: int(time.time()))
    # Not reset by a failed poll, as the bash's `head` was not: None is the
    # bash's unset variable.
    head: str | None = None

    def seconds(self) -> int:
        return int(time.time()) - self.t0

    def note(self, msg: str) -> None:
        if not self.args.quiet:
            err(f"{PROG}: {msg}")

    def render(self, p: Probe, cause: str = "", reason: str = "") -> None:
        x = fetch_extras(self)
        if self.args.json:
            out(render_json(self, p, x, cause, reason))
        else:
            render_text(self, p, x)


def run(argv: list[str], env=None) -> int:
    env = os.environ if env is None else env
    args = parse(argv)
    if args is None:
        return 0
    if not args.pr:
        raise Die("a PR number is required (try --help)")
    if shutil.which("gh") is None:
        raise Die("gh is required but not installed.")
    repo = args.repo
    if not repo:
        try:
            repo = gh.run(["repo", "view", "--json", "nameWithOwner"], what="gh repo view")
            repo = json.loads(repo)["nameWithOwner"]
        except (gh.GhError, ValueError, KeyError, TypeError):
            raise Die("could not determine the repository; pass owner/repo.") from None
    ctx = Ctx(args.pr, repo, read_config(env), args)

    try:
        wait = bash_int(args.wait)
    except OctalError as e:
        # The bash's arithmetic failed at the deadline and at the `WAIT > 0`
        # test, neither of which stopped it: it polled once, like no --wait,
        # with bash's own message on stderr even under -q.
        err(f"{PROG}: --wait: {e}")
        wait = 0
    interval = bash_int(args.interval)
    deadline = ctx.seconds() + wait
    # A single failed lookup is a blip, not a verdict; only a run of them
    # means the PR is genuinely unreadable. Same tolerance as wait-merged.sh.
    failures = 0
    p: Probe | None = None
    while True:
        p = probe(ctx)
        if p is not None:
            failures = 0
            if p.head_reviewed:
                ctx.render(p)
                return 0
            # TERMINAL STATE FIRST. A PR closed without merging will receive
            # nothing further. A MERGED one still can, and routinely does
            # here — that is the whole reason the post-merge sweep exists —
            # so it keeps waiting.
            if p.state == "CLOSED":
                ctx.render(p)
                return 1
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
            if p.state == "OPEN" and p.refusal_current:
                ctx.note("the reviewer declined this PR — no review will arrive without a change")
                ctx.render(p, "reviewer-declined", p.refusal_reason)
                if not args.json:
                    suffix = f": {p.refusal_reason}" if p.refusal_reason else ""
                    out(f"PR #{ctx.pr} NO REVIEW COMING — the reviewer declined{suffix} (exit 5)")
                return 5
            if p.state == "OPEN" and no_review_coming(p):
                ctx.note("head has advanced past the newest review and none is requested")
                ctx.render(p, "head-moved")
                if not args.json:
                    out(f"PR #{ctx.pr} NO REVIEW COMING — the head moved past every review; dispatch a re-review (exit 5)")
                return 5
        else:
            failures += 1
            if failures >= 3:
                raise Die(f"could not read PR #{ctx.pr} in {ctx.repo}.")
            ctx.note(f"could not read PR #{ctx.pr} (attempt {failures}); retrying")

        if not wait > 0:
            break
        # Clamp the nap to what is left, exactly as wait-merged.sh does.
        # Breaking whenever a WHOLE interval no longer fits made `--wait`
        # mean "the last deadline a full interval lands on": `--wait 10s`
        # against the default 30s interval polled once and exited on the
        # spot, and any wait that is not a multiple of the interval ended up
        # to one interval early. The deadline is the deadline.
        remaining = deadline - ctx.seconds()
        if not remaining > 0:
            break
        nap = min(interval, remaining)
        if ctx.head is None:
            # The bash's `${head:0:8}` under `set -u`: a first poll that
            # could not even read the PR, then a wait, aborted the script
            # with status 1 and bash's message, before the third failure
            # could say "could not read". Kept, not fixed.
            err(f"{PROG}: head: unbound variable")
            return 1
        ctx.note(f"no independent review of {ctx.head[:8]} yet; next check in {nap}s")
        time.sleep(nap)

    # Fell out: either one-shot, or the wait expired with nothing. Requires a
    # probe that COMPLETED — `head` alone is not enough, because it is set
    # before the reviews lookup that may be the thing that failed.
    if p is None or not p.head:
        raise Die(f"could not read PR #{ctx.pr} in {ctx.repo}.")
    ctx.render(p)
    return 1


def main() -> int:
    try:
        return run(sys.argv[1:])
    except Die as e:
        err(f"{PROG}: {e}")
        return e.code


if __name__ == "__main__":
    sys.exit(main())
