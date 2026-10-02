#!/usr/bin/env python3
"""The oracle for policies/githooks/ (pre-commit, commit-msg): the
.agent-fabric/ fence at the keyboard, ported assertion for assertion from
policies/githooks/test_hooks.sh.

pre-commit refuses a commit staging anything under .agent-fabric/ unless
the agent's runtime binding holds the fabric-coordinator role; commit-msg
then records that role as the Fabric-Role trailer. The binding is read
through runtime/identity.py, so a throwaway AGENT_FABRIC_STATE_DIR is the
whole fixture.

The hooks under test are the directory in $GITHOOKS_DIR, default
policies/githooks, so one file runs against the bash-era copy and its
replacement. The one difference from the bash: its "setup: drain on main"
guard prints only when it fails, and so does the port.

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.abspath(os.environ.get("GITHOOKS_DIR") or os.path.join(HERE, "policies", "githooks"))
if not os.path.isfile(os.path.join(HOOKS, "pre-commit")):
    sys.exit(f"test: hooks not found at {HOOKS}")
FABRIC = os.path.normpath(os.path.join(HOOKS, "..", ".."))

T = tempfile.mkdtemp(prefix="test_githooks_cli.")
STATE = f"{T}/state"
REPO = f"{T}/repo"
HOME = f"{T}/home"
os.makedirs(HOME)
LOGIN = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
HOST = subprocess.run(["hostname", "-s"], capture_output=True, text=True, check=True).stdout.strip()

fails = 0
err = ""
path_prefix = ""   # the stand-in `id` of the locale section, prepended to PATH


def check(label: str, good: bool, detail: str = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    if "\n" not in detail:
        print(f"  FAIL {label}: {detail}")
        return
    print(f"  FAIL {label}:")
    for line in detail.splitlines():
        print(f"      {line}")


def section(title: str) -> None:
    print(title)


def base_env(state: bool = False) -> dict:
    # A session's own AGENT_FABRIC_*, CLAUDE_* ... would bind the hooks to the
    # caller; the binding is the scratch state dir or nothing.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "CLAUDE_", "GZCOORD_")) and k != "CLAUDECODE"}
    env["HOME"] = HOME
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    if path_prefix:
        env["PATH"] = f"{path_prefix}:{env.get('PATH', '')}"
    if state:
        env["AGENT_FABRIC_STATE_DIR"] = STATE
    return env


def git(*args: str, state: bool = False) -> tuple:
    """(rc, stdout, stderr) of git in the scratch repo; commits never sign."""
    p = subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=REPO,
                       env=base_env(state), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def msg() -> str:
    return git("log", "-1", "--format=%B")[1]


def bind(role: str) -> None:
    os.makedirs(f"{STATE}/agents/{LOGIN}", exist_ok=True)
    with open(f"{STATE}/agents/{LOGIN}/binding.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({"agent": LOGIN, "host": HOST, "role": role or None, "project": "demo",
                            "working_copy": None, "updated_at": "x"}, separators=(",", ":")) + "\n")


def unbind() -> None:
    d = f"{STATE}/agents"
    for name in os.listdir(d):
        try:
            os.remove(f"{d}/{name}/binding.json")
        except FileNotFoundError:
            pass


def put(rel: str, content: str, mode: str = "w") -> None:
    p = f"{REPO}/{rel}"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, mode, encoding="utf-8") as f:
        f.write(content)


def sub(path: str, pattern: str, repl: str) -> None:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(re.sub(pattern, lambda _: repl, text, flags=re.M))


def new_repo() -> None:
    shutil.rmtree(REPO, ignore_errors=True)
    os.makedirs(f"{REPO}/.agent-fabric/memory/backend-dev")
    os.makedirs(f"{REPO}/src")
    git("init", "-q")
    git("config", "user.email", "t@e")
    git("config", "user.name", "t")
    git("config", "core.hooksPath", HOOKS)
    put("src/a.txt", "code\n")
    put(".agent-fabric/memory/backend-dev/workflow.md", "slice\n")
    git("add", "-A")
    git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "base")


def commit_rc(*args: str) -> int:
    global err
    rc, _, err = git(*args, state=True)
    return rc


def try_commit(rel: str, message: str) -> int:
    put(rel, "more\n", "a")
    git("add", "-A")
    return commit_rc("commit", "-q", "-m", message)


def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.M) is not None


def run() -> None:
    global err, path_prefix
    section("a commit outside .agent-fabric/ is untouched by the fence, and declares the role that made it")
    bind("backend-dev"); new_repo()
    check("commits with any role", try_commit("src/a.txt", "code") == 0, f"refused\n{err}")
    check("…and declares Fabric-Role: backend-dev (every account commits under one author; the trailer names the lane)",
          has(r"^Fabric-Role: backend-dev$", msg()), f"no trailer on a code commit\n{msg()}")
    check("a typed trailer on a code commit is left as typed (a claim, not the binding)",
          try_commit("src/a.txt", "typed\n\nFabric-Role: architect-cto") == 0, f"refused\n{err}")
    check("…and not doubled", len(re.findall(r"^Fabric-Role:", msg(), re.M)) == 1, f"trailer doubled\n{msg()}")
    unbind()
    check("no binding: the commit is admitted", try_commit("src/a.txt", "unbound") == 0, f"refused without a binding\n{err}")
    check("…and declares nothing (a fact about the account, never a claim it cannot make)",
          "Fabric-Role" not in msg(), "a trailer with no binding to back it")

    section("a commit under .agent-fabric/ needs the role bound")
    bind("backend-dev"); new_repo()
    check("backend-dev bound: refused",
          try_commit(".agent-fabric/memory/backend-dev/workflow.md", "hand edit") == 1, "hand edit committed")
    check("the refusal says what is bound", "this agent's binding holds: backend-dev" in err, f"wording\n{err}")
    # A wrong slice is corrected at its source memory or with merge_target
    # (agent-fabric ADR-014), never raised: the refusal a holder reads says so.
    check("…and gives the slice correction, not a raise",
          "merge_target" in err and "raise" not in err.lower(), f"slice wording\n{err}")
    bind(""); new_repo()
    check("no role bound: refused",
          try_commit(".agent-fabric/memory/backend-dev/workflow.md", "hand edit") == 1, "unbound commit admitted")
    bind("fabric-coordinator"); new_repo()
    check("fabric-coordinator bound: allowed",
          try_commit(".agent-fabric/memory/backend-dev/workflow.md", "drain") == 0, f"coordinator refused\n{err}")
    check("…and the commit declares Fabric-Role: fabric-coordinator",
          has(r"^Fabric-Role: fabric-coordinator$", msg()), f"no trailer\n{msg()}")

    section("the declaration is the fact the fence checked, never a paste")
    bind("backend-dev"); new_repo()
    check("a typed trailer does not substitute for the binding",
          try_commit(".agent-fabric/memory/backend-dev/workflow.md", "x\n\nFabric-Role: fabric-coordinator") == 1,
          "pasted trailer admitted")

    section("in agent-fabric itself, every commit needs the role")
    bind("backend-dev"); new_repo()
    put("policies/authority.json", '{"role_definitions":{"role":"fabric-coordinator","holders":[]}}\n')
    # The hooks recognise the fabric by their own location: point them at a copy living inside this repo.
    os.makedirs(f"{REPO}/policies/githooks")
    os.makedirs(f"{REPO}/runtime")
    for name in ("pre-commit", "commit-msg", "guarded-change.sh", "locale-carve-out.sh"):
        shutil.copy2(f"{HOOKS}/{name}", f"{REPO}/policies/githooks/")
    shutil.copy2(f"{FABRIC}/runtime/identity.py", f"{REPO}/runtime/")   # the hooks read the binding through their own fabric's resolver
    git("config", "core.hooksPath", f"{REPO}/policies/githooks")
    git("add", "-A"); git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "hooks in place")
    check("backend-dev bound: a code change in the fabric is refused",
          try_commit("src/a.txt", "code") == 1, f"fabric code change committed\n{err}")
    check("the refusal names the whole repository", "agent-fabric itself" in err, f"wording\n{err}")
    bind("fabric-coordinator")
    check("fabric-coordinator bound: allowed", try_commit("src/a.txt", "code") == 0, f"coordinator refused in fabric\n{err}")
    check("…and every fabric commit declares the role",
          has(r"^Fabric-Role: fabric-coordinator$", msg()), "no trailer on a fabric commit")

    section("in agent-fabric itself, a commit touching docs/adr/ leaves the decision records consistent")
    for d in ("tools/fabric", "docs", "projects"):
        os.makedirs(f"{REPO}/{d}", exist_ok=True)
    shutil.copy2(f"{FABRIC}/tools/fabric/adr.py", f"{REPO}/tools/fabric/")
    for d in ("adr", "live-checks"):
        shutil.copytree(f"{FABRIC}/docs/{d}", f"{REPO}/docs/{d}", dirs_exist_ok=True)
    shutil.copy2(f"{FABRIC}/projects/registry.json", f"{REPO}/projects/")
    git("add", "-A"); git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "records in place")
    check("a consistent change to docs/adr/ commits",
          try_commit("docs/adr/DIGEST.md", "a note in the digest") == 0, f"a consistent records change was refused\n{err}")
    check("a hand-edited generated index: refused, naming it",
          try_commit("docs/adr/index.json", "hand-edit the generated index") == 1 and "index.json: stale" in err,
          f"an inconsistent index was committed\n{err}")
    git("reset", "-q", "--hard")
    # The staged tree is what is checked: a consistent working tree does not
    # cover a commit that leaves the regenerated index out of it.
    adr1 = f"{REPO}/docs/adr/ADR-001-decision-records.md"
    digest = f"{REPO}/docs/adr/DIGEST.md"
    sub(adr1, r"^# ADR-001 — Decision records$", "# ADR-001 — Decision record rules")
    sub(digest, r"^### ADR-001 — Decision records \(Accepted\)$", "### ADR-001 — Decision record rules (Accepted)")
    subprocess.run([sys.executable, f"{REPO}/tools/fabric/adr.py", "--root", REPO, "index", "--write"],
                   env=base_env(), capture_output=True)
    git("add", "docs/adr/ADR-001-decision-records.md", "docs/adr/DIGEST.md")
    rc = commit_rc("commit", "-q", "-m", "retitle, index left unstaged")
    check("the staged tree is checked: an index left out of the commit is refused",
          rc == 1 and "index.json: stale" in err, f"a commit leaving the index behind was admitted (rc={rc})\n{err}")
    git("add", "-A")
    rc = commit_rc("commit", "-q", "-m", "retitle with its index")
    check("…and commits once the index is staged with it", rc == 0, f"the complete commit was refused\n{err}")
    sub(adr1, r"^\*\*Pillar:\*\* P2$", "**Pillar:** P2\n**Evidence:** src/a.txt")
    check("Evidence anywhere in the staged tree resolves in the hook as in CI",
          try_commit("docs/adr/DIGEST.md", "a record whose evidence lives elsewhere in the tree") == 0,
          f"the hook refused Evidence outside docs/adr\n{err}")
    # A staged tree that cannot be written out stops the commit: checking what
    # did get written would pass a tree the commit does not contain. A path
    # longer than a file name may be makes checkout-index fail for real.
    # Staged by hand: try_commit's add -A would unstage a path with no file.
    put("docs/adr/DIGEST.md", "more\n", "a"); git("add", "docs/adr/DIGEST.md")
    p = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=REPO, env=base_env(), input="x\n",
                       capture_output=True, text=True)
    git("update-index", "--add", "--cacheinfo", f"100644,{p.stdout.strip()},src/{'n' * 300}")
    rc = commit_rc("commit", "-q", "-m", "a staged tree that cannot be materialized")
    check("a staged tree that cannot be written out stops the commit",
          rc == 1 and "cannot materialize the staged tree" in err, f"the hook checked a partial tree\n{err}")
    git("reset", "-q", "--hard")

    section("the one carve-out: a locale's translations, by the holder of the role named for the suffix")
    # The hook matches the suffix against `id -un`. The account running the
    # suite is any login (user, python-dev-01: "01" is no locale), so this
    # section answers as a language-culture login; the binding stays the real
    # login's, as identity.py reads it.
    os.makedirs(f"{T}/bin")
    with open(f"{T}/bin/id", "w", encoding="utf-8") as f:
        f.write('#!/bin/sh\n[ "$*" = "-un" ] && { echo language-culture-ge; exit 0; }\nexec /usr/bin/id "$@"\n')
    os.chmod(f"{T}/bin/id", 0o755)
    path_prefix = f"{T}/bin"
    suffix = "ge"
    loc = f"identities/roles/language-culture/locale/{suffix}"
    bind("language-culture")
    os.makedirs(f"{REPO}/{loc}", exist_ok=True)
    os.makedirs(f"{REPO}/identities/roles/language-culture/locale/zz", exist_ok=True)
    check(f"language-culture bound on login *-{suffix}: locale/{suffix}/ commits",
          try_commit(f"{loc}/team.md", "ge team") == 0, f"the holder's own locale refused\n{err}")
    check("…declaring its own role, not the coordinator's",
          has(r"^Fabric-Role: language-culture$", msg()), f"trailer on a carve-out commit\n{msg()}")
    check("another suffix's locale: refused, naming the suffix",
          try_commit("identities/roles/language-culture/locale/zz/team.md", "another locale") == 1 and "named for zz" in err,
          f"another locale admitted\n{err}")
    os.makedirs(f"{REPO}/{loc}", exist_ok=True)
    put(f"{loc}/memory.md", "x\n", "a"); put("src/a.txt", "y\n", "a"); git("add", "-A")
    rc = commit_rc("commit", "-qm", "locale plus code"); git("reset", "-q", "--hard")
    check("a locale file beside any other path: the whole-repository refusal",
          rc == 1 and "agent-fabric itself" in err, f"mixed commit admitted\n{err}")
    check("the role's English charter is not the locale: refused",
          try_commit("identities/roles/language-culture/charter.md", "the English charter") == 1,
          f"charter admitted to the holder\n{err}")
    # The holder folds main into its branch: main moved elsewhere (a code file), the branch adds only its locale — allowed; a merge that also hand-edits a code file is refused.
    git("checkout", "-q", "-b", "feat/ge"); try_commit(f"{loc}/harness.md", "ge harness")
    git("checkout", "-q", "-"); bind("fabric-coordinator"); try_commit("src/a.txt", "main moved")
    main_branch = git("branch", "--show-current")[1].strip()
    git("checkout", "-q", "feat/ge"); bind("language-culture")
    rc = commit_rc("merge", "-q", "--no-ff", "--no-edit", main_branch)
    check("a merge of main into the holder's locale branch commits, declaring its role",
          rc == 0 and has(r"^Fabric-Role: language-culture$", msg()), f"the holder cannot fold main\n{err}")
    try_commit("src/a.txt", "x"); git("reset", "-q", "--hard"); bind("fabric-coordinator")
    git("checkout", "-q", main_branch); try_commit("src/a.txt", "main moved again")
    git("checkout", "-q", "feat/ge"); bind("language-culture")
    git("merge", "-q", "--no-ff", "--no-commit", main_branch, state=True)
    put("src/a.txt", "edited during the merge\n", "a"); git("add", "src/a.txt")
    rc = commit_rc("commit", "-qm", "merge plus a hand edit")
    check("a merge that also hand-edits outside the locale: refused", rc == 1, f"hand-edited merge admitted\n{err}")
    git("merge", "--abort"); git("reset", "-q", "--hard"); git("checkout", "-q", main_branch)
    bind("backend-dev")
    check("another role on the same login: refused",
          try_commit(f"{loc}/memory.md", "ge memory") == 1, f"wrong role admitted to a locale\n{err}")
    bind("fabric-coordinator")
    check("the coordinator still commits anywhere, the locale included",
          try_commit(f"{loc}/memory.md", "ge memory") == 0, f"coordinator refused in a locale\n{err}")
    path_prefix = ""

    section("in agent-fabric itself an amend is a guarded change too")
    bind("backend-dev")
    rc = commit_rc("commit", "-q", "--amend", "--no-edit")
    check("backend-dev bound: an amend in the fabric is refused", rc == 1, f"amend admitted under backend-dev\n{err}")
    bind("fabric-coordinator")
    git("commit", "-q", "--amend", "-m", "rewritten")   # message without a trailer
    rc = commit_rc("commit", "-q", "--amend", "--no-edit")
    check("fabric-coordinator bound: the amend commits", rc == 0, f"amend refused\n{err}")
    check("…and the amend carries the trailer (git am + amend is the handover route)",
          has(r"^Fabric-Role: fabric-coordinator$", msg()), f"no trailer on an amend\n{msg()}")

    section("a merge that only folds main's .agent-fabric/ changes is no change of its own")
    # main gets a drain (coordinator); a backend-dev branch then folds main.
    bind("fabric-coordinator"); new_repo()
    git("checkout", "-q", "-b", "feature"); put("src/a.txt", "feature\n", "a"); git("add", "-A")
    git("commit", "-qm", "feature", state=True)
    if git("checkout", "-q", "master")[0] != 0:
        git("checkout", "-q", "main")
    if try_commit(".agent-fabric/memory/backend-dev/workflow.md", "drain on main") != 0:
        check("setup: drain on main", False, err)
    git("checkout", "-q", "feature"); bind("backend-dev")
    prev = git("rev-parse", "--abbrev-ref", "@{-1}")[1].strip()
    rc = commit_rc("merge", "-q", "--no-ff", "--no-edit", prev)
    check("backend-dev bound: the fold commits", rc == 0, f"the fold was refused\n{err}")
    check("…and declares the role that folded it, as every commit does",
          has(r"^Fabric-Role: backend-dev$", msg()), f"no trailer on the fold\n{msg()}")
    check("…and .agent-fabric/ equals main's", git("diff", "HEAD^2", "HEAD", "--", ".agent-fabric/")[1] == "",
          "fold altered .agent-fabric/")

    section("a merge that also hand-edits a slice is refused")
    git("reset", "-q", "--hard", "HEAD^"); bind("backend-dev")
    prev = git("rev-parse", "--abbrev-ref", "@{-1}")[1].strip()
    git("merge", "-q", "--no-ff", "--no-commit", prev, state=True)
    put(".agent-fabric/memory/backend-dev/workflow.md", "by hand\n", "a"); git("add", "-A")
    rc = commit_rc("commit", "-qm", "fold plus edit")
    check("backend-dev bound: refused", rc == 1, "a merge carrying a hand edit was admitted")
    check("…by the fence", "this agent's binding holds: backend-dev" in err, f"wording\n{err}")
    git("merge", "--abort"); git("reset", "-q", "--hard")

    section("the attribution ban still holds on the same hook")
    bind("fabric-coordinator"); new_repo()
    check("Co-authored-by is still refused",
          try_commit("src/a.txt", "x\n\nCo-authored-by: Someone <s@e>") == 1, "ban lost")

    print()
    section("in a managed project, its own docs/adr/ is its own")
    bind("fabric-coordinator"); new_repo()
    put("docs/adr/index.json", "not ours\n")
    check("a managed project's docs/adr/ is not checked by the fabric's hook",
          try_commit("docs/adr/index.json", "a project record") == 0,
          f"the fabric's hook judged a project's records\n{err}")


try:
    run()
finally:
    shutil.rmtree(T, ignore_errors=True)

if fails:
    print(f"{fails} FAILED")
    sys.exit(1)
print("all passed")
