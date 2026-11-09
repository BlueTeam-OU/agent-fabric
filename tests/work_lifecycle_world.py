"""tests/work_lifecycle_world.py — the world the test_work_lifecycle*.py suites pin the job lifecycle in (agent-fabric ADR-037).

One scratch state directory, one scratch HOME, a dead relay, a fake gh first on PATH and two checkouts with bare origins, so
`bin/fabric-jobs` runs as the real command and nothing reaches the login's own list, relay or GitHub. The environment is built
from scratch: no AGENT_FABRIC_*, GITHUB_* or CLAUDE_* variable of the session reaches the command, but those named below."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid

import jobs_world
from instance_fixtures import write_operator_projects

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "bin", "fabric-jobs")
GH_PROJECT = "fixture-proj"
OTHER_PROJECT = "other-proj"
OTHER_REPO = "fixture-org/other-proj"

# gh: a pull request's state is looked up in $FAKE_DIR/gh.json ({"states": {"<repo>#<n>": "MERGED"|"OPEN"|"CLOSED"}}); one the
# file does not list is an HTTP 404, which is what a lookup that cannot be told looks like.
FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
doc = json.load(open(os.path.join(os.environ["FAKE_DIR"], "gh.json")))
if a[:2] == ["pr", "list"]:
    print("[]")
elif a[:2] == ["pr", "view"] and "--repo" in a:
    key = a[a.index("--repo") + 1] + "#" + a[2]
    if key in doc["states"]:
        print(json.dumps({"state": doc["states"][key]}))
        sys.exit(0)
    sys.stderr.write("GraphQL: Could not resolve to a PullRequest (HTTP 404)\\n")
    sys.exit(1)
else:
    sys.stderr.write("fake gh: unsupported: " + " ".join(a) + "\\n")
    sys.exit(2)
"""


class World:
    """Built in setUp, removed by `close`. `run` is the command; `jobs` the list as stored; `put` writes it."""

    def __init__(self, session: str = "sess-A") -> None:
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="work-lifecycle-"))
        home = os.path.join(self.tmp, "home")
        self.fake = os.path.join(self.tmp, "fake")
        os.makedirs(home)
        os.makedirs(os.path.join(self.fake, "bin"))
        with open(os.path.join(self.fake, "bin", "gh"), "w", encoding="utf-8") as fh:
            fh.write(FAKE_GH)
        os.chmod(os.path.join(self.fake, "bin", "gh"), 0o755)
        self.gh_says({})
        dead = socket.socket()
        dead.bind(("127.0.0.1", 0))
        dead_url = f"http://127.0.0.1:{dead.getsockname()[1]}"
        dead.close()
        self.login = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
        host = socket.gethostname().split(".")[0]
        registry = os.path.join(self.tmp, "registry.json")
        with open(registry, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "hosts": {host: {"operator": "user"}},
                       "placement": {self.login: host, "user": host}}, fh)
        self.state = os.path.join(self.tmp, "state")
        # The journal (episodic.py) is the agent's own: it has no store without the agent id. A test's id, in a store of its own.
        store = os.path.join(self.tmp, "store")
        os.makedirs(store)
        with open(os.path.join(store, ".agent-id"), "w", encoding="utf-8") as fh:
            fh.write("01a0f782-7e06-7dee-811f-0a860ed93bf3\n")
        self.env = {
            "AGENT_FABRIC_SECRET_STORE": store,
            "PATH": os.path.join(self.fake, "bin") + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": home, "LANG": "C.UTF-8", "TMPDIR": self.tmp, "PYTHONDONTWRITEBYTECODE": "1",
            "AGENT_FABRIC_STATE_DIR": self.state, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_HOSTS_REGISTRY": registry,
            "CLAUDE_BRIDGE_URL": dead_url, "CLAUDE_BRIDGE_AUTH_TOKEN": "tok",
            "FABRIC_STATE_CHANNEL": "t:state:control", "FABRIC_CONTROL_CHANNEL": "t:control",
            "CLAUDE_CODE_SESSION_ID": session, "FAKE_DIR": self.fake, "GH_REPO": jobs_world.GH_REPO,
            "AGENT_FABRIC_OPERATOR": write_operator_projects(
                os.path.join(self.tmp, "operator"), {GH_PROJECT: [f"git@github.com:{jobs_world.GH_REPO}.git"],
                                                     OTHER_PROJECT: [f"git@github.com:{OTHER_REPO}.git"]}),
            **jobs_world.identity_env(),
        }
        origins = os.path.join(self.tmp, "origins")
        self.alpha = jobs_world.seeded(os.path.join(self.tmp, "alpha"), origins)
        self.beta = jobs_world.seeded(os.path.join(self.tmp, "beta"), origins)

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def gh_says(self, states: dict[str, str]) -> None:
        with open(os.path.join(self.fake, "gh.json"), "w", encoding="utf-8") as fh:
            json.dump({"states": states}, fh)

    def answer(self, request_id: str) -> None:
        """This login's journal holds a REPLY to `request_id` that the carrier accepted: the REQUEST is answered (rule 14, row R10)."""
        me = f"{socket.gethostname().split('.')[0]}/{self.login}"
        reply = str(uuid.uuid4())
        text = (f"[GZCOORD/1] REPLY\nFROM: {me}\nROLE: x\nPROJECT: p\nTO: peer/sender\nIN-REPLY-TO: {request_id}\n"
                f"MESSAGE-ID: {reply}\nSUBJECT: re\n\nREPLY:\nok\n")
        episodic = os.path.join(ROOT, "tools", "fabric", "episodic.py")
        for argv, given in ((["gzcoord-out-pending"], text), (["gzcoord-out-final", reply, "--state", "accepted"], None)):
            r = subprocess.run([sys.executable, episodic, *argv], env=self.env, input=given, capture_output=True, text=True, timeout=60)
            assert r.returncode == 0, r.stderr

    def run(self, *argv: str, cwd: str | None = None, session: str | None = None, extra_env: dict[str, str] | None = None,
            stdin: str | None = None) -> subprocess.CompletedProcess:
        env = {**self.env, **({"CLAUDE_CODE_SESSION_ID": session} if session else {}), **(extra_env or {})}
        return subprocess.run([JOBS, *argv], cwd=cwd or self.alpha, env=env, input=stdin, capture_output=True, text=True, timeout=120)

    @property
    def path(self) -> str:
        return os.path.join(self.state, "agents", self.login, "jobs.json")

    def jobs(self) -> list[dict]:
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)["jobs"]

    def job(self, job_id: str) -> dict:
        return next(j for j in self.jobs() if j["id"] == job_id)

    def put(self, mutate) -> None:
        """Edit the stored list as a writer other than fabric-jobs would (a seeded state, never a path under test)."""
        with open(self.path, encoding="utf-8") as fh:
            doc = json.load(fh)
        mutate(doc)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def add(self, title: str, **flags: str) -> str:
        argv = ["add", title, *(a for k, v in flags.items() for a in (f"--{k.replace('_', '-')}", v))]
        out = self.run(*argv)
        assert out.returncode == 0, out.stderr
        return out.stdout.split()[1]

    def switch(self, *argv: str, cwd: str | None = None, session: str | None = None) -> subprocess.CompletedProcess:
        """`switch` as the suites that use it as a way to take a job do: memory written in the copy first (settle asks for it)."""
        jobs_world.touch_memory(self.env["HOME"], cwd or self.alpha)
        return self.run("switch", *argv, cwd=cwd, session=session)
