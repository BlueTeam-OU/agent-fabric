#!/usr/bin/env python3
"""tools/fabric/github/scheduled_red.py

Turns a red scheduled run into a job on the login that runs this.

A scheduled run's conclusion reaches only the Actions tab. The stripped
nightly was red from 2026-10-19 for twelve days and no job or message
noticed. This reads the newest completed `schedule` run of one workflow
and, when it failed, adds one job to this login's list through
fabric-jobs' own code (jobs.new_job under the list's lock, never a write
of jobs.json).

Usage:
  tools/fabric/github/scheduled_red.py --repository <org/repo> --workflow <file.yml>
      [--branch main] [--project <registry id>] [--dry-run]

  --project   the job's project; default the registry id the repository resolves to.
              A repository no project registers needs --project: a job is never
              filed under whatever project the working directory happens to be.
  --dry-run   says what it would add and adds nothing.

Reads, all through gh.api so the gh ledger counts them: the workflow's runs with event=schedule and
status=completed on the branch, newest first; for a red or cancelled newest run, its jobs; and for each
cancelled job, its check-run annotations.

  success, skipped              one line, exit 0, nothing added
  cancelled                     read the run's jobs: a job that hit timeout-minutes is cancelled, not
                                failed, so a cancelled job carrying GitHub's "exceeded the maximum
                                execution time" annotation makes the run red; otherwise green as before
  failure, timed_out            exit 0 with one line: the job added, or the
                                open job whose title carries every marker of the failed jobs (or the bare
                                workflow-wide marker of an earlier version)
                                (any state but done or dropped) and nothing added
  any other conclusion          of the NEWEST run: unreadable (exit 3), never green; an older
                                run this cannot read only ends the red-since count

A red run's failed jobs come from the run's jobs API; each gets a marker
[scheduled-red:<org/repo>/<file.yml>#<job>], and the filed job's title names them and ends in them.
An open job for one failed job never hides another's: only the failed jobs with no open marked job
are filed. A red run whose jobs name none failed is filed under the marker
[scheduled-red:<org/repo>/<file.yml>#*], saying so. An open job carrying the bare
workflow-wide marker of an earlier version covers every job.

Exit codes:
  0  read; the line says whether a job was added
  2  bad command line, or a repository no project registers and no --project
  3  the runs could not be read (no token, network, API error, an answer of a
     shape this does not know, no completed run): the reason on stderr, nothing added
  4  the runs were read and are red, but the job list could not be read or written
"""
# Red-since is the first failed run after the newest success in the page
# read (30 runs), not the first red of the streak by any other count: when
# the page holds no success the date is "or earlier" than the oldest red in
# it, said so; so it is when an older run cannot be read (it ends the count). The dated line is the evidence a person reads a week later.
from __future__ import annotations

import argparse
import dataclasses
import datetime
import importlib.util
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402

PROG = "scheduled_red"
PAGE = 30
GREEN = ("success", "skipped", "cancelled")
RED = ("failure", "timed_out")
UNKNOWN = "unknown"  # an older run parse_runs could not read; never a verdict
REPOSITORY = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")
WORKFLOW = re.compile(r"[A-Za-z0-9._-]+\.ya?ml")
BRANCH = re.compile(r"[A-Za-z0-9._/-]+")


class Unreadable(Exception):
    """The runs could not be read: exit 3."""


class Unfiled(Exception):
    """The job list could not be read or written: exit 4."""


TIMEOUT_NOTE = "exceeded the maximum execution time"
JOB_NAME = re.compile(r"[^A-Za-z0-9._ ()-]")


@dataclass(frozen=True)
class Run:
    id: int | None  # None: an older run whose id was not an integer; never invented
    conclusion: str
    date: str  # YYYY-MM-DD, UTC


def marker(repository: str, workflow: str, job: str | None = None) -> str:
    # `#` after the file name: the workflow-wide marker is never a prefix of a job's, so one cannot match the other.
    # A name is cut to the charset a marker can hold, so a `]` in a job name never ends it early.
    return f"[scheduled-red:{repository}/{workflow}" + (f"#{JOB_NAME.sub('_', job)}" if job else "") + "]"


def parse_run(raw: object) -> Run | None:
    """One run of the answer: None when it is not completed; Unreadable when it is not a run this
    understands (an id, a status, a defined conclusion and a dated, zoned created_at)."""
    if not isinstance(raw, dict):
        raise Unreadable("a run is not an object")
    run_id, status, conclusion, created = (raw.get(k) for k in ("id", "status", "conclusion", "created_at"))
    if not isinstance(run_id, int) or isinstance(run_id, bool) or not isinstance(status, str):
        raise Unreadable("a run has no integer id and a status")
    if status != "completed":
        return None
    if not isinstance(conclusion, str) or conclusion not in GREEN + RED:
        raise Unreadable(f"run {run_id} concluded {conclusion!r}, which this does not define as green or red")
    try:
        when = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        raise Unreadable(f"run {run_id} has no readable created_at") from None
    if when.tzinfo is None:
        raise Unreadable(f"run {run_id} has a created_at with no zone")
    return Run(run_id, conclusion, when.astimezone(datetime.timezone.utc).date().isoformat())


def parse_runs(data: object) -> list[Run]:
    """The completed runs of an answer, newest first as GitHub sends them; a shape not known is
    Unreadable, never an empty list. Only the newest completed run is the verdict, so only it is held
    to the contract: an older run this cannot read (startup_failure is what a broken workflow file
    records) ends the red-since count as an UNKNOWN run, and never hides a red newest one."""
    if not isinstance(data, dict) or not isinstance(data.get("workflow_runs"), list):
        raise Unreadable("the answer has no workflow_runs list")
    runs: list[Run] = []
    for raw in data["workflow_runs"]:
        try:
            run = parse_run(raw)
        except Unreadable:
            if not runs:
                raise
            rid = raw.get("id") if isinstance(raw, dict) else None
            run = Run(rid if isinstance(rid, int) and not isinstance(rid, bool) else None, UNKNOWN, "")
        if run:
            runs.append(run)
    if not runs:
        raise Unreadable("no completed scheduled run on the branch to judge")
    return runs


def red_since(runs: list[Run]) -> str:
    """When the newest red streak began, from the page of runs, newest first."""
    streak = []
    for r in runs:
        if r.conclusion == "success":
            return streak[-1].date if streak else r.date
        if r.conclusion == UNKNOWN:
            which = f"run {r.id}" if r.id is not None else "a run"
            return f"{streak[-1].date} or earlier ({which} before it is one this does not read)"
        if r.conclusion in RED:
            streak.append(r)
    return f"{streak[-1].date} or earlier (no success in the last {len(runs)} completed runs)"


def read_runs(repository: str, workflow: str, branch: str) -> list[Run]:
    query = urllib.parse.urlencode({"event": "schedule", "status": "completed", "branch": branch, "per_page": PAGE})
    try:
        data = gh.api(f"repos/{repository}/actions/workflows/{workflow}/runs?{query}")
    except gh.GhError as e:
        raise Unreadable(str(e)) from None
    return parse_runs(data)


def unnamed_marker(repository: str, workflow: str) -> str:
    # `*` is outside the charset a job name is cut to, so no job's marker equals it; and it is not the bare
    # workflow-wide marker of an earlier version, which covers every job and must not be confused with this one.
    return f"[scheduled-red:{repository}/{workflow}#*]"


def read_failed_jobs(repository: str, run: Run) -> tuple[list[str], list[str]]:
    """(failed, timed_out) job names of one run, from its jobs API. A job whose conclusion is failure or
    timed_out failed; a `cancelled` one is read for GitHub's timeout annotation, because a job that hit
    timeout-minutes concludes cancelled and a concurrency or a person's cancel does not carry it.
    Anything unreadable is Unreadable, never an empty list that reads green."""
    try:
        data = gh.api(f"repos/{repository}/actions/runs/{run.id}/jobs?per_page=100")
    except gh.GhError as e:
        raise Unreadable(str(e)) from None
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list) or not isinstance(data.get("total_count"), int):
        raise Unreadable(f"the jobs of run {run.id} are not an answer this knows")
    if data["total_count"] != len(data["jobs"]):
        raise Unreadable(f"run {run.id} has {data['total_count']} jobs and one page holds {len(data['jobs'])}")
    failed: list[str] = []
    timed_out: list[str] = []
    for job in data["jobs"]:
        if not isinstance(job, dict) or not isinstance(job.get("name"), str) or not job["name"]:
            raise Unreadable(f"a job of run {run.id} has no name")
        conclusion = job.get("conclusion")
        if conclusion in RED:
            failed.append(job["name"])
        elif conclusion == "cancelled":
            job_id = job.get("id")
            if not isinstance(job_id, int) or isinstance(job_id, bool):
                raise Unreadable(f"cancelled job {job['name']!r} of run {run.id} has no integer id")
            try:
                notes = gh.api(f"repos/{repository}/check-runs/{job_id}/annotations?per_page=100")
            except gh.GhError as e:
                raise Unreadable(str(e)) from None
            if not isinstance(notes, list):
                raise Unreadable(f"the annotations of job {job_id} are not a list")
            if any(isinstance(n, dict) and TIMEOUT_NOTE in str(n.get("message", "")) for n in notes):
                timed_out.append(job["name"])
    return failed, timed_out


def title_of(repository: str, workflow: str, run: Run, since: str, jobs: list[str], timed_out: frozenset = frozenset()) -> str:
    named = (", ".join(f"{j} (timed out)" if j in timed_out else j for j in jobs) if jobs
             else "no failed job named by the run's jobs")
    marks = " ".join(marker(repository, workflow, j) for j in jobs) if jobs else unnamed_marker(repository, workflow)
    return (f"{workflow} of {repository}: scheduled run {run.id} of {run.date} is red in {named}, red since {since}; "
            f"read the failing files, contract each fix to its holder {marks}")


def load_jobs():
    """fabric-jobs' own module, loaded by path as its tests do."""
    spec = importlib.util.spec_from_file_location("fabric_jobs_cli", os.path.join(os.path.dirname(HERE), "jobs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def open_marked(doc: dict, mark: str, open_states) -> dict | None:
    return next((j for j in doc["jobs"] if j.get("state") in open_states and mark in str(j.get("title", ""))), None)


def file_job(repository: str, workflow: str, project: str, run: Run, since: str, dry_run: bool,
             failed: list[str], timed_out: frozenset = frozenset()) -> str:
    jobs = load_jobs()

    def unlisted(doc: dict) -> tuple[list[str], dict | None]:
        """The failed jobs with no open marked job, and the open job that covers the first failed one when none is
        left. A red with no named failed job is one workflow-wide unit."""
        legacy = open_marked(doc, marker(repository, workflow), jobs.OPEN)
        if legacy:  # filed before markers named a job: it covers whichever job failed, as it always did
            return [], legacy
        if not failed:
            listed = open_marked(doc, unnamed_marker(repository, workflow), jobs.OPEN)
            return [], listed
        missing = [j for j in failed if not open_marked(doc, marker(repository, workflow, j), jobs.OPEN)]
        return missing, (None if missing else open_marked(doc, marker(repository, workflow, failed[0]), jobs.OPEN))

    try:
        if dry_run:
            missing, listed = unlisted(jobs.identity.read_jobs())
            added = None
            title = title_of(repository, workflow, run, since, missing, timed_out)
        else:
            def add_unless_listed(doc: dict):
                missing, listed = unlisted(doc)
                if listed:
                    return listed, False
                title = title_of(repository, workflow, run, since, missing, timed_out)
                return jobs.new_job(doc, title, topic="ci", project=project, priority="high"), True
            job, added = jobs.mutate(add_unless_listed)
            listed = None if added else job
    except (jobs.Refused, SystemExit, OSError, ValueError) as e:
        raise Unfiled(str(e) if not isinstance(e, SystemExit) else str(e.code)) from None
    if listed:
        return f"red: {workflow} run {run.id} of {run.date}; not added, {listed['id']} is open: {listed['title']}"
    if dry_run:
        return f"red: would add a high-priority ci job in {project}: {title}"
    return f"red: added {jobs.line(job)}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=PROG, description=__doc__.split("\n\n")[0])
    ap.add_argument("--repository", required=True)
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--branch", default="main")
    ap.add_argument("--project")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    for value, rx, what in ((args.repository, REPOSITORY, "--repository <org/repo>"), (args.workflow, WORKFLOW, "--workflow <file.yml>"),
                            (args.branch, BRANCH, "--branch")):
        if not rx.fullmatch(value) or ".." in value:
            ap.error(f"{what}: {value!r} is not one")
    project = args.project
    if not project:
        from github import common
        try:
            project = common.resolve_repository(args.repository)[1]
        except common.NoRepository as e:
            print(f"{PROG}: {e}", file=sys.stderr)
            return 2
        if not project:
            print(f"{PROG}: no project registers {args.repository}; name one with --project", file=sys.stderr)
            return 2
    try:
        runs = read_runs(args.repository, args.workflow, args.branch)
        newest = runs[0]
        failed: list[str] = []
        timed_out: list[str] = []
        if newest.conclusion in RED or newest.conclusion == "cancelled":
            failed, timed_out = read_failed_jobs(args.repository, newest)
        if newest.conclusion == "cancelled":
            if not timed_out:  # a plain cancel is not a red: only a timed-out job makes it one
                print(f"ok: {args.workflow} run {newest.id} of {newest.date} concluded cancelled; nothing added")
                return 0
            runs[0] = dataclasses.replace(newest, conclusion="timed_out")  # red_since counts the streak from it
        elif newest.conclusion in GREEN:
            print(f"ok: {args.workflow} run {newest.id} of {newest.date} concluded {newest.conclusion}; nothing added")
            return 0
        failed = failed + [j for j in timed_out if j not in failed]
        print(file_job(args.repository, args.workflow, project, newest, red_since(runs), args.dry_run, failed, frozenset(timed_out)))
        return 0
    except Unreadable as e:
        print(f"{PROG}: cannot read the scheduled runs of {args.workflow} in {args.repository}: {e}", file=sys.stderr)
        return 3
    except Unfiled as e:
        print(f"{PROG}: {args.workflow} is red but the job list could not be used: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
