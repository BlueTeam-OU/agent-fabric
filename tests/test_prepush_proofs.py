#!/usr/bin/env python3
"""policies/githooks/pre-push and the timestamp proofs of ADR-057 §5 rule 4:
a real `git push` to a bare repository with the hook installed and commits
signed by bin/fabric-sign (a fake `ots`, no network). What is proved: the
proofs waiting in the spool become notes and refs/notes/fabric-ots goes with
the branch; two agents pushing to one remote merge their notes instead of the
second being refused; a remote that refuses the notes refuses the push; a
push with no proofs anywhere (history signed before fabric-sign) touches no
notes ref; the hook's own push of the notes ref is admitted as it is.

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from git_env import scrub_process_env  # noqa: E402
scrub_process_env()
from instance_fixtures import own_instance_tree, write_registry  # noqa: E402
from signing_fixture import drop_key, make_agent_key  # noqa: E402
from signing import notes, proof  # noqa: E402
own_instance_tree()

SIGN = os.path.join(HERE, "bin", "fabric-sign")
T = tempfile.mkdtemp(prefix="test_prepush_proofs.")
# Only the pre-push hook: the commit hooks fence roles and trailers, which is not what is tested here.
HOOKS = f"{T}/hooks"
os.makedirs(HOOKS)
os.symlink(os.path.join(HERE, "policies", "githooks", "pre-push"), f"{HOOKS}/pre-push")
GNUPG, PRIMARY, SUB = make_agent_key(T)
REMOTE = f"{T}/remote.git"
OPERATOR = f"{T}/operator"
FAKE_OTS = f"{T}/ots"
fails = 0

with open(FAKE_OTS, "w", encoding="utf-8") as f:
    f.write(f'''#!{sys.executable}
import hashlib, sys
path = sys.argv[-1]
open(path + ".ots", "wb").write({proof.MAGIC!r} + b"\\x01\\x08" + hashlib.sha256(open(path, "rb").read()).digest() + b"\\x00cal")
''')
os.chmod(FAKE_OTS, 0o755)


def check(label: str, good: bool, detail: str = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    print(f"  FAIL {label}: {detail}")


def env(agent: str) -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "HOME": f"{T}/home-{agent}", "LANG": "C.UTF-8", "GNUPGHOME": GNUPG,
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
            "AGENT_FABRIC_OPERATOR": OPERATOR, "AGENT_FABRIC_PYTHON": sys.executable,
            "FABRIC_SIGN_OTS": FAKE_OTS, "FABRIC_SIGN_SPOOL": f"{T}/spool-{agent}", "PYTHONDONTWRITEBYTECODE": "1"}


def git(agent: str, *args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", cwd or f"{T}/{agent}", *args], env=env(agent), capture_output=True, text=True, timeout=120)


def clone(agent: str) -> None:
    os.makedirs(f"{T}/home-{agent}", exist_ok=True)
    subprocess.run(["git", "clone", "-q", REMOTE, f"{T}/{agent}"], env=env(agent), check=True, capture_output=True, timeout=120)
    for k, v in (("core.hooksPath", HOOKS), ("notes.rewriteRef", notes.REF), ("gpg.program", SIGN),
                 ("user.signingkey", SUB + "!"), ("commit.gpgsign", "true")):
        git(agent, "config", k, v)


def commit(agent: str, name: str, signed: bool = True) -> str:
    with open(f"{T}/{agent}/{name}", "w", encoding="utf-8") as f:
        f.write(name + "\n")
    git(agent, "add", name)
    r = git(agent, "-c", f"commit.gpgsign={'true' if signed else 'false'}", "commit", "-q", "-m", name)
    assert r.returncode == 0, r.stderr
    return git(agent, "rev-parse", "HEAD").stdout.strip()


def remote_note(sha: str) -> bytes | None:
    p = subprocess.run(["git", "-C", REMOTE, "notes", f"--ref={notes.REF}", "show", sha], capture_output=True, timeout=30)
    return p.stdout if p.returncode == 0 else None


def remote_has_ref() -> bool:
    return subprocess.run(["git", "-C", REMOTE, "rev-parse", "--verify", "--quiet", notes.REF], capture_output=True, timeout=30).returncode == 0


def run() -> None:
    write_registry(f"{OPERATOR}/projects", {"projects": {"plain": {"remotes": [], "default_branch": "main"}}})
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", REMOTE], check=True, capture_output=True, env=env("a"))
    seed = f"{T}/seed"
    subprocess.run(["git", "clone", "-q", REMOTE, seed], check=True, capture_output=True, env=env("a"))
    with open(f"{seed}/README", "w") as f:
        f.write("r\n")
    for args in (["add", "README"], ["commit", "-q", "-m", "seed"], ["push", "-q", "origin", "main"]):
        subprocess.run(["git", "-C", seed, "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, env=env("a"))
    clone("a")
    clone("b")

    print("a signed commit and its proof go together")
    sha_a = commit("a", "one")
    waiting = os.listdir(f"{T}/spool-a")
    check("the proof waits in a's spool", len(waiting) == 1, str(waiting))
    r = git("a", "push", "-q", "origin", "HEAD:refs/heads/work-a")
    check("the push succeeds", r.returncode == 0, r.stderr)
    held = remote_note(sha_a)
    check("the remote holds the note for the pushed commit", held is not None and proof.matches(
        notes.commit_signature(git("a", "cat-file", "commit", sha_a).stdout.encode()) or b"", held or b""), str(held))
    check("the waiting proof is spent", os.listdir(f"{T}/spool-a") == [])

    print("a second agent pushes to the same remote")
    git("b", "fetch", "-q", "origin")
    sha_b = commit("b", "two")
    r = git("b", "push", "-q", "origin", "HEAD:refs/heads/work-b")
    check("its push is not refused for the notes a already pushed", r.returncode == 0, r.stderr)
    check("the remote holds both notes", remote_note(sha_a) is not None and remote_note(sha_b) is not None)
    r = git("a", "push", "-q", "origin", "HEAD:refs/heads/work-a2")
    check("a pushes again after b's notes moved the remote's ref: still fine", r.returncode == 0, r.stderr)

    print("the remote refuses the notes")
    hook = f"{REMOTE}/hooks/update"
    with open(hook, "w") as f:
        f.write('#!/bin/sh\ncase "$1" in refs/notes/*) echo "notes refused" >&2; exit 1;; esac\n')
    os.chmod(hook, 0o755)
    sha_c = commit("a", "three")
    r = git("a", "push", "-q", "origin", "HEAD:refs/heads/work-c")
    check("the push is refused, naming the notes ref", r.returncode != 0 and notes.REF in r.stderr, r.stderr)
    check("…and the branch did not arrive", git("a", "ls-remote", "origin", "refs/heads/work-c").stdout.strip() == "")
    os.unlink(hook)
    r = git("a", "push", "-q", "origin", "HEAD:refs/heads/work-c")
    check("positive control: without the refusal the same push passes and its note arrives",
          r.returncode == 0 and remote_note(sha_c) is not None, r.stderr)

    print("a push that only deletes")
    git("a", "push", "-q", "origin", "HEAD:refs/heads/work-del")
    git("a", "push", "-q", "origin", f":{notes.REF}")
    check("removes the notes ref and does not put it back", not remote_has_ref())
    r = git("a", "push", "-q", "origin", ":refs/heads/work-del")
    check("…also a branch deletion: admitted, and the notes ref stays removed", r.returncode == 0 and not remote_has_ref(), r.stderr)
    git("a", "push", "-q", "origin", "HEAD:refs/heads/work-del2")
    check("positive control: the next push of a branch restores it", remote_has_ref())

    print("a push that deletes one ref and adds another")
    sha_m = commit("a", "mixed")
    r = git("a", "push", "-q", "origin", f":{notes.REF}", "HEAD:refs/heads/work-mix")
    check("pushes no notes: the deletion succeeds and the ref stays removed", r.returncode == 0 and not remote_has_ref(), r.stderr)
    check("…and the branch arrived", git("a", "ls-remote", "origin", "refs/heads/work-mix").stdout.split()[:1] == [sha_m], "")
    git("a", "push", "-q", "origin", "HEAD:refs/heads/work-mix2")
    check("positive control: the next plain push restores the notes", remote_has_ref() and remote_note(sha_m) is not None)

    print("a note that holds another signature's proof")
    sha_s1 = commit("a", "stale-donor")
    subprocess.run([SIGN, "note", sha_s1], cwd=f"{T}/a", env=env("a"), capture_output=True, timeout=60, check=True)
    sha_s2 = commit("a", "stale-heir")
    for name in os.listdir(f"{T}/spool-a"):
        os.unlink(f"{T}/spool-a/{name}")
    git("a", "notes", f"--ref={notes.REF}", "copy", sha_s1, sha_s2)
    r = git("a", "push", "-q", "origin", "HEAD:refs/heads/work-stale")
    check("is not published, and the hook says it removed it",
          remote_note(sha_s2) is None and "removed" in r.stderr and git("a", "notes", f"--ref={notes.REF}", "list", sha_s2).returncode != 0, r.stderr)
    check("…while the donor's own note is", remote_note(sha_s1) is not None)

    print("a dry run")
    sha_d = commit("a", "dry")
    r = git("a", "push", "--dry-run", "-q", "origin", "HEAD:refs/heads/work-dry")
    check("changes nothing: no note, the proof still waiting, nothing on the remote",
          r.returncode == 0 and remote_note(sha_d) is None and len(os.listdir(f"{T}/spool-a")) == 1
          and git("a", "ls-remote", "origin", "refs/heads/work-dry").stdout.strip() == "", r.stderr)
    r = git("a", "push", "-q", "origin", "HEAD:refs/heads/work-dry")
    check("positive control: the real push attaches and pushes it", r.returncode == 0 and remote_note(sha_d) is not None, r.stderr)
    # git takes any unique prefix of a long option; each spelling is its own commit with its own waiting proof.
    for spelling in ("--dry", "--dry-r"):
        sha_p = commit("a", "dry" + spelling)
        waiting = len(os.listdir(f"{T}/spool-a"))
        r = git("a", "push", spelling, "-q", "origin", f"HEAD:refs/heads/work-dry{spelling}")
        check(f"{spelling} changes nothing either", r.returncode == 0 and remote_note(sha_p) is None
              and len(os.listdir(f"{T}/spool-a")) == waiting
              and git("a", "ls-remote", "origin", f"refs/heads/work-dry{spelling}").stdout.strip() == "", r.stderr)
        r = git("a", "push", "-q", "origin", f"HEAD:refs/heads/work-dry{spelling}")
        check(f"positive control: the real push after {spelling} pushes its note", r.returncode == 0 and remote_note(sha_p) is not None, r.stderr)

    print("a branch pushed as the notes ref's name")
    commit("b", "forged", signed=False)
    r = git("b", "push", "-f", "-q", "origin", "HEAD:" + notes.REF)
    check("is checked like any push: the unsigned commit is refused", r.returncode != 0 and remote_note(sha_a) is not None, r.stderr)
    git("b", "reset", "-q", "--hard", "HEAD~1")

    print("pushing the notes ref by itself")
    r = git("a", "push", "-q", "origin", notes.REF)
    check("is admitted", r.returncode == 0, r.stderr)

    print("history with no proof")
    shutil.rmtree(f"{T}/spool-b", ignore_errors=True)
    git("b", "update-ref", "-d", notes.REF)
    commit("b", "old", signed=False)
    git("b", "config", "commit.gpgsign", "false")
    r = git("b", "push", "-q", "origin", "HEAD:refs/heads/work-old")
    check("an unsigned commit is still refused by the signature rule", r.returncode != 0, r.stderr)
    git("b", "reset", "-q", "--hard", "HEAD~1")
    git("b", "config", "commit.gpgsign", "true")
    sha_b2 = commit("b", "plain-signed")
    os.unlink(f"{T}/spool-b/" + os.listdir(f"{T}/spool-b")[0])
    r = git("b", "push", "-q", "origin", "HEAD:refs/heads/work-b2")
    check("a signed commit whose proof is gone passes this hook (the checker judges proofs)", r.returncode == 0, r.stderr)
    check("…and no note is invented for it", remote_note(sha_b2) is None)


try:
    run()
finally:
    drop_key(GNUPG)
    shutil.rmtree(T, ignore_errors=True)
print(f"{fails} failed" if fails else "all passed")
sys.exit(1 if fails else 0)
