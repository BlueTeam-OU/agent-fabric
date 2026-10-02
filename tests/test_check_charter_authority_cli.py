#!/usr/bin/env python3
"""The CLI oracle for policies/check_charter_authority.sh: what the guard says
and exits, assertion for assertion, as policies/test_check_charter_authority.sh
asserted it (tests/test_charter_authority.py covers the module's internals).

Built on a throwaway git repository, because the guard's whole input is a
COMMITTED diff against a base ref. The first version of the bash test modified
the working tree and asserted the guard fired; it did not, and could not --
`git diff BASE...HEAD` never sees an uncommitted change. A positive control is
the only reason that was caught.

The script under test is the path in $CHARTER_GUARD, default
policies/check_charter_authority.sh; its module is copied from the tools/
beside that script's directory.

Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.abspath(os.environ.get("CHARTER_GUARD") or os.path.join(HERE, "policies", "check_charter_authority.sh"))
if not os.path.isfile(GUARD):
    sys.exit(f"test: script under test not found at {GUARD}")
TOOLS = os.path.join(os.path.dirname(os.path.dirname(GUARD)), "tools", "fabric")

T = tempfile.mkdtemp(prefix="test_check_charter_authority_cli.")
HOME = f"{T}/home"
SANDBOX = f"{T}/sandbox"
fails = 0


def check(label: str, good: bool, detail: str = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    print(f"  FAIL {label}: {detail}")


def env(**more: str) -> dict[str, str]:
    # The caller's own AGENT_FABRIC_*, GITHUB_*, CLAUDE* and GZCOORD_* never
    # reach the guard; each case sets what it needs.
    # GIT_* (GIT_DIR, GIT_INDEX_FILE from a run inside a hook) and XDG_* (a real
    # git config or binding) would point the fixture at the caller's (review of #83).
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE", "GZCOORD_", "GIT_", "XDG_"))}
    e.update(HOME=HOME, GIT_CONFIG_NOSYSTEM="1")
    e.update(more)
    return e


def git(*args: str) -> None:
    # This host signs commits globally; a scratch commit must not ask for a key.
    subprocess.run(["git", "-C", SANDBOX, "-c", "commit.gpgsign=false", *args],
                   env=env(), check=True, capture_output=True)


def put(rel: str, content: str, mode: str = "w") -> None:
    path = f"{SANDBOX}/{rel}"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding="utf-8") as f:
        f.write(content)


def new_repo() -> None:
    """A repo with a base commit, the guard in place, and a charter to touch."""
    shutil.rmtree(SANDBOX, ignore_errors=True)
    os.makedirs(f"{SANDBOX}/policies")
    shutil.copy(GUARD, f"{SANDBOX}/policies/check_charter_authority.sh")
    # The guard is a shim that finds its module beside it (ADR-040 §5 rule 4),
    # so the copy above needs the module copied too; the original bash ignores
    # these files. Kept out of the repository under test by info/exclude, below.
    os.makedirs(f"{SANDBOX}/tools/fabric/guards")
    shutil.copy(f"{TOOLS}/git.py", f"{SANDBOX}/tools/fabric/")
    for name in os.listdir(f"{TOOLS}/guards"):
        if name.endswith(".py"):
            shutil.copy(f"{TOOLS}/guards/{name}", f"{SANDBOX}/tools/fabric/guards/")
    put("identities/roles/flutter-dev/charter.md", "scope\n")
    put("identities/roles/catalog.json", '{"roles":[]}\n')
    put("policies/authority.json", '{"role_definitions":{"role":"fabric-coordinator","holders":["coord-01"]}}\n')
    put("projects/demo/taxonomy.json", '{"roles":[]}\n')
    put("memory/projects/demo/flutter-dev/workflow.md", "other\n")
    git("init", "-q")
    git("config", "user.email", "t@e")
    git("config", "user.name", "t")
    put(".git/info/exclude", "tools/\n", "a")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("branch", "-q", "base-ref")
    # Renamed so there is no `main` for the guard to fall back to:
    # the unresolvable-base case below depends on its absence.
    git("branch", "-q", "-M", "sandbox-head")


def commit_change(rel: str) -> None:
    put(rel, "changed\n", "a")
    git("add", "-A")
    git("commit", "-qm", f"change {rel}")


def guard(branch: str, base: str = "base-ref", **more: str) -> tuple[int, str]:
    p = subprocess.run(["bash", "policies/check_charter_authority.sh"], cwd=SANDBOX, capture_output=True,
                       env=env(AGENT_FABRIC_CHARTER_BASE=base, AGENT_FABRIC_CHARTER_BRANCH=branch, **more),
                       timeout=60)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")


def is_rc(label: str, branch: str, want: int) -> None:
    rc = guard(branch)[0]
    check(label, rc == want, f"exit {rc}")


def main() -> int:
    os.makedirs(HOME)

    print("a charter change by another role")
    new_repo()
    commit_change("identities/roles/flutter-dev/charter.md")
    is_rc("refused (exit 1)", "develop-qzapp/flutter-dev-01/feat/thing", 1)
    out = guard("develop-qzapp/flutter-dev-01/feat/thing")[1]
    check("names the branch owner", "flutter-dev-01" in out, out)
    check("names the file", "charter.md" in out, out)
    check("says what to do instead", "Propose it instead" in out, out)

    print("the same change by a recognised holder of fabric-coordinator")
    is_rc("allowed for a listed holder (exit 0)", "develop-qzapp/coord-01/feat/x", 0)
    is_rc("allowed for an account named for the role", "develop-qzapp/fabric-coordinator-02/feat/x", 0)

    print("architect-cto no longer owns role definitions")
    is_rc("refused (exit 1)", "develop-qzapp/architect-cto-01/feat/x", 1)

    print("a branch cannot add itself to the holders in the same change")
    new_repo()
    p = f"{SANDBOX}/policies/authority.json"
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    d["role_definitions"]["holders"].append("web-dev-01")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f)
    git("add", "-A")
    git("commit", "-qm", "self-appoint")
    is_rc("the holders list is read from the base side", "develop-qzapp/web-dev-01/feat/x", 1)

    print("routing policy is protected too")
    new_repo()
    put("routing/policies/review-grade.json", "{}\n")
    git("add", "-A")
    git("commit", "-qm", "add policy")
    git("branch", "-f", "base-ref")
    commit_change("routing/policies/review-grade.json")
    is_rc("refused", "develop-qzapp/backend-dev-02/feat/x", 1)

    print("a locale holder's translation is the carve-out's, not this guard's")
    new_repo()
    put("identities/roles/language-culture/locale/ru/charter.md", "устав\n")
    put("identities/roles/language-culture/locale/ru/brief.md", "бриф\n")
    git("add", "-A")
    git("commit", "-qm", "add locale")
    git("branch", "-f", "base-ref")
    commit_change("identities/roles/language-culture/locale/ru/charter.md")
    commit_change("identities/roles/language-culture/locale/ru/brief.md")
    is_rc("a translated charter and brief pass (exit 0)", "develop-qzapp/language-culture-ru/fix/ru-locale", 0)
    commit_change("identities/roles/flutter-dev/charter.md")
    is_rc("…but the same branch changing a role's own charter is refused",
          "develop-qzapp/language-culture-ru/fix/ru-locale", 1)

    print("the catalogue is protected too")
    new_repo()
    commit_change("identities/roles/catalog.json")
    is_rc("refused", "develop-qzapp/web-dev-01/feat/x", 1)

    print("a project's taxonomy (where roles apply) is protected too")
    new_repo()
    commit_change("projects/demo/taxonomy.json")
    is_rc("refused", "develop-qzapp/web-dev-01/feat/x", 1)

    print("an agent HOLDING a role does not own its definition")
    # The account is named for the role it was stood up as; holding flutter-dev
    # and editing flutter-dev's charter is still not architect-cto's authority.
    new_repo()
    commit_change("identities/roles/flutter-dev/charter.md")
    is_rc("refused for the role's own instance", "develop-qzapp/flutter-dev-02/feat/widen-my-remit", 1)

    print("an ordinary slice is NOT protected")
    # The control that keeps this from being a blanket ban on touching .roles/:
    # every other file there is generated, and the drain rewrites them.
    new_repo()
    commit_change("memory/projects/demo/flutter-dev/workflow.md")
    is_rc("a distilled slice may change on any branch", "develop-qzapp/flutter-dev-01/feat/x", 0)

    print("nothing changed at all")
    new_repo()
    is_rc("passes", "develop-qzapp/flutter-dev-01/feat/x", 0)

    print("the merge queue's synthetic ref")
    # It HAS three segments, so segment-counting reads its second as the base
    # branch and fails every charter change at the gate. Matched by name.
    new_repo()
    commit_change("identities/roles/flutter-dev/charter.md")
    is_rc("not enforced in the queue", "gh-readonly-queue/main/pr-999-abc", 0)
    out = guard("gh-readonly-queue/main/pr-999-abc")[1]
    check("says where it IS enforced", "the pull_request run" in out, out)

    print("no base ref is resolvable")
    # The guard must NOT fail the build here. An environment that cannot show
    # it a diff is not a violation, and exiting non-zero would block every PR
    # rather than the one changing a charter -- which is exactly what the
    # first version did in CI, where actions/checkout leaves no origin/main.
    new_repo()
    commit_change("identities/roles/flutter-dev/charter.md")
    branch = "develop-qzapp/flutter-dev-01/feat/x"
    rc, out = guard(branch, base="no-such-ref", GITHUB_BASE_REF="")
    check("passes rather than blocking every PR", rc == 0, f"exit {rc}")
    rc, out = guard(branch, base="no-such-ref", GITHUB_BASE_REF="")
    check("says it did not enforce", "NOT ENFORCED" in out, out)

    print("a detached HEAD")
    is_rc("reports rather than guessing", "HEAD", 0)

    print()
    if fails:
        print(f"{fails} FAILED")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(T, ignore_errors=True)
