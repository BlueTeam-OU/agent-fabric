#!/usr/bin/env python3
"""tools/fabric/github/pr_sessions.py — which SESSION owns which PR, newest
first (ADR-040 Wave 1; `fabric-pr sessions` runs it; the runtime/github shim is deprecated, and the
managed projects' tools/gh/pr-sessions.sh forward to that path).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      [-n|--limit N] [/OPEN|/open|--open] [/MERGED|/merged|--merged]
            [/CLOSED|/closed|--closed] [/all|--all] [--mine]
            [/unattributed|--unattributed] [--session REGEX] [--by-session]
            [--no-threads] [/unresolved|--unresolved]
            [/lastItem:N|--lastItem:N] [/lastDate:<N>d|<N>h|<N>m]
            [-h|--help]
            Parsed left to right, each error at the argument that causes it;
            a value option takes the NEXT argument whatever it is; -h/--help
            prints and exits 0 at once, so an earlier bad flag wins and a
            later one is never read.
  env       AGENT_FABRIC_ROOT (where runtime/identity.py is; default: the
            repository this module is in)
  stdout    the help; or the table — a header row (not with --by-session),
            the rows, then the legend — or the one-line "no PRs" answers
            (`pr-sessions: no … in the last N <state> PR(s).`)
  stderr    every refusal (prefixed `pr-sessions: `), the truncated-window
            warning, `(checked the newest N of the last M <state> PRs)`
            under /unresolved, and the NOTE counting rows no scope can reach
  exit      0 listed (even if the result is empty), or help; 2 invocation
            problem — bad flag, conflicting flags, no gh, not
            authenticated, a bad --session regex, /unresolved that cannot
            be answered
  help      HELP below, byte for byte what the bash printed from its own
            header; its "no gh/jq" is the bash's — jq is no longer used,
            gh alone is required
  lines     stdout and stderr are flushed in program order, so a caller that
            merges the two (2>&1) sees the order the bash printed in

Rows, in the order the bash applied them: fetch (`gh pr list`, state and
limit chosen here) -> POOL (/lastDate, then /lastItem) -> scope (default
this session, /all, /unattributed, --session) -> slice to the candidates ->
thread lookup (one aliased GraphQL query) -> /unresolved -> slice to -n.

WHY (carried from the bash header): every PR carries the same GitHub
author, because every session pushes with the same credentials, so `gh pr
list` answers nothing about who is doing what. The session identity lives
in the BRANCH NAME — <hostname -s>/<login>/<type>/<short-desc> — so the
first two segments are the session (the login on this host; an older
branch carries a working-copy name there instead, see Me.legacy) and
everything after is the work. Rows belonging to THIS session are marked,
which is what the stay-in-your-own-lane rules turn on: never push to,
rebase, delete or answer reviews on another session's branch.

DEFAULT SCOPE: run inside a clone, and it shows THIS session's PRs. Asking
"which PRs are mine" from inside a working tree is the common case, and
the login you run as already answers it — so that is the default rather
than something to remember a flag for. Pass /all to see every session.
(There is no unscoped-outside-a-repo case: `gh pr list` needs a repo
context and fails first, so the empty-ME branch below is belt-and-braces
for a future --repo flag, not a path you can reach today.)

/unattributed IS THE THIRD SCOPE, and it exists because the other two
cannot reach these rows. A branch that does not parse — a pre-convention
`feat/x`, whatever /install-github-app names its own — belongs to no
session, so every scoped run drops it and /all merely stops filtering
rather than selecting it. The count in the NOTE said how many were hidden
and no invocation could list them, which is a backlog nothing surfaces:
four such PRs sat on seven unresolved P1/P2 threads for a month, invisible
to every session's sweep because no session owned them. The pairing that
matters is `/unattributed /unresolved`: scope is applied BEFORE the thread
lookup's candidate slice, so narrowing to the unowned rows first is also
what gets their threads queried at all — under /all they compete for the
same 100 slots as every recent PR and lose, being by definition the older
ones.

State is chosen at FETCH time, so like /lastItem and /lastDate it narrows
the pool before scope, /unresolved and -n ever see it. /lastItem and
/lastDate narrow the POOL and are applied BEFORE everything else; that is
what separates them from -n: -n trims the printed page, these decide what
was ever considered.

The THR column counts UNRESOLVED review threads. These no longer gate a
merge (required_review_thread_resolution went off 2026-08-06), which is
precisely why the column matters: a PR can merge with findings
outstanding, so this count is the only place they surface. A trailing "!"
means the last word in at least one of them is NOT the PR author's, i.e.
somebody is waiting on a reply. "2" without the bang means you answered
and simply have not resolved the threads.
"""
from __future__ import annotations

import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
# Split out of this module; the names stay importable from here, where the
# unit suite reaches them.
from github.pr_sessions_owner import (  # noqa: E402, F401
    BOT_OWNER, UNATTRIBUTED, Me, conventional, cutoff_for, session_of, who_am_i, work_of)
from github.pr_sessions_threads import (  # noqa: E402, F401
    THREAD_ALIAS, THREADS_QUERY, keeps_unresolved, lookup_threads, thr_column, thread_counts)

HELP = """Which SESSION owns which PR, newest first.

Every PR in this repo carries the same GitHub author, because every
session pushes with the same credentials. `gh pr list` therefore shows
one name against all of them and answers nothing about who is doing
what. The session identity lives in the BRANCH NAME instead — the
repo-root CLAUDE.md mandates

    <hostname -s>/<login>/<type>/<short-desc>

so the first two segments are the session — the login on this host —
and everything after is the work (an older branch carries a
working-copy name there instead; see ME_LEGACY). This script reads
that, and marks the rows belonging to THIS session so "mine vs theirs"
is visible at a glance — which is what the
stay-in-your-own-lane rules turn on: never push to, rebase, delete or
answer reviews on another session's branch.

DEFAULT SCOPE: run inside a clone, and it shows THIS session's PRs.
Asking "which PRs are mine" from inside a working tree is the common
case, and the login you run as already answers it — so that
is the default rather than something to remember a flag for. Pass
/all to see every session.

(There is no unscoped-outside-a-repo case to describe: `gh pr list`
needs a repo context and fails first, so the script never gets that
far. The empty-ME branch below is belt-and-braces for a future
--repo flag, not a path you can reach today.)

/unattributed IS THE THIRD SCOPE, and it exists because the other two
cannot reach these rows. A branch that does not parse — dependabot's,
a pre-convention `feat/x`, whatever /install-github-app names its own
— belongs to no session, so every scoped run drops it and /all merely
stops filtering rather than selecting it. The count in the NOTE said
how many were hidden and no invocation could list them, which is a
backlog nothing surfaces: four such PRs sat on seven unresolved P1/P2
threads for a month, invisible to every session's sweep because no
session owned them. Scope to them directly and they are answerable.

The pairing that matters is `/unattributed /unresolved`: scope is
applied BEFORE the thread lookup's candidate slice, so narrowing to
the unowned rows first is also what gets their threads queried at all
— under /all they compete for the same 100 slots as every recent PR
and lose, being by definition the older ones.

Usage:
  fabric-pr sessions                 # THIS session's PRs (default)
  fabric-pr sessions /all            # every session
  fabric-pr sessions /unattributed   # only PRs no session owns
  fabric-pr sessions -n 50           # last 50 rows
  fabric-pr sessions /OPEN           # open PRs only
  fabric-pr sessions /MERGED         # merged only  (/CLOSED too)
  fabric-pr sessions --session legacy-clone-3
  fabric-pr sessions /all --by-session   # grouped, all sessions
  fabric-pr sessions /lastItem:50    # pool = 50 most recent PRs
  fabric-pr sessions /lastDate:2d    # pool = updated in the last 2 days
  fabric-pr sessions /lastDate:6h /unresolved   # ...then filter
  fabric-pr sessions /unresolved     # only PRs with an open thread
  fabric-pr sessions /all /unresolved # ...across every session
  fabric-pr sessions /unattributed /unresolved  # ...owed by nobody

State is chosen at FETCH time, so like /lastItem and /lastDate it
narrows the pool before scope, /unresolved and -n ever see it.
  fabric-pr sessions --no-threads    # skip the review-thread lookup

/lastItem and /lastDate narrow the POOL, and are applied BEFORE
everything else — session scope, /unresolved and -n all operate on
what they leave behind. That is what separates them from -n: -n trims
the printed page, these decide what was ever considered.

The THR column counts UNRESOLVED review threads. These no longer gate
a merge (required_review_thread_resolution went off 2026-08-06), which
is precisely why the column matters: a PR can merge with findings
outstanding, so this count is the only place they surface. A
trailing "!" means the last word in at least one of them is NOT the
PR author's, i.e. somebody is waiting on a reply. "2" without the
bang means you answered and simply have not resolved the threads.

Exit codes:
  0  listed (even if the result is empty)
  2  invocation problem (no gh/jq, not authenticated, bad flag)"""

PR_FIELDS = ["number", "state", "headRefName", "title", "updatedAt", "isDraft", "mergedAt"]
MINE, UNOWNED = "__MINE__", "__UNATTRIBUTED__"
# 500 bounds the fetch this script INFERS for you. It is a guess about how
# far back to look, so capping it is free.
DERIVED_FETCH_CAP = 500


class Die(Exception):
    """A refusal: the message is the stderr text, verbatim; exit 2."""


def out(text: str) -> None:
    sys.stderr.flush()
    print(text, flush=True)


def err(text: str) -> None:
    # Flushed both ways: a caller merging 2>&1 sees the order the bash
    # printed in, which the oracle's assertions and every pipeline read.
    sys.stdout.flush()
    print(text, file=sys.stderr, flush=True)


# ── branch -> session ────────────────────────────────────────────────


# ── /lastDate ────────────────────────────────────────────────────────


# ── the thread lookup ────────────────────────────────────────────────


# ── arguments ────────────────────────────────────────────────────────

class Opts:
    def __init__(self) -> None:
        self.limit = "20"
        self.state, self.state_set = "all", ""   # which flag chose it, so a conflict can be named
        self.filter = ""
        self.scope_explicit, self.scope_set = False, ""   # which flag chose it, so a conflict can be named
        self.grouped, self.threads, self.unresolved = False, True, False
        # _SET flags rather than an empty-string sentinel: `/lastItem:` and
        # `/lastDate:` PASS an empty value, and treating that as "unset" made
        # a malformed flag render as no filter at all — the whole list,
        # looking like a successful narrow. Passed-but-empty must be an
        # error.
        self.last_item, self.last_item_set = "", False
        self.last_date, self.last_date_set = "", False

    def set_state(self, state: str, flag: str) -> None:
        # gh takes ONE --state. Two conflicting flags would otherwise
        # resolve to whichever came last, quietly showing a different set
        # than asked.
        if self.state_set and self.state != state:
            raise Die(f"pr-sessions: {self.state_set} and {flag} conflict — pick one state.")
        self.state, self.state_set = state, flag

    def set_scope(self, scope: str, flag: str) -> None:
        # Two scope flags resolved LAST-WINS in silence, so `/unattributed
        # /all` quietly printed every PR and `/all /unattributed` quietly
        # printed only the unowned ones — the same "a mistyped filter must
        # not render as no filter" hazard, reached with two valid flags.
        # Conflicting STATE flags are already refused; scope now matches.
        if self.scope_explicit and self.filter != scope:
            raise Die(f"pr-sessions: {self.scope_set} and {flag} are different scopes — pick one.")
        self.filter, self.scope_set, self.scope_explicit = scope, flag, True


def parse(argv: list[str]) -> Opts | None:
    """The options, or None when --help was answered."""
    o = Opts()
    i = 0
    while i < len(argv):
        a = argv[i]
        # A flag that takes a value must HAVE one. The bash version's
        # `shift 2` with nothing to consume left its loop re-reading the
        # same argument forever; a hung script is a worse failure than a
        # rejected one, and it looks like a slow network call.
        if a in ("-n", "--limit", "--session"):
            if i + 1 >= len(argv):
                raise Die(f"pr-sessions: {a} needs a value (try --help).")
            value = argv[i + 1]
            if a == "--session":
                o.set_scope(value, f"{a} {value}")
            else:
                o.limit = value
            i += 2
            continue
        i += 1
        if a in ("/OPEN", "/open", "--open"):
            o.set_state("open", a)
        elif a in ("/MERGED", "/merged", "--merged"):
            o.set_state("merged", a)
        elif a in ("/CLOSED", "/closed", "--closed"):
            o.set_state("closed", a)
        elif a in ("/all", "--all"):
            o.set_scope("", a)
        elif a == "--mine":
            o.set_scope(MINE, a)
        elif a in ("/unattributed", "--unattributed"):
            o.set_scope(UNOWNED, a)
        elif a == "--by-session":
            o.grouped = True
        elif a == "--no-threads":
            o.threads = False
        elif a in ("/unresolved", "--unresolved"):
            o.unresolved = True
        elif a.startswith(("/lastItem:", "--lastItem:")):
            o.last_item, o.last_item_set = a.split(":", 1)[1], True
        elif a.startswith(("/lastDate:", "--lastDate:")):
            o.last_date, o.last_date_set = a.split(":", 1)[1], True
        elif a in ("-h", "--help"):
            out(HELP)
            return None
        else:
            raise Die(f"pr-sessions: unknown option '{a}' (try --help)")
    return o


def unattributed_note(count: int) -> None:
    """Say it on EVERY exit path, not only the one that prints a table. A
    disclosure that lives in the footer alone is missing from the two paths
    that exit early — no rows at all, and /unresolved finding no known open
    threads. Those print a reassuring "no PRs" and are exactly the answers a
    reader acts on, so the silence would fall precisely where it costs
    most."""
    if count <= 0:
        return
    err(f"  NOTE: {count} PR(s) name no live session — the branch does not\n"
        "  parse as <host>/<agent>/<type>/<short-desc> (a Dependabot branch\n"
        "  is not among them: those rows are role:devex-tooling's)\n"
        "  — so they cannot be scoped to a\n"
        "  session and are not listed. Pass /unattributed to list exactly\n"
        "  those, or /all to stop filtering.")


def status_of(row: dict) -> str:
    if row.get("isDraft"):
        return "DRAFT"
    return row["state"] if row.get("state") in ("OPEN", "MERGED") else "CLOSED"


def day_of(row: dict) -> str:
    updated = row.get("updatedAt")
    return "null" if updated is None else updated[:10]


def select(rows: list[dict], scope: str, me: Me, cutoff: str, last_item: int, candidates: int) -> tuple[list[dict], int]:
    """(the rows to show, how many the scope dropped as unattributable).

    Rows whose branch does not parse as <host>/<clone>/<type>/<desc> cannot
    be attributed to a session, so any scope filter removes them. COUNTED,
    because removing them silently is how a listing looks complete when it
    is not — the answer a reader acts on is the one that says "nothing
    outstanding". Counted in the SAME pass that builds the rows, and from
    what is left after /lastDate and /lastItem have narrowed the pool. A
    separate pass over the unnarrowed rows would announce PRs the caller
    never asked about: `/lastItem:1` would name an unscopable PR that was
    outside the one-item pool and had therefore not been omitted by
    anything. Sharing the pipeline is what keeps the two answers about the
    same set by construction, rather than by two pipelines happening to
    agree.

    OLDER BRANCHES. Before the login identity model, prefixes carried the
    working-copy directory name; a prefix naming THIS working copy is this
    agent's own (Me.legacy). Any other older prefix is simply that
    session's: no record of retired clones is kept, so nothing is inherited
    and nothing is orphaned."""
    tagged = []
    for r in rows:
        branch = r.get("headRefName")
        if not isinstance(branch, str):
            raise Die(f"pr-sessions: could not select rows — check the --session pattern ('{scope}') is a valid regex.")
        s = session_of(branch)
        tagged.append({**r, "_s": s, "_o": s, "_w": work_of(branch)})
    pool = sorted(tagged, key=lambda r: -r["number"])
    # POOL FIRST: /lastDate then /lastItem, before scope or anything else.
    if cutoff:
        pool = [r for r in pool if r.get("updatedAt") is not None and r["updatedAt"] >= cutoff]
    if last_item > 0:
        pool = pool[:last_item]
    # The pool is now fixed, so both answers describe the same set. Nothing
    # is dropped by scope when there is no scope, so /all reports zero
    # rather than a number no filter ever acted on. /unattributed reports
    # zero for the opposite reason: these rows are the listing, not what the
    # listing left out. Counting them would print "N PR(s) ... are not
    # listed" directly above the N rows — a disclosure contradicting the
    # page it sits under, and the one scope where the omission it warns of
    # cannot happen.
    dropped = 0 if scope in ("", UNOWNED) else sum(1 for r in pool if r["_s"] == UNATTRIBUTED)
    if scope == MINE:
        chosen = [r for r in pool if me.owns(r["_o"])]
    elif scope == UNOWNED:
        chosen = [r for r in pool if r["_s"] == UNATTRIBUTED]
    elif scope != "":
        chosen = []
        pattern = None
        for r in pool:
            try:
                # Compiled on the first row, where jq's test() first failed:
                # a bad pattern over an empty pool was no error in the bash.
                pattern = pattern or re.compile(scope, re.IGNORECASE)
            except re.error:
                # `--session '['` kills the matcher, and taking that for an
                # empty result printed "no PRs for a session matching '['",
                # exit 0. A bad pattern and a genuinely empty result must
                # not look alike: one is an invocation error to fix, the
                # other is an answer.
                raise Die(f"pr-sessions: could not select rows — check the --session pattern ('{scope}') is a valid regex.") from None
            if pattern.search(r["_s"]):
                chosen.append(r)
    else:
        chosen = pool
    return sorted(chosen, key=lambda r: -r["number"])[:candidates], dropped


def run(argv: list[str]) -> int:
    o = parse(argv)
    if o is None:
        return 0

    # -n reached shell arithmetic in the bash, which re-evaluates the
    # CONTENTS of a variable as an expression — including command
    # substitution inside an array subscript, so `-n 'x[$(rm -rf …)]'` was
    # code execution, not a bad number. Here too it is validated before any
    # use: a positive integer is the only thing it may be.
    if not re.fullmatch(r"[1-9][0-9]*", o.limit):
        raise Die(f"pr-sessions: -n/--limit needs a positive integer, got '{o.limit}'.")
    limit = int(o.limit)

    # Validated whenever the flag was PASSED, not merely when non-empty.
    # `--session unconventional` ALREADY selected exactly these rows,
    # because the session string is the literal "(unconventional)" and
    # --session is a regex match. It simply did so while printing the
    # omission NOTE above the rows it had just listed, and the "others
    # belong to parallel sessions" footer. Normalising it to the sentinel
    # makes one scope with one set of messages, rather than two routes that
    # disagree about what they showed. Only an exact word is normalised: a
    # broad pattern like `.` matches "(unconventional)" too, and silently
    # redirecting that would be the last-wins hazard set_scope just closed.
    if o.filter in ("unconventional", "UNCONVENTIONAL", UNATTRIBUTED, "Unconventional"):
        o.filter = UNOWNED

    if o.last_item_set and not re.fullmatch(r"[1-9][0-9]*", o.last_item):
        raise Die(f"pr-sessions: /lastItem needs a positive integer, got '{o.last_item}'.")
    last_item = int(o.last_item) if o.last_item_set else 0

    cutoff = ""
    if o.last_date_set:
        try:
            cutoff = cutoff_for(o.last_date)
        except (OverflowError, ValueError):
            raise Die(f"pr-sessions: could not compute a cutoff for '{o.last_date}'.") from None
        if cutoff is None:
            raise Die(f"pr-sessions: /lastDate needs <N>d, <N>h or <N>m — got '{o.last_date}'.")

    if o.unresolved and not o.threads:
        raise Die("pr-sessions: /unresolved needs the thread lookup — drop --no-threads.")

    if not shutil.which("gh"):
        raise Die("pr-sessions: gh is required but not installed.")

    me_str, legacy, role = who_am_i()
    # Inside a clone with no explicit scope: show this session's PRs. If ME
    # cannot be resolved there is nothing to infer, so fall through to
    # everything — unreachable today (gh needs a repo and fails earlier),
    # kept so the default cannot silently become "someone else's session"
    # if a --repo flag is ever added.
    defaulted = False
    if not o.scope_explicit and me_str:
        o.filter, defaulted = MINE, True
    me_str = me_str or "unknown/unknown"
    me = Me(me_str, legacy, role)

    # -n bounds the ROWS SHOWN, not how far back we look. With a filter the
    # two differ sharply: `--mine -n 8` fetching only the newest 8 PRs
    # returned NOTHING here, because all 8 belonged to parallel sessions —
    # an empty list that reads as "you have no PRs" rather than "your PRs
    # are older than the window". So widen the fetch and trim after
    # filtering.
    fetch = limit
    if o.filter or o.unresolved or cutoff or last_item:
        fetch = min(max(limit * 20, 200), DERIVED_FETCH_CAP)
    # An EXPLICIT /lastItem:N is not a guess — it is the pool the caller
    # asked for, and it is honoured whole. The cap used to apply here too,
    # so /lastItem:600 quietly built a 600-row pool out of 500 rows and then
    # filtered it, dropping matches without a word. `gh pr list --limit`
    # paginates, so there is nothing to clamp for.
    if last_item and last_item > fetch:
        fetch = last_item

    # /unresolved filters on data that only exists AFTER the thread lookup,
    # so the candidate set has to be wider than the page — otherwise a PR
    # with an open thread just past row -n would be invisible, which is the
    # same window trap `--mine -n 8` fell into. Capped so the aliased
    # GraphQL query stays one sane request.
    candidates = limit
    if o.unresolved:
        candidates = 100
        # AN EXPLICIT /lastItem IS A REQUEST, NOT A SUGGESTION. The 100
        # exists to keep the aliased GraphQL query one sane request when
        # nobody has said how far to look. But it was applied as the final
        # slice, AFTER /lastItem had already narrowed the pool — so `/all
        # /lastItem:150 /unresolved` quietly queried the newest 100 and
        # never asked about rows 101-150. The caller had named a number and
        # got a different one, with nothing said.
        if last_item > candidates:
            candidates = last_item
        candidates = min(candidates, fetch)

    try:
        rows = gh.pr_list(PR_FIELDS, state=o.state, limit=fetch)
    except gh.GhError:
        raise Die("pr-sessions: could not list PRs (gh not authenticated, or not in a repo).") from None

    # A /lastDate window is only as complete as the rows fetched: if the
    # fetch came back full, older PRs inside the window may exist beyond it
    # and the pool is silently short. Say so rather than presenting a
    # truncated window as the window.
    if cutoff and len(rows) >= fetch:
        err(f"pr-sessions: fetched the full {fetch}-PR page, so the {o.last_date} window may be\n"
            "  truncated — PRs updated in it can exist further back. Raise it with /lastItem:N.")

    selected, unattributed = select(rows, o.filter, me, cutoff, last_item, candidates)

    if not selected:
        what = "PRs"
        if o.filter == MINE:
            what = f"PRs for this session ({me_str})"
        elif o.filter == UNOWNED:
            what = "PRs without a parsable session branch"
        elif o.filter:
            what = f"PRs for a session matching '{o.filter}'"
        out(f"pr-sessions: no {what} in the last {fetch} {o.state} PR(s).")
        if defaulted:
            out("  (scoped to this session by default — pass /all to see every session)")
        unattributed_note(unattributed)
        return 0

    threads: dict | None = {}
    if o.threads:
        threads = lookup_threads([r["number"] for r in selected])
    if o.unresolved and threads is None:
        raise Die("pr-sessions: could not read review threads, so /unresolved cannot be answered.\n"
                  "  (gh api graphql failed, or the repository could not be resolved)")

    if o.unresolved:
        selected = [r for r in selected if keeps_unresolved(r, threads)]
    selected = sorted(selected, key=lambda r: -r["number"])[:limit]

    lines: list[str] = []
    if o.grouped:
        groups: dict[str, list[dict]] = {}
        for r in selected:
            groups.setdefault(r["_s"], []).append(r)
        # Newest group first; equal newest numbers keep the session names'
        # own order.
        for s in sorted(sorted(groups), key=lambda k: -max(r["number"] for r in groups[k])):
            g = groups[s]
            # OWNER decides the marker; the heading is the session name
            # exactly where it is least obvious.
            lines.append(f"\n{s}{'   <- this session' if me.owns(g[0]['_o']) else ''}")
            for r in sorted(g, key=lambda r: -r["number"]):
                lines.append(f"  #{r['number']}  {status_of(r):<6}  {thr_column(r, threads, o.threads):>3}"
                             f"  {day_of(r)}  {r['_w']}")
    else:
        for r in selected:
            mark = "*" if me.owns(r["_o"]) else " "
            lines.append(f"{mark} #{r['number']!s:<4}  {status_of(r):<6}  {thr_column(r, threads, o.threads):>3}"
                         f"  {day_of(r)}  {r['_s']:<30}  {r['_w']}")
    # A command substitution in the bash: trailing newlines do not survive.
    table = "\n".join(lines).rstrip("\n")

    if not o.grouped:
        out(f"  {'PR':<5}  {'STATE':<6}  {'THR':>3}  {'UPDATED':<10}  {'SESSION':<30}  WORK")
    if not table.strip(" \t\n"):
        scope = f"this session ({me_str})"
        if o.filter == "":
            scope = "any session"
        elif o.filter == UNOWNED:
            scope = "branches no session owns"
        elif o.filter != MINE:
            scope = f"sessions matching '{o.filter}'"
        out(f"pr-sessions: no PRs with unresolved review threads for {scope}")
        out(f"  (checked the newest {candidates} of the last {fetch} {o.state} PRs)")
        unattributed_note(unattributed)
        return 0

    out(table)

    # SAY WHAT WAS ACTUALLY CHECKED, not only when the answer is empty. This
    # footer used to print on the empty branch alone, so a run that found
    # something in the newest N looked complete while rows beyond that were
    # never queried. "Nothing outstanding" and "nothing outstanding in the
    # part I looked at" are different answers, and only one of them was ever
    # qualified. stderr, so a piped caller's data is unchanged.
    if o.unresolved:
        err(f"  (checked the newest {candidates} of the last {fetch} {o.state} PRs)")
    unattributed_note(unattributed)

    out("")
    if defaulted:
        out(f"  Scoped to this session ({me_str}) — pass /all for every session.")
    elif o.filter == UNOWNED:
        # The "*" legend would be a lie here: no row under this scope can be
        # this session's, because every one of them failed to parse as any
        # session at all. Saying who these belong to instead is the useful
        # sentence, since "leave other sessions' PRs alone" is precisely the
        # rule that does NOT apply and has kept these unanswered.
        out("  These branches parse as no session, so the stay-in-your-lane rule\n"
            "  has no owner to point at — findings here are unowned, not somebody\n"
            "  else's. Check with the surface's role before acting on the code.")
    elif not o.grouped:
        out(f"  * = this session ({me_str}).  Others belong to parallel sessions:\n"
            "  do not push to, rebase, delete, or answer reviews on their branches.")
    return 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except Die as e:
        err(str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
