#!/usr/bin/env python3
"""tools/fabric/github/scheduled_red.py with `gh` replaced on PATH by a stub that answers from recorded
workflow-runs responses: no network. The job list is a real one in a temporary state directory, written by
fabric-jobs' own code. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree, write_registry  # noqa: E402

own_instance_tree()
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "tools", "fabric", "github", "scheduled_red.py")
REPO, FLOW = "BlueTeam-OU/agent-fabric", "stripped-nightly.yml"
MARK = f"[scheduled-red:{REPO}/{FLOW}]"

# gh api's call is argv[1:]; the stub records it and answers the fixture, or fails as MODE says.
GH = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "$MOCK_STATE/calls"
case "$(cat "$MOCK_STATE/mode" 2>/dev/null || echo ok)" in
  ok) cat "$MOCK_STATE/runs.json" ;;
  noauth) echo "gh: To use GitHub CLI, run: gh auth login" >&2; exit 4 ;;
  http500) echo "gh: Server Error (HTTP 500)" >&2; exit 1 ;;
  notjson) echo "<html>proxy</html>" ;;
esac
'''


def run(created: str, conclusion: str | None, run_id: int, status: str = "completed") -> dict:
    return {"id": run_id, "status": status, "conclusion": conclusion, "created_at": created, "event": "schedule"}


# Recorded shape of GET repos/{r}/actions/workflows/{f}/runs?event=schedule&status=completed, newest first
# (other fields trimmed to what the reader may use).
RED = [run("2026-11-02T03:17:04Z", "failure", 300), run("2026-11-01T03:17:01Z", "cancelled", 299),
       run("2026-10-31T03:16:58Z", "failure", 298), run("2026-10-30T03:17:12Z", "timed_out", 297),
       run("2026-10-18T03:17:00Z", "success", 296), run("2026-10-17T03:17:00Z", "failure", 295)]
GREEN = [dict(RED[0], conclusion="success")] + RED[1:]


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:600]}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="sr") as tmp:
        mock, bindir, home, state = (os.path.join(tmp, d) for d in ("mock", "bin", "home", "state"))
        for d in (mock, bindir, home):
            os.makedirs(d)
        with open(os.path.join(bindir, "gh"), "w", encoding="utf-8") as fh:
            fh.write(GH)
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        # The registry is instance data a stripped tree lacks: the repository resolves through one this test plants.
        fixture_root = os.path.join(tmp, "root")
        write_registry(os.path.join(fixture_root, "projects"),
                       {"version": 1, "projects": {"agent-fabric": {"remotes": [f"https://github.com/{REPO}"]}}})
        env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": home, "MOCK_STATE": mock, "AGENT_FABRIC_STATE_DIR": state,
               "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_OPERATOR": fixture_root, "LC_ALL": "C.UTF-8", "GH_REPO": REPO}

        def feed(runs: list[dict], mode: str = "ok") -> None:
            with open(os.path.join(mock, "runs.json"), "w", encoding="utf-8") as fh:
                json.dump({"total_count": len(runs), "workflow_runs": runs}, fh)
            with open(os.path.join(mock, "mode"), "w", encoding="utf-8") as fh:
                fh.write(mode)

        def tool(*extra: str, project: bool = True) -> subprocess.CompletedProcess:
            argv = [sys.executable, TOOL, "--repository", REPO, "--workflow", FLOW, *(["--project", "agent-fabric"] if project else []), *extra]
            return subprocess.run(argv, env=env, cwd=tmp, capture_output=True, text=True, timeout=120)

        def jobs() -> list[dict]:
            p = os.path.join(state, "agents", subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip(), "jobs.json")
            try:
                with open(p, encoding="utf-8") as fh:
                    return json.load(fh)["jobs"]
            except FileNotFoundError:
                return []

        def set_state(job_id: str, state_name: str) -> None:
            p = os.path.join(state, "agents", subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip(), "jobs.json")
            with open(p, encoding="utf-8") as fh:
                doc = json.load(fh)
            for j in doc["jobs"]:
                if j["id"] == job_id:
                    j["state"] = state_name
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)

        print("a green or inconclusive newest run")
        feed(GREEN)
        p = tool()
        check("success: one line, exit 0, nothing added", p.returncode == 0 and len(p.stdout.splitlines()) == 1 and not jobs(), (p, jobs()))
        for conclusion in ("skipped", "cancelled"):
            feed([dict(RED[0], conclusion=conclusion)] + RED[1:])
            p = tool()
            check(f"{conclusion}: exit 0, nothing added", p.returncode == 0 and not jobs(), (p, jobs()))
        feed([dict(RED[0], status="in_progress", conclusion=None)] + GREEN)
        p = tool()
        check("a run still in progress is not the newest completed one", p.returncode == 0 and "success" in p.stdout and not jobs(), p)

        print("red")
        feed([dict(RED[0], conclusion="timed_out")] + RED[1:])
        check("timed_out is red as failure is", (p := tool("--dry-run")).returncode == 0 and "would add" in p.stdout, p)
        feed(RED)
        check("--dry-run says what it would add and adds nothing", (p := tool("--dry-run")).returncode == 0 and "would add" in p.stdout
              and MARK in p.stdout and not jobs(), (p, jobs()))
        p = tool()
        added = jobs()
        j = added[0] if added else {}
        check("red with no job: one job added, exit 0", p.returncode == 0 and len(added) == 1 and j.get("state") == "queued", (p, added))
        check("...high priority, topic ci, project as named", (j.get("priority"), j.get("topic"), j.get("project")) == ("high", "ci", "agent-fabric"), j)
        title = j.get("title", "")
        check("...the title names the workflow, run id and date, red since the first red after the last success, and ends in the marker",
              FLOW in title and "300" in title and "2026-11-02" in title and "red since 2026-10-30" in title and "contract each fix to its holder" in title
              and title.endswith(MARK), title)
        calls = open(os.path.join(mock, "calls"), encoding="utf-8").read().splitlines()
        reads = [c for c in calls if "actions/workflows" in c]
        check("...the read asks for event=schedule, status=completed on the branch", reads and all(
            f"repos/{REPO}/actions/workflows/{FLOW}/runs" in c and "event=schedule" in c and "status=completed" in c and "branch=main" in c for c in reads), calls)

        print("red with an open marked job")
        for state_name in ("queued", "active", "paused", "blocked", "delivered"):
            set_state("j1", state_name)
            p = tool()
            check(f"{state_name}: nothing added, the line names j1", p.returncode == 0 and len(jobs()) == 1 and "j1" in p.stdout, (p, jobs()))
        check("--dry-run names it too", "j1" in tool("--dry-run").stdout)

        print("red with only a done marked job")
        set_state("j1", "done")
        p = tool()
        check("done: a second job is added", p.returncode == 0 and len(jobs()) == 2 and jobs()[1]["title"].endswith(MARK), (p, jobs()))
        other = subprocess.run([sys.executable, TOOL, "--repository", REPO, "--workflow", "other.yml", "--project", "agent-fabric"],
                               env=env, cwd=tmp, capture_output=True, text=True, timeout=120)
        check("another workflow's marker is another job", other.returncode == 0 and len(jobs()) == 3, (other, jobs()))

        print("the project defaults to the repository's registry id")
        set_state("j2", "done")
        set_state("j3", "done")
        p = tool(project=False)
        check("a registered repository files under its id", p.returncode == 0 and jobs()[-1]["project"] == "agent-fabric", (p, jobs()[-1:]))
        n = len(jobs())
        p = subprocess.run([sys.executable, TOOL, "--repository", "nobody/unregistered", "--workflow", FLOW],
                           env=env, cwd=tmp, capture_output=True, text=True, timeout=120)
        check("an unregistered repository without --project: exit 2, nothing added", p.returncode == 2 and len(jobs()) == n and p.stderr.strip(), p)

        print("the runs cannot be read")
        for mode in ("noauth", "http500", "notjson"):
            feed(RED, mode)
            n = len(jobs())
            p = tool()
            check(f"{mode}: exit 3, reason on stderr, no stdout, nothing added", p.returncode == 3 and p.stderr.strip() and not p.stdout and len(jobs()) == n, p)
        bad = {
            "no workflow_runs": {"total_count": 0},
            "no completed run": {"workflow_runs": [run("2026-11-02T03:17:04Z", None, 5, "queued")]},
            "an undefined conclusion": {"workflow_runs": [run("2026-11-02T03:17:04Z", "startup_failure", 5)]},
            "a date not a date": {"workflow_runs": [run("yesterday", "failure", 5)]},
            "an id not an integer": {"workflow_runs": [run("2026-11-02T03:17:04Z", "failure", "5")]},
            "a list for the answer": [],
        }
        for label, doc in bad.items():
            with open(os.path.join(mock, "runs.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            with open(os.path.join(mock, "mode"), "w", encoding="utf-8") as fh:
                fh.write("ok")
            p = tool()
            check(f"{label}: exit 3, nothing added, never a green line", p.returncode == 3 and not p.stdout and len(jobs()) == n, p)

        print("a streak with no success in the page")
        feed([run("2026-11-02T03:17:04Z", "failure", 9), run("2026-11-01T03:17:04Z", "failure", 8)])
        set_state(jobs()[-1]["id"], "done")
        p = tool("--dry-run")
        check("red since is said to be the oldest seen or earlier", "red since 2026-11-01 or earlier" in p.stdout, p)

        print("an older run this does not read")
        for j in jobs():
            set_state(j["id"], "done")
        n = len(jobs())
        feed([RED[0], run("2026-10-31T03:16:58Z", "failure", 298), run("2026-10-20T03:16:00Z", "startup_failure", 290)] + RED[4:])
        p = tool("--dry-run")
        check("a red newest run is still red when an older one concluded startup_failure; red since says where the count ended",
              p.returncode == 0 and "would add" in p.stdout and "red since 2026-10-31 or earlier (run 290" in p.stdout, p)
        feed([RED[0], {"status": "completed", "conclusion": "failure"}] + RED[4:])
        p = tool("--dry-run")
        check("...an older run with no id is said as \"a run\", never given a number", p.returncode == 0 and "(a run before it" in p.stdout and "run 0" not in p.stdout, p)
        feed([run("2026-11-02T03:17:04Z", "startup_failure", 300), RED[2]])
        p = tool()
        check("...but the NEWEST run's undefined conclusion is still unreadable, exit 3, nothing added", p.returncode == 3 and len(jobs()) == n, p)

        print("a dropped marked job")
        feed(RED)
        tool()
        set_state(jobs()[-1]["id"], "dropped")
        n = len(jobs())
        p = tool()
        check("dropped is closed, as fabric-jobs counts it: red files a new job (decision recorded in the PR)", p.returncode == 0 and len(jobs()) == n + 1, (p, jobs()[-1:]))

        print("the control: the fixture is what is read")
        for j in jobs():
            set_state(j["id"], "done")
        n = len(jobs())
        feed(RED)
        check("the red fixture adds a job", tool().returncode == 0 and len(jobs()) == n + 1)
        for j in jobs():
            set_state(j["id"], "done")
        n = len(jobs())
        feed(GREEN)
        p = tool()
        check("the same fixture made green adds nothing", p.returncode == 0 and len(jobs()) == n, (p, jobs()[n:]))

        print("the command line")
        for argv in (["--repository", "nope", "--workflow", FLOW], ["--repository", REPO, "--workflow", "../x.yml"],
                     ["--repository", REPO, "--workflow", FLOW, "--branch", "a b"], ["--repository", REPO]):
            p = subprocess.run([sys.executable, TOOL, *argv], env=env, cwd=tmp, capture_output=True, text=True, timeout=60)
            check(f"{' '.join(argv[-2:])}: exit 2, nothing added", p.returncode == 2 and len(jobs()) == n, p)

    print(f"\ntest_scheduled_red: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
