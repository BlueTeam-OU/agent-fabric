#!/usr/bin/env python3
"""runtime/github/owed-supply.sh [--days N] [--json]

List every supply branch nobody has folded yet.

THE STATE THIS NAMES. A change has one owner, and the roles it needs
supply it (agent-fabric identities/prompt/team.md): a supplier that
cannot put its commit on the caller's branch pushes a contributor branch

    <host>/<supplier-login>/for/<caller-login>/<what>

that the caller folds unrebased. The hand-off names a FOLD-BY date; past
it unclaimed the supplier pings once. "Owed" is therefore a state with a
clock, and this is what lists it.

WHAT IS LISTED. Every branch on origin of that shape whose head is
reachable from NO open pull request — neither a pull request's own head
branch nor an ancestor of one (a folded supply branch is reachable from
the caller's pull request and is not owed). For each: its age (from the
head commit's committer date), the supplier and the caller (from the
name), the head, and the branch. The FOLD-BY date itself lives in the
hand-off message, so the reader applies it; the DEFAULT is the next day,
and a row a day or more old is marked past it. --days N narrows the list
to branches at least N days old, for the "ping once" step. A branch
already reachable from the default branch has LANDED: it is owed to
nobody, listed apart, and the supplier deletes it.

AND THE OTHER DIRECTION: an open pull request whose body names an
AWAITING-SUPPLY with no range line for it. A caller that has asked a
supplier for a piece records the wait in its body as a line

    AWAITING-SUPPLY: <supplier-login>

and, once the piece is folded, the range line
`<sha>..<sha>: <supplier-login> (<role>)`. A body with the first and not
the second waits on supply that the reachability check cannot see (it may
be a single commit still to come, on no branch at all). Listed as
"awaiting", by pull request and login; the project's arm refuses to arm
one.

Usage:
  runtime/github/owed-supply.sh [--days N] [--json]

Exit codes:
  0  listed (an empty list is a good state, and is said); --json prints
     {owed: [...], landed: [...], awaiting: [...]}
  2  gh, the repository or one of its reads could not be read

The repository is GH_REPO, else this working copy's origin on github.com,
never gh's default. Reads GitHub only; nothing in the working copy is
touched.
"""
# The docstring is --help, whole. Ported from a managed project's
# tools/gh/owed-supply.sh (ADR-040; its test, unchanged, the oracle).
#
# THE CONTRACT, frozen from devex-tooling's port contract 1/8 and its
# rulings of 2026-10-08:
#   argv    [--days N] [--json] [-h|--help], read in order: --help prints
#           this docstring and exits 0 where it stands; --days takes the
#           next word, ASCII digits only, read as decimal ("08" is 8),
#           else "owed-supply: --days needs a whole number", exit 2; any
#           other word "owed-supply: unknown option '<x>' (try --help)",
#           exit 2. Repeated, the last --days wins.
#   env     GH_REPO (through gh.this_repo); nothing else of its own.
#   reads   repos/R/branches (every page), keeping names of the shape
#           <a>/<b>/for/<c>/<rest>; the open pull requests (200 at most:
#           number, headRefName, headRefOid, title, body); repos/R's
#           default_branch; per unclaimed branch repos/R/compare/<base>...
#           <head>'s behind_by, and its head commit's committer date.
#   stdout  the lines below, verbatim; --json one object, indented two
#           spaces as jq prints it, or on one line when there is no
#           supply branch at all (the bash's `jq -c` there).
#   stderr  one line per refusal, each "owed-supply: …", exit 2:
#           gh is required; cannot read the repository: <why>; could not
#           list branches of R; could not list open pull requests; cannot
#           read the default branch of R: <why>; cannot run — the compare
#           for A...B failed: <gh's error line>.
#   exit    0 listed, 2 could not run. Never a traceback.
# Departures from the bash, each agreed with devex-tooling (2026-10-08):
# the repository is gh.this_repo(), never `gh repo view`'s default (#109);
# no jq, so no "jq is required"; the compare failure names gh's error
# line, not the first line of stdout and stderr merged (the "{" of an
# error body); every call is bounded, a timeout failing that call; the
# default branch unread is exit 2 — the bash fell back to "main", and on a
# repository whose default is not main every landed branch's compare
# 404s and was listed OWED at exit 0, a confident wrong answer.
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
from github import pr_gate  # noqa: E402

SUPPLY_SHAPE = re.compile(r"[^/]+/[^/]+/for/[^/]+/.+")
_SURROGATE = re.compile("[\ud800-\udfff]")
UNRELATED = "unrelated"


class Refusal(Exception):
    """The run cannot answer: its line goes to stderr, exit 2."""


def _text(v) -> str:
    """A pull request's string field as jq's "\\(.x)" printed it: null is
    "null", and a lone surrogate (valid JSON, unprintable UTF-8) is the
    replacement character jq writes for it."""
    if v is None:
        return "null"
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    return _SURROGATE.sub("\ufffd", s)


def parse_args(argv: list[str]) -> tuple[int | None, str, bool] | None:
    """(days, days as written, json), or None when --help was asked."""
    days, days_word, as_json = None, "", False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--days":
            word = argv[i + 1] if i + 1 < len(argv) else ""
            if not re.fullmatch(r"[0-9]+", word):
                raise Refusal("--days needs a whole number")
            days, days_word = int(word), word
            i += 2
        elif a == "--json":
            as_json = True
            i += 1
        elif a in ("-h", "--help"):
            return None
        else:
            raise Refusal(f"unknown option '{a}' (try --help)")
    return days, days_word, as_json


def supply_branches(repo: str) -> list[tuple[str, str]]:
    """(name, head sha) of every branch of the supply shape, as listed."""
    try:
        items = gh.api(f"repos/{repo}/branches?per_page=100", paginate=True)
    except gh.GhError:
        raise Refusal(f"could not list branches of {repo}") from None
    out = []
    for b in items if isinstance(items, list) else [None]:
        name = b.get("name") if isinstance(b, dict) else None
        if not isinstance(name, str):
            raise Refusal(f"could not list branches of {repo}")
        if not SUPPLY_SHAPE.fullmatch(name):
            continue
        commit = b.get("commit")
        sha = commit.get("sha") if isinstance(commit, dict) else None
        if not isinstance(sha, str):
            raise Refusal(f"could not list branches of {repo}")
        out.append((name, sha))
    return out


def open_pull_requests(repo: str) -> list[dict]:
    try:
        prs = gh.pr_list(["number", "headRefName", "headRefOid", "title", "body"], repo=repo, limit=200)
    except (gh.GhError, ValueError):
        raise Refusal("could not list open pull requests") from None
    if not isinstance(prs, list) or not all(isinstance(p, dict) for p in prs):
        raise Refusal("could not list open pull requests")
    return prs


def awaiting(prs: list[dict]) -> list[dict]:
    """The open pull requests naming an AWAITING-SUPPLY with no range line
    for it — pr_gate's reading, which arm shares."""
    rows = []
    for p in prs:
        body = p.get("body") if isinstance(p.get("body"), str) else ""
        unmet = pr_gate.awaiting_supply(body)
        if unmet:
            rows.append({"number": p.get("number"), "title": p.get("title"), "awaiting_supply": unmet})
    return rows


def default_branch(repo: str) -> str:
    try:
        data = gh.api(f"repos/{repo}")
    except gh.GhError as e:
        raise Refusal(f"cannot read the default branch of {repo}: {e.reason}") from None
    name = data.get("default_branch") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name:
        raise Refusal(f"cannot read the default branch of {repo}: the answer names none")
    return name


def behind_by(repo: str, base: str, head: str):
    """compare/<base>...<head>'s behind_by — 0 exactly when base is
    reachable from head — or UNRELATED for no common ancestor."""
    try:
        data = gh.api(f"repos/{repo}/compare/{base}...{head}")
    except gh.GhError as e:
        # gh renders the status as "(HTTP 404)", which e.status reads; the
        # request URL gh may also print can hold 404 inside a sha, so the
        # bare number is never matched (a proxy failure on such a compare
        # once read as "unrelated"). Any other failure is not "not
        # claimed": a rate limit would list every supply branch as owed at
        # exit 0.
        if e.status == 404 or re.search(r'"status": ?"404"', e.stdout) or "No common ancestor" in e.reason:
            return UNRELATED
        raise Refusal(f"cannot run — the compare for {base}...{head} failed: {e.reason}") from None
    return data.get("behind_by") if isinstance(data, dict) else None


def reachable(repo: str, base: str, head: str) -> bool:
    b = behind_by(repo, base, head)
    return type(b) is int and b == 0


def committed(repo: str, sha: str) -> str:
    """The head commit's committer date, or "" when it cannot be read: an
    unknown age, never a failed run."""
    try:
        data = gh.api(f"repos/{repo}/commits/{sha}")
    except gh.GhError:
        return ""
    try:
        date = data["commit"]["committer"]["date"]
    except (TypeError, KeyError):
        return ""
    return date if isinstance(date, str) else ""


def age_in_days(date: str, now: int) -> int | None:
    """Whole days since `date`, truncated toward zero as bash's $(( )) did;
    None when it does not parse. A date without a zone is UTC (date -u)."""
    try:
        when = dt.datetime.fromisoformat(date)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    seconds = now - int(when.timestamp())
    return seconds // 86400 if seconds >= 0 else -(-seconds // 86400)


def classify(repo: str, branches: list[tuple[str, str]], prs: list[dict], base: str, days: int | None,
             now: int) -> tuple[list[dict], list[dict]]:
    owed, landed = [], []
    for name, sha in branches:
        if any(p.get("headRefName") == name for p in prs):
            continue
        # Folded: the supply head is an ancestor of some open PR's head.
        # Each compare is asked in turn and the first claim ends the scan,
        # so a failing compare after a claim is never asked.
        if any(reachable(repo, sha, _text(p.get("headRefOid"))) for p in prs):
            continue
        # A supply branch folded into a caller's PR that has since merged
        # is reachable from the default branch and owed to nobody — the
        # queue deletes the caller's branch, not the supplier's. Said as
        # its own line, so the supplier deletes it rather than pings.
        if reachable(repo, sha, base):
            landed.append({"branch": name, "head": sha})
            continue
        date = committed(repo, sha)
        age = age_in_days(date, now) if date else None
        # Unknown age is not young: --days keeps it.
        if days is not None and age is not None and age < days:
            continue
        parts = name.split("/")
        # The default FOLD-BY is the next day; the hand-off may have named
        # a later one, which only the message knows — so "past" here is
        # "past the default", said as such.
        owed.append({"branch": name, "head": sha, "supplier": parts[1], "caller": parts[3], "committed": date,
                     "age_days": age, "past_default_fold_by": None if age is None else age >= 1})
    return owed, landed


def say_awaiting(rows: list[dict]) -> None:
    if not rows:
        return
    print(f"owed-supply: {len(rows)} open pull request(s) name a AWAITING-SUPPLY with no range line for it "
          "(supply asked for, not yet folded — do not arm):")
    for r in rows:
        print(f"  #{_text(r['number'])}  AWAITING-SUPPLY {', '.join(r['awaiting_supply'])}  {_text(r['title'])}")


def _json(doc: dict, compact: bool) -> str:
    def clean(v):
        if isinstance(v, str):
            return _SURROGATE.sub("\ufffd", v)
        if isinstance(v, list):
            return [clean(x) for x in v]
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items()}
        return v
    if compact:
        return json.dumps(clean(doc), ensure_ascii=False, separators=(",", ":"))
    return json.dumps(clean(doc), ensure_ascii=False, indent=2)


def run(argv: list[str]) -> int:
    parsed = parse_args(argv)
    if parsed is None:
        print(__doc__.strip("\n"))
        return 0
    days, days_word, as_json = parsed
    if not shutil.which("gh"):
        raise Refusal("gh is required")
    try:
        repo = gh.this_repo()
    except gh.GhError as e:
        raise Refusal(f"cannot read the repository: {e.reason}") from None

    branches = supply_branches(repo)
    prs = open_pull_requests(repo)
    waiting = awaiting(prs)
    if not branches:
        if as_json:
            print(_json({"owed": [], "landed": [], "awaiting": waiting}, compact=True))
        else:
            print(f"owed-supply: no supply branches on {repo} (nothing of the shape <host>/<login>/for/<login>/<what>).")
            say_awaiting(waiting)
        return 0

    base = default_branch(repo)
    owed, landed = classify(repo, branches, prs, base, days, int(time.time()))
    if as_json:
        print(_json({"owed": owed, "landed": landed, "awaiting": waiting}, compact=False))
        return 0
    say_awaiting(waiting)
    if landed:
        print(f"owed-supply: landed already (reachable from {base} — owed to nobody; the supplier deletes the branch):")
        for r in landed:
            print(f"  {r['head'][:8]}  {r['branch']}")
    if not owed:
        if days is not None:
            print(f"owed-supply: no supply branch older than {days_word} day(s) is unclaimed on {repo}.")
        else:
            print(f"owed-supply: every supply branch on {repo} is reachable from an open pull request — nothing owed.")
        return 0
    print(f"owed-supply: {len(owed)} supply branch(es) on {repo} reachable from no open pull request (the FOLD-BY "
          "date is in the hand-off message; the default is the next day; --days N narrows):")
    row = "  {:<5} {:<9} {:<18} {:<18} {:<9} {}"
    print(row.format("AGE", "FOLD-BY", "SUPPLIER", "CALLER", "HEAD", "BRANCH"))
    for r in owed:
        age = "?" if r["age_days"] is None else f"{r['age_days']}d"
        fold = "?" if r["past_default_fold_by"] is None else "PAST" if r["past_default_fold_by"] else "today"
        print(row.format(age, fold, r["supplier"], r["caller"], r["head"][:8], r["branch"]))
    return 0


def main() -> int:
    # The bash wrote UTF-8 whatever the locale; so does this, or the em
    # dashes in its own lines fail under a non-UTF-8 LANG.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    try:
        return run(sys.argv[1:])
    except Refusal as e:
        print(f"owed-supply: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
