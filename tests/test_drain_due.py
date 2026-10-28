#!/usr/bin/env python3
"""tools/fabric/drain_due.py, bin/fabric-drain-due and the drain units (ADR-034 §7 step 3, j434). A fixture fabric-ctl
prints the rows a real one would, from a state directory of the test's own: no relay, no account, no network. Each rule
has its positive control (the same run with the rule's condition changed does the thing)."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from git_env import scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
scrub_process_env()
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 86_400_000
NOW = 1_800_000_000_000          # 2027-01-15 08:00:00 UTC
TODAY = "2027-01-15"
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
_spec = importlib.util.spec_from_file_location("drain_due_under_test", os.path.join(ROOT, "tools", "fabric", "drain_due.py"))
dd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dd)
identity = dd.identity


def bundle(slug: str, claims: int, oldest_days: float | None, *, rendering: int = 0, **extra) -> dict:
    report = {"claims": claims, "counts": {"in_scope": claims}, "needs_rendering": ["r"] * rendering, "skipped_no_roles_class": []}
    if oldest_days is not None:
        report["oldest_drainable_ms"] = int(NOW - oldest_days * DAY)
    elif claims + rendering == 0:
        report["oldest_drainable_ms"] = None
    return {"slug": slug, "status": "ok", "files": 3, "working_copy": f"/w/{slug}", "report": report, **extra}


def row(account: str, bundles: list | None, **extra) -> dict:
    return {"account": account, "host": "h", "status": "ok", "memory": {"status": "ok", "bundles": bundles}, **extra}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:900]}"))
        fails += not good

    with tempfile.TemporaryDirectory(prefix="drain-due-", dir="/tmp") as raw:
        tmp = os.path.realpath(raw)
        state = os.path.join(tmp, "state")
        os.makedirs(state)
        os.environ["AGENT_FABRIC_STATE_DIR"] = state
        login = identity.current_agent()

        def bind(role: str | None) -> None:
            os.makedirs(identity.agent_state_dir(), exist_ok=True)
            with open(identity.binding_path(), "w", encoding="utf-8") as fh:
                json.dump({"agent": login, "host": identity.current_host(), "role": role, "updated_at": "2027-01-01T00:00:00Z"}, fh)

        def ctl(rows: list[str] | list[dict], *, status: int = 0, name: str = "ctl") -> str:
            """A fabric-ctl that prints `rows`, records its argv beside itself and the directory it was given."""
            path = os.path.join(tmp, name)
            lines = [r if isinstance(r, str) else json.dumps(r) for r in rows]
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"#!{sys.executable}\nimport json, os, sys\n"
                         f"open({path + '.argv'!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
                         f"out = sys.argv[sys.argv.index('--out') + 1]\nos.makedirs(os.path.join(out, 'acct'), exist_ok=True)\n"
                         f"open(os.path.join(out, 'acct', 'wc.tar'), 'w').write('x')\n"
                         f"sys.stdout.write({chr(10).join(lines) + chr(10)!r})\nsys.exit({status})\n")
            os.chmod(path, 0o755)
            return path

        def run(path: str, *extra: str, now: int = NOW) -> tuple[int, str, str]:
            import contextlib
            import io
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = dd.main(["--ctl", path, *extra], now_ms=lambda: now)
            return code, out.getvalue(), err.getvalue()

        def jobs() -> list[dict]:
            return json.loads(dd.jobs_cli("list", "--json", "--stored", "--all").stdout)

        def report(day: str = TODAY) -> dict:
            with open(os.path.join(identity.agent_state_dir(), "drain", day, "report.json"), encoding="utf-8") as fh:
                return json.load(fh)

        # --- the fleet of the acceptance: an over-bound store, a store within it, an empty one, an account that is silent
        fleet = [row("dev-01", [bundle("alpha", 3, 20.0), bundle("beta", 2, 4.5, rendering=1)]),
                 row("dev-02", [bundle("gamma", 0, None)]),
                 {"account": "dev-03", "host": "h", "status": "no answer"}]

        print("fabric-drain-due: off the coordinator's role it changes nothing")
        marker = ctl(fleet, name="ctl-off")
        for role in ("python-dev", None):
            bind(role)
            before = sorted(os.walk(state))
            code, out, err = run(marker)
            check(f"role {role}: exit 0, one line, nothing run, nothing written",
                  code == 0 and len(out.strip().splitlines()) == 1 and "fabric-coordinator" in out and err == ""
                  and not os.path.exists(marker + ".argv") and sorted(os.walk(state)) == before, (code, out, err))
        os.remove(identity.binding_path())
        code, out, err = run(marker)
        check("no binding at all is no role, not a failure", code == 0 and not os.path.exists(marker + ".argv"), (code, out, err))
        with open(identity.binding_path(), "w", encoding="utf-8") as fh:
            fh.write("{broken")
        code, out, err = run(marker)
        check("an unreadable binding is said and fails: it is not 'another role'", code == 1 and "not valid JSON" in err and not os.path.exists(marker + ".argv"), (code, err))

        print("fabric-drain-due: the first run")
        bind("fabric-coordinator")
        path = ctl(fleet)
        code, out, err = run(path)
        check("exit 0, summary line names the job", code == 0 and err == "" and "job j" in out, (code, out, err))
        argv = json.load(open(path + ".argv"))
        run_dir = os.path.join(identity.agent_state_dir(), "drain", TODAY)
        check("ctl was asked for every account's memory into the dated directory, as JSON",
              argv[:2] == ["all", "memory"] and argv[argv.index("--out") + 1] == run_dir and "--json" in argv, argv)
        rep = report()
        stores = {(s["account"], s["store"]): s for s in rep["stores"]}
        a = stores[("dev-01", "alpha")]
        check("an over-bound store: count, age, over_bound true", a["drainable"] == 3 and a["oldest_age_days"] == 20.0 and a["over_bound"] is True and a["status"] == "ok", a)
        b = stores[("dev-01", "beta")]
        check("a held memory counts as drainable; within the bound", b["drainable"] == 3 and b["oldest_age_days"] == 4.5 and b["over_bound"] is False, b)
        g = stores[("dev-02", "gamma")]
        check("a store with nothing waiting is ok, no age, not over", g["drainable"] == 0 and g["oldest_age_days"] is None and g["over_bound"] is False and g["status"] == "ok", g)
        u = stores[("dev-03", None)]
        check("an account that did not answer is unknown, never 0 and never within the bound",
              u["status"] == "unknown" and u["drainable"] is None and u["over_bound"] is None and u["oldest_age_days"] is None and "no answer" in u["why"], u)
        check("totals", rep["totals"] == {"claims": 6, "stores": 2, "oldest_age_days": 20.0, "over_bound": 1, "unknown": 1} and rep["bound_days"] == 14, rep["totals"])
        check("report.json is private", stat.S_IMODE(os.stat(os.path.join(run_dir, "report.json")).st_mode) == 0o600
              and stat.S_IMODE(os.stat(run_dir).st_mode) == 0o700)
        js = [j for j in jobs() if j.get("topic") == "drain-due"]
        check("one job, high, titled with count, stores, age and bound, the unknown account said",
              len(js) == 1 and js[0]["priority"] == "high" and js[0]["title"] == f"drain {TODAY}: 6 claims in 2 stores, oldest 20.0 d (bound 14), 1 unknown", js)
        first = js[0]["id"]

        print("fabric-drain-due: the second run updates that job")
        better = [row("dev-01", [bundle("alpha", 1, 6.0)])]
        code, out, err = run(ctl(better, name="ctl2"), now=NOW + 3600_000)
        js = [j for j in jobs() if j.get("topic") == "drain-due"]
        check("still one job, the same id, new title, priority back to normal, the change logged",
              code == 0 and len(js) == 1 and js[0]["id"] == first and js[0]["title"] == f"drain {TODAY}: 1 claims in 1 stores, oldest 6.0 d (bound 14)"
              and js[0]["priority"] == "normal" and js[0]["log"][-1].get("note", "").startswith("title updated"), (code, err, js))
        dd.jobs_cli("prio", first, "blocking")
        run(ctl(fleet, name="ctl3"))
        js = [j for j in jobs() if j["id"] == first]
        check("an owner's blocking priority stays; the title still follows", js[0]["priority"] == "blocking" and js[0]["title"].startswith(f"drain {TODAY}: 6 claims"), js)
        dd.jobs_cli("prio", first, "normal")
        run(ctl(fleet, name="ctl3b"))
        check("a normal job is raised to high when a store goes over (positive control of the above)", [j for j in jobs() if j["id"] == first][0]["priority"] == "high")

        print("fabric-drain-due: a delivered drain is past; a new one is a new job")
        dd.jobs_cli("start", first)
        dd.jobs_cli("deliver", first, "develop-qzapp/x/feat/landing")
        code, out, err = run(ctl(fleet, name="ctl4"))
        mine = [j for j in jobs() if j.get("topic") == "drain-due"]
        check("a second job beside the delivered one", code == 0 and len(mine) == 2 and sorted(j["state"] for j in mine) == ["delivered", "queued"], (code, err, mine))

        print("fabric-drain-due: nothing drainable, nothing known")
        code, out, err = run(ctl([row("dev-01", [bundle("alpha", 0, None)])], name="ctl5"))
        check("no drainable memory adds no job", code == 0 and len([j for j in jobs() if j.get("topic") == "drain-due"]) == 2 and "no job" in out, (code, out, err))
        code, out, err = run(ctl([{"account": "dev-01", "host": "h", "status": "no answer"}], name="ctl6"))
        check("no store answered at all is a failed unit, the report still written", code == 1 and "no store answered" in err and report()["totals"]["unknown"] == 1, (code, err))
        code, out, err = run(ctl([row("dev-01", [])], name="ctl7"))
        check("an account with no memory directory is known and empty, not a failure", code == 0, (code, err))

        print("fabric-drain-due: what cannot be told stays unknown")
        stale = bundle("old", 2, None)       # an older control agent: counts, no age
        for label, rows_, why in (
                ("a report with no age", [row("d", [stale])], "no age"),
                ("a failed harvest", [row("d", [{"slug": "x", "status": "harvest-failed"}])], "harvest-failed"),
                ("a refused memory section", [{"account": "d", "host": "h", "status": "ok", "memory": {"status": "refused"}}], "refused"),
                ("a row with no memory section", [{"account": "d", "host": "h", "status": "ok"}], "no memory section"),
                ("an age that is not a time", [row("d", [{**bundle("x", 1, 1.0), "report": {"claims": 1, "needs_rendering": [], "oldest_drainable_ms": "soon"}}])], "no age"),
                ("a claims count that is not a number", [row("d", [{**bundle("x", 1, 1.0), "report": {"claims": True, "needs_rendering": []}}])], "usable")):
            s = dd.stores_of(rows_, NOW)[0]
            check(f"{label}: unknown, not over, not 0 days", s["status"] == "unknown" and s["over_bound"] is None and s["oldest_age_days"] is None and why in s["why"], s)
        check("an unknown age keeps the count it did give", dd.stores_of([row("d", [stale])], NOW)[0]["drainable"] == 2)
        edge = dd.stores_of([row("d", [{**bundle("x", 1, None), "report": {"claims": 1, "needs_rendering": [], "oldest_drainable_ms": NOW - 14 * DAY}}]),
                             row("d", [{**bundle("y", 1, None), "report": {"claims": 1, "needs_rendering": [], "oldest_drainable_ms": NOW - 14 * DAY - 1}}])], NOW)
        check("exactly the bound is within it, a millisecond more is over", [s["over_bound"] for s in edge] == [False, True], edge)

        print("fabric-drain-due: the collection itself failing")
        runs = os.path.join(identity.agent_state_dir(), "drain")
        before = sorted(os.listdir(runs))
        for label, spec, want in (("ctl exit 3", ctl([], status=3, name="c8"), "exited 3"),
                                  ("a line that is not JSON", ctl(["not json"], name="c9"), "not JSON"),
                                  ("no rows", ctl([], name="c10"), "no rows"),
                                  ("a missing ctl", os.path.join(tmp, "absent"), "cannot run")):
            code, out, err = run(spec, now=NOW + 40 * DAY)
            check(f"{label}: exit 1, said", code == 1 and want in err, (code, err))
        check("a failing run kept every earlier run (its own empty directory is the only change)",
              set(os.listdir(runs)) - set(before) <= {"2027-02-24"} and set(before) <= set(os.listdir(runs)), os.listdir(runs))

        print("fabric-drain-due: the last 4 runs are kept")
        for d in ("2026-12-01", "2026-12-08", "2026-12-15", "2026-12-22", "2026-12-29", "2027-01-05"):
            os.makedirs(os.path.join(runs, d), exist_ok=True)
        os.makedirs(os.path.join(runs, "notes"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "elsewhere"))
        os.symlink(os.path.join(tmp, "elsewhere"), os.path.join(runs, "2026-11-01"))
        shutil.rmtree(os.path.join(runs, "2027-02-24"), ignore_errors=True)   # the failing runs' own, not an earlier run
        code, out, err = run(ctl(fleet, name="c11"))
        left = sorted(d for d in os.listdir(runs) if d[:1].isdigit())
        check("the newest four dated directories remain", code == 0 and left == ["2026-12-22", "2026-12-29", "2027-01-05", "2027-01-15"], (code, err, left))
        check("a name that is not a date and a link's target are untouched, the link itself is gone",
              "notes" in os.listdir(runs) and os.path.isdir(os.path.join(tmp, "elsewhere")) and not os.path.lexists(os.path.join(runs, "2026-11-01")), os.listdir(runs))

        print("fabric-drain-due: the installed command and the units")
        env = {**os.environ, "AGENT_FABRIC_PYTHON": sys.executable}
        bind("python-dev")
        r = subprocess.run([os.path.join(ROOT, "bin", "fabric-drain-due"), "--ctl", marker], capture_output=True, text=True, timeout=60, env=env, check=False)
        check("bin/fabric-drain-due off-role: one line, exit 0", r.returncode == 0 and len(r.stdout.strip().splitlines()) == 1 and "fabric-coordinator" in r.stdout, (r.returncode, r.stdout, r.stderr))
        r = subprocess.run([os.path.join(ROOT, "bin", "fabric-drain-due"), "--bogus"], capture_output=True, text=True, timeout=60, env=env, check=False)
        check("bad argv exits 2", r.returncode == 2, (r.returncode, r.stderr))
        unit = {}
        for kind in ("service", "timer"):
            with open(os.path.join(ROOT, "runtime", "control", f"agent-fabric-drain.{kind}"), encoding="utf-8") as fh:
                unit[kind] = fh.read()
        svc, timer = unit["service"], unit["timer"]
        check("service: oneshot, runs the shim, bounded to cover the ctl budget plus the job work",
              "Type=oneshot" in svc and "bin/fabric-drain-due" in svc and "TimeoutStartSec=15min" in svc
              and dd.CTL_TIMEOUT_S + 60 + dd.JOBS_TIMEOUT_S * 3 < 15 * 60, svc)
        check("timer: Monday 06:00 UTC, persistent, 15 min spread",
              "OnCalendar=Mon *-*-* 06:00:00 UTC" in timer and "Persistent=true" in timer and "RandomizedDelaySec=15min" in timer and "WantedBy=timers.target" in timer, timer)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
