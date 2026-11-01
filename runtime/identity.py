#!/usr/bin/env python3
"""runtime/identity.py — the one place agent identity is resolved.

    AGENT IDENTITY = the Linux login of the effective user   (`id -un`)

The agent's name comes from the operating-system account Claude Code (or
any other harness) is running under. Nothing else participates: not the
current directory, not the repository or clone name, not the branch, not
the project, not a session id, and not an environment variable. Those are
CONTEXT — attributes bound to the agent at runtime — and this module
resolves them separately so they can never be mistaken for the name.

    identity.py             the agent name
    identity.py --json      the full runtime context (agent + bindings)
    identity.py --cwd DIR   the context as seen from DIR

Runtime state (which role the agent holds, which project and working copy
it is on) lives OUTSIDE the repository, per agent:

    $AGENT_FABRIC_STATE_DIR/agents/<login>/binding.json
    default: ${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/

Every other tool in agent-fabric — the role activator, the launchers, the
harvesters, the GZCoord runtime, the Claude Code hooks — defers to this
module (or to `bin/fabric-whoami`, which execs it). None of them derives
the agent name on its own.

The state layer (ADR-003). Every file under
`agents/<login>/` is written by this module and by nothing else:
`atomic_write` (a temporary beside the target, fsync, os.replace — the old
file stays whole through a crash or a full disk), `agent_lock` (a
flock on `agents/<login>/.lock`, re-entrant only in the thread holding
it; every read-modify-write of per-agent state holds it, across processes
and threads), `update_binding` and
`append_history` on top of both. A binding is per (agent, host): one
written on another machine is refused by `read_binding` the way another
agent's is, so a shared home never carries a role from one host to the
next.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import fcntl
import importlib.util
import json
import os
import pwd
import re
import socket
import sys
import tempfile
import threading
from typing import TypedDict

# The repository this module lives in. AGENT_FABRIC_ROOT lets a test point
# at a fixture tree; it never influences the agent NAME.
FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(
    os.path.dirname(os.path.realpath(__file__)))


def current_agent(getpwuid=pwd.getpwuid, geteuid=os.geteuid) -> str:
    """The agent's canonical name: the login of the effective user.

    Equivalent to `id -un`. The two parameters exist so a test can pass a
    fake passwd lookup; there is deliberately no environment override.
    """
    return getpwuid(geteuid()).pw_name


def current_host() -> str:
    """Short hostname. Recorded beside the agent, never part of its name."""
    return socket.gethostname().split(".")[0]


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def state_root() -> str:
    override = os.environ.get("AGENT_FABRIC_STATE_DIR")
    if override:
        return os.path.abspath(override)
    xdg = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(xdg, "agent-fabric")


def agent_state_dir(agent: str | None = None) -> str:
    return os.path.join(state_root(), "agents", agent or current_agent())



# The runtime binding, as write_binding stamps it and its writers fill it
# (role.py bind/unbind, the session-start hook, rename_history). The keys a
# writer may leave out live in a total=False subclass: under `from
# __future__ import annotations` TypedDict counts NotRequired[...] as
# required. tests/test_role.py holds a real bind's binding to it.
class _BindingKeys(TypedDict):
    agent: str
    host: str
    updated_at: str


class Binding(_BindingKeys, total=False):
    role: str | None
    project: str | None
    working_copy: str | None
    workspace: str | None
    session: str | None
    installed: list[dict[str, str]]

def binding_path(agent: str | None = None) -> str:
    return os.path.join(agent_state_dir(agent), "binding.json")


# ---------------------------------------------------------------------------
# The state layer's two primitives. Every file under the agent's state
# directory — and every file a fabric tool rewrites in an account's home
# (transcripts, ~/.claude.json, history) — goes through these, so a crash,
# a full disk or a kill leaves the previous file whole, and two processes
# never interleave a read-modify-write (review, 2026-09-16: the rename tool
# rewrote JSON in place and bypassed write_binding; nothing serialized the
# binding, the history or the model profile).

def atomic_write(path: str, data: "bytes | str", mode: int | None = None) -> None:
    """Write `data` to `path` all-or-nothing: a temporary file beside it,
    flushed and fsynced, then os.replace — the reader sees the old file
    or the new one, never a torn one. The temporary is removed on any
    failure. `mode` sets the permission bits (0o600 for a private file);
    otherwise the existing file's bits are kept, or the umask applies."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data.encode("utf-8") if isinstance(data, str) else data)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        elif os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class _AgentHold:
    """One agent's lock as this process holds it. `lock` is the thread
    fence; `owner`, `depth`, `fd` and `shared` are written only by the
    thread holding `lock`, so a thread comparing `owner` to its own ident
    is never told yes by another thread's hold."""
    __slots__ = ("lock", "owner", "depth", "fd", "shared")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.owner: int | None = None
        self.depth = 0
        self.fd: int | None = None
        self.shared = False


# Owned by a thread, not only keyed by agent (audit F03, 2026-11-01): keyed
# by agent alone, a second thread of agentd or fabric-op took the first
# one's hold for its own and ran its read-modify-write unserialized, and
# the first one's exit unlocked the flock under it. _HOLDS_GUARD only makes
# the per-agent entry once; it is never held across a flock wait.
_HOLDS_GUARD = threading.Lock()
_HOLDS: dict[str, _AgentHold] = {}


def _forget_holds_in_child() -> None:
    # A forked child is another process and must take the flock itself.
    # What it inherited is the parent's view: a hold "owned" by the forking
    # thread (same ident in the child, so it would skip the flock), or a
    # thread lock another parent thread held that nobody in the child will
    # ever release. The inherited descriptors share the parent's open file
    # description, so the child must not LOCK_UN them (that would unlock
    # the parent); closing them is safe, since a flock lives until its last
    # descriptor goes and the parent still has its own.
    global _HOLDS_GUARD, _HOLDS
    for hold in _HOLDS.values():
        if hold.fd is not None:
            with contextlib.suppress(OSError):
                os.close(hold.fd)
    _HOLDS_GUARD = threading.Lock()
    _HOLDS = {}


os.register_at_fork(after_in_child=_forget_holds_in_child)


@contextlib.contextmanager
def agent_lock(agent: str | None = None, *, shared: bool = False):
    """Serialize the mutations of one agent's runtime state — the binding,
    the role history, the model profile, a role activation — across
    processes and across the threads of one: an exclusive flock on
    agents/<login>/.lock, held for the block, behind a per-agent thread
    lock. Re-entrant within the thread that holds it (an activation
    appends history under the lock it already holds): flock conflicts
    with itself across two descriptors, so the lock is taken once and
    nested uses count. Another thread waits for the holder's outermost
    exit. A reader that wants a consistent snapshot may take it `shared`;
    an exclusive request nested in a shared hold is refused, because the
    flock cannot be upgraded without letting go of it in between."""
    agent = agent or current_agent()
    with _HOLDS_GUARD:
        hold = _HOLDS.setdefault(agent, _AgentHold())
    me = threading.get_ident()
    if hold.owner == me:
        if hold.shared and not shared:
            raise RuntimeError(f"identity: an exclusive agent_lock({agent!r}) inside a shared one; take it exclusive at the outermost level")
        hold.depth += 1
        try:
            yield
        finally:
            hold.depth -= 1
        return
    hold.lock.acquire()
    try:
        directory = agent_state_dir(agent)
        os.makedirs(directory, exist_ok=True)
        fd = os.open(os.path.join(directory, ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        except BaseException:
            os.close(fd)
            raise
        hold.owner, hold.depth, hold.fd, hold.shared = me, 1, fd, shared
        try:
            yield
        finally:
            hold.owner, hold.depth, hold.fd = None, 0, None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
    finally:
        # Last, after the flock and its descriptor: the next thread in
        # opens its own and finds nothing of this hold left.
        hold.lock.release()


def read_binding(agent: str | None = None) -> Binding | dict:
    """The agent's runtime binding, or {} when none has been written.

    A binding that names a different agent than the directory it sits in
    is refused rather than trusted: the directory is keyed by the login,
    and a record disagreeing with it is a copied file, not a binding. So is
    one written on another host: the login is the identity, but the state
    is a runtime instance on one machine — a home directory shared or
    synced between hosts would otherwise let two instances of one login
    write over each other's binding (review, 2026-09-16). A move between
    hosts is a rebind there.
    """
    agent = agent or current_agent()
    path = binding_path(agent)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        raise SystemExit(f"identity: {path} is not valid JSON ({exc})")
    if not isinstance(data, dict):
        raise SystemExit(f"identity: {path} is not a JSON object")
    if data.get("agent") not in (None, agent):
        raise SystemExit(f"identity: {path} names agent {data.get('agent')!r}, "
                         f"but this is {agent!r}'s state directory")
    host = current_host()
    if data.get("host") not in (None, host):
        raise SystemExit(f"identity: {path} was written on host {data.get('host')!r}, but this is {host!r}: "
                         "the state directory is shared between hosts. Bind here (fabric-role bind <role>) "
                         "rather than trust another machine's binding.")
    return data


def write_binding(binding: dict, agent: str | None = None) -> str:
    """Write the agent's binding atomically. `agent` and `host` are stamped
    from the OS, never taken from the caller's dictionary. Callers that
    read first and write back go through update_binding, which holds the
    agent lock across both."""
    agent = agent or current_agent()
    record = dict(binding)
    record["agent"] = agent
    record["host"] = current_host()
    record["updated_at"] = now_iso()
    path = binding_path(agent)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return path


def update_binding(mutate, agent: str | None = None) -> dict:
    """Read-modify-write under the agent lock: `mutate(binding)` returns
    the new record (or edits it in place and returns None). Two processes
    updating at once — a session-start hook and a rebind, two hooks of
    two sessions of one login — serialize here instead of the last writer
    silently winning."""
    agent = agent or current_agent()
    with agent_lock(agent):
        binding = read_binding(agent)
        new = mutate(binding)
        if new is None:
            new = binding
        write_binding(new, agent)
        return new


def append_history(record: dict, agent: str | None = None) -> str:
    """One JSON line appended to agents/<login>/role-history.jsonl, under
    the agent lock so two writers never interleave a line."""
    agent = agent or current_agent()
    path = os.path.join(agent_state_dir(agent), "role-history.jsonl")
    with agent_lock(agent):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    return path


def jobs_path(agent: str | None = None) -> str:
    return os.path.join(agent_state_dir(agent), "jobs.json")


def read_jobs(agent: str | None = None) -> dict:
    """The agent's job list (agent-fabric ADR-037): {"agent", "host",
    "seq", "jobs": [...]}, or an empty list when none has been written.
    Refused like a binding when it names another agent or was written on
    another host: the list is one runtime instance's, never a copy's."""
    agent = agent or current_agent()
    path = jobs_path(agent)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {"agent": agent, "host": current_host(), "seq": 0, "jobs": []}
    except ValueError as exc:
        raise SystemExit(f"identity: {path} is not valid JSON ({exc})")
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise SystemExit(f"identity: {path} is not a job list")
    if data.get("agent") not in (None, agent):
        raise SystemExit(f"identity: {path} names agent {data.get('agent')!r}, but this is {agent!r}'s state directory")
    if data.get("host") not in (None, current_host()):
        raise SystemExit(f"identity: {path} was written on host {data.get('host')!r}, but this is "
                         f"{current_host()!r}: the state directory is shared between hosts")
    data.setdefault("seq", 0)
    return data


def update_jobs(mutate, agent: str | None = None) -> dict:
    """Read-modify-write of the job list under the agent lock, as
    update_binding: two sessions of one login, or the control agent adding
    the owner's job, serialize here. `mutate(doc)` edits the document in
    place or returns a new one; agent and host are stamped from the OS."""
    agent = agent or current_agent()
    with agent_lock(agent):
        doc = read_jobs(agent)
        new = mutate(doc)
        if new is None:
            new = doc
        new["agent"], new["host"], new["updated_at"] = agent, current_host(), now_iso()
        path = jobs_path(agent)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_write(path, json.dumps(new, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return new


# The fleet hold (agent-fabric ADR-037 rule 13): present means held. Only
# the control agent's `hold`/`unhold` actions write it; the job tool, the
# status and the session-start hook read it. Its absence is the normal
# state, so a reader never creates it.
HOLD_REASON_MAX = 200
HOLD_DECISION = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.ASCII)


def hold_path(agent: str | None = None) -> str:
    return os.path.join(agent_state_dir(agent), "hold.json")


def read_hold(agent: str | None = None) -> dict | None:
    """The hold, {"agent", "host", "reason", "decision", "set_by", "set_at"},
    or None when the login is not held. A file that cannot be read as a
    hold is refused, never read as no hold: somebody wrote it to stop job
    starts, and a corrupt one must not be what lets them through."""
    agent = agent or current_agent()
    path = hold_path(agent)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except ValueError as exc:
        raise SystemExit(f"identity: {path} is not valid JSON ({exc}); the login counts as held until it is fixed or unhold removes it")
    if not isinstance(data, dict) or not isinstance(data.get("reason"), str):
        raise SystemExit(f"identity: {path} is not a hold; the login counts as held until unhold removes it")
    if data.get("agent") not in (None, agent):
        raise SystemExit(f"identity: {path} names agent {data.get('agent')!r}, but this is {agent!r}'s state directory")
    return data


def set_hold(reason: str, set_by: str, decision: str | None = None, agent: str | None = None) -> dict:
    """Write the hold, replacing one already set (a second `hold` restates
    the reason). `reason` is one line of at most HOLD_REASON_MAX
    characters; `decision`, when given, is a GZCoord MESSAGE-ID."""
    agent = agent or current_agent()
    if not isinstance(reason, str) or not reason.strip() or "\n" in reason or "\r" in reason or len(reason) > HOLD_REASON_MAX:
        raise ValueError(f"a hold's reason is one non-empty line of at most {HOLD_REASON_MAX} characters")
    if decision is not None and not HOLD_DECISION.fullmatch(decision):
        raise ValueError("a hold's decision is a MESSAGE-ID (a lowercase UUID)")
    with agent_lock(agent):
        # Stamped under the lock: of two holds racing, the one left standing
        # is the one with the later set_at.
        record = {"agent": agent, "host": current_host(), "reason": reason.strip(),
                  "decision": decision, "set_by": set_by, "set_at": now_iso()}
        path = hold_path(agent)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return record


def clear_hold(agent: str | None = None) -> bool:
    """Lift the hold: True when one was removed, False when none was set."""
    agent = agent or current_agent()
    with agent_lock(agent):
        try:
            os.unlink(hold_path(agent))
        except FileNotFoundError:
            return False
    return True


# Plans the coordinator keeps (agent-fabric ADR-047): one file per plan in
# the agent's own state, written only here, under the agent lock.
PLAN_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}", re.ASCII)


def plans_dir(agent: str | None = None) -> str:
    return os.path.join(agent_state_dir(agent), "plans")


def plan_path(plan_id: str, agent: str | None = None) -> str:
    """agents/<login>/plans/<id>.json. The id is a slug: it names a file."""
    if not isinstance(plan_id, str) or not PLAN_ID.fullmatch(plan_id):
        raise SystemExit(f"identity: {plan_id!r} is not a plan id (lowercase letters, digits and dashes, at most 63)")
    return os.path.join(plans_dir(agent), plan_id + ".json")


def read_plan(plan_id: str, agent: str | None = None) -> dict | None:
    """The plan, or None when none has that id."""
    path = plan_path(plan_id, agent)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except ValueError as exc:
        raise SystemExit(f"identity: {path} is not valid JSON ({exc})")
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise SystemExit(f"identity: {path} is not a plan")
    return data


def list_plans(agent: str | None = None) -> list[dict]:
    """Every plan of the agent, by id."""
    try:
        names = sorted(n[:-5] for n in os.listdir(plans_dir(agent)) if n.endswith(".json"))
    except FileNotFoundError:
        return []
    return [p for p in (read_plan(n, agent) for n in names if PLAN_ID.fullmatch(n)) if p is not None]


def update_plan(plan_id: str, mutate, agent: str | None = None) -> dict:
    """Read-modify-write of one plan under the agent lock, as update_jobs.
    `mutate(doc)` gets the plan, or None when there is none yet, and edits it
    in place or returns the plan to keep; a SystemExit it raises leaves the
    file as it was. Nothing to keep (no plan, and mutate returned none) is
    refused, never written: a file holding null would read as no plan.
    The directory and the file are private (0700, 0600), as the state is."""
    agent = agent or current_agent()
    with agent_lock(agent):
        doc = read_plan(plan_id, agent)
        new = mutate(doc)
        if new is None:
            new = doc
        if not isinstance(new, dict):
            raise SystemExit(f"identity: plan {plan_id!r}: nothing to write (no plan, and none was made)")
        path = plan_path(plan_id, agent)
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        atomic_write(path, json.dumps(new, ensure_ascii=False, indent=2, sort_keys=True) + "\n", mode=0o600)
        return new


def launch_role_drift(binding: dict, environ: dict | None = None) -> str | None:
    """A session was launched with one role in its system prompt
    (AGENT_FABRIC_LAUNCH_ROLE, stamped by runtime/openrouter/launch); the
    binding may have been changed under it since, from a login shell.
    The two must not disagree silently: this is the one sentence both
    bin/fabric-status and the session-start hook print when they do.
    None when there is no stamp (not a fabric launch) or no drift."""
    env = os.environ if environ is None else environ
    launched = env.get("AGENT_FABRIC_LAUNCH_ROLE")
    if not launched:
        return None
    current = binding.get("role")
    if launched == current:
        return None
    return (f"launched as {launched}, binding now {current or '(none)'} — this session's prompt "
            f"still holds {launched}; relaunch to hold {current or 'no role'}")


def _workingcopy():
    """tools/fabric/workingcopy.py, loaded by path so this file works from
    any cwd and any sys.path."""
    spec = importlib.util.spec_from_file_location(
        "fabric_workingcopy", os.path.join(FABRIC_ROOT, "tools", "fabric", "workingcopy.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_context(cwd: str | None = None, session: str | None = None,
                    agent: str | None = None) -> dict:
    """The agent plus everything bound to it right now.

    `project` comes from the working copy `cwd` sits in when that copy is a
    registered project; otherwise from the agent's binding (the project the
    role was activated for). `project_source` says which. The working copy
    is reported as a path and as its basename — the basename is a label
    for humans and logs, never an identity.
    """
    agent = agent or current_agent()
    cwd = os.path.abspath(cwd or os.getcwd())
    wc = _workingcopy().resolve(cwd)
    binding = read_binding(agent)
    if wc.get("project"):
        project, source = wc["project"], "working-copy"
    elif binding.get("project"):
        project, source = binding["project"], "binding"
    else:
        project, source = None, None
    host = current_host()
    return {
        "agent": agent,
        "host": host,
        # The GZCoord address (SPEC §3.1), composed once here so a message
        # written by hand takes it as printed rather than rebuilt from two
        # fields; the relay transport doc points here for it.
        "address": f"{host}/{agent}",
        "role": binding.get("role"),
        "project": project,
        "project_source": source,
        "working_copy": wc.get("path"),
        "working_copy_id": wc.get("id"),
        "remote": wc.get("remote"),
        "session": session or os.environ.get("CLAUDE_SESSION_ID"),
        "cwd": cwd,
        "fabric_root": FABRIC_ROOT,
        "state_dir": agent_state_dir(agent),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Resolve the current agent identity and its runtime context.")
    ap.add_argument("--json", action="store_true", help="print the full context as JSON")
    ap.add_argument("--host", action="store_true", help="print the host label only")
    ap.add_argument("--role", action="store_true",
                    help="print the role this agent's binding holds (empty when none) — the binding alone, no working-copy resolution")
    ap.add_argument("--cwd", default=None, help="resolve working copy and project as seen from this directory")
    ap.add_argument("--session", default=None, help="session identifier to record in the context")
    args = ap.parse_args(argv)
    if args.host:
        print(current_host())
        return 0
    if args.role:
        print((read_binding() or {}).get("role") or "")
        return 0
    if args.json:
        print(json.dumps(resolve_context(args.cwd, args.session), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(current_agent())
    return 0


if __name__ == "__main__":
    sys.exit(main())
