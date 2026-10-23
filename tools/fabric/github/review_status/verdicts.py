"""tools/fabric/github/review_status/verdicts.py — reviews and verdict comments read into what counts for the head.
A part of tools/fabric/github/pr_review_status.py, whose docstring is the contract."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from github import review_coverage
from github.review_status.base import jkey, login_of
from github.review_status.config import TRUSTED_ASSOCIATIONS, Config


# The reviewer's verdict comment: the sha in the body is abbreviated.
VERDICT_SHA = re.compile(r"Reviewed commit:[^`]*`(?P<sha>[0-9a-f]{7,40})`", re.IGNORECASE)


# post_review writes `<!-- model: <name> -->` on the line after the marker; "codex" is the second engine
# (agent-fabric ADR-053), anything else, or no model, is the review class's own.
MODEL_LINE = re.compile(r"^<!-- model: (?P<model>[^>]*?) -->$", re.MULTILINE)


def engine_of(review: dict) -> str:
    """"codex" for a review posted with `--model codex`, else "claude". Read from the header only (the first
    two lines; three for a v2 review, whose second line may be the partial-coverage line), never the body's text,
    which quotes code and may carry such a line."""
    body = review.get("body") or ""
    header = "\n".join(body.split("\n")[:3 if body.startswith(review_coverage.V2_PREFIX) else 2])
    m = MODEL_LINE.search(header)
    return "codex" if m and m.group("model").strip().lower() == "codex" else "claude"


# The marker review_codex posts when its engine cannot run on a head (the allowance is spent, the gateway is down):
# an additional engine's stand-in for that exact head, never a review (arm_policy.additional_engines). It is read
# only as the FIRST LINE of a review object, by the account a blind review counts from (classify), so a stranger
# who posts it skips nothing. The reason is one word: it goes into the arming basis and the gate line as written.
UNAVAILABLE = re.compile(r"<!-- agent-fabric-engine-unavailable v1 engine=(?P<engine>[a-z]+) head=(?P<head>[0-9a-f]{40,64})"
                         r" reason=(?P<reason>[A-Za-z0-9._:-]+) at=(?P<at>[^\s>]+) -->")


def unavailable_of(review: dict) -> dict | None:
    """{engine, head, reason, at} of a review whose first line is the unavailable marker, else None."""
    m = UNAVAILABLE.fullmatch((review.get("body") or "").split("\n", 1)[0].rstrip("\r"))
    return m.groupdict() if m else None


PASS_LINE = re.compile(r"\spass\s")


# ── what counts ─────────────────────────────────────────────────────────

@dataclass
class Buckets:
    independent: list = field(default_factory=list)
    outsiders: list = field(default_factory=list)
    blind: list = field(default_factory=list)
    unavailable: list = field(default_factory=list)
    marked_others: list = field(default_factory=list)
    # Reviews of the poster's own that carry a v2 marker and are not coverage: a path not read, a block that does not
    # read, a marker naming another commit than the one the review is on. Shown, never counted.
    partial: list = field(default_factory=list)
    self_: list = field(default_factory=list)

    @property
    def qualifying(self) -> list:
        """WHAT COUNTS AS COVERAGE: every independent review, and every
        blind review — reported on its own line, so provenance survives."""
        return self.independent + self.blind


def uncounted_v2(review: dict) -> str:
    """Why a review whose first line opens a v2 marker is not coverage of the commit it is on, or "" when it is (or
    when it is no v2 review). The marker's head must be the commit the review was posted on: post-review writes both
    from one header, so a disagreement is a review that did not come from it."""
    v2 = review_coverage.read_review(review.get("body") or "")
    if v2 is None:
        return ""
    if not v2.counts:
        return v2.why_not[:200]
    if v2.marker.head != review.get("commit_id"):
        return f"the marker names head {v2.marker.head[:8]}, the review is on {str(review.get('commit_id'))[:8]}"
    return ""


def classify(reviews: list[dict], author: str, cfg: Config) -> Buckets:
    """Independent = not authored by the PR author. The empty-body test is
    NOT used to classify: a genuine reviewer may leave an empty-bodied
    review carrying only inline comments. Authorship is the honest axis.
    MARKED FIRST, then authorship. A blind review is authored by the same
    account as everything else, so classifying by author first loses it;
    and a marked review is never an independent one — gating the marker test
    on authorship made a marked review from another login count as genuine
    independent coverage, silently, in the dangerous direction. It is blind
    only from the author or a named poster (below), and otherwise counts as
    nothing.

    startswith, NOT contains. The emitter guarantees the marker is the
    FIRST LINE; a substring test counted any review whose body merely
    QUOTED the marker — reviewing this mechanism is enough to do it — and
    subtracted that review from `self` at the same time. A false "this was
    reviewed" is worse than the under-counting this whole change exists to
    fix. The current marker and every legacy one the forwarder names: a
    review starts with one of them or it is unmarked."""
    def is_marked(r: dict) -> bool:
        body = r.get("body") or ""
        return any(body.startswith(m) for m in cfg.markers) or body.startswith(review_coverage.V2_PREFIX)

    def trusted(r: dict) -> bool:
        """AN INDEPENDENT REVIEWER IS SOMEONE THE REPOSITORY TRUSTS: its
        owner, a member of its organisation, or a collaborator, as GitHub's
        own `author_association` says. On a public repository anyone can
        review; binding only the MARKED review to its poster left a
        stranger's unmarked review counting as coverage (the review of #41,
        2026-09-26). Any other account's review is reported as not
        coverage. A configured reviewer (AGENT_FABRIC_VERDICT_AUTHORS) is
        trusted by name: a GitHub App's review carries the association
        NONE."""
        return r.get("author_association") in TRUSTED_ASSOCIATIONS or login_of(r) in cfg.verdict_authors

    # An engine's unavailable marker is no review, from anyone: from the account a blind review counts from it stands
    # in for that engine on its head (b.unavailable), from any other it is reported as a marked review is, and it is
    # never an independent review or one of the author's thread replies.
    gone = [r for r in reviews if not is_marked(r) and unavailable_of(r)]
    marked = [r for r in reviews if is_marked(r)]
    unmarked = [r for r in reviews if not is_marked(r) and r not in gone]
    b = Buckets()
    b.independent = [r for r in unmarked if login_of(r) != author and trusted(r)]
    b.outsiders = [r for r in unmarked if login_of(r) != author and not trusted(r)]
    # BLIND REVIEWS ARE COVERAGE, and authorship cannot see them. Every
    # session pushes as the SAME account, so the review class's review,
    # posted by the session that owns the PR, is authored by the PR author
    # and would fall into `self` — the bucket labelled "thread replies …
    # not coverage". The marker is what tells them apart: an exact string
    # fabric-pr post-review emits and nothing else produces by accident.
    # AND THE POSTER IS BOUND. The marker is published in every tree that
    # carries fabric-pr post-review, so on a public repository any account can
    # post a review whose first line is the marker; counting it made a
    # stranger's review the head's coverage, indistinguishable in the
    # report (a blind review of a managed project, 2026-09-25). A marked
    # review counts only from the PR author or a named poster; any other is
    # reported, login and all, as not coverage.
    posted = [r for r in marked if login_of(r) == author or login_of(r) in cfg.review_posters]
    # A v2 review is coverage only when its block reads and every path is read (ADR-065 §5 rule 4); v1 as before.
    b.blind = [r for r in posted if not uncounted_v2(r)]
    b.partial = [r for r in posted if uncounted_v2(r)]
    b.unavailable = [r for r in gone if login_of(r) == author or login_of(r) in cfg.review_posters]
    b.marked_others = [r for r in marked + gone if login_of(r) != author and login_of(r) not in cfg.review_posters]
    b.self_ = [r for r in unmarked if login_of(r) == author]
    return b


def verdicts_of(comments: list[dict], author: str, cfg: Config) -> list[dict]:
    """A comment from a CONFIGURED automated reviewer that names the commit
    it reviewed. The sha in the body is abbreviated, so the head is matched
    on prefix in BOTH directions (see head_covered) — neither string is
    reliably the longer one.

    The sha is READ, never inferred from "a comment arrived after the push":
    a verdict can arrive after a push and still describe the commit before
    it, and a confident wrong answer there is exactly what this script
    exists to avoid."""
    rows = []
    try:
        for c in comments:
            if login_of(c) not in cfg.verdict_authors or login_of(c) == author:
                continue
            m = VERDICT_SHA.search(c.get("body") or "")
            if m:
                rows.append({"login": login_of(c), "at": c.get("created_at"), "sha": m.group("sha")})
    except (AttributeError, TypeError):
        return []
    return rows


def newest(values) -> str:
    """`sort | last // ""` over timestamps that may be null."""
    vs = sorted(values, key=jkey)
    return vs[-1] if vs and vs[-1] is not None else ""


def refusal_of(comments: list[dict], cfg: Config) -> tuple[str, str]:
    """(when, reason). REFUSALS. A configured automated reviewer may decline
    in the same comment stream and from the same account. That is not
    slowness, it is a review that will not happen — exactly the state exit 5
    exists to name — but nothing in the review objects says so, so a wait
    would otherwise sit out its whole timeout. Matched on the reviewer's own
    wording (AGENT_FABRIC_REVIEWER_REFUSAL_RE), never on a "sounds negative"
    heuristic: a wrong positive abandons a review that was merely slow, the
    more expensive mistake. Empty pattern: no refusals.

    THE REASON, read off the same comment: the first line of the reviewer's
    own words, so the status line says what the reviewer said and never
    reads as a refusal of THIS diff when it was not."""
    if cfg.refusal_re is None:
        return "", ""
    try:
        from_reviewer = [c for c in comments if login_of(c) in cfg.verdict_authors]
        at = newest(c.get("created_at") for c in from_reviewer if cfg.refusal_re.search(c.get("body") or ""))
        if not at:
            return "", ""
        bodies = [c.get("body") or "" for c in from_reviewer if c.get("created_at") == at]
        lines = [l for l in (bodies[0] if bodies else "").replace("\r", "").split("\n") if l]
        return at, (lines[0] if lines else "")[:160]
    except (AttributeError, TypeError):
        return "", ""


def request_of(comments: list[dict], cfg: Config) -> str:
    """A PENDING REQUEST, read from the same comment stream when a project
    asks its automated reviewer with a phrase
    (AGENT_FABRIC_REVIEW_REQUEST_RE) rather than a GitHub review request. NO
    allow-list here, deliberately: this signal can only turn 5 ("nothing is
    coming") into 1 ("not yet") — it never marks a head reviewed, so the
    worst a forged request can do is make the tool wait longer. Empty
    pattern: no requests."""
    if cfg.request_re is None:
        return ""
    try:
        return newest(c.get("created_at") for c in comments if cfg.request_re.search(c.get("body") or ""))
    except (AttributeError, TypeError):
        return ""


def head_covered(head: str, verdicts: list[dict], qualifying: list[dict]) -> bool:
    """Either kind of evidence counts, and a verdict comment is checked even
    when there are no review objects at all — a PR whose only review came
    back CLEAN has none.

    COVERAGE IS "ANY review targets head", NOT "the newest one does". A
    review opened before the last push but SUBMITTED after a fresh one is
    newer by timestamp and older by commit, so selecting by recency lets a
    stale review mask a real one — and this script would then call the head
    unreviewed while the review it wanted was already sitting there. The
    newest is kept for REPORTING only."""
    if any(head.startswith(v["sha"]) or v["sha"].startswith(head) for v in verdicts):
        return True
    return any(r.get("commit_id") == head for r in qualifying)
