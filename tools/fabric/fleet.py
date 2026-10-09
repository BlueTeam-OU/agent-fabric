#!/usr/bin/env python3
"""tools/fabric/fleet.py — the fleet's data on demand (Fleet Deck, Stage 1):
one record per placed agent, assembled from what the control plane already
answers, when a view asks, never in the background.

    fetch(sections, agent=None, max_age=None) -> dict      the library
    bin/fabric-fleet --json [--agent L] [--section a,b] [--max-age S] [--days N]

CONTRACT
  stdout    one JSON object: {"schema": 1, "at", "sections": [names read],
            "agents": [{"login", "host", "address", "kind", "sections":
            {name: record}}]}; "cache" appears only when the cache could not
            be used, with why. A record is {"status": "ok", "src", "at",
            "data"} or {"status": "failed", "src", "at", "why"}: `src` says
            where the value was read (proc-local, hostexec, op:<name>,
            pr-gate), `at` when. The granularity is the section record, not
            each number in `data`.
  Every placed agent has a record for every section asked: a source that
  failed, answered without the agent, or timed out is a failed record with
  its cause, never a crash and never an absent agent.
  stderr    one `fabric-fleet: ` line on a refusal.
  exit      0 an answer was printed (failed records included: they are the
            answer); 2 usage, an unknown agent, an unreadable registry.

SECTIONS, by cost class (the TTL is how long a cached answer is reused)
  C0 proc 5 s · states 5 s · presence 10 s
  C1 jobs 30 s · usage 60 s · host 60 s · fabric 60 s
  C2 prs 120 s · closed_jobs 300 s · accounts 120 s
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

SIDE EFFECT  `prs` runs pr-gate --in-flight, which does `git fetch --prune
  origin` in this checkout, on each call that has no fresh cached prs record
  for every agent asked (so always with --max-age 0 or without a cache).

NEVER read: /proc/*/environ, cmdline, transcripts (fleet_proc.py).
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import roots  # noqa: E402
import fleet_proc  # noqa: E402

SCHEMA = 1
CTL_TIMEOUT_S = 20          # fabric-ctl's own wait for the control agents' replies
CALL_TIMEOUT_S = 90         # the subprocess bound over it: its relay reads can stall too
PR_TIMEOUT_S = 120          # pr-gate fetches origin and lists PRs
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
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))


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


def call(ctx: Ctx, argv: list[str], timeout: float = CALL_TIMEOUT_S, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Not found, hung and unreadable are told apart in the why; a non-zero
    exit is returned, because fabric-ctl exits non-zero with rows to read."""
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
        p = call(ctx, [os.path.join(ctx.root, "bin", "fabric-ctl"), target, op, "--json", "--timeout", str(CTL_TIMEOUT_S), *tail])
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
    p = call(ctx, [os.path.join(ctx.root, "bin", "fabric-ctl"), "all", "states", "--json", "--timeout", str(CTL_TIMEOUT_S)])
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
                    p = call(ctx, argv, timeout=60)
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


def prs_read(ctx: Ctx, agents: list[Agent]) -> dict[str, Any]:
    p = call(ctx, [os.path.join(ctx.root, "runtime", "github", "pr-gate.sh"), "--in-flight", "--json"], timeout=PR_TIMEOUT_S, cwd=ctx.root)
    try:
        doc = json.loads(p.stdout)
        rows = doc["rows"]
    except (ValueError, KeyError, TypeError):
        raise SourceError(f"pr-gate: {last_line(p.stderr) or f'exit {p.returncode}, no answer'}") from None
    mine: dict[str, list[dict]] = {a.login: [] for a in agents}
    for r in rows:
        owner = r.get("owner", "")
        login = owner.split("/", 1)[1] if "/" in owner else ""   # the ref is <host>/<login>/<type>/<what>
        if login in mine:
            mine[login].append({k: r.get(k) for k in ("pr", "branch", "ahead", "last_commit", "paths_total")})
    # fetch_ok/prs_ok false mean the rows are the last fetch's / "PR unknown":
    # the answer is still the best there is, said as it is.
    return {a.login: {"prs": mine[a.login], "fetch_ok": doc.get("fetch_ok"), "prs_ok": doc.get("prs_ok"), "base": doc.get("base")}
            for a in agents}


def closed_jobs_read(ctx: Ctx, agents: list[Agent]) -> dict[str, Any]:
    def one(a: Agent) -> Any:
        if a.kind == "human":
            # sudo goes one way, into role accounts (ADR-010 rule 12, ADR-044 §2).
            return Failed("human login: not an account the fleet enters (ADR-010 rule 12)")
        try:
            p = call(ctx, [os.path.join(ctx.root, "bin", "fabric-host"), a.host, "run", "--as", a.login, "--",
                           "fabric-jobs", "list", "--all", "--json"], timeout=60)
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
        return {"closed_total": len(closed),
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
    Section("closed_jobs", "C2", 300, (Source("hostexec", closed_jobs_read),)),
    Section("accounts", "C2", 120, (ctl_source("accounts"),)),
    Section("tokens", "C3", 600, (ctl_source("tokens"),)),
    Section("disk", "C3", 600, (ctl_source("disk"),)),
)}
DEFAULT_SECTIONS = [n for n, s in SECTIONS.items() if s.cost != "C3"]


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
            json.dump({"version": 1, "agents": entries}, fh)
        os.replace(tmp, os.path.join(directory, f"{section}.json"))
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


# ── fetching ────────────────────────────────────────────────────────

def stamp(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_section(ctx: Ctx, section: Section, agents: list[Agent]) -> dict[str, dict]:
    """Every agent gets a record: the first source that answers for it, else
    a failed one naming each source's why."""
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


def fetch_section(ctx: Ctx, section: Section, agents: list[Agent], max_age: float | None, directory: str | None) -> dict[str, dict]:
    limit = section.ttl if max_age is None else max_age
    now = ctx.clock()
    name = cache_name(ctx, section)
    entries = cache_read(directory, name)
    out: dict[str, dict] = {}
    stale = []
    for a in agents:
        e = entries.get(a.login)
        if e and limit > 0 and 0 <= now - e["t"] <= limit:
            out[a.login] = e["record"]
        else:
            stale.append(a)
    if stale:
        fresh = read_section(ctx, section, stale)
        out.update(fresh)
        kept = {k: v for k, v in entries.items()}
        for login, rec in fresh.items():
            if rec["status"] == "ok":
                kept[login] = {"t": now, "record": rec}
            else:
                kept.pop(login, None)
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
    answers: dict[str, dict[str, dict]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(names)) as pool:
        futures = {n: pool.submit(fetch_section, ctx, SECTIONS[n], agents, max_age, directory) for n in names}
        for n, f in futures.items():
            answers[n] = f.result()
    doc: dict[str, Any] = {"schema": SCHEMA, "at": stamp(ctx.clock()), "sections": names, "agents": [
        {"login": a.login, "host": a.host, "address": a.address, "kind": a.kind,
         "sections": {n: answers[n][a.login] for n in names}} for a in agents]}
    if directory is None:
        doc["cache"] = {"usable": False, "why": why}
    return doc


# ── the command ─────────────────────────────────────────────────────

HELP = """usage: fabric-fleet --json [--agent LOGIN] [--section a,b] [--max-age S] [--days N]

The fleet's data, one record per placed agent, read when asked.
  --agent L      only that agent
  --section ..   comma list of: {sections}, or C0..C3 for a cost class
                 (default: every section but C3; tokens and disk only when named)
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
