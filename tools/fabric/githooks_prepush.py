#!/usr/bin/env python3
"""The decision behind policies/githooks/pre-push: may these refs be pushed?

A managed project's arm.json may carry a `direct` block (tools/fabric/github/
arm.py documents it): a holder of one of its roles pushes straight to the
project's default branch, except for a change to a file matching
`direct.pr_paths`, which still arrives as a pull request with the blind
review (agent-fabric ADR-019 §5 rule 1). fabric-pr arm never sees a direct
push, so this hook, at the keyboard, is the only place the rule is enforced.

A project that is not managed, or whose arm.json has no `direct` key, gets
no rule from here at all: exit 0, silent. Every other doubt about a managed
direct project refuses, because a boundary this hook could not read must not
read as absent. The one exception is a working copy whose project marker is
unusable: the project, and so the default branch, is unknown, so only a push
to main or master is refused there and every other ref passes.

A direct push must also be a fast-forward of the remote's tip, and it may not
add or change an executable file (mode 100755) whatever its name: pr_paths
matches names, the mode is what makes a file run.

Usage (git runs the hook with the remote's name and URL, ref lines on stdin):
    githooks_prepush.py <remote-name> <remote-url> < refs
Exit codes: 0 admitted, 1 refused (the reason on stderr)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import roots  # noqa: E402
import workingcopy  # noqa: E402

FABRIC_ROOT = os.path.dirname(os.path.dirname(HERE))
ZERO = re.compile(r"^0+\Z")
GIT_TIMEOUT_S = 60
BINDING_TIMEOUT_S = 10
EXECUTABLE = "100755"
# Without a project there is no registry default_branch to compare with, so
# both names git hosts use for it stand in.
UNKNOWN_PROJECT_DEFAULTS = ("refs/heads/main", "refs/heads/master")


class Refused(Exception):
    pass


def _git(*args: str) -> str:
    try:
        p = subprocess.run(["git", *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as e:
        raise Refused(f"git {args[0]} could not run ({type(e).__name__}: {e})") from None
    if p.returncode != 0:
        raise Refused(f"git {' '.join(args)} failed: {p.stderr.strip() or p.stdout.strip()}")
    return p.stdout


def _held_role() -> str:
    # The binding is read by identity.py alone, as pre-commit does, so the
    # hook and the commit fence cannot disagree about who holds which role.
    try:
        p = subprocess.run([sys.executable, os.path.join(FABRIC_ROOT, "runtime", "identity.py"), "--role"],
                           capture_output=True, text=True, check=False, timeout=BINDING_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise Refused(f"the session's role binding could not be read within {BINDING_TIMEOUT_S}s") from None
    return p.stdout.strip() if p.returncode == 0 else ""


def _direct_rules(project: str) -> dict | None:
    """The project's `direct` block, None when it has none (no arm.json
    included: such a project is not direct)."""
    path = roots.project_integration(project, "gh", "arm.json", engine=FABRIC_ROOT)
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise Refused(f"{path} cannot be read ({type(e).__name__}: {e})") from None
    direct = doc.get("direct") if isinstance(doc, dict) else None
    if direct is None:
        return None
    try:
        roles = direct["roles"]
        pr_paths = re.compile(direct["pr_paths"], re.I)
    except (KeyError, TypeError, re.error) as e:
        raise Refused(f"{path}: direct is not usable ({type(e).__name__}: {e})") from None
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise Refused(f"{path}: direct.roles must list role names")
    return {"roles": roles, "pr_paths": pr_paths}


def _fast_forward(branch: str, local: str, remote: str) -> None:
    # The diff of two tips says nothing about ancestry: a force push that
    # rewrites main would be judged only by what differs, so history that
    # the remote has and the push drops must be refused here.
    try:
        known = subprocess.run(["git", "cat-file", "-e", f"{remote}^{{commit}}"], capture_output=True,
                               timeout=GIT_TIMEOUT_S).returncode == 0
        if not known:
            raise Refused(f"the remote's {branch} ({remote[:12]}) is not in this clone: fetch first")
        rc = subprocess.run(["git", "merge-base", "--is-ancestor", remote, local], capture_output=True,
                            timeout=GIT_TIMEOUT_S).returncode
    except (OSError, subprocess.SubprocessError) as e:
        raise Refused(f"git could not check that the push fast-forwards {branch} ({type(e).__name__}: {e})") from None
    if rc != 0:
        raise Refused(f"this push does not fast-forward {branch} (the remote's {remote[:12]} is not an ancestor "
                      "of what is pushed): a direct push never rewrites the default branch")


def _changed(remote_name: str, branch: str, local: str, remote: str) -> list[tuple[str, str]]:
    """(path, new mode) of every file the pushed range adds or changes."""
    if ZERO.match(remote):
        # A branch the remote does not have yet: what it adds is measured
        # from where it leaves the remote's default branch. Without that
        # ref nothing says what is new, and a guess could admit a PR path.
        tracking = f"refs/remotes/{remote_name}/{branch}"
        try:
            base = _git("merge-base", tracking, local).strip()
        except Refused:
            raise Refused(f"cannot tell what a new {branch} adds: no merge base with {tracking} "
                          "(fetch the remote first)") from None
    else:
        base = remote
    out = _git("diff", "--raw", "--no-renames", "-z", f"{base}..{local}").split("\0")
    changed = []
    # -z --raw: ":<old mode> <new mode> <old sha> <new sha> <status>" NUL path NUL
    for meta, path in zip(out[0::2], out[1::2]):
        fields = meta.lstrip(":").split()
        if len(fields) == 5 and fields[4][:1] != "D":
            changed.append((path, fields[1]))
    return changed


def check(remote_name: str, lines: list[str]) -> None:
    try:
        info = workingcopy.resolve(os.getcwd())
    except SystemExit as e:
        # A bad marker hides the project, so it cannot hide a push to the
        # branch that might be a direct project's default; any other ref is
        # no business of this hook and must not be held hostage by the marker.
        if any(len(f) == 4 and f[2] in UNKNOWN_PROJECT_DEFAULTS for f in map(str.split, lines)):
            raise Refused(f"{e.code}\n  (the project is unknown, so a push to main or master cannot be "
                          "told from a direct project's default branch)") from None
        return
    project = info.get("project")
    if not project:
        return
    entry = (workingcopy.load_registry().get("projects") or {}).get(project) or {}
    rules = _direct_rules(project)
    if rules is None:
        return
    branch = entry.get("default_branch")
    if not branch:
        raise Refused(f"projects/registry.json gives {project} no default_branch")
    target = f"refs/heads/{branch}"
    for line in lines:
        fields = line.split()
        if len(fields) != 4 or fields[2] != target:
            continue
        _, local, _, remote = fields
        if ZERO.match(local):
            raise Refused(f"deleting {branch} is not a direct push: the default branch of {project} is not removed")
        held = _held_role()
        if held not in rules["roles"]:
            raise Refused(f"the direct push to {branch} is the {' / '.join(rules['roles'])} role's; this "
                          f"session's binding holds {held or '(no role bound)'}, and every other change "
                          "arrives as a pull request")
        if not ZERO.match(remote):
            _fast_forward(branch, local, remote)
        changed = _changed(remote_name, branch, local, remote)
        executable = [p for p, mode in changed if mode == EXECUTABLE]
        if executable:
            raise Refused(f"these files are executable (mode {EXECUTABLE}) and go by pull request "
                          f"(agent-fabric ADR-019 §5 rule 1, {project}), not by a direct push to {branch}:\n  "
                          + "\n  ".join(executable[:20]))
        pr = [p for p, _ in changed if rules["pr_paths"].search(p)]
        if pr:
            raise Refused(f"these files go by pull request (agent-fabric ADR-019 §5 rule 1, {project}'s "
                          f"arm.json direct.pr_paths), not by a direct push to {branch}:\n  "
                          + "\n  ".join(pr[:20]) + (f"\n  … ({len(pr)} files)" if len(pr) > 20 else ""))


def main(argv: list[str]) -> int:
    try:
        check(argv[1] if len(argv) > 1 else "origin", sys.stdin.read().splitlines())
    except Refused as e:
        print(f"pre-push: {e}", file=sys.stderr)
        return 1
    except SystemExit as e:
        # workingcopy.resolve raises SystemExit(message) on a bad marker.
        print(f"pre-push: {e.code}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:
        print(f"pre-push: the project's rules could not be read ({type(e).__name__}: {e})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
