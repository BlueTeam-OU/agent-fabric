"""Fixtures shared by the tests of policies/githooks/ (Wave 9 batch 4): a scratch git repository with a controlled environment, and a
way to call the two sourced libraries (guarded-change.sh, locale-carve-out.sh) as the hooks do. Not a test: no AGENT_FABRIC_*,
GITHUB_*, CLAUDE_* or inherited git variable ever reaches a child, and every path a test writes is under its own temporary directory.

GITHOOKS_DIR names the directory under test (default policies/githooks), so one test file runs against the bash libraries today and
against their replacement later; the hooks themselves are always called by path, as git calls them."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITHOOKS_DIR = os.path.abspath(os.environ.get("GITHOOKS_DIR") or os.path.join(ROOT, "policies", "githooks"))
# PYTHONDONTWRITEBYTECODE: a hook runs the real tools/fabric modules through links, and Python would write __pycache__ beside them in the checkout
GIT_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


class Repo:
    """A scratch repository on branch main with one commit, under its own temporary directory."""

    def __init__(self, files: dict[str, str] | None = None, name: str = "repo"):
        self.root = tempfile.mkdtemp(prefix="githooks-test-")
        self.path = os.path.join(self.root, name)
        os.makedirs(self.path)
        self.git("init", "-q", "-b", "main")
        self.git("config", "commit.gpgsign", "false")      # the account's signing is not what these tests test
        for rel, text in (files or {"README": "r\n"}).items():
            self.write(rel, text)
        self.git("add", "-A")
        self.git("commit", "-qm", "base")

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def git(self, *args: str, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", self.path, *args], capture_output=True, text=True, timeout=120, check=check,
                              env={**GIT_ENV, "HOME": self.root, **(env or {})})

    def write(self, rel: str, text: str, append: bool = False) -> None:
        full = os.path.join(self.path, rel)
        # the checkout is never a scratch file: a path that resolves outside this repository's own temporary root is a test bug. Judged
        # BEFORE any directory is made (realpath resolves the links that exist and leaves the rest as written), or the refusal itself
        # would have created the directory beyond the link.
        if not os.path.realpath(full).startswith(os.path.realpath(self.root) + os.sep):
            raise AssertionError(f"{rel} resolves outside the scratch root: {os.path.realpath(full)}")
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "a" if append else "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, rel: str, text: str = "x\n", message: str = "c") -> None:
        self.write(rel, text, append=True)
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def stage(self, rel: str, text: str = "x\n") -> None:
        self.write(rel, text, append=True)
        self.git("add", "-A")

    def worktree(self, branch: str, name: str = "wt") -> "Repo":
        """A linked worktree of this repository on a new branch, under the same temporary root, so it goes with it. It shares the
        repository's config, core.hooksPath included, as a worktree of agent-fabric shares the clone's."""
        wt = Repo.__new__(Repo)
        wt.root, wt.path = self.root, os.path.join(self.root, name)
        self.git("worktree", "add", "-q", "-b", branch, wt.path)
        return wt


def call_library(lib: str, repo_path: str, script: str, *args: str, path: str = "/usr/bin:/bin", ceiling: str = "") -> subprocess.CompletedProcess:
    """`bash -c 'set -u; . LIB; SCRIPT' bash ARGS` from inside the repository: the way pre-commit and commit-msg source the library
    (with `set -uo pipefail` in force). `script` sees the library's functions and its variables."""
    return subprocess.run(["bash", "-c", f"set -uo pipefail; . \"{lib}\"; {script}", "bash", *args], cwd=repo_path, capture_output=True,
                          text=True, timeout=120,
                          env={**GIT_ENV, "PATH": path, "HOME": repo_path, **({"GIT_CEILING_DIRECTORIES": ceiling} if ceiling else {})})


# ---- a scratch fabric root, for the hooks themselves -------------------------------------------------------------------------------
# The hooks find the fabric from their own path (FABRIC_ROOT = two directories above the real path of the hook). A scratch root holds a
# COPY of the hooks under test, its own policies/authority.json, and symlinks to the real runtime/ and tools/, so a test chooses the
# owner role, the contributors and the layout without touching the checkout. The scratch root is itself a git repository when a test
# wants "agent-fabric itself"; a managed project is a second repository beside it.
import json  # noqa: E402
import pwd  # noqa: E402

# The login the HOOKS see is a fixed one: they ask `id -un`, and a stand-in `id` first on PATH answers LOGIN, so no test depends on the account
# that runs it (a CI runner, python-dev-01, a language-culture-ge login). The binding file is keyed by the real login, as runtime/identity.py
# reads it (from the password database, not from `id`). HOST is the first segment of a contributor branch, which contributors.py ignores.
LOGIN = "stub-dev-03"
HOST = "testhost"
REAL_LOGIN = pwd.getpwuid(os.geteuid()).pw_name
ID_STUB = '#!/bin/sh\nif [ "$1" = "-un" ]; then echo ' + LOGIN + '; else exec /usr/bin/id "$@"; fi\n'


class Fabric:
    def __init__(self, owner_role: str | None = "fabric-coordinator", contributors: list | None = None, authority_text: str | None = None,
                 link_tools: bool = True):
        self.root = tempfile.mkdtemp(prefix="githooks-fabric-")
        self.fabric = os.path.join(self.root, "fabric")
        self.hooks = os.path.join(self.fabric, "policies", "githooks")
        shutil.copytree(GITHOOKS_DIR, os.path.dirname(self.hooks) + "/githooks", symlinks=True)
        os.makedirs(os.path.join(self.fabric, "policies"), exist_ok=True)
        if link_tools:
            # runtime/ is linked whole; tools/fabric/ is a REAL directory of links to the real entries, so a test that stages a NEW file
            # under tools/fabric/ creates it in the scratch root and never writes through a link into the checkout (Repo.write refuses
            # any path that leaves its root).
            os.symlink(os.path.join(ROOT, "runtime"), os.path.join(self.fabric, "runtime"))
            os.makedirs(os.path.join(self.fabric, "tools", "fabric"))
            for entry in os.listdir(os.path.join(ROOT, "tools", "fabric")):
                os.symlink(os.path.join(ROOT, "tools", "fabric", entry), os.path.join(self.fabric, "tools", "fabric", entry))
        if authority_text is not None:
            self.write_authority_text(authority_text)
        elif owner_role is not None:
            doc: dict = {"role_definitions": {"role": owner_role, "holders": []}}
            if contributors is not None:
                doc["contributors"] = contributors
            self.write_authority_text(json.dumps(doc))
        self.state = os.path.join(self.root, "state")
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.home)
        self.stubs = os.path.join(self.root, "stubs")
        os.makedirs(self.stubs)
        with open(os.path.join(self.stubs, "id"), "w", encoding="utf-8") as fh:
            fh.write(ID_STUB)
        os.chmod(os.path.join(self.stubs, "id"), 0o755)
        self.repos: list[Repo] = []

    def write_authority_text(self, text: str) -> None:
        with open(os.path.join(self.fabric, "policies", "authority.json"), "w", encoding="utf-8") as fh:
            fh.write(text)

    def cleanup(self) -> None:
        for repo in self.repos:
            repo.cleanup()
        shutil.rmtree(self.root, ignore_errors=True)

    def project(self, name: str = "project", files: dict[str, str] | None = None, hooks: bool = True) -> Repo:
        """A managed-project repository beside the fabric (its toplevel is not the fabric root), hooks installed unless told not."""
        repo = Repo(files or {"src/a.txt": "code\n", ".agent-fabric/memory/backend-dev/workflow.md": "slice\n"}, name=name)
        self.repos.append(repo)
        self._adopt(repo, hooks)
        return repo

    def itself(self, files: dict[str, str] | None = None, branch: str = "main") -> Repo:
        """The fabric root as a git repository: "agent-fabric itself". The base commit carries policies/ and the two links."""
        repo = Repo.__new__(Repo)
        repo.root, repo.path = self.root, self.fabric
        repo.git("init", "-q", "-b", branch)
        repo.git("config", "commit.gpgsign", "false")
        for rel, text in (files or {"src/a.txt": "code\n"}).items():
            repo.write(rel, text)
        repo.git("add", "-A")
        repo.git("commit", "-qm", "base")
        self._adopt(repo, True)
        return repo

    def _adopt(self, repo: Repo, hooks: bool) -> None:
        repo.git("config", "user.email", "t@example.invalid")
        repo.git("config", "user.name", "t")
        if hooks:
            repo.git("config", "core.hooksPath", self.hooks)

    def bind(self, role: str | None) -> None:
        d = os.path.join(self.state, "agents", REAL_LOGIN)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "binding.json"), "w", encoding="utf-8") as fh:
            json.dump({"agent": REAL_LOGIN, "role": role}, fh)

    def unbind(self) -> None:
        shutil.rmtree(self.state, ignore_errors=True)

    def env(self, **extra: str) -> dict[str, str]:
        env = {**GIT_ENV, "HOME": self.home, "GIT_CONFIG_NOSYSTEM": "1", "AGENT_FABRIC_STATE_DIR": self.state,
               "PATH": f"{self.stubs}:{GIT_ENV['PATH']}"}
        env.update(extra)
        return env

    def hook(self, name: str, repo: Repo, *args: str, stdin: str = "", **extra: str) -> subprocess.CompletedProcess:
        """A hook run directly, from the repository, as git runs it: by path, in the repository's directory, with the hook's own arguments."""
        return subprocess.run([os.path.join(self.hooks, name), *args], cwd=repo.path, input=stdin, capture_output=True, text=True, timeout=120,
                              env=self.env(**extra))

    def commit(self, repo: Repo, message: str, *flags: str, **extra: str) -> subprocess.CompletedProcess:
        """`git commit` through the installed hooks, with the session's binding in the environment."""
        return subprocess.run(["git", "-C", repo.path, "commit", "-q", *flags, "-m", message], capture_output=True, text=True, timeout=120,
                              env=self.env(**extra))
