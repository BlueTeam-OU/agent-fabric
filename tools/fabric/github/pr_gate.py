#!/usr/bin/env python3
"""tools/fabric/github/pr_gate.py — my open pull requests: how many commits,
and what stands between each and main (ADR-040 Wave 1;
runtime/github/pr-gate.sh is its shim, and the managed projects'
tools/gh/pr-gate.sh forward to that path). --in-flight and --overlap were
pr-gate-inflight.sh, sourced by the bash; they are in_flight() here.

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      [<pr>…] [--all] [--json] [--in-flight] [--overlap <pr|branch>]
            [--path <prefix>]… [-h|--help]
  env       AGENT_FABRIC_PR_REVIEW_STATUS (the review reader, run as a
            program), AGENT_FABRIC_PR_SESSION (<host>/<login>),
            AGENT_FABRIC_ROOT, AGENT_FABRIC_PR_BASE (--in-flight's base)
  stdout    the rows (three to five lines each), or with --json the rows
            as data; --in-flight a header and one line per branch, or an
            object with its rows
  stderr    every `pr-gate: ` note — a skipped number, a failed fetch,
            the 500-PR cap, a refusal
  exit      0 listed; 2 gh, git or the repository could not be read, a
            usage error (--in-flight/--overlap: also a failed fetch or an
            unreadable PR list, said first)

The review is asked of pr-review-status as a PROGRAM, by path, and read
from its text: the path is the seam the oracle mocks, and the managed
projects point it at their own reader.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
import git  # noqa: E402
from github import commit_class, local, pr_review_status  # noqa: E402
from github.review_status.base import listed, obj  # noqa: E402

FABRIC = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

HELP = """My open pull requests: how many commits, and what stands between each
and main.

THE QUESTION IT ANSWERS. "Show my open PRs, how many commits, is it
mergeable?" needed four tools and a head count by hand: pr-sessions.sh
for the list, git rev-list for the commits, gh pr checks for the
checks, pr-review-status.sh for the review, and the owner's arming rule
applied on top — eight or more WORK commits arm at the gate, a security
boundary too; under eight the owner is asked;
sixteen is batch-size advice for the next batch, never a block. One line
per PR now carries all of it, and a verdict.

WHAT A ROW SAYS
  #N  <owner> [(me)]  commits=T (W work, F fix, M merge[, R netted by a revert])  checks=<green|red:<names>|pending:<k>|none-yet|?>
      review=<head reviewed|NOT on head|none>  threads=<u>  armed=<yes|no>
      queue=<pos>  verdict

  owner  the session that opened it — <host>/<login> from the branch
         prefix, never the PR author (every session pushes as one
         GitHub user); "(me)" marks this session's. With --all, the
         repository's open PRs by owner: whose gate each one is at.
  commits all commits over the base, then the split: WORK ones are neither merges nor review fixes
         nor netted — a revert and the commit it reverts, both in the
         range, count in no column (git's "This reverts commit <sha>"
         line is the fact; each commit nets once, so a revert-then-
         reapply leaves the original as work) —
         (a fix is a commit carrying an "Answers: <labels>" trailer —
         the primary signal — or, without one, whose subject opens
         with "review" or names a review AND says it answers one —
         "review F4: …", "…: address the blind review", "re-review
         nits: …"; a fix(scope): bug fix is WORK — the count rule
         excludes fixes; the subjects counted as fix are printed so
         the split can be checked; commit-class.sh is the classifier)
  checks green when every reported check passed; red names the failed
         ones; pending counts the ones still running; none-yet when no
         check has reported (seconds after a push); ? when they could
         not all be read, which blocks
  review whether a review — an independent one, or the review class's blind review — covers the CURRENT head
         (pr-review-status.sh's reading)
  verdict one of:
    MERGEABLE — arm (8–16 work commits, gate met: post the basis, arm)
    MERGEABLE — ask the owner (under 8 work commits, gate met)
    MERGEABLE — N work commits, over 16: smaller batches next time (advice, never a block)
    MERGEABLE — commits unknown (the base is not fetched; count by hand)
    ARMED and clear / ARMED but held: <what> / QUEUED — nothing to do
    BLOCKED: <what> — a draft, red checks, pending checks, no check yet,
    checks unread,
    no review of the head, unresolved threads, a conflict
  A pull request given by number that is not OPEN is said and skipped.

Usage:
  tools/gh/pr-gate.sh              # every open PR of this session (branch prefix <host>/<login>/)
  tools/gh/pr-gate.sh 861 877      # these PRs, whoever opened them
  tools/gh/pr-gate.sh --all        # every open PR in the repository
  tools/gh/pr-gate.sh --json       # rows as data
  tools/gh/pr-gate.sh --in-flight [--path <prefix>]...   # every job in flight
  tools/gh/pr-gate.sh --overlap <PR number | branch>     # what shares its paths

IN FLIGHT. Before assigning a job, starting one, or relying on another
agent's branch, the question is what already exists; a job waiting for
a merge sits on a pushed branch with no PR, where the verdict rows above
never look (2026-09-26: an assignment withdrawn three minutes in, an
hour lost, the job on such a branch since 09-21; 62 of them against 3
open PRs that day). --in-flight lists every branch on origin not merged
into the base, PR or not: owner (the <host>/<login> prefix, else
"unattributed" -- never the GitHub author), PR number or "no PR",
commits ahead, last commit time, and the paths it changes against its
merge base with the base (what it changes, not what anyone declared).
--path keeps the rows changing something under a prefix; --overlap keeps
the rows sharing a changed path with the named PR or branch, and lists
the shared paths. It reserves nothing: a row says "this exists", and
"shares paths" is not "conflicts" -- trial-merge.sh answers that.

Exit codes:
  0  listed
  2  gh, git or the repository could not be read (--in-flight/--overlap:
     also a failed fetch, said first -- the rows are what origin last showed)

Environment (the self-test):
  AGENT_FABRIC_PR_REVIEW_STATUS   path of pr-review-status.sh (default beside this script)
  AGENT_FABRIC_PR_SESSION         the <host>/<login> prefix (default: fabric-whoami)"""

PR_FIELDS = ["number", "title", "headRefName", "headRefOid", "baseRefName", "state", "isDraft", "body"]
LIST_CAP = 500
INFLIGHT_PATHS_CAP = 200   # a row's paths as data; the total is always given
GATE_QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) {
    mergeStateStatus mergeable headRefOid
    reviewThreads(first: 100) { nodes { isResolved } pageInfo { hasNextPage endCursor } }
    mergeQueueEntry { position state }
    autoMergeRequest { enabledAt }
    statusCheckRollup { contexts(first: 100) { pageInfo { hasNextPage endCursor } nodes {
      ... on CheckRun { name status conclusion }
      ... on StatusContext { context state } } } } } } }"""
# The rest of the checks past GATE_QUERY's first 100. Read whole or not at
# all: a red check on page two read as "green" would let a PR be armed.
# headRefOid is asked again because the rollup is the CURRENT head's: a
# push between the pages would splice two heads' checks into one answer.
CONTEXTS_QUERY = """query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) {
    headRefOid
    statusCheckRollup { contexts(first: 100, after: $after) { pageInfo { hasNextPage endCursor } nodes {
      ... on CheckRun { name status conclusion }
      ... on StatusContext { context state } } } } } } }"""
CONTEXT_PAGES = 50
RED = re.compile(r"FAILURE|ERROR|TIMED_OUT|CANCELLED|ACTION_REQUIRED|STARTUP_FAILURE")
RUNNING_STATUS = re.compile(r"IN_PROGRESS|QUEUED|PENDING|WAITING|REQUESTED")
RUNNING_STATE = re.compile(r"PENDING|EXPECTED")
AWAITING = re.compile(r"^\s*-?\s*AWAITING-SUPPLY:\s*(?P<who>\S+)")
HEAD_REVIEWED = re.compile(r"^  head reviewed\? *: *([a-z]*)")
ANY_REVIEW = re.compile(r"^  (?:independent reviews|blind reviews|verdict comments) *: *([0-9]*)")


class Usage(Exception):
    pass


def note(msg: str) -> None:
    print(f"pr-gate: {msg}", file=sys.stderr)


def alt(*values):
    """jq's `a // b`: the first value that is neither null nor false."""
    for v in values:
        if v is not None and v is not False:
            return v
    return None


def jq_str(v) -> str:
    """A value as jq's string interpolation writes it."""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def succeeds(*args: str) -> bool:
    """A git call read as the bash read it: any failure is "no". git.ok
    raises on a status other than 0 or 1, and a failed fetch is 128."""
    try:
        return git.run(".", *args, check=False).returncode == 0
    except git.GitError:
        return False


def session_prefix() -> str:
    session = os.environ.get("AGENT_FABRIC_PR_SESSION", "")
    if session:
        return session
    whoami = os.path.join(os.environ.get("AGENT_FABRIC_ROOT") or FABRIC, "bin", "fabric-whoami")
    if os.access(whoami, os.X_OK):
        try:
            r = subprocess.run([whoami, "--json"], capture_output=True, text=True, timeout=30,
                               stdin=subprocess.DEVNULL)
            me = json.loads(r.stdout)
            session = f"{jq_str(me.get('host'))}/{jq_str(me.get('agent'))}"
        except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
            session = ""
    if not session or session == "null/null":
        host = local.probe(["hostname", "-s"])[1].strip()
        user = local.probe(["id", "-un"])[1].strip()
        session = f"{host}/{user}"
    return session


# ── commits over the base: work / review-fix / merge ─────────────────

def count_commits(num: int, repo: str, base: str, head: str) -> dict | None:
    """The split of origin/<base>..<head>, or None when the clone cannot
    answer it. The classifier is commit_class, the one place the rule
    lives, so a measurement of the band after the fact reads the same
    split. The subjects counted as fix (and netted) are returned, so the
    split can be checked; the count rule is applied on it and a misread
    moves the band."""
    if not succeeds("cat-file", "-e", f"{head}^{{commit}}") \
            or not succeeds("rev-parse", "--verify", "-q", f"origin/{base}^{{commit}}"):
        return None
    return split_range(num, repo, f"origin/{base}..{head}", head, f"origin/{base}")


def split_range(num: int, repo: str, rev_range: str, head: str = "", base: str = "") -> dict:
    """The work / fix / merge / netted split of a range of PR #num's
    commits — the gate's before arming, and pr-compliance's after the
    merge (<merge>^1..<merge>^2), so the band is measured as it was
    applied. <head> is the range's tip: with it, a PR folded into it is
    read as one (commit_class.Folds), once per PR the range names; <base>
    is the range's base, and a PR whose head is already in it was folded
    into an earlier PR, not this one."""
    folded = commit_class.Folds(repo, head, base=base) if head else None
    # Kind: values joined by US (0x1f), never a tab or a newline, so the
    # line stays one record; commit_class.kind takes the last of them.
    r = git.run(".", "log", "--format=%H%x09%P%x09%s%x09%(trailers:key=Answers,valueonly,unfold,separator=%x20)"
                "%x09%(trailers:key=Kind,valueonly,unfold,separator=%x1f)",
                rev_range, check=False)
    shas, cls, subj = [], {}, {}
    for line in r.stdout.splitlines():
        fields = line.split("\t", 4) + [""] * 4
        sha, parents, subject, answers, kind = fields[:5]
        if not sha:
            continue
        shas.append(sha)
        cls[sha] = commit_class.classify(parents, subject, answers, str(num), repo, kind, folded)
        subj[sha] = subject
    # Two passes: classify each commit, then net out every revert whose
    # partner is in the range — the pair changes nothing and counts
    # nothing, in whichever column each of them fell. A COMMIT NETS ONCE.
    # git log lists newest first, so a chain "feat A; revert A; reapply A"
    # is walked reapply → revert: the reapply nets the revert, and the
    # revert — already netted — no longer nets A, which stays work: the
    # tree after the chain is the tree after A. Netting every pair a commit
    # belongs to counted the whole chain as nothing (review, 2026-09-20, F1).
    skip: set[str] = set()
    for sha in shas:
        if sha in skip:
            continue
        body = git.run(".", "log", "-1", "--format=%b", sha, check=False).stdout
        for target in commit_class.revert_targets(body):
            for other in shas:
                if other.startswith(target) and other != sha and other not in skip and sha not in skip:
                    skip.update((sha, other))
    c = {"work": 0, "fix": 0, "merge": 0, "netted": 0, "fix_subjects": [], "netted_subjects": []}
    for sha in shas:
        # F2: what was netted is printed like the fix subjects, so the
        # column whose misread moves the band can be checked by eye.
        if sha in skip:
            c["netted"] += 1
            c["netted_subjects"].append(subj[sha])
        elif cls[sha] == "merge":
            c["merge"] += 1
        elif cls[sha] == "fix":
            c["fix"] += 1
            c["fix_subjects"].append(subj[sha])
        else:
            c["work"] += 1
    return c


# ── checks, threads, arming, queue, merge state ─────────────────────

def check_contexts(owner: str, name: str, num: int, after: str | None, head: str) -> list[dict]:
    """The check contexts of the PR's `head` from `after` on, page by page.
    Raises gh.GhError (or a lookup error on a malformed answer) when any
    page cannot be read, and ValueError for a continuation with no cursor
    (GitHub reads a null `after` as the first page, so it would be counted
    twice), a head that moved, or more than CONTEXT_PAGES pages."""
    nodes: list[dict] = []
    for _ in range(CONTEXT_PAGES):
        if not after:
            raise ValueError("a next page of checks with no cursor")
        data = gh.graphql(CONTEXTS_QUERY, owner=owner, name=name, number=num, after=after)
        pr = data["repository"]["pullRequest"]
        if not head or pr["headRefOid"] != head:
            raise ValueError("the head moved while its checks were read")
        page = pr["statusCheckRollup"]["contexts"]
        more = listed(page["nodes"])
        if more is None:
            raise TypeError("a page of checks that is not a list of objects")
        nodes += more
        info = obj(page.get("pageInfo"))
        if info is None:
            raise TypeError("a page of checks whose pageInfo is not an object")
        if not info.get("hasNextPage"):
            return nodes
        after = info.get("endCursor")
    raise ValueError(f"more than {CONTEXT_PAGES * 100} checks")


def gate_state(repo: str, num: int, head: str) -> dict | None:
    """The gate's reading of the PR, its checks those of `head`, the head
    its row reports: a push since the PR list was read makes them "?"."""
    owner, name = repo.split("/", 1)
    try:
        repository = obj(gh.graphql(GATE_QUERY, owner=owner, name=name, number=num).get("repository"))
    except (gh.GhError, ValueError):
        return None
    pr = repository.get("pullRequest") if repository is not None else None
    # The queue position is read, not counted: one that cannot be read
    # leaves no verdict to give, so the PR is unreadable as a whole.
    queued = obj(pr.get("mergeQueueEntry")) if isinstance(pr, dict) else None
    if not isinstance(pr, dict) or queued is None:
        return None
    rollup = obj(pr.get("statusCheckRollup"))
    contexts = obj(rollup.get("contexts")) if rollup is not None else None
    nodes = listed(contexts.get("nodes")) if contexts is not None else None
    cinfo = obj(contexts.get("pageInfo")) if contexts is not None else None
    if cinfo is None:
        nodes = None
    if not head or pr.get("headRefOid") != head:
        nodes = None
    if nodes is not None and cinfo.get("hasNextPage"):
        try:
            nodes = nodes + check_contexts(owner, name, num, cinfo.get("endCursor"), head)
        except (gh.GhError, ValueError, TypeError, KeyError, AttributeError):
            nodes = None
    checks = "?" if nodes is None else checks_of(nodes)
    page = obj(pr.get("reviewThreads"))
    threads = listed(page.get("nodes")) if page is not None else None
    info = obj(page.get("pageInfo")) if page is not None else None
    if info is None:
        threads = None
    if threads is not None and info.get("hasNextPage"):
        # Past the first 100 the count was short and read as whole (review
        # of #71): the rest are read page by page, and a rest that cannot be
        # read makes the count unknown, which blocks like any count but 0.
        # A null cursor is not a continuation: review_threads would start
        # again at the first page and count it twice.
        try:
            if not info.get("endCursor"):
                raise ValueError("a next page of review threads with no cursor")
            threads = threads + pr_review_status.review_threads(owner, name, num, after=info.get("endCursor"))
        except (gh.GhError, ValueError, TypeError, KeyError, AttributeError):
            threads = None
    queue = alt(queued.get("position"))
    return {
        "unresolved": "?" if threads is None else
                      str(sum(1 for t in threads if not alt(t.get("isResolved")))),
        "armed": "yes" if pr.get("autoMergeRequest") is not None else "no",
        "queue": "" if queue is None else jq_str(queue),
        "mstate": jq_str(alt(pr.get("mergeStateStatus"), "?")),
        "mergeable": jq_str(alt(pr.get("mergeable"), "?")),
        "checks": checks,
    }


def checks_of(nodes: list[dict]) -> str:
    red = [jq_str(alt(n.get("name"), n.get("context"))) if alt(n.get("name"), n.get("context")) is not None else ""
           for n in nodes if RED.search(str(alt(n.get("conclusion"), n.get("state"), "")))]
    pending = sum(1 for n in nodes
                  if (RUNNING_STATUS.search(str(alt(n.get("status"), ""))) or RUNNING_STATE.search(str(alt(n.get("state"), ""))))
                  and alt(n.get("conclusion"), "") == "")
    if red:
        return "red:" + ",".join(red)
    if pending:
        return f"pending:{pending}"
    if not nodes:
        return "none-yet"
    return "green"


def review_reader() -> list[str]:
    """The review reader's argv head: AGENT_FABRIC_PR_REVIEW_STATUS, a
    program of its own, else this checkout's `fabric-pr review-status`."""
    if os.environ.get("AGENT_FABRIC_PR_REVIEW_STATUS"):
        return [os.environ["AGENT_FABRIC_PR_REVIEW_STATUS"]]
    return [os.path.join(FABRIC, "bin", "fabric-pr"), "review-status"]


def review_of_head(reader: list[str], num: int) -> str:
    """pr-review-status's reading of the current head. A reader that
    cannot run is "?", like one that could not read the PR — the bash
    read a missing reader as "none"."""
    try:
        r = subprocess.run([*reader, str(num)], capture_output=True, text=True, timeout=300,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return "?"
    if r.returncode == 2:
        return "?"
    head_reviewed, any_review = "", 0
    for line in r.stdout.splitlines():
        m = HEAD_REVIEWED.match(line)
        if m and not head_reviewed:
            head_reviewed = m.group(1) or ""
        m = ANY_REVIEW.match(line)
        if m and m.group(1):
            any_review += int(m.group(1))
    if head_reviewed == "yes":
        return "head reviewed"
    return "NOT on head" if any_review > 0 else "none"


def awaiting_supply(body: str) -> list[str]:
    """An AWAITING-SUPPLY line in the body with no range line for that
    login: supply asked for and not folded (the reading owed-supply.sh
    and arm.sh share; #886 review F3 — the skill said this was read here
    and it was not). The login is matched literally: jq put it into the
    pattern raw."""
    logins = []
    for line in (body or "").split("\n"):
        m = AWAITING.match(line)
        if m:
            logins.append(m.group("who").split("/")[-1])
    return [l for l in logins
            if not re.search(r"[0-9a-f]{7,40}\.\.[0-9a-f]{7,40}:\s*" + re.escape(l) + r"([^A-Za-z0-9_-]|$)", body)]


def verdict(num: int, base: str, draft: bool, commits: dict | None, st: dict, review: str,
            awaiting: list[str]) -> str:
    blocks = []
    if draft:
        blocks.append("a draft — mark it ready first")
    if st["mergeable"] == "CONFLICTING":
        blocks.append(f"conflicts with {base}")
    checks = st["checks"]
    if checks.startswith("red:"):
        blocks.append(f"red checks: {checks[4:]}")
    if checks.startswith("pending:"):
        blocks.append(f"{checks[8:]} check(s) pending")
    if checks == "none-yet":
        blocks.append("no check has reported yet (seconds after a push, or nothing runs on this PR)")
    if checks == "?":
        blocks.append("the checks could not all be read")
    if review != "head reviewed":
        blocks.append(f"no review of the head ({review})")
    if st["unresolved"] != "0":
        blocks.append(f"{st['unresolved']} unresolved thread(s)")
    if awaiting:
        blocks.append(f"awaiting supply from {', '.join(awaiting)} (AWAITING-SUPPLY in the body, no range line yet)")
    if st["queue"]:
        return f"QUEUED (position {st['queue']}) — nothing to do"
    if st["armed"] == "yes" and not blocks:
        return "ARMED and clear — merges on the queue's run"
    if st["armed"] == "yes":
        return "ARMED but held: " + "; ".join(blocks)
    if blocks:
        return "BLOCKED: " + "; ".join(blocks)
    if commits is None:
        return "MERGEABLE — commits unknown (fetch the base); apply the count rule by hand"
    work = commits["work"]
    if work > 16:
        return f"MERGEABLE — {work} work commits, over 16: smaller batches next time; arm on the basis"
    if work >= 8:
        return f"MERGEABLE — arm: post the basis ({work} work commits, review on head) and gh pr merge {num} --auto"
    return f"MERGEABLE — ask the owner ({work} work commits < 8), then arm"


def owner_of(branch: str) -> str:
    """The session that opened it, from the branch's <host>/<login>/
    prefix — never the PR author, since every session pushes as one GitHub
    user. A branch of another shape has no session to name and is shown
    as its first segment."""
    p = branch.split("/")
    return "/".join(p[:2]) if len(p) >= 3 else p[0]


def render(row: dict) -> str:
    if row["commits_known"]:
        total = row["work_commits"] + row["fix_commits"] + row["merge_commits"] + row["netted_commits"]
        netted = f", {row['netted_commits']} netted by a revert" if row["netted_commits"] > 0 else ""
        commits = (f"{total} ({row['work_commits']} work, {row['fix_commits']} fix, {row['merge_commits']} merge"
                   f"{netted})")
    else:
        commits = "unknown (fetch)"
    queue = f"  queue={row['queue_position']}" if row["queue_position"] != "" else ""
    out = (f"#{row['number']}  {row['owner']}{' (me)' if row['mine'] else ''}  commits={commits}  "
           f"checks={row['checks']}  review={row['review']}  threads={row['unresolved_threads']}  "
           f"armed={row['armed']}{queue}\n      {jq_str(row['title'])[0:88]}")
    if row["fix_subjects"]:
        out += "\n      counted as fix: " + "; ".join(f'"{s[0:60]}"' for s in row["fix_subjects"])
    if row["netted_subjects"]:
        out += "\n      netted by a revert: " + "; ".join(f'"{s[0:60]}"' for s in row["netted_subjects"])
    return out + f"\n      {row['verdict']}"


# ── in flight ───────────────────────────────────────────────────────
# Every branch on origin is read from git, so a pushed branch with no PR
# is a row like any other; GitHub only adds which branches have one. The
# owner is the branch's <host>/<login> prefix, because every agent pushes
# as one GitHub user and the author says nothing about who did the work.
# Nothing here writes but the fetch, which pr-gate already does.

def in_flight(repo: str, as_json: bool, overlap: str, prefixes: list[str]) -> int:
    fetch_ok = prs_ok = True
    if not succeeds("fetch", "-q", "--prune", "origin"):
        fetch_ok = False
        seen = "never"
        path = git.run(".", "rev-parse", "--git-path", "FETCH_HEAD", check=False).stdout.strip()
        try:
            seen = dt.datetime.fromtimestamp(os.stat(path).st_mtime, dt.UTC).strftime("%Y-%m-%dT%H:%MZ")
        except OSError:
            pass
        note(f"git fetch origin failed — the rows below are what origin showed this clone at its last fetch ({seen})")
    base = os.environ.get("AGENT_FABRIC_PR_BASE", "")
    if not base:
        base = git.run(".", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False).stdout.strip() \
            or "origin/main"
    if not succeeds("rev-parse", "-q", "--verify", f"{base}^{{commit}}"):
        note(f"the base {base} is not in this clone")
        return 2

    try:
        prmap = gh.pr_list(["number", "headRefName"], repo=repo, limit=LIST_CAP)
        if not isinstance(prmap, list):
            raise ValueError
    except (gh.GhError, ValueError):
        prs_ok, prmap = False, []
        note('could not list pull requests — the PR column reads unavailable, never "no PR"')
    if len(prmap) >= LIST_CAP:
        note(f"{LIST_CAP} open pull requests read — the list is capped there.")

    rows = []
    # The full ref name: a short one is ambiguous beside a local branch
    # called origin/<x>, and origin/HEAD shortens to a bare "origin".
    refs = git.run(".", "for-each-ref",
                   "--format=%(refname)\t%(objectname)\t%(committerdate:iso8601-strict)\t%(committerdate:unix)",
                   "refs/remotes/origin/", check=False).stdout
    for line in refs.splitlines():
        ref, sha, when, epoch = (line.split("\t") + ["", "", "", ""])[:4]
        if not ref:
            continue
        name = ref.removeprefix("refs/remotes/origin/")
        if name == "HEAD" or f"origin/{name}" == base:
            continue
        if succeeds("merge-base", "--is-ancestor", sha, base):
            continue   # merged: not in flight
        m = re.match(r"([^/]+/[^/]+)/.+", name, re.S)
        owner = m.group(1) if m else "unattributed"
        if prs_ok:
            pr = next((p.get("number") for p in prmap if isinstance(p, dict) and p.get("headRefName") == name), None)
            pr = "none" if pr is None else pr
        else:
            pr = "unavailable"
        r = git.run(".", "rev-list", "--count", f"{base}..{sha}", check=False)
        ahead = int(r.stdout) if r.returncode == 0 and r.stdout.strip().isdigit() else None
        r = git.run(".", "diff", "--name-only", f"{base}...{sha}", check=False)
        if r.returncode != 0:
            note(f"{name} could not be diffed (deleted meanwhile?) — skipped")
            continue
        rows.append({"branch": name, "owner": owner,
                     "pr": int(pr) if re.fullmatch(r"[0-9]+", str(pr)) else pr,
                     "sha": sha, "last_commit": when, "epoch": int(epoch) if epoch.isdigit() else 0,
                     "ahead": ahead, "paths": [p for p in r.stdout.split("\n") if p]})

    # The target is found among ALL rows, before --path narrows them: a
    # target changing nothing under the prefix is still in flight.
    target = ""
    if overlap:
        if re.fullmatch(r"[0-9]+", overlap):
            if not prs_ok:
                note(f"#{overlap} cannot be resolved to a branch — the PR list is unavailable; name the branch instead")
                return 2
            target = next((r["branch"] for r in rows if r["pr"] == int(overlap)), "")
            if not target:
                note(f"#{overlap} is not an open PR with a branch in flight on origin")
                return 2
        else:
            target = overlap
            if not any(r["branch"] == target for r in rows):
                note(f"{target} is not a branch in flight on origin (merged, deleted, or not pushed)")
                return 2
        theirs = set(next(r["paths"] for r in rows if r["branch"] == target))
        shared_rows = []
        for r in rows:
            if r["branch"] != target:
                r["shared"] = [p for p in r["paths"] if p in theirs]
                if r["shared"]:
                    shared_rows.append(r)
        rows = shared_rows

    if prefixes:
        def under(p: str) -> bool:
            return any(p == x or p.startswith(x.removesuffix("/") + "/") for x in prefixes)
        rows = [r for r in rows if any(under(p) for p in r["paths"])]

    for r in rows:
        r["paths_total"] = len(r["paths"])
        r["paths"] = r["paths"][:INFLIGHT_PATHS_CAP]
        if "shared" in r:
            r["shared_total"] = len(r["shared"])
            r["shared"] = r["shared"][:INFLIGHT_PATHS_CAP]
    rows = sorted(rows, key=lambda r: r["epoch"])[::-1]
    for r in rows:
        del r["epoch"]

    if as_json:
        doc = {"base": base, "fetched_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "fetch_ok": fetch_ok, "prs_ok": prs_ok}
        if target:
            doc["overlap_with"] = target
        doc["rows"] = rows
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        if target:
            print(f"in flight on {repo} sharing a path with {target} (against {base}): {len(rows)} — no shared path "
                  "is not the same as compatible: two changes can clash in meaning without sharing a file")
        else:
            print(f"in flight on {repo} (not merged into {base}): {len(rows)}")
        for r in rows:
            pr = r["pr"]
            prs = f"#{pr}" if isinstance(pr, int) else ("no PR" if pr == "none" else "PR unavailable")
            line = (f"{r['owner']}  {r['branch']}  {prs}  ahead={jq_str(r['ahead'])}  last={r['last_commit'][0:16]}  "
                    f"paths={r['paths_total']}")
            if "shared" in r:
                line += (f"\n    shares {r['shared_total']}: {', '.join(r['shared'][:8])}"
                         f"{', …' if r['shared_total'] > 8 else ''}")
            print(line)
    return 0 if fetch_ok and prs_ok else 2


# ── the gate ────────────────────────────────────────────────────────

def run(argv: list[str]) -> int:
    as_json = show_all = inflight = False
    nums, overlap, prefixes = [], "", []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--all":
            show_all = True
        elif a == "--in-flight":
            inflight = True
        elif a == "--overlap":
            if i + 1 >= len(argv) or not argv[i + 1]:
                raise Usage("--overlap takes a PR number or a branch")
            inflight, overlap = True, argv[i + 1]
            i += 1
        elif a == "--path":
            if i + 1 >= len(argv) or not argv[i + 1]:
                raise Usage("--path takes a path prefix")
            prefixes.append(argv[i + 1])
            i += 1
        elif a in ("-h", "--help"):
            print(HELP)
            return 0
        elif re.fullmatch(r"[0-9]+", a):
            nums.append(a)
        else:
            raise Usage(f"unknown option '{a}' (try --help)")
        i += 1
    for tool in ("gh", "git"):
        if not shutil.which(tool):
            raise Usage(f"{tool} is required")

    try:
        repo = gh.this_repo()
    except gh.GhError as e:
        raise Usage(f"cannot read the repository: {e.reason}") from None
    session = session_prefix()

    if inflight:
        if nums or show_all:
            raise Usage("--in-flight and --overlap take no PR numbers and no --all (they read every branch)")
        return in_flight(repo, as_json, overlap, prefixes)
    if prefixes:
        raise Usage("--path goes with --in-flight or --overlap")

    # The PRs to read.
    prs = []
    if nums:
        for n in nums:
            try:
                one = json.loads(gh.run(["pr", "view", n, "--repo", repo, "--json", ",".join(PR_FIELDS)],
                                        what=f"gh pr view {n}"))
                if not isinstance(one, dict):
                    raise ValueError
            except (gh.GhError, ValueError):
                note(f"#{n} is not a pull request of {repo} (or gh could not read it)")
                continue
            if one.get("state") != "OPEN":
                note(f"#{n} is {jq_str(one.get('state'))} — not at any gate; skipped.")
                continue
            prs.append(one)
    else:
        try:
            prs = gh.pr_list(PR_FIELDS, repo=repo, limit=LIST_CAP)
            if not isinstance(prs, list):
                raise ValueError
        except (gh.GhError, ValueError):
            raise Usage("could not list pull requests") from None
        if len(prs) >= LIST_CAP:
            note(f"{LIST_CAP} open pull requests read — the list is capped there.")
        if not show_all:
            prs = [p for p in prs if str(p.get("headRefName") or "").startswith(f"{session}/")]
    if not prs:
        if as_json:
            print("[]")
        elif nums:
            print(f"pr-gate: none of the numbers given is a pull request of {repo}.")
        elif show_all:
            print(f"pr-gate: no open pull request on {repo}.")
        else:
            print(f"pr-gate: no open pull request from {session} on {repo} (branch prefix {session}/).")
        return 0

    # A failed fetch is said, not swallowed: the counts below are read from
    # the local clone, and a stale or missing origin makes them wrong in
    # both directions (review F2 on #886).
    fetched = succeeds("fetch", "-q", "origin")
    if not fetched:
        note("git fetch origin failed — the base is stale, so no commit count is trusted (commits unknown)")
    reader = review_reader()
    rows = []
    for p in prs:
        num, head, base = p.get("number"), jq_str(p.get("headRefOid")), jq_str(p.get("baseRefName"))
        branch = jq_str(p.get("headRefName"))
        commits = count_commits(num, repo, base, head) if fetched else None
        st = gate_state(repo, num, head)
        if st is None:
            note(f"could not read pull request #{num} from GitHub (the graphql read failed); nothing is invented — "
                 "run again.")
            return 2
        review = review_of_head(reader, num)
        awaiting = awaiting_supply(p.get("body") or "")
        owner = owner_of(branch)
        known = commits is not None
        rows.append({
            "number": num, "title": p.get("title"), "branch": branch, "owner": owner, "mine": owner == session,
            "head": head[:8],
            "work_commits": commits["work"] if known else None,
            "fix_commits": commits["fix"] if known else None,
            "fix_subjects": commits["fix_subjects"] if known else [],
            "merge_commits": commits["merge"] if known else None,
            "netted_commits": commits["netted"] if known else None,
            "netted_subjects": commits["netted_subjects"] if known else [],
            "commits_known": known,
            "awaiting_supply": awaiting,
            "checks": st["checks"], "review": review, "unresolved_threads": st["unresolved"], "armed": st["armed"],
            "queue_position": st["queue"], "merge_state": st["mstate"], "draft": alt(p.get("isDraft")) is True,
            "verdict": verdict(num, base, alt(p.get("isDraft")) is True, commits, st, review, awaiting),
        })
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            print(render(row))
    return 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except Usage as e:
        note(str(e))
        return 2
    except git.GitError as e:
        note(f"{e} — git could not be read; nothing is invented.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
