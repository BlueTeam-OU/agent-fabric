"""tests/jobs_world.py — the world `fabric-jobs switch` settles against (agent-fabric ADR-037 rule 10), for the suites that
use `next` as a way to take a job rather than to test the settling: every checkout has a bare origin with main pushed, the
memory directory changes before a switch, and a job without artifacts is given one gh calls merged before it is done."""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
from git_env import git_env  # noqa: E402 — tests/, the script's own directory

GH_REPO = "fixture-org/fixture-proj"
LANDED = f"{GH_REPO}#1"       # the pull request a fake gh calls merged


def seeded(path: str, origins: str) -> str:
    """A checkout of a new bare origin under `origins`, main pushed and origin/HEAD set."""
    bare = os.path.join(origins, os.path.basename(path) + ".git")
    os.makedirs(origins, exist_ok=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True, env=git_env())
    os.makedirs(path)
    for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "seed"], ["remote", "add", "origin", bare],
                 ["push", "-q", "origin", "main"], ["remote", "set-head", "origin", "main"]):
        subprocess.run(["git", "-C", path, *args], check=True, env=git_env())
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
