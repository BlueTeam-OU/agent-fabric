#!/usr/bin/env python3
"""Behavioural tests for runtime/claude-code/hooks/session-start.py and
runtime/claude-code/bootstrap.sh: a session started from the parent
projects/ directory learns the agent from the OS, records the working
copy and project it is in, and never touches the role.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
import socket
HOST = socket.gethostname().split('.')[0]
ROOT = os.path.dirname(HERE)
HOOK = os.path.join(ROOT, "runtime", "claude-code", "hooks", "session-start.sh")
BOOTSTRAP = os.path.join(ROOT, "runtime", "claude-code", "bootstrap.sh")


def id_un() -> str:
    return subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()


def git_repo(path: str, remote: str) -> None:
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q", "."], cwd=path, check=True)
    subprocess.run(["git", "remote", "add", "origin", remote], cwd=path, check=True)


def run_hook(payload: dict, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", HOOK], input=json.dumps(payload), capture_output=True, text=True, env=env)


def context_of(proc: subprocess.CompletedProcess) -> str:
    """The hook's stdout is one JSON object whose additionalContext is
    what the session is given; the human line is its first line."""
    doc = json.loads(proc.stdout)
    assert doc["hookSpecificOutput"]["hookEventName"] == "SessionStart", proc.stdout
    return doc["hookSpecificOutput"]["additionalContext"]


def test_hook_records_context_not_identity(tmp: str) -> None:
    state = os.path.join(tmp, "state")
    wc = os.path.join(tmp, "legacy-clone-2")
    git_repo(wc, "git@github.com:gzapi-org/gzapp.git")
    env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state,
           "USER": "architect01", "LOGNAME": "architect01"}
    # A pre-existing binding with a role: the hook must keep it.
    os.makedirs(os.path.join(state, "agents", id_un()))
    with open(os.path.join(state, "agents", id_un(), "binding.json"), "w", encoding="utf-8") as fh:
        json.dump({"agent": id_un(), "host": HOST, "role": "architect-cto", "updated_at": "x"}, fh)
    proc = run_hook({"cwd": wc, "session_id": "sess-123"}, env)
    assert proc.returncode == 0, proc.stderr
    ctx = context_of(proc)
    assert ctx.splitlines()[0].startswith(f"agent-fabric: agent={id_un()}"), ctx
    assert "project=gzapp" in ctx and "role=architect-cto" in ctx, ctx
    b = json.load(open(os.path.join(state, "agents", id_un(), "binding.json"), encoding="utf-8"))
    assert b["agent"] == id_un() and b["role"] == "architect-cto"
    assert b["project"] == "gzapp" and b["working_copy"] == wc and b["session"] == "sess-123", b


def test_hook_gives_the_project_layer_from_the_working_copy(tmp: str) -> None:
    """The remit for the role in THIS working copy and the pointer to its
    INDEX are the hook's to give (the role layer is the launcher's); what
    the working copy lacks is said in one line, and outside a working
    copy there is no project layer at all."""
    state = os.path.join(tmp, "state")
    wc = os.path.join(tmp, "gzapp")
    git_repo(wc, "git@github.com:gzapi-org/gzapp.git")
    os.makedirs(os.path.join(state, "agents", id_un()))
    with open(os.path.join(state, "agents", id_un(), "binding.json"), "w", encoding="utf-8") as fh:
        json.dump({"agent": id_un(), "host": HOST, "role": "db-admin", "updated_at": "x"}, fh)
    env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state}
    ctx = context_of(run_hook({"cwd": wc}, env))
    assert "has no remit for db-admin" in ctx and "no distilled knowledge for db-admin" in ctx, ctx
    os.makedirs(os.path.join(wc, ".agent-fabric", "roles"))
    os.makedirs(os.path.join(wc, ".agent-fabric", "memory", "db-admin"))
    with open(os.path.join(wc, ".agent-fabric", "roles", "db-admin.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: db-admin\nclass: remit\nproject: gzapp\n---\n\n# db-admin — remit in gzapp\n\nREMIT-BODY-LINE: migrations under infra/db/.\n")
    with open(os.path.join(wc, ".agent-fabric", "memory", "db-admin", "INDEX.md"), "w", encoding="utf-8") as fh:
        fh.write("# index\n")
    ctx = context_of(run_hook({"cwd": wc}, env))
    assert "REMIT-BODY-LINE" in ctx and "class: remit" not in ctx, ctx
    assert "# db-admin — remit in gzapp (.agent-fabric/roles/db-admin.md)" in ctx, ctx
    assert ".agent-fabric/memory/db-admin/INDEX.md lists every slice" in ctx and "nothing else now" in ctx, ctx
    parent = os.path.join(tmp, "projects"); os.makedirs(parent)
    ctx = context_of(run_hook({"cwd": parent}, env))
    assert "not in a registered working copy" in ctx and "REMIT-BODY-LINE" not in ctx, ctx


def test_hook_says_when_the_binding_drifted_from_the_launch(tmp: str) -> None:
    """Launched as one role (the stamp the launcher exports), bound to
    another since: the hook prints the drift line; same role, no line."""
    state = os.path.join(tmp, "state")
    parent = os.path.join(tmp, "projects"); os.makedirs(parent)
    os.makedirs(os.path.join(state, "agents", id_un()))
    with open(os.path.join(state, "agents", id_un(), "binding.json"), "w", encoding="utf-8") as fh:
        json.dump({"agent": id_un(), "host": HOST, "role": "db-admin", "updated_at": "x"}, fh)
    env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state, "AGENT_FABRIC_LAUNCH_ROLE": "backend-dev"}
    proc = run_hook({"cwd": parent}, env)
    assert proc.returncode == 0, proc.stderr
    assert "DRIFT launched as backend-dev, binding now db-admin" in proc.stdout and "relaunch" in proc.stdout, proc.stdout
    env["AGENT_FABRIC_LAUNCH_ROLE"] = "db-admin"
    proc = run_hook({"cwd": parent}, env)
    assert "DRIFT" not in proc.stdout, proc.stdout
    env.pop("AGENT_FABRIC_LAUNCH_ROLE")
    proc = run_hook({"cwd": parent}, env)
    assert "DRIFT" not in proc.stdout, "an unlaunched session has nothing to drift from"


def test_hook_says_when_the_working_copy_trails_its_origin(tmp: str) -> None:
    """A working copy behind its origin's default branch (as of its last
    fetch) is said to the session, which would otherwise take an older
    CLAUDE.md for the project's; a current one says nothing."""
    state = os.path.join(tmp, "state"); os.makedirs(os.path.join(state, "agents", id_un()))
    env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state}
    g = lambda cwd, *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                                      cwd=cwd, check=True, capture_output=True)
    origin = os.path.join(tmp, "origin.git"); g(tmp, "init", "-q", "--bare", "-b", "main", origin)
    wc = os.path.join(tmp, "gzapp"); g(tmp, "clone", "-q", origin, wc)
    g(wc, "commit", "-q", "--allow-empty", "-m", "base"); g(wc, "push", "-q", "origin", "HEAD:main")
    g(wc, "remote", "set-url", "--push", "origin", origin)
    ctx = context_of(run_hook({"cwd": wc}, env))
    assert "lacks" not in ctx, ctx
    other = os.path.join(tmp, "other"); g(tmp, "clone", "-q", origin, other)
    g(other, "commit", "-q", "--allow-empty", "-m", "newer"); g(other, "push", "-q", "origin", "HEAD:main")
    g(wc, "fetch", "-q", "origin")
    ctx = context_of(run_hook({"cwd": wc}, env))
    assert "this working copy (main) lacks 1 commit(s) of origin/main" in ctx, ctx


def test_hook_says_when_the_branch_sweep_is_due(tmp: str) -> None:
    """A working copy never swept, or last swept over a week ago, is said
    to the session; a sweep by bin/fabric-branches records the working copy
    under the same name the hook reads, and silences it."""
    state = os.path.join(tmp, "state"); os.makedirs(os.path.join(state, "agents", id_un()))
    env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state}
    g = lambda cwd, *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                                      cwd=cwd, check=True, capture_output=True)
    origin = os.path.join(tmp, "origin.git"); g(tmp, "init", "-q", "--bare", "-b", "main", origin)
    wc = os.path.join(tmp, "gzapp"); g(tmp, "clone", "-q", origin, wc)
    g(wc, "commit", "-q", "--allow-empty", "-m", "base"); g(wc, "push", "-q", "origin", "HEAD:main")
    ctx = context_of(run_hook({"cwd": wc}, env))
    assert "branch sweep due in this working copy (never swept)" in ctx, ctx
    sweep = subprocess.run([os.path.join(ROOT, "bin", "fabric-branches"), "--sweep"], cwd=wc,
                           capture_output=True, text=True, env={**env, "GH_TOKEN": ""})
    assert sweep.returncode == 0, sweep.stdout + sweep.stderr
    ctx = context_of(run_hook({"cwd": wc}, env))
    assert "branch sweep due" not in ctx, ctx
    record = os.path.join(state, "agents", id_un(), "branch-sweep.json")
    with open(record, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc = {k: "2026-01-01T00:00:00Z" for k in doc}
    with open(record, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    ctx = context_of(run_hook({"cwd": wc}, env))
    assert "branch sweep due in this working copy (last 2026-01-01)" in ctx, ctx


def test_a_subagent_start_never_rebinds_the_login(tmp: str) -> None:
    """A worktree-isolated subagent starts in <checkout>/.claude/worktrees/
    <name>/ with the parent's session id; the hook ran there and repointed
    the login's binding at the subagent's scratch checkout (2026-10-01)."""
    state = os.path.join(tmp, "state")
    main_wc = os.path.join(tmp, "agent-fabric")
    git_repo(main_wc, "git@github.com:gzapi-org/agent-fabric.git")
    sub_wc = os.path.join(main_wc, ".claude", "worktrees", "agent-abc123")
    git_repo(sub_wc, "git@github.com:gzapi-org/agent-fabric.git")
    env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state}
    binding_path = os.path.join(state, "agents", id_un(), "binding.json")
    os.makedirs(os.path.dirname(binding_path))
    with open(binding_path, "w", encoding="utf-8") as fh:
        json.dump({"agent": id_un(), "host": HOST, "role": "fabric-coordinator", "working_copy": main_wc,
                   "session": "parent", "updated_at": "x"}, fh)
    before = open(binding_path, "rb").read()
    for payload in ({"cwd": sub_wc, "session_id": "parent"},
                    {"cwd": main_wc, "session_id": "parent", "agent_id": "abc123", "agent_type": "code-medium"}):
        proc = run_hook(payload, env)
        assert proc.returncode == 0, proc.stderr
        # Not a byte of it: a rewrite to the same fields re-stamps updated_at.
        assert open(binding_path, "rb").read() == before, (payload, open(binding_path).read())
    # A subagent's start creates no binding where there was none.
    os.unlink(binding_path)
    run_hook({"cwd": sub_wc, "session_id": "parent"}, env)
    assert not os.path.exists(binding_path), "a subagent's start created a binding"
    with open(binding_path, "wb") as fh:
        fh.write(before)
    # agent_type alone is a main session launched with --agent: it binds.
    run_hook({"cwd": main_wc, "session_id": "main-agent", "agent_type": "code-plan"}, env)
    assert json.load(open(binding_path, encoding="utf-8"))["session"] == "main-agent", open(binding_path).read()
    # The session's own start still writes it.
    other = os.path.join(tmp, "other-clone")
    git_repo(other, "git@github.com:gzapi-org/agent-fabric.git")
    run_hook({"cwd": other, "session_id": "next"}, env)
    b = json.load(open(binding_path, encoding="utf-8"))
    assert b["working_copy"] == other and b["session"] == "next", b


def test_hook_from_the_parent_directory_has_no_project(tmp: str) -> None:
    state = os.path.join(tmp, "state")
    parent = os.path.join(tmp, "projects")
    os.makedirs(parent)
    env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state}
    proc = run_hook({"cwd": parent}, env)
    assert proc.returncode == 0, proc.stderr
    assert f"agent={id_un()}" in proc.stdout and "project=(none)" in proc.stdout, proc.stdout
    assert "role=(none" in proc.stdout, proc.stdout


def test_hook_reports_a_bad_marker_and_still_starts(tmp: str) -> None:
    """An invalid .agent-fabric-project is a hard error in the resolver
    (workingcopy.resolve); the hook turns it into context the session
    reads, never a blocked start."""
    state = os.path.join(tmp, "state")
    wc = os.path.join(tmp, "typo")
    git_repo(wc, "git@github.com:gzapi-org/gzapp.git")
    with open(os.path.join(wc, ".agent-fabric-project"), "w", encoding="utf-8") as fh:
        fh.write("gzap\n")
    env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state}
    proc = run_hook({"cwd": wc, "session_id": "sess-9"}, env)
    assert proc.returncode == 0, proc.stderr
    ctx = context_of(proc)
    assert ".agent-fabric-project" in ctx and "'gzap'" in ctx, ctx
    assert "project=gzapp" not in ctx, "the marker was ignored and the remote decided"


def test_hook_never_blocks(tmp: str) -> None:
    env = {**os.environ, "AGENT_FABRIC_ROOT": os.path.join(tmp, "nowhere"),
           "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state")}
    proc = run_hook({"cwd": "/"}, env)
    assert proc.returncode == 0, "a broken control plane must not block a session start"
    proc = subprocess.run(["bash", HOOK], input="not json", capture_output=True, text=True,
                          env={**os.environ, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state2")})
    assert proc.returncode == 0


def test_hook_exports_the_control_plane_into_the_session_shell(tmp: str) -> None:
    """A SessionStart hook may append `export` lines to $CLAUDE_ENV_FILE;
    the harness sources them into every later Bash call. AGENT_FABRIC_ROOT
    must be one of them — the integration docs run inbox.mjs through it,
    and until 2026-09-14 it was set only for the hook's own child."""
    env_file = os.path.join(tmp, "claude-env")
    env = {**os.environ, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state"), "CLAUDE_ENV_FILE": env_file}
    env.pop("AGENT_FABRIC_ROOT", None)
    proc = run_hook({"cwd": "/"}, env)
    assert proc.returncode == 0, proc.stderr
    exported = subprocess.run(["bash", "-c", f'source "{env_file}" && printf %s "$AGENT_FABRIC_ROOT"'],
                              capture_output=True, text=True).stdout
    assert exported == ROOT, exported
    # Resume and compaction run the hook again: the line is written once.
    run_hook({"cwd": "/"}, env)
    assert open(env_file, encoding="utf-8").read().count("export AGENT_FABRIC_ROOT=") == 1
    # Without the file nothing is written anywhere and the hook still runs.
    env.pop("CLAUDE_ENV_FILE")
    assert run_hook({"cwd": "/"}, env).returncode == 0


def test_hook_says_when_the_session_has_no_inbox_watch(tmp: str) -> None:
    """Under a process named claude with no `inbox.mjs --follow` beneath it,
    the context says to arm the watch; with one beneath it, it does not."""
    state = os.path.join(tmp, "state")
    env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state}
    fake = os.path.join(tmp, "bin", "claude")
    os.makedirs(os.path.dirname(fake))
    payload = os.path.join(tmp, "payload.json")
    with open(payload, "w", encoding="utf-8") as fh:
        json.dump({"cwd": tmp, "session_id": "sess-w", "source": "resume"}, fh)
    with open(fake, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/bash\n"  # not env: env re-execs bash and the process is no longer named claude
                 
                 "if [ \"$1\" = watch ]; then (exec -a 'node inbox.mjs --follow' sleep 20) & w=$!; sleep 0.3; fi\n"
                 "if [ \"$1\" = named ]; then (exec -a 'node /home/x/.local/bin/gzcoord-inbox --follow' sleep 20) & w=$!; sleep 0.3; fi\n"
                 f"bash {HOOK} < {payload}\n"
                 "[ -n \"${w:-}\" ] && kill $w\n")
    os.chmod(fake, 0o755)
    bare = subprocess.run([fake], capture_output=True, text=True, env=env)
    assert "NO INBOX WATCH is running for this session (resume)" in context_of(bare), bare.stdout
    armed = subprocess.run([fake, "watch"], capture_output=True, text=True, env=env)
    assert "NO INBOX WATCH" not in context_of(armed), armed.stdout
    named = subprocess.run([fake, "named"], capture_output=True, text=True, env=env)
    assert "NO INBOX WATCH" not in context_of(named), "the watch armed by its name on PATH was not seen:\n" + named.stdout


def test_bootstrap_restarts_the_control_agent_unless_its_caller_is_the_control_agent(tmp: str) -> None:
    """A changed unit is restarted by bootstrap run by hand, and left to the
    daemon when the daemon runs it (`fabric-ctl upgrade fabric`): a restart
    there would kill the process waiting on bootstrap."""
    import socket
    runtime_dir = os.path.join(tmp, "run"); os.makedirs(runtime_dir)
    bus = socket.socket(socket.AF_UNIX); bus.bind(os.path.join(runtime_dir, "bus"))
    bindir = os.path.join(tmp, "bin"); os.makedirs(bindir)
    calls = os.path.join(tmp, "systemctl.log")
    with open(os.path.join(bindir, "systemctl"), "w") as fh:
        fh.write(f'#!/bin/sh\necho "$*" >> {calls}\n[ "$2" = is-active ] && echo active\nexit 0\n')
    os.chmod(os.path.join(bindir, "systemctl"), 0o755)
    try:
        for defer in (True, False):
            projects = os.path.join(tmp, f"projects-{defer}"); home = os.path.join(tmp, f"home-{defer}")
            os.makedirs(projects); os.makedirs(home)
            if os.path.exists(calls): os.unlink(calls)
            env = {**os.environ, "HOME": home, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, f"state-{defer}"),
                   "XDG_RUNTIME_DIR": runtime_dir, "PATH": bindir + os.pathsep + os.environ["PATH"]}
            env.pop("CLAUDE_CONFIG_DIR", None)
            if defer: env["AGENT_FABRIC_DEFER_AGENTD_RESTART"] = "1"
            else: env.pop("AGENT_FABRIC_DEFER_AGENTD_RESTART", None)
            proc = subprocess.run(["bash", BOOTSTRAP, "--projects", projects], capture_output=True, text=True, env=env)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            restarted = "restart agent-fabric-agentd" in open(calls).read()
            if defer:
                assert not restarted, "the daemon running bootstrap was restarted under it"
                assert "agent-fabric-agentd: unit changed; restart left to the caller" in proc.stdout, proc.stdout
            else:
                assert restarted, "a changed unit was not restarted by a hand bootstrap"
    finally:
        bus.close()


def test_bootstrap_writes_only_the_workspace_and_home_files(tmp: str) -> None:
    projects = os.path.join(tmp, "projects")
    home = os.path.join(tmp, "home")
    os.makedirs(projects); os.makedirs(home)
    # A runtime dir with no bus: the control agent's unit is installed and
    # never handed to THIS account's real user manager.
    runtime_dir = os.path.join(tmp, "run"); os.makedirs(runtime_dir)
    env = {**os.environ, "HOME": home, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state"), "XDG_RUNTIME_DIR": runtime_dir}
    env.pop("CLAUDE_CONFIG_DIR", None)
    # A folder in the workspace that is not a registered working copy: never trusted.
    stray = os.path.join(projects, "not-a-project"); os.makedirs(stray)
    proc = subprocess.run(["bash", BOOTSTRAP, "--projects", projects, "--dry-run"], capture_output=True, text=True, env=env)
    assert "systemd/user/agent-fabric-agentd.service (would write)" in proc.stdout, proc.stdout
    # Claude Code itself may create .claude.json when bootstrap asks it
    # something; what the dry run must not do is record any trust there.
    cfg = os.path.join(home, ".claude.json")
    recorded = json.load(open(cfg, encoding="utf-8")).get("projects", {}) if os.path.exists(cfg) else {}
    assert "trusted in Claude Code (would write)" in proc.stdout and not any(
        v.get("hasTrustDialogAccepted") for v in recorded.values()), "the dry run says what it would trust and records none"
    proc = subprocess.run(["bash", BOOTSTRAP, "--projects", projects], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    unit = os.path.join(home, ".config", "systemd", "user", "agent-fabric-agentd.service")
    assert os.path.isfile(unit), "the control agent's unit is installed per account"
    trusted = {d for d, v in json.load(open(os.path.join(home, ".claude.json"), encoding="utf-8"))["projects"].items()
               if v.get("hasTrustDialogAccepted") is True}
    assert trusted == {os.path.realpath(projects), os.path.realpath(ROOT)}, \
        ("the workspace and the fabric are trusted, and a folder that is no registered working copy is not", trusted)
    assert "agent-fabric-agentd: installed, not started" in proc.stdout and "no user manager" in proc.stdout, proc.stdout
    claude_md = open(os.path.join(projects, "CLAUDE.md"), encoding="utf-8").read()
    assert "@agent-fabric/CLAUDE.md" in claude_md and len(claude_md.splitlines()) <= 8, claude_md
    settings = json.load(open(os.path.join(projects, ".claude", "settings.json"), encoding="utf-8"))
    hooks = json.dumps(settings["hooks"])
    assert "session-start.sh" in hooks and "agent-dispatch-guard.sh" in hooks and ROOT in hooks
    assert "communication/gzcoord/scripts/inbox.mjs" in hooks, "the workspace drains the GZCoord inbox too"
    for event in ("PreToolUse", "UserPromptSubmit", "SessionEnd"):
        assert "plan-hold.sh" in json.dumps(settings["hooks"][event]), f"the plan hold follows the mode on {event}"
    assert "model-fallback-note.sh" in json.dumps(settings["hooks"]["PostModelSwitch"]), "an automatic fallback is announced to the session"
    assert any("plan-hold.sh" in json.dumps(g) and "matcher" not in g for g in settings["hooks"]["PreToolUse"]), "the plan hold sees every tool call"
    assert "statusline.sh" in settings["statusLine"]["command"]
    assert settings["env"]["CLAUDE_CODE_DISABLE_TERMINAL_TITLE"] == "1", "the hook must be the only tab-title writer"
    assert not os.path.exists(os.path.join(home, ".claude", "commands", "role.md")), "/role is retired; nothing installs it"
    with open(os.path.join(home, ".claude", "agents", "code-review.md"), encoding="utf-8") as fh:
        assert "\nmodel: claude-opus-5-5\n" in fh.read(), "the reviewer file carries the anthropic column's pin"
    with open(os.path.join(home, ".claude", "agents", "code-high.md"), encoding="utf-8") as fh:
        assert "\nmodel: opus\n" in fh.read(), "an unpinned class keeps its alias"
    for skill in ("subagent-dispatch", "gzcoord-send", "gzcoord-receive"):
        assert os.path.isfile(os.path.join(home, ".claude", "skills", skill, "SKILL.md")), skill
    # Every command a session is told to run is on PATH by name and allowed
    # by a narrow rule — never a wrapper that runs another command (the
    # owner, 2026-09-26: no approval for any fabric script or executable).
    cmds = json.load(open(os.path.join(ROOT, "runtime", "claude-code", "commands.json"), encoding="utf-8"))
    for name, rel in cmds["commands"].items():
        link = os.path.join(home, ".local", "bin", name)
        assert os.path.islink(link) and os.readlink(link) == os.path.join(ROOT, rel), (name, link)
    allow = json.load(open(os.path.join(home, ".claude", "settings.json"), encoding="utf-8"))["permissions"]["allow"]
    assert "Bash(gzcoord-inbox *)" in allow and "Bash(fabric-status *)" in allow, allow
    assert not any(f"Bash({n} *)" in allow for n in cmds["not_allowed"]), allow
    # A file at a command's name that the fabric did not make is the
    # account's: refused, named, never replaced.
    foreign = os.path.join(home, ".local", "bin", "gzmsg")
    os.remove(foreign); open(foreign, "w").write("mine\n")
    again = subprocess.run(["bash", BOOTSTRAP, "--projects", projects], capture_output=True, text=True, env=env)
    assert "is not a link this fabric made" in again.stderr and open(foreign).read() == "mine\n", again.stderr
    allow = json.load(open(os.path.join(home, ".claude", "settings.json"), encoding="utf-8"))["permissions"]["allow"]
    assert "Bash(gzmsg *)" not in allow, "a foreign gzmsg on PATH kept the fabric's allow rule"
    os.remove(foreign)
    for f in ("code-low.md", "code-medium.md", "code-high.md"):
        assert os.path.isfile(os.path.join(home, ".claude", "agents", f))
    assert not os.path.exists(os.path.join(projects, ".git")), "projects/ must not become a repository"
    # A registered working copy beside the fabric gets the hooks — also
    # when it is a LINKED WORKTREE, whose .git is a file, not a directory.
    main_repo = os.path.join(tmp, "main-repo")
    subprocess.run(["git", "init", "-q", "-b", "main", main_repo], check=True)
    subprocess.run(["git", "-C", main_repo, "remote", "add", "origin", "git@github.com:gzapi-org/gzapp.git"], check=True)
    gitenv = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    open(os.path.join(main_repo, "seed"), "w").write("s\n")
    subprocess.run(["git", "-C", main_repo, "add", "seed"], check=True)
    subprocess.run(["git", "-C", main_repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed"], check=True, env=gitenv)
    linked = os.path.join(projects, "gzapp-linked")
    subprocess.run(["git", "-C", main_repo, "worktree", "add", "-q", "--detach", linked, "HEAD"], check=True)
    assert os.path.isfile(os.path.join(linked, ".git")), "a linked worktree's .git is a file"
    proc = subprocess.run(["bash", BOOTSTRAP, "--projects", projects], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    hooks_path = subprocess.run(["git", "-C", linked, "config", "--get", "core.hooksPath"], capture_output=True, text=True).stdout.strip()
    assert hooks_path == os.path.join(ROOT, "policies", "githooks"), f"the linked worktree got no hooks: {hooks_path!r}\n{proc.stdout}"
    # Idempotent: a second run changes nothing.
    proc = subprocess.run(["bash", BOOTSTRAP, "--projects", projects], capture_output=True, text=True, env=env)
    assert "0 written" in proc.stdout, proc.stdout
    # An account that still carries the retired /role command from an
    # earlier bootstrap: our copy is removed (dry-run says so first), a
    # human's own commands/role.md and a .before-agent-fabric backup stay.
    retired = os.path.join(home, ".claude", "commands", "role.md")
    os.makedirs(os.path.dirname(retired), exist_ok=True)
    with open(retired, "w", encoding="utf-8") as fh:
        fh.write("---\ndescription: x\n---\n!`python3 /old/agent-fabric/tools/fabric/role.py $ARGUMENTS`\n")
    with open(retired + ".before-agent-fabric", "w", encoding="utf-8") as fh:
        fh.write("the human's own\n")
    proc = subprocess.run(["bash", BOOTSTRAP, "--projects", projects, "--dry-run"], capture_output=True, text=True, env=env)
    assert "would remove" in proc.stdout and os.path.isfile(retired), proc.stdout
    proc = subprocess.run(["bash", BOOTSTRAP, "--projects", projects], capture_output=True, text=True, env=env)
    assert not os.path.exists(retired) and "removed: /role is retired" in proc.stdout, proc.stdout
    assert os.path.isfile(retired + ".before-agent-fabric"), "the human's backup was touched"
    with open(retired, "w", encoding="utf-8") as fh:
        fh.write("---\ndescription: my own role command\n---\nnothing to do with the fabric\n")
    proc = subprocess.run(["bash", BOOTSTRAP, "--projects", projects], capture_output=True, text=True, env=env)
    assert os.path.isfile(retired), "a command the human wrote was removed"
    os.remove(retired); os.remove(retired + ".before-agent-fabric")
    # An existing settings file keeps its own entries.
    with open(os.path.join(projects, ".claude", "settings.json"), "w", encoding="utf-8") as fh:
        json.dump({"permissions": {"allow": ["Bash(ls:*)"]}, "env": {"MY_OWN": "x"}, "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}, fh)
    proc = subprocess.run(["bash", BOOTSTRAP, "--projects", projects], capture_output=True, text=True, env=env)
    settings = json.load(open(os.path.join(projects, ".claude", "settings.json"), encoding="utf-8"))
    assert settings["env"] == {"MY_OWN": "x", "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"}, settings["env"]
    assert settings["permissions"] == {"allow": ["Bash(ls:*)"]}
    assert any("echo mine" in json.dumps(g) for g in settings["hooks"]["SessionStart"])
    assert any("session-start.sh" in json.dumps(g) for g in settings["hooks"]["SessionStart"])
    # Entries from an EARLIER bootstrap out of another checkout are replaced,
    # not kept beside the new ones: an account that moved from a shared path
    # to its own clone must end up with one set of hooks.
    with open(os.path.join(projects, ".claude", "settings.json"), "w", encoding="utf-8") as fh:
        json.dump({"hooks": {"SessionStart": [{"hooks": [{"type": "command",
                   "command": "bash \"/somewhere/else/agent-fabric/runtime/claude-code/hooks/session-start.sh\""}]}]}}, fh)
    proc = subprocess.run(["bash", BOOTSTRAP, "--projects", projects], capture_output=True, text=True, env=env)
    settings = json.load(open(os.path.join(projects, ".claude", "settings.json"), encoding="utf-8"))
    starts = [json.dumps(g) for g in settings["hooks"]["SessionStart"]]
    assert not any("/somewhere/else" in g for g in starts), starts
    assert sum("session-start.sh" in g for g in starts) == 1, starts


def test_hook_says_the_job_list(tmp: str) -> None:
    """Silent with no open job; the active job and the queue when there is
    one; a warning when the active job's working copy is not this session's."""
    state = os.path.join(tmp, "state"); os.makedirs(os.path.join(state, "agents", id_un()))
    env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_STATE_DIR": state}
    here, there = os.path.join(tmp, "here"), os.path.join(tmp, "there")
    git_repo(here, "https://example.invalid/here.git"); git_repo(there, "https://example.invalid/there.git")
    jobs = lambda *a: subprocess.run([os.path.join(ROOT, "bin", "fabric-jobs"), *a], cwd=here, env=env,
                                     capture_output=True, text=True, check=True)
    assert "jobs —" not in context_of(run_hook({"cwd": here}, env))
    jobs("add", "the job here"); jobs("add", "the job there", "--working-copy", there)
    ctx = context_of(run_hook({"cwd": here}, env))
    assert "jobs — none active; 2 queued. `fabric-jobs next`" in ctx, ctx
    jobs("start", "j1")
    ctx = context_of(run_hook({"cwd": here}, env))
    assert "jobs — active j1: the job here; 1 queued" in ctx and "Your active job is in" not in ctx, ctx
    jobs("block", "j1", "a reply"); jobs("start", "j2")
    ctx = context_of(run_hook({"cwd": here}, env))
    assert f"active j2: the job there; 1 blocked" in ctx and f"Your active job is in {there}, and this session is in {here}" in ctx \
        and "fabric-fresh --job j2" in ctx, ctx
    # A list the hook cannot read never costs the session its start.
    with open(os.path.join(state, "agents", id_un(), "jobs.json"), "w", encoding="utf-8") as fh:
        fh.write("{ not json")
    proc = run_hook({"cwd": here}, env)
    ctx = context_of(proc)
    assert proc.returncode == 0 and "agent=" in ctx and "jobs —" not in ctx, proc.stdout + proc.stderr


def main() -> int:
    cases = [test_hook_records_context_not_identity, test_a_subagent_start_never_rebinds_the_login,
             test_hook_gives_the_project_layer_from_the_working_copy,
             test_hook_says_when_the_binding_drifted_from_the_launch,
             test_hook_from_the_parent_directory_has_no_project,
             test_hook_says_when_the_working_copy_trails_its_origin,
             test_hook_reports_a_bad_marker_and_still_starts,
             test_hook_never_blocks, test_hook_exports_the_control_plane_into_the_session_shell,
             test_hook_says_when_the_session_has_no_inbox_watch,
             test_hook_says_when_the_branch_sweep_is_due,
             test_hook_says_the_job_list,
             test_bootstrap_restarts_the_control_agent_unless_its_caller_is_the_control_agent,
             test_bootstrap_writes_only_the_workspace_and_home_files]
    failures = 0
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                case(tmp)
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
