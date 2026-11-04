"""tools/fabric/project_clone.py — what placing a project's working copy on an account decides, shared by the two
callers that do it: provisioning's step 6 (provisioning/worker.py, as the account through sudo) and the control
agent's `clone` action (control/clone.py, as the account itself). Each caller runs its own git; the judgements
are here once, so the two cannot disagree about which remote a project has or when an origin is rewritten.

Pure: no subprocess, no environment, no account. Standard library only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


def ssh_remote(project: Any) -> str | None:
    """The SSH remote of a registry project entry (its first remote when it names none), or None for an entry
    that has no usable remote: an account holds keys for SSH, and the https remote is the fabric's own
    bootstrap clone only."""
    remotes = project.get("remotes") if isinstance(project, dict) else None
    if not isinstance(remotes, list) or not remotes or not all(isinstance(x, str) and x for x in remotes):
        return None
    return next((x for x in remotes if x.startswith("git@")), remotes[0])


def registry_remote(registry_text: str, pid: str) -> str | None:
    """The SSH remote the registry holds for `pid`, or None when it does not hold the project, has no remote for
    it or is not a registry. Unknown stays unknown: the caller refuses, it never guesses a URL."""
    try:
        projects = json.loads(registry_text).get("projects")
    except (ValueError, AttributeError):
        return None
    if not isinstance(projects, dict):
        return None
    return ssh_remote(projects.get(pid))


@dataclass(frozen=True)
class OriginPlan:
    """`action`: "none" (no remote to point at), "unreadable" (the clone's origin could not be read: left as it
    is), "keep" (already the registry's), "set" (rewrite it). `warning` is said beside any action."""
    action: str
    warning: str = ""


def plan_origin(remote: str, have: str, pushurl: str) -> OriginPlan:
    """What to do with the origin of a clone that is already there. It keeps the origin it was made with: step 4
    clones the fabric over https (the account has no key yet) and is then skipped as present, which would leave
    the account pushing to an origin it holds no credentials for. Only a URL that was read and differs is
    rewritten (`have` empty is a lookup that failed, not a different URL). `remote set-url` leaves a push URL of
    its own alone, so pushes would still go there: said, not rewritten (a hand-made setting is the person's)."""
    if not remote:
        return OriginPlan("none")
    if not have:
        return OriginPlan("unreadable")
    warning = f"origin has its own push URL {pushurl}; pushes still go there" if pushurl and pushurl != remote else ""
    return OriginPlan("keep" if have == remote else "set", warning)
