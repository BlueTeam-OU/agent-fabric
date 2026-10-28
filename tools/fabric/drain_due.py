#!/usr/bin/env python3
"""tools/fabric/drain_due.py — the scheduled drain's collection and report (agent-fabric ADR-034 §7 step 3, j434;
bin/fabric-drain-due is its shim, runtime/control/agent-fabric-drain.{service,timer} run it weekly).

CONTRACT.
  argv      [--ctl PATH] [--timeout SECONDS] [-h]. --ctl names the fabric-ctl to run (default: bin/fabric-ctl of this
            checkout); --timeout is the budget handed to `fabric-ctl all memory` (default 600).
  env       AGENT_FABRIC_STATE_DIR / XDG_STATE_HOME (through runtime/identity.py): the binding that is read and the
            state directory the runs are kept in. Nothing else is read; the child gets this environment as it is.
  role      Runs only under a `fabric-coordinator` binding. Under another role, or none, it says so in one line on
            stdout, changes nothing and exits 0: authority is the role's, not the account's (ADR-034 §7). A binding
            that cannot be read is not "another role": it is said and the exit is 1.
  work      1. `fabric-ctl all memory --out <state>/drain/<UTC date>/ --json --timeout N`, unsigned. The bundles land
               there; landing them is not done here (a collision needs the owner's ruling, memory/README.md).
            2. <that directory>/report.json: per store (an account's memory directory) the drainable count, the age in
               days of its oldest undrained memory and whether that is over the bound (harvest_memory.DRAIN_BOUND_DAYS).
               An account that did not answer, a store whose harvest failed and a report with no age are "unknown":
               status "unknown", never 0 and never over_bound false.
            3. One job on this login's own list (fabric-jobs, topic drain-due): "drain <date>: N claims in M stores,
               oldest D d (bound 14)", priority high when any store is over the bound, normal otherwise. A job of that
               topic that is still queued, active, paused or blocked is updated in place (title; priority only while it
               is normal or high, so an owner's `blocking` stays); a delivered one is a drain whose landing is under
               way, and a new job is added beside it. Nothing drainable anywhere adds and changes no job.
            4. The last 4 run directories are kept; older ones are removed. Only after a report was written, so a
               failing week never evicts the runs that worked.
  stdout    the report's summary line, and the job's id.
  stderr    every failure, prefixed `fabric-drain-due: `.
  exit      0 done, or not the coordinator; 1 the collection or the report failed, or no store answered at all (a
            week of "unknown" must show as a failed unit in the journal), or the job could not be kept; 2 bad argv.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Callable

HERE = os.path.dirname(os.path.realpath(__file__))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layout = _load("fabric_layout", os.path.join(HERE, "layout.py"))
identity = _load("fabric_identity", os.path.join(layout.FABRIC_ROOT, "runtime", "identity.py"))
harvest = _load("fabric_harvest", os.path.join(HERE, "harvest_memory.py"))

ROLE = "fabric-coordinator"
BOUND_DAYS = harvest.DRAIN_BOUND_DAYS
KEEP_RUNS = 4
TOPIC = "drain-due"
CTL_TIMEOUT_S = 600
JOBS_TIMEOUT_S = 60
DAY_MS = 86_400_000
RUN_DIR = re.compile(r"\d{4}-\d{2}-\d{2}\Z", re.ASCII)
# A job that holds a drain still to collect or being landed by hand; delivered ones are past it.
UPDATABLE = ("queued", "active", "paused", "blocked")


class Failed(Exception):
    """A failure said in one line, exit 1."""


def utc_date(now_ms: int) -> str:
    return datetime.datetime.fromtimestamp(now_ms / 1000, datetime.UTC).strftime("%Y-%m-%d")


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def store_of(row: dict, bundle: dict, now_ms: int) -> dict:
    """One store's line. Unknown wherever the report cannot say: a missing age is not 'nothing waits'."""
    login = row["account"]
    slug = bundle.get("slug") if isinstance(bundle.get("slug"), str) else "?"
    out: dict[str, Any] = {"account": login, "store": slug + (":projects-root" if bundle.get("projects_root") else ""),
                           "drainable": None, "oldest_age_days": None, "over_bound": None, "status": "unknown"}
    status = bundle.get("status")
    if status != "ok":
        out["why"] = f"bundle {status}"
        return out
    report = bundle.get("report")
    claims = _count(report.get("claims")) if isinstance(report, dict) else None
    rendering = report.get("needs_rendering") if isinstance(report, dict) else None
    if claims is None or not isinstance(rendering, list):
        out["why"] = "no usable harvest report"
        return out
    out["drainable"] = claims + len(rendering)
    if out["drainable"] == 0:
        out.update(status="ok", oldest_age_days=None, over_bound=False)
        return out
    oldest = report.get("oldest_drainable_ms")
    if _count(oldest) is None:
        out["why"] = "no age in the report (an older control agent, or a malformed one)"
        return out
    age_ms = max(0, now_ms - oldest)
    out.update(status="ok", oldest_age_days=round(age_ms / DAY_MS, 2), over_bound=age_ms > BOUND_DAYS * DAY_MS)
    return out


def stores_of(rows: list[dict], now_ms: int) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        unknown = {"account": row["account"], "store": None, "drainable": None, "oldest_age_days": None,
                   "over_bound": None, "status": "unknown"}
        if row.get("status") != "ok":
            out.append({**unknown, "why": f"account {row.get('status')}"})
            continue
        memory = row.get("memory")
        if not isinstance(memory, dict) or memory.get("status") != "ok":
            said = memory.get("status") if isinstance(memory, dict) else "no memory section"
            out.append({**unknown, "why": f"memory {said}"})
            continue
        bundles = memory.get("bundles")
        if not isinstance(bundles, list):
            out.append({**unknown, "why": "memory bundles unreadable"})
            continue
        out.extend(store_of(row, b, now_ms) if isinstance(b, dict) else {**unknown, "why": "bundle unreadable"} for b in bundles)
    return out


def summarize(stores: list[dict]) -> dict:
    waiting = [s for s in stores if s["status"] == "ok" and s["drainable"]]
    # Unknown stores with a count still contribute it: a known number is not thrown away with the unknown age.
    counted = [s for s in stores if s["drainable"]]
    ages = [s["oldest_age_days"] for s in waiting]
    return {"claims": sum(s["drainable"] for s in counted), "stores": len(counted),
            "oldest_age_days": max(ages) if ages else None,
            "over_bound": sum(1 for s in stores if s["over_bound"]),
            "unknown": sum(1 for s in stores if s["status"] == "unknown")}


def build_report(rows: list[dict], now_ms: int) -> dict:
    stores = stores_of(rows, now_ms)
    return {"date": utc_date(now_ms), "generated_ms": now_ms, "bound_days": BOUND_DAYS,
            "stores": stores, "totals": summarize(stores)}


def title_of(report: dict) -> str:
    t = report["totals"]
    age = "?" if t["oldest_age_days"] is None else f"{t['oldest_age_days']:.1f}"
    return (f"drain {report['date']}: {t['claims']} claims in {t['stores']} stores, oldest {age} d (bound {report['bound_days']})"
            + (f", {t['unknown']} unknown" if t["unknown"] else ""))


def priority_of(report: dict) -> str:
    return "high" if report["totals"]["over_bound"] else "normal"


def run_ctl(ctl: str, run_dir: str, timeout: int) -> list[dict]:
    """The rows `fabric-ctl all memory --json` prints, one JSON object a line. ctl exits 1 for a silent account or a
    refused bundle and still prints every row, so 0 and 1 both carry rows; any other status, or a line that is not a
    row, means the collection itself failed."""
    argv = [ctl, "all", "memory", "--out", run_dir, "--json", "--timeout", str(timeout)]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout + 60, check=False)
    except subprocess.TimeoutExpired:
        raise Failed(f"fabric-ctl did not finish in {timeout + 60} s") from None
    except OSError as e:
        raise Failed(f"cannot run {ctl}: {e}") from None
    if r.returncode not in (0, 1):
        raise Failed(f"fabric-ctl exited {r.returncode}: {(r.stderr or r.stdout).strip().splitlines()[-1:] or ['no output']}")
    rows = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise Failed(f"fabric-ctl printed a line that is not JSON: {line[:80]!r}") from None
        if not isinstance(row, dict) or not isinstance(row.get("account"), str):
            raise Failed(f"fabric-ctl printed a row with no account: {line[:80]!r}")
        rows.append(row)
    if not rows:
        raise Failed("fabric-ctl printed no rows" + (f" ({r.stderr.strip().splitlines()[-1]})" if r.stderr.strip() else ""))
    return rows


def write_report(run_dir: str, report: dict) -> None:
    os.makedirs(run_dir, mode=0o700, exist_ok=True)
    os.chmod(run_dir, 0o700)
    identity.atomic_write(os.path.join(run_dir, "report.json"), json.dumps(report, indent=2, sort_keys=True) + "\n", mode=0o600)


def prune_runs(drain_root: str, keep: int = KEEP_RUNS) -> list[str]:
    """Remove all but the newest `keep` dated run directories. A link is unlinked, never followed; a name that is not a
    date is not ours and stays."""
    names = sorted((n for n in os.listdir(drain_root) if RUN_DIR.match(n)), reverse=True)
    gone = []
    for name in names[keep:]:
        path = os.path.join(drain_root, name)
        if os.path.islink(path) or not os.path.isdir(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)
        gone.append(name)
    return gone


def jobs_cli(*args: str) -> subprocess.CompletedProcess:
    # cwd: the job's project and working copy are the ones its directory resolves to (jobs.py), and the timer's
    # directory is this checkout.
    r = subprocess.run([sys.executable, os.path.join(HERE, "jobs.py"), *args], capture_output=True, text=True,
                       timeout=JOBS_TIMEOUT_S, check=False, cwd=layout.FABRIC_ROOT)
    if r.returncode != 0:
        raise Failed(f"fabric-jobs {args[0]} failed: {(r.stderr or r.stdout).strip()[-200:]}")
    return r


def open_drain_jobs() -> list[dict]:
    """--stored: the state stream (the relay) is not asked; a weekly timer must not depend on it."""
    jobs = json.loads(jobs_cli("list", "--json", "--stored").stdout)
    return [j for j in jobs if j.get("topic") == TOPIC and j.get("state") in UPDATABLE]


def keep_job(report: dict) -> str | None:
    """The one job of this drain: updated when one is still open, added otherwise. None when nothing is drainable."""
    if not report["totals"]["claims"]:
        return None
    title, priority = title_of(report), priority_of(report)
    open_ = open_drain_jobs()
    if not open_:
        jobs_cli("add", title, "--topic", TOPIC, "--priority", priority)
        added = open_drain_jobs()
        if len(added) != 1:
            raise Failed(f"expected the one drain job after adding it, the list holds {len(added)}")
        return added[0]["id"]
    # Oldest first: a second open one is a stack an earlier run or a hand left; only the first is updated.
    job = min(open_, key=lambda j: int(j["id"].lstrip("j")))

    def retitle(doc: dict) -> None:
        for j in doc["jobs"]:
            if j["id"] == job["id"] and j["state"] in UPDATABLE:
                now = identity.now_iso()
                j["title"], j["updated"] = title, now
                j.setdefault("log", []).append({"at": now, "state": j["state"], "note": "title updated by fabric-drain-due"})
    identity.update_jobs(retitle)
    # An owner's `blocking` stays; only the two this tool sets are moved.
    if job.get("priority") in ("normal", "high") and job.get("priority") != priority:
        jobs_cli("prio", job["id"], priority)
    return job["id"]


def main(argv: list[str] | None = None, now_ms: Callable[[], int] = lambda: int(time.time() * 1000)) -> int:
    ap = argparse.ArgumentParser(prog="fabric-drain-due", description="collect every account's undrained memory, report its age against the bound, keep one drain job (ADR-034 §7 step 3)")
    ap.add_argument("--ctl", default=os.path.join(layout.FABRIC_ROOT, "bin", "fabric-ctl"))
    ap.add_argument("--timeout", type=int, default=CTL_TIMEOUT_S)
    args = ap.parse_args(argv)
    if args.timeout < 1:
        ap.error("--timeout must be at least 1 second")
    try:
        role = identity.read_binding().get("role")
    except SystemExit as e:
        print(f"fabric-drain-due: {e}", file=sys.stderr)
        return 1
    if role != ROLE:
        print(f"fabric-drain-due: this login holds {role or 'no role'}, not {ROLE}; nothing done")
        return 0
    now = now_ms()
    drain_root = os.path.join(identity.agent_state_dir(), "drain")
    run_dir = os.path.join(drain_root, utc_date(now))
    try:
        os.makedirs(run_dir, mode=0o700, exist_ok=True)
        rows = run_ctl(args.ctl, run_dir, args.timeout)
        # The age is read against the time the collection ended: a slow run does not make a memory look younger.
        report = build_report(rows, now_ms())
        write_report(run_dir, report)
        job = keep_job(report)
        prune_runs(drain_root)
    except (Failed, OSError, ValueError) as e:
        print(f"fabric-drain-due: {e}", file=sys.stderr)
        return 1
    print(f"{title_of(report)} -> {run_dir}/report.json" + (f"; job {job}" if job else "; no job (nothing drainable)"))
    if report["stores"] and all(s["status"] == "unknown" for s in report["stores"]):
        print("fabric-drain-due: no store answered", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
