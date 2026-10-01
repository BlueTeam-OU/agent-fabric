#!/usr/bin/env python3
"""Tests for tools/fabric/guards/agent_fabric_dir_authority.py's internals;
the behaviour is policies/test_check_agent_fabric_dir_authority.sh's, run
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
from guards import agent_fabric_dir_authority as da  # noqa: E402
from guards import common  # noqa: E402

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


def sh(cwd: str, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=env or GIT_ENV, check=True, capture_output=True,
                          text=True, timeout=60).stdout


def trailers(message: str) -> str:
    return subprocess.run(["git", "interpret-trailers", "--parse"], input=message, env=GIT_ENV, text=True,
                          capture_output=True, timeout=60).stdout


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    print("the locale pattern is the hooks' pattern")
    with open(os.path.join(HERE, "policies", "githooks", "locale-carve-out.sh")) as f:
        hook = f.read()
    check("the hook's regex is in the module, verbatim", da.LOCALE_PATH.pattern in hook)

    print("locale_carve_out_role")
    L = "identities/roles/language-culture/locale/ge/"
    check("one locale", da.locale_carve_out_role([L + "a.md", L + "b.md"]) == ("language-culture", "ge"))
    check("no path", da.locale_carve_out_role([]) is None)
    check("two suffixes", da.locale_carve_out_role([L + "a.md", L.replace("/ge/", "/ru/") + "a.md"]) is None)
    check("two roles", da.locale_carve_out_role([L + "a.md", "identities/roles/x/locale/ge/a.md"]) is None)
    check("deeper than the locale directory", da.locale_carve_out_role([L + "d/a.md"]) is None)
    check("one foreign path spoils it", da.locale_carve_out_role([L + "a.md", "README.md"]) is None)
    check("a prefix of the path does not match", da.locale_carve_out_role(["x/" + L + "a.md"]) is None)

    print("declared_role reads the trailer as awk -F': *' did")
    def role(msg: str) -> str:
        return da.declared_role(msg, trailers(msg))
    check("the trailer", role("s\n\nFabric-Role: fabric-coordinator\n") == "fabric-coordinator")
    check("any case", role("s\n\nfabric-ROLE: r\n") == "r")
    check("no space after the colon", role("s\n\nFabric-Role:r\n") == "r")
    check("the last one wins", role("s\n\nFabric-Role: a\nFabric-Role: b\n") == "b")
    check("none", role("s\n\nbody\n") == "")
    check("a value with a colon stops at it", role("s\n\nFabric-Role: a:b\n") == "a")
    check("a trailing space is part of the value", da.declared_role("", "Fabric-Role: r \n") == "r ")
    check("another key is not the role", role("s\n\nNot-Fabric-Role: r\n") == "")
    check("a role in the body is not a trailer", role("s\n\nFabric-Role: r\n\nmore\n") == "")

    print("owner_role_of")
    tmp = tempfile.mkdtemp(prefix="dir-authority-")
    try:
        top = os.path.join(tmp, "proj")
        sib = os.path.join(tmp, "agent-fabric")
        os.makedirs(os.path.join(top, "policies"))
        os.makedirs(os.path.join(sib, "policies"))
        check("the default", da.owner_role_of(top, {}, "main") == "fabric-coordinator")
        with open(os.path.join(sib, "policies", "authority.json"), "w") as f:
            json.dump({"role_definitions": {"role": "sibling"}}, f)
        check("the sibling checkout", da.owner_role_of(top, {}, "main") == "sibling")
        os.makedirs(os.path.join(tmp, "elsewhere", "policies"))
        with open(os.path.join(tmp, "elsewhere", "policies", "authority.json"), "w") as f:
            json.dump({"role_definitions": {"role": "named"}}, f)
        check("$AGENT_FABRIC_ROOT", da.owner_role_of(top, {"AGENT_FABRIC_ROOT": os.path.join(tmp, "elsewhere")}, "main")
              == "named")

        print("in agent-fabric itself the owner is the base's, never the branch's")
        fab = os.path.join(tmp, "fab")
        os.makedirs(os.path.join(fab, "policies"))
        sh(fab, "init", "-q", "-b", "main")
        sh(fab, "commit", "-q", "--allow-empty", "-m", "before the file")
        sh(fab, "tag", "before")
        with open(os.path.join(fab, "policies", "authority.json"), "w") as f:
            json.dump({"role_definitions": {"role": "base-owner"}}, f)
        sh(fab, "add", "-A")
        sh(fab, "commit", "-q", "-m", "base")
        sh(fab, "checkout", "-q", "-b", "h/intruder/feat/x")
        with open(os.path.join(fab, "policies", "authority.json"), "w") as f:
            json.dump({"role_definitions": {"role": "intruder"}}, f)
        sh(fab, "commit", "-qam", "name myself the owner")
        check("the branch's edit names nobody", da.owner_role_of(fab, {}, "main") == "base-owner")
        check("a base without the file: the default", da.owner_role_of(fab, {}, "before") == "fabric-coordinator")

        print("a branch that deletes the file keeps agent-fabric's scope (review of #72)")
        sh(fab, "rm", "-q", "policies/authority.json")
        with open(os.path.join(fab, "other.txt"), "w") as f:
            f.write("x\n")
        sh(fab, "add", "-A")
        sh(fab, "commit", "-qm", "delete the file, then change something else with no trailer")
        check("still agent-fabric itself", da.is_fabric_itself(fab, "main"))
        scope, commits = da.commits_to_examine(fab, "main")
        check("every commit is examined", scope == "agent-fabric itself" and len(commits) == 2)
        check("a base and a tree without the file: a managed project", not da.is_fabric_itself(fab, "before"))

        print("the run, end to end in a scratch managed project")
        rr = os.path.join(tmp, "p")
        os.mkdir(rr)
        sh(rr, "init", "-q", "-b", "main")
        sh(rr, "commit", "-q", "--allow-empty", "-m", "base")
        sh(rr, "checkout", "-q", "-b", "work")

        def commit(path: str, msg: str, author: str | None = None) -> None:
            full = os.path.join(rr, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "a") as f:
                f.write("x\n")
            sh(rr, "add", "-A")
            env = dict(GIT_ENV)
            if author:
                env["GIT_AUTHOR_NAME"] = author
            sh(rr, "commit", "-q", "-m", msg, env=env)

        def run(env: dict[str, str] | None = None) -> tuple[int, str, str]:
            out, er = io.StringIO(), io.StringIO()
            cwd = os.getcwd()
            os.chdir(rr)
            try:
                with redirect_stdout(out), redirect_stderr(er):
                    # A fabric with no authority.json: the default role, not
                    # whatever a sibling checkout beside the scratch says.
                    rc = da.run({**GIT_ENV, "AGENT_FABRIC_ROOT": os.path.join(tmp, "no-fabric"), **(env or {})})
            finally:
                os.chdir(cwd)
            return rc, out.getvalue(), er.getvalue()

        rc, o, _ = run()
        check("nothing under .agent-fabric/", rc == 0 and "no commit changes .agent-fabric/" in o)
        commit("src/a.py", "code")
        rc, o, _ = run()
        check("a commit outside .agent-fabric/ is not examined in a project", rc == 0)
        commit(".agent-fabric/memory/x.md", "slice")
        rc, _, e = run()
        check("an undeclared change is refused", rc == 1 and "[Fabric-Role: none]" in e)
        sh(rr, "reset", "-q", "--hard", "HEAD~1")
        commit(".agent-fabric/memory/x.md", "slice\n\nFabric-Role: fabric-coordinator")
        rc, o, _ = run()
        check("a declared change passes", rc == 0 and "1 commit(s)" in o)
        commit(".agent-fabric/memory/y.md", "slice\n\nFabric-Role: backend-dev")
        rc, _, e = run()
        check("another role is refused", rc == 1 and "[Fabric-Role: backend-dev]" in e)
        sh(rr, "reset", "-q", "--hard", "HEAD~1")

        commit(".agent-fabric/a.md", "tr\n\nFabric-Role: backend-dev")
        rc, _, _ = run()
        check("a role's own declaration is no carve-out outside a locale", rc == 1)
        sh(rr, "reset", "-q", "--hard", "HEAD~1")

        commit(".agent-fabric/w.md", "bump", author="dependabot[bot]")
        rc, _, _ = run()
        check("dependabot outside .github/workflows/ is refused", rc == 1)
        sh(rr, "reset", "-q", "--hard", "HEAD~1")

        print("merge commits are not examined; their parents are")
        sh(rr, "checkout", "-q", "-b", "side", "main")
        commit(".agent-fabric/s.md", "side\n\nFabric-Role: fabric-coordinator")
        sh(rr, "checkout", "-q", "work")
        sh(rr, "merge", "-q", "--no-ff", "-m", "merge without trailer", "side")
        rc, o, _ = run()
        check("only the declared side commit counts", rc == 0 and "2 commit(s)" in o)

        print("failing to list is a refusal, never a pass")
        rc, _, e = run({"AGENT_FABRIC_CHARTER_BASE": "nope", "GITHUB_BASE_REF": ""})
        check("an unresolvable caller base falls through to main", rc == 0)
        sh(rr, "branch", "-m", "main", "trunk")
        rc, o, _ = run()
        check("no base is not enforced, exit 0", rc == 0 and "NOT ENFORCED" in o)
        sh(rr, "branch", "-m", "trunk", "main")
        r = subprocess.run([sys.executable, "-c",
                            "import sys; sys.path.insert(0, sys.argv[1]);"
                            "from guards import common\n"
                            "def body():\n    raise common.Refused('x')\n"
                            "sys.exit(common.run_main('n', body))", os.path.join(HERE, "tools", "fabric")],
                           capture_output=True, text=True, timeout=60)
        rc = r.returncode if r.stderr == "n: x\n" else -1
        check("a Refused is exit 2", rc == 2)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                da.commits_to_examine(rr, "no-such-ref")
                refused = False
            except common.Refused:
                refused = True
        check("a rev-list that fails is refused", refused)

        print("agent-fabric itself examines every commit")
        rr = os.path.join(tmp, "self")
        os.mkdir(rr)
        sh(rr, "init", "-q", "-b", "main")
        commit("policies/authority.json", "base")
        sh(rr, "checkout", "-q", "-b", "work")
        commit("policies/notes.md", "auth\n\nFabric-Role: fabric-coordinator")
        commit("src/b.py", "code")
        rc, _, e = run()
        check("an undeclared commit anywhere is refused in agent-fabric itself", rc == 1 and "agent-fabric itself" in e)
        sh(rr, "reset", "-q", "--hard", "HEAD~1")
        commit("identities/roles/backend-dev/locale/ge/team.md", "tr\n\nFabric-Role: backend-dev")
        rc, o, _ = run()
        check("the locale carve-out, in agent-fabric itself", rc == 0 and "locale carve-out" in o)
        sh(rr, "reset", "-q", "--hard", "HEAD~1")
        commit("identities/roles/backend-dev/locale/ge/a.md", "tr\n\nFabric-Role: language-culture")
        rc, _, _ = run()
        check("another role's locale declaration is no carve-out", rc == 1)
        sh(rr, "reset", "-q", "--hard", "HEAD~1")
        commit(".github/workflows/ci.yml", "bump", author="dependabot[bot]")
        rc, o, _ = run()
        check("dependabot's workflows-only commit is carved out", rc == 0 and "action-pin carve-out" in o)
        commit(".github/workflows/ci.yml", "bump", author="dependabot[bot]")
        commit("src/c.py", "bump", author="dependabot[bot]")
        rc, _, _ = run()
        check("dependabot touching code is refused", rc == 1)
        sh(rr, "reset", "-q", "--hard", "HEAD~2")

        commit(".github/workflows/ci.yml", "bump", author="someone-else")
        rc, _, _ = run()
        check("a workflows-only commit by another author is refused", rc == 1)
        sh(rr, "reset", "-q", "--hard", "HEAD~1")

        # Path-limited listing drops merges by history simplification, so only
        # here, with every commit examined, does --no-merges have work to do.
        sh(rr, "checkout", "-q", "-b", "side", "main")
        commit("policies/notes.md", "side\n\nFabric-Role: fabric-coordinator")
        sh(rr, "checkout", "-q", "work")
        commit("policies/other.md", "own\n\nFabric-Role: fabric-coordinator")
        sh(rr, "merge", "-q", "--no-ff", "-m", "merge without trailer", "side")
        rc, o, _ = run()
        check("a merge commit is not examined in agent-fabric itself", rc == 0 and "4 commit(s)" in o)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("outside a repository it is exit 2")
    tmp = tempfile.mkdtemp(prefix="dir-authority-")
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "tools", "fabric", "guards", "agent_fabric_dir_authority.py")],
                           cwd=tmp, env={**GIT_ENV, "GIT_CEILING_DIRECTORIES": os.path.dirname(tmp)},
                           capture_output=True, text=True, timeout=60)
        check("exit 2 and one line", r.returncode == 2 and r.stderr.strip() == "check_agent_fabric_dir_authority: not inside a git repository")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
