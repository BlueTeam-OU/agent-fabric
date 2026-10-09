"""tools/fabric/github/review_status/probe.py — GitHub asked: the PR, its timeline, its review threads, one probe of the head.
A part of tools/fabric/github/pr_review_status.py, whose docstring is the contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import gh
from github.review_status.base import jstr, jkey, listed, obj
from github.review_status.verdicts import PASS_LINE, Buckets, classify, verdicts_of, newest, refusal_of, request_of, head_covered

if TYPE_CHECKING:
    from github.pr_review_status import Ctx


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
        more, info = listed(page["nodes"]), obj(page.get("pageInfo"))
        if more is None or info is None:
            raise TypeError("a page of review threads that is not a list of objects with its pageInfo")
        nodes += more
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
    # None is "unknown", as `unresolved` is: the checks could not be read.
    checks_pass: int | None
    checks_other: int | None


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
    # and prints its table either way: the count reads what it printed. A
    # failure that printed no table is unknown — a 502 or a timeout read as
    # "0 pass, 0 other" looked like a head with no checks — except gh's own
    # "no checks reported", which is a real zero (gh.no_checks_reported).
    try:
        table = gh.run(["pr", "checks", ctx.pr, "--repo", ctx.repo], what=f"gh pr checks {ctx.pr}")
    except gh.GhError as e:
        if gh.no_checks_reported(e):
            table = ""
        elif e.code in (1, 8) and e.stdout.strip():
            table = e.stdout
        else:
            return Extras(threads, unresolved, None, None)
    rows = table.split("\n")
    if rows and rows[-1] == "":
        rows.pop()
    passed = sum(1 for r in rows if PASS_LINE.search(r))
    return Extras(threads, unresolved, passed, len(rows) - passed)
