#!/usr/bin/env python3
"""tools/fabric/bootstrap.py step 5c: the signing settings of a working copy
policies/signing.json covers (agent-fabric ADR-057 §5 rules 2-4).

A fixture fabric (its own bin/fabric-sign stand-in, policy and registry) and
scratch working copies; Bootstrap.signing is called as working_copy_hooks
calls it. What is proved: a covered copy gets gpg.format, both programs at
the account's linked fabric-sign, the key fabric-sign prints for the format
and commit.gpgsign; a second run changes nothing; an uncovered copy keeps
what it has; a key fabric-sign cannot give, a link that is not the fabric's,
a policy that cannot be read and a write that fails halfway each leave the
copy as it was; notes.rewriteRef for the proofs is removed and no other.

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from git_env import scrub_process_env  # noqa: E402
scrub_process_env()
import bootstrap  # noqa: E402

T = tempfile.mkdtemp(prefix="bsign.")
FABRIC = os.path.join(T, "fabric")
PROJECTS = os.path.join(T, "projects")
LOCAL_BIN = os.path.join(T, "bin")
LOG = os.path.join(T, "sign.log")
LINK = os.path.join(LOCAL_BIN, "fabric-sign")
SSH_KEY = "key::ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFixtureFixtureFixtureFixtureFixtureFix"
PGP_KEY = "0123456789ABCDEF0123456789ABCDEF01234567!"
REGISTRY = {"version": 1, "projects": {
    "widget": {"remotes": ["git@github.com:acme/widget.git"]},
    "moved": {"remotes": ["git@github.com:neworg/thing.git", "git@github.com:oldorg/thing.git"]},
    "other": {"remotes": ["git@github.com:acme/other.git"]},
}}
fails = 0


def check(label: str, good: bool, detail: object = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    print(f"  FAIL {label}: {detail}")


def put(path: str, content: str, mode: int | None = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if mode is not None:
        os.chmod(path, mode)


def policy(repos: dict) -> None:
    put(os.path.join(FABRIC, "policies", "signing.json"),
        json.dumps({"default": {"format": "ssh", "since": None}, "repositories": repos}))


def git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=60)


def cfg(repo: str, key: str) -> str | None:
    r = git(repo, "config", "--local", "--get-all", key)
    return r.stdout.strip() if r.returncode == 0 else None


def working_copy(name: str) -> str:
    wc = os.path.join(PROJECTS, name)
    os.makedirs(wc)
    subprocess.run(["git", "init", "-q", wc], check=True, capture_output=True)
    return wc


def run(wc: str, pid: str, dry: bool = False, b: bootstrap.Bootstrap | None = None) -> tuple[bootstrap.Bootstrap, str, str]:
    b = b or bootstrap.Bootstrap(PROJECTS, dry, root=FABRIC)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        b.signing(wc, pid, REGISTRY)
    return b, out.getvalue(), err.getvalue()


SETTINGS = ("gpg.format", "gpg.program", "gpg.ssh.program", "user.signingkey", "commit.gpgsign")


def main() -> None:
    for k in [k for k in os.environ if k.startswith("AGENT_FABRIC_")]:
        del os.environ[k]
    os.environ["AGENT_FABRIC_LOCAL_BIN"] = LOCAL_BIN
    os.environ["FAKE_SIGN_LOG"] = LOG
    # The stand-in prints what fabric-sign key prints for each format, or
    # fails as fabric-sign does without the account's key.
    put(os.path.join(FABRIC, "bin", "fabric-sign"),
        "#!/bin/sh\n"
        'echo "$*" >> "$FAKE_SIGN_LOG"\n'
        '[ "$FAKE_SIGN_FAIL" = 1 ] && { echo "fabric-sign key: no store key for this account" >&2; exit 1; }\n'
        f'[ "$2" = ssh ] && echo "{SSH_KEY}" || echo "{PGP_KEY}"\n', 0o755)
    put(os.path.join(FABRIC, "projects", "registry.json"), json.dumps(REGISTRY))
    os.makedirs(LOCAL_BIN)
    os.symlink(os.path.join(FABRIC, "bin", "fabric-sign"), LINK)
    policy({"acme/widget": {"format": "ssh", "since": None}, "oldorg/thing": {"format": "openpgp"}})

    print("a covered working copy")
    wc = working_copy("widget")
    b, out, err = run(wc, "widget")
    got = {k: cfg(wc, k) for k in SETTINGS}
    check("written: ssh, both programs at the linked fabric-sign, its key, commit.gpgsign",
          got == {"gpg.format": "ssh", "gpg.program": LINK, "gpg.ssh.program": LINK, "user.signingkey": SSH_KEY,
                  "commit.gpgsign": "true"}, got)
    check("...said with +, counted written", out.startswith(f"  +  {wc} (widget): signing = ssh") and b.changed == 1, out + err)
    check("...the key asked of fabric-sign key ssh", open(LOG).read().split("\n")[0] == "key ssh", open(LOG).read())
    b, out, err = run(wc, "widget")
    check("a second run: said =, nothing written", out == f"  =  {wc} (widget): signing (ssh)\n" and b.changed == 0
          and b.same == 1, out + err)
    git(wc, "config", "--local", "--add", "notes.rewriteRef", "refs/notes/commits")
    git(wc, "config", "--local", "--add", "notes.rewriteRef", "refs/notes/fabric-ots")
    b, out, err = run(wc, "widget")
    check("notes.rewriteRef for the proofs is removed, another kept (rule 4)",
          cfg(wc, "notes.rewriteRef") == "refs/notes/commits" and "notes.rewriteRef for the proofs removed" in out,
          (cfg(wc, "notes.rewriteRef"), out))

    print("the format is the policy's, under the project's any name")
    moved = working_copy("thing")
    b, out, err = run(moved, "moved")
    check("a repository named by its old remote is covered, in its format: openpgp",
          cfg(moved, "gpg.format") == "openpgp" and cfg(moved, "user.signingkey") == PGP_KEY, (out, err))
    policy({"acme/widget": {"format": "openpgp"}, "oldorg/thing": {"format": "openpgp"}})
    b, out, err = run(wc, "widget")
    check("a format changed in the policy is changed in the copy",
          cfg(wc, "gpg.format") == "openpgp" and cfg(wc, "user.signingkey") == PGP_KEY, (out, err))
    policy({"acme/widget": {"format": "ssh", "since": None}, "oldorg/thing": {"format": "openpgp"}})
    run(wc, "widget")

    print("what is left as it is")
    other = working_copy("other")
    git(other, "config", "--local", "gpg.program", "/usr/local/bin/ots-git-gpg-wrapper.sh")
    b, out, err = run(other, "other")
    check("an uncovered copy keeps its settings, and nothing is said",
          cfg(other, "gpg.program") == "/usr/local/bin/ots-git-gpg-wrapper.sh" and cfg(other, "gpg.format") is None
          and out == err == "" and b.changed == b.failed == 0, (out, err))
    fresh = working_copy("widget2")
    os.environ["FAKE_SIGN_FAIL"] = "1"
    b, out, err = run(fresh, "widget")
    del os.environ["FAKE_SIGN_FAIL"]
    check("a key fabric-sign cannot give: said, counted NOT written, nothing written",
          all(cfg(fresh, k) is None for k in SETTINGS) and "fabric-sign key ssh gave no key" in err
          and "no store key" in err and b.failed == 1, (out, err))
    os.remove(LINK)
    os.symlink("/usr/bin/true", LINK)
    b, out, err = run(fresh, "widget")
    check("a fabric-sign link that is not this fabric's: said, nothing written",
          all(cfg(fresh, k) is None for k in SETTINGS) and "is not this fabric's fabric-sign" in err and b.failed == 1,
          (out, err))
    os.remove(LINK)
    b, out, err = run(fresh, "widget", dry=True)
    check("a dry run: said +, nothing written (the link is made by the same run's step, not yet)",
          all(cfg(fresh, k) is None for k in SETTINGS) and out.startswith(f"  +  {fresh} (widget): signing = ssh"),
          (out, err))
    os.symlink(os.path.join(FABRIC, "bin", "fabric-sign"), LINK)

    b = bootstrap.Bootstrap(PROJECTS, False, root=FABRIC)
    real_set, calls = b.git_set, []

    def failing_set(repo: str, key: str, value: str) -> None:
        calls.append(key)
        if len(calls) == 3:
            raise bootstrap.Stop(1, "bootstrap: config locked")
        real_set(repo, key, value)
    b.git_set = failing_set
    git(fresh, "config", "--local", "gpg.program", "/old/program")
    b, out, err = run(fresh, "widget", b=b)
    check("a write that fails halfway: what was written is put back, said, counted NOT written",
          cfg(fresh, "gpg.program") == "/old/program" and cfg(fresh, "gpg.format") is None
          and cfg(fresh, "gpg.ssh.program") is None and "left as they were" in err and b.failed == 1,
          ({k: cfg(fresh, k) for k in SETTINGS}, out, err))

    put(os.path.join(FABRIC, "policies", "signing.json"), "{broken")
    b = bootstrap.Bootstrap(PROJECTS, False, root=FABRIC)
    b, out1, err1 = run(fresh, "widget", b=b)
    b, out2, err2 = run(wc, "widget", b=b)
    check("a policy that cannot be read: said once, counted once, no copy touched",
          err1.count("no working copy's signing settings written") == 1 and err2 == "" and b.failed == 1
          and cfg(fresh, "gpg.format") is None, (err1, err2))


try:
    main()
finally:
    shutil.rmtree(T, ignore_errors=True)
print("all passed" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
