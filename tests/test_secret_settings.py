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
import shutil
import stat
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
import secretstore.settings as S  # noqa: E402
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
            n0 = count()
            p = run("settings-put", "--from", src)
            check(label, p.returncode == 1 and "nothing written" in p.stderr and all(n in p.stderr for n in needles)
                  and count() == n0 and g("status", "--porcelain") == "", p.stdout + p.stderr)

        refused("a source that is not there is refused", os.path.join(tmp, "nope"), "nope")
        refused("a file for a source is refused", tree("f", {"x": b"1"}) + "/x", "not a directory")
        os.symlink(tree("real", {"x": b"1"}), os.path.join(tmp, "linked"))
        os.symlink(os.path.join(tmp, "real"), os.path.join(tmp, "linked-real"))
        # xonly grants search but not read, above the source:
        os.makedirs(os.path.join(tmp, "xonly", "inner"))
        with open(os.path.join(tmp, "xonly", "inner", "f"), "w") as fh:
            fh.write("1")
        os.chmod(os.path.join(tmp, "xonly"), 0o311)
        refused("a link for a source is refused, not followed", os.path.join(tmp, "linked"), "link is not followed")
        refused("a link for a source is refused with a trailing slash too", os.path.join(tmp, "linked") + "/", "link is not followed")
        refused("link/. is no way round the link either", os.path.join(tmp, "linked") + "/.", "link is not followed")
        os.makedirs(os.path.join(tmp, "real", "sub"))
        with open(os.path.join(tmp, "real", "sub", "a"), "w") as fh:
            fh.write("1")
        got = S._read_tree(os.path.join(tmp, "xonly", "inner"))
        check("a source below a directory that grants search but not read is read (ancestors are opened O_PATH)",
              got == {"f": b"1"}, repr(got))
        os.chmod(os.path.join(tmp, "xonly"), 0o755)
        refused("a link in an ANCESTOR of the source is refused too, not followed",
                os.path.join(tmp, "linked-real", "sub"), "in any component of the path")
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

        refused("a .gitignore in the tree is refused: it would drop files from the commit without a word",
                tree("gi", {".gitignore": b"note-*", "x": b"1"}), ".gitignore")
        fifo = tree("ff", {"a": b"1"})
        os.mkfifo(os.path.join(fifo, "pipe"))
        refused("a FIFO is refused, not opened and waited on", fifo, "pipe", "not a plain file")
        big = tree("big", {"a": b"1"})
        with open(os.path.join(big, "huge"), "wb") as fh:
            fh.truncate(16 * 1024 * 1024 + 1)
        refused("a file over the size cap is refused", big, "huge", "size cap")
        hl = tree("hl", {"a": b"1"})
        os.link(os.path.join(hl, "a"), os.path.join(tmp, "other-name-for-a"))
        refused("a file with several hard links is refused", hl, "hard links")
        deep = tree("dp", {"a": b"1"})
        nest = deep
        for i in range(20):
            nest = os.path.join(nest, "d")
        os.makedirs(nest)
        refused("a tree nested too deep is refused by name, not a traceback", deep, "nested deeper")
        refused("an empty tree is refused by name", tree("empty", {}), "no files")
        refused("profile.json as a directory is refused, not skipped", tree("pd", {"avatar.png": png, "profile.json/x": b"1"}),
                "profile.json", "plain file")
        many = tree("many", {f"f{i}": b"x" for i in range(1001)})
        refused("more files than the cap is refused", many, "more than")
        emptyprof = tree("ep", {"avatar.png": png})
        os.makedirs(os.path.join(emptyprof, "profile.json"))
        refused("an EMPTY profile.json directory is refused too", emptyprof, "profile.json", "plain file")
        locked = tree("lk", {"a": b"1", "locked/b": b"2"})
        os.chmod(os.path.join(locked, "locked"), 0)
        refused("an unreadable directory is refused by name, never skipped", locked, "locked")
        os.chmod(os.path.join(locked, "locked"), 0o700)

        # The race the path-based check lost: the entry is a plain file when it is looked at and a link
        # (or a FIFO) when it is opened. The lie below stands in for the swap; the open must still refuse.
        from unittest import mock
        secret = os.path.join(tmp, "private")
        with open(secret, "w") as fh:
            fh.write("agent's own file")
        swapped = tree("sw", {"keep": b"1"})
        os.symlink(secret, os.path.join(swapped, "x"))
        os.mkfifo(os.path.join(swapped, "y"))
        real_stat = os.stat

        def lying_stat(path, *a, dir_fd=None, follow_symlinks=True):
            r = real_stat(path, *a, dir_fd=dir_fd, follow_symlinks=follow_symlinks)
            if path in ("x", "y"):
                return os.stat_result((stat.S_IFREG | 0o644, *tuple(r)[1:]))
            return r
        for victim in ("x", "y"):
            only = tree(f"sw-{victim}", {"keep": b"1"})
            os.symlink(secret, os.path.join(only, "x")) if victim == "x" else os.mkfifo(os.path.join(only, "y"))
            with mock.patch.object(S.os, "stat", lying_stat):
                try:
                    got = S._read_tree(only)
                    check(f"{victim}: swapped in after the stat, it is refused at the open, never read", False, repr(got))
                except secret_store.StoreError as e:
                    check(f"{victim}: swapped in after the stat, it is refused at the open, never read",
                          victim in str(e) and "nothing written" in str(e), str(e))

        # The very first write fails (git would ignore the file): even the settings/ directory it made is gone.
        with open(os.path.join(store, ".git", "info", "exclude"), "a") as fh:
            fh.write("zz-*\n")
        p = run("settings-put", "--from", tree("first", {"zz-1": b"1"}))
        check("a failed FIRST write leaves no settings/ directory behind", p.returncode == 1 and "not staged" in p.stderr
              and not os.path.exists(os.path.join(store, "settings")), p.stdout + p.stderr)

        # No remote: the commit would reach no one, and the store's own helpers skip a missing remote silently.
        subprocess.run(["git", "-C", store, "remote", "remove", "origin"], check=True, env=env)
        refused("a store with no remote is refused, nothing written", tree("nr", {"a": b"1"}), "no remote")
        subprocess.run(["git", "-C", store, "remote", "add", "origin", remote], check=True, env=env)
        subprocess.run(["git", "-C", store, "fetch", "-q", "origin"], check=True, env=env)
        subprocess.run(["git", "-C", store, "branch", "-q", "--set-upstream-to=origin/main"], check=True, env=env)

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
        # The judgement a pull makes of this commit, made for real: a second clone whose HEAD is BEHIND the commit
        # (otherwise the function judges nothing and says "passes" for anything). The control, a commit signed by
        # another key, must be refused by the same call.
        from unittest import mock
        from secretstore.trust import _verify_incoming
        judge = os.path.join(tmp, "judge")
        subprocess.run(["git", "clone", "-q", remote, judge], check=True, env=env)
        tip = subprocess.run(["git", "-C", judge, "rev-parse", "HEAD"], capture_output=True, text=True, env=env).stdout.strip()
        base = subprocess.run(["git", "-C", judge, "rev-parse", "HEAD~1"], capture_output=True, text=True, env=env).stdout.strip()
        subprocess.run(["git", "-C", judge, "config", "agent-fabric.trustedbase", base], check=True, env=env)
        subprocess.run(["git", "-C", judge, "reset", "-q", "--hard", base], check=True, env=env)
        with mock.patch.dict(os.environ, env):
            try:
                verdict = _verify_incoming(judge, tip, aid)
            except secret_store.StoreError as e:
                verdict = f"refused: {e}"
        check("…and the store's own verify-on-pull accepts it: signed by the agent's key, a writer", verdict == tip, str(verdict))
        other = os.path.join(tmp, "other-gnupg")
        os.makedirs(other, mode=0o700)
        subprocess.run(["gpg", "--homedir", other, "--batch", "--passphrase", "", "--quick-gen-key", "stranger@example.org"],
                       check=True, env=env, capture_output=True)
        fpr = subprocess.run(["gpg", "--homedir", other, "--list-keys", "--with-colons"], capture_output=True, text=True,
                             env=env).stdout.split("fpr:::::::::")[1].split(":")[0]
        os.makedirs(os.path.join(judge, "settings"), exist_ok=True)
        with open(os.path.join(judge, "settings", "x"), "w") as fh:
            fh.write("1")
        genv = {**env, "GNUPGHOME": other}
        subprocess.run(["git", "-C", judge, "add", "-A"], check=True, env=genv)
        subprocess.run(["git", "-C", judge, "-c", "user.name=t", "-c", "user.email=t@t", f"-c", f"user.signingkey={fpr}",
                        "commit", "-q", "-S", "-m", "by another key"], check=True, env=genv)
        stranger = subprocess.run(["git", "-C", judge, "rev-parse", "HEAD"], capture_output=True, text=True, env=env).stdout.strip()
        subprocess.run(["git", "-C", judge, "config", "agent-fabric.trustedbase", tip], check=True, env=env)
        subprocess.run(["git", "-C", judge, "update-ref", "HEAD", tip], check=True, env=env)
        with mock.patch.dict(os.environ, env):
            try:
                _verify_incoming(judge, stranger, aid)
                control = "accepted"
            except secret_store.StoreError as e:
                control = f"refused: {e}"
        check("…and the same call refuses a commit signed by another key (the control: it can fail)",
              control.startswith("refused") and "no writer" in control, control)
        verified = run("verify")
        check("…and the store still verifies", verified.returncode == 0, verified.stdout + verified.stderr)

        before = count()
        p = run("settings-put", "--from", good)
        check("the same tree again is no commit (its write verified what the remote holds first, ADR-042)", p.returncode == 0 and "unchanged" in p.stdout and count() == before, p.stdout + p.stderr)

        p = run("settings-put", "--from", tree("two", {"profile.json": profile(first_name="Vik")}))
        check("a profile alone is checked against the avatar the store holds, and added without deleting the rest",
              p.returncode == 0 and count() == before + 1 and "avatar-rejected/2.png" in g("ls-files", "settings"), p.stdout + p.stderr)


        # The remote moves ahead (another clone of the same agent writes a new avatar): this run must catch up first
        # and judge against THAT avatar; a profile naming the old one is then refused.
        other_store = os.path.join(tmp, "store2")
        subprocess.run(["git", "clone", "-q", remote, other_store], check=True, env=env)
        subprocess.run(["git", "-C", other_store, "config", "agent-fabric.trustedbase",
                        g("config", "--local", "--get", "agent-fabric.trustedbase").strip()], check=True, env=env)
        env2 = {**env, "AGENT_FABRIC_SECRET_STORE": other_store}
        png2 = png + b"-second"
        newer = tree("newer", {"avatar.png": png2, "profile.json": profile(avatar={"file": "settings/avatar.png",
                    "sha256": hashlib.sha256(png2).hexdigest(), "candidate": 2})})
        p = subprocess.run([sys.executable, TOOL, "settings-put", "--from", newer], env=env2, cwd=tmp, capture_output=True, text=True)
        check("another clone of the agent moves the remote ahead", p.returncode == 0, p.stdout + p.stderr)
        n_ahead = count()
        p = run("settings-put", "--from", tree("stale", {"profile.json": profile()}))
        check("a profile naming the avatar this clone last saw is refused: the store caught up with the remote first",
              p.returncode == 1 and "sha256" in p.stderr and "avatar.png" in g("ls-files", "settings") and count() == n_ahead + 1,
              p.stdout + p.stderr + str(count()))
        p = run("settings-put", "--from", tree("fresh", {"profile.json": profile(avatar={"file": "settings/avatar.png",
                "sha256": hashlib.sha256(png2).hexdigest(), "candidate": 2})}))
        check("…and the profile that names the remote's avatar is taken, a fast-forward of the remote",
              p.returncode == 0 and g("rev-parse", "HEAD") == subprocess.run(["git", "--git-dir", remote, "rev-parse", "main"],
              capture_output=True, text=True).stdout
              and hashlib.sha256(subprocess.run(["git", "-C", store, "show", "HEAD:settings/avatar.png"], env=env,
                                                capture_output=True, check=True).stdout).hexdigest() == hashlib.sha256(png2).hexdigest(),
              p.stdout + p.stderr)
        refused("an avatar alone that the store's profile does not name is refused: the result is checked, not the tree",
                tree("av", {"avatar.png": png + b"new"}), "sha256")
        wrong = json.loads(profile())
        wrong["avatar"]["sha256"] = "0" * 64
        refused("a profile alone whose sha256 is not the store's avatar is refused",
                tree("pw", {"profile.json": json.dumps(wrong).encode()}), "sha256")

        # A plain file where the tree wants a directory: the write fails AFTER the first files were replaced, so the
        # reset has something to put back (a failure _read_tree can see would never reach the store).
        with open(os.path.join(store, "settings", "sub"), "w") as fh:
            fh.write("a file")
        subprocess.run(["git", "-C", store, "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", store, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "a plain file"], check=True, env=env)
        before_fail = count()
        broken = tree("brk", {"a-new.txt": b"1", "avatar-rejected/2.png": b"changed", "newdir/deeper/a": b"1", "sub/x": b"z"})
        p = run("settings-put", "--from", broken)
        check("a write that fails half way puts the store back: nothing staged, modified or left over",
              p.returncode == 1 and "nothing written" in p.stderr and "Traceback" not in p.stderr and g("status", "--porcelain",
              "--untracked-files=all") == "" and not os.path.exists(os.path.join(store, "settings", "a-new.txt"))
              and g("show", "HEAD:settings/avatar-rejected/2.png") == "r" and count() == before_fail, p.stderr[-900:])
        with open(os.path.join(store, "settings", "avatar-rejected", "2.png")) as fh:
            check("…and the file the failed run had replaced is the old one on disk", fh.read() == "r")
        check("…and the directories it made are gone too (a later file of that name is not blocked)",
              not os.path.exists(os.path.join(store, "settings", "newdir")))
        subprocess.run(["git", "-C", store, "reset", "-q", "--hard", "HEAD~1"], check=True, env=env)

        # An interrupt while the commit is being signed: the store goes back, nothing staged, nothing left on disk.
        n_int = count()
        with mock.patch.dict(os.environ, env), mock.patch.object(S, "_commit", side_effect=KeyboardInterrupt):
            try:
                S.settings_put(tree("intr", {"newdir2/a": b"1", "avatar-rejected/int.txt": b"i"}))
                outcome = "returned"
            except secret_store.StoreError as e:
                outcome = "interrupted" if "interrupted" in str(e) and "nothing written" in str(e) else str(e)
        check("an interrupt in the commit undoes the write: nothing staged, no file or directory left",
              outcome == "interrupted" and g("status", "--porcelain", "--untracked-files=all") == "" and count() == n_int
              and not os.path.exists(os.path.join(store, "settings", "newdir2")), outcome)

        # SIGTERM and SIGHUP while signing: the same undo as for Ctrl-C, ending as a one-line refusal, the handlers put back.
        import signal as _signal
        for sig in (_signal.SIGTERM, _signal.SIGHUP):
            n_term = count()
            before_handler = _signal.getsignal(sig)
            with mock.patch.dict(os.environ, env), mock.patch.object(S, "_commit", side_effect=lambda *a: os.kill(os.getpid(), sig)):
                try:
                    S.settings_put(tree(f"term{int(sig)}", {"avatar-rejected/term.txt": b"t"}))
                    outcome = "returned"
                except secret_store.StoreError as e:
                    outcome = "interrupted" if "interrupted" in str(e) and "nothing written" in str(e) else str(e)
            check(f"{sig.name} during the commit undoes the write like an interrupt, and the handler is put back",
                  outcome == "interrupted" and g("status", "--porcelain", "--untracked-files=all") == ""
                  and count() == n_term and _signal.getsignal(sig) == before_handler, outcome)

        # git commit killed by the signal leaves its index.lock: the undo must still succeed.
        lock_path = os.path.join(store, ".git", "index.lock")

        def killed_commit(*a):
            open(lock_path, "w").close()
            raise KeyboardInterrupt
        n_lock = count()
        with mock.patch.dict(os.environ, env), mock.patch.object(S, "_commit", side_effect=killed_commit):
            try:
                S.settings_put(tree("lockt", {"avatar-rejected/lock.txt": b"l"}))
                outcome = "returned"
            except secret_store.StoreError as e:
                outcome = "interrupted" if "interrupted" in str(e) and "nothing written" in str(e) else str(e)
        check("a stale index.lock left by the killed commit does not stop the undo",
              outcome == "interrupted" and not os.path.exists(lock_path)
              and g("status", "--porcelain", "--untracked-files=all") == "" and count() == n_lock, outcome)

        # A flagged file would be skipped by git add while the profile naming its hash is staged.
        subprocess.run(["git", "-C", store, "update-index", "--assume-unchanged", "settings/avatar.png"], check=True, env=env)
        p = run("settings-put", "--from", tree("flag", {"avatar-rejected/f.txt": b"f"}))
        check("an assume-unchanged file below settings/ is refused", p.returncode == 1 and "assume-unchanged" in p.stderr, p.stdout + p.stderr)
        subprocess.run(["git", "-C", store, "update-index", "--no-assume-unchanged", "settings/avatar.png"], check=True, env=env)

        # An interrupt AFTER the commit exists must not say "nothing written": the commit stands, the next run pushes it.
        n_after = count()
        with mock.patch.dict(os.environ, env), mock.patch.object(S.entries, "_after_commit", side_effect=KeyboardInterrupt):
            try:
                S.settings_put(tree("after-commit", {"avatar-rejected/after.txt": b"a"}))
                said = "returned"
            except secret_store.StoreError as e:
                said = str(e)
        check("an interrupt after the commit says it stands, never 'nothing written', and says Ctrl-C",
              count() == n_after + 1 and "after the commit was made" in said and "nothing written" not in said
              and "(Ctrl-C)" in said, said)
        p = run("settings-put", "--from", tree("after-commit", {"avatar-rejected/after.txt": b"a"}))
        check("…and the next run pushes it as no new commit", p.returncode == 0 and "unchanged" in p.stdout
              and g("rev-parse", "HEAD") == subprocess.run(["git", "--git-dir", remote, "rev-parse", "main"],
                                                           capture_output=True, text=True).stdout, p.stdout + p.stderr)
        with mock.patch.dict(os.environ, env), mock.patch.object(S, "_read_tree", side_effect=KeyboardInterrupt):
            try:
                S.settings_put(tree("readint", {"a": b"1"}))
                said = "returned"
            except secret_store.StoreError as e:
                said = str(e)
        check("Ctrl-C while the tree is read is the same one-line refusal", "interrupted (Ctrl-C)" in said and "nothing written" in said, said)
        saved = _signal.getsignal(_signal.SIGHUP)
        _signal.signal(_signal.SIGHUP, _signal.SIG_IGN)
        try:
            with mock.patch.dict(os.environ, env), mock.patch.object(S, "_put", side_effect=lambda f, s: _signal.getsignal(_signal.SIGHUP)):
                during = S.settings_put(tree("nohup", {"a": b"1"}))
        finally:
            _signal.signal(_signal.SIGHUP, saved)
        check("a caller that ignores SIGHUP (nohup) keeps ignoring it", during == _signal.SIG_IGN, repr(during))

        # A retained avatar whose COMMITTED bytes differ from its checkout while the store reads as clean (an invertible
        # smudge/clean pair): a profile alone that names the checkout's hash must be refused, judged from the blobs.
        rot = "tr 'a-zA-Z' 'n-za-mN-ZA-M'"
        subprocess.run(["git", "-C", store, "config", "filter.rot.smudge", rot], check=True, env=env)
        subprocess.run(["git", "-C", store, "config", "filter.rot.clean", rot], check=True, env=env)
        with open(os.path.join(store, ".git", "info", "attributes"), "w") as fh:
            fh.write("settings/avatar.png filter=rot\n")
        committed_png = subprocess.run(["git", "-C", store, "show", "HEAD:settings/avatar.png"], env=env, capture_output=True).stdout
        os.unlink(os.path.join(store, "settings", "avatar.png"))
        subprocess.run(["git", "-C", store, "checkout", "--", "settings/avatar.png"], check=True, env=env)
        with open(os.path.join(store, "settings", "avatar.png"), "rb") as fh:
            checkout_png = fh.read()
        check("(the smudge filter makes the checkout differ from the committed bytes while the store reads clean: the case is real)",
              checkout_png != committed_png and g("status", "--porcelain") == "")
        n_eol = count()
        p = run("settings-put", "--from", tree("eolp", {"profile.json": profile(avatar={"file": "settings/avatar.png",
                "sha256": hashlib.sha256(checkout_png).hexdigest(), "candidate": 1})}))
        check("a profile naming the checkout bytes of a retained avatar that git commits differently is refused",
              p.returncode == 1 and "sha256" in p.stderr and count() == n_eol, p.stdout + p.stderr)
        os.unlink(os.path.join(store, ".git", "info", "attributes"))
        subprocess.run(["git", "-C", store, "config", "--remove-section", "filter.rot"], check=True, env=env)
        os.unlink(os.path.join(store, "settings", "avatar.png"))
        subprocess.run(["git", "-C", store, "checkout", "--", "settings/avatar.png"], check=True, env=env)

        # A gitlink (submodule) below settings/: a destination inside it would be a write into another repository.
        sub_repo = os.path.join(tmp, "subrepo")
        subprocess.run(["git", "init", "-q", "-b", "main", sub_repo], check=True, env=env)
        subprocess.run(["git", "-C", sub_repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "commit", "-q", "--allow-empty", "-m", "s"], check=True, env=env)
        sub_oid = subprocess.run(["git", "-C", sub_repo, "rev-parse", "HEAD"], capture_output=True, text=True, env=env).stdout.strip()
        subprocess.run(["git", "clone", "-q", sub_repo, os.path.join(store, "settings", "subm")], check=True, env=env)
        subprocess.run(["git", "-C", store, "update-index", "--add", "--cacheinfo", f"160000,{sub_oid},settings/subm"], check=True, env=env)
        subprocess.run(["git", "-C", store, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "a gitlink"], check=True, env=env)
        n_sub = count()
        p = run("settings-put", "--from", tree("viasub", {"avatar-rejected/s.txt": b"s"}))
        check("a gitlink (submodule) below settings/ is refused, nothing written", p.returncode == 1 and "gitlink" in p.stderr
              and count() == n_sub, p.stdout + p.stderr)
        subprocess.run(["git", "-C", store, "reset", "-q", "--hard", "HEAD~1"], check=True, env=env)
        shutil.rmtree(os.path.join(store, "settings", "subm"), ignore_errors=True)

        # An interrupted catch-up rebase that left a rebase in progress and a stale lock: said, never hidden.
        class Reb:
            pass
        os.makedirs(os.path.join(store, ".git", "rebase-merge"), exist_ok=True)
        open(os.path.join(store, ".git", "index.lock"), "w").close()
        try:
            S._abort_rebase(store)
            said_reb = "no error"
        except secret_store.StoreError as e:
            said_reb = str(e)
        check("a rebase git cannot abort is said, not reported as undone", "middle of a rebase" in said_reb, said_reb)
        shutil.rmtree(os.path.join(store, ".git", "rebase-merge"), ignore_errors=True)
        if os.path.exists(os.path.join(store, ".git", "index.lock")):
            os.unlink(os.path.join(store, ".git", "index.lock"))

        # An inherited GIT_DIR (a hook's environment) must not point any git call of the command at another repository.
        other_repo = os.path.join(tmp, "elsewhere.git")
        subprocess.run(["git", "init", "-q", "--bare", other_repo], check=True, env=env)
        denv = {**env, "GIT_DIR": other_repo}
        p = subprocess.run([sys.executable, TOOL, "settings-put", "--from", tree("gitdir", {"avatar-rejected/gd.txt": b"g"})],
                           env=denv, cwd=tmp, capture_output=True, text=True)
        check("an inherited GIT_DIR does not misdirect the command (the staged blobs are read from the store)",
              p.returncode == 0 and "committed" in p.stdout, p.stdout + p.stderr)

        # A clean filter (autocrlf) would commit different bytes than the ones validated.
        subprocess.run(["git", "-C", store, "config", "core.autocrlf", "true"], check=True, env=env)
        n_crlf = count()
        p = run("settings-put", "--from", tree("crlf", {"avatar-rejected/crlf.txt": b"a\r\nb\r\n"}))
        check("a git filter that would change the staged bytes is refused, nothing written", p.returncode == 1
              and "filter" in p.stderr and count() == n_crlf and g("status", "--porcelain", "--untracked-files=all") == "", p.stdout + p.stderr)
        subprocess.run(["git", "-C", store, "config", "--unset", "core.autocrlf"], check=True, env=env)

        stray = os.path.join(store, "settings", "stray")
        with open(stray, "w") as fh:
            fh.write("not from the tree")
        n_stray = count()
        p = run("settings-put", "--from", tree("st", {"avatar-rejected/9.txt": b"9"}))
        check("an untracked file already below settings/ is refused, never swept into the commit",
              p.returncode == 1 and "untracked" in p.stderr and count() == n_stray, p.stdout + p.stderr)
        os.unlink(stray)
        with open(os.path.join(store, ".git", "info", "exclude"), "a") as fh:
            fh.write("note-*\n")
        hidden = os.path.join(store, "settings", "avatar-rejected", "note-1")
        with open(hidden, "w") as fh:
            fh.write("mine")
        p = run("settings-put", "--from", tree("ig2", {"avatar-rejected/note-1": b"theirs"}))
        check("an ignored file already below settings/ is refused, never overwritten",
              p.returncode == 1 and "ignored" in p.stderr and open(hidden).read() == "mine", p.stdout + p.stderr)
        os.unlink(hidden)
        p = run("settings-put", "--from", tree("after", {"avatar-rejected/3.txt": b"ok\n"}))
        check("…and the next write works", p.returncode == 0 and "committed" in p.stdout, p.stdout + p.stderr)

        # A push that failed leaves the commit local; the next run, with nothing new to write, catches it up.
        hook = os.path.join(remote, "hooks", "pre-receive")
        with open(hook, "w") as fh:
            fh.write("#!/bin/sh\nexit 1\n")
        os.chmod(hook, 0o755)
        later = tree("later", {"avatar-rejected/4.txt": b"4\n"})
        p = run("settings-put", "--from", later)
        local = g("rev-parse", "HEAD").strip()
        remote_head = subprocess.run(["git", "--git-dir", remote, "rev-parse", "main"], capture_output=True, text=True).stdout.strip()
        check("a refused push is an error and leaves the commit local", p.returncode != 0 and local != remote_head, p.stdout + p.stderr)
        os.unlink(hook)
        p = run("settings-put", "--from", later)
        remote_head = subprocess.run(["git", "--git-dir", remote, "rev-parse", "main"], capture_output=True, text=True).stdout.strip()
        check("…and the same tree again pushes it, as no new commit", p.returncode == 0 and "unchanged" in p.stdout
              and remote_head == g("rev-parse", "HEAD").strip(), p.stdout + p.stderr)

        # A .gitignore already committed in the store would drop new files from the commit unannounced.
        with open(os.path.join(store, "settings", ".gitignore"), "w") as fh:
            fh.write("note-*\n")
        subprocess.run(["git", "-C", store, "add", "-f", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", store, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "an ignore file"], check=True, env=env)
        n_ign = count()
        p = run("settings-put", "--from", tree("ign", {"avatar-rejected/note-1": b"x"}))
        check("a file git would ignore is refused, never reported as committed", p.returncode == 1
              and "not staged" in p.stderr and count() == n_ign and g("status", "--porcelain", "--untracked-files=all") == "",
              p.stdout + p.stderr)
        subprocess.run(["git", "-C", store, "reset", "-q", "--hard", "HEAD~1"], check=True, env=env)

        # settings/ itself a link in the store: the write would land outside it.
        outside = os.path.join(tmp, "outside")
        os.makedirs(outside)
        with open(os.path.join(outside, "victim"), "w") as fh:
            fh.write("ORIGINAL")
        subprocess.run(["git", "-C", store, "rm", "-r", "-q", "settings"], check=True, env=env)
        os.symlink(outside, os.path.join(store, "settings"))
        subprocess.run(["git", "-C", store, "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", store, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "settings is a link"], check=True, env=env)
        p = run("settings-put", "--from", tree("viaroot", {"victim": b"OVERWRITTEN"}))
        check("settings/ itself being a link is refused, and nothing outside the store is written",
              p.returncode == 1 and "is a link" in p.stderr and open(os.path.join(outside, "victim")).read() == "ORIGINAL",
              p.stdout + p.stderr)
        subprocess.run(["git", "-C", store, "reset", "-q", "--hard", "HEAD~1"], check=True, env=env)

        # A name that is not UTF-8 is written and staged like any other (no decode error half way).
        odd = os.path.join(tmp, "odd")
        os.makedirs(odd)
        with open(os.path.join(os.fsencode(odd), b"a\xff.txt"), "wb") as fh:
            fh.write(b"x")
        p = run("settings-put", "--from", odd)
        check("a file name that is not UTF-8 is committed, the store left clean", p.returncode == 0
              and g("status", "--porcelain", "--untracked-files=all") == "", p.stdout + p.stderr)

        # A link committed below settings/ in the store carries a write out of it: refused.
        os.symlink(secret, os.path.join(store, "settings", "trap"))
        subprocess.run(["git", "-C", store, "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", store, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "a link"], check=True, env=env)
        p = run("settings-put", "--from", tree("viatrap", {"trap": b"1"}))
        check("a path that is a link in the store is refused", p.returncode == 1 and "is a link" in p.stderr
              and open(secret).read() == "agent's own file", p.stdout + p.stderr)
        subprocess.run(["git", "-C", store, "reset", "-q", "--hard", "HEAD~1"], check=True, env=env)

        check("env/ is as the first commit left it: no settings write touched it",
              g("ls-tree", "-r", "HEAD", "env") == g("ls-tree", "-r", g("rev-list", "--max-parents=0", "HEAD").split()[0], "env"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
