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
from github.review_status.probe import PR_FIELDS, TIMELINE_QUERY, THREADS_QUERY  # noqa: E402, F401
from github.review_status.probe import THREAD_PAGES, review_threads, Probe, head_born  # noqa: E402, F401
from github.review_status.probe import formal_request_at, probe, no_review_coming, Extras  # noqa: E402, F401
from github.review_status.probe import fetch_extras  # noqa: E402, F401


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
