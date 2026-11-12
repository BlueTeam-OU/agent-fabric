#!/usr/bin/env python3
"""tools/fabric/operator_checkout.py — the operator's checkout beside the engine, and the engine pin it carries
(agent-fabric ADR-045 §6, docs/split/move-plan.md §2 item 3).

Every account holds two checkouts: the engine, <projects>/agent-fabric, and the operator repository,
<projects>/blueteam-fabric (BlueTeam-OU/blueteam-fabric, private). Nothing resolves THROUGH the second yet
(step B is later); this module only provisions it, keeps it current, and reads the one thing the operator
decides for the engine: its version.

THE PIN (the owner's decision, 2026-11-12, recorded in an ADR-045 amendment): the operator repository's
.agent-fabric/fabric-ref, ADR-011's file, one line, the full 40-hex engine commit. One reader, `engine_plan`,
serves the control agent's `upgrade fabric`, the launcher's pull and moveto's entry refresh: the engine
fast-forwards TO the pin and never past it. The pin is read from the operator checkout's committed HEAD,
never from its working tree, so an edit left uncommitted is not a pin.

  absent          no checkout, no commit, or no fabric-ref in HEAD: behaviour is today's (the engine tracks
                  origin/main) with one line saying no pin is in force. An absent pin that froze the engine
                  would stop every upgrade until step D, so absence never holds anything back.
  malformed       present but unreadable, not a regular file, or not exactly one 40-hex id: REFUSED, said.
                  Unknown is not absent: a pin nobody can read is a pin somebody meant.
  pinned          the engine moves to the pin when HEAD is an ancestor of it. A pin the engine does not have
                  after its fetch, one behind HEAD, or one HEAD has diverged from, leaves the engine where it
                  is and says why.

A missing operator checkout is reported and never replaced by the engine's tree (roots: a missing root is a
path that does not exist). An unreachable operator remote is said and is never fatal to the engine half.

Command line (stdout: nothing; stderr: the report lines; the callers parse the exit status only):
  operator_checkout.py ensure  --projects DIR [--dry-run]   clone when absent, fast-forward when present
  operator_checkout.py refresh --engine DIR --projects DIR  sync the operator, then move the engine to the pin
                                                            (or origin/main with no pin); moveto's entry
  exit  0 done or said-and-carried-on; 1 the engine could not be moved (the line says why); 2 bad argument.
Standard library only; git through git.py.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass

import importlib.util

HERE = os.path.dirname(os.path.realpath(__file__))


def _load_git():
    # By path, never from sys.path: the launcher loads this module from the fabric being launched, and a
    # directory on its path would answer for the launcher's other imports (launcher/base.py says why).
    spec = importlib.util.spec_from_file_location("fabric_git", os.path.join(HERE, "git.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


git = _load_git()

OPERATOR_DIR = "blueteam-fabric"
# SSH, as every account clones its private projects: the repository is private, so an https URL would ask for
# a credential this account may not hold.
DEFAULT_CLONE_URL = "git@github.com:BlueTeam-OU/blueteam-fabric.git"
CLONE_URL_ENV = "AGENT_FABRIC_OPERATOR_CLONE_URL"
PIN_PATH = ".agent-fabric/fabric-ref"
FETCH_TIMEOUT_S = 60
CLONE_TIMEOUT_S = 180
_SHA = re.compile(r"[0-9a-f]{40}")
# git's words for a remote that exists and has no such branch: an empty repository (blueteam-fabric today),
# which is a state of the operator, not an unreachable remote.
_NO_REMOTE_MAIN = "couldn't find remote ref"


def path(projects: str) -> str:
    return os.path.join(projects, OPERATOR_DIR)


def clone_url(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return env.get(CLONE_URL_ENV) or DEFAULT_CLONE_URL


def _noninteractive() -> dict[str, str]:
    # A clone or fetch that asks for a password hangs a bootstrap that nobody is watching.
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


def cause(stderr: str, code: int) -> str:
    """git ends a refusal with advice ("and the repository exists."); the cause is its first fatal:/error:/ssh: line."""
    lines = [l for l in stderr.strip().splitlines() if l.strip() and not l.startswith("hint:")]
    named = [l for l in lines if l.startswith(("fatal:", "error:", "ssh:"))]
    return (named or lines or [f"git exit {code}"])[0 if named else -1]


def is_checkout(op: str) -> bool:
    if not os.path.isdir(op):
        return False
    try:
        top = git.out(op, "rev-parse", "--show-toplevel")
    except git.GitError:
        return False
    return os.path.realpath(top) == os.path.realpath(op)


# ── the operator checkout ───────────────────────────────────────────

@dataclass
class Sync:
    # absent | not-a-checkout | cloned | would-clone | current | updated | empty | offline | left
    state: str
    line: str


def absent_line(op: str) -> str:
    return f"operator checkout {op} is absent; no engine pin is in force, the engine tracks origin/main"


def sync(op: str, fetch_timeout: float = FETCH_TIMEOUT_S) -> Sync:
    """Bring a present operator checkout to its origin/main; never forced. Says what it did not do."""
    if not os.path.lexists(op):
        return Sync("absent", absent_line(op))
    if not is_checkout(op):
        return Sync("not-a-checkout", f"operator checkout {op} exists but is not a git checkout of its own; left as it is")
    try:
        r = git.run(op, "fetch", "-q", "origin", "main", check=False, env=_noninteractive(), timeout=fetch_timeout)
    except git.GitError as e:
        return Sync("offline", f"operator checkout {op}: {e.reason}; not refreshed")
    if r.returncode != 0:
        if _NO_REMOTE_MAIN in r.stderr:
            return Sync("empty", f"operator repository at {op} has no main branch yet")
        return Sync("offline", f"operator checkout {op}: remote unreachable ({cause(r.stderr, r.returncode)}); not refreshed")
    try:
        branch = git.out(op, "symbolic-ref", "-q", "--short", "HEAD", check=False)
        behind = int(git.out(op, "rev-list", "--count", "HEAD..origin/main"))
    except (git.GitError, ValueError) as e:
        return Sync("left", f"operator checkout {op}: cannot tell how far behind it is ({e}); left as it is")
    if behind == 0:
        return Sync("current", "")
    if branch != "main":
        return Sync("left", f"operator checkout {op} is on {branch or 'a detached HEAD'}, not main, and {behind} commit(s) behind; left as it is")
    try:
        git.run(op, "merge", "-q", "--ff-only", "origin/main", env=_noninteractive())
    except git.GitError as e:
        return Sync("left", f"operator checkout {op} cannot fast-forward ({e.reason}); left as it is")
    return Sync("updated", f"operator checkout {op} fast-forwarded {behind} commit(s)")


def clone(projects: str, url: str, *, dry_run: bool = False) -> Sync:
    """Clone the operator repository beside the engine when it is not there. Never into a path that exists."""
    op = path(projects)
    if os.path.lexists(op):
        return sync(op)
    if dry_run:
        return Sync("would-clone", f"operator checkout {op} would be cloned from {url}")
    try:
        r = git.run(projects, "clone", "-q", url, op, check=False, env=_noninteractive(), timeout=CLONE_TIMEOUT_S)
    except git.GitError as e:
        return Sync("offline", f"operator checkout {op} not cloned from {url}: {e.reason}")
    if r.returncode != 0:
        return Sync("offline", f"operator checkout {op} not cloned from {url}: {cause(r.stderr, r.returncode)}")
    return Sync("cloned", f"operator checkout {op} cloned from {url}")


# ── the pin ─────────────────────────────────────────────────────────

@dataclass
class Pin:
    kind: str          # "absent" | "pinned" | "malformed"
    sha: str = ""
    why: str = ""      # for absent and malformed: the reason, in the words a line carries


def read_pin(op: str) -> Pin:
    if not os.path.lexists(op):
        return Pin("absent", why=absent_line(op))
    if not is_checkout(op):
        return Pin("absent", why=f"operator checkout {op} is not a git checkout of its own; no engine pin is in force, the engine tracks origin/main")
    try:
        if git.run(op, "rev-parse", "-q", "--verify", "HEAD^{commit}", check=False).returncode != 0:
            return Pin("absent", why=f"operator checkout {op} has no commits; no engine pin is in force, the engine tracks origin/main")
        entry = git.out(op, "ls-tree", "HEAD", "--", PIN_PATH)
        if not entry:
            return Pin("absent", why=f"operator checkout {op} has no {PIN_PATH}; no engine pin is in force, the engine tracks origin/main")
        mode = entry.split(None, 1)[0]
        if mode not in ("100644", "100755"):
            return Pin("malformed", why=f"{PIN_PATH} in {op} is not a regular file (mode {mode})")
        size = int(git.out(op, "cat-file", "-s", f"HEAD:{PIN_PATH}"))
        # The byte count is checked beside the text: git.run decodes in text mode, which folds a CRLF into a
        # newline, so only the size tells "sha\r\n" from "sha\n".
        if size not in (40, 41):
            return Pin("malformed", why=f"{PIN_PATH} in {op} is not one full 40-hex commit id ({size} bytes)")
        raw = git.run(op, "cat-file", "blob", f"HEAD:{PIN_PATH}", errors="replace").stdout
    except (git.GitError, ValueError) as e:
        return Pin("malformed", why=f"{PIN_PATH} in {op} cannot be read ({e})")
    line = raw[:-1] if raw.endswith("\n") else raw
    if not _SHA.fullmatch(line):
        return Pin("malformed", why=f"{PIN_PATH} in {op} is not one full 40-hex commit id")
    return Pin("pinned", sha=line)


# ── the one reader ──────────────────────────────────────────────────

@dataclass
class EnginePlan:
    """target: where to fast-forward the engine to (a commit under a pin, the ref origin/main without one), "" to
    leave it where it is. refusal: set when the pin
    is malformed (a verdict, not a plan). notes: lines for the caller to say."""
    target: str = ""
    refusal: str = ""
    notes: list[str] | None = None

    def __post_init__(self) -> None:
        if self.notes is None:
            self.notes = []


def engine_plan(engine: str, pin: Pin) -> EnginePlan:
    """Where the engine may move, once its own fetch is done. Without a pin that is origin/main as it is today.
    With one it is the pin: reachable, not behind HEAD, a descendant of it. Nothing here moves anything."""
    if pin.kind == "malformed":
        return EnginePlan(refusal=pin.why)
    if pin.kind == "absent":
        # A ref name, not a commit: with no pin the callers go where they always went, and say so.
        return EnginePlan(target="origin/main", notes=[pin.why])
    try:
        have = git.run(engine, "cat-file", "-e", f"{pin.sha}^{{commit}}", check=False).returncode == 0
        if not have:
            return EnginePlan(notes=[f"the operator pins engine {pin.sha[:12]}, which this checkout does not have after its fetch; the engine stays where it is"])
        if git.ok(engine, "merge-base", "--is-ancestor", "HEAD", pin.sha):
            return EnginePlan(target=pin.sha)
        if git.ok(engine, "merge-base", "--is-ancestor", pin.sha, "HEAD"):
            return EnginePlan(notes=[f"the engine is ahead of the operator's pin {pin.sha[:12]}; the engine stays where it is"])
    except git.GitError as e:
        return EnginePlan(notes=[f"the pin {pin.sha[:12]} cannot be compared with the engine ({e.reason}); the engine stays where it is"])
    return EnginePlan(notes=[f"the engine has diverged from the operator's pin {pin.sha[:12]}; the engine stays where it is"])


# With a caller's budget the operator fetch gets this share and the engine fetch the next one; the rest is
# local git and process start. The engine half is the one the caller needs, so the operator, whose
# unreachability is never fatal, is the one bounded small.
OPERATOR_SHARE, ENGINE_SHARE = 0.3, 0.5


def refresh(engine: str, projects: str, budget: float | None = None) -> tuple[int, list[str]]:
    """moveto's entry: sync the operator, fetch the engine, fast-forward it to the plan's target. (status, lines).
    `budget` is the seconds the caller will wait for the whole refresh; without it each fetch has its own bound."""
    lines: list[str] = []
    op = path(projects)
    op_timeout = FETCH_TIMEOUT_S if budget is None else min(FETCH_TIMEOUT_S, budget * OPERATOR_SHARE)
    engine_timeout = FETCH_TIMEOUT_S if budget is None else min(FETCH_TIMEOUT_S, budget * ENGINE_SHARE)
    s = sync(op, op_timeout)
    # absent and not-a-checkout are said once, by the pin's own note below.
    if s.line and s.state not in ("absent", "not-a-checkout"):
        lines.append(s.line)
    try:
        git.run(engine, "fetch", "-q", "origin", "main", env=_noninteractive(), timeout=engine_timeout)
    except git.GitError as e:
        return 1, lines + [f"engine git fetch: {e.reason}"]
    plan = engine_plan(engine, read_pin(op))
    if plan.refusal:
        return 1, lines + [plan.refusal]
    lines += plan.notes or []
    if not plan.target:
        return 0, lines
    try:
        git.run(engine, "merge", "-q", "--ff-only", plan.target)
    except git.GitError as e:
        return 1, lines + [e.reason]
    return 0, lines


def main(argv: list[str]) -> int:
    def usage(msg: str) -> int:
        print(f"operator_checkout: {msg}", file=sys.stderr)
        return 2
    if not argv or argv[0] not in ("ensure", "refresh"):
        return usage("usage: ensure --projects DIR [--dry-run] | refresh --engine DIR --projects DIR [--budget SECONDS]")
    opts: dict[str, str] = {}
    dry = False
    rest = iter(argv[1:])
    for a in rest:
        if a == "--dry-run" and argv[0] == "ensure":
            dry = True
        elif a in ("--projects", "--engine", "--budget") and (argv[0] == "refresh" or a == "--projects"):
            v = next(rest, None)
            if not v:
                return usage(f"{a} needs a value")
            opts[a] = v
        else:
            return usage(f"unknown argument {a}")
    projects = opts.get("--projects")
    if not projects or not os.path.isdir(projects) or (argv[0] == "refresh" and not opts.get("--engine")):
        return usage("--projects names no directory" if not projects or not os.path.isdir(projects or "") else "--engine is required")
    if argv[0] == "ensure":
        s = clone(projects, clone_url(), dry_run=dry)
        if s.line:
            print(s.line, file=sys.stderr)
        return 0
    budget: float | None = None
    if "--budget" in opts:
        try:
            budget = float(opts["--budget"])
        except ValueError:
            budget = 0.0
        if not (budget > 0 and budget < float("inf")):
            return usage("--budget needs a positive number of seconds")
    rc, lines = refresh(opts["--engine"], projects, budget)
    for l in lines:
        print(l, file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
