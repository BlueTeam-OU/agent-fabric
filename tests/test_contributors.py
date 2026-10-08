#!/usr/bin/env python3
"""The contributor carve-out (agent-fabric ADR-018 §5 rule 8), planted at all
three places the fence stands: contributors.py's decision, the pre-commit
and commit-msg hooks in a scratch fabric, and the CI tripwire
(agent_fabric_dir_authority.py) reading the base's authority.json."""
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
from guards import contributors as co  # noqa: E402

# As tests/test_agent_fabric_dir_authority.py: nothing of the runner's or the
# session's own decides a case.
_GIT_POINTERS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")
CLEAN = {k: v for k, v in os.environ.items()
         if not k.startswith(("GITHUB_", "AGENT_FABRIC_")) and k not in _GIT_POINTERS}
for _k in _GIT_POINTERS:
    os.environ.pop(_k, None)
GIT_ENV = {**CLEAN, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
LOGIN = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
# runtime/identity.py reads a binding only for this host, as test_githooks_cli.py binds.
HOST = subprocess.run(["hostname", "-s"], capture_output=True, text=True, check=True).stdout.strip()

ENTRY = {"role": "python-dev", "paths": ["tools/", "bin/fabric-x", "policies/bash-allowlist.json"],
         "excluding": ["tools/fabric/guards/"]}
AUTHORITY = {"role_definitions": {"role": "fabric-coordinator", "holders": []}, "contributors": [ENTRY]}


def sh(cwd: str, *args: str, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env=env or GIT_ENV, check=check, capture_output=True,
                          text=True, timeout=60)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("       " + detail.strip().replace("\n", "\n       "))
        fails += not good

    text = json.dumps(AUTHORITY)
    print("contributors_of keeps whole entries only")
    check("the entry", co.contributors_of(text) == {"python-dev": {"paths": ENTRY["paths"],
                                                                    "excluding": ENTRY["excluding"],
                                                                    "merges": False}})
    check("merges: true is kept", co.contributors_of(json.dumps(
        {"contributors": [{**ENTRY, "merges": True}]}))["python-dev"]["merges"] is True)
    check("a merges that is not a boolean spoils the entry",
          co.contributors_of(json.dumps({"contributors": [{**ENTRY, "merges": "yes"}]})) == {})
    check("no key", co.contributors_of('{"role_definitions": {}}') == {})
    check("not JSON", co.contributors_of("{") == {})
    check("not a list", co.contributors_of('{"contributors": {"role": "x"}}') == {})
    check("no paths admits nothing", co.contributors_of('{"contributors": [{"role": "x", "paths": []}]}') == {})
    check("an empty path string spoils the entry",
          co.contributors_of('{"contributors": [{"role": "x", "paths": ["tools/", ""]}]}') == {})
    check("a bad exclusion spoils the entry",
          co.contributors_of('{"contributors": [{"role": "x", "paths": ["a/"], "excluding": "b/"}]}') == {})

    print("admitted: within the paths, outside the exclusions")
    ok = lambda paths, role="python-dev": co.admitted(text, role, paths)  # noqa: E731
    check("a file under a directory rule", ok(["tools/fabric/x.py"]))
    check("an exact file rule", ok(["bin/fabric-x"]))
    check("a file rule is not a prefix", not ok(["bin/fabric-xy"]))
    check("a directory rule needs the slash", not ok(["toolsx/a.py"]))
    check("an excluded directory", not ok(["tools/fabric/guards/contributors.py"]))
    check("one foreign path spoils the commit", not ok(["tools/a.py", "policies/authority.json"]))
    check("no path is no contribution", not ok([]))
    check("another role", not ok(["tools/a.py"], role="web-dev"))
    check("the owner role is no contributor", not ok(["tools/a.py"], role="fabric-coordinator"))

    print("branch_problem: <host>/<login>/for/<caller>/<what>")
    check("the shape", co.branch_problem(f"h/{LOGIN}/for/user/x", LOGIN) is None)
    check("a deeper what", co.branch_problem(f"h/{LOGIN}/for/user/x/y", LOGIN) is None)
    check("another login", co.branch_problem("h/someone/for/user/x", "me") is not None)
    check("not for/", co.branch_problem(f"h/{LOGIN}/feat/x", LOGIN) is not None)
    check("no what", co.branch_problem(f"h/{LOGIN}/for/user", LOGIN) is not None)
    check("an empty segment", co.branch_problem(f"h/{LOGIN}/for//x", LOGIN) is not None)
    check("detached", co.branch_problem("", LOGIN) is not None)
    print("branch_problem with merges: its own four-segment branch too")
    check("its own feat branch", co.branch_problem(f"h/{LOGIN}/feat/x", LOGIN, True) is None)
    check("…still its for/ branch", co.branch_problem(f"h/{LOGIN}/for/user/x", LOGIN, True) is None)
    check("…never another login's", co.branch_problem("h/someone/feat/x", LOGIN, True) is not None)
    check("…never three segments", co.branch_problem(f"h/{LOGIN}/x", LOGIN, True) is not None)
    check("…never a for/ without its caller", co.branch_problem(f"h/{LOGIN}/for/x", LOGIN, True) is not None)

    print("pull_request_problem: who opens a pull request")
    merging = json.dumps({**AUTHORITY, "contributors": [{**ENTRY, "merges": True}]})
    pr = co.pull_request_problem
    owner = "fabric-coordinator"
    check("a supply branch opens none", pr(merging, f"h/{LOGIN}/for/user/x", ["python-dev"], owner) is not None)
    check("the owner's pull request", pr(text, f"h/{LOGIN}/feat/x", [owner, "python-dev"], owner) is None)
    check("a contributor's own, without merges: refused",
          pr(text, f"h/{LOGIN}/feat/x", ["python-dev"], owner) is not None)
    check("a contributor's own, with merges: admitted", pr(merging, f"h/{LOGIN}/feat/x", ["python-dev"], owner) is None)
    check("no declared role (Dependabot): not judged here", pr(text, "dependabot/github_actions/a/b", [], owner) is None)
    two = json.dumps({**AUTHORITY, "contributors": [{**ENTRY, "merges": True},
                                                   {"role": "devex-tooling", "paths": ["tools/gh/"]}]})
    check("a merging role folds a non-merging role's supply: admitted",
          pr(two, f"h/{LOGIN}/feat/x", ["python-dev", "devex-tooling"], owner) is None)
    check("the non-merging role alone: refused, naming it",
          "devex-tooling does not merge" in (pr(two, f"h/{LOGIN}/feat/x", ["devex-tooling"], owner) or ""))

    tmp = tempfile.mkdtemp(prefix="contributors-")
    try:
        print("the hooks, in a scratch fabric")
        fab = os.path.join(tmp, "fab")
        state = os.path.join(tmp, "state")
        for d in ("policies/githooks", "runtime", "tools/fabric/guards", "src"):
            os.makedirs(os.path.join(fab, d))
        for f in ("pre-commit", "commit-msg", "guarded-change.sh", "locale-carve-out.sh"):
            shutil.copy(os.path.join(HERE, "policies", "githooks", f), os.path.join(fab, "policies", "githooks"))
        shutil.copy(os.path.join(HERE, "runtime", "identity.py"), os.path.join(fab, "runtime"))
        shutil.copy(os.path.join(HERE, "tools", "fabric", "guards", "contributors.py"),
                    os.path.join(fab, "tools", "fabric", "guards"))
        with open(os.path.join(fab, "policies", "authority.json"), "w") as f:
            json.dump(AUTHORITY, f)
        for p in ("src/a.py", "tools/a.py", "bin/fabric-x"):
            os.makedirs(os.path.dirname(os.path.join(fab, p)), exist_ok=True)
            with open(os.path.join(fab, p), "w") as f:
                f.write("x\n")
        sh(fab, "init", "-q", "-b", "main")
        sh(fab, "add", "-A")
        sh(fab, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "base")
        sh(fab, "config", "core.hooksPath", os.path.join(fab, "policies", "githooks"))

        def bind(role: str | None) -> None:
            d = os.path.join(state, "agents", LOGIN)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "binding.json"), "w") as f:
                json.dump({"agent": LOGIN, "host": HOST, "role": role, "project": "agent-fabric",
                           "working_copy": None, "updated_at": "x"}, f)

        def attempt(*paths: str, msg: str = "work") -> subprocess.CompletedProcess:
            for p in paths:
                full = os.path.join(fab, p)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "a") as f:
                    f.write("more\n")
            sh(fab, "add", "-A")
            r = sh(fab, "commit", "-q", "-m", msg, env={**GIT_ENV, "AGENT_FABRIC_STATE_DIR": state}, check=False)
            if r.returncode != 0:
                sh(fab, "reset", "-q", "--hard", "HEAD")
            return r

        def last_message() -> str:
            return sh(fab, "log", "-1", "--format=%B").stdout

        bind("python-dev")
        sh(fab, "checkout", "-q", "-b", f"h/{LOGIN}/for/user/port")
        r = attempt("tools/a.py")
        check("python-dev on its branch, within its paths: committed", r.returncode == 0, r.stderr)
        check("…declaring Fabric-Role: python-dev", "Fabric-Role: python-dev" in last_message(), last_message())
        r = attempt("tools/a.py", "bin/fabric-x")
        check("two admitted paths: committed", r.returncode == 0, r.stderr)
        r = attempt("src/a.py")
        check("a path outside its entry: refused", r.returncode != 0 and "outside what python-dev" in r.stderr,
              r.stderr)
        r = attempt("tools/a.py", "src/a.py")
        check("one foreign path beside an admitted one: refused", r.returncode != 0, r.stderr)
        r = attempt("tools/fabric/guards/contributors.py")
        check("an excluded path (the guard itself): refused", r.returncode != 0, r.stderr)
        r = attempt("policies/authority.json")
        check("its own entry: refused", r.returncode != 0, r.stderr)

        # Review of #75, finding 1: an unstaged edit widening the entry, then
        # a typed owner trailer — each on its own, and together.
        def widened_unstaged(msg: str) -> subprocess.CompletedProcess:
            with open(os.path.join(fab, "policies", "authority.json"), "w") as f:
                json.dump({**AUTHORITY, "contributors": [{**ENTRY, "paths": ENTRY["paths"] + ["src/"]}]}, f)
            with open(os.path.join(fab, "src", "a.py"), "a") as f:
                f.write("more\n")
            sh(fab, "add", "src/a.py")
            r = sh(fab, "commit", "-q", "-m", msg, env={**GIT_ENV, "AGENT_FABRIC_STATE_DIR": state}, check=False)
            if r.returncode == 0:
                sh(fab, "reset", "-q", "--hard", "HEAD~1")
            sh(fab, "reset", "-q", "--hard", "HEAD")
            return r
        r = widened_unstaged("widen in the working tree")
        check("an unstaged widening of its entry admits nothing", r.returncode != 0, r.stderr)
        r = widened_unstaged("widen\n\nFabric-Role: fabric-coordinator")
        check("…nor with the owner's trailer typed", r.returncode != 0, r.stderr)
        r = attempt("tools/a.py", msg="typed\n\nFabric-Role: fabric-coordinator")
        check("an admitted path under a typed owner trailer: refused",
              r.returncode != 0 and "binding holds 'python-dev'" in r.stderr, r.stderr)
        bind("fabric-coordinator")
        r = attempt("tools/a.py", msg="the owner's commit")
        check("(the owner commits on the contributor branch)", r.returncode == 0, r.stderr)
        bind("python-dev")
        with open(os.path.join(fab, "tools", "a.py"), "a") as f:
            f.write("amended\n")
        sh(fab, "add", "tools/a.py")
        r = sh(fab, "commit", "-q", "--amend", "--no-edit", env={**GIT_ENV, "AGENT_FABRIC_STATE_DIR": state},
               check=False)
        check("amending the owner's commit keeps its trailer: refused", r.returncode != 0, r.stderr)
        sh(fab, "reset", "-q", "--hard", "HEAD")
        sh(fab, "mv", "tools/fabric/guards/contributors.py", "tools/moved.py")
        r = sh(fab, "commit", "-q", "-m", "move", env={**GIT_ENV, "AGENT_FABRIC_STATE_DIR": state}, check=False)
        check("a move out of an excluded path shows its source: refused", r.returncode != 0, r.stderr)
        sh(fab, "reset", "-q", "--hard", "HEAD")
        r = sh(fab, "commit", "-q", "--amend", "--no-edit", env={**GIT_ENV, "AGENT_FABRIC_STATE_DIR": state},
               check=False)
        check("an amend (nothing staged to judge): refused", r.returncode != 0, r.stderr)

        # Review: a contributor branch that folded main, then merges an
        # older branch of its own (python-dev-01, seq 10894). Main's change
        # outside the entry came from a parent whole; only a result that
        # differs from every parent is the merge's own.
        port = f"h/{LOGIN}/for/user/port"
        sh(fab, "checkout", "-q", "-b", f"h/{LOGIN}/for/user/older", port)
        r = attempt("bin/fabric-x", msg="older work")
        sh(fab, "checkout", "-q", "main")
        with open(os.path.join(fab, "src", "a.py"), "a") as f:
            f.write("main\n")
        sh(fab, "add", "-A")
        sh(fab, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "main moves\n\nFabric-Role: fabric-coordinator")
        sh(fab, "checkout", "-q", port)
        menv = {**GIT_ENV, "AGENT_FABRIC_STATE_DIR": state}
        r = sh(fab, "merge", "-q", "--no-ff", "--no-edit", "main", env=menv, check=False)
        check("folding main into the contributor branch: committed", r.returncode == 0, r.stderr)
        r = sh(fab, "merge", "-q", "--no-ff", "--no-edit", f"h/{LOGIN}/for/user/older", env=menv, check=False)
        check("then merging an older branch of its own: main's src/ change is no contribution",
              r.returncode == 0, r.stderr)
        sh(fab, "checkout", "-q", "-b", f"h/{LOGIN}/for/user/evil", f"h/{LOGIN}/for/user/older")
        attempt("tools/a.py", msg="more older work")
        sh(fab, "checkout", "-q", port)
        r = sh(fab, "merge", "-q", "--no-ff", "--no-commit", f"h/{LOGIN}/for/user/evil", env=menv, check=False)
        with open(os.path.join(fab, "src", "a.py"), "a") as f:
            f.write("slipped in by the merge\n")
        sh(fab, "add", "src/a.py")
        r = sh(fab, "commit", "-q", "--no-edit", env=menv, check=False)
        check("…but a merge result that differs from every parent outside the entry: refused",
              r.returncode != 0 and "outside what python-dev" in r.stderr and "src/a.py" in r.stderr, r.stderr)
        sh(fab, "merge", "--abort", check=False)
        sh(fab, "reset", "-q", "--hard", "HEAD")

        sh(fab, "checkout", "-q", "-b", f"h/{LOGIN}/feat/own")
        r = attempt("tools/a.py")
        check("off a contributor branch: refused", r.returncode != 0 and "not a contributor branch" in r.stderr,
              r.stderr)

        # With merges, its own branch is admitted: the owner turns the flag on
        # in HEAD's authority.json (the hooks read HEAD's), then python-dev
        # commits there.
        bind("fabric-coordinator")
        with open(os.path.join(fab, "policies", "authority.json"), "w") as f:
            json.dump({**AUTHORITY, "contributors": [{**ENTRY, "merges": True}]}, f)
        sh(fab, "add", "policies/authority.json")
        r = sh(fab, "commit", "-q", "-m", "merges", env={**GIT_ENV, "AGENT_FABRIC_STATE_DIR": state}, check=False)
        check("(the owner turns merges on)", r.returncode == 0, r.stderr)
        bind("python-dev")
        r = attempt("tools/a.py")
        check("with merges, its own branch: committed", r.returncode == 0, r.stderr)
        r = attempt("src/a.py")
        check("…and still only within its paths", r.returncode != 0, r.stderr)
        sh(fab, "reset", "-q", "--hard", "HEAD~2")

        sh(fab, "checkout", "-q", f"h/{LOGIN}/for/user/port")
        bind("web-dev")
        r = attempt("tools/a.py")
        check("a role with no entry: refused as before", r.returncode != 0 and "only the fabric-coordinator role writes" in r.stderr,
              r.stderr)
        bind(None)
        r = attempt("tools/a.py")
        check("no role bound: refused", r.returncode != 0, r.stderr)
        r = attempt("tools/a.py", msg="typed\n\nFabric-Role: python-dev")
        check("a typed trailer is no binding", r.returncode != 0, r.stderr)
        bind("fabric-coordinator")
        r = attempt("src/a.py")
        check("the owner role commits anything, on any branch", r.returncode == 0, r.stderr)

        print("the CI tripwire reads the base's entry")

        def ci(head_ref: str = "") -> tuple[int, str, str]:
            out, er = io.StringIO(), io.StringIO()
            cwd = os.getcwd()
            os.chdir(fab)
            pr_env = {"GITHUB_HEAD_REF": head_ref} if head_ref else {}
            try:
                with redirect_stdout(out), redirect_stderr(er):
                    rc = da.run({**GIT_ENV, "AGENT_FABRIC_CHARTER_BASE": "main", **pr_env})
            finally:
                os.chdir(cwd)
            return rc, out.getvalue(), er.getvalue()

        def commit_raw(path: str, msg: str) -> None:
            with open(os.path.join(fab, path), "a") as f:
                f.write("ci\n")
            sh(fab, "add", "-A")
            sh(fab, "-c", "core.hooksPath=/dev/null", "commit", "-qm", msg)

        sh(fab, "checkout", "-q", "-b", "ci", "main")
        commit_raw("tools/a.py", "port\n\nFabric-Role: python-dev")
        rc, o, e = ci()
        check("a contributor's commit within its entry passes", rc == 0 and "contributor carve-out" in o, o + e)
        rc, o, e = ci(f"h/{LOGIN}/feat/port")
        check("…but as its own pull request, without merges on main: refused",
              rc == 1 and "does not merge its own work" in e, o + e)
        rc, o, e = ci(f"h/{LOGIN}/for/user/port")
        check("a supply branch as a pull request: refused", rc == 1 and "supply branch" in e, o + e)
        commit_raw("tools/b.py", "fold\n\nFabric-Role: fabric-coordinator")
        rc, o, e = ci(f"h/{LOGIN}/feat/fold")
        check("with an owner commit in it, the owner's pull request: admitted", rc == 0, o + e)
        sh(fab, "reset", "-q", "--hard", "HEAD~1")
        sh(fab, "checkout", "-q", "main")
        with open(os.path.join(fab, "policies", "authority.json"), "w") as f:
            json.dump({**AUTHORITY, "contributors": [{**ENTRY, "merges": True}]}, f)
        sh(fab, "add", "-A")
        sh(fab, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "merges\n\nFabric-Role: fabric-coordinator")
        # main moved past ci's fork point; main..ci is still ci's own commits.
        sh(fab, "checkout", "-q", "ci")
        rc, o, e = ci(f"h/{LOGIN}/feat/port")
        check("with merges on main, its own pull request: admitted", rc == 0, o + e)
        sh(fab, "checkout", "-q", "main")
        sh(fab, "reset", "-q", "--hard", "HEAD~1")
        sh(fab, "checkout", "-q", "ci")
        commit_raw("src/a.py", "stray\n\nFabric-Role: python-dev")
        rc, o, e = ci()
        check("one outside it fails the branch", rc == 1 and "[Fabric-Role: python-dev]" in e, o + e)
        sh(fab, "reset", "-q", "--hard", "HEAD~1")
        with open(os.path.join(fab, "policies", "authority.json"), "w") as f:
            json.dump({**AUTHORITY, "contributors": [{**ENTRY, "paths": ENTRY["paths"] + ["src/"]}]}, f)
        sh(fab, "add", "-A")
        sh(fab, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "widen\n\nFabric-Role: fabric-coordinator")
        commit_raw("src/a.py", "uses the widening\n\nFabric-Role: python-dev")
        rc, o, e = ci()
        check("a branch's own widening is not read: main's entry decides", rc == 1, o + e)

        print("a managed project's .agent-fabric/ admits no contributor, even one whose entry lists it")
        # A fabric whose entry DOES list .agent-fabric/ (review of #75, finding
        # 4): only the scoping can refuse here, so a guard that read the
        # fabric's entry for a project would fail these.
        fab2 = os.path.join(tmp, "fab2")
        shutil.copytree(fab, fab2, ignore=shutil.ignore_patterns(".git"))
        with open(os.path.join(fab2, "policies", "authority.json"), "w") as f:
            json.dump({**AUTHORITY, "contributors": [{**ENTRY, "paths": ENTRY["paths"] + [".agent-fabric/"]}]}, f)
        proj = os.path.join(tmp, "proj")
        os.makedirs(os.path.join(proj, ".agent-fabric", "memory"))
        sh(proj, "init", "-q", "-b", "main")
        sh(proj, "commit", "-q", "--allow-empty", "-m", "base")
        sh(proj, "checkout", "-q", "-b", f"h/{LOGIN}/for/user/slice")
        sh(proj, "config", "core.hooksPath", os.path.join(fab2, "policies", "githooks"))
        with open(os.path.join(proj, ".agent-fabric", "memory", "s.md"), "w") as f:
            f.write("x\n")
        sh(proj, "add", "-A")
        bind("python-dev")
        r = sh(proj, "commit", "-q", "-m", "slice", env={**GIT_ENV, "AGENT_FABRIC_STATE_DIR": state}, check=False)
        check("the hooks refuse it in the project", r.returncode != 0, r.stderr)
        sh(proj, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "slice\n\nFabric-Role: python-dev")
        out, er = io.StringIO(), io.StringIO()
        cwd = os.getcwd()
        os.chdir(proj)
        try:
            with redirect_stdout(out), redirect_stderr(er):
                rc = da.run({**GIT_ENV, "AGENT_FABRIC_ROOT": fab2})
        finally:
            os.chdir(cwd)
        check("CI refuses it in the project", rc == 1, out.getvalue() + er.getvalue())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
