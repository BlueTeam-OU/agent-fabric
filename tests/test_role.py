#!/usr/bin/env python3
"""Behavioural tests for tools/fabric/role.py.

Stdlib only; run as `python3 tests/test_role.py`. Each case runs the real
activator against a throwaway agent-fabric root, a throwaway state
directory and a throwaway workspace, so nothing here touches the real
repository or the real binding.

What makes an activator dangerous rather than merely broken: it deletes
files, it writes into the directories the harness scans, and it is the
only thing that knows which of those files it put there. Added here: it
must never touch the AGENT — the login — while binding a role to it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROLE_PY = os.path.join(ROOT, "tools", "fabric", "role.py")


def id_un() -> str:
    return subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()


def build_fabric(root: str) -> None:
    """A miniature agent-fabric: two roles, one project with memory."""
    os.makedirs(os.path.join(root, "projects"))
    with open(os.path.join(root, "projects", "registry.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "projects": {"demo": {"remotes": ["git@example.com:org/demo.git"]}}}, fh)
    for role, skills, commands in (
        ("flutter-dev", ["widget-testing", "ble-debugging"], ["run-emulator.md"]),
        ("backend-dev", ["migration-check"], []),
    ):
        base = os.path.join(root, "identities", "roles", role)
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, "charter.md"), "w", encoding="utf-8") as fh:
            fh.write(f"---\nrole: {role}\nclass: charter\n---\n\n# {role}\n")
        # The demo project's memory lives in its working copy (the fixture
        # workspace beside this fabric), never here.
        mem = os.path.join(os.path.dirname(root), "demo-clone", ".agent-fabric", "memory", role)
        os.makedirs(mem, exist_ok=True)
        with open(os.path.join(mem, "INDEX.md"), "w", encoding="utf-8") as fh:
            fh.write(f"# {role} index\n")
        if role == "flutter-dev":
            wf = os.path.join(mem, "workflow")
            os.makedirs(wf, exist_ok=True)
            for slice_name in ("hot-reload-traps.md", "apk-signing.md"):
                with open(os.path.join(wf, slice_name), "w", encoding="utf-8") as fh:
                    fh.write(f"---\nrole: {role}\nclass: workflow\ntier: 1\n---\n\nbody\n")
            with open(os.path.join(wf, "notes.txt"), "w", encoding="utf-8") as fh:
                fh.write("not a slice\n")
        for skill in skills:
            d = os.path.join(base, "skills", skill)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as fh:
                fh.write(f"---\nname: {skill}\ndescription: {skill} for {role}\n---\n\nbody\n")
        for command in commands:
            d = os.path.join(base, "commands")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, command), "w", encoding="utf-8") as fh:
                fh.write("---\ndescription: x\n---\n\nbody\n")
    # The real modules, reachable from the fixture root.
    for rel in ("tools/fabric/layout.py", "tools/fabric/workingcopy.py", "tools/fabric/role.py",
                "runtime/identity.py"):
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), os.path.join(root, rel))


def build_workspace(ws: str, remote: str | None = "git@example.com:org/demo.git") -> None:
    os.makedirs(ws, exist_ok=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    if remote and not os.path.exists(os.path.join(ws, ".git")):
        subprocess.run(["git", "init", "-q", "."], cwd=ws, env=env, check=True)
        subprocess.run(["git", "remote", "add", "origin", remote], cwd=ws, env=env, check=True)
    committed = os.path.join(ws, ".claude", "skills", "adr-lookup")
    os.makedirs(committed, exist_ok=True)
    with open(os.path.join(committed, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nname: adr-lookup\ndescription: committed and universal\n---\n")
    os.makedirs(os.path.join(ws, ".claude", "commands"), exist_ok=True)


class Fixture:
    def __init__(self, tmp: str):
        self.root = os.path.join(tmp, "fabric")
        self.state = os.path.join(tmp, "state")
        self.ws = os.path.join(tmp, "demo-clone")
        build_fabric(self.root)
        build_workspace(self.ws)
        self.env = {**os.environ, "AGENT_FABRIC_ROOT": self.root, "AGENT_FABRIC_STATE_DIR": self.state}
        self.env.pop("CLAUDE_PROJECT_DIR", None)
        # This suite may itself run inside a session; the activator under
        # test is a login-shell tool and refuses the harness's environment
        # (test_binding_is_refused_inside_a_session puts it back).
        for name in ("CLAUDECODE", "CLAUDE_ENV_FILE", "AGENT_FABRIC_LAUNCH_PROFILE"):
            self.env.pop(name, None)

    def run(self, *argv: str, workspace: str | None = None) -> subprocess.CompletedProcess:
        ws = workspace or self.ws
        return subprocess.run([sys.executable, os.path.join(self.root, "tools", "fabric", "role.py"),
                               *argv, "--workspace", ws], capture_output=True, text=True, env=self.env)

    def binding(self) -> dict:
        with open(os.path.join(self.state, "agents", id_un(), "binding.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def history(self) -> list[dict]:
        path = os.path.join(self.state, "agents", id_un(), "role-history.jsonl")
        with open(path, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def exclude(self) -> str:
        with open(os.path.join(self.ws, ".git", "info", "exclude"), encoding="utf-8") as fh:
            return fh.read()


def _tier1(f: "Fixture", role: str, project: str | None) -> list[str]:
    """layout.tier1_paths as the session-start hook will consult it, run in
    the fixture root. The activator no longer prints a "load now" list —
    the launcher and the hook deliver these — so the layout is asked
    directly, from the binding the activator wrote."""
    code = (
        "import importlib.util, json, os, sys\n"
        "spec = importlib.util.spec_from_file_location('l', os.path.join(os.environ['AGENT_FABRIC_ROOT'], 'tools/fabric/layout.py'))\n"
        "l = importlib.util.module_from_spec(spec); spec.loader.exec_module(l)\n"
        "role, project, wc = sys.argv[1], sys.argv[2] or None, sys.argv[3] or None\n"
        "if project and wc: l.set_working_copy(project, wc)\n"
        "print(json.dumps(l.tier1_paths(role, project)))\n")
    b = f.binding()
    r = subprocess.run([sys.executable, "-c", code, role, project or "", b.get("working_copy") or ""],
                       env=f.env, capture_output=True, text=True, cwd=f.ws)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_install_places_copies_under_exact_names(f: Fixture) -> None:
    proc = f.run("flutter-dev")
    assert proc.returncode == 0, proc.stderr
    assert os.path.isfile(os.path.join(f.ws, ".claude/skills/widget-testing/SKILL.md"))
    assert os.path.isfile(os.path.join(f.ws, ".claude/skills/ble-debugging/SKILL.md"))
    assert os.path.isfile(os.path.join(f.ws, ".claude/commands/run-emulator.md"))
    assert not os.path.islink(os.path.join(f.ws, ".claude/skills/widget-testing")), "copies, not links"


def test_binding_names_the_agent_by_login_and_the_role_separately(f: Fixture) -> None:
    b = f.binding()
    assert b["agent"] == id_un(), b
    assert b["role"] == "flutter-dev"
    assert b["project"] == "demo", "project resolved from the workspace's remote"
    assert b["working_copy"] and os.path.basename(b["working_copy"]) == "demo-clone"
    assert "clone_id" not in b and "dir_basename" not in b, "no directory-derived identity"
    paths = {i["path"] for i in b["installed"]}
    assert ".claude/skills/widget-testing" in paths
    assert all(i.get("digest") for i in b["installed"])


def test_exclude_block_names_the_copies_and_keeps_user_entries(f: Fixture) -> None:
    text = f.exclude()
    assert "/.claude/skills/widget-testing" in text
    assert "/.claude/commands/run-emulator.md" in text
    assert "# pre-existing user entry" in text


def test_switch_removes_only_what_it_installed(f: Fixture) -> None:
    proc = f.run("backend-dev")
    assert proc.returncode == 0, proc.stderr
    assert os.path.isfile(os.path.join(f.ws, ".claude/skills/migration-check/SKILL.md"))
    assert not os.path.exists(os.path.join(f.ws, ".claude/skills/widget-testing"))
    assert not os.path.exists(os.path.join(f.ws, ".claude/commands/run-emulator.md"))
    assert os.path.isfile(os.path.join(f.ws, ".claude/skills/adr-lookup/SKILL.md")), "never a sweep"


def test_role_changes_agent_does_not(f: Fixture) -> None:
    b = f.binding()
    assert b["role"] == "backend-dev" and b["agent"] == id_un()
    hist = f.history()
    assert [h["role"] for h in hist] == ["flutter-dev", "backend-dev"], hist
    assert hist[-1]["reason"] == "role-change" and hist[-1]["previous_role"] == "flutter-dev"
    assert {h["agent"] for h in hist} == {id_un()}


def test_nothing_committed_is_written(f: Fixture) -> None:
    proc = subprocess.run(["git", "status", "--porcelain"], cwd=f.ws, capture_output=True, text=True)
    tracked_dirty = [l for l in proc.stdout.splitlines() if not l.startswith("??")]
    assert not tracked_dirty, proc.stdout
    assert not os.path.exists(os.path.join(f.root, "memory", "role-history.jsonl"))


def test_locally_adapted_copy_blocks_a_switch(f: Fixture) -> None:
    target = os.path.join(f.ws, ".claude/skills/migration-check/SKILL.md")
    with open(target, "a", encoding="utf-8") as fh:
        fh.write("\nlocal adaptation\n")
    proc = f.run("flutter-dev")
    assert proc.returncode == 1, "an adapted copy must stop the switch"
    assert "adapted" in proc.stderr.lower()
    assert os.path.exists(target)


def test_force_stashes_before_replacing(f: Fixture) -> None:
    proc = f.run("flutter-dev", "--force")
    assert proc.returncode == 0, proc.stderr
    stash_root = os.path.join(f.state, "agents", id_un(), "stash")
    found = [os.path.join(d, n) for d, _, names in os.walk(stash_root) for n in names]
    assert any("migration-check" in p for p in found), found


def test_collision_with_a_committed_skill_is_refused_and_leaves_role_intact(f: Fixture) -> None:
    before = f.binding()
    assert before["role"] == "flutter-dev"
    clash = os.path.join(f.root, "identities/roles/backend-dev/skills/adr-lookup")
    os.makedirs(clash, exist_ok=True)
    with open(os.path.join(clash, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nname: adr-lookup\ndescription: impostor\n---\n")
    try:
        proc = f.run("backend-dev")
        assert proc.returncode == 1, "must refuse to shadow a committed skill"
        assert "adr-lookup" in proc.stderr
        with open(os.path.join(f.ws, ".claude/skills/adr-lookup/SKILL.md"), encoding="utf-8") as fh:
            assert "committed and universal" in fh.read()
        for item in before["installed"]:
            assert os.path.exists(os.path.join(f.ws, item["path"])), f"{item['path']} deleted by a refusal"
        assert f.binding()["role"] == "flutter-dev"
    finally:
        shutil.rmtree(clash)


def test_activation_says_where_the_role_reaches_the_session(f: Fixture) -> None:
    """Nothing to "load now": the activator says the launcher puts the
    charter (and brief, when one exists) into the prompt and the hook
    delivers the project's remit."""
    proc = f.run("flutter-dev", "--force")
    assert proc.returncode == 0, proc.stderr
    assert "bound." in proc.stdout and "system prompt" in proc.stdout, proc.stdout
    assert "(no brief yet)" in proc.stdout and "session-start hook" in proc.stdout, proc.stdout
    assert "load now" not in proc.stdout
    with open(os.path.join(f.root, "identities", "roles", "flutter-dev", "brief.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: flutter-dev\nclass: brief\n---\n\n# flutter-dev — brief\n")
    proc = f.run("flutter-dev")
    assert "charter and brief of flutter-dev" in proc.stdout, proc.stdout


def test_tier1_lists_charter_index_and_workflow_from_project_memory(f: Fixture) -> None:
    assert f.run("flutter-dev", "--force").returncode == 0
    listed = _tier1(f, "flutter-dev", "demo")
    assert listed[0].endswith("identities/roles/flutter-dev/charter.md"), listed
    assert listed[1].endswith("demo-clone/.agent-fabric/memory/flutter-dev/INDEX.md"), listed
    assert listed[2].endswith("workflow/apk-signing.md") and listed[3].endswith("workflow/hot-reload-traps.md"), listed
    assert not any(p.endswith("notes.txt") for p in listed), listed


def test_tier1_omits_a_class_the_role_does_not_have(f: Fixture) -> None:
    assert f.run("backend-dev").returncode == 0
    listed = _tier1(f, "backend-dev", "demo")
    assert [os.path.basename(p) for p in listed] == ["charter.md", "INDEX.md"], listed
    f.run("flutter-dev")


def test_tier1_accepts_the_single_file_workflow_shape(f: Fixture) -> None:
    path = os.path.join(f.ws, ".agent-fabric/memory/backend-dev/workflow.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("---\nrole: backend-dev\nclass: workflow\ntier: 1\n---\n\nbody\n")
    try:
        assert f.run("backend-dev").returncode == 0
        assert any(p.endswith("backend-dev/workflow.md") for p in _tier1(f, "backend-dev", "demo"))
    finally:
        os.remove(path)
        f.run("flutter-dev")


def test_outside_a_working_copy_only_the_charter_loads(f: Fixture, tmp: str) -> None:
    """The parent projects/ directory is a legitimate workspace: no git,
    no project. The agent is still the same login."""
    parent = os.path.join(tmp, "projects")
    build_workspace(parent, remote=None)
    proc = f.run("backend-dev", workspace=parent)
    assert proc.returncode == 0, proc.stderr
    assert f.binding()["agent"] == id_un() and f.binding()["project"] is None
    assert [os.path.basename(p) for p in _tier1(f, "backend-dev", None)] == ["charter.md"]
    assert "no project is bound" in proc.stdout
    assert os.path.isfile(os.path.join(parent, ".claude/skills/migration-check/SKILL.md"))
    # Moving back to the repo workspace removes the copies from the parent.
    f.run("flutter-dev")
    assert not os.path.exists(os.path.join(parent, ".claude/skills/migration-check"))


def test_explicit_project_binds_even_without_a_working_copy(f: Fixture, tmp: str) -> None:
    parent = os.path.join(tmp, "elsewhere")
    build_workspace(parent, remote=None)
    proc = f.run("backend-dev", "--project", "demo", workspace=parent)
    assert proc.returncode == 0, proc.stderr
    assert f.binding()["project"] == "demo"
    assert "remit" in proc.stdout and "session-start hook" in proc.stdout, proc.stdout
    # The project is bound, but its memory lives in a working copy this
    # binding does not know: only the charter is reachable, and that is
    # said by the shape of the list, never by a guess at a location.
    assert [os.path.basename(p) for p in _tier1(f, "backend-dev", "demo")] == ["charter.md"]
    f.run("flutter-dev")


def test_status_reports_agent_and_role(f: Fixture) -> None:
    proc = f.run("status")
    assert proc.returncode == 0, proc.stderr
    assert f"agent     {id_un()}" in proc.stdout, proc.stdout
    assert "flutter-dev" in proc.stdout
    assert "clone_id" not in proc.stdout and "dir_basename" not in proc.stdout


def test_deactivate_clears_role_keeps_agent(f: Fixture) -> None:
    proc = f.run("deactivate")
    assert proc.returncode == 0, proc.stderr
    b = f.binding()
    assert b["role"] is None and b["agent"] == id_un()
    assert not os.path.exists(os.path.join(f.ws, ".claude/skills/widget-testing"))
    assert f.history()[-1]["reason"] == "deactivate"
    f.run("flutter-dev")


def test_binding_is_refused_inside_a_session(f: Fixture, tmp: str) -> None:
    """A role is bound from a login shell; under a running session the
    prompt already carries the launched role, so activate and deactivate
    refuse (each harness variable on its own), status and list do not."""
    assert f.run("backend-dev").returncode == 0
    for name in ("CLAUDECODE", "CLAUDE_ENV_FILE", "AGENT_FABRIC_LAUNCH_PROFILE"):
        env = {**f.env, name: "1"}
        r = subprocess.run([sys.executable, os.path.join(f.root, "tools", "fabric", "role.py"), "flutter-dev"],
                           cwd=f.ws, env=env, capture_output=True, text=True)
        assert r.returncode == 1 and f"${name} is set" in r.stderr and "relaunch" in r.stderr, (name, r.stderr)
        r = subprocess.run([sys.executable, os.path.join(f.root, "tools", "fabric", "role.py"), "deactivate"],
                           cwd=f.ws, env=env, capture_output=True, text=True)
        assert r.returncode == 1 and "refusing to drop the role" in r.stderr, (name, r.stderr)
        for harmless in ("status", "list"):
            r = subprocess.run([sys.executable, os.path.join(f.root, "tools", "fabric", "role.py"), harmless],
                               cwd=f.ws, env=env, capture_output=True, text=True)
            assert r.returncode == 0, (name, harmless, r.stderr)
    assert f.binding()["role"] == "backend-dev", "a refused rebind changed the binding"


def test_a_role_change_announces_nothing(f: Fixture, tmp: str) -> None:
    """Binding, changing or dropping a role posts nothing: who holds a role,
    and whether a session runs, is the control plane's to answer
    (runtime/control/presence.mjs). A stub `node` records every send, so
    "nothing" is what the relay would have seen."""
    # Own fixture: the shared one has no gzcoord scripts and the stub node must not leak into other cases.
    own = os.path.join(tmp, "announce"); os.makedirs(own, exist_ok=True); f = Fixture(own)
    scripts = os.path.join(f.root, "communication", "gzcoord", "scripts")
    os.makedirs(scripts); open(os.path.join(scripts, "gzmsg.mjs"), "w").close(); open(os.path.join(scripts, "send.mjs"), "w").close()
    log = os.path.join(own, "node.log"); bindir = os.path.join(own, "bin"); os.makedirs(bindir)
    stub = r"""#!/usr/bin/env bash
case "$*" in
  *gzmsg.mjs\ new-id) echo 01a09fc1-0000-7000-8000-000000000009 ;;
  *send.mjs\ -) body=$(cat); printf 'SEND %s\n' "$(printf '%s' "$body" | head -3 | tr '\n' ' ')" >> "$LOG"; echo 'sent seq 1' ;;
esac
"""
    with open(os.path.join(bindir, "node"), "w", encoding="utf-8") as fh:
        fh.write(stub)
    os.chmod(os.path.join(bindir, "node"), 0o755)
    f.env["PATH"] = bindir + os.pathsep + f.env["PATH"]; f.env["LOG"] = log
    assert f.run("backend-dev").returncode == 0
    assert f.run("flutter-dev").returncode == 0
    assert f.run("deactivate").returncode == 0
    assert f.run("backend-dev", "--no-announce").returncode == 0, "--no-announce is still accepted"
    lines = open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
    assert not [l for l in lines if l.startswith("SEND")], f"presence is the control plane's; a role change posts nothing: {lines}"


def test_unknown_role_is_a_usage_error(f: Fixture) -> None:
    assert f.run("no-such-role").returncode == 2


def test_activation_works_inside_a_linked_worktree(f: Fixture, tmp: str) -> None:
    """A linked worktree's `.git` is a FILE; the exclude block must land in
    the common dir git actually reads."""
    main_repo = os.path.join(tmp, "main-repo")
    os.makedirs(main_repo)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    git = lambda *a, cwd=main_repo: subprocess.run(["git", "-c", "commit.gpgsign=false", *a], cwd=cwd, capture_output=True, text=True, env=env)  # noqa: E731
    git("init", "-q", ".")
    with open(os.path.join(main_repo, "seed.txt"), "w", encoding="utf-8") as fh:
        fh.write("seed\n")
    git("add", "seed.txt"); git("commit", "-q", "-m", "init")
    linked = os.path.join(tmp, "linked")
    assert git("worktree", "add", "-q", "--detach", linked, "HEAD").returncode == 0
    assert os.path.isfile(os.path.join(linked, ".git"))
    proc = f.run("flutter-dev", "--force", workspace=linked)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    resolved = subprocess.run(["git", "rev-parse", "--git-path", "info/exclude"], cwd=linked,
                              capture_output=True, text=True).stdout.strip()
    target = resolved if os.path.isabs(resolved) else os.path.join(linked, resolved)
    with open(target, encoding="utf-8") as fh:
        assert ".claude/skills/widget-testing" in fh.read()
    f.run("flutter-dev", "--force")


def _tree(ws: str) -> dict[str, str]:
    """Every file under the workspace's .claude/ with its bytes' digest, and
    the exclude block — the whole observable state a switch may touch."""
    import hashlib
    out: dict[str, str] = {}
    for d, _, names in os.walk(os.path.join(ws, ".claude")):
        for n in names:
            full = os.path.join(d, n)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, ws)] = hashlib.sha256(fh.read()).hexdigest()
    with open(os.path.join(ws, ".git", "info", "exclude"), encoding="utf-8") as fh:
        out["<exclude>"] = fh.read()
    return out


def test_a_failure_anywhere_in_the_switch_restores_everything(f: Fixture) -> None:
    """The switch is a transaction: at every injectable point — after
    staging, after the previous copies were moved out, mid-install, after
    install, after the binding was written — a failure leaves the
    workspace, the exclude block and the binding exactly as they were."""
    assert f.run("flutter-dev", "--force").returncode == 0
    before_tree, before_binding = _tree(f.ws), f.binding()
    assert before_binding["role"] == "flutter-dev"
    for point in ("after-stage", "backup:.claude/skills/widget-testing", "after-backup",
                  "install:.claude/skills/migration-check", "after-install", "after-binding"):
        f.env["AGENT_FABRIC_FAULT"] = f"role:{point}"
        try:
            proc = f.run("backend-dev")
        finally:
            f.env.pop("AGENT_FABRIC_FAULT", None)
        assert proc.returncode != 0 and "injected fault" in proc.stderr, (point, proc.stderr)
        assert "restored" in proc.stderr, (point, proc.stderr)
        assert _tree(f.ws) == before_tree, f"workspace changed after a failure at {point}"
        assert f.binding() == before_binding or {**f.binding(), "updated_at": None} == {**before_binding, "updated_at": None}, \
            f"binding changed after a failure at {point}"
        assert not os.path.exists(os.path.join(f.ws, ".claude", ".agent-fabric-staging")), point
        assert not os.path.exists(os.path.join(f.ws, ".claude", ".agent-fabric-backup")), point
    # and a first activation that fails leaves no binding at all
    dead = os.path.join(f.state, "agents", id_un(), "binding.json")
    saved = open(dead, "rb").read(); os.remove(dead)
    f.env["AGENT_FABRIC_FAULT"] = "role:after-binding"
    try:
        proc = f.run("backend-dev")
    finally:
        f.env.pop("AGENT_FABRIC_FAULT", None)
    assert proc.returncode != 0 and not os.path.exists(dead), "a failed first activation left a binding"
    open(dead, "wb").write(saved)
    # the transaction's directories are excluded, so an interrupted run never dirties git status
    assert ".claude/.agent-fabric-staging" in f.exclude() and ".claude/.agent-fabric-backup" in f.exclude()
    # after all that, a clean switch still works
    assert f.run("backend-dev").returncode == 0 and f.binding()["role"] == "backend-dev"


def test_a_backup_left_by_a_crash_is_stashed_not_dropped(f: Fixture) -> None:
    leftover = os.path.join(f.ws, ".claude", ".agent-fabric-backup", "tx-old", ".claude", "skills", "gone")
    os.makedirs(leftover)
    with open(os.path.join(leftover, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write("what an earlier run had replaced\n")
    os.makedirs(os.path.join(f.ws, ".claude", ".agent-fabric-staging", "tx-old"))
    proc = f.run("flutter-dev")
    assert proc.returncode == 0, proc.stderr
    assert "interrupted run's backup moved to" in proc.stderr, proc.stderr
    assert not os.path.exists(os.path.join(f.ws, ".claude", ".agent-fabric-backup"))
    assert not os.path.exists(os.path.join(f.ws, ".claude", ".agent-fabric-staging"))
    stashed = [os.path.join(d, n) for d, _, names in os.walk(os.path.join(f.state, "agents", id_un(), "stash")) for n in names]
    assert any(p.endswith("gone/SKILL.md") for p in stashed), stashed


def test_a_failed_deactivation_restores_the_copies(f: Fixture) -> None:
    assert f.binding()["role"] == "flutter-dev"
    before_tree, before_binding = _tree(f.ws), f.binding()
    f.env["AGENT_FABRIC_FAULT"] = "role:after-binding"
    try:
        proc = f.run("deactivate")
    finally:
        f.env.pop("AGENT_FABRIC_FAULT", None)
    assert proc.returncode != 0 and "restored" in proc.stderr, proc.stderr
    assert _tree(f.ws) == before_tree and {**f.binding(), "updated_at": None} == {**before_binding, "updated_at": None}


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        with open(os.path.join(f.ws, ".git/info/exclude"), "a", encoding="utf-8") as fh:
            fh.write("# pre-existing user entry\nscratch/\n")
        cases = [
            test_install_places_copies_under_exact_names,
            test_binding_names_the_agent_by_login_and_the_role_separately,
            test_exclude_block_names_the_copies_and_keeps_user_entries,
            test_switch_removes_only_what_it_installed,
            test_role_changes_agent_does_not,
            test_nothing_committed_is_written,
            test_locally_adapted_copy_blocks_a_switch,
            test_force_stashes_before_replacing,
            test_collision_with_a_committed_skill_is_refused_and_leaves_role_intact,
            test_activation_says_where_the_role_reaches_the_session,
            test_tier1_lists_charter_index_and_workflow_from_project_memory,
            test_tier1_omits_a_class_the_role_does_not_have,
            test_tier1_accepts_the_single_file_workflow_shape,
            test_outside_a_working_copy_only_the_charter_loads,
            test_explicit_project_binds_even_without_a_working_copy,
            test_status_reports_agent_and_role,
            test_deactivate_clears_role_keeps_agent,
            test_binding_is_refused_inside_a_session,
            test_a_role_change_announces_nothing,
            test_unknown_role_is_a_usage_error,
            test_activation_works_inside_a_linked_worktree,
            test_a_failure_anywhere_in_the_switch_restores_everything,
            test_a_backup_left_by_a_crash_is_stashed_not_dropped,
            test_a_failed_deactivation_restores_the_copies,
        ]
        for case in cases:
            try:
                case(f, tmp) if case.__code__.co_argcount == 2 else case(f)
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
        print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
