#!/usr/bin/env python3
"""tools/fabric/ci_warnings.py — the warnings and deprecations a repository's
recent CI runs print, each once, with its workflow, job, step and count.

    fabric-ci-warnings [--repo OWNER/NAME] [--runs N] [--workflow NAME] [--branch B] [--level L[,L]] [--json]

Read-only: it lists the repository's latest completed workflow runs, their
jobs, each job's check-run annotations and its run log, through gh (gh.py),
sends only GETs and changes nothing on GitHub or here, bar the line each gh call leaves in the local gh ledger like every tool's. The owner of a repository's `.github/` runs it
and fixes what it names (the owner's rule of 2026-11-01: every managed
repository's CI warnings and deprecations are cleared by its owner).

Contract.
  argv     --repo defaults to this working copy's origin (gh.this_repo, never gh's
           own default); --runs 1..100 (default 10) is how many of the newest
           completed runs are read; --workflow keeps the runs whose workflow name
           or file name equals it; --branch keeps one branch's runs; --level keeps the
           findings of those levels (warning, notice, log; default all three — `log`
           is the text match, which a build that prints hundreds of its own
           "warning:" lines makes long); --json prints
           the findings as one JSON object (with a `cleared` object, below). Anything
           else is a usage error.
  stdout   the report. One finding per distinct (workflow, job, step, level,
           message); `count` is how many times it was printed over the runs read,
           `runs` in how many of them. Most frequent first.
  stderr   a failure or a usage error, one line, no traceback.
  exit     0 every job of every run read, findings or none; 1 the runs could not be
           listed, or the repository's declaration (below) could not be read or is invalid; 2 usage; 3 some job's log or annotations could not be read (the
           report still lists the rest, and says which jobs were not read — an
           unread job is unknown, never "clean").

What is a finding, and its limits.
  - A log line the runner marks `##[warning]` or `##[notice]` (what `::warning::` and
    `::notice::` print). A multi-line message is read by its marked first line only.
  - An annotation of the job's check run at level warning or notice that no log line
    carries (the runner's own notices, such as an image migration, are annotations
    only); it has no step.
  - An unmarked log line outside the runner's echo of a step's script and
    environment that has the word "deprecated" or "deprecation" in it, or starts
    with warn/warning/npm warn: level `log`. A step's own `::group::Run …` is taken
    for the runner's echo and its unmarked lines are not read. This is a text match, so a program that prints such a word in its own
    output is reported too; the finding names the line for a person to judge.
    Gradle's welcome-banner item "Important project hierarchy lookup deprecations" is
    the one line of that kind read as not a warning at all.
  - The repository's owner clears a level-`log` finding in the owner's own repository,
    never here: `.github/ci-warnings-cleared.json` on the default branch, read through
    the contents API, absent (HTTP 404) meaning nothing is declared:
        {"cleared": [{"regex": "<pattern>", "reason": "<why this is not a warning>"}]}
    `regex` must match the whole message (re.fullmatch, after the cleaning below) and
    `reason` is required, and both are shown with control characters made inert; a
    pattern is run unbounded, so one that backtracks catastrophically stalls the run; no other key is accepted, so a typo is refused, not ignored.
    Only level `log` is clearable: a line GitHub marks warning or notice stays a
    finding until the workflow stops printing it. A cleared finding leaves the list
    and is counted and said: "N cleared by <file>" with each entry's reason and its
    own count (an entry matching nothing says 0, so a stale one is seen), and in
    --json under `cleared`. A declaration that cannot be read for any reason but its
    absence, or is invalid, fails the run (exit 1): an unknown declaration never
    clears a line. It applies to every run read, whatever its branch; it clears
    only when --level includes log.
  - The step is found from the line's timestamp against the job's step times, which
    GitHub gives to the second. A second shared by two steps names both, joined by
    " | "; a line outside every step is "(no step)". Never a guess between them.
  - Messages are compared after stripping ANSI colours and runs of whitespace;
    nothing else is normalised, so a warning that embeds a run-specific value counts
    once per value.
A job that was skipped, or has not finished, is not read.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import gh  # noqa: E402

LEVELS = ("warning", "notice", "log")
MAX_RUNS = 100
DEFAULT_RUNS = 10
SHOW_WIDTH = 400   # the text report cuts a message here; --json keeps it whole

_STAMP = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?Z ?")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_MARKED = re.compile(r"##\[(warning|notice)\](.*)")
_GROUP = re.compile(r"##\[group\](.*)")
# The groups the runner and a `run:` step open for what they echo — the header's
# image and permissions, the script, the env — whose lines are not the step's output.
_ECHO_GROUP = re.compile(r"^(?:Run |Runner Image|Operating System|GITHUB_TOKEN Permissions|Job defined at)")
# The word, not the stem: apt lists node-util-deprecate and a hundred lines about it.
_DEPRECATED = re.compile(r"\b(?:deprecated|deprecation\w*)\b", re.IGNORECASE)
_WARN_START = re.compile(r"^\s*(?:npm warn\b|warn(?:ing)?\s*[:\]])", re.IGNORECASE)
_REPO = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
# An item of Gradle's welcome banner, not a deprecation the build reports; the whole message, so a
# real line that merely starts with the words is still read.
_NOT_A_WARNING = re.compile(r"(?:[-*\u2022]\s*)?Important project hierarchy lookup deprecations\.?")
CLEARED_FILE = ".github/ci-warnings-cleared.json"


class Unread(Exception):
    """A job's log or annotations, or the repository's cleared-file, could not be read: said, never skipped."""


# What is left of a control character after colours are gone (an OSC title, a private CSI, a bell) must not
# reach a terminal: log text is a stranger's.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def clean(text: str) -> str:
    # Whitespace is folded first: a CRLF is a line ending, not an escape to show as "?".
    return " ".join(_CONTROL.sub("?", word) for word in _ANSI.sub("", text).split())


def _second(stamp: str | None) -> dt.datetime | None:
    if not stamp:
        return None
    try:
        return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).replace(microsecond=0)
    except ValueError:
        return None


def parse_log(text: str) -> list[tuple[dt.datetime | None, str, str]]:
    """(second, level, message) for each warning-like line of a job log, in order.
    level is warning, notice or log (an unmarked line, see the module header)."""
    found: list[tuple[dt.datetime | None, str, str]] = []
    in_echo = False
    in_group = False
    for raw in text.lstrip("\ufeff").splitlines():
        stamp = _STAMP.match(raw)
        when = _second(stamp.group(1) + "Z") if stamp else None
        line = raw[stamp.end():] if stamp else raw
        marked = _MARKED.fullmatch(line)
        if marked:
            message = clean(marked.group(2))
            if message:
                found.append((when, marked.group(1), message))
            continue
        group = _GROUP.fullmatch(line)
        if group:
            in_group, in_echo = True, bool(_ECHO_GROUP.match(group.group(1)))
            continue
        if line.startswith("##[endgroup]"):
            in_group = in_echo = False
            continue
        if line.startswith("##["):
            continue
        if in_group and in_echo:
            continue
        message = clean(line)
        if _NOT_A_WARNING.fullmatch(message):
            continue
        # A line opening with a quote or brace is a structured dump (CodeQL prints its tool
        # configuration as JSON, whose option descriptions say "DEPRECATED"), not a warning.
        if message and message[0] not in '"{[' and (_DEPRECATED.search(message) or _WARN_START.match(message)):
            found.append((when, "log", message))
    return found


class Declaration:
    """The repository's own clearing of level-`log` findings (CLEARED_FILE)."""

    def __init__(self, entries: list[tuple[re.Pattern, str]] | None = None) -> None:
        self.entries = entries or []

    @classmethod
    def parse(cls, text: str) -> "Declaration":
        try:
            doc = json.loads(text)
        except ValueError as e:
            raise Unread(f"{CLEARED_FILE} is not JSON: {e}") from None
        if not isinstance(doc, dict) or set(doc) != {"cleared"} or not isinstance(doc["cleared"], list):
            raise Unread(f'{CLEARED_FILE} must be {{"cleared": [...]}} and nothing else')
        entries = []
        for i, item in enumerate(doc["cleared"]):
            if not isinstance(item, dict) or set(item) != {"regex", "reason"} \
                    or not all(isinstance(v, str) for v in item.values()) or not item["reason"].strip():
                raise Unread(f'{CLEARED_FILE} entry {i} must be {{"regex": ..., "reason": ...}} with a reason')
            try:
                entries.append((re.compile(item["regex"]), item["reason"].strip()))
            except re.error as e:
                raise Unread(f"{CLEARED_FILE} entry {i}: bad regex: {e}") from None
        return cls(entries)

    def split(self, rows: list[dict]) -> tuple[list[dict], dict]:
        """(rows still findings, the cleared summary). First matching entry takes a row."""
        kept, per = [], [{"regex": rx.pattern, "reason": why, "count": 0, "distinct": 0} for rx, why in self.entries]
        for row in rows:
            hit = None
            if row["level"] == "log":
                hit = next((i for i, (rx, _) in enumerate(self.entries) if rx.fullmatch(row["message"])), None)
            if hit is None:
                kept.append(row)
            else:
                per[hit]["count"] += row["count"]
                per[hit]["distinct"] += 1
        return kept, {"file": CLEARED_FILE, "count": sum(p["count"] for p in per),
                      "distinct": sum(p["distinct"] for p in per), "entries": per}


def read_declaration(repo: str) -> Declaration:
    """Absent (HTTP 404) is no declaration; any other failure is Unread, never 'nothing cleared'."""
    what = f"gh api GET contents/{CLEARED_FILE}"
    try:
        doc = gh.api(f"repos/{repo}/contents/{CLEARED_FILE}")
    except gh.GhError as e:
        if e.status == 404:
            return Declaration()
        raise Unread(str(e)) from None
    try:
        if not isinstance(doc, dict) or doc.get("encoding") != "base64":
            raise ValueError("not a base64 file")
        text = base64.b64decode(doc["content"], validate=False).decode("utf-8")
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise Unread(f"{what}: the answer is not a readable file") from None
    return Declaration.parse(text)


def step_names(steps: list[dict], when: dt.datetime | None) -> str:
    """The step(s) whose [started, completed] seconds contain `when`."""
    if when is None:
        return "(no step)"
    names = []
    for step in steps:
        start, end = _second(step.get("started_at")), _second(step.get("completed_at"))
        if start is not None and end is not None and start <= when <= end:
            names.append(clean(str(step.get("name", "?"))))
    return " | ".join(names) if names else "(no step)"


class Findings:
    """Distinct findings with their counts; the key is what makes two the same."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str, str, str], dict] = {}

    def add(self, workflow: str, job: str, step: str, level: str, message: str, run_id: int) -> None:
        key = (workflow, job, step, level, message)
        row = self.rows.setdefault(key, {"workflow": workflow, "job": job, "step": step, "level": level,
                                         "message": message, "count": 0, "run_ids": []})
        row["count"] += 1
        if run_id not in row["run_ids"]:
            row["run_ids"].append(run_id)

    def ordered(self) -> list[dict]:
        out = []
        for row in self.rows.values():
            out.append({**{k: v for k, v in row.items() if k != "run_ids"}, "runs": len(row["run_ids"]),
                        "latest_run": max(row["run_ids"])})
        return sorted(out, key=lambda r: (-r["count"], r["workflow"], r["job"], r["step"], r["level"], r["message"]))


def job_findings(job: dict, log: str, annotations: list[dict]) -> list[tuple[str, str, str]]:
    """(step, level, message) for one job: its log's findings, plus the annotations the log does not carry."""
    steps = job.get("steps") or []
    out = [(step_names(steps, when), level, message) for when, level, message in parse_log(log)]
    carried = {(level, message) for _, level, message in out if level != "log"}
    for note in annotations:
        level = note.get("annotation_level")
        if level not in ("warning", "notice"):
            continue
        text = str(note.get("message") or "")
        first = clean(text.strip().splitlines()[0]) if text.strip() else ""
        # Equal, not contained: a short log message ("ok") is inside any longer annotation.
        if first and (level, first) not in carried:
            out.append(("(no step)", level, clean(text)))
    return out


def read_job(repo: str, job: dict) -> tuple[str, list[dict]]:
    job_id = job.get("id")
    if not isinstance(job_id, int):
        raise Unread("the job has no id")
    try:
        log = gh.run(["api", f"repos/{repo}/actions/jobs/{job_id}/logs"], what=f"gh api GET actions/jobs/{job_id}/logs")
        notes = gh.api(f"repos/{repo}/check-runs/{job_id}/annotations", paginate=True)
    except gh.GhError as e:
        raise Unread(str(e)) from None
    return log, notes or []


def workflow_label(run: dict) -> str:
    return clean(str(run.get("name") or os.path.basename(str(run.get("path") or "").split("@")[0]) or "?"))


def wanted(run: dict, workflow: str | None) -> bool:
    if workflow is None:
        return True
    path = os.path.basename(str(run.get("path") or "").split("@")[0])
    return workflow in (run.get("name"), path)


def collect(repo: str, runs: int, workflow: str | None, branch: str | None):
    """(runs read, jobs read, Findings, unread descriptions). A GhError listing runs or jobs propagates."""
    query = f"per_page={MAX_RUNS if workflow else runs}&status=completed"
    if branch:
        query += "&branch=" + urllib.parse.quote(branch, safe="")
    answer = gh.api(f"repos/{repo}/actions/runs?{query}")
    listed = answer.get("workflow_runs") if isinstance(answer, dict) else None
    if not isinstance(listed, list):
        raise gh.GhError("gh api GET actions/runs", "the answer has no workflow_runs list", transient=True)
    chosen = [r for r in listed if isinstance(r, dict) and wanted(r, workflow)][:runs]
    findings, unread, jobs_read = Findings(), [], 0
    for run in chosen:
        run_id = run.get("id")
        label = workflow_label(run)
        jobs = gh.api(f"repos/{repo}/actions/runs/{run_id}/jobs", paginate=True, items_key="jobs") or []
        for job in jobs:
            if job.get("status") != "completed" or job.get("conclusion") == "skipped":
                continue
            try:
                log, notes = read_job(repo, job)
            except Unread as e:
                unread.append(f"{label} / {clean(str(job.get('name', '?')))} (run {run_id}): {clean(str(e))}")
                continue
            jobs_read += 1
            for step, level, message in job_findings(job, log, notes):
                findings.add(label, clean(str(job.get("name", "?"))), step, level, message, int(run_id))
    return len(chosen), jobs_read, findings, unread


def render(repo: str, nruns: int, njobs: int, rows: list[dict], unread: list[str], cleared: dict | None = None) -> str:
    head = f"fabric-ci-warnings: {repo} — {nruns} run(s), {njobs} job(s) read; {len(rows)} distinct finding(s)"
    lines = [head]
    for r in rows:
        message = r["message"] if len(r["message"]) <= SHOW_WIDTH else r["message"][:SHOW_WIDTH] + "…"
        lines += ["", f"{r['count']}x  {r['workflow']} / {r['job']} / {r['step']}  [{r['level']}]",
                  f"    {message}",
                  f"    in {r['runs']} of {nruns} run(s); latest run {r['latest_run']}"]
    if cleared and cleared["entries"]:
        lines += ["", f"{cleared['count']} line(s) cleared ({cleared['distinct']} distinct) by {cleared['file']}:"]
        lines += [f"  {e['count']}x  /{clean(e['regex'])}/ — {clean(e['reason'])}" for e in cleared["entries"]]
    if unread:
        lines += ["", f"NOT READ ({len(unread)}) — these jobs are unknown, not clean:"] + [f"  {u}" for u in unread]
    return "\n".join(lines) + "\n"


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # One line, as every other refusal here: the usage block is what --help is for.
        print(f"fabric-ci-warnings: {message}", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(
        prog="fabric-ci-warnings",
        description="Print the warnings and deprecations a repository's recent CI runs print, each once, with "
                    "workflow, job, step and count. Read-only: runs, jobs, annotations and logs through gh; "
                    "fixes nothing.",
        epilog="exit: 0 read in full; 1 runs could not be listed, or the cleared-file could not be read or is invalid; 2 usage; 3 some job was not read (listed in "
               "the report).")
    p.add_argument("--repo", metavar="OWNER/NAME", help="the repository (default: this working copy's origin)")
    p.add_argument("--runs", type=int, default=DEFAULT_RUNS, metavar="N",
                   help=f"how many of the newest completed runs to read, 1..{MAX_RUNS} (default {DEFAULT_RUNS})")
    p.add_argument("--workflow", metavar="NAME", help="only runs of the workflow with this name or file name")
    p.add_argument("--branch", metavar="B", help="only runs on this branch")
    p.add_argument("--level", metavar="L[,L]", default=",".join(LEVELS),
                   help="only findings of these levels: warning, notice (as GitHub marks them) and log (a text "
                        "match on an unmarked line); default all")
    p.add_argument("--json", action="store_true", help="print the findings as one JSON object")
    return p


def main(argv: list[str], out=None, err=None) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    if not 1 <= args.runs <= MAX_RUNS:
        print(f"fabric-ci-warnings: --runs must be 1..{MAX_RUNS}, not {args.runs}", file=err)
        return 2
    levels = args.level.split(",")
    if not set(levels) <= set(LEVELS) or "" in levels:
        print(f"fabric-ci-warnings: --level takes {', '.join(LEVELS)} separated by commas, not {args.level!r}", file=err)
        return 2
    try:
        repo = args.repo or gh.this_repo()
        if not _REPO.fullmatch(repo):
            print(f"fabric-ci-warnings: --repo is not OWNER/NAME: {repo!r}", file=err)
            return 2
        nruns, njobs, findings, unread = collect(repo, args.runs, args.workflow, args.branch)
        declaration = read_declaration(repo)
    except gh.GhError as e:
        print(f"fabric-ci-warnings: {e}", file=err)
        return 1
    except Unread as e:
        print(f"fabric-ci-warnings: {clean(str(e))}", file=err)
        return 1
    rows, cleared = (declaration if "log" in levels else Declaration()).split([r for r in findings.ordered() if r["level"] in levels])
    if args.json:
        json.dump({"repo": repo, "runs_read": nruns, "jobs_read": njobs, "findings": rows, "cleared": cleared,
                   "not_read": unread},
                  out, indent=2, sort_keys=True)
        out.write("\n")
    else:
        out.write(render(repo, nruns, njobs, rows, unread, cleared))
    return 3 if unread else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
