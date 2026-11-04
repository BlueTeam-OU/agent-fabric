"""tools/fabric/memory_flagrun.py (fabric-memory-check --flags; assemble.py --flags) — the flag phase of the drain
(agent-fabric ADR-050 rules 3, 5, 6 and 8): from the drained corpora and the drain report to one REQUEST per agent
that owns the flagged sections. memory_flags decides and renders; this reads the world it is given, sends, and
remembers what it sent.

CONTRACT
  runs      on the coordinator's account, after assemble (`assemble.py --flags`), or alone between drains
            (`fabric-memory-check --flags [--project ID] [--send]`). One runner at a time: the ledger is appended
            without a lock.
  input     memory_check's rows for the fabric's memory/ (label `agent-fabric`) and the project's
            .agent-fabric/memory/ (label: the project), the report's `memory_marks`, `review_horizons` and
            `section_writers` (layout.project_report_path). No report is a refusal: who wrote a section is how it
            is routed.
  fleet     `fabric-ctl all presence --json` gives each account's role (online or not) and whether a session is
            running; `fabric-ctl all jobs --json` the REQUESTs still open on each. An account that did not answer
            for its jobs counts as having the REQUEST open: unknown is never "send again". A fleet that cannot be
            read is a refusal, not a guess at who holds a role.
  dry run   the default: the plan is printed, nothing is sent, written or asked of a model. `--send` sends.
  send      one REQUEST per owning agent, TO that login (never a role), by `gzcoord-send`. Exit 0 sent and the
            flags are in the ledger at once; exit 4 the agent has no session: not sent, not recorded, tried again
            by the next run; any other exit is reported and the run exits 1. The other agents are still tried.
  hints     with `--send`, a maybe-stale flag about to be sent gets memory_hint.attach_hints' guess, rendered as
            a model's guess. No CLI or a failed call: no hint and one line, the REQUESTs go anyway.
  ledger    `<agent state dir>/memory-flags.jsonl`: one line per flag sent, {key, to, message_id, at (UTC)}. A flag
            whose last REQUEST is an open job of the same agent is not sent again; neither is one sent less than
            INTAKE_GRACE_S ago, since an agent's session turns the REQUEST into a job only when it reads it. A job
            that is already done is not told from one never made (fabric-ctl lists open jobs only), so the grace
            also holds a flag whose job finished: it is sent again once the grace has passed and it still stands.
  silent    an account that did not answer the presence or jobs query is unknown, never absent: a flag whose last
            writer or last REQUEST addressee is silent is held, listed, and sent by none; a role no answering account
            holds is reported "no holder" with the number of silent accounts, any of which may hold it.
  report    `flags: N routed to M agents (hints: k, none: j)` and the per-agent list on stdout; from assemble also
            the report's `memory_flags`. Nothing in a slice, the corpus or the tree changes by a hint or a send.
  exit      0; 1 a send failed or the phase could not run after a drain; 2 usage, as the check's.
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Callable

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "runtime"))
import identity  # noqa: E402
import layout  # noqa: E402
import memory_check  # noqa: E402
import memory_flags  # noqa: E402
import memory_hint  # noqa: E402
import roots  # noqa: E402
from gzcoord import gzmsg  # noqa: E402

CTL_TIMEOUT_S = 120
SEND_TIMEOUT_S = 180
NO_SESSION_EXIT = 4        # gzcoord-send: the addressee has no session running; nothing was sent
INTAKE_GRACE_S = 7 * 86400
LEDGER_NAME = "memory-flags.jsonl"
STAMP = "%Y-%m-%dT%H:%M:%SZ"


class FlagRunError(Exception):
    """The phase cannot run: one line, the fact that fixes it."""


@dataclass
class Corpus:
    prefix: str           # "f" or "p": memory_flags.REPORT_PREFIX's key, and the id letter of a mark
    label: str
    root: str
    tree: str
    own_project: str | None


@dataclass
class Fleet:
    holders: dict[str, list[str]]           # role -> addresses, running or not
    running: set[str]
    open_jobs: dict[str, "set[str] | None"]  # address -> MESSAGE-IDs of its open REQUEST jobs; None: it did not answer
    silent: set[str]                        # accounts whose presence did not answer: their role is unknown


def corpora_of(project: str, fabric_root: str, working_copy: str | None) -> list[Corpus]:
    out = [Corpus("f", layout.FABRIC_PROJECT_ID, roots.memory_dir(root=fabric_root), fabric_root, layout.FABRIC_PROJECT_ID)]
    if working_copy:
        # The fabric's own project has both corpora in one checkout: one label each, or the hints' sources and the
        # flags' keys of the two would be one.
        label = project if project != layout.FABRIC_PROJECT_ID else f"{project}/{layout.PROJECT_DIRNAME}"
        out.append(Corpus("p", label, os.path.join(working_copy, layout.PROJECT_MEMORY_SUBDIR), working_copy, None))
    return [c for c in out if os.path.isdir(c.root)]


def gather(corpora: list[Corpus], report: dict, history: "memory_check.History | None" = None) -> tuple[list[memory_flags.Flag], dict]:
    """(the flags, the `sources` memory_hint reads) of the checks, the marks and the horizons."""
    history = history or memory_check.History()
    flags: list[memory_flags.Flag] = []
    sources: dict[str, dict] = {}
    for c in corpora:
        rows = memory_check.check(c.root, c.tree, project=c.own_project, history=history)
        flags += memory_flags.flags_from_rows(c.label, rows, memory_flags.REPORT_PREFIX[c.prefix])
        trees = [c.tree]
        for sl in memory_check.read_corpus(c.root):
            for t in memory_check.origin_trees(sl.get("meta") or {}, c.tree, c.own_project)[0]:
                if t not in trees:
                    trees.append(t)
        sources[c.label] = {"corpus": c.root, "trees": trees, "tree": c.tree, "own_project": c.own_project}
    by_prefix = {c.prefix: c.root for c in corpora}
    labels = {c.prefix: c.label for c in corpora}
    memory_flags.flags_from_marks(report.get("memory_marks") or {}, by_prefix, labels, into=flags)
    memory_flags.flags_from_horizons(report.get("review_horizons") or {}, by_prefix, labels, into=flags)
    return flags, sources


def run_ctl(argv: list[str], timeout: float = CTL_TIMEOUT_S) -> list[dict]:
    """The JSON lines `fabric-ctl all <op> --json` prints, one per account."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout, check=False, errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        raise FlagRunError(f"{os.path.basename(argv[0])} {argv[-2]} could not run ({type(e).__name__})") from None
    rows = []
    for line in r.stdout.splitlines():
        try:
            row = json.loads(line)
        except (ValueError, RecursionError):      # a line nested past the parser's depth is as unreadable as one that is not JSON
            continue
        if isinstance(row, dict) and isinstance(row.get("account"), str) and isinstance(row.get("host"), str):
            rows.append(row)
    if not rows:
        raise FlagRunError(f"fabric-ctl all {argv[-2]} gave no account (exit {r.returncode}): who holds a role is not guessed")
    return rows


def job_objects(jobs: Any) -> bool:
    """Whether `jobs` is what an account that answered gives: a list of job objects, each with the fields open_message_ids
    reads in their types. An account on older code, or one whose answer carries an error text in the list, is unknown."""
    return isinstance(jobs, list) and all(
        isinstance(j, dict) and isinstance(j.get("state"), str) and isinstance(j.get("title", ""), str)
        and (j.get("source") is None or (isinstance(j["source"], dict) and isinstance(j["source"].get("message_id", ""), (str, type(None)))))
        for j in jobs)


def read_fleet(ctl: list[str], run: Callable[..., list[dict]] = run_ctl) -> Fleet:
    holders: dict[str, list[str]] = {}
    running: set[str] = set()
    silent: set[str] = set()
    for row in run([*ctl, "all", "presence", "--json"]):
        p = row.get("presence")
        address = f"{row['host']}/{row['account']}"
        if row.get("status") != "ok" or not isinstance(p, dict) or p.get("status") != "ok":
            silent.add(address)
            continue
        if not isinstance(p.get("role"), str) or not p["role"]:
            continue
        holders.setdefault(p["role"], []).append(address)
        if p.get("online") is True:
            running.add(address)
    open_jobs: dict[str, "set[str] | None"] = {}
    for row in run([*ctl, "all", "jobs", "--json"]):
        j = row.get("jobs")
        ok = row.get("status") == "ok" and isinstance(j, dict) and j.get("status") == "ok" and job_objects(j.get("jobs"))
        open_jobs[f"{row['host']}/{row['account']}"] = memory_flags.open_message_ids(j) if ok else None
    return Fleet(holders, running, open_jobs, silent)


def seconds_of(stamp: str) -> float | None:
    """Epoch seconds of a ledger's UTC stamp."""
    try:
        return calendar.timegm(time.strptime(stamp, STAMP))
    except ValueError:
        return None


def is_open_in(fleet: Fleet, sent: dict[str, dict], now: float) -> Callable[[str, str], bool]:
    """Whether a REQUEST stands: an open job of the agent, a job it has not been shown to turn into yet, or an
    agent that did not say. Only a job gone from a list that was read, past the grace, lets a flag go again."""
    at = {v["message_id"]: v["at"] for v in sent.values()}

    def is_open(address: str, message_id: str) -> bool:
        jobs = fleet.open_jobs.get(address)
        if jobs is None or message_id in jobs:
            return True
        sent_at = seconds_of(at.get(message_id, ""))
        return sent_at is not None and now - sent_at < INTAKE_GRACE_S
    return is_open


def ledger_path() -> str:
    return os.path.join(identity.agent_state_dir(), LEDGER_NAME)


def send_request(send: list[str], text: str, timeout: float = SEND_TIMEOUT_S) -> tuple[int, str]:
    """(gzcoord-send's exit status, its last stderr line). The message goes through a private file, never argv."""
    with tempfile.TemporaryDirectory(prefix="memory-flags.", dir=_scratch_base()) as d:
        path = os.path.join(d, "request.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        try:
            r = subprocess.run([*send, path], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout, check=False, errors="replace")
        except subprocess.TimeoutExpired:
            return 124, f"gzcoord-send did not answer within {timeout:g} s"
        except OSError as e:
            return 127, f"gzcoord-send could not run ({e.strerror or e})"
    # gzcoord-send's warnings and presence lines come before the refusal itself.
    said = (r.stderr or r.stdout or "").strip().splitlines()
    return r.returncode, memory_flags.one_line(said[-1] if said else "", 200)


def _scratch_base() -> str | None:
    try:
        base = identity.agent_state_dir()
    except Exception:  # noqa: BLE001 — no identity (a test, a bare shell): the temporary directory
        return None
    return base if os.path.isdir(base) else None


@dataclass
class Outcome:
    plan: memory_flags.Plan
    hints: dict
    sent: dict[str, str]            # address -> MESSAGE-ID
    unsent: dict[str, str]          # address -> why not
    held: list[tuple[memory_flags.Flag, str]]   # (flag, why): its owner is unknown, so it is sent by none
    failed: bool = False


def execute(flags: list[memory_flags.Flag], sources: dict, writers: dict, fleet: Fleet, *, ledger: str, sender: str, sender_role: str,
            project: str, send: list[str] | None, now: float | None = None, run_hint: Callable[..., Any] = subprocess.run,
            hint_argv: list[str] | None = None, hint_timeout: float = memory_hint.HINT_TIMEOUT_S,
            say: Callable[[str], None] = lambda m: print(m, file=sys.stderr), history: "memory_check.History | None" = None,
            taxonomy: "gzmsg.Taxonomy | None" = None) -> Outcome:
    """Plan, and when `send` (the gzcoord-send command) is given: hint, send, record. Without it nothing is asked of
    a model, sent or written."""
    now = time.time() if now is None else now
    sent = memory_flags.load_ledger(ledger)
    silent_logins = {memory_flags.login_of(a) for a in fleet.silent}
    held: list[tuple[memory_flags.Flag, str]] = []
    routable = []
    for f in flags:
        writer = (writers.get(f.report_key) or {}).get("agent")
        prior = sent.get(f.key, {}).get("to")
        if writer in silent_logins or (prior and (prior in fleet.silent or fleet.open_jobs.get(prior, ()) is None)):
            held.append((f, "the account that last wrote it or was last asked about it did not answer"))
        else:
            routable.append(f)
    plan = memory_flags.plan(routable, writers, fleet.holders, fleet.running, sent, is_open_in(fleet, sent, now))
    if fleet.silent:
        plan.unrouted = [(f, why + f" (any of the {len(fleet.silent)} account(s) that did not answer may hold it)" if why.endswith("has no holder") else why)
                         for f, why in plan.unrouted]
    out = Outcome(plan, {"eligible": 0, "hinted": 0, "skipped": 0, "failed": None}, {}, {}, held)
    if send is None:
        return out
    queued = [f for fl in plan.requests.values() for f in fl]
    out.hints = memory_hint.attach_hints(queued, sources, run=run_hint, say=say, history=history, argv=hint_argv, timeout=hint_timeout)
    at = time.strftime(STAMP, time.gmtime(now))
    for address in sorted(plan.requests):
        batch = plan.requests[address]
        try:
            text, mid = memory_flags.render_request(address, batch, sender, sender_role, project, taxonomy=taxonomy)
            rc, why = send_request(send, text)
        except (ValueError, OSError) as e:      # one agent's REQUEST that cannot be made does not stop the others
            out.unsent[address] = f"{type(e).__name__}: {memory_flags.one_line(e, 200)}"
            out.failed = True
            continue
        if rc == 0:
            try:
                memory_flags.append_ledger(ledger, batch, address, mid, at)
            except OSError as e:
                # It went out: the next run sends these flags again, and this is how that duplicate is recognised.
                out.unsent[address] = f"sent as {mid} but not recorded in the ledger ({e.strerror or e}); the next run sends it again"
                out.failed = True
            else:
                out.sent[address] = mid
            continue
        if rc == NO_SESSION_EXIT:
            out.unsent[address] = "no session running; tried again by the next run"
        else:
            # Exit 3 includes a post whose outcome is unknown: it may have been delivered, and the next run sends again.
            out.unsent[address] = f"gzcoord-send exited {rc}" + (f": {why}" if why else "") + (" (it may have been delivered)" if rc == 3 else "")
            out.failed = True
    return out


def summary(o: Outcome, dry: bool) -> dict:
    routed = sum(len(v) for v in o.plan.requests.values())
    return {"routed": routed, "agents": {a: len(v) for a, v in sorted(o.plan.requests.items())},
            "hints": o.hints["hinted"], "none": o.hints["eligible"] - o.hints["hinted"],
            "open": len(o.plan.open), "deferred": len(o.plan.deferred),
            "held": [{"flag": f.key, "why": why} for f, why in o.held],
            "unrouted": [{"flag": f.key, "why": why} for f, why in o.plan.unrouted],
            "sent": sorted(o.sent), "unsent": o.unsent, "hint_failed": o.hints["failed"], "dry_run": dry}


def lines(o: Outcome, dry: bool) -> list[str]:
    s = summary(o, dry)
    out = [f"flags: {s['routed']} routed to {len(s['agents'])} agents (hints: {s['hints']}, none: {s['none']})"]
    for address, n in s["agents"].items():
        how = sorted({o.plan.how[f.key] for f in o.plan.requests[address]})
        state = "sent" if address in o.sent else (f"not sent — {o.unsent[address]}" if address in o.unsent else "")
        out.append(f"  {address}: {n} flag(s) [{', '.join(how)}]" + (f" {state}" if state else ""))
    if s["open"]:
        out.append(f"  open: {s['open']} flag(s) whose REQUEST is still open, not sent again")
    if s["deferred"]:
        out.append(f"  deferred: {s['deferred']} flag(s) past {memory_flags.MAX_FLAGS} for one agent, for the next run")
    for item in s["held"]:
        out.append(f"  held: {item['flag']} — {item['why']}")
    for item in s["unrouted"]:
        out.append(f"  unrouted: {item['flag']} — {item['why']}")
    if dry:
        out.append("dry run: nothing sent, no model asked (--send sends)")
    return out


def read_report(project: str, where: Any = layout) -> dict:
    try:
        path = where.project_report_path(project)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except LookupError as e:        # layout: no working copy known for the project
        raise FlagRunError(str(e)) from None
    except (OSError, ValueError) as e:
        raise FlagRunError(f"no drain report for {project} ({type(e).__name__}): run the drain first, who wrote a section is how it is routed") from None
    if not isinstance(doc, dict):
        raise FlagRunError(f"{path} is not a drain report")
    return doc


def program(env: str, name: str, where: Any = layout) -> list[str]:
    return [os.environ.get(env) or os.path.join(where.FABRIC_ROOT, "bin", name)]


def phase(project: str, *, send: bool, record_in_report: bool = False, where: Any = layout, **inject: Any) -> int:
    """The whole phase for `project`, printing its lines. `where` is the layout module that knows the fabric root and
    the project's working copy: the assembler holds its own copy of it, told them by its arguments. `inject` replaces
    the clock, the model call and the history, for a test."""
    try:
        report = read_report(project, where)
        corpora = corpora_of(project, where.FABRIC_ROOT, where.working_copy_for(project))
        flags, sources = gather(corpora, report, inject.get("history"))
        fleet = read_fleet(program("AGENT_FABRIC_CTL", "fabric-ctl", where))
        me = gzmsg.whoami()
        if send and not me.get("role"):
            raise FlagRunError("this session is bound to no role: the REQUESTs would carry none")
        path = gzmsg.find_taxonomy()
        o = execute(flags, sources, report.get("section_writers") or {}, fleet, ledger=ledger_path(),
                    sender=f"{me['host']}/{me['agent']}", sender_role=me.get("role") or "", project=project,
                    send=program("AGENT_FABRIC_GZCOORD_SEND", "gzcoord-send", where) if send else None,
                    taxonomy=gzmsg.load_taxonomy(path) if path else None,
                    **{k: v for k, v in inject.items() if k in ("now", "run_hint", "hint_argv", "hint_timeout", "say")})
    except (FlagRunError, memory_check.Refused, ValueError, OSError) as e:
        print(f"memory flags: {e}", file=sys.stderr)
        return 1
    for line in lines(o, not send):
        print(line)
    for address, why in o.unsent.items():
        print(f"memory flags: {address} not sent — {why}", file=sys.stderr)
    if record_in_report:
        write_summary(project, summary(o, not send), where)
    return 1 if o.failed else 0


def write_summary(project: str, doc: dict, where: Any = layout) -> None:
    """The report with `memory_flags` replaced, whole and by rename."""
    path = where.project_report_path(project)
    report = read_report(project, where)
    report["memory_flags"] = doc
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="fabric-memory-check --flags", add_help=False)
    ap.add_argument("--flags", action="store_true")
    ap.add_argument("--project", default=layout.FABRIC_PROJECT_ID)
    ap.add_argument("--send", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        print("fabric-memory-check: usage: --flags [--project ID] [--send]", file=sys.stderr)
        return 2
    return phase(a.project, send=a.send)
