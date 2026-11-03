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

One read: the workflow's runs with event=schedule and status=completed on
the branch, newest first, through gh.api, so the gh ledger counts it.

  success, skipped, cancelled   one line, exit 0, nothing added
  failure, timed_out            exit 0 with one line: the job added, or the
                                open job whose title carries the marker
                                [scheduled-red:<org/repo>/<file.yml>] (any
                                state but done or dropped) and nothing added
  any other conclusion          unreadable (exit 3): what the contract does not
                                define is never read as green

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
# it, said so. The dated line is the evidence a person reads a week later.
from __future__ import annotations

import argparse
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
REPOSITORY = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")
WORKFLOW = re.compile(r"[A-Za-z0-9._-]+\.ya?ml")
BRANCH = re.compile(r"[A-Za-z0-9._/-]+")


class Unreadable(Exception):
    """The runs could not be read: exit 3."""


class Unfiled(Exception):
    """The job list could not be read or written: exit 4."""


@dataclass(frozen=True)
class Run:
    id: int
    conclusion: str
    date: str  # YYYY-MM-DD, UTC


def marker(repository: str, workflow: str) -> str:
    return f"[scheduled-red:{repository}/{workflow}]"


def parse_runs(data: object) -> list[Run]:
    """The completed runs of an answer, newest first as GitHub sends them; a shape not
    known is Unreadable, never an empty list."""
    if not isinstance(data, dict) or not isinstance(data.get("workflow_runs"), list):
        raise Unreadable("the answer has no workflow_runs list")
    runs = []
    for raw in data["workflow_runs"]:
        if not isinstance(raw, dict):
            raise Unreadable("a run is not an object")
        run_id, status, conclusion, created = (raw.get(k) for k in ("id", "status", "conclusion", "created_at"))
        if not isinstance(run_id, int) or isinstance(run_id, bool) or not isinstance(status, str):
            raise Unreadable("a run has no integer id and a status")
        if status != "completed":
            continue
        if not isinstance(conclusion, str) or conclusion not in GREEN + RED:
            raise Unreadable(f"run {run_id} concluded {conclusion!r}, which this does not define as green or red")
        try:
            when = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            raise Unreadable(f"run {run_id} has no readable created_at") from None
        if when.tzinfo is None:
            raise Unreadable(f"run {run_id} has a created_at with no zone")
        runs.append(Run(run_id, conclusion, when.astimezone(datetime.timezone.utc).date().isoformat()))
    if not runs:
        raise Unreadable("no completed scheduled run on the branch to judge")
    return runs


def red_since(runs: list[Run]) -> str:
    """When the newest red streak began, from the page of runs, newest first."""
    streak = []
    for r in runs:
        if r.conclusion == "success":
            return streak[-1].date if streak else r.date
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


def title_of(repository: str, workflow: str, run: Run, since: str) -> str:
    return (f"{workflow} of {repository}: scheduled run {run.id} of {run.date} is red, red since {since}; "
            f"read the failing files, contract each fix to its holder {marker(repository, workflow)}")


def load_jobs():
    """fabric-jobs' own module, loaded by path as its tests do."""
    spec = importlib.util.spec_from_file_location("fabric_jobs_cli", os.path.join(os.path.dirname(HERE), "jobs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def open_marked(doc: dict, mark: str, open_states) -> dict | None:
    return next((j for j in doc["jobs"] if j.get("state") in open_states and mark in str(j.get("title", ""))), None)


def file_job(repository: str, workflow: str, project: str, run: Run, since: str, dry_run: bool) -> str:
    jobs = load_jobs()
    mark, title = marker(repository, workflow), title_of(repository, workflow, run, since)
    try:
        if dry_run:
            doc = jobs.identity.read_jobs()
            listed = open_marked(doc, mark, jobs.OPEN)
            added = None
        else:
            def add_unless_listed(doc: dict):
                listed = open_marked(doc, mark, jobs.OPEN)
                if listed:
                    return listed, False
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
        if newest.conclusion in GREEN:
            print(f"ok: {args.workflow} run {newest.id} of {newest.date} concluded {newest.conclusion}; nothing added")
            return 0
        print(file_job(args.repository, args.workflow, project, newest, red_since(runs), args.dry_run))
        return 0
    except Unreadable as e:
        print(f"{PROG}: cannot read the scheduled runs of {args.workflow} in {args.repository}: {e}", file=sys.stderr)
        return 3
    except Unfiled as e:
        print(f"{PROG}: {args.workflow} is red but the job list could not be used: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
