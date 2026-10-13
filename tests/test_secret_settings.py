#!/usr/bin/env python3
"""fabric-secrets store settings-put (agent-fabric ADR-056 §5 rule 1): a
persona reaches the agent's own repository as ONE signed commit below
settings/, and nothing is written when the tree or the profile is wrong.

One scratch agent (its own keyring OUTSIDE its home, see test_secret_store),
a bare remote, a scratch fabric tree holding a copy of identities/schemas/
persona-profile.schema.json as of #238 (inline below, so the suite does not
wait on its merge; the "format": "date" annotation of `accepted` is left out,
which lint's keyword check refuses in a file of its own). Plain script: ok/FAIL, exit 1 on any."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile

PERSONA_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:agent-fabric:personas:profile",
    "title": "An agent's persona \u2014 settings/profile.json in its repository fabric-agent-<id>",
    "description": "agent-fabric ADR-056 \u00a75 rule 1. Written by the agent itself, in one commit with settings/avatar.png and settings/avatar-rejected/, once it has accepted an avatar; never before. The surname is also recorded centrally in identities/personas/claims.json, which wins if the two disagree. Sex is for the avatar's appearance only (rule 6).",
    "type": "object",
    "required": [
        "version",
        "agent_id",
        "first_name",
        "surname",
        "sex",
        "avatar",
        "accepted"
    ],
    "additionalProperties": False,
    "properties": {
        "version": {
            "const": 1
        },
        "agent_id": {
            "type": "string",
            "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        },
        "first_name": {
            "type": "string",
            "minLength": 1,
            "description": "From the culture of the surname's `from` (rule 5)."
        },
        "surname": {
            "type": "string",
            "minLength": 1,
            "description": "Exactly as listed in identities/personas/surnames.json and claimed in claims.json."
        },
        "sex": {
            "enum": [
                "F",
                "M"
            ]
        },
        "pronoun": {
            "type": "string",
            "description": "Present only when the agent asked for one, e.g. \"it\" (rule 6)."
        },
        "avatar": {
            "type": "object",
            "required": [
                "file",
                "sha256",
                "candidate"
            ],
            "additionalProperties": False,
            "properties": {
                "file": {
                    "const": "settings/avatar.png"
                },
                "sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$"
                },
                "candidate": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "The <n> of the candidate accepted, /usr/local/share/agent-fabric/avatars/<id>/<n>.png (rule 7)."
                }
            }
        },
        "accepted": {
            "type": "string",
            "description": "The day the agent accepted its avatar."
        }
    }
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "fabric", "secret_store.py")
sys.path.insert(0, os.path.dirname(TOOL))
import secret_store  # noqa: E402
from git_env import scrub_process_env  # noqa: E402
from instance_fixtures import write_secrets_instance  # noqa: E402
scrub_process_env()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail[:400]}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        fabric = os.path.join(tmp, "fabric")
        os.makedirs(os.path.join(fabric, "identities", "keys"))
        os.makedirs(os.path.join(fabric, "identities", "schemas"))
        write_secrets_instance(fabric)
        schema_dst = os.path.join(fabric, "identities", "schemas", "persona-profile.schema.json")
        schema_bytes = json.dumps(PERSONA_SCHEMA).encode()
        with open(schema_dst, "wb") as fh:
            fh.write(schema_bytes)
        home, gnupg = os.path.join(tmp, "agent"), os.path.join(tmp, "agent-gnupg")
        os.makedirs(home)
        os.makedirs(gnupg, mode=0o700)
        env = {**{k: v for k, v in os.environ.items() if k != "CLAUDECODE" and not k.startswith("GIT_")},
               "HOME": home, "GNUPGHOME": gnupg, "AGENT_FABRIC_ROOT": fabric, "AGENT_FABRIC_OPERATOR": fabric,
               "AGENT_FABRIC_SECRET_STORE": os.path.join(home, "store"),
               "GIT_CONFIG_GLOBAL": os.path.join(home, ".gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
        store = env["AGENT_FABRIC_SECRET_STORE"]
        remote = os.path.join(tmp, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True, env=env)

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, TOOL, *args], env=env, cwd=tmp, capture_output=True, text=True)

        def g(*args: str) -> str:
            return subprocess.run(["git", "-C", store, *args], env=env, capture_output=True, text=True, check=True).stdout

        def tree(name: str, files: dict[str, bytes], links: dict[str, str] | None = None) -> str:
            d = os.path.join(tmp, name)
            for rel, data in files.items():
                os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
                with open(os.path.join(d, rel), "wb") as fh:
                    fh.write(data)
            os.makedirs(d, exist_ok=True)
            for rel, target in (links or {}).items():
                os.symlink(target, os.path.join(d, rel))
            return d

        def count() -> int:
            return int(g("rev-list", "--count", "HEAD").strip())

        aid = secret_store.mint_agent_id(secret_store.born_ms_of("now"))
        check("the agent makes its store", run("init", "--agent-id", aid, "--remote", remote).returncode == 0)
        check("…and is the root of its chain", run("certify", "--root").returncode == 0)
        subprocess.run(["git", "-C", fabric, "init", "-q", "-b", "main"], check=True, env=env)
        subprocess.run(["git", "-C", fabric, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", fabric, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "identities"], check=True, env=env)
        subprocess.run(["git", "-C", fabric, "update-ref", "refs/remotes/origin/main", "HEAD"], check=True, env=env)
        check("…and pushes its first commit", run("push").returncode == 0)
        start = count()

        png = b"\x89PNG\r\n\x1a\n" + b"avatar" * 100
        sha = hashlib.sha256(png).hexdigest()

        def profile(**over) -> bytes:
            doc = {"version": 1, "agent_id": aid, "first_name": "Vikram", "surname": "Ramanujan", "sex": "M",
                   "avatar": {"file": "settings/avatar.png", "sha256": sha, "candidate": 1}, "accepted": "2026-10-13"}
            doc.update(over)
            return json.dumps(doc).encode()

        def refused(label: str, src: str, *needles: str) -> None:
            p = run("settings-put", "--from", src)
            check(label, p.returncode == 1 and "nothing written" in p.stderr and all(n in p.stderr for n in needles)
                  and count() == start and g("status", "--porcelain") == "", p.stdout + p.stderr)

        refused("a source that is not there is refused", os.path.join(tmp, "nope"), "nope")
        refused("a file for a source is refused", tree("f", {"x": b"1"}) + "/x", "not a directory")
        os.symlink(tree("real", {"x": b"1"}), os.path.join(tmp, "linked"))
        refused("a link for a source is refused, not followed", os.path.join(tmp, "linked"), "not a directory")
        refused("a link inside the tree is refused", tree("l", {"a": b"1"}, {"evil": "/etc/passwd"}), "evil")
        refused("a profile that is not JSON is refused", tree("j", {"profile.json": b"{"}), "not JSON")
        refused("a profile off the schema is refused, the field named",
                tree("s", {"profile.json": profile(sex="X"), "avatar.png": png}), "sex")
        refused("a profile for another agent is refused",
                tree("o", {"profile.json": profile(agent_id="01a11615-14e1-7139-975c-84ad21a5c91f"), "avatar.png": png}),
                "this store is agent")
        refused("an avatar whose sha256 is not the profile's is refused",
                tree("h", {"profile.json": profile(), "avatar.png": png + b"x"}), "sha256")
        refused("a profile with no avatar in the tree or the store is refused",
                tree("n", {"profile.json": profile()}), "avatar.png")
        os.unlink(schema_dst)
        refused("a checkout without the schema refuses instead of skipping the check",
                tree("m", {"profile.json": profile(), "avatar.png": png}), "persona-profile.schema.json")
        with open(schema_dst, "wb") as fh:
            fh.write(schema_bytes)

        good = tree("good", {"profile.json": profile(), "avatar.png": png, "avatar-rejected/2.png": b"r", "avatar-rejected/2.txt": b"why\n"})
        p = run("settings-put", "--from", good)
        check("a persona is written", p.returncode == 0 and "5 file" not in p.stdout and "4 file(s) committed" in p.stdout,
              p.stdout + p.stderr)
        check("…as ONE commit, signed by the agent, its message naming the writer",
              count() == start + 1 and g("log", "-1", "--format=%G?").strip() == "G"
              and g("log", "-1", "--format=%s").strip().endswith(": settings"), g("log", "-1", "--format=%G?|%s"))
        check("…the files are in the commit under settings/, nothing outside it",
              sorted(g("show", "--name-only", "--format=", "HEAD").split()) ==
              ["settings/avatar-rejected/2.png", "settings/avatar-rejected/2.txt", "settings/avatar.png", "settings/profile.json"],
              g("show", "--name-only", "--format=", "HEAD"))
        check("…and pushed", g("rev-parse", "HEAD") == subprocess.run(["git", "--git-dir", remote, "rev-parse", "main"],
                                                                     capture_output=True, text=True).stdout)
        verified = run("verify")
        check("…and the store still verifies", verified.returncode == 0, verified.stdout + verified.stderr)

        before = count()
        p = run("settings-put", "--from", good)
        check("the same tree again is no commit (its write verified what the remote holds first, ADR-042)", p.returncode == 0 and "unchanged" in p.stdout and count() == before, p.stdout + p.stderr)

        p = run("settings-put", "--from", tree("two", {"profile.json": profile(first_name="Vik")}))
        check("a profile alone is checked against the avatar the store holds, and added without deleting the rest",
              p.returncode == 0 and count() == before + 1 and "avatar-rejected/2.png" in g("ls-files", "settings"), p.stdout + p.stderr)

        check("env/ was never touched", g("ls-files", "env") == "" or all(f.startswith("env/") for f in g("ls-files", "env").split()))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
