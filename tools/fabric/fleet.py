#!/usr/bin/env python3
"""tools/fabric/fleet.py — the fleet's data on demand (Fleet Deck, Stage 1):
one record per placed agent, assembled from what the control plane already
answers, when a view asks, never in the background.

    fetch(sections, agent=None, max_age=None) -> dict      the library
    bin/fabric-fleet --json [--agent L] [--section a,b] [--max-age S] [--days N]

CONTRACT
  stdout    one JSON object: {"schema": 1, "at", "sections": [names read],
            "agents": [{"login", "host", "address", "kind", "sections":
            {name: record}}], plus one top-level record per fleet section
            asked (FLEET SECTIONS); "cache" appears only when the cache could
            not be used, with why. A record is {"status": "ok", "src", "at",
            "data"}, {"status": "failed", "src", "at", "why"} or a stale one
            (STALE): `src` says
            where the value was read (proc-local, hostexec, op:<name>,
            pr-gate), `at` when. The granularity is the section record, not
            each number in `data`.
  Every placed agent has a record for every agent section asked (and the
  document one for every fleet section, below): a source that
  failed, answered without the agent, or timed out is a failed record with
  its cause, never a crash and never an absent agent.
  stderr    one `fabric-fleet: ` line on a refusal.
  exit      0 an answer was printed (failed records included: they are the
            answer); 2 usage, an unknown agent, an unreadable registry.

STALE  A section whose fresh read failed for an agent, whose last good value
  is no older than its class's stale window, is not "failed": it is
  {"status": "stale", "src", "at" (when the value was read), "age_s", "why"
  (the fresh read's failure), "data" (the last good value)}. Past the window
  the record is failed, as before; a failure is still never cached, and a
  failed refresh leaves the last good entry where it was. A slow account
  reads as old, not unknown.

TIMEOUTS  each cost class has its own bound on the program that reads it:
  `ctl` is fabric-ctl's wait for the control agents' replies, `call` the
  bound over the whole program (its relay reads can stall past the wait).
  class  ctl  call  stale window
  C0       8    40       60 s
  C1      20    60      600 s
  C2      30   120     1800 s
  C3      60   180     7200 s

FLEET SECTIONS  `plans` and `prs_unplaced` are about the fleet, not an agent:
  each is one record, {status, src, at, data|why} (stale as above), under
  its own name at the top of the document and in no agent's "sections".
  plans.data = {login, plans: [{id, title, status, created_at, steps: [{id,
  title, owner, depends_on, job, state, reason, started, finished,
  times_why, est_days}]}]}: the plans of the login that runs this (the
  coordinator's files; another login has none), steps in the plan's order,
  `state` what fabric-plan says (planned, waiting, unknown, or the job's),
  `started` the first time the job was active and `finished` the last time
  it was done, dropped or delivered, from the job's log as the owner's full
  list gives it through the executor (null where it never was; null with
  `times_why` where the list could not be read: unknown, not "never").
  prs_unplaced.data = {prs: [...rows of prs...], fetch_ok, prs_ok, base,
  gate_ok}: the PRs whose owner is no placed account. Asking for `prs`
  adds it; `plans` is named only. "sections" lists every name read: an
  agent section is a key of each agent's "sections", a fleet one a key of
  the document.
  prs rows (per agent and unplaced): pr, number, repo (<org>/<name> of this
  checkout's origin; the other projects' repositories are not read), branch,
  ahead, last_commit, paths_total from pr-gate --in-flight, and fabric-pr
  gate --json's own title, head, work_commits, fix_commits, checks, review,
  unresolved_threads, armed, queue_position, draft, verdict; the gate fields
  are null with `gate_ok` false and `gate_why` when the gate could not be
  read; `gate_found` says whether the PR was at the gate (null when the gate
  was not read). The in-flight row and the gate row of a PR join by number,
  or by branch where the listing had no number (a number the gate lacks is
  a PR not at the gate: gate_found false). closed_jobs.data adds done_total (state done only) to closed_total.

ATTENTION  `attention` (Fleet Deck's "needs you" views) is told from the `states` and `jobs` records of the same
  fetch, which a fetch that names it reads and shows too (like prs_unplaced with prs). It has no source of its
  own and no cache entry: it is as fresh as its inputs. data = {level, reason, since, blocked, pending}:
    level    needs_input  the account's most-wanting session waits on a PERSON (session-state's `blocked`:
                          a permission prompt, an input or elicitation dialog); wins over waiting
             waiting      an open job is blocked, on something that is not a person
             none         neither (no session, or only working and idle ones; no blocked job)
    reason   null for needs_input (the hook records that a session is blocked, not why; a later step),
             else the most recently updated blocked job's `blocked_on`: the agent's own words as a line,
             control characters and white space collapsed, cut at 80 characters, content NOT scrubbed
             (it can name a path): a view shows it as text only
    since    needs_input: that session's `since`; waiting: that job's `updated`; else null; null too where unknown
    blocked, pending  the numbers of open jobs in state blocked and queued
  `at` is the oldest of the two inputs' read times. Stale when an input is (data from the last good values,
  `age_s` the oldest, `why` both); failed, never level `none`, when an input failed, when the account's state
  is `unknown` (no fresh state record), or when the jobs answer is not a list. A human login has no control
  agent (ADR-044): its attention is failed with that why. Agreed with the views' author (rust-ui-dev-01).
  Not here, for want of a source on the control plane: context_pct, output activity, needs_input's reason.

SECTIONS, by cost class (the TTL is how long a cached answer is reused)
  C0 proc 5 s · states 5 s · presence 10 s
  C1 jobs 30 s · usage 60 s · host 60 s · fabric 60 s · attention (derived: no TTL, no cache of its own)
  C2 prs 120 s · prs_unplaced 120 s · plans 120 s · closed_jobs 300 s · accounts 120 s
  C3 tokens 600 s · disk 600 s     only when named: they walk disks/logs
  A section's `sources` are tried in order and the first that answers wins;
  Stage 2's control-plane ops replace a source here without changing the
  record's shape. `closed_jobs` is a Stage 1 bridge: the jobs files read
  on each host through the executor, read-only, until an op serves them.

CACHE  $XDG_RUNTIME_DIR/fabric-fleet/<section>.json (tokens-<days>.json: the
  window is part of the question), 0600 in a 0700
  directory, replaced atomically; a fresh entry is reused across processes.
  Entries are per agent, so `--agent L` never makes the rest look fresh.
  Only successes are cached: a failure is asked again, since a cached
  failure would outlive its cause. Two processes refreshing one section at
  once both write whole files and the later one wins; the loser's entries
  are re-read next time. No XDG_RUNTIME_DIR means no cache, not /tmp.

SIDE EFFECT  `prs` and `prs_unplaced` (a default section, riding with prs)
  run pr-gate --in-flight, which does `git fetch --prune origin` in this
  checkout, and `fabric-pr gate --all --json`, which reads GitHub for every
  open PR, on each call that has no fresh cached record for every agent
  asked (so always with --max-age 0 or without a cache); once per fetch for
  both sections.

NEVER read: /proc/*/environ, cmdline, transcripts (fleet_proc.py).
"""
from __future__ import annotations

import concurrent.futures
import dataclasses
import datetime as dt
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import roots  # noqa: E402
import fleet_proc  # noqa: E402

SCHEMA = 1
CACHE_VERSION = 2   # 2: prs rows carry the gate's fields, closed_jobs done_total
# class -> (ctl wait, whole-program bound, stale window), in seconds. The
# program bound is over the wait because a control agent's relay read can
# stall past it; pr-gate (C2) fetches origin and lists PRs, which is what
# 120 s is for.
COST_CLASSES = {"C0": (8, 40, 60), "C1": (20, 60, 600), "C2": (30, 120, 1800), "C3": (60, 180, 7200)}
CTL_TIMEOUT_S, CALL_TIMEOUT_S = 20, 90   # a Ctx made by hand, outside any section: the bounds before the classes
CLOSED_CAP = 20
HOST_RUN_WORKERS = 8
DEFAULT_PYTHON = "/usr/local/bin/fabric-python"


class FleetError(Exception):
    """A usage error or an unreadable registry: the CLI's exit 2."""


class SourceError(Exception):
    """A source could not answer; the message is the why a record carries."""


@dataclass(frozen=True)
class Agent:
    login: str
    host: str
    kind: str

    @property
    def address(self) -> str:
        return f"{self.host}/{self.login}"


# What a fleet-scope section is asked for and cached under: one pseudo-agent,
# so the same read, cache and stale rules serve it.
FLEET = Agent("*", "", "fleet")


@dataclass
class Failed:
    """One agent a source answered for, but with a failure of its own."""
    why: str


class _Declined:
    """A source's answer for an agent that is not its to answer (another
    host's /proc): not a failure, and not worth a word in the why."""


DECLINED = _Declined()
HUMAN = "human login: no control agent (ADR-044)"


@dataclass
class Ctx:
    root: str
    ssh_hosts: frozenset[str]
    run: Callable[..., subprocess.CompletedProcess]
    clock: Callable[[], float] = time.time
    here: str = field(default_factory=fleet_proc.roots_host)
    days: int | None = None
    sample: Callable[..., dict] = fleet_proc.collect
    ctl_s: float = CTL_TIMEOUT_S      # set per section by read_section: its cost class's
    call_s: float = CALL_TIMEOUT_S
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    memo: dict = field(default_factory=dict)         # what two sections of one fetch read once between them
    memo_lock: threading.Lock = field(default_factory=threading.Lock)

    def once(self, key: str, read: Callable[[], Any]) -> Any:
        """`read()` once per fetch, its value or its exception given to every
        section that asks: prs and prs_unplaced read the same gate rows."""
        with self.memo_lock:
            slot = self.memo.setdefault(key, [threading.Lock(), None])
        with slot[0]:
            if slot[1] is None:
                try:
                    slot[1] = (True, read())
                except Exception as e:  # noqa: BLE001 — handed on to each asker, who judges it
                    slot[1] = (False, e)
        ok, value = slot[1]
        if not ok:
            raise value
        return value


@dataclass(frozen=True)
class Source:
    label: str
    read: Callable[[Ctx, list[Agent]], dict[str, Any]]   # login -> data | Failed


@dataclass(frozen=True)
class Section:
    name: str
    cost: str
    ttl: int
    sources: tuple[Source, ...]
    scope: str = "agent"        # "fleet": one record for the whole fleet, under its name at the top of the document
    derives: tuple[str, ...] = ()   # computed from these sections' records of the same fetch: no source, no cache of its own

    @property
    def ctl_s(self) -> float:
        return COST_CLASSES[self.cost][0]

    @property
    def call_s(self) -> float:
        return COST_CLASSES[self.cost][1]

    @property
    def stale_s(self) -> float:
        return COST_CLASSES[self.cost][2]


# ── running things ──────────────────────────────────────────────────

def run_program(argv: list[str], *, timeout: float, cwd: str | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """An argument list, a timeout, stdin closed: the callers read the result.
    Its own process group, killed whole on a timeout: pr-gate's git and gh,
    and the executor's ssh, are grandchildren that `subprocess.run`'s kill
    of the direct child would leave running."""
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd, env=env,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()   # the group is already gone; the leader at least. A sudo'd member we may not signal is skipped without error and is what the bounded communicate() below covers
        try:
            p.communicate(timeout=5)   # a survivor holding the pipes must not hold us
        except subprocess.TimeoutExpired:
            pass
        raise
    return subprocess.CompletedProcess(argv, p.returncode, out, err)


def call(ctx: Ctx, argv: list[str], timeout: float | None = None, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Not found, hung and unreadable are told apart in the why; a non-zero
    exit is returned, because fabric-ctl exits non-zero with rows to read.
    The bound is the section's cost class's unless the caller names one."""
    timeout = ctx.call_s if timeout is None else timeout
    try:
        return ctx.run(argv, timeout=timeout, cwd=cwd, env=ctx.env)
    except FileNotFoundError:
        raise SourceError(f"{os.path.basename(argv[0])} not found") from None
    except subprocess.TimeoutExpired:
        raise SourceError(f"{os.path.basename(argv[0])} did not answer within {round(timeout)} s") from None
    except OSError as e:
        raise SourceError(f"{os.path.basename(argv[0])} could not run: {e.strerror or e}") from None


def last_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def json_lines(text: str) -> list[dict]:
    out = []
    for ln in (text or "").splitlines():
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


# ── the sources ─────────────────────────────────────────────────────

CTL_META = {"account", "host", "status", "op", "latency_ms", "agentd"}
# fabric-ctl's row says `ok` whenever the control agent replied at all; the
# op's own result is inside it, under a key that is the op's name except for
# these two (ctl.mjs rows()). An op that threw is {status: 'failed', error}
# there; `read-failed` and `unreadable` are usage's and the tokens reader's
# own words for the same thing. Every other status (partial, none,
# no-records, not-signed-in…) is an answer and stays in `data` for the
# reader to judge.
PAYLOAD_KEY = {"host": "machine", "usage": "usage_status"}
FAILED_STATUSES = frozenset({"failed", "read-failed", "unreadable"})


def op_failure(row: dict, op: str) -> str | None:
    payload = row.get(PAYLOAD_KEY.get(op, op))
    if payload is None:
        return f"the control agent answered without a {op} result (an agentd that does not know the op, or a failed read)"
    status = payload if isinstance(payload, str) else payload.get("status") if isinstance(payload, dict) else None
    if status in FAILED_STATUSES:
        error = payload.get("error") if isinstance(payload, dict) else None
        return f"{op} {status}" + (f": {error}" if error else "")
    return None


def split_humans(agents: list[Agent]) -> tuple[dict[str, Any], list[Agent]]:
    """A human login has no control agent (ADR-044): fabric-ctl drops it from
    `all` and refuses it by name, so it is said here instead of asked."""
    return {a.login: Failed(HUMAN) for a in agents if a.kind == "human"}, [a for a in agents if a.kind != "human"]


def agent_count(ctx: Ctx) -> int:
    return sum(1 for a in load_placements(ctx.root).values() if a.kind != "human")


def ctl_source(op: str) -> Source:
    """`fabric-ctl <target> <op> --json`: one row per account. The data is
    every key the control agent filled in; a row that is not `ok`, or whose
    op result failed or is missing, is that agent's failure."""
    def read(ctx: Ctx, agents: list[Agent]) -> dict[str, Any]:
        out, rest = split_humans(agents)
        if not rest:
            return out
        tail = ["--days", str(ctx.days)] if op == "tokens" and ctx.days is not None else []
        # fabric-ctl takes one target or `all`: one agent asked is that
        # login's call; any larger subset is read as `all`, one relay round
        # trip, and the rows of the others are not used.
        target = rest[0].login if len(rest) == 1 and agent_count(ctx) > 1 else "all"
        p = call(ctx, [os.path.join(ctx.root, "bin", "fabric-ctl"), target, op, "--json", "--timeout", str(ctx.ctl_s), *tail])
        rows = json_lines(p.stdout)
        if not rows:
            raise SourceError(f"fabric-ctl {op}: {last_line(p.stderr) or f'exit {p.returncode}, no rows'}")
        for row in rows:
            login = row.get("account")
            if not isinstance(login, str):
                continue
            if row.get("status") != "ok":
                out[login] = Failed(str(row.get("status") or "no status"))
            elif (why := op_failure(row, op)) is not None:
                out[login] = Failed(why)
            else:
                out[login] = {k: v for k, v in row.items() if k not in CTL_META and v is not None}
        return out
    return Source(f"op:{op}", read)


def states_read(ctx: Ctx, agents: list[Agent]) -> dict[str, Any]:
    # `states` rows are keyed by address, not account, and carry no status.
    out, rest = split_humans(agents)
    if not rest:
        return out
    p = call(ctx, [os.path.join(ctx.root, "bin", "fabric-ctl"), "all", "states", "--json", "--timeout", str(ctx.ctl_s)])
    rows = json_lines(p.stdout)
    if not rows:
        raise SourceError(f"fabric-ctl states: {last_line(p.stderr) or f'exit {p.returncode}, no rows'}")
    for row in rows:
        address = row.get("address")
        if isinstance(address, str) and "/" in address:
            out[address.split("/", 1)[1]] = {k: v for k, v in row.items() if k != "address"}
    return out


def python_of(ctx: Ctx) -> str:
    return ctx.env.get("AGENT_FABRIC_PYTHON") or DEFAULT_PYTHON


def proc_source(label: str, remote: bool) -> Source:
    def read(ctx: Ctx, agents: list[Agent]) -> dict[str, Any]:
        out: dict[str, Any] = {a.login: DECLINED for a in agents}
        by_host: dict[str, list[Agent]] = {}
        for a in agents:
            if (a.host in ctx.ssh_hosts or a.host != ctx.here) == remote:
                by_host.setdefault(a.host, []).append(a)

        def one(host: str, group: list[Agent]) -> dict[str, Any]:
            logins = [a.login for a in group]
            if not remote:
                # In-process: this host's /proc is read by the code that is asking.
                answered = ctx.sample(logins, host=host)["agents"]
            else:
                argv = [os.path.join(ctx.root, "bin", "fabric-host"), host, "run", "--", python_of(ctx),
                        "@fabric/tools/fabric/fleet_proc.py", "--json"]
                for login in logins:
                    argv += ["--login", login]
                try:
                    p = call(ctx, argv)
                    answered = json.loads(p.stdout)["agents"]
                    if not isinstance(answered, dict):
                        raise TypeError("agents is not an object")
                except SourceError as e:
                    return {l: Failed(f"{host}: {e}") for l in logins}
                except (ValueError, KeyError, TypeError):
                    return {l: Failed(f"fleet_proc on {host}: {last_line(p.stderr) or f'exit {p.returncode}, no answer'}") for l in logins}
            return {l: answered[l] if l in answered else Failed(f"{host} has no account {l}") for l in logins}
        # One host at a time would make a hung one cost every other its
        # 60 s; each host's failure is its own agents' and no one else's.
        if by_host:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(by_host)) as pool:
                for answers in pool.map(lambda kv: one(*kv), by_host.items()):
                    out.update(answers)
        return out
    return Source(label, read)


PR_ROW_KEYS = ("pr", "branch", "ahead", "last_commit", "paths_total")
# fabric-pr gate --json's own names, passed through as it prints them.
GATE_KEYS = ("title", "head", "work_commits", "fix_commits", "checks", "review", "unresolved_threads", "armed",
             "queue_position", "draft", "verdict")


def origin_repo(ctx: Ctx) -> str | None:
    """<org>/<name> of this checkout's origin, or None when it cannot be told."""
    try:
        p = call(ctx, ["git", "-C", ctx.root, "remote", "get-url", "origin"], timeout=ctx.ctl_s)
    except SourceError:
        return None
    url = p.stdout.strip() if p.returncode == 0 else ""
    tail = url.removesuffix(".git").replace(":", "/").split("/")
    return "/".join(tail[-2:]) if len(tail) >= 2 and all(tail[-2:]) else None


def pr_rows(ctx: Ctx) -> dict:
    """Every PR of this checkout's repository, once per fetch: pr-gate's
    in-flight rows (what changed, how far ahead) joined with `fabric-pr gate
    --all --json` (where each is at the gate) by PR number. When the gate
    could not be read the rows carry the in-flight fields alone and say so
    (`gate_ok` false, `gate_why`): unknown stays unknown."""
    p = call(ctx, [os.path.join(ctx.root, "bin", "fabric-pr"), "gate", "--in-flight", "--json"], cwd=ctx.root)
    try:
        doc = json.loads(p.stdout)
        rows = doc["rows"]
    except (ValueError, KeyError, TypeError):
        raise SourceError(f"pr-gate: {last_line(p.stderr) or f'exit {p.returncode}, no answer'}") from None
    gate: dict[Any, dict] = {}
    gate_why = None
    try:
        g = call(ctx, [os.path.join(ctx.root, "bin", "fabric-pr"), "gate", "--all", "--json"], cwd=ctx.root)
        listed = json.loads(g.stdout)
        if not isinstance(listed, list):
            raise ValueError("not a list")
        gate = {r.get("number"): r for r in listed if isinstance(r, dict)}
    except SourceError as e:
        gate_why = str(e)
    except ValueError:
        gate_why = f"fabric-pr gate: {last_line(g.stderr) or f'exit {g.returncode}, unreadable output'}"
    repo = origin_repo(ctx)
    by_branch = {r.get("branch"): r for r in gate.values() if r.get("branch")}
    out, seen = [], set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        n = r.get("pr")
        # The number joins; only where the listing could not give one ("none",
        # "unavailable": the PR is newer than its read, or gh failed) does the
        # branch. A number the gate does not list is a PR not at the gate.
        numbered = isinstance(n, int) and not isinstance(n, bool)
        gr = gate.get(n) if numbered else by_branch.get(r.get("branch"))
        if gr is not None:
            seen.add(gr.get("number"))
        out.append({**{k: r.get(k) for k in PR_ROW_KEYS}, "number": gr.get("number") if gr is not None else n if numbered else None,
                    "repo": repo, **{k: (gr or {}).get(k) for k in GATE_KEYS}, "owner": r.get("owner", "") or (gr or {}).get("owner", ""),
                    "gate_found": None if gate_why else gr is not None})
    for n, gr in gate.items():
        if n not in seen:     # an open PR the in-flight listing did not carry: still at its gate
            out.append({**{k: None for k in PR_ROW_KEYS}, "pr": n, "number": n, "branch": gr.get("branch"), "repo": repo,
                        **{k: gr.get(k) for k in GATE_KEYS}, "owner": gr.get("owner", ""), "gate_found": True})
    return {"rows": out, "fetch_ok": doc.get("fetch_ok"), "prs_ok": doc.get("prs_ok"), "base": doc.get("base"),
            "gate_ok": gate_why is None, **({"gate_why": gate_why} if gate_why else {})}


def pr_meta(doc: dict) -> dict:
    # fetch_ok/prs_ok false mean the rows are the last fetch's / "PR unknown":
    # the answer is still the best there is, said as it is.
    return {k: doc[k] for k in ("fetch_ok", "prs_ok", "base", "gate_ok", "gate_why") if k in doc}


def owner_login(row: dict) -> str:
    owner = row.get("owner") or ""
    return owner.split("/", 1)[1] if "/" in owner else ""   # the ref is <host>/<login>/<type>/<what>


def prs_read(ctx: Ctx, agents: list[Agent]) -> dict[str, Any]:
    doc = ctx.once("pr_rows", lambda: pr_rows(ctx))
    mine: dict[str, list[dict]] = {a.login: [] for a in agents}
    for r in doc["rows"]:
        if owner_login(r) in mine:
            mine[owner_login(r)].append({k: v for k, v in r.items() if k != "owner"})
    return {a.login: {"prs": mine[a.login], **pr_meta(doc)} for a in agents}


def prs_unplaced_read(ctx: Ctx, _agents: list[Agent]) -> dict[str, Any]:
    """The PRs whose owner is no placed account (a dependabot branch, a
    stranger's, a ref that does not name one): kept, never dropped."""
    doc = ctx.once("pr_rows", lambda: pr_rows(ctx))
    placed = load_placements(ctx.root)
    rows = [r for r in doc["rows"] if owner_login(r) not in placed]
    return {FLEET.login: {"prs": rows, **pr_meta(doc)}}


# ── plans ───────────────────────────────────────────────────────────

DONE_LIKE = ("done", "dropped", "delivered")


def log_times(row: dict | None) -> tuple[str | None, str | None]:
    """(started, finished) from a job's log: the first time it was active,
    the last time it was done, dropped or delivered; None where it never was."""
    log = row.get("log") if isinstance(row, dict) else None
    if not isinstance(log, list):
        return None, None
    entries = [e for e in log if isinstance(e, dict) and isinstance(e.get("at"), str)]
    started = next((e["at"] for e in entries if e.get("state") == "active"), None)
    finished = next((e["at"] for e in reversed(entries) if e.get("state") in DONE_LIKE), None)
    return started, finished


def plans_read(ctx: Ctx, _agents: list[Agent]) -> dict[str, Any]:
    """The plans of the login that runs this, as fabric-plan shows them (a
    step's state is its job's, read now: ADR-047 rule 3), each step with
    when its job started and finished. The plan files are the running
    coordinator's state, written only through identity.update_plan, and
    this reads them without fabric-plan's role check: the deck is run by
    the operator's login, which holds them. Another login has none, and
    `login` says whose they are.

    The control agent's job list drops each job's log ("the log stays on the
    account"), so the times come from the owner's own list read through the
    executor (`fabric-jobs list --all`, the bridge ADR-046 rule 5 names; the
    record's `src` says so). A list that cannot be read leaves a step's times
    null with `times_why`: unknown, never "it never ran"."""
    import plan as plan_mod       # loads runtime/identity.py: only a fleet-scope section needs it
    reader = plan_mod.FleetReader(run=lambda argv, timeout: ctx.run(argv, timeout=timeout, cwd=None, env=ctx.env),
                                  ctl_s=ctx.ctl_s, call_s=ctx.call_s, root=ctx.root)
    try:
        stored = plan_mod.identity.list_plans()
    except SystemExit as e:         # identity's way of refusing an unreadable plan file
        raise SourceError(str(e)) from None
    jobs_cache: dict = {}           # one list per login for every plan of this read, derive's and ours

    def times(owner_job: str | None, row: dict | None) -> tuple[str | None, str | None, str | None]:
        """(started, finished, why-not) for a step's job."""
        if not owner_job:
            return None, None, None
        if isinstance(row, dict) and isinstance(row.get("log"), list):
            return (*log_times(row), None)
        login, _, job_id = owner_job.partition(":")
        if ("closed", login) not in jobs_cache:      # the key plan.find_job keeps the executor's list under
            try:
                jobs_cache[("closed", login)] = reader.closed_jobs(login)
            except plan_mod.Unreadable as e:
                jobs_cache[("closed", login)] = e
        listed = jobs_cache[("closed", login)]
        if isinstance(listed, Exception):
            return None, None, f"{login}'s full job list: {listed}"[:300]
        found = next((j for j in listed if isinstance(j, dict) and j.get("id") == job_id), None)
        if found is None:
            return None, None, f"{owner_job} is not on {login}'s full job list"
        return (*log_times(found), None)
    plans = []
    for pl in stored:
        rows: dict[str, dict] = {}
        steps = plan_mod.derive(pl, reader, rows, jobs_cache)
        out = []
        for s in steps:
            started, finished, why = times(s.get("job") if s["state"] != "unknown" else None, rows.get(s["id"]))
            out.append({"id": s["id"], "title": s.get("title"), "owner": s.get("owner"), "depends_on": s.get("depends_on", []),
                        "job": s.get("job"), "state": s["state"], "reason": s.get("reason"),
                        "started": started, "finished": finished, "times_why": why, "est_days": s.get("est_days")})
        plans.append({"id": pl.get("id"), "title": pl.get("title"), "status": pl.get("status"), "created_at": pl.get("created_at"),
                      "steps": out})
    return {FLEET.login: {"login": plan_mod.identity.current_agent(), "plans": plans}}


def closed_jobs_read(ctx: Ctx, agents: list[Agent]) -> dict[str, Any]:
    def one(a: Agent) -> Any:
        if a.kind == "human":
            # sudo goes one way, into role accounts (ADR-010 rule 12, ADR-044 §2).
            return Failed("human login: not an account the fleet enters (ADR-010 rule 12)")
        try:
            p = call(ctx, [os.path.join(ctx.root, "bin", "fabric-host"), a.host, "run", "--as", a.login, "--",
                           "fabric-jobs", "list", "--all", "--json"])
            if p.returncode != 0:
                return Failed(f"fabric-jobs on {a.host} as {a.login}: {last_line(p.stderr) or f'exit {p.returncode}'}")
            jobs = json.loads(p.stdout)
            if not isinstance(jobs, list):
                raise ValueError("not a list")
        except SourceError as e:
            return Failed(str(e))
        except ValueError:
            return Failed(f"fabric-jobs on {a.host} as {a.login}: unreadable output")
        closed = sorted((j for j in jobs if isinstance(j, dict) and j.get("state") in ("done", "dropped")),
                        key=lambda j: str(j.get("updated", "")), reverse=True)
        return {"closed_total": len(closed), "done_total": sum(1 for j in closed if j.get("state") == "done"),
                "closed": [{k: j.get(k) for k in ("id", "title", "state", "topic", "project", "updated")} for j in closed[:CLOSED_CAP]]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(HOST_RUN_WORKERS, max(1, len(agents)))) as pool:
        return dict(zip((a.login for a in agents), pool.map(one, agents)))


SECTIONS: dict[str, Section] = {s.name: s for s in (
    Section("proc", "C0", 5, (proc_source("proc-local", remote=False), proc_source("hostexec", remote=True))),
    Section("states", "C0", 5, (Source("op:states", states_read),)),
    Section("presence", "C0", 10, (ctl_source("presence"),)),
    Section("jobs", "C1", 30, (ctl_source("jobs"),)),
    Section("usage", "C1", 60, (ctl_source("usage"),)),
    Section("host", "C1", 60, (ctl_source("host"),)),
    Section("fabric", "C1", 60, (ctl_source("fabric"),)),
    Section("prs", "C2", 120, (Source("pr-gate", prs_read),)),
    Section("prs_unplaced", "C2", 120, (Source("pr-gate", prs_unplaced_read),), scope="fleet"),
    Section("plans", "C2", 120, (Source("fabric-plan+hostexec", plans_read),), scope="fleet"),
    Section("closed_jobs", "C2", 300, (Source("hostexec", closed_jobs_read),)),
    Section("accounts", "C2", 120, (ctl_source("accounts"),)),
    Section("attention", "C1", 0, (), derives=("states", "jobs")),
    Section("tokens", "C3", 600, (ctl_source("tokens"),)),
    Section("disk", "C3", 600, (ctl_source("disk"),)),
)}
# plans is named, not default: it asks the control agents for every linked job.
DEFAULT_SECTIONS = [n for n, s in SECTIONS.items() if s.cost != "C3" and n != "plans"]


# ── the registry ────────────────────────────────────────────────────

def load_registry(root: str) -> dict:
    path = roots.hosts_registry(engine=root)
    try:
        with open(path, encoding="utf-8") as fh:
            reg = json.load(fh)
    except (OSError, ValueError) as e:
        raise FleetError(f"cannot read the hosts registry {path}: {e}") from None
    if not isinstance(reg, dict) or not isinstance(reg.get("placement"), dict):
        raise FleetError(f"the hosts registry {path} has no placement object")
    return reg


def load_placements(root: str) -> dict[str, Agent]:
    reg = load_registry(root)
    kinds = reg.get("kinds") if isinstance(reg.get("kinds"), dict) else {}
    return {login: Agent(login, host, "human" if kinds.get(login) == "human" else "agent")
            for login, host in sorted(reg["placement"].items())}


def ssh_hosts(root: str) -> frozenset[str]:
    hosts = load_registry(root).get("hosts")
    hosts = hosts if isinstance(hosts, dict) else {}
    return frozenset(h for h, v in hosts.items() if isinstance(v, dict) and v.get("ssh") is not None)


# ── the cache ───────────────────────────────────────────────────────

def cache_dir(env: dict[str, str]) -> tuple[str | None, str]:
    """(directory, why-not). Created 0700; refused if it is a link or another
    user's: a cache another account can write is a way to forge the deck."""
    base = env.get("XDG_RUNTIME_DIR")
    if not base:
        return None, "XDG_RUNTIME_DIR is not set"
    path = os.path.join(base, "fabric-fleet")
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
        st = os.lstat(path)
    except OSError as e:
        return None, f"{path}: {e.strerror or e}"
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
        return None, f"{path} is not a private directory of this user"
    return path, ""


def cache_read(directory: str | None, section: str) -> dict[str, dict]:
    if not directory:
        return {}
    try:
        with open(os.path.join(directory, f"{section}.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        if doc["version"] != CACHE_VERSION:
            return {}      # another shape of record (a section's keys changed): a miss, never served as this one's
        entries = doc["agents"]
        return {k: v for k, v in entries.items() if isinstance(v, dict) and isinstance(v.get("t"), (int, float)) and isinstance(v.get("record"), dict)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}   # absent, torn by nothing (writes are atomic) or foreign: a miss


def cache_write(directory: str | None, section: str, entries: dict[str, dict]) -> None:
    if not directory:
        return
    fd, tmp = tempfile.mkstemp(prefix=f".{section}.", suffix=".tmp", dir=directory)   # 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"version": CACHE_VERSION, "agents": entries}, fh)
        os.replace(tmp, os.path.join(directory, f"{section}.json"))
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


# ── attention: what the Fleet Deck's "needs you" views read ─────────

ATTENTION_REASON_MAX = 80
ATTENTION_SRC = "derived:states+jobs"


def attention_text(value: Any) -> str | None:
    """A job's own words, for a board cell: control, format and surrogate characters become spaces
    (a bidi override or a lone surrogate must not reach a view or break the JSON), white space is
    collapsed, and the text is cut at ATTENTION_REASON_MAX characters. The content is not scrubbed: it
    is whatever the agent wrote, and a view shows it as text only."""
    if not isinstance(value, str):
        return None
    flat = " ".join("".join(" " if unicodedata.category(c)[0] == "C" else c for c in value).split())
    if not flat:
        return None
    return flat if len(flat) <= ATTENTION_REASON_MAX else flat[:ATTENTION_REASON_MAX - 1].rstrip() + "…"


def attention_data(states: Any, jobs: Any) -> dict[str, Any] | str:
    """The attention data from the `states` and `jobs` record data of one agent, or the why it cannot be told.
    needs_input: the account's most-wanting session waits on a person (the session-state hook's
    `blocked`); waiting: an open job is blocked, on something that is not a person; none: neither.
    needs_input wins. The account's state read as `unknown` (no fresh record) is not `none`."""
    if not isinstance(states, dict) or states.get("state") not in ("blocked", "working", "idle", "none"):
        why = states.get("why") if isinstance(states, dict) else None
        return f"states: the account's session state is not known ({why or 'no usable state'})"
    # The record's data is the control agent's row without its meta keys: the jobs op's own answer
    # {status, jobs: [...]} sits under `jobs` (ctl rows()), so the list is jobs.jobs.jobs.
    payload = jobs.get("jobs") if isinstance(jobs, dict) else None
    listed = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(listed, list) or not all(isinstance(j, dict) for j in listed):
        return "jobs: the answer carries no list of jobs"
    blocked = [j for j in listed if j.get("state") == "blocked"]
    pending = sum(1 for j in listed if j.get("state") == "queued")
    base = {"blocked": len(blocked), "pending": pending}
    if states["state"] == "blocked":
        since = states.get("since")
        return {"level": "needs_input", "reason": None, "since": since if isinstance(since, str) else None, **base}
    if blocked:
        # The one it most recently began to wait on; the first listed among equals.
        job = max(blocked, key=lambda j: j["updated"] if isinstance(j.get("updated"), str) else "")
        updated = job.get("updated")
        return {"level": "waiting", "reason": attention_text(job.get("blocked_on")),
                "since": updated if isinstance(updated, str) else None, **base}
    return {"level": "none", "reason": None, "since": None, **base}


def attention_record(states: dict, jobs: dict, now: float) -> dict:
    """One agent's attention record from its `states` and `jobs` records: as old as its oldest input
    (`at`), stale when an input is (the last good values, `age_s` the oldest), failed when an input
    failed or cannot be told: never `none` for what is unknown."""
    inputs = {"states": states, "jobs": jobs}
    failed = {k: r.get("why") for k, r in inputs.items() if r.get("status") == "failed"}
    if failed:
        return {"status": "failed", "src": ATTENTION_SRC, "at": stamp(now), "why": "; ".join(f"{k}: {w}" for k, w in failed.items())}
    data = attention_data(states.get("data"), jobs.get("data"))
    if isinstance(data, str):
        return {"status": "failed", "src": ATTENTION_SRC, "at": stamp(now), "why": data}
    ats = [r["at"] for r in inputs.values() if isinstance(r.get("at"), str)]
    rec: dict[str, Any] = {"status": "ok", "src": ATTENTION_SRC, "at": min(ats) if ats else stamp(now), "data": data}
    old = {k: r for k, r in inputs.items() if r.get("status") == "stale"}
    if old:
        rec.update(status="stale", age_s=max(r.get("age_s") or 0 for r in old.values()),
                   why="; ".join(f"{k}: {r.get('why')}" for k, r in old.items()))
    return rec


# A derived section's reader: the answers of this fetch, the agents, the time -> login -> record.
DERIVERS: dict[str, Callable[[dict[str, dict[str, dict]], list[Agent], float], dict[str, dict]]] = {
    "attention": lambda answers, agents, now: {a.login: attention_record(answers["states"][a.login], answers["jobs"][a.login], now)
                                               for a in agents},
}
assert set(DERIVERS) == {n for n, s in SECTIONS.items() if s.derives}, "every derived section has its reader"


# ── fetching ────────────────────────────────────────────────────────

def stamp(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_section(ctx: Ctx, section: Section, agents: list[Agent]) -> dict[str, dict]:
    """Every agent gets a record: the first source that answers for it, else
    a failed one naming each source's why."""
    ctx = dataclasses.replace(ctx, ctl_s=section.ctl_s, call_s=section.call_s)
    records: dict[str, dict] = {}
    whys: dict[str, list[str]] = {a.login: [] for a in agents}
    pending = list(agents)
    for source in section.sources:
        if not pending:
            break
        try:
            answers = source.read(ctx, pending)
        except SourceError as e:
            for a in pending:
                whys[a.login].append(f"{source.label}: {e}")
            continue
        except Exception as e:  # noqa: BLE001 — a source's bug is that section's failure, not the deck's
            for a in pending:
                whys[a.login].append(f"{source.label}: internal error ({type(e).__name__}: {e})"[:300])
            continue
        still = []
        for a in pending:
            got = answers.get(a.login)
            if got is DECLINED:
                still.append(a)
            elif isinstance(got, dict):
                records[a.login] = {"status": "ok", "src": source.label, "at": stamp(ctx.clock()), "data": got}
            else:
                whys[a.login].append(f"{source.label}: {got.why if isinstance(got, Failed) else 'no row for this agent'}")
                still.append(a)
        pending = still
    for a in pending:
        records[a.login] = {"status": "failed", "src": ",".join(s.label for s in section.sources), "at": stamp(ctx.clock()),
                            "why": "; ".join(whys[a.login]) or "no source"}
    return records


def cache_name(ctx: Ctx, section: Section) -> str:
    # The window is part of what was asked: a 7-day answer is not a 30-day one.
    # days is an int the command line validated, so the name is safe.
    return f"{section.name}-{ctx.days}" if section.name == "tokens" and ctx.days is not None else section.name


def stale_record(entry: dict, why: str, now: float) -> dict:
    old = entry["record"]
    return {"status": "stale", "src": old.get("src"), "at": old.get("at"), "age_s": max(0, round(now - entry["t"])),
            "why": why, "data": old.get("data")}


def fetch_section(ctx: Ctx, section: Section, agents: list[Agent], max_age: float | None, directory: str | None) -> dict[str, dict]:
    limit = section.ttl if max_age is None else max_age
    now = ctx.clock()
    name = cache_name(ctx, section)
    entries = cache_read(directory, name)
    out: dict[str, dict] = {}
    asked = []
    for a in agents:
        e = entries.get(a.login)
        if e and limit > 0 and 0 <= now - e["t"] <= limit:
            out[a.login] = e["record"]
        else:
            asked.append(a)
    if asked:
        fresh = read_section(ctx, section, asked)
        # What stays: every entry still inside the stale window, the failed
        # refreshes' last good values included, and every success just read.
        kept = {k: v for k, v in entries.items() if 0 <= now - v["t"] <= section.stale_s}
        for login, rec in fresh.items():
            if rec["status"] == "ok":
                kept[login] = {"t": now, "record": rec}
                out[login] = rec
            elif (old := kept.get(login)) is not None and 0 <= now - old["t"] <= section.stale_s:
                out[login] = stale_record(old, rec["why"], now)
            else:
                kept.pop(login, None)
                out[login] = rec
        if kept != entries:
            try:
                cache_write(directory, name, kept)
            except OSError:
                pass   # a cache that cannot be written is a slower answer, not a wrong one
    return out


def fetch(sections: list[str] | None = None, agent: str | None = None, max_age: float | None = None, *,
          root: str | None = None, ctx: Ctx | None = None, days: int | None = None) -> dict:
    names = list(sections) if sections else list(DEFAULT_SECTIONS)
    for n in names:
        if n not in SECTIONS:
            raise FleetError(f"no section {n} (sections: {', '.join(SECTIONS)})")
    if "prs" in names and "prs_unplaced" not in names:
        names.append("prs_unplaced")      # the PRs of no placed account ride with the placed ones
    for n in list(names):
        names += [i for i in SECTIONS[n].derives if i not in names]    # what a derived section is told from is read, and shown
    root = root or roots.engine_root()
    placed = load_placements(root)
    if agent is not None and agent not in placed:
        raise FleetError(f"{agent} is not a placed account (runtime/hosts/registry.json)")
    agents = [placed[agent]] if agent else list(placed.values())
    if ctx is None:
        ctx = Ctx(root=root, ssh_hosts=ssh_hosts(root), run=run_program)
    if days is not None:
        ctx.days = days
    directory, why = cache_dir(ctx.env)
    ctx.memo.clear()      # what two sections share lasts one fetch, not the Ctx
    answers: dict[str, dict[str, dict]] = {}
    read = [n for n in names if not SECTIONS[n].derives]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(read)) as pool:
        futures = {n: pool.submit(fetch_section, ctx, SECTIONS[n], [FLEET] if SECTIONS[n].scope == "fleet" else agents, max_age, directory)
                   for n in read}
        for n, f in futures.items():
            answers[n] = f.result()
    for n in names:
        if SECTIONS[n].derives:
            answers[n] = DERIVERS[n](answers, agents, ctx.clock())
    per_agent = [n for n in names if SECTIONS[n].scope == "agent"]
    doc: dict[str, Any] = {"schema": SCHEMA, "at": stamp(ctx.clock()), "sections": names, "agents": [
        {"login": a.login, "host": a.host, "address": a.address, "kind": a.kind,
         "sections": {n: answers[n][a.login] for n in per_agent}} for a in agents]}
    for n in names:
        if SECTIONS[n].scope == "fleet":
            doc[n] = answers[n][FLEET.login]
    if directory is None:
        doc["cache"] = {"usable": False, "why": why}
    return doc


# ── the command ─────────────────────────────────────────────────────

HELP = """usage: fabric-fleet --json [--agent LOGIN] [--section a,b] [--max-age S] [--days N]

The fleet's data, one record per placed agent, read when asked.
  --agent L      only that agent
  --section ..   comma list of: {sections}, or C0..C3 for a cost class
                 (default: every section but C3 and plans; tokens, disk and plans
                 only when named; prs brings prs_unplaced)
  --max-age S    reuse a cached answer up to S seconds old (0 = read afresh);
                 default each section's own TTL
  --days N       the window for `tokens`"""


def expand(spec: str) -> list[str]:
    names: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if part in ("C0", "C1", "C2", "C3"):
            names += [n for n, s in SECTIONS.items() if s.cost == part]
        elif part:
            names.append(part)
    return list(dict.fromkeys(names))


def main(argv: list[str]) -> int:
    as_json = False
    agent = spec = None
    max_age: float | None = None
    days: int | None = None
    i = 0

    def usage(msg: str) -> int:
        print(f"fabric-fleet: {msg}", file=sys.stderr)
        return 2
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(HELP.format(sections=", ".join(SECTIONS)))
            return 0
        if a == "--json":
            as_json = True
        elif a in ("--agent", "--section", "--max-age", "--days"):
            if i + 1 >= len(argv):
                return usage(f"{a} needs a value")
            i += 1
            v = argv[i]
            if a == "--agent":
                agent = v
            elif a == "--section":
                spec = v
            else:
                try:
                    n = float(v) if a == "--max-age" else int(v)
                except ValueError:
                    return usage(f"{a} needs a number, not {v!r}")
                if n < 0 or (a == "--days" and n < 1):
                    return usage(f"{a} {v} is out of range")
                if a == "--max-age":
                    max_age = n
                else:
                    days = int(n)
        else:
            return usage(f"unknown argument {a}")
        i += 1
    if not as_json:
        return usage("--json is required")
    if spec is not None and not expand(spec):
        return usage("--section names no section")
    if days is not None and "tokens" not in (expand(spec) if spec is not None else DEFAULT_SECTIONS):
        return usage("--days applies to the tokens section: name it with --section")
    try:
        doc = fetch(expand(spec) if spec is not None else None, agent, max_age, days=days)
    except FleetError as e:
        return usage(str(e))
    print(json.dumps(doc, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
