#!/usr/bin/env python3
"""tools/fabric/role.py — bind a role to the current agent (bin/fabric-role).

>>> help
    role.py activate <role> [--project ID] [--workspace DIR] [--force]
    role.py status                       what is this agent right now?
    role.py deactivate                   remove the installed copies
    role.py list                         the roles available

The AGENT is the Linux login (runtime/identity.py); it never changes here.
Activation binds a ROLE to that agent — recorded in the agent's runtime
binding outside the repository — and installs the role's skills and
commands into the WORKSPACE's `.claude/`, where the harness discovers them.
The workspace is `--workspace`, else $CLAUDE_PROJECT_DIR, else the current
directory: the place Claude Code will be launched from, which may be the
parent `projects/` directory or one working copy.

FROM A LOGIN SHELL, NEVER INSIDE A SESSION (owner, 2026-09-15). The
launcher reads the binding and renders the role into the session's
system prompt (tools/fabric/launch_prompt.py); a session's role is fixed
for its life, and a rebind under a running session would leave its
prompt and its binding disagreeing until a relaunch. So activate and
deactivate refuse when the environment says a session is running
(CLAUDECODE, CLAUDE_ENV_FILE, AGENT_FABRIC_LAUNCH_PROFILE); status and
list change nothing and run anywhere. bin/fabric-role is the front door
and refuses first; this is the backstop for a Bash tool call that names
the file directly. The old /role command is gone.

Why copies rather than symlinks: an agent that lives as one role for weeks
adapts its own tools. A copy lets that happen and survives; a link would
make every agent share one file. So the copy is working state, and a switch
that would discard local edits stops and says so instead.

Why nothing here writes to a committed file: a switch can happen in the
middle of unrelated work. The binding goes to the agent's state directory;
a per-agent `role-history.jsonl` there keeps the chronology for provenance.

A switch is a transaction (review, 2026-09-16). The new copies are built
under `.claude/.agent-fabric-staging/<tx>/` first; the previous ones are
moved, not deleted, to `.claude/.agent-fabric-backup/<tx>/`; each staged
copy reaches its name by one rename; the binding is written last and is
the commit point. Anything failing before the cleanup — a full disk, a
kill, a fault a test injects (AGENT_FABRIC_FAULT) — rolls the workspace,
the exclude block and the binding back to what they were, under the
agent lock the whole way. A backup a crash left behind is moved to the
stash on the next run, never silently dropped.

Exit 0 on success, 1 on a refusal that needs a decision, 2 on usage error.
<<< help
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layout = _load("fabric_layout", os.path.join(HERE, "layout.py"))
identity = _load("fabric_identity", os.path.join(layout.FABRIC_ROOT, "runtime", "identity.py"))

MARK_BEGIN = "# >>> agent-fabric role activator (generated) >>>"
MARK_END = "# <<< agent-fabric role activator (generated) <<<"


def digest_path(path: str) -> str:
    """Content digest of a file or a whole directory, order-independent."""
    sha = hashlib.sha256()
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            sha.update(fh.read())
        return sha.hexdigest()[:32]
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            sha.update(os.path.relpath(full, path).encode())
            with open(full, "rb") as fh:
                sha.update(fh.read())
    return sha.hexdigest()[:32]


def git_exclude_path(workspace: str) -> str | None:
    """Where git reads local excludes for this workspace, or None when the
    workspace is not inside a repository (the parent `projects/` directory).

    `git rev-parse --git-path` is git's own resolver, so linked worktrees,
    separate git dirs and submodules are handled without this code knowing
    about any of them.
    """
    try:
        out = subprocess.run(["git", "rev-parse", "--git-path", "info/exclude"],
                             cwd=workspace, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not out:
        return None
    return out if os.path.isabs(out) else os.path.join(workspace, out)


def write_exclude_block(workspace: str, paths: list[str]) -> None:
    """Installed copies are untracked files with ordinary names, so git is
    told about them explicitly, locally, in a delimited block."""
    exclude = git_exclude_path(workspace)
    if exclude is None:
        return
    os.makedirs(os.path.dirname(exclude), exist_ok=True)
    existing: list[str] = []
    if os.path.exists(exclude):
        with open(exclude, encoding="utf-8") as fh:
            keep, skipping = [], False
            for line in fh.read().split("\n"):
                if line.strip() == MARK_BEGIN:
                    skipping = True
                    continue
                if line.strip() == MARK_END:
                    skipping = False
                    continue
                if not skipping:
                    keep.append(line)
            existing = keep
    while existing and existing[-1] == "":
        existing.pop()
    block = [MARK_BEGIN, "# Installed by tools/fabric/role.py; do not edit by hand."]
    block += [f"/{p}" for p in sorted(set(paths) | set(TRANSIENT_DIRS))]
    block.append(MARK_END)
    identity.atomic_write(exclude, "\n".join(existing + [""] + block) + "\n")


def adapted_items(workspace: str, installed: list[dict]) -> list[dict]:
    out = []
    for item in installed:
        target = os.path.join(workspace, item["path"])
        if os.path.exists(target) and digest_path(target) != item.get("digest"):
            out.append(item)
    return out


STAGING_DIR = os.path.join(".claude", ".agent-fabric-staging")
BACKUP_DIR = os.path.join(".claude", ".agent-fabric-backup")
TRANSIENT_DIRS = (STAGING_DIR, BACKUP_DIR)


def _fault(point: str) -> None:
    """Failure injection for tests/test_role.py: raise at a named point when
    AGENT_FABRIC_FAULT names it (`role:<point>`). Never set outside a test;
    the rollback it exercises is what a kill or a full disk would need."""
    if os.environ.get("AGENT_FABRIC_FAULT") == f"role:{point}":
        raise RuntimeError(f"injected fault at {point}")


def _txid() -> str:
    return identity.now_iso().replace(":", "") + f"-{os.getpid()}"


def _remove(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def sweep_leftovers(workspace: str, state_dir: str) -> list[str]:
    """A previous run that died after its commit point may have left its
    staging (copies of committed sources: dropped) and its backup (the
    copies it had replaced: kept, moved to the stash). Returns what was
    moved so the caller can say so."""
    moved: list[str] = []
    staging = os.path.join(workspace, STAGING_DIR)
    if os.path.isdir(staging):
        shutil.rmtree(staging, ignore_errors=True)
    backup = os.path.join(workspace, BACKUP_DIR)
    if os.path.isdir(backup):
        for tx in sorted(os.listdir(backup)):
            src = os.path.join(backup, tx)
            dst = os.path.join(state_dir, "stash", f"interrupted-{tx}")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            moved.append(dst)
        shutil.rmtree(backup, ignore_errors=True)
    return moved


class WorkspaceTransaction:
    """The workspace half of an activation or deactivation: stage, back up,
    swap, and either commit (drop the backup) or roll back (restore it).
    Renames only, so each step is atomic on the filesystem the workspace
    is on; the set of steps is made whole again by rollback()."""

    def __init__(self, workspace: str, previous_workspace: str, txid: str):
        self.workspace, self.previous_workspace = workspace, previous_workspace
        self.staging = os.path.join(workspace, STAGING_DIR, txid)
        self.backup = os.path.join(previous_workspace, BACKUP_DIR, txid)
        self.staged: list[tuple[str, str]] = []      # (staged path, target rel)
        self.moved_out: list[tuple[str, str]] = []   # (original target, backup path)
        self.moved_in: list[str] = []                # targets now in place

    def stage(self, plan: list[tuple[str, str, str]]) -> list[dict]:
        """Copy every source into staging and digest it there; nothing under
        the workspace's real names changes."""
        installed: list[dict] = []
        for source, rel, kind in plan:
            staged = os.path.join(self.staging, rel)
            os.makedirs(os.path.dirname(staged), exist_ok=True)
            if os.path.isdir(source):
                shutil.copytree(source, staged)
            else:
                shutil.copy2(source, staged)
            self.staged.append((staged, rel))
            installed.append({"path": rel, "source": os.path.relpath(source, layout.FABRIC_ROOT),
                              "kind": kind, "digest": digest_path(staged)})
        return installed

    def back_up(self, previous: list[dict]) -> None:
        """Move exactly what a previous activation installed out of the way —
        never a sweep, never a delete."""
        for item in previous:
            target = os.path.join(self.previous_workspace, item["path"])
            if not os.path.lexists(target):
                continue
            kept = os.path.join(self.backup, item["path"])
            os.makedirs(os.path.dirname(kept), exist_ok=True)
            os.rename(target, kept)
            self.moved_out.append((target, kept))
            _fault(f"backup:{item['path']}")

    def install(self) -> None:
        for staged, rel in self.staged:
            target = os.path.join(self.workspace, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            os.rename(staged, target)
            self.moved_in.append(target)
            _fault(f"install:{rel}")

    def rollback(self) -> None:
        for target in reversed(self.moved_in):
            _remove(target)
        for target, kept in reversed(self.moved_out):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            os.rename(kept, target)
        self.moved_in.clear(); self.moved_out.clear()
        self.commit()

    def commit(self) -> None:
        """Drop the transaction's directories; best effort, after the binding
        is the fact. A leftover is swept by the next run (sweep_leftovers)."""
        for d in (self.staging, self.backup):
            shutil.rmtree(d, ignore_errors=True)
            parent = os.path.dirname(d)
            try:
                os.rmdir(parent)
            except OSError:
                pass


def append_history(state_dir: str, record: dict) -> None:
    # The agent's history file, appended under the agent lock (identity.py).
    identity.append_history(record, os.path.basename(state_dir))


# ---------------------------------------------------------------------------
# A role change announces nothing on the channel. It once sent a GOODBYE as
# the role being left, a type GZCOORD/1 has since retired; who holds which
# role, and whether a session runs, is now the control plane's to answer,
# from each account's binding and
# process table (tools/fabric/control/presence.py, docs/adr/ADR-030-presence-replaces-hello-and-goodbye.md).


def cmd_list() -> int:
    roles = layout.list_roles()
    if not roles:
        print(f"no roles under {layout.roles_dir()}")
        return 2
    print("available roles:", ", ".join(roles))
    return 0


def cmd_status(ctx: dict) -> int:
    binding = identity.read_binding(ctx["agent"])
    print(f"agent     {ctx['agent']}")
    print(f"host      {ctx['host']}")
    print(f"role      {binding.get('role') or '(none active)'}")
    print(f"project   {ctx['project'] or '(none)'}"
          + (f"  [from {ctx['project_source']}]" if ctx.get("project_source") else ""))
    print(f"working   {ctx['working_copy'] or '(not in a working copy)'}")
    if binding.get("workspace"):
        print(f"workspace {binding['workspace']}")
    if binding.get("updated_at"):
        print(f"since     {binding['updated_at']}")
    workspace = binding.get("workspace") or ""
    for item in binding.get("installed", []):
        drift = ""
        target = os.path.join(workspace, item["path"])
        if os.path.exists(target) and digest_path(target) != item.get("digest"):
            drift = "   [adapted locally]"
        print(f"  {item['kind']:8} {item['path']}{drift}")
    if not binding.get("role"):
        roles = layout.list_roles()
        if roles:
            print("available roles:", ", ".join(roles))
    return 0


HARNESS_ENV = ("CLAUDECODE", "CLAUDE_ENV_FILE", "AGENT_FABRIC_LAUNCH_PROFILE")


def harness_env_reason() -> str | None:
    """The variable that says a session is running, or None. One place,
    matching bin/fabric-role's own check."""
    for name in HARNESS_ENV:
        if os.environ.get(name):
            return name
    return None


def refuse_inside_session(what: str) -> int:
    name = harness_env_reason()
    if not name:
        return 0
    print(f"role: refusing to {what} inside a harness session (${name} is set).\n"
          "A role is bound from a login shell, never inside a session: the session's\n"
          "prompt already carries the role it was launched with, and a rebind under it\n"
          "would disagree with that prompt until a relaunch. Open a terminal, run\n"
          "fabric-role there, then relaunch.", file=sys.stderr)
    return 1


def cmd_deactivate(ctx: dict) -> int:
    if refuse_inside_session("drop the role"):
        return 1
    with identity.agent_lock(ctx["agent"]):
        return _deactivate_locked(ctx)


def _deactivate_locked(ctx: dict) -> int:
    binding = identity.read_binding(ctx["agent"])
    workspace = binding.get("workspace")
    if not binding.get("role"):
        print("no role active for this agent")
        return 0
    previous = binding.get("installed", []) or []
    tx = WorkspaceTransaction(workspace or ctx["state_dir"], workspace or ctx["state_dir"], _txid())
    try:
        if workspace:
            for path in sweep_leftovers(workspace, ctx["state_dir"]):
                print(f"an interrupted run's backup moved to {path}", file=sys.stderr)
            tx.back_up(previous)
            write_exclude_block(workspace, [])
        identity.write_binding({**binding, "role": None, "installed": [], "session": ctx.get("session")},
                               ctx["agent"])
        _fault("after-binding")
    except BaseException:
        tx.rollback()
        if workspace:
            write_exclude_block(workspace, [item["path"] for item in previous])
        identity.write_binding(binding, ctx["agent"])
        print("role: deactivation failed; the workspace and the binding were restored", file=sys.stderr)
        raise
    tx.commit()
    append_history(ctx["state_dir"], {
        "agent": ctx["agent"], "host": ctx["host"], "role": None,
        "previous_role": binding.get("role"), "project": binding.get("project"),
        "working_copy": binding.get("working_copy"), "valid_from": identity.now_iso(),
        "reason": "deactivate",
    })
    active = os.path.join(ctx["state_dir"], "active")
    if os.path.islink(active) or os.path.exists(active):
        os.remove(active)
    print(f"agent: {ctx['agent']}   role: (none)")
    return 0


def cmd_activate(ctx: dict, role: str, workspace: str, force: bool, project: str | None) -> int:
    if refuse_inside_session("bind a role"):
        return 1
    role_dir = layout.role_dir(role)
    if not os.path.isfile(os.path.join(role_dir, "charter.md")):
        print(f"role: no role '{role}' under {layout.roles_dir()}", file=sys.stderr)
        available = layout.list_roles()
        if available:
            print("available roles: " + ", ".join(available), file=sys.stderr)
        return 2
    # Everything from the first read of the binding to its write happens
    # under the agent lock: a concurrent activation, hook or rebind waits.
    with identity.agent_lock(ctx["agent"]):
        return _activate_locked(ctx, role, workspace, force, project)


def _activate_locked(ctx: dict, role: str, workspace: str, force: bool, project: str | None) -> int:
    role_dir = layout.role_dir(role)
    if not os.path.isfile(os.path.join(role_dir, "charter.md")):
        print(f"role: no role '{role}' under {layout.roles_dir()}", file=sys.stderr)
        available = layout.list_roles()
        if available:
            print("available roles: " + ", ".join(available), file=sys.stderr)
        return 2

    binding = identity.read_binding(ctx["agent"])
    previous = binding.get("installed", []) or []
    previous_workspace = binding.get("workspace") or workspace

    # 1. What is installed now, and has any of it been adapted?
    adapted = adapted_items(previous_workspace, previous)
    if adapted and not force:
        print("role: refusing — these copies were adapted in the workspace:", file=sys.stderr)
        for item in adapted:
            print(f"  {os.path.join(previous_workspace, item['path'])}", file=sys.stderr)
        print("\nThose edits exist only there. Promote them into identities/roles/<role>/\n"
              "with a pull request if they should outlive this workspace, or re-run with\n"
              "--force to stash and replace them.", file=sys.stderr)
        return 1

    # 1b. Build and validate the WHOLE plan before touching anything.
    plan: list[tuple[str, str, str]] = []
    skills_src = os.path.join(role_dir, "skills")
    if os.path.isdir(skills_src):
        for name in sorted(os.listdir(skills_src)):
            source = os.path.join(skills_src, name)
            if os.path.isdir(source):
                plan.append((source, os.path.join(".claude", "skills", name), "skill"))
    commands_src = os.path.join(role_dir, "commands")
    if os.path.isdir(commands_src):
        for name in sorted(os.listdir(commands_src)):
            if name.endswith(".md"):
                plan.append((os.path.join(commands_src, name),
                             os.path.join(".claude", "commands", name), "command"))

    ours = {item["path"] for item in previous} if previous_workspace == workspace else set()
    collisions = [rel for _s, rel, _k in plan
                  if os.path.exists(os.path.join(workspace, rel)) and rel not in ours]
    if collisions:
        print("role: refusing — these already exist in the workspace and are not ours to replace:",
              file=sys.stderr)
        for rel in collisions:
            print(f"  {os.path.join(workspace, rel)}", file=sys.stderr)
        print("\nA committed skill or command of the same name would be shadowed. Rename "
              "the role's copy. Nothing was changed.", file=sys.stderr)
        return 1

    stash_dir = ""
    if adapted and force:
        stash_dir = os.path.join(ctx["state_dir"], "stash", identity.now_iso().replace(":", ""))
        for item in adapted:
            target = os.path.join(previous_workspace, item["path"])
            destination = os.path.join(stash_dir, item["path"])
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if os.path.isdir(target):
                shutil.copytree(target, destination)
            else:
                shutil.copy2(target, destination)

    # The project bound here is the one the WORKSPACE belongs to (or the one
    # named explicitly). A previous binding's project is deliberately not
    # carried over: activating from the parent directory means no project
    # context, and saying so beats silently keeping a stale one.
    if not project and ctx.get("project_source") == "working-copy":
        project = ctx["project"]
    changed = binding.get("role") != role or binding.get("project") != project

    # 2–4 are one transaction: stage the new copies, move the previous ones
    # out (never a sweep, never a delete), swap the staged ones in by rename,
    # then bind — the binding is the commit point. Any failure before the
    # cleanup restores the workspace, both exclude blocks and the binding.
    for path in sweep_leftovers(workspace, ctx["state_dir"]):
        print(f"an interrupted run's backup moved to {path}", file=sys.stderr)
    tx = WorkspaceTransaction(workspace, previous_workspace, _txid())
    try:
        installed = tx.stage(plan)
        _fault("after-stage")
        tx.back_up(previous)
        _fault("after-backup")
        if previous_workspace != workspace:
            write_exclude_block(previous_workspace, [])
        tx.install()
        _fault("after-install")
        write_exclude_block(workspace, [item["path"] for item in installed])
        identity.write_binding({
            "role": role, "project": project, "working_copy": ctx["working_copy"],
            "workspace": workspace, "session": ctx.get("session"), "installed": installed,
        }, ctx["agent"])
        _fault("after-binding")
    except BaseException:
        tx.rollback()
        write_exclude_block(previous_workspace, [item["path"] for item in previous])
        if previous_workspace != workspace:
            write_exclude_block(workspace, [])
        if binding:
            identity.write_binding(binding, ctx["agent"])
        else:
            _remove(identity.binding_path(ctx["agent"]))
        print(f"role: activation of {role} failed; the workspace and the binding were restored",
              file=sys.stderr)
        raise
    tx.commit()
    if changed or not binding:
        append_history(ctx["state_dir"], {
            "agent": ctx["agent"], "host": ctx["host"], "role": role,
            "previous_role": binding.get("role"), "project": project,
            "working_copy": ctx["working_copy"], "valid_from": identity.now_iso(),
            "reason": "initial" if not binding.get("role") else "role-change",
        })
    active = os.path.join(ctx["state_dir"], "active")
    if os.path.islink(active) or os.path.exists(active):
        os.remove(active)
    os.symlink(role_dir, active)

    # 5. Tell the caller what to load. Tier 1 only.
    print(f"agent: {ctx['agent']}   role: {role}   host: {ctx['host']}   "
          f"project: {project or '(none)'}")
    if stash_dir:
        print(f"stashed adapted copies -> {stash_dir}")
    if installed:
        for item in installed:
            print(f"  installed {item['kind']:8} {os.path.join(workspace, item['path'])}")
    else:
        print("  (this role ships no skills or commands yet)")
    # 5. Where the role reaches the session: nothing to "load now". The
    #    launcher renders charter, brief and the shared sections into the
    #    system prompt; the project's remit and index arrive from the
    #    session-start hook, following the working copy.
    brief = os.path.join(role_dir, "brief.md")
    print(f"\nbound. The next launch (runtime/openrouter/launch) puts the charter"
          f"{' and brief' if os.path.isfile(brief) else ' (no brief yet)'} of {role}"
          " into the session's system prompt;")
    if project:
        print(f"the project's remit ({layout.PROJECT_ROLES_SUBDIR}/{role}.md) and index reach it "
              "from the session-start hook.")
    else:
        print("no project is bound: launch from inside a registered working copy for its remit.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Activate a role for the current agent.")
    ap.add_argument("command", nargs="?", help="activate | status | deactivate | list, or a role id")
    ap.add_argument("role", nargs="?", help="role id, e.g. flutter-dev")
    ap.add_argument("--status", action="store_true", help="alias for `status`")
    ap.add_argument("--force", action="store_true",
                    help="replace locally adapted copies, stashing them first")
    ap.add_argument("--project", default=None, help="logical project id to bind the role to")
    ap.add_argument("--workspace", default=None,
                    help="directory whose .claude/ receives skills (default: $CLAUDE_PROJECT_DIR or cwd)")
    # Accepted so a script that passes it keeps working; nothing is announced.
    ap.add_argument("--no-announce", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    workspace = os.path.abspath(args.workspace or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    ctx = identity.resolve_context(cwd=workspace)

    command, role = args.command, args.role
    if args.status or command in (None, "status"):
        return cmd_status(ctx)
    if command == "list":
        return cmd_list()
    if command == "deactivate":
        return cmd_deactivate(ctx)
    if command == "activate":
        if not role:
            ap.error("activate needs a role id")
    else:
        role, command = command, "activate"
    return cmd_activate(ctx, role, workspace, args.force, args.project)


if __name__ == "__main__":
    sys.exit(main())
