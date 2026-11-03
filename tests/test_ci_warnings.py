#!/usr/bin/env python3
"""fabric-ci-warnings (bin/fabric-ci-warnings, tools/fabric/ci_warnings.py) against recorded gh answers.

The fake `gh` answers `gh api <path>` from a table of recorded shapes (a runs
list, a jobs list with steps, a plain-text job log, check-run annotations) and
logs every request. What is promised: each warning once with its workflow, job,
step and count over the runs; an annotation the log already carries is not
counted twice, one it does not carry is reported without a step; the runner's
echo of a script and a structured dump are not warnings; two steps sharing a
second are both named; an unreadable job is said, never read as clean (exit 3);
a failed listing is one line and exit 1; usage is exit 2; nothing but GET is
ever sent. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "bin", "fabric-ci-warnings")
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import ci_warnings  # noqa: E402

GH = r'''#!{python}
import json, os, sys
a = sys.argv[1:]
path = a[1].split("?")[0]
method = a[a.index("--method") + 1] if "--method" in a else "GET"
with open(os.environ["GH_LOG"], "a") as fh:
    fh.write(json.dumps({"method": method, "path": path, "query": a[1].partition("?")[2]}) + "\n")
table = json.load(open(os.environ["GH_TABLE"]))
if path in table.get("fail", {}):
    print(table["fail"][path], file=sys.stderr)
    sys.exit(1)
if path in table.get("text", {}):
    sys.stdout.write(table["text"][path])
    sys.exit(0)
answer = table["json"][path]
print(json.dumps([answer] if "--slurp" in a else answer))
'''

REPO = "o/r"


def step(name, start, end):
    return {"name": name, "started_at": f"2026-11-03T{start}.000Z", "completed_at": f"2026-11-03T{end}.000Z"}


# A recorded log: the runner's header group, a step's echoed script (which says
# "deprecated" in its own env), a marked warning, an ANSI-coloured notice, an
# unmarked npm deprecation, a structured dump, and a warning on a shared second.
LOG = "\n".join([
    "﻿2026-11-03T01:00:00.1000000Z ##[group]Runner Image",
    "2026-11-03T01:00:00.1000001Z Image: ubuntu-24.04 (deprecated tag)",
    "2026-11-03T01:00:00.1000002Z ##[endgroup]",
    "2026-11-03T01:00:01.1000000Z ##[group]Run echo deprecated",
    "2026-11-03T01:00:01.1000001Z echo deprecated",
    "2026-11-03T01:00:01.1000002Z ##[endgroup]",
    "2026-11-03T01:00:02.2000000Z ##[warning]Node.js 20 actions are deprecated. Use node24.",
    "2026-11-03T01:00:03.3000000Z ##[notice]\x1b[33mcache   miss\x1b[0m",
    "2026-11-03T01:00:04.4000000Z npm warn deprecated glob@7.2.3: Glob versions prior to v9 are no longer supported",
    '2026-11-03T01:00:04.5000000Z   "title" : "DEPRECATED - a dumped option",',
    "2026-11-03T01:00:05.6000000Z ##[warning]shared second",
    "2026-11-03T01:00:09.0000000Z all good",
]) + "\n"

JOB = {"id": 11, "name": "static", "status": "completed", "conclusion": "success",
       "steps": [step("Set up job", "01:00:00", "01:00:01"), step("Install", "01:00:02", "01:00:04"),
                 step("Lint", "01:00:05", "01:00:05"), step("Test", "01:00:05", "01:00:09")]}
NOTES = [
    {"annotation_level": "warning", "message": "Node.js 20 actions are deprecated. Use node24."},   # the log carries it
    {"annotation_level": "notice", "message": "The ubuntu-latest label will migrate.\nMore at a URL."},
    {"annotation_level": "failure", "message": "boom"},
]


def table(runs, jobs_by_run, extra_json=None, text=None, fail=None):
    js = {f"repos/{REPO}/actions/runs": {"workflow_runs": runs}}
    for rid, jobs in jobs_by_run.items():
        js[f"repos/{REPO}/actions/runs/{rid}/jobs"] = {"jobs": jobs}
    js.update(extra_json or {})
    return {"json": js, "text": text or {}, "fail": fail or {}}


def main() -> int:
    fails = 0

    def check(label, good, detail=""):
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    print("ci-warnings: the log")
    found = ci_warnings.parse_log(LOG)
    got = [(lvl, msg) for _, lvl, msg in found]
    check("marked warning and notice, an unmarked deprecation; ANSI stripped",
          got == [("warning", "Node.js 20 actions are deprecated. Use node24."), ("notice", "cache miss"),
                  ("log", "npm warn deprecated glob@7.2.3: Glob versions prior to v9 are no longer supported"),
                  ("warning", "shared second")], str(got))
    check("the runner's header group and a step's echoed script are not read; a dumped option is not a warning",
          not any("Image" in m or "echo" in m or "dumped" in m for _, _, m in found), str(got))
    steps = JOB["steps"]
    when = {m: w for w, _, m in found}
    check("a line is attributed to its step by second",
          ci_warnings.step_names(steps, when["Node.js 20 actions are deprecated. Use node24."]) == "Install")
    check("a second two steps share names both, never one of them",
          ci_warnings.step_names(steps, when["shared second"]) == "Lint | Test")
    check("a line outside every step has none, and so has an unstamped one",
          ci_warnings.step_names(steps, None) == "(no step)"
          and ci_warnings.step_names(steps[:1], when["shared second"]) == "(no step)")

    runs = [{"id": 2, "name": "ci", "path": ".github/workflows/ci.yml@refs/heads/main"},
            {"id": 1, "name": "ci", "path": ".github/workflows/ci.yml@refs/heads/main"},
            {"id": 3, "name": "pr-counts", "path": ".github/workflows/pr-counts.yml@refs/heads/x"}]
    skipped = {"id": 99, "name": "never", "status": "completed", "conclusion": "skipped", "steps": []}
    running = {"id": 98, "name": "later", "status": "in_progress", "conclusion": None, "steps": []}
    pr_job = {"id": 31, "name": "counts", "status": "completed", "conclusion": "success", "steps": []}
    base_tab = table(
        runs, {2: [JOB, skipped, running], 1: [JOB], 3: [pr_job]},
        extra_json={f"repos/{REPO}/check-runs/11/annotations": NOTES, f"repos/{REPO}/check-runs/31/annotations": []},
        text={f"repos/{REPO}/actions/jobs/11/logs": LOG, f"repos/{REPO}/actions/jobs/31/logs": "2026-11-03T02:00:00.0Z ok\n"})

    with tempfile.TemporaryDirectory() as t:
        bin_, log, tab = os.path.join(t, "bin"), os.path.join(t, "log"), os.path.join(t, "table.json")
        os.makedirs(bin_)
        with open(os.path.join(bin_, "gh"), "w", encoding="utf-8") as fh:
            fh.write(GH.replace("{python}", sys.executable))
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        base = {"PATH": bin_ + os.pathsep + "/usr/bin:/bin", "HOME": t, "XDG_STATE_HOME": os.path.join(t, "state"),
                "GH_LOG": log, "GH_TABLE": tab, "LC_ALL": "C.UTF-8"}

        def run(tab_data, *args):
            with open(tab, "w", encoding="utf-8") as fh:
                json.dump(tab_data, fh)
            if os.path.exists(log):
                os.remove(log)
            r = subprocess.run([TOOL, *args], env=base, capture_output=True, text=True, timeout=120)
            calls = []
            if os.path.exists(log):
                with open(log, encoding="utf-8") as fh:
                    calls = [json.loads(l) for l in fh]
            return r.returncode, r.stdout, r.stderr, calls

        print("ci-warnings: the command")
        rc, out, err, calls = run(base_tab, "--repo", REPO, "--json")
        doc = json.loads(out) if rc == 0 else {}
        rows = {(r["workflow"], r["job"], r["step"], r["level"], r["message"][:20]): r for r in doc.get("findings", [])}
        check("exit 0, three runs and their three read jobs counted (skipped and unfinished jobs not read)",
              rc == 0 and doc.get("runs_read") == 3 and doc.get("jobs_read") == 3 and not err, f"{rc} {err} {out[:300]}")
        dep = rows.get(("ci", "static", "Install", "warning", "Node.js 20 actions a"))
        check("a warning printed in two runs is one finding: count 2, in 2 runs, latest run 2",
              bool(dep) and (dep["count"], dep["runs"], dep["latest_run"]) == (2, 2, 2), json.dumps(doc)[:500])
        check("the annotation the log carries is not a second finding",
              not any(r["step"] == "(no step)" and "Node.js" in r["message"] for r in rows.values()))
        ann = rows.get(("ci", "static", "(no step)", "notice", "The ubuntu-latest la"))
        check("an annotation no log line carries is reported without a step, whole; a failure annotation is not",
              bool(ann) and ann["count"] == 2 and "More at a URL." in ann["message"]
              and not any("boom" in r["message"] for r in rows.values()))
        check("the shared second names both steps",
              ("ci", "static", "Lint | Test", "warning", "shared second") in rows)
        check("a run whose jobs have none contributes none; no unread jobs",
              not any(r["workflow"] == "pr-counts" for r in rows.values()) and doc.get("not_read") == [])
        check("read-only: only GETs, and the run listing asked for completed runs",
              {c["method"] for c in calls} == {"GET"} and "status=completed" in calls[0]["query"], str(calls[:2]))

        rc, out, err, _ = run(base_tab, "--repo", REPO)
        check("text report: head line, the finding with its count, workflow / job / step and level",
              rc == 0 and out.startswith(f"fabric-ci-warnings: {REPO} — 3 run(s), 3 job(s) read; 5 distinct finding(s)\n")
              and "2x  ci / static / Install  [warning]\n    Node.js 20 actions are deprecated. Use node24.\n" in out
              and "in 2 of 3 run(s); latest run 2" in out, out)

        rc, out, err, calls = run(base_tab, "--repo", REPO, "--workflow", "pr-counts.yml", "--runs", "1", "--branch", "a b")
        check("--workflow (by file name) keeps one workflow's runs; --branch is sent escaped",
              rc == 0 and "1 run(s), 1 job(s)" in out and "branch=a%20b" in calls[0]["query"], out + err)

        bad = json.loads(json.dumps(base_tab))
        bad["fail"][f"repos/{REPO}/actions/jobs/31/logs"] = "gh: Not Found (HTTP 404)"
        rc, out, err, _ = run(bad, "--repo", REPO)
        check("a job whose log cannot be read is listed as not read, the rest still reported, exit 3",
              rc == 3 and "NOT READ (1)" in out and "counts (run 3)" in out and "HTTP 404" in out
              and "2x  ci / static / Install" in out, f"{rc}\n{out}{err}")

        bad = json.loads(json.dumps(base_tab))
        bad["fail"][f"repos/{REPO}/check-runs/31/annotations"] = "gh: Server Error (HTTP 502)"
        rc, out, _, _ = run(bad, "--repo", REPO)
        check("unreadable annotations are not read as 'none': the job is not read either",
              rc == 3 and "NOT READ (1)" in out and "counts (run 3)" in out, out)

        bad = json.loads(json.dumps(base_tab))
        bad["fail"][f"repos/{REPO}/actions/runs"] = "gh: Not Found (HTTP 404)"
        rc, out, err, _ = run(bad, "--repo", REPO)
        check("runs that cannot be listed: one line on stderr, nothing on stdout, exit 1, no traceback",
              rc == 1 and out == "" and err.startswith("fabric-ci-warnings: ") and "Traceback" not in err
              and err.count("\n") == 1, err)

        shapeless = json.loads(json.dumps(base_tab))
        shapeless["json"][f"repos/{REPO}/actions/runs"] = {"message": "odd"}
        rc, out, err, _ = run(shapeless, "--repo", REPO)
        check("an answer without a workflow_runs list is a failure, never 'no warnings'",
              rc == 1 and out == "" and "workflow_runs" in err, f"{rc} {out}{err}")

        quiet = table([], {})
        rc, out, _, _ = run(quiet, "--repo", REPO)
        check("no runs: exit 0 and says so", rc == 0 and "0 run(s), 0 job(s) read; 0 distinct" in out, out)

        for args in (["--runs", "0"], ["--runs", "101"], ["--runs", "x"], ["--repo", "nope"], ["--fix"]):
            rc, out, err, calls = run(base_tab, *args)
            check(f"usage {args}: exit 2, nothing sent to GitHub", rc == 2 and not calls and out == "", f"{rc} {err}")
        rc, out, err, calls = run(base_tab, "--help")
        check("--help: exit 0, names the options and the exit codes",
              rc == 0 and all(w in out for w in ("--repo", "--runs", "--workflow", "--branch", "--json", "exit:")) and not calls)

    print(f"\ntest_ci_warnings: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
