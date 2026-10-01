#!/usr/bin/env python3
"""runtime/claude-code/hooks/session-start.py — the SessionStart hook.

Reads the hook payload (cwd, session_id) on stdin, resolves the agent and
its context through runtime/identity.py, records the working copy,
project and session in the agent's runtime binding — never the role,
which only bin/fabric-role changes, from a login shell — and returns the
PROJECT LAYER of the session's context as hook output:

    {"hookSpecificOutput": {"hookEventName": "SessionStart",
                            "additionalContext": "agent-fabric: agent=… role=… project=… \n<the remit>\n<the INDEX pointer>"}}

The role layer (charter, brief, team and memory sections) is in the
system prompt the launcher rendered (tools/fabric/launch_prompt.py) and
never here. What goes here is what follows the working copy: the
project's remit for the role (<working copy>/.agent-fabric/roles/<role>.md
— what the function covers in THIS repository) and one line pointing at
the role's INDEX.md there. The hook runs at start, on resume and after a
compaction, so this layer is re-given each time from the cwd of the
moment — a session that moved to another working copy gets that
project's remit — and the drift line (a rebind under a running session)
is said at each of them. Read back live 2026-09-15: the JSON form is
taken (docs/live-checks/2026-09-15-append-system-prompt.md §6).

The agent name is whatever the OS says. The payload's cwd only tells us
which working copy and project the session is in; a session started in
the parent projects/ directory has neither and says so.

Never blocks a session start: any failure is one line on stderr and exit 0.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys
import time

FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))


SUBAGENT_WORKTREE = re.compile(r"/\.claude/worktrees/[^/]+(/|$)")


def is_subagent(payload, cwd: str) -> bool:
    """A subagent's start, not the session's: the payload names an agent,
    or the cwd is a worktree the harness made for one
    (<checkout>/.claude/worktrees/<name>/)."""
    if isinstance(payload, dict) and (payload.get("agent_id") or payload.get("agent_type")):
        return True
    try:
        return bool(SUBAGENT_WORKTREE.search(os.path.realpath(cwd)))
    except (OSError, ValueError):
        return False


def main() -> int:
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    session = payload.get("session_id") if isinstance(payload, dict) else None
    try:
        spec = importlib.util.spec_from_file_location(
            "fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))
        identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity)
        ctx = identity.resolve_context(cwd=cwd or os.getcwd(), session=session)
        # A subagent the harness starts in its own worktree runs this hook
        # too, with that worktree as its cwd and the parent's session id:
        # written, it repointed the LOGIN's binding at a subagent's scratch
        # checkout, and lint, fabric-status and fabric-jobs then read the
        # wrong working copy until the next start (found 2026-10-01, four
        # Wave 3 workers). A subagent reads the binding; it never writes it.
        subagent = is_subagent(payload, cwd or os.getcwd())
        # Under the agent lock: another hook (a second session of this
        # login) or a rebind from the shell may be writing the same file.
        binding = identity.update_binding(lambda b: b if subagent else {**b,
            "working_copy": ctx["working_copy"],
            "project": ctx["project"] if ctx["project_source"] == "working-copy" else b.get("project"),
            "session": session or b.get("session"),
        }, ctx["agent"])
        role = binding.get("role")
        lines = [f"agent-fabric: agent={ctx['agent']} host={ctx['host']} "
                 f"role={role or '(none — bin/fabric-role bind <role>)'} "
                 f"project={ctx['project'] or '(none)'} "
                 f"working_copy={ctx['working_copy'] or '(not in a working copy)'} "
                 f"control_plane={FABRIC_ROOT}"]
        # The hook runs on start, resume and after a compaction: a rebind
        # from a login shell under a running session is said at the next
        # of those, never left to disagree silently with the prompt.
        drift = identity.launch_role_drift(binding)
        if drift:
            lines.append(f"agent-fabric: DRIFT {drift}")
        lines += project_layer(role, ctx["project"], ctx["working_copy"])
        try:
            lines += trailing(ctx["working_copy"])
        except Exception:  # noqa: BLE001 — a git oddity must not cost the session its project layer
            pass
        try:
            lines += sweep_due(ctx["working_copy"], identity.agent_state_dir(ctx["agent"]))
        except Exception:  # noqa: BLE001 — a state oddity must not cost the session its project layer
            pass
        try:
            lines += jobs_line(identity.read_jobs(ctx["agent"]), ctx["working_copy"])
        except (Exception, SystemExit):  # noqa: BLE001 — a job list it cannot read must not cost the session its start
            pass
        try:
            missing = watch_running() is False
        except Exception:  # noqa: BLE001 — a /proc oddity must not cost the session its project layer
            missing = False
        if missing:
            lines.append(WATCH_MISSING.format(source=payload.get("source") or "start"))
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": "\n".join(lines)}}))
    except (Exception, SystemExit) as exc:  # noqa: BLE001 — a hook must never block a session
        # identity.py refuses with SystemExit (a binding from another host or
        # agent); the session still starts, and is told what was refused.
        msg = str(exc.code if isinstance(exc, SystemExit) else exc)
        print(f"agent-fabric session-start: {msg}", file=sys.stderr)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": f"agent-fabric: session-start could not resolve this session's binding — {msg}"}}))
    return 0


def trailing(working_copy: str | None) -> list[str]:
    """One line when the working copy lacks commits of its origin's
    default branch, as of its last fetch. A project's CLAUDE.md is binding
    the moment the session loads it, and a clone left on an old main gave
    a session rules its project had already replaced; the launcher fetches
    and fast-forwards a clean default branch, and says the gap otherwise —
    this says it to the session. No fetch here: a hook runs on every
    resume and must not wait on the network."""
    if not working_copy:
        return []
    git = lambda *a: subprocess.run(["git", "-C", working_copy, *a], capture_output=True, text=True, timeout=5)
    try:
        ref = git("symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD").stdout.strip() or "origin/main"
        n = git("rev-list", "--count", f"HEAD..{ref}")
        if n.returncode != 0 or not n.stdout.strip().isdigit() or int(n.stdout) == 0:
            return []
        branch = git("symbolic-ref", "-q", "--short", "HEAD").stdout.strip() or "(detached)"
    except (OSError, subprocess.SubprocessError):
        return []
    return [f"agent-fabric: this working copy ({branch}) lacks {int(n.stdout)} commit(s) of {ref} as of its last "
            f"fetch; its CLAUDE.md and rules may be older than the project's — bring it up to date before relying on them."]


SWEEP_EVERY_DAYS = 7


def sweep_due(working_copy: str | None, state_dir: str, now: float | None = None) -> list[str]:
    """One line when this working copy's last branch sweep (bin/fabric-branches
    --sweep, which records it) is older than a week, or never ran. A nudge
    at the session's start, not a timer: the fabric is pull-based, and the
    owner chose a weekly reminder over a step at the end of every job."""
    if not working_copy:
        return []
    try:
        with open(os.path.join(state_dir, "branch-sweep.json"), encoding="utf-8") as fh:
            last = json.load(fh).get(working_copy)
    except (OSError, ValueError, AttributeError):
        last = None
    if isinstance(last, str):
        try:
            at = datetime.datetime.fromisoformat(last.replace("Z", "+00:00")).timestamp()
        except ValueError:
            at = 0.0
        if (now if now is not None else time.time()) - at < SWEEP_EVERY_DAYS * 86400:
            return []
    since = f"last {last[:10]}" if isinstance(last, str) else "never swept"
    return [f"agent-fabric: branch sweep due in this working copy ({since}) — when nothing is running on the tree, "
            f"run `fabric-branches --sweep`: it deletes the local branches and worktrees wholly on origin/main and "
            f"reports the rest, which you bring to the person (the branch-hygiene skill)."]


def jobs_line(doc: dict, working_copy: str | None) -> list[str]:
    """The agent's job list in one line (ADR-037): the active job and how
    many wait behind it, and a warning when the active job's working copy
    is not this session's — the restart rule broken, or a job left active
    by a session that ended. Nothing when the list has no open job."""
    jobs = doc.get("jobs") or []
    active = next((j for j in jobs if j.get("state") == "active"), None)
    queued = sum(1 for j in jobs if j.get("state") == "queued")
    blocked = sum(1 for j in jobs if j.get("state") == "blocked")
    if not active and not queued and not blocked:
        return []
    waiting = ", ".join(f"{n} {what}" for n, what in ((queued, "queued"), (blocked, "blocked")) if n) or "nothing waiting"
    if not active:
        return [f"agent-fabric: jobs — none active; {waiting}. `fabric-jobs next` starts the next one "
                f"and says whether it needs a fresh session."]
    line = f"agent-fabric: jobs — active {active['id']}: {active.get('title', '')[:120]}; {waiting} (`fabric-jobs list`)."
    wc = active.get("working_copy")
    if wc and working_copy != wc:
        line += (f" Your active job is in {wc}, and this session is in {working_copy or 'no working copy'}: "
                 f"continue it there (`fabric-fresh --job {active['id']}`), or block or deliver it before other work.")
    return [line]


# The inbox watch is a Monitor the session itself arms (gzcoord-receive
# §1); a resume or a launcher restart ends the process that ran it and the
# harness does not bring it back, so the inbox went quiet with no sign
# (devex-tooling and architect-cto-01 after their restarts, 2026-09-25).
# The skill said to re-arm; a resumed session did not reread it. A hook
# cannot start a Monitor, so it says so here, at the moment it is true.
# The command is the name on PATH, never `$AGENT_FABRIC_ROOT/…`: the
# harness asks before any command carrying an expansion, and a watch
# re-armed every thirty minutes asked every time (the owner, 2026-09-26;
# runtime/claude-code/commands.json).
WATCH_MISSING = ("agent-fabric: NO INBOX WATCH is running for this session ({source}) — arm it now, "
                 "as your first action: Monitor(command: 'gzcoord-inbox --follow', "
                 "description: 'gzcoord inbox watch', timeout_ms: 1800000), and re-arm it at each expiry notice "
                 "(gzcoord-receive §1). One watch per session: never a second.")


def watch_running(proc: str = "/proc", pid: int | None = None) -> bool | None:
    """Whether a `inbox.mjs --follow` runs under the session this hook
    belongs to: the nearest ancestor whose command is `claude`. None when
    there is no such ancestor (not under a harness) — nothing to say."""
    def stat(p: int) -> tuple[str, int] | None:
        try:
            with open(f"{proc}/{p}/stat", encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
        except OSError:
            return None
        comm = raw[raw.index("(") + 1:raw.rindex(")")]
        return comm, int(raw[raw.rindex(")") + 2:].split()[1])
    session, p = None, pid or os.getpid()
    for _ in range(64):
        st = stat(p)
        if not st:
            break
        if st[0] == "claude":
            session = p
            break
        if st[1] <= 1:
            break
        p = st[1]
    if session is None:
        return None
    parents: dict[int, int] = {}
    for d in os.listdir(proc):
        if d.isdigit() and (st := stat(int(d))):
            parents[int(d)] = st[1]
    for d, _ in parents.items():
        try:
            with open(f"{proc}/{d}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        # The script by its file, or by the name bootstrap links it under
        # (the watch the message below prescribes): missing the name told an
        # armed session to arm a second consumer (review of #42).
        if not ("inbox.mjs" in cmd or "gzcoord-inbox" in cmd) or "--follow" not in cmd:
            continue
        a = d
        for _ in range(64):
            a = parents.get(a, 0)
            if a == session:
                return True
            if a <= 1:
                break
    return False


def project_layer(role: str | None, project: str | None, working_copy: str | None) -> list[str]:
    """The remit and the INDEX pointer for (role, project) in this working
    copy, as context lines; what is missing is said in one line each."""
    if not role:
        return []
    if not (project and working_copy):
        return ["agent-fabric: not in a registered working copy — no project remit for "
                f"{role} here; cd into one and the next start or resume gives it."]
    remit = os.path.join(working_copy, ".agent-fabric", "roles", f"{role}.md")
    index = os.path.join(working_copy, ".agent-fabric", "memory", role, "INDEX.md")
    out: list[str] = []
    try:
        with open(remit, encoding="utf-8") as fh:
            body = fh.read()
        body = re.sub(r"\A---\n.*?\n---\n", "", body, count=1, flags=re.DOTALL).strip("\n")
        out.append(f"# {role} — remit in {project} ({os.path.relpath(remit, working_copy)})\n\n{body}")
    except OSError:
        out.append(f"agent-fabric: {project} has no remit for {role} "
                   f"({os.path.relpath(remit, working_copy)} is missing); the charter is the whole definition here.")
    if os.path.isfile(index):
        out.append(f"Your knowledge of {project}: {os.path.relpath(index, working_copy)} lists every slice with "
                   "its cue — open a slice when its cue matches what you are doing; nothing else now.")
    else:
        out.append(f"agent-fabric: {project} has no distilled knowledge for {role} yet "
                   f"({os.path.relpath(os.path.dirname(index), working_copy)}/).")
    return out


if __name__ == "__main__":
    sys.exit(main())
