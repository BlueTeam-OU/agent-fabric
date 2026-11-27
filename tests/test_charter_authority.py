#!/usr/bin/env python3
"""Tests for tools/fabric/guards/charter_authority.py and common.py's
internals; the behaviour is tests/test_check_charter_authority_cli.py's, run
against the shim (ADR-040 §5 rule 5)."""
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
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from guards import charter_authority as ca  # noqa: E402
from guards import common  # noqa: E402
from guards import contributors  # noqa: E402
import roots  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

# Commits made here must not read the caller's config (signing, hooks).
# Nothing of the runner's or the session's own: CI sets GITHUB_HEAD_REF and
# GITHUB_BASE_REF on a pull request, a launched session sets
# AGENT_FABRIC_ROOT, and a suite run from inside a git hook inherits
# GIT_DIR, GIT_INDEX_FILE and GIT_WORK_TREE, which would point the guard's
# git at the outer repository; inherited, any of them decides a case for
# its own reasons.
CLEAN = {k: v for k, v in os.environ.items()
         if not k.startswith(("GITHUB_", "AGENT_FABRIC_"))
         and k not in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")}
# The guards' git calls take the process's own environment, not a dict
# this test hands them: the repository-pointing ones leave it too.
for _k in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY"):
    os.environ.pop(_k, None)
GIT_ENV = {**CLEAN, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}


def sh(cwd: str, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True, timeout=60)


def sh_out(cwd: str, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True, text=True,
                          timeout=60).stdout.strip()


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    print("lines_of reads command output as mapfile -t does")
    check("empty is none", common.lines_of("") == [])
    check("a final newline is not a line", common.lines_of("a\nb\n") == ["a", "b"])
    check("an empty middle line stays", common.lines_of("a\n\nb") == ["a", "", "b"])
    check("only \\n splits", common.lines_of("a\x0bb c\n") == ["a\x0bb c"])

    print("role_of names a role only when it is a non-empty string")
    check("the committed name", common.role_of('{"role_definitions":{"role":"r1"}}') == "r1")
    for label, text in (("empty", '{"role_definitions":{"role":""}}'), ("a number", '{"role_definitions":{"role":5}}'),
                        ("null", '{"role_definitions":{"role":null}}'), ("not JSON", "{"),
                        ("no key", "{}"), ("a list at the top", "[]"), ("a string section", '{"role_definitions":"x"}')):
        check(f"{label} is None", common.role_of(text) is None)

    print("agent_of takes the second segment of <host>/<agent>/<type>/<desc>")
    check("the agent", ca.agent_of("h/web-dev-01/feat/x") == "web-dev-01")
    check("two segments name nobody", ca.agent_of("h/a") is None)
    check("one segment names nobody", ca.agent_of("main") is None)
    check("an empty second segment", ca.agent_of("h//feat/x") is None)
    check("more than four segments", ca.agent_of("h/a/feat/x/y") == "a")
    check("three segments count", ca.agent_of("h/a/x") == "a")

    print("holders_of fails closed")
    check("a list of strings", ca.holders_of('{"role_definitions":{"holders":["a","b"]}}') == ["a", "b"])
    check("a string names nobody", ca.holders_of('{"role_definitions":{"holders":"abc"}}') == [])
    check("a non-string entry names nobody", ca.holders_of('{"role_definitions":{"holders":["a",5]}}') == [])
    check("not JSON", ca.holders_of("nope") == [])
    check("a list at the top", ca.holders_of("[]") == [])
    check("no holders", ca.holders_of("{}") == [])
    check("a space is not a separator", ca.holders_of('{"role_definitions":{"holders":["a b"]}}') == ["a b"])

    print("is_holder: the list alone, never a login's name")
    check("listed", ca.is_holder("x", ["x"]))
    check("fabric-coordinator unlisted is not a holder", not ca.is_holder("fabric-coordinator", ["user"]))
    check("fabric-coordinator-2 unlisted is not a holder", not ca.is_holder("fabric-coordinator-2", ["user"]))
    check("nobody listed, nobody holds", not ca.is_holder("fabric-coordinator-02", []))
    check("a stranger", not ca.is_holder("web-dev-01", ["x"]))
    check("a `*` holder is not a glob", not ca.is_holder("web-dev-01", ["*"]))
    check("a holder is whole, not a prefix", not ca.is_holder("web-dev-01", ["web"]))

    print("the protected set")
    check("charter and brief are :(glob)", ":(glob)identities/roles/*/charter.md" in ca.PROTECTED
          and ":(glob)identities/roles/*/brief.md" in ca.PROTECTED)
    for p in ("identities/roles/catalog.json", ".agent-fabric/taxonomy.json", "projects/*/taxonomy.json",
              "routing/policies/*", "policies/authority.json"):
        check(p, p in ca.PROTECTED)

    print("base resolution, in a real repository")
    tmp = tempfile.mkdtemp(prefix="charter-authority-")
    try:
        repo = os.path.join(tmp, "r")
        os.mkdir(repo)
        sh(repo, "init", "-q", "-b", "main")
        sh(repo, "commit", "-q", "--allow-empty", "-m", "c0")
        sh(repo, "branch", "other")
        sh(repo, "update-ref", "refs/remotes/origin/rel", "HEAD")
        check("main", common.resolve_base(repo, {}) == "main")
        # Mutation: common.py:73 `"origin/main", "main"` -> `"main"` (a local main that has moved on is not the base)
        sh(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        sh(repo, "commit", "-q", "--allow-empty", "-m", "c1, local main moves past origin/main")
        check("origin/main before a local main that differs", common.resolve_base(repo, {}) == "origin/main")
        sh(repo, "update-ref", "-d", "refs/remotes/origin/main")
        check("the caller's ref first", common.resolve_base(repo, {"AGENT_FABRIC_CHARTER_BASE": "other"}) == "other")
        check("an unresolvable caller ref falls through",
              common.resolve_base(repo, {"AGENT_FABRIC_CHARTER_BASE": "nope"}) == "main")
        check("origin/<GITHUB_BASE_REF>", common.resolve_base(repo, {"GITHUB_BASE_REF": "rel"}) == "origin/rel")
        sh(repo, "branch", "-m", "main", "trunk")
        check("no base, no GITHUB_BASE_REF: none", common.resolve_base(repo, {}) is None)
        check("no base, a fetch that fails: none", common.resolve_base(repo, {"GITHUB_BASE_REF": "zz"}) is None)

        print("the run, end to end in a scratch repository")
        rr = os.path.join(tmp, "w")
        os.mkdir(rr)
        sh(rr, "init", "-q", "-b", "main")
        # The guard reads the base's list where the repository stores it: operator/policies/ with no operator exported.
        authority = os.path.join(rr, roots.git_path("policies", "authority.json", base=rr, environ={}))
        os.makedirs(os.path.dirname(authority))
        with open(authority, "w") as f:
            json.dump({"role_definitions": {"role": "fabric-coordinator", "holders": ["boss"]}}, f)
        sh(rr, "add", "-A")
        sh(rr, "commit", "-q", "-m", "base")
        sh(rr, "checkout", "-q", "-b", "h/web-dev-01/feat/x")
        os.makedirs(os.path.join(rr, "identities", "roles", "r"))
        with open(os.path.join(rr, "identities", "roles", "r", "charter.md"), "w") as f:
            f.write("x\n")
        sh(rr, "add", "-A")
        sh(rr, "commit", "-q", "-m", "charter")

        def run(**env: str) -> tuple[int, str, str]:
            out, er = io.StringIO(), io.StringIO()
            old = os.environ.copy()
            os.environ.clear()
            os.environ.update({**GIT_ENV, **env})
            try:
                with redirect_stdout(out), redirect_stderr(er):
                    rc = ca.run([rr], dict(os.environ))
            finally:
                os.environ.clear()
                os.environ.update(old)
            return rc, out.getvalue(), er.getvalue()

        rc, _, e = run()
        check("a non-holder's charter change is refused", rc == 1 and "web-dev-01" in e)
        print("the branch: the override, then the pull request's head, then HEAD")
        check("the override wins over GITHUB_HEAD_REF",
              ca.head_branch(rr, {"AGENT_FABRIC_CHARTER_BRANCH": "a/b/c/d", "GITHUB_HEAD_REF": "e/f/g/h"}) == "a/b/c/d")
        check("GITHUB_HEAD_REF wins over HEAD", ca.head_branch(rr, {"GITHUB_HEAD_REF": "e/f/g/h"}) == "e/f/g/h")
        check("an empty GITHUB_HEAD_REF (a push) falls to HEAD",
              ca.head_branch(rr, {"GITHUB_HEAD_REF": ""}) == sh_out(rr, "rev-parse", "--abbrev-ref", "HEAD"))
        rc, o, _ = run(AGENT_FABRIC_CHARTER_BRANCH="h/boss/feat/x")
        check("a listed holder passes", rc == 0 and "OK" in o)
        rc, o, _ = run(AGENT_FABRIC_CHARTER_BRANCH="gh-readonly-queue/main/pr-1-abc")
        check("the merge queue's ref is not enforced", rc == 0 and "not" in o)
        rc, o, _ = run(AGENT_FABRIC_CHARTER_BRANCH="HEAD")
        check("a detached HEAD is not enforced", rc == 0 and "not" in o and "'HEAD'" in o)
        rc, o, _ = run(AGENT_FABRIC_CHARTER_BRANCH="two/segments")
        check("an unknowable branch is not enforced", rc == 0 and "not knowable" in o)
        rc, o, _ = run(AGENT_FABRIC_CHARTER_BASE="main", AGENT_FABRIC_CHARTER_BRANCH="h/boss/feat/x")
        check("the base is read, not the branch's list", rc == 0)

        # The list is read from the BASE: a branch that adds itself is refused.
        with open(authority, "w") as f:
            json.dump({"role_definitions": {"role": "fabric-coordinator", "holders": ["boss", "web-dev-01"]}}, f)
        sh(rr, "add", "-A")
        sh(rr, "commit", "-q", "-m", "add self")
        rc, _, e = run()
        check("a branch cannot add itself to the holders", rc == 1)

        print("failing to diff is a refusal, never a pass")
        rc, _, e = run(AGENT_FABRIC_CHARTER_BASE="HEAD~5")
        check("an unresolvable base is skipped, then main is used", rc == 1)
        sh(rr, "checkout", "-q", "--orphan", "unrelated")
        sh(rr, "commit", "-q", "--allow-empty", "-m", "u")
        r = subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "guards", "charter_authority.py"), rr],
                           env={**GIT_ENV, "AGENT_FABRIC_CHARTER_BASE": "main"}, capture_output=True, text=True,
                           timeout=60)
        check("no merge base is exit 2", r.returncode == 2 and "cannot diff" in r.stderr)
        with redirect_stderr(io.StringIO()):
            rc = ca.run([os.path.join(tmp, "absent")], {})
        check("a missing root is exit 2", rc == 2)

        print("after move-plan step D the holders are the operator main's, or the guard refuses")
        opsrc, opclone = os.path.join(tmp, "op-src"), os.path.join(tmp, "op-clone")
        os.makedirs(os.path.join(opsrc, "policies"))
        sh(opsrc, "init", "-q", "-b", "main")
        with open(os.path.join(opsrc, "policies", "authority.json"), "w") as f:
            json.dump({"role_definitions": {"role": "fabric-coordinator", "holders": ["boss"]}}, f)
        sh(opsrc, "add", "-A")
        sh(opsrc, "commit", "-q", "-m", "the operator's authority")
        sh(tmp, "clone", "-q", opsrc, opclone)
        rr = os.path.join(tmp, "engine")
        os.makedirs(os.path.join(rr, os.path.dirname(contributors.ENGINE_MARKER)))
        sh(rr, "init", "-q", "-b", "main")
        with open(os.path.join(rr, contributors.ENGINE_MARKER), "w") as f:
            f.write("# the engine's code\n")
        sh(rr, "add", "-A")
        sh(rr, "commit", "-q", "-m", "base: the engine, no operator tree")
        sh(rr, "checkout", "-q", "-b", "h/web-dev-01/feat/x")
        # A definition the branch adds under operator/, with a list naming itself: neither is what is read.
        authority = os.path.join(rr, roots.git_path("policies", "authority.json", base=rr, environ={}))
        os.makedirs(os.path.join(rr, "operator", "identities", "roles", "r"))
        with open(os.path.join(rr, "operator", "identities", "roles", "r", "charter.md"), "w") as f:
            f.write("x\n")
        os.makedirs(os.path.dirname(authority), exist_ok=True)
        with open(authority, "w") as f:
            json.dump({"role_definitions": {"role": "fabric-coordinator", "holders": ["web-dev-01"]}}, f)
        sh(rr, "add", "-A")
        sh(rr, "commit", "-q", "-m", "charter, and a list naming me")
        op = {"AGENT_FABRIC_OPERATOR_GIT": opclone}
        rc, _, e = run(**op)
        check("a non-holder is refused by the operator's list, not the branch's", rc == 1 and "web-dev-01" in e)
        rc, o, _ = run(**op, AGENT_FABRIC_CHARTER_BRANCH="h/boss/feat/x")
        check("the operator's holder passes", rc == 0 and "OK" in o)
        for label, env in (("a missing operator repository", {"AGENT_FABRIC_OPERATOR_GIT": os.path.join(tmp, "op-nowhere")}),
                           ("a ref it does not have", {**op, "AGENT_FABRIC_OPERATOR_REF": "no-such-ref"})):
            try:
                rc, _, _ = run(**env, AGENT_FABRIC_CHARTER_BRANCH="h/boss/feat/x")
                said, status = f"exit {rc}", rc
            except common.Refused as refusal:
                said, status = str(refusal), common.refusal_status(refusal)
            check(f"{label}: refused, naming the read, under the operator's own status", "refuses rather than narrow" in said
                  and "operator repository" in said and "no holder can be named" in said and status == common.OPERATOR_UNREADABLE)
        nowhere = {"AGENT_FABRIC_OPERATOR_GIT": os.path.join(tmp, "op-nowhere")}

        def entry(**env: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "guards", "charter_authority.py"), rr],
                                  env={**GIT_ENV, "AGENT_FABRIC_CHARTER_BASE": "main", "AGENT_FABRIC_CHARTER_BRANCH": "h/boss/feat/x",
                                       **env}, capture_output=True, text=True, timeout=60)

        r = entry(**nowhere)
        check("…exit 4 from the entry, never 0 and never 2", r.returncode == 4 and "refuses rather than narrow" in r.stderr)
        # The base's own read that cannot run is any other refusal: exit 2, which a run gated elsewhere still counts.
        real_read = contributors.fabric_authority

        def base_unreadable(*_args: object, **_kw: object) -> None:
            raise contributors.AuthorityUnreadable("cannot ask git whether main has policies/authority.json (stand-in)")

        contributors.fabric_authority = base_unreadable
        try:
            try:
                run(**nowhere, AGENT_FABRIC_CHARTER_BRANCH="h/boss/feat/x")
                status = 0
            except common.Refused as refusal:
                status = common.refusal_status(refusal)
        finally:
            contributors.fabric_authority = real_read
        check("an authority read at the base that cannot run is exit 2, not the operator's status", status == 2)
        # The diff comes before the holders are read: with no merge base the refusal is the diff's, exit 2, though the
        # operator is unreadable too (review of #717, F7).
        sh(rr, "checkout", "-q", "--orphan", "h/boss/feat/unrelated")
        sh(rr, "commit", "-q", "--allow-empty", "-m", "no merge base with main")
        r = entry(**nowhere)
        check("no merge base, the operator unreadable as well: the diff's refusal, exit 2, not 4",
              r.returncode == 2 and "cannot diff" in r.stderr and "operator repository" not in r.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("a closed stdout ends the run as a killed pipe does")
    r = subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0, sys.argv[1]);"
                        "from guards import common;"
                        "sys.stdout.close = lambda: None\n"
                        "def body():\n    raise BrokenPipeError()\n"
                        "sys.exit(common.run_main('x', body))", os.path.join(HERE, "tools", "fabric")],
                       capture_output=True, timeout=60)
    check("141", r.returncode == 141)

    print("the shim is bash builtins only and hands over the root")
    with open(os.path.join(HERE, "policies", "check_charter_authority.sh")) as f:
        shim = f.read()
    check("exec of the module with the root, on the pinned Python",
          'exec "$py" "$here/../tools/fabric/guards/charter_authority.py" "$here/.."' in shim
          and 'py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"' in shim)

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
