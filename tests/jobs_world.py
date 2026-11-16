"""tests/jobs_world.py — the world `fabric-jobs switch` settles against (agent-fabric ADR-037 rule 10), for the suites that
use `next` as a way to take a job rather than to test the settling: every checkout has a bare origin with main pushed, the
memory directory changes before a switch, and a job without artifacts is given one gh calls merged before it is done."""
from __future__ import annotations

import atexit
import contextlib
import datetime
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from unittest import mock
from git_env import git_env  # noqa: E402 — tests/, the script's own directory

GH_REPO = "fixture-org/fixture-proj"
LANDED = f"{GH_REPO}#1"       # the pull request a fake gh calls merged


_TEMPLATE: str | None = None


def _template() -> str:
    """One seeded checkout and its bare origin, built once per process: a world copies it (about 7 ms) instead of running six git
    commands (about 60 ms), and a suite makes hundreds of worlds. Removed when the process ends."""
    global _TEMPLATE
    if _TEMPLATE is None:
        root = tempfile.mkdtemp(prefix="jobs-world-template-")
        atexit.register(shutil.rmtree, root, True)
        bare, path = os.path.join(root, "origin.git"), os.path.join(root, "checkout")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True, env=git_env())
        os.makedirs(path)
        for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "seed"], ["remote", "add", "origin", bare],
                     ["push", "-q", "origin", "main"], ["remote", "set-head", "origin", "main"]):
            subprocess.run(["git", "-C", path, *args], check=True, env=git_env())
        _TEMPLATE = root
    return _TEMPLATE


def seeded(path: str, origins: str) -> str:
    """A checkout of a new bare origin under `origins`, main pushed and origin/HEAD set."""
    bare = os.path.join(origins, os.path.basename(path) + ".git")
    os.makedirs(origins, exist_ok=True)
    root = _template()
    shutil.copytree(os.path.join(root, "origin.git"), bare, symlinks=True)
    shutil.copytree(os.path.join(root, "checkout"), path, symlinks=True)
    # The copied checkout's origin is the template's absolute path: a world that pushed would write the template.
    subprocess.run(["git", "-C", path, "remote", "set-url", "origin", bare], check=True, env=git_env())
    return path


def identity_env() -> dict[str, str]:
    # CLAUDE_CONFIG_DIR names no directory: a switch runs fabric-branches --sweep, which removes the ended sessions' scratch under
    # $TMPDIR it finds in the harness's registry there; with none it keeps all, and the suite never touches this login's real cache.
    return {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org",
            "CLAUDE_CONFIG_DIR": "/nonexistent/claude-config"}


def touch_memory(home: str, working_copy: str) -> None:
    """A memory file written now, in the directory Claude Code keeps for `working_copy`."""
    d = os.path.join(home, ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(working_copy)), "memory")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "fact.md"), "w", encoding="utf-8") as fh:
        fh.write(str(datetime.datetime.now()))


def landed(state_dir: str, login: str, job_id: str) -> None:
    """Give a job without artifacts one that gh calls merged, so `done` has the evidence switch asks for; the log is not touched."""
    path = os.path.join(state_dir, "agents", login, "jobs.json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    for j in doc["jobs"]:
        if j["id"] == job_id and not j.get("artifacts"):
            j["artifacts"] = [LANDED]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


_JOBS = None
_SWEEP = None   # the leave_sweep module of the package _JOBS was loaded with: a suite that loads jobs.py again replaces sys.modules["fabric_jobs"]


def inprocess(env: dict[str, str], cwd: str, *argv: str, quiet_sweep: bool = False) -> subprocess.CompletedProcess:
    """`fabric-jobs <argv>` as jobs.main in this process under `env` (the whole environment) and `cwd`. A suite reads the list
    after nearly every verb, hundreds of times, and the command is two interpreter starts (bash, then Python) for each; the verbs
    the cases are about still run as the command. `quiet_sweep`: the sweep a switch runs on leaving a job is `branches.py` as a
    command (~0.85 s), here an empty script that exits 0; for the suites whose cases take a job with `next` and ask nothing
    of the sweep (tests/test_jobs_switch.py reads it as the command in its own section)."""
    global _JOBS, _SWEEP
    if _JOBS is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location("jobs_world_jobs", os.path.join(root, "tools", "fabric", "jobs.py"))
        _JOBS = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, env):
            spec.loader.exec_module(_JOBS)
        _SWEEP = sys.modules["fabric_jobs"].leave_sweep
    sweep = _SWEEP
    real_branches = sweep.BRANCHES
    if quiet_sweep:
        sweep.BRANCHES = _quiet_script()
    out, err, here = io.StringIO(), io.StringIO(), os.getcwd()
    try:
        os.chdir(cwd)
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = _JOBS.main(list(argv))
            except SystemExit as e:
                rc = e.code
    finally:
        os.chdir(here)
        sweep.BRANCHES = real_branches
    return subprocess.CompletedProcess(list(argv), rc if isinstance(rc, int) else (0 if rc is None else 1), out.getvalue(), err.getvalue())


_QUIET: str | None = None


def _quiet_script() -> str:
    global _QUIET
    if _QUIET is None:
        d = tempfile.mkdtemp(prefix="jobs-world-quiet-")
        atexit.register(shutil.rmtree, d, True)
        _QUIET = os.path.join(d, "quiet-branches.py")
        open(_QUIET, "w").close()
    return _QUIET


def listing(env: dict[str, str], cwd: str, *argv: str) -> str:
    """The stdout of `fabric-jobs list --all --json <argv>`, in process (inprocess)."""
    r = inprocess(env, cwd, "list", "--all", "--json", *argv)
    assert r.returncode == 0, f"fabric-jobs list exited {r.returncode}: {r.stderr}"
    return r.stdout
