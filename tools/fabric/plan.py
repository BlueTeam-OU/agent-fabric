#!/usr/bin/env python3
"""tools/fabric/plan.py — the coordinator's plans as data (agent-fabric
ADR-047), behind bin/fabric-plan.

    fabric-plan new <id> <title>
    fabric-plan step add <plan> <title> --owner <login> [--after s1,s2] [--est-days N] [--note TEXT]
    fabric-plan link <plan> <step> <login>:<job>  [--replace]
    fabric-plan show [<plan>] [--json]
    fabric-plan export <plan>

CONTRACT
  A plan is {id, title, created_at, status, steps}; a step {id, title,
  owner, depends_on, job, est_days?, note?}, `owner` a placed login and `job`
  `<login>:<job-id>` or null. Plans live in the running coordinator's state,
  agents/<login>/plans/<id>.json, written only through runtime/identity.py
  (update_plan). A plan's `status` is "open"; no command changes it yet.
  A step has no state of its own (ADR-047 rule 3): it is its job's, read
  now, or
    planned   no job, and nothing it depends on is unfinished
    waiting   no job, and a step it depends on is not done
    unknown   the job cannot be read, with the reason
  The job is read from its owner's open list (`fabric-ctl <login> jobs
  --json`); one that is not there is read from the closed list through the
  host executor (`fabric-host <host> run --as <login> -- fabric-jobs list
  --all --json`, the bridge ADR-046 rule 5 names); when the first cannot be
  asked the second is tried, and both reasons are said if both fail. Unknown
  stays unknown: no state is guessed from a failed read.
  env     AGENT_FABRIC_STATE_DIR (the state root), AGENT_FABRIC_HOSTS_REGISTRY
  stdout  the answer (`show --json`: one JSON document)
  stderr  every refusal, one line `fabric-plan: <why>`
  exit    0 done; 1 refused (any session not bound to fabric-coordinator
          too, a duplicate or unknown id, an owner or job not placed); 2 usage
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from typing import Any, Callable

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import roots  # noqa: E402

FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(HERE))
ROLE = "fabric-coordinator"
CALL_TIMEOUT_S = 60
CTL_TIMEOUT_S = 20          # fabric-ctl's own wait for the control agents' replies, as fleet.py

LOGIN = re.compile(r"[a-z_][a-z0-9_-]{0,31}", re.ASCII)
STEP_ID = re.compile(r"s[1-9][0-9]{0,3}", re.ASCII)
LINK = re.compile(r"([a-z_][a-z0-9_-]{0,31}):(j[1-9][0-9]*)", re.ASCII)
JOB_STATES = ("queued", "active", "blocked", "delivered", "done", "dropped")   # tools/fabric/jobs.py STATES
TITLE_MAX = 200
EST_MAX = 3650


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


identity = _load("fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))


class Refused(Exception):
    """A refusal said in one line; nothing was written."""


class Unreadable(Exception):
    """A job list that could not be read, and why."""


# ── reading the jobs ────────────────────────────────────────────────

def printable(value: Any) -> str:
    """Text from another account as one line a terminal shows and never
    obeys: C0, DEL and C1 (U+009B is a CSI) as '?', whitespace collapsed."""
    return " ".join("".join("?" if ord(c) < 32 or 127 <= ord(c) < 160 else c for c in str(value)).split())


def bounded_run(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess:
    """fleet.py's runner: an argument list, a timeout, stdin closed, and the
    whole process group killed on a timeout (the executor's ssh and sudo are
    grandchildren that subprocess.run's kill of the child leaves running)."""
    import fleet
    return fleet.run_program(argv, timeout=timeout)


def hosts_registry() -> dict:
    with open(roots.hosts_registry(), encoding="utf-8") as fh:
        reg = json.load(fh)
    if not isinstance(reg, dict) or any(k in reg and not isinstance(reg[k], dict) for k in ("placement", "kinds")):
        raise ValueError("not a registry")
    return reg


class FleetReader:
    """The two sources of a job's state. `run(argv, timeout=)` returns a
    CompletedProcess; a test fakes it and nothing else."""

    def __init__(self, run: Callable[..., Any] = bounded_run):
        self.run = run

    def _ask(self, argv: list[str], what: str) -> subprocess.CompletedProcess:
        try:
            return self.run(argv, timeout=CALL_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise Unreadable(f"{what} did not answer in {CALL_TIMEOUT_S} s") from None
        except OSError as e:
            raise Unreadable(f"{what} could not run: {printable(e.strerror or e)}") from None

    @staticmethod
    def _exit(r: subprocess.CompletedProcess, what: str) -> Unreadable:
        said = ((r.stderr or "") + (r.stdout or "")).strip().splitlines()
        return Unreadable(f"{what} exited {r.returncode}" + (f": {printable(said[-1])[:160]}" if said else ""))

    def open_jobs(self, login: str) -> list[dict]:
        what = f"fabric-ctl {login} jobs"
        r = self._ask([os.path.join(FABRIC_ROOT, "bin", "fabric-ctl"), login, "jobs", "--json", "--timeout", str(CTL_TIMEOUT_S)], what)
        # fabric-ctl exits 1 with the account's row printed when it did not answer: the row says why.
        try:
            rows = [json.loads(line) for line in (r.stdout or "").splitlines() if line.strip()]
            row = rows[0]
            if row.get("status") != "ok":
                raise Unreadable(f"{login}'s control agent: {printable(row.get('status'))}")
            jobs = row.get("jobs") or {}
            if jobs.get("status") != "ok":
                raise Unreadable(f"{login}'s jobs: {printable(jobs.get('status'))}"
                                 + (f" ({printable(jobs['error'])[:160]})" if jobs.get("error") else ""))
            listed = jobs.get("jobs")
            if not isinstance(listed, list):
                raise ValueError("no job list")
        except (ValueError, IndexError, AttributeError, TypeError):
            if r.returncode != 0:
                raise self._exit(r, what) from None
            raise Unreadable(f"{what} answered something else") from None
        if r.returncode != 0:
            raise self._exit(r, what)
        return listed

    def closed_jobs(self, login: str) -> list[dict]:
        try:
            reg = hosts_registry()
        except (OSError, ValueError) as e:
            raise Unreadable(f"the hosts registry could not be read ({e.__class__.__name__})") from None
        if (reg.get("kinds") or {}).get(login) == "human":
            raise Unreadable(f"{login} is a human login: no agent enters a human's account (ADR-010 rule 12)")
        host = (reg.get("placement") or {}).get(login)
        if not host:
            raise Unreadable(f"{login} is placed on no host")
        what = f"fabric-host {host} run --as {login} fabric-jobs list"
        r = self._ask([os.path.join(FABRIC_ROOT, "bin", "fabric-host"), host, "run", "--as", login, "--",
                       "fabric-jobs", "list", "--all", "--json"], what)
        if r.returncode != 0:
            raise self._exit(r, what)
        try:
            listed = json.loads(r.stdout or "")
            if not isinstance(listed, list):
                raise ValueError("not a list")
            return listed
        except ValueError:
            raise Unreadable(f"{what} answered something else") from None


def find_job(reader: Any, cache: dict, login: str, job_id: str) -> dict:
    """The job's row, or Unreadable with why. Each list is asked once per login."""
    problems: list[str] = []
    for source, ask in (("open", reader.open_jobs), ("closed", reader.closed_jobs)):
        if (source, login) not in cache:
            try:
                cache[(source, login)] = ask(login)
            except Unreadable as e:
                cache[(source, login)] = e
        got = cache[(source, login)]
        if isinstance(got, Unreadable):
            problems.append(f"{source} list: {got}")
            continue
        for j in got:
            if isinstance(j, dict) and j.get("id") == job_id:
                return j
    if len(problems) == 2:
        raise Unreadable("; ".join(problems))
    if problems:
        raise Unreadable(f"{job_id} is not on the list that could be read; the other could not ({problems[0]})")
    raise Unreadable(f"{job_id} is on neither the open nor the closed list of {login}")


def derive(plan: dict, reader: Any) -> list[dict]:
    """The plan's steps, each with `state` and, for waiting and unknown, `reason` (ADR-047 rule 3)."""
    cache: dict = {}
    out: list[dict] = []
    done: set[str] = set()
    for step in plan["steps"]:
        s = dict(step)
        link = step.get("job")
        if link:
            m = LINK.fullmatch(str(link))
            try:
                if not m:
                    raise Unreadable(f"the link {link!r} is not <login>:<job-id>")
                row = find_job(reader, cache, m.group(1), m.group(2))
                state = row.get("state")
                if state not in JOB_STATES:
                    raise Unreadable(f"{link} has a state this tool does not know ({str(state)[:40]!r})")
                s["state"] = state
            except Unreadable as e:
                s["state"], s["reason"] = "unknown", str(e)
        else:
            behind = [d for d in step.get("depends_on", []) if d not in done]
            if behind:
                s["state"], s["reason"] = "waiting", "waits for " + ", ".join(behind)
            else:
                s["state"] = "planned"
        if s["state"] == "done":
            done.add(step["id"])
        out.append(s)
    return out


# ── the commands ───────────────────────────────────────────────────

def clean_title(text: str) -> str:
    if any((ord(c) < 32 and c not in "\t\n\r") or 127 <= ord(c) < 160 for c in text):
        raise Refused("a title carries a control character")
    text = " ".join(text.split())
    if not text or len(text) > TITLE_MAX:
        raise Refused(f"a title is one line of 1 to {TITLE_MAX} characters")
    return text


def placed(login: str) -> None:
    """The login is one the hosts registry places, and an agent's: a typo would
    link to a list nobody reads, and no agent enters a human's account."""
    if not LOGIN.fullmatch(login):
        raise Refused(f"{login!r} is not a login")
    try:
        reg = hosts_registry()
    except (OSError, ValueError) as e:
        raise Refused(f"the hosts registry could not be read ({e.__class__.__name__}): cannot tell whether {login} is placed") from None
    if login not in (reg.get("placement") or {}):
        raise Refused(f"{login} is placed on no host (runtime/hosts/registry.json)")
    if (reg.get("kinds") or {}).get(login) == "human":
        raise Refused(f"{login} is a human login: a step is an agent's job (ADR-044)")


def get_plan(plan_id: str) -> dict:
    plan = identity.read_plan(plan_id)
    if plan is None:
        raise Refused(f"no plan {plan_id!r}")
    return plan


def cmd_new(a: argparse.Namespace) -> int:
    title = clean_title(a.title)

    def make(doc: dict | None) -> dict:
        if doc is not None:
            raise Refused(f"plan {a.id} exists")
        return {"id": a.id, "title": title, "created_at": identity.now_iso(), "status": "open", "steps": []}
    identity.update_plan(a.id, make)
    print(f"plan {a.id}")
    return 0


def cmd_step_add(a: argparse.Namespace) -> int:
    title = clean_title(a.title)
    placed(a.owner)
    est: Any = None
    if a.est_days is not None:
        try:
            est = float(a.est_days)
        except ValueError:
            raise Refused("--est-days is a number of days") from None
        if not 0 < est <= EST_MAX:
            raise Refused(f"--est-days is more than 0 and at most {EST_MAX}")
        est = int(est) if est == int(est) else est
    after = [x for x in (a.after or "").split(",") if x]
    note = clean_title(a.note) if a.note is not None else None
    made: dict = {}

    def add(doc: dict | None) -> dict:
        if doc is None:
            raise Refused(f"no plan {a.plan!r}")
        known = {s["id"] for s in doc["steps"]}
        for d in after:
            if d not in known:
                raise Refused(f"--after names {d}, which is not a step of {a.plan}")
        n = max([int(s["id"][1:]) for s in doc["steps"] if STEP_ID.fullmatch(s["id"])] or [0]) + 1
        step: dict = {"id": f"s{n}", "title": title, "owner": a.owner, "depends_on": list(dict.fromkeys(after)), "job": None}
        if est is not None:
            step["est_days"] = est
        if note is not None:
            step["note"] = note
        doc["steps"].append(step)
        made.update(step)
        return doc
    identity.update_plan(a.plan, add)
    print(f"step {made['id']}")
    return 0


def cmd_link(a: argparse.Namespace) -> int:
    m = LINK.fullmatch(a.job)
    if not m:
        raise Refused(f"{a.job!r} is not <login>:<job-id>")
    placed(m.group(1))

    def link(doc: dict | None) -> dict:
        if doc is None:
            raise Refused(f"no plan {a.plan!r}")
        step = next((s for s in doc["steps"] if s["id"] == a.step), None)
        if step is None:
            raise Refused(f"{a.plan} has no step {a.step}")
        if step.get("job") and step["job"] != a.job and not a.replace:
            raise Refused(f"{a.step} is linked to {step['job']}; --replace to link {a.job} instead")
        step["job"] = a.job
        return doc
    identity.update_plan(a.plan, link)
    print(f"{a.step} -> {a.job}")
    return 0


# Markup, and the characters a renderer needs to make a link of bare text (GFM autolinks http://, www. and
# user@host) or to strike it through (~); each is ASCII punctuation, so a backslash before it renders as itself.
# The pipe is left to the cell join, which escapes it once.
_MD_META = re.compile(r"([\\`*_\[\]<>&:@.~])")


def md_text(value: Any) -> str:
    """Text from another account for a markdown cell: one line, and its markup
    characters escaped, so a reason never renders as a link, a tag, a strike-through or a table."""
    return _MD_META.sub(r"\\\1", printable(value))


def render_step(s: dict) -> str:
    where = f"{s['owner']}" + (f" -> {s['job']}" if s.get("job") else "")
    tail = f"  ({printable(s['reason'])})" if s.get("reason") else ""
    return f"  {s['id']:<5}{s['state']:<10}{where:<34}{s['title']}{tail}"


def cmd_show(a: argparse.Namespace, reader: Any) -> int:
    if a.plan is None:
        plans = identity.list_plans()
        if a.json:
            print(json.dumps({"plans": [{k: p[k] for k in ("id", "title", "created_at", "status")} | {"steps": len(p["steps"])}
                                        for p in plans]}, ensure_ascii=False, indent=2))
        else:
            for p in plans:
                print(f"{p['id']:<24}{p['status']:<8}{len(p['steps'])} steps  {p['title']}")
            if not plans:
                print("no plans")
        return 0
    plan = get_plan(a.plan)
    steps = derive(plan, reader)
    if a.json:
        print(json.dumps({**plan, "steps": steps, "read_at": identity.now_iso()}, ensure_ascii=False, indent=2))
        return 0
    print(f"plan {plan['id']}  [{plan['status']}]  {plan['title']}")
    for s in steps:
        print(render_step(s))
    return 0


def cmd_export(a: argparse.Namespace, reader: Any) -> int:
    plan = get_plan(a.plan)
    steps = derive(plan, reader)
    lines = [f"# Plan {plan['id']}: {plan['title']}", "",
             f"Status: {plan['status']}. Created {plan['created_at']}. States read {identity.now_iso()}.", "",
             "| Step | Title | Owner | Job | After | Est. days | State |", "|---|---|---|---|---|---|---|"]
    for s in steps:
        cells = [s["id"], s["title"], s["owner"], s.get("job") or "", ", ".join(s.get("depends_on", [])),
                 str(s.get("est_days", "")), s["state"] + (f" ({md_text(s['reason'])})" if s.get("reason") else "")]
        lines.append("| " + " | ".join(printable(c).replace("|", "\\|") for c in cells) + " |")
    notes = [f"- {s['id']}: {s['note']}" for s in steps if s.get("note")]
    if notes:
        lines += ["", "Notes:", *notes]
    print("\n".join(lines))
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fabric-plan", description="the coordinator's plans (agent-fabric ADR-047)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="a new plan")
    p.add_argument("id")
    p.add_argument("title")
    st = sub.add_parser("step", help="steps of a plan").add_subparsers(dest="step_cmd", required=True)
    s = st.add_parser("add", help="add a step")
    s.add_argument("plan")
    s.add_argument("title")
    s.add_argument("--owner", required=True, metavar="LOGIN")
    s.add_argument("--after", metavar="s1,s2")
    s.add_argument("--est-days", metavar="N")
    s.add_argument("--note")
    ln = sub.add_parser("link", help="link a step to the job queued for it")
    ln.add_argument("plan")
    ln.add_argument("step")
    ln.add_argument("job", metavar="LOGIN:JOB")
    ln.add_argument("--replace", action="store_true")
    sh = sub.add_parser("show", help="the plans, or one plan with its steps' states")
    sh.add_argument("plan", nargs="?")
    sh.add_argument("--json", action="store_true")
    ex = sub.add_parser("export", help="a plan as markdown, for a record or a pull request")
    ex.add_argument("plan")
    return ap


def main(argv: list[str] | None = None, reader: Any = None) -> int:
    a = parser().parse_args(argv)
    try:
        role = (identity.read_binding() or {}).get("role")
        if role != ROLE:
            raise Refused(f"plans are kept by the role {ROLE}; this session is bound to {role or 'no role'}")
        for name in ("plan", "id"):
            if getattr(a, name, None) is not None and not identity.PLAN_ID.fullmatch(getattr(a, name)):
                raise Refused(f"{getattr(a, name)!r} is not a plan id (lowercase letters, digits and dashes, at most 63)")
        reader = reader or FleetReader()
        if a.cmd == "new":
            return cmd_new(a)
        if a.cmd == "step":
            return cmd_step_add(a)
        if a.cmd == "link":
            return cmd_link(a)
        if a.cmd == "show":
            return cmd_show(a, reader)
        return cmd_export(a, reader)
    except Refused as e:
        print(f"fabric-plan: {e}", file=sys.stderr)
        return 1
    except SystemExit as e:                  # identity's refusals: a state file it will not read
        if isinstance(e.code, str):
            print(f"fabric-plan: {e.code}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
