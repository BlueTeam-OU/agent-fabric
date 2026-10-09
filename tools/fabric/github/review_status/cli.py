"""tools/fabric/github/review_status/cli.py — the command line: --help, the bash's integer and duration rules, the parsed arguments.
A part of tools/fabric/github/pr_review_status.py, whose docstring is the contract."""
from __future__ import annotations

import re
from dataclasses import dataclass
from github.review_status.base import Die, out


HELP = """Has THE HEAD of this PR been reviewed — by a reviewer other than the
author, or by the review class's blind review? A raw `gh pr view`
cannot answer that.

Two GitHub behaviours make the obvious reading wrong, and both bit
this repo:

  1. Replying to a review thread (addPullRequestReviewThreadReply)
     creates a REVIEW object with an empty body, authored by you.
     Three self-replies look like three new reviews. On one PR that
     made a self-authored thread look like independent coverage.

  2. A review comment's `commit_id` is re-anchored to the CURRENT
     head whenever the file it points at has not changed. A finding
     written against an old commit therefore DISPLAYS as though it
     were evaluated against code that did not exist when it was
     written. `original_commit_id` is the honest field.

So: classify by MARKER then by AUTHOR, and compare each counted
review's commit against headRefOid. Everything else is noise.

WHAT COUNTS. Three buckets, reported on their own lines:
  independent reviews — review objects by an account other than the
                        PR author that the repository trusts: its
                        owner, an organisation member or a collaborator
                        (GitHub's author_association), or a login named
                        in AGENT_FABRIC_VERDICT_AUTHORS (an App's review
                        carries the association NONE). Every session
                        pushes as one account, so this is a person, not
                        another session; anyone else's review is listed
                        as "not trusted" and is not coverage;
  blind reviews       — the review class's reviews, posted by
                        post-review.sh as review objects whose FIRST
                        LINE is REVIEW_MARKER (below), BY the account
                        the sessions push as — the PR author, or one
                        named in AGENT_FABRIC_REVIEW_POSTERS: the
                        fabric's review of every PR, dispatched by the
                        session that owns it and judged before it is
                        answered. A marked review by any other account
                        is reported, with its login, and is NOT
                        coverage: the marker is published in every
                        tree, and on a public repository anyone can
                        post it;
  self reviews        — the author's own thread replies; not coverage.
A head is reviewed when an independent or a blind review targets it.

An AUTOMATED REVIEWER is not assumed. A project that runs one names
its accounts in AGENT_FABRIC_VERDICT_AUTHORS (a JSON array); then a
review object from one of them is independent coverage whatever its
association, a comment from one of them naming `Reviewed commit: <sha>` counts as a
verdict on that sha, the phrases in AGENT_FABRIC_REVIEWER_REFUSAL_RE
read as that reviewer declining (exit 5, the cause named), and a
comment matching AGENT_FABRIC_REVIEW_REQUEST_RE reads as a pending
request. All three are empty by default: no verdicts, no refusals, no
requests — the review class is the review.

WAITING (--wait). Nothing reviews a push by itself: a session
dispatches the review class and posts its review. So `--wait` is for
a review known to be in flight (another session's, a person's), and
there are two "no review yet" states:

  * never reviewed          — wait, up to the timeout.
  * reviewed, then pushed   — nothing will arrive on its own; a
                              re-review of the new range is owed.
                              Exits 5 IMMEDIATELY with the cause,
                              rather than burning the timeout.

...on an OPEN pr. A MERGED pr keeps waiting (a review can still land
on it); a pr CLOSED without merging ends the wait at 1.

Usage:
  pr-review-status.sh <pr-number> [owner/repo] [options]

Options:
  --wait <duration>      poll until the head is reviewed (default 0 =
                         answer once and exit)
  --interval <duration>  between polls (default 30; the API is rate
                         limited and reviewers are slow)
  -q, --quiet            no progress lines on stderr
  --json                 the final answer as one JSON object on stdout
                         instead of the report (the exit code is the
                         same): state, merge_state, head,
                         head_reviewed, the three buckets as
                         {count, rows}, marked_by_others, not_trusted,
                         no_review_coming ({cause, reason} or null),
                         verdicts, unresolved_threads (null when the
                         lookup failed), checks {pass, other} (both
                         null when the lookup failed)
  -h, --help             this text

Durations take an optional unit — 90, 90s, 10m, 2h. A bare number is
SECONDS.

Exit codes:
  0  the current head has at least one counted review — ANY of them,
     not merely the most recent, which can be older by commit than
     one submitted before it — or a configured reviewer's verdict
     comment naming it
  1  it does not — nothing yet, --wait expired still waiting, or the
     pr was closed without merging
  2  invocation problem (no gh, not authenticated, unknown PR), or the
     pr could not be read — including a reviews or comments lookup that
     FAILED, which is never reported as "no reviews"
  5  no review is COMING on its own, on an OPEN pr: the head advanced
     past every counted review with none requested — a re-review is
     owed — or a configured automated reviewer declined (the `decline
     reason` line says which phrase). Never returned for a merged pr."""


# ── arguments ───────────────────────────────────────────────────────────

class OctalError(ValueError):
    """bash's own arithmetic error, in its words (without the script path and
    line number bash put in front, which a module cannot reproduce)."""


def bash_int(digits: str) -> int:
    """A digit string as bash's `$(( ))` reads it: a leading zero is OCTAL,
    and an 8 or 9 in one is bash's own error. The bash did arithmetic on
    these and nothing else, so `--wait 010` was 8 seconds; that is kept
    rather than fixed (ADR-040: the port moves the tool, it does not change
    it)."""
    if len(digits) > 1 and digits.startswith("0"):
        try:
            return int(digits, 8)
        except ValueError:
            raise OctalError(f'{digits}: value too great for base (error token is "{digits}")') from None
    return int(digits)


def as_seconds(flag: str, raw: str) -> str:
    """Durations take an optional unit: 90, 90s, 10m, 2h. A BARE NUMBER IS
    SECONDS — which is what every existing invocation already meant, so
    nothing changes for a caller that passed one. The result is a string,
    as the bash's was: a bare number comes back unchanged, which is how
    `--interval 010` is refused below while `--interval 010m` is 480.

    The table stands alone, pinned by this script's own suite. A project
    that keeps a waiter of its own with the same units asserts its copy in
    its own suite; the fabric's suite cannot see it, so nothing here claims
    the two agree."""
    bad = Die(f"{flag} needs a duration like 90, 90s, 10m or 2h, got '{raw}'.")
    if raw == "" or any(c not in "0123456789smh" for c in raw):
        raise bad
    n = raw[:-1] if raw[-1] in "smh" else raw
    if not (n.isascii() and n.isdigit()):
        raise bad
    # Inside the bash's `$(as_seconds ...)`: its arithmetic error ended the
    # substitution with a status, which the caller turned into exit 2.
    try:
        if raw.endswith("h"):
            return str(bash_int(n) * 3600)
        if raw.endswith("m"):
            return str(bash_int(n) * 60)
    except OctalError as e:
        raise Die(str(e)) from None
    return n


@dataclass
class Args:
    pr: str = ""
    repo: str = ""
    wait: str = "0"
    interval: str = "30"
    quiet: bool = False
    json: bool = False


def parse(argv: list[str]) -> Args | None:
    """None when --help was printed."""
    a = Args()
    i = 0
    while i < len(argv):
        w = argv[i]
        if w in ("--wait", "--interval"):
            if i + 1 >= len(argv):
                raise Die(f"{w} needs a value (try --help).")
            secs = as_seconds(w, argv[i + 1])
            if w == "--wait":
                a.wait = secs
            else:
                if not re.fullmatch(r"[1-9][0-9]*", secs):
                    raise Die(f"{w} must be greater than zero, got '{argv[i + 1]}'.")
                a.interval = secs
            i += 2
            continue
        if w in ("-q", "--quiet"):
            a.quiet = True
        elif w == "--json":
            a.json = True
        elif w in ("-h", "--help"):
            out(HELP)
            return None
        elif w.startswith("-"):
            raise Die(f"unknown option '{w}' (try --help)")
        elif not a.pr:
            a.pr = w
        elif not a.repo:
            a.repo = w
        else:
            raise Die(f"unexpected argument '{w}' (try --help)")
        i += 1
    return a
