#!/usr/bin/env python3
"""tools/fabric/reflect_jobs.py — the weekly reflection pass, put on every
agent's job list (agent-fabric ADR-058 rule 1). Behind bin/fabric-reflect-jobs;
the coordinator runs it before a drain.

    fabric-reflect-jobs [--dry-run] [--json] [--week YYYY-Www] [login..]

Targets: every placed login of kind agent (control/ctl.placements), or the
logins given; a login that is unplaced or human is refused, nothing run (exit
2). For each, `fabric-ctl <login> jobs --json` is asked; an open job whose
title starts with "Reflection pass" means the login is skipped and that job
named: a pass not yet worked is never stacked, since the next pass reads the
whole span anyway. Otherwise `fabric-ctl <login> jobs-add` adds the pass. One
login per request: control/jobs.py refuses `all` and this command loops.

Output, one line per login: `added <job>`, `would add` (--dry-run, which asks
the lists and adds nothing), `skipped (open <job>)`, or `failed: <reason>`;
--json prints a list of {login, result, job|reason}. A login that failed does
not stop the others. Exit 0 all added or skipped, 1 any failed, 2 usage.

fabric-ctl is run by argv through an injectable runner, so a test needs no
relay and no agentd. What fabric-ctl says about an account that did not answer
is a failure here, never an empty list: unknown stays unknown.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from typing import Callable

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from control import ctl  # noqa: E402

PASS_PREFIX = "Reflection pass"
TITLE_MAX = 300          # control/jobs.py TITLE_MAX: a longer title would be refused per login
CTL_TIMEOUT_S = 120      # the whole fabric-ctl run; its own reply wait is shorter
FABRIC_CTL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "bin", "fabric-ctl")
WEEK = re.compile(r"([0-9]{4})-W([0-9]{2})")

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


class Usage(Exception):
    pass


def real_runner(argv: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=CTL_TIMEOUT_S, check=False)


def iso_week(now: datetime.datetime) -> str:
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


def check_week(week: str) -> str:
    m = WEEK.fullmatch(week)
    if m:
        try:
            datetime.date.fromisocalendar(int(m[1]), int(m[2]), 1)
            return week
        except ValueError:
            pass
    raise Usage(f"--week {week!r} is not an ISO week like 2026-W42")


def pass_title(week: str) -> str:
    title = (f"{PASS_PREFIX} {week} (ADR-058): run fabric-reflect, judge each lesson against memory/RUBRIC.md, "
             "write what passes as your own memory with a roles_class and origin: reflection plus the "
             "MESSAGE-IDs, then fabric-reflect done --through <row>")
    assert len(title) <= TITLE_MAX and "\n" not in title
    return title


def targets(given: list[str], placed: list[dict]) -> list[str]:
    if not given:
        return [p["login"] for p in placed if p["kind"] == "agent"]
    kinds = {p["login"]: p["kind"] for p in placed}
    bad = [f"{g} ({'human' if kinds[g] == 'human' else 'kind ' + kinds[g]})" if g in kinds else f"{g} (not placed)"
           for g in given if kinds.get(g) != "agent"]
    if bad:
        raise Usage("not a placed login of kind agent: " + ", ".join(bad))
    return list(dict.fromkeys(given))


def _row_of(cp: "subprocess.CompletedProcess[str]", login: str) -> dict:
    """The one row fabric-ctl --json printed for this login; ValueError when there is none to trust."""
    rows = []
    for line in cp.stdout.splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                raise ValueError(f"fabric-ctl printed a line that is not JSON (exit {cp.returncode})") from None
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError(f"fabric-ctl printed {len(rows)} rows for one login (exit {cp.returncode}): "
                         + (cp.stderr.strip().splitlines() or ["no reason given"])[-1])
    row = rows[0]
    if row.get("status") != "ok":
        raise ValueError(f"{login} did not answer: {row.get('status')}")
    return row


def open_pass(login: str, run: Runner) -> str | None:
    """The id of this login's open reflection job, or None; ValueError when the list is not known."""
    row = _row_of(run([FABRIC_CTL, login, "jobs", "--json"]), login)
    jobs = row.get("jobs")
    if not isinstance(jobs, dict) or jobs.get("status") != "ok" or not isinstance(jobs.get("jobs"), list):
        raise ValueError("the job list was not answered: " + str(jobs.get("error") if isinstance(jobs, dict) else jobs)[:200])
    for job in jobs["jobs"]:
        title = job.get("title") if isinstance(job, dict) else None
        if isinstance(title, str) and title.startswith(PASS_PREFIX):
            return str(job.get("id"))
    return None


def add_pass(login: str, week: str, run: Runner) -> str:
    argv = [FABRIC_CTL, login, "jobs-add", "--topic", "reflection", "--project", "agent-fabric",
            "--priority", "normal", "--json", "--", pass_title(week)]
    res = _row_of(run(argv), login).get("jobsAdd")
    if not isinstance(res, dict):
        raise ValueError("no answer to jobs-add")
    if res.get("status") != "added":
        raise ValueError(str(res.get("reason") or res.get("status")))
    return str(res.get("job"))


def reflect_one(login: str, week: str, run: Runner, dry_run: bool) -> dict:
    try:
        existing = open_pass(login, run)
        if existing is not None:
            return {"login": login, "result": "skipped", "job": existing}
        if dry_run:
            return {"login": login, "result": "would-add"}
        return {"login": login, "result": "added", "job": add_pass(login, week, run)}
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        reason = "no answer within %d s" % CTL_TIMEOUT_S if isinstance(e, subprocess.TimeoutExpired) else str(e)
        return {"login": login, "result": "failed", "reason": " ".join(reason.split())}


_CONTROL = re.compile("[\u0000-\u001f\u007f-\u009f]")


def line_of(r: dict) -> str:
    what = {"added": f"added {r.get('job')}", "would-add": "would add",
            "skipped": f"skipped (open {r.get('job')})", "failed": f"failed: {r.get('reason')}"}[r["result"]]
    # What an account sent (a job id, a refusal) reaches the operator's terminal: control characters shown escaped.
    return _CONTROL.sub(lambda m: f"\\x{ord(m.group(0)):02x}", f"{r['login']}: {what}")


def parse(argv: list[str]) -> dict:
    out = {"dry_run": False, "json": False, "week": None, "logins": []}
    it = iter(argv)
    for a in it:
        if a == "--dry-run":
            out["dry_run"] = True
        elif a == "--json":
            out["json"] = True
        elif a == "--week":
            out["week"] = next(it, None)
            if out["week"] is None:
                raise Usage("--week needs a value")
        elif a.startswith("--week="):
            out["week"] = a[len("--week="):]
        elif a.startswith("-"):
            raise Usage(f"unknown option {a}")
        else:
            out["logins"].append(a)
    return out


def main(argv: list[str] | None = None, *, run: Runner = real_runner, placed: Callable[[], list[dict]] = ctl.placements,
         now: Callable[[], datetime.datetime] = lambda: datetime.datetime.now(datetime.timezone.utc),
         out: Callable[[str], None] = print) -> int:
    try:
        args = parse(sys.argv[1:] if argv is None else argv)
        week = check_week(args["week"]) if args["week"] is not None else iso_week(now())
        logins = targets(args["logins"], placed())
    except Usage as e:
        print(f"fabric-reflect-jobs: {e}\nusage: fabric-reflect-jobs [--dry-run] [--json] [--week YYYY-Www] [login..]", file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print(f"fabric-reflect-jobs: the placements cannot be read: {e}", file=sys.stderr)
        return 1
    if not logins:
        print("fabric-reflect-jobs: no placed login of kind agent; nothing to do", file=sys.stderr)
    results = [reflect_one(login, week, run, args["dry_run"]) for login in logins]
    if args["json"]:
        out(json.dumps(results))
    else:
        for r in results:
            out(line_of(r))
    return 1 if any(r["result"] == "failed" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
