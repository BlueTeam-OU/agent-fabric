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

import base64
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
    "2026-11-03T01:00:06.0000000Z Setting up node-util-deprecate (1.0.2-3) ...",
    "2026-11-03T01:00:07.0000000Z tests/t.py:3: DeprecationWarning: ssl.TLSVersion.TLSv1 is deprecated",
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
    # No declaration unless a case brings one: the repository answers 404 for the file.
    failing = {f"repos/{REPO}/contents/{ci_warnings.CLEARED_FILE}": "gh: Not Found (HTTP 404)"}
    failing.update(fail or {})
    return {"json": js, "text": text or {}, "fail": failing}


def declare(tab_data, doc):
    """A copy of the table whose repository declares `doc` (text or object) in its cleared file."""
    out = json.loads(json.dumps(tab_data))
    path = f"repos/{REPO}/contents/{ci_warnings.CLEARED_FILE}"
    del out["fail"][path]
    text = doc if isinstance(doc, str) else json.dumps(doc)
    out["json"][path] = {"type": "file", "encoding": "base64", "content": base64.encodebytes(text.encode()).decode()}
    return out


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
                  ("warning", "shared second"),
                  ("log", "tests/t.py:3: DeprecationWarning: ssl.TLSVersion.TLSv1 is deprecated")], str(got))
    check("the runner's header group and a step's echoed script are not read; a dumped option and a package named *-deprecate are not warnings",
          not any("Image" in m or "echo" in m or "dumped" in m or "util-deprecate" in m for _, _, m in found), str(got))
    steps = JOB["steps"]
    when = {m: w for w, _, m in found}
    check("a line is attributed to its step by second",
          ci_warnings.step_names(steps, when["Node.js 20 actions are deprecated. Use node24."]) == "Install")
    check("a second two steps share names both, never one of them",
          ci_warnings.step_names(steps, when["shared second"]) == "Lint | Test")
    carried = ci_warnings.job_findings({"steps": []}, "2026-11-03T01:00:00.0Z ##[notice]ok\n",
                                       [{"annotation_level": "warning", "message": "image is deprecated; look at the notice"},
                                        {"annotation_level": "notice", "message": "ok"}])
    check("a short log message does not hide a longer annotation; an equal one at its level is carried",
          [(l, m) for _, l, m in carried] == [("notice", "ok"), ("warning", "image is deprecated; look at the notice")],
          str(carried))
    dirty = ci_warnings.clean("a\x1b]0;pwned\x07b\x1b[?25lc\x1b[33md")
    check("terminal escapes other than colours are made inert; colours are still stripped",
          not any(c in dirty for c in "\x1b\x07") and dirty.endswith("cd"), repr(dirty))
    check("CRLF in an annotation folds to a space, not a '?'",
          ci_warnings.clean("a\r\nb\x0bc") == "a b c", repr(ci_warnings.clean("a\r\nb\x0bc")))
    check("a workflow name is cleaned too",
          ci_warnings.workflow_label({"name": "x\x1b]0;t\x07y"}) == "x?]0;t?y", ci_warnings.workflow_label({"name": "x\x1b]0;t\x07y"}))
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
              rc == 0 and out.startswith(f"fabric-ci-warnings: {REPO} — 3 run(s), 3 job(s) read; 6 distinct finding(s)\n")
              and "2x  ci / static / Install  [warning]\n    Node.js 20 actions are deprecated. Use node24.\n" in out
              and "in 2 of 3 run(s); latest run 2" in out, out)

        rc, out, err, calls = run(base_tab, "--repo", REPO, "--workflow", "pr-counts.yml", "--runs", "1", "--branch", "a b")
        check("--workflow (by file name) keeps one workflow's runs; --branch is sent escaped",
              rc == 0 and "1 run(s), 1 job(s)" in out and "branch=a%20b" in calls[0]["query"], out + err)

        rc, out, err, _ = run(base_tab, "--repo", REPO, "--level", "warning,log")
        check("--level keeps the named levels only",
              rc == 0 and "[notice]" not in out and "[warning]" in out and "[log]" in out and "4 distinct" in out, out)
        rc, out, err, calls = run(base_tab, "--repo", REPO, "--level", "warning,loud")
        check("--level with an unknown level: exit 2, nothing sent", rc == 2 and not calls and "--level" in err, err)

        rc, out, err, calls = run(base_tab, "--repo", REPO, "--branch", "feat+x&y")
        check("--branch is percent-encoded whole (+ and & included)", "branch=feat%2Bx%26y" in calls[0]["query"], str(calls[:1]))

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
            check(f"usage {args}: exit 2, one stderr line, nothing sent to GitHub",
                  rc == 2 and not calls and out == "" and err.count("\n") == 1, f"{rc} {err}")
        rc, out, err, calls = run(base_tab, "--help")
        check("--help: exit 0, names the options and the exit codes",
              rc == 0 and all(w in out for w in ("--repo", "--runs", "--workflow", "--branch", "--level", "--json", "exit:")) and not calls)

        print("ci-warnings: log matches the owner clears, and the Gradle banner")
        GZAPP = ["a deprecated bootstrap name is CAUGHT", "deprecated-refs: OK",
                 "Passed Tests.Flag is deprecated [12 ms]"]
        CONTROLS = ["npm warn deprecated foo@1", "DEPRECATION: Python 3.7 reached end of life",
                    "(node:1) [DEP0005] DeprecationWarning: Buffer() is deprecated"]
        log2 = "\n".join(["2026-11-03T03:00:0%d.0000000Z %s" % (i, m)
                          for i, m in enumerate(["Important project hierarchy lookup deprecations", *GZAPP, *CONTROLS])]) + "\n"
        job2 = {"id": 41, "name": "build", "status": "completed", "conclusion": "success", "steps": []}
        tab2 = table([{"id": 5, "name": "ci", "path": ".github/workflows/ci.yml@refs/heads/main"}], {5: [job2]},
                     extra_json={f"repos/{REPO}/check-runs/41/annotations": []},
                     text={f"repos/{REPO}/actions/jobs/41/logs": log2})

        def messages(doc):
            return [r["message"] for r in doc["findings"]]

        rc, out, err, _ = run(tab2, "--repo", REPO, "--json")
        doc = json.loads(out)
        check("no declaration: the banner is not a finding; the gzapp lines and the three controls are; nothing cleared",
              rc == 0 and sorted(messages(doc)) == sorted(GZAPP + CONTROLS) and doc["cleared"]["count"] == 0, out)
        for label, declared in (
                ("no match", [{"regex": "unrelated line", "reason": "r"}]),
                ("a regex that only covers part of a control", [{"regex": "npm warn", "reason": "r"}])):
            rc, out, _, _ = run(declare(tab2, {"cleared": declared}), "--repo", REPO, "--json")
            check(f"a declaration that does not match ({label}) leaves every control a finding",
                  rc == 0 and set(CONTROLS) <= set(messages(json.loads(out))), out)
        mine = {"cleared": [{"regex": "a deprecated bootstrap name is CAUGHT", "reason": "self-test label"},
                            {"regex": "deprecated-refs: OK", "reason": "a passing check"},
                            {"regex": r"Passed Tests\..* \[\d+ ms\]", "reason": "xUnit test names"},
                            {"regex": "never printed", "reason": "stale"}]}
        rc, out, err, _ = run(declare(tab2, mine), "--repo", REPO, "--json")
        doc = json.loads(out)
        cleared = doc["cleared"]
        check("each gzapp line is cleared by the declaration, counted per entry, and the controls stay findings",
              rc == 0 and sorted(messages(doc)) == sorted(CONTROLS) and cleared["count"] == 3 and cleared["distinct"] == 3
              and [e["count"] for e in cleared["entries"]] == [1, 1, 1, 0] and cleared["file"] == ci_warnings.CLEARED_FILE, out)
        rc, out, _, _ = run(declare(tab2, mine), "--repo", REPO)
        check("text report says N cleared by the file, with each reason",
              rc == 0 and f"3 line(s) cleared (3 distinct) by {ci_warnings.CLEARED_FILE}:" in out
              and "— self-test label" in out and "0x  /never printed/ — stale" in out and "3 distinct finding(s)" in out, out)
        evil = {"cleared": [{"regex": "deprecated-refs: OK", "reason": "ok\n\n9x  forged\x1b[2J\x1b]0;t\x07"}]}
        rc, out, _, _ = run(declare(tab2, evil), "--repo", REPO)
        check("a declaration's reason cannot send an escape or forge a finding line",
              rc == 0 and "\x1b" not in out and "\x07" not in out and "\n9x  forged" not in out and "1x  /deprecated-refs: OK/ — ok 9x forged" in out, repr(out[-200:]))
        rc, out, _, _ = run(declare(tab2, {"cleared": [{"regex": ".*", "reason": "all"}]}), "--repo", REPO, "--level", "warning")
        check("with --level excluding log nothing is cleared or counted as cleared",
              rc == 0 and "cleared" not in out, out)
        marked = table([{"id": 5, "name": "ci", "path": ".github/workflows/ci.yml@refs/heads/main"}], {5: [job2]},
                       extra_json={f"repos/{REPO}/check-runs/41/annotations": []},
                       text={f"repos/{REPO}/actions/jobs/41/logs": "2026-11-03T03:00:00.0Z ##[warning]Node 20 is deprecated\n"})
        rc, out, _, _ = run(declare(marked, {"cleared": [{"regex": ".*", "reason": "all"}]}), "--repo", REPO, "--json")
        doc = json.loads(out)
        check("a warning GitHub marks is not clearable, even by a regex that matches it",
              rc == 0 and messages(doc) == ["Node 20 is deprecated"] and doc["cleared"]["count"] == 0, out)
        for label, bad_doc in (("not JSON", "{"), ("no reason", {"cleared": [{"regex": "x", "reason": " "}]}),
                               ("an unknown key", {"cleared": [], "note": 1}),
                               ("an entry key typo", {"cleared": [{"regex": "x", "reason": "r", "level": "log"}]}),
                               ("a bad regex", {"cleared": [{"regex": "(", "reason": "r"}]})):
            rc, out, err, _ = run(declare(tab2, bad_doc), "--repo", REPO)
            check(f"an invalid declaration ({label}): one stderr line, exit 1, nothing reported",
                  rc == 1 and out == "" and err.startswith("fabric-ci-warnings: ") and err.count("\n") == 1, f"{rc} {out}{err}")
        unreadable = json.loads(json.dumps(tab2))
        unreadable["fail"][f"repos/{REPO}/contents/{ci_warnings.CLEARED_FILE}"] = "gh: Server Error (HTTP 502)"
        rc, out, err, _ = run(unreadable, "--repo", REPO)
        check("a declaration that cannot be read (not a 404) fails the run, never 'nothing cleared'",
              rc == 1 and out == "" and "502" in err, f"{rc} {out}{err}")

    print(f"\ntest_ci_warnings: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
