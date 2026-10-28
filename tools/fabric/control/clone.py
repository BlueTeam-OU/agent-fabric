"""tools/fabric/control/clone.py — `clone <project-id>`, a signed action: this account gets the working copy of a
registered project (owner's request, REQUEST 01a182bb: a clone is otherwise made only by provisioning's step 6,
a step of a whole run, and an operation on an existing account goes through a signed action).

What the control agent does, as the login it runs as:
  1. refuses an id that is no registry id or that projects/registry.json does not hold (nothing is run);
  2. clones the registry's SSH remote into ~/projects/<id>, or, when a clone is already there, reports it
     `present` and points its origin at the registry's remote as step 6 does (project_clone.plan_origin is the
     one judgement both use);
  3. runs the fabric checkout's runtime/claude-code/bootstrap.sh as it is, so core.hooksPath covers the new
     working copy.

Bootstrap runs after a `present` too, not only after a clone: a clone whose bootstrap failed is `failed`, the
next run finds it present, and a bootstrap skipped there would leave that working copy without its hooks for
good. It is idempotent, so the re-run costs time and nothing else.

Nothing of a request but the project id is used, and that only after it matched the registry's grammar and the
registry itself named it: the remote, the destination and every argv come from the registry and this code.
Role binding, secrets and anything a project owns beyond its clone (ports, toolchains) are not this action's.
"""
from __future__ import annotations

import os
import signal
import subprocess
from typing import Any, Callable

from control.ops import util
from control.tools import MAX_BUFFER
from control.upgrade import BOOTSTRAP_TIMEOUT_MS, last_line
import project_clone
import roots
from registry_id import REGISTRY_ID

# tools/fabric/control/ -> the checkout this code is in.
_CODE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
CLONE_TIMEOUT_MS = 20 * 60 * 1000
GIT_TIMEOUT_MS = 60 * 1000
# The operator waits past the account's own bounds (the clone, the three git calls on a present copy at most,
# bootstrap), so a hung one is the account's verdict, not a silence.
CLONE_BUDGET_S = (CLONE_TIMEOUT_MS + 3 * GIT_TIMEOUT_MS + BOOTSTRAP_TIMEOUT_MS) // 1000 + 30
REASON_MAX = 300


def _failed(reason: str, **more: str) -> dict:
    return {"status": "failed", "reason": reason[:REASON_MAX], **more}


def _why(e: BaseException, what: str, timeout_ms: int) -> str:
    """One line for a program that did not finish, whichever way it did not: the five failures stay distinct."""
    if isinstance(e, subprocess.TimeoutExpired):
        return f"{what} did not finish within {util.whole(timeout_ms / 1000)} s"
    if isinstance(e, util.OutputOverflow):
        return f"{what} printed more than {MAX_BUFFER // 1048576} MiB"
    if isinstance(e, subprocess.CalledProcessError):
        if e.returncode < 0:
            return f"{what} was killed by {signal.Signals(-e.returncode).name}"
        return f"{what} exited {e.returncode}: {last_line(e)}"
    return f"{what} could not run: {util.node_error(e, [what])}"


def _env(home: str) -> dict[str, str]:
    """The daemon's environment for git: HOME is the account's, no GIT_* of the caller reaches a repository it
    was not meant for, and a prompt for a password is a failure, never a wait."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return {**env, "HOME": home, "GIT_TERMINAL_PROMPT": "0"}


def _git_value(run: Callable[..., Any], repo: str, key: str, env: dict[str, str]) -> str:
    """A config value of the clone, or "" for one that is absent or could not be read: a failed lookup is not a
    different URL, so the caller leaves the clone as it is."""
    try:
        r = run(["git", "-C", repo, "config", "--get", key], cwd=repo, env=env, timeout=GIT_TIMEOUT_MS / 1000, max_bytes=MAX_BUFFER)
    except (subprocess.SubprocessError, OSError):
        return ""
    return util.decode(r.stdout).strip("\n")


def clone(request: Any, root: str | None = None, home: str | None = None, run: Callable[..., Any] = util.run_bounded,
          clone_timeout_ms: int = CLONE_TIMEOUT_MS) -> dict:
    root = _CODE_ROOT if root is None else root
    home = os.path.expanduser("~") if home is None else home
    a = request.get("args") if isinstance(request, dict) else None
    pid = a.get("project") if isinstance(a, dict) and list(a) == ["project"] else None
    if not (isinstance(pid, str) and REGISTRY_ID.fullmatch(pid)):
        return {"status": "refused", "reason": "clone takes one argument, a project id"}
    try:
        with open(roots.projects_registry(engine=root), encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, ValueError) as e:
        return _failed(f"the registry could not be read: {util.node_error(e, ['registry'])}")
    remote = project_clone.registry_remote(text, pid)
    if remote is None:
        return {"status": "refused", "reason": f"the registry holds no project {pid} with a remote"}
    env = _env(home)
    parent = os.path.join(home, "projects")
    dest = os.path.join(parent, pid)
    try:
        os.makedirs(parent, exist_ok=True)
        present_dir = os.path.isdir(os.path.join(dest, ".git")) and not os.path.islink(dest)
        taken = os.path.lexists(dest)
    except OSError as e:
        return _failed(f"~/projects could not be read: {util.node_error(e, [parent])}")
    out: dict[str, Any] = {"project": pid, "remote": remote[:REASON_MAX]}
    if present_dir:
        out["status"] = "present"
        have = _git_value(run, dest, "remote.origin.url", env)
        plan = project_clone.plan_origin(remote, have, _git_value(run, dest, "remote.origin.pushurl", env) if have else "")
        if plan.action == "set":
            try:
                run(["git", "-C", dest, "remote", "set-url", "origin", remote], cwd=dest, env=env, timeout=GIT_TIMEOUT_MS / 1000, max_bytes=MAX_BUFFER)
            except (subprocess.SubprocessError, OSError) as e:
                return _failed(_why(e, "git remote set-url", GIT_TIMEOUT_MS), project=pid)
        out["origin"] = plan.action
        if plan.warning:
            out["warning"] = plan.warning[:REASON_MAX]
    elif taken:
        return _failed(f"~/projects/{pid} exists and is not a working copy; left as it is", project=pid)
    else:
        try:
            run(["git", "clone", "-q", "--", remote, dest], cwd=parent, env=env, timeout=clone_timeout_ms / 1000, max_bytes=MAX_BUFFER)
        except (subprocess.SubprocessError, OSError) as e:
            return _failed(_why(e, "git clone", clone_timeout_ms), project=pid)
        out["status"] = "cloned"
    try:
        # AGENT_FABRIC_DEFER_AGENTD_RESTART: bootstrap would restart this daemon in the middle of its own reply if it
        # found its unit changed; a clone changes no unit, and the fabric upgrade is what carries one.
        run(["bash", os.path.join(root, "runtime", "claude-code", "bootstrap.sh")], cwd=root,
            env={**env, "AGENT_FABRIC_DEFER_AGENTD_RESTART": "1"}, timeout=BOOTSTRAP_TIMEOUT_MS / 1000, max_bytes=MAX_BUFFER)
    except (subprocess.SubprocessError, OSError) as e:
        return _failed(f"{out['status']}, but " + _why(e, "bootstrap.sh", BOOTSTRAP_TIMEOUT_MS), project=pid)
    return out
