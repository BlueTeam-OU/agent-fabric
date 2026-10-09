#!/usr/bin/env python3
"""runtime/github/pr-compliance.sh [--days N] [--json]        (default: 7)

The Actions-minute compliance measures, from GitHub and the fetched
origin.

A project that pays for its CI minutes sets targets that nothing else
measures: how many pull_request CI runs a pull request pays before it
lands (the open and the fold), whether one under the count rule's
work-commit floor states the class of exemption that let it open, how
many standalone i18n-only pull requests land, and how many supply
branches sit past their FOLD-BY.
This prints them for a window of merged pull requests, and names every
pull request behind each number so the number can be argued with.

The numbers are the project's: projects/<id>/integration/gh/
compliance.json in agent-fabric (the working copy's project), or the
file AGENT_FABRIC_COMPLIANCE_CONFIG names. A project that declares none
is exit 2.

For each pull request merged in the window:
  runs        pull_request runs of the project's workflow on its head
              branch created while it was open, createdAt to mergedAt
              ("?" when they cannot be read — never zero; "N+" when the
              read was full, a lower bound)
  work/fix    its commits over the base, classed as the gate classes
              them before arming (commit_class), a revert and the commit
              it reverts netted ("N netted" in the row, netted_commits in
              --json)
  exemption   under the floor, does the body or a comment state why it
              opened anyway (the project's exemption phrases)
  i18n-only   every changed file under the project's i18n prefix
  bot         a bot's pull request (the project's bot branch prefix):
              shown as "bot" in the EXEMPT column and kept out of the
              under-the-floor list — the count rule binds sessions, and a
              bot cannot state an exemption. Its runs still count.
Plus, from owed-supply: supply branches past the default FOLD-BY and
open pull requests awaiting a AWAITING-SUPPLY.

Exit codes:
  0  measured (a window with no merged pull request is said)
  2  gh, git, the project's numbers or owed-supply could not be read

Reads GitHub (the repository is GH_REPO, else this working copy's origin
on github.com) and the fetched origin (git log over each merge commit's
parents); nothing in the working copy is touched. It runs `git fetch
origin` first; when that fails it says so on stderr and still measures,
from the origin the clone last fetched — so a count may be stale, and a
merge commit never fetched reads 'unknown'. --json carries the same fact
as `origin_fetched` (true/false).
"""
# The docstring is --help, whole. Ported from a managed project's
# tools/gh/pr-compliance.sh (ADR-040; its test, run unchanged but for the
# two cases below, the oracle).
#
# THE CONTRACT, frozen from devex-tooling's port contract 2/8 and its
# rulings of 2026-10-08:
#   argv    [--days N] [--json] [-h|--help], read in order: --help prints
#           this docstring and exits 0 where it stands; --days takes the
#           next word, ASCII digits only, 1 or more, read as decimal and
#           printed as written, else "pr-compliance: --days needs a whole
#           number of 1 or more", exit 2; any other word "pr-compliance:
#           unknown option '<x>' (try --help)", exit 2.
#   env     GH_REPO (through gh.this_repo); AGENT_FABRIC_COMPLIANCE_CONFIG
#           (a compliance.json used instead of the project's);
#           AGENT_FABRIC_OPERATOR, else AGENT_FABRIC_ROOT (the tree whose
#           projects/ holds it, as arm reads it); AGENT_FABRIC_OWED_SUPPLY, a TEST SEAM only — a
#           command run as `bash <it> --json` instead of owed-supply in
#           process (a project's forwarder maps its old name onto it).
#   config  {workflow, i18n_prefix (null drops the I18N column and its
#           line), i18n_target_note (optional, printed after the i18n
#           count), floor (>= 1), runs_target (>= 0), exemption (a regex,
#           matched case-insensitively), bot_prefix}; the printed
#           "under <floor>" and "(target <runs_target>; …)" are its numbers.
#   reads   the merged pull requests since now - N days (200 at most:
#           number, title, headRefName, baseRefName, createdAt, mergedAt,
#           mergeCommit, body, files, comments); per pull request the
#           workflow's pull_request runs on its head branch (100 at
#           most), counted when created in [createdAt, mergedAt]; `git fetch -q origin`, once; per merge commit the split
#           of <merge>^1..<merge>^2 (pr_gate.split_range).
#   stdout  the lines below, verbatim; --json one object, indented two
#           spaces as jq printed it.
#   stderr  the fetch line (the run goes on, origin_fetched false); and
#           one line per refusal, each "pr-compliance: …", exit 2: gh is
#           required; git is required; the compliance.json lines; cannot
#           read the repository: <why>; could not list merged pull
#           requests; owed-supply could not run: <its line>.
#   exit    0 measured, 2 could not measure. Never a traceback.
# Departures from the bash, each agreed with devex-tooling (2026-10-08):
# the numbers are project config, not the bash's literals; the repository is
# gh.this_repo(), never `gh repo view`'s default (#109); no jq; every call
# is bounded, and a run count that fails or times out is null ("?"), never
# zero; the classifier is the fabric's commit_class in process, so the
# oracle's stub-log case and its "no agent-fabric" case are retired (this
# module's test pins the first in process); owed-supply runs in process,
# AGENT_FABRIC_OWED_SUPPLY its test seam. A title is carried as GitHub
# gave it, where the bash's @tsv-and-read mangled a tab or a backslash.
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
import git  # noqa: E402
import roots  # noqa: E402
from github import local, owed_supply, pr_gate  # noqa: E402

OWED_SUPPLY_TIMEOUT_S = 600
_SURROGATE = re.compile("[\ud800-\udfff]")


class Refusal(Exception):
    """The run cannot measure: its line goes to stderr, exit 2."""


def parse_args(argv: list[str]) -> tuple[int, str, bool] | None:
    """(days, days as written, json), or None when --help was asked."""
    days, days_word, as_json = 7, "7", False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--days":
            word = argv[i + 1] if i + 1 < len(argv) else ""
            if not re.fullmatch(r"[0-9]+", word) or int(word) < 1:
                raise Refusal("--days needs a whole number of 1 or more")
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


# ── the project's numbers ────────────────────────────────────────────

def config_path() -> str:
    explicit = os.environ.get("AGENT_FABRIC_COMPLIANCE_CONFIG", "")
    if explicit:
        return explicit
    top = local.toplevel()
    if not top:
        return ""
    try:
        import workingcopy
        pid = workingcopy.resolve(top).get("project")
    except (Exception, SystemExit):   # a marker naming nothing the registry knows exits
        pid = None
    return roots.project_integration(pid, "gh", "compliance.json") if pid else ""


def load_config(path: str) -> dict:
    if not path:
        raise Refusal("no project found for this working copy, so no compliance.json to read its numbers from"
                      " (projects/<id>/integration/gh/compliance.json in agent-fabric, or"
                      " AGENT_FABRIC_COMPLIANCE_CONFIG)")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        cfg = {
            "workflow": doc["workflow"], "i18n_prefix": doc["i18n_prefix"], "floor": doc["floor"],
            "runs_target": doc["runs_target"], "exemption": re.compile(doc["exemption"], re.I),
            "bot_prefix": doc["bot_prefix"], "i18n_target_note": doc.get("i18n_target_note"),
        }
        if cfg["i18n_target_note"] is not None and not isinstance(cfg["i18n_target_note"], str):
            raise TypeError("i18n_target_note is neither absent nor a string")
        for key in ("workflow", "bot_prefix"):
            if not (isinstance(cfg[key], str) and cfg[key]):
                raise TypeError(f"{key} is not a non-empty string")
        if cfg["i18n_prefix"] is not None and not (isinstance(cfg["i18n_prefix"], str) and cfg["i18n_prefix"]):
            raise TypeError("i18n_prefix is neither null nor a non-empty string")
        if type(cfg["floor"]) is not int or cfg["floor"] < 1:
            raise TypeError("floor is not a whole number of 1 or more")
        if type(cfg["runs_target"]) is not int or cfg["runs_target"] < 0:
            raise TypeError("runs_target is not a whole number")
    except FileNotFoundError:
        raise Refusal(f"this project declares no compliance.json ({path}); its numbers cannot be read") from None
    except (OSError, ValueError, KeyError, TypeError, re.error) as e:
        raise Refusal(f"{path} is not a usable compliance.json ({type(e).__name__}: {e})") from None
    return cfg


# ── the reads ────────────────────────────────────────────────────────

def merged_pull_requests(repo: str, since: str) -> list[dict]:
    try:
        prs = gh.pr_list(["number", "title", "headRefName", "baseRefName", "createdAt", "mergedAt", "mergeCommit",
                          "body", "files", "comments"], repo=repo, state="merged", search=f"merged:>={since}", limit=200)
    except (gh.GhError, ValueError):
        raise Refusal("could not list merged pull requests") from None
    if not isinstance(prs, list) or not all(isinstance(p, dict) and type(p.get("number")) is int for p in prs):
        raise Refusal("could not list merged pull requests")
    return prs


RUNS_READ = 100


def pull_request_runs(repo: str, workflow: str, branch: str, opened: str, merged: str) -> tuple[int | None, bool]:
    """This pull request's runs: on its head branch, created while it was
    open. A branch name is not a pull request — an earlier one on the same
    name, or a fork's `main`, counted into the row — so the count is
    scoped to [opened, merged]. Runs outlive the branch the queue deletes,
    so a merged pull request's count is still readable; one that cannot be
    read is None. The second value: the read was full, so the count is a
    lower bound."""
    # An empty --branch is no filter at all, and no window is no scope:
    # either would be a plausible number that is not this pull request's.
    if not branch or not opened or not merged:
        return None, False
    try:
        out = gh.run(["run", "list", "--repo", repo, "--workflow", workflow, "--event", "pull_request", "--branch",
                      branch, "--limit", str(RUNS_READ), "--json", "databaseId,createdAt"], what="gh run list")
        runs = json.loads(out)
    except (gh.GhError, ValueError):
        return None, False
    if not isinstance(runs, list) or not all(isinstance(r, dict) and isinstance(r.get("createdAt"), str) for r in runs):
        return None, False
    # The runs API's timestamps and the pull request's are both UTC "Z",
    # so they order as text.
    return sum(1 for r in runs if opened <= r["createdAt"] <= merged), len(runs) >= RUNS_READ


def fetch_origin() -> bool:
    """A failed fetch is said, not swallowed (as pr-gate does): the
    work/fix counts are read from the clone's origin, so a stale one gives
    yesterday's numbers with no sign — and --json carries it as
    origin_fetched, so a reader of the data sees it too."""
    try:
        fetched = git.run(".", "fetch", "-q", "origin", check=False).returncode == 0
    except git.GitError:
        fetched = False
    if not fetched:
        print("pr-compliance: git fetch origin failed — commit counts come from the origin this clone last fetched "
              "and may be stale; a merge commit it never saw reads 'unknown'", file=sys.stderr)
    return fetched


def commit_split(num: int, repo: str, merge_commit: str) -> dict | None:
    """The pull request's own commits, first parent the base and second its
    head, split as the gate splits them before arming — or the band
    measured after the merge is not the band applied before it. None when
    the clone cannot answer: no merge commit, one never fetched, or one
    with no second parent."""
    if not merge_commit:
        return None
    try:
        if not git.ok(".", "cat-file", "-e", f"{merge_commit}^{{commit}}") \
                or not git.ok(".", "rev-parse", "--verify", "-q", f"{merge_commit}^2"):
            return None
    except git.GitError:
        return None
    return pr_gate.split_range(num, repo, f"{merge_commit}^1..{merge_commit}^2", f"{merge_commit}^2",
                               f"{merge_commit}^1")


def supply(repo: str) -> dict:
    seam = os.environ.get("AGENT_FABRIC_OWED_SUPPLY", "")
    if not seam:
        try:
            return owed_supply.measure(repo)
        except owed_supply.Refusal as e:
            raise Refusal(f"owed-supply could not run: owed-supply: {e}") from None
    try:
        r = subprocess.run(["bash", seam, "--json"], capture_output=True, text=True, timeout=OWED_SUPPLY_TIMEOUT_S,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Refusal(f"owed-supply could not run: {type(e).__name__}") from None
    if r.returncode != 0:
        lines = [l for l in r.stderr.splitlines() if l.strip()] or [f"exit {r.returncode}"]
        raise Refusal(f"owed-supply could not run: {lines[-1]}")
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = None
    if not isinstance(doc, dict) or not isinstance(doc.get("owed"), list) or not isinstance(doc.get("awaiting"), list):
        raise Refusal("owed-supply could not run: its --json is not {owed, landed, awaiting}")
    return doc


# ── the measure ──────────────────────────────────────────────────────

def row(p: dict, repo: str, cfg: dict) -> dict:
    num, branch = p["number"], p.get("headRefName") or ""
    mc = p.get("mergeCommit").get("oid") if isinstance(p.get("mergeCommit"), dict) else None
    mc = mc if isinstance(mc, str) else ""
    split = commit_split(num, repo, mc)
    known = split is not None
    split = split or {"work": 0, "fix": 0, "merge": 0, "netted": 0}
    comments = p.get("comments") if isinstance(p.get("comments"), list) else []
    text = "\n".join([p.get("body") or ""] + [(c.get("body") or "") if isinstance(c, dict) else "" for c in comments])
    exempt = bool(cfg["exemption"].search(text))
    bot = branch.startswith(cfg["bot_prefix"])
    files = p.get("files") if isinstance(p.get("files"), list) else []
    paths = [f.get("path") if isinstance(f, dict) else None for f in files]
    i18n = bool(cfg["i18n_prefix"]) and len(paths) > 0 and all(
        isinstance(x, str) and x.startswith(cfg["i18n_prefix"]) for x in paths)
    opened = p.get("createdAt") if isinstance(p.get("createdAt"), str) else ""
    merged = p.get("mergedAt") if isinstance(p.get("mergedAt"), str) else ""
    runs, saturated = pull_request_runs(repo, cfg["workflow"], branch, opened, merged)
    return {"number": num, "title": p.get("title") if isinstance(p.get("title"), str) else "", "branch": branch,
            "merged_at": merged, "pull_request_runs": runs, "pull_request_runs_lower_bound": saturated,
            "work_commits": split["work"], "fix_commits": split["fix"], "merge_commits": split["merge"],
            "netted_commits": split["netted"], "commits_known": known, "exemption_stated": exempt, "bot": bot,
            "i18n_only": i18n,
            "under_floor_unstated": known and split["work"] < cfg["floor"] and not exempt and not bot}


def per_pr(total: int, known: int) -> int | float | None:
    """total / known to two places, rounded half away from zero as jq's
    round did; an integral value is an int, as jq printed it."""
    if not known:
        return None
    v = math.floor(total / known * 100 + 0.5) / 100
    return int(v) if v.is_integer() else v


def summary(rows: list[dict], days: int, since: str, fetched: bool, owed: dict, cfg: dict) -> dict:
    counted = [r["pull_request_runs"] for r in rows if r["pull_request_runs"] is not None]
    return {
        "window_days": days, "since": since, "origin_fetched": fetched, "merged": len(rows),
        "pull_request_runs": {
            "known": len(counted), "total": sum(counted), "per_pr": per_pr(sum(counted), len(counted)),
            # A full read clipped a row: the total and the mean are then
            # at least these, never exactly.
            "lower_bound": any(r["pull_request_runs_lower_bound"] for r in rows if r["pull_request_runs"] is not None),
            "over_target": [r["number"] for r in rows
                            if r["pull_request_runs"] is not None and r["pull_request_runs"] > cfg["runs_target"]]},
        "under_floor_unstated": [r["number"] for r in rows if r["under_floor_unstated"]],
        "i18n_only": [r["number"] for r in rows if r["i18n_only"]],
        "supply_past_fold_by": [o.get("branch") for o in owed["owed"]
                                if isinstance(o, dict) and o.get("past_default_fold_by") is True],
        "awaiting_supply": [a.get("number") for a in owed["awaiting"] if isinstance(a, dict)],
        "prs": rows,
    }


def _clean(v):
    """A lone surrogate (valid JSON, unprintable UTF-8) as the replacement
    character jq wrote for it."""
    if isinstance(v, str):
        return _SURROGATE.sub("\ufffd", v)
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


def numbers(xs: list) -> str:
    return " ".join(f"#{x}" for x in xs) if xs else "none"


def say(s: dict, repo: str, days_word: str, cfg: dict) -> None:
    print(f"pr-compliance: {s['merged']} pull request(s) merged on {repo} in the last {days_word} day(s)"
          f" (since {s['since']}).")
    i18n = cfg["i18n_prefix"] is not None
    if s["prs"]:
        cells = []
        for r in s["prs"]:
            netted = f", {r['netted_commits']} netted" if r["netted_commits"] > 0 else ""
            commits = (f"{r['work_commits']} work, {r['fix_commits']} fix, {r['merge_commits']} merge{netted}"
                       if r["commits_known"] else "unknown (fetch)")
            exempt = "bot" if r["bot"] else "n/a" if r["work_commits"] >= cfg["floor"] and r["commits_known"] \
                else "stated" if r["exemption_stated"] else "NONE"
            runs = "?" if r["pull_request_runs"] is None else \
                f"{r['pull_request_runs']}{'+' if r['pull_request_runs_lower_bound'] else ''}"
            cells.append([f"#{r['number']}", runs, commits, exempt] + (["ONLY" if r["i18n_only"] else "-"] if i18n else [])
                         + [r["title"][0:60]])
        # The COMMITS column is as wide as its widest cell: a fixed width
        # let a "…, 2 netted" cell push EXEMPT out from under its header,
        # the column a reader scans for NONE.
        cw = max([len("COMMITS")] + [len(c[2]) for c in cells])
        line = "  {:<6} {:<5} {:<%d} {:<9}%s {}" % (cw, " {:<9}" if i18n else "")
        print(line.format("PR", "RUNS", "COMMITS", "EXEMPT", *(["I18N"] if i18n else []), "TITLE"))
        for c in cells:
            print(line.format(*c))
    print()
    runs = s["pull_request_runs"]
    ge = "≥" if runs["lower_bound"] else ""
    print(f"pull_request runs per merged PR: {'unknown' if runs['per_pr'] is None else ge + str(runs['per_pr'])}"
          f" (target {cfg['runs_target']}; {ge}{runs['total']} runs over {runs['known']} PR(s); over target:"
          f" {numbers(runs['over_target'])})")
    print(f"under {cfg['floor']} work commits with no exemption stated: {numbers(s['under_floor_unstated'])}")
    if i18n:
        only = s["i18n_only"]
        named = f" ({numbers(only)})" if only else ""
        note = f" {cfg['i18n_target_note']}" if cfg["i18n_target_note"] else ""
        print(f"standalone i18n-only PRs: {len(only)}{named}{note}")
    past = s["supply_past_fold_by"]
    print(f"supply branches past the default FOLD-BY: {' '.join(past) if past else 'none'}")
    print(f"open PRs awaiting a AWAITING-SUPPLY: {numbers(s['awaiting_supply'])}")


def run(argv: list[str]) -> int:
    parsed = parse_args(argv)
    if parsed is None:
        print(__doc__.strip("\n"))
        return 0
    days, days_word, as_json = parsed
    for tool in ("gh", "git"):
        if not shutil.which(tool):
            raise Refusal(f"{tool} is required")
    cfg = load_config(config_path())
    try:
        repo = gh.this_repo()
    except gh.GhError as e:
        raise Refusal(f"cannot read the repository: {e.reason}") from None
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    merged = merged_pull_requests(repo, since)
    fetched = fetch_origin()
    rows = [row(p, repo, cfg) for p in merged]
    s = summary(rows, days, since, fetched, supply(repo), cfg)
    if as_json:
        print(json.dumps(_clean(s), ensure_ascii=False, indent=2))
    else:
        say(_clean(s), repo, days_word, cfg)
    return 0


def main() -> int:
    # The bash wrote UTF-8 whatever the locale; so does this, or the em
    # dashes in its own lines fail under a non-UTF-8 LANG.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    try:
        return run(sys.argv[1:])
    except Refusal as e:
        print(f"pr-compliance: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
