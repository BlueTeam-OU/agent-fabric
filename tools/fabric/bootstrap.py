#!/usr/bin/env python3
"""tools/fabric/bootstrap.py — make agent-fabric's workspace instructions
available to a Claude Code session launched from the parent projects/
directory, for THIS account. Ported from runtime/claude-code/bootstrap.sh
(ADR-040 §5), which is now its shim; tests/test_bootstrap_cli.py is the
parity oracle, tests/test_bootstrap_internals.py holds what it cannot see.

Writes, idempotently, and only machine-local files:
  <projects>/CLAUDE.md               3 lines; imports agent-fabric/CLAUDE.md
  <projects>/.claude/settings.json   hooks + status line pointing at agent-fabric
  (removes ~/.claude/commands/role.md if an earlier bootstrap installed it:
   /role is retired — a role is bound from the shell, bin/fabric-role)
  ~/.claude/agents/{code-*,code-review}.md
                                     the capability-class agent files, from runtime/claude-code/agents/,
                                     via install_agent_files.py (the review pin, merged for this login)
  ~/.claude/hooks/review-bash-guard.{py,sh}
                                     the review class's Bash fence and its shim; the code-review
                                     agent file looks here when the launch project has no .claude/ copy
  ~/.claude/settings.json            the fabric's user-scope keys (runtime/claude-code/user-settings.py):
                                     attribution commit "", pr "", sessionUrl false — the harness's
                                     Co-Authored-By/Generated-with reminder off at its source —
                                     showThinkingSummaries and verbose on, tui default, the
                                     memory-write check hook (PostToolUse), env DISABLE_AUTOUPDATER,
                                     permissions (the fabric's commands allowed, auto mode), autoMode
                                     from policies/auto-mode.json and the auto-mode wizard off;
                                     every other key kept
  ~/.claude/skills/subagent-dispatch/SKILL.md
  ~/.claude/skills/fabric-decisions/SKILL.md
  ~/.claude/skills/branch-hygiene/SKILL.md
  ~/.claude/skills/agent-jobs/SKILL.md
  ~/.claude/skills/gzcoord-send/SKILL.md, gzcoord-receive/SKILL.md
                                     the dispatch policy as a loadable skill, from policies/
  ~/.local/bin/<name>                every command a session runs, by name
                                     (runtime/claude-code/commands.json)
  <units>/agent-fabric-agentd.service
                                     the control agent (runtime/control/), enabled and started
                                     in this account's user manager when one is running
  <units>/gzcoord-relay.service      ONLY on the account whose workspace hosts the relay
                                     ($PROJECTS/.gzcoord/venv exists): the relay as a unit
  ~/.cache/agent-fabric/langid/venv/ the language detector (pycld2) for the control agent's
                                     script op (runtime/langid/), best effort
  (removes ~/.doppler, ~/.local/bin/doppler and ~/.config/agent-fabric/secrets-source:
   Doppler is retired, ADR-038)
  <state>/agents/<login>/store-trust-base.done
                                     ADR-042's migration, once: every store this account holds then
                                     (its own, its children's mirrors) trusts the head it holds
                                     (secret_store.py trust-base --store DIR)
  <state>/agents/<login>/episodic.db this account's GZCoord history, imported once through the
                                     relay as itself (episodic.py gzcoord-import --if-needed,
                                     agent-fabric ADR-041 rule 9), best effort
where <units> is $XDG_CONFIG_HOME/systemd/user, else ~/.config/systemd/user.

Nothing here names an agent: the hooks ask the OS who is running at
session start. Nothing here makes projects/ a git repository. A managed
project keeps its own CLAUDE.md and .claude/ for sessions launched inside
it. Re-running refreshes only what differs.

The projects directory defaults to the parent of this checkout — the
layout agent-fabric assumes is projects/agent-fabric beside the working
copies it manages.

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):

  argv         [--projects DIR] [--dry-run], in any order. Anything else:
               "bootstrap: unknown argument X" on stderr, nothing on
               stdout, exit 2. --projects naming no directory, or with no
               value: one line on stderr, nothing on stdout, exit 1.
  environment  HOME; CLAUDE_CONFIG_DIR (else ~/.claude for the agent
               files, the guard, the user settings and the skills; the
               trust goes to its .claude.json, else ~/.claude.json);
               XDG_CONFIG_HOME (the systemd user units); XDG_RUNTIME_DIR
               (the user manager's bus; set to /run/user/<uid> for the
               children when unset, outside a dry run);
               AGENT_FABRIC_LOCAL_BIN (else ~/.local/bin);
               AGENT_FABRIC_DEFER_AGENTD_RESTART (non-empty: a changed
               control-agent unit is not restarted, and the line says so);
               the collation locale (LC_ALL / LC_COLLATE / LANG), which
               orders the working copies as bash's glob did. Everything
               else is passed on to the children as it is.
  stdout       the header "agent-fabric bootstrap for agent <login> —
               projects: <dir>"; one line per thing written or current:
               "  +  path" (written; "(would write)" / "(would link)" in a
               dry run), "  =  path", "  -  path (removed: …)",
               "     (kept the previous file as …)", "  *  unit: state",
               "  !  …" for what could not be done and is not counted;
               the children's own lines (install_agent_files, user-settings,
               workspace_trust, langid/install.sh, retire-doppler); then
               "bootstrap: C written, S already current[, F NOT written
               (above)]." and "Launch from <dir>: cd "<dir>" && claude
               — the session starts as <login>."
  stderr       the refusals counted as NOT written ("  !  <link> is not a
               link this fabric made …", "  !  <link>: could not link",
               "  !  runtime/claude-code/commands.json unreadable …",
               "  !  <working copy>: <why> …"), the children's own, and the
               line a stopped run ends with ("bootstrap: …").
  exit         0 when the run reached its summary, NOT-written lines
               included; 2 a bad argument; 1 --projects names no
               directory, a file the run must write cannot be written
               (install's word: "bootstrap: install: …"), or the workspace
               settings are not a JSON object; 127 git missing, at the first
               write;
               install_agent_files' own non-zero status (nothing after the
               agent files ran); git's own status when a hooksPath cannot be
               set.
  writes       the list above, with mode 644 (the user settings and
               .claude.json keep their writers' modes); a person's version
               of a file it replaces, every time it differs from what the
               fabric last wrote there, under the first free
               <file>.before-agent-fabric[.N] with that file's own mode;
               the hash of each file written or found current in
               <state>/agents/<login>/fabric-written.json (and its .lock).
               Nothing under --dry-run but what the children's own dry runs
               leave (none).
  calls        this interpreter: runtime/identity.py,
               runtime/claude-code/user-settings.py <settings> [--dry-run],
               runtime/claude-code/retire-doppler.py [--dry-run],
               tools/fabric/episodic.py gzcoord-import --if-needed (not
               under --dry-run; 20 s);
               tools/fabric/install_agent_files.py
               [--dry-run]; bash runtime/langid/install.sh [--dry-run];
               git (through git.py): config --get / config core.hooksPath,
               rev-parse --is-inside-work-tree; systemctl --user
               daemon-reload | enable [--now] | restart | is-active; curl
               -sf -m 1 http://127.0.0.1:8765/status; ss -Hltnp 'sport =
               :8765'; pgrep -u <uid> -x claude-bridge. In-process:
               workingcopy.resolve, workspace_trust.main.
  relied on    new-agent's worker (runtime/provisioning/new-agent-worker.sh,
               step 7): exit status, the log's last lines on failure; the
               control agent's `upgrade fabric` (runtime/control/upgrade.mjs):
               exit status, the last line on failure, and the stdout line
               "restart left to the caller"; moveto's enter: exit status
               only, output discarded, 30 s.

The helpers under runtime/ run on this interpreter, the fleet's pinned
Python, as ADR-040 §5 rule 4 has it for bootstrap's port: the bash ran
them on the host's python3 and stopped with 127 before step 2 without
one. Only step 7's venv, the language detector's own environment, is
still made with the host's python3; without it that step says so and the
run carries on.

DELIBERATE DEPARTURES from the bash, each a defect the oracle pinned as the
bash behaved, fixed here with its case changed:
  1. A working copy whose .agent-fabric-project marker names no registered
     project ended the whole run at step 5, silently, exit 1 (workingcopy.py
     failed inside the pid pipeline under pipefail and set -e): every copy
     after it, the trust, the units, langid and Doppler were skipped. Now
     one line on stderr names the working copy and why, it is counted NOT
     written, and the run carries on.
  2. A relay port held by a process ss could not name (no pid in its
     answer, or no ss on the host) ended the run at step 6b, silently, exit
     1 (grep -o failed inside the holder pipeline): the pgrep fallback and
     the "pid unknown" line were never reached, the relay not even
     enabled. Now ss, then pgrep, then "unknown", as intended.
  3. User settings that are not JSON ended the run in the agent files with
     a traceback from runtime/mcp/websearch-locale/install.py (allow- and
     deny-websearch read the file first), before user-settings.py could
     refuse it. install.py now says one line and leaves the file alone
     (exit 0 for allow-websearch and remove, which have nothing to take
     out of a file the harness cannot read either; exit 1 for set and
     deny-websearch, which cannot write theirs). On any login but a
     language-culture one the run carries on to user-settings.py's own
     refusal, counted NOT written; on a language-culture login the
     installer's deny-websearch is that exit 1, and the run ends in the
     agent files, said in install.py's one line, not a traceback.
  4. put() re-made a .before-agent-fabric backup each time a fabric file
     carrying no "agent-fabric" marker changed (the guard, three of the
     skills), so the second change replaced the person's original with the
     fabric's own previous file. Now a person's version is kept every time
     it differs from what the fabric last wrote, never over another backup
     and never twice (tools/fabric/fabric_writes.py), as the installer
     does.
  5. The systemd units went to ~/.config/systemd/user whatever
     XDG_CONFIG_HOME said; `systemctl --user` reads $XDG_CONFIG_HOME/
     systemd/user when it is set. Now the units go there.
Unpinned, and smaller: no temporary directory (the merge is in memory);
commands.json unreadable, and workspace settings that are JSON but not an
object, are one line rather than a traceback; install_agent_files is run
by this interpreter rather than through its shim; workingcopy and
workspace_trust run in-process on this interpreter.

Left as they are (reported, not decided here): the exit is 0 when the
summary has NOT-written lines; the agent files, steps 4, 5b and 7 are not
in the counts, and step 5's lines are counted in a dry run; some refusals
go to stdout ("  !  langid", "  !  workspace trust", a relay held) and
others to stderr.
"""
from __future__ import annotations

import json
import locale
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
# The fabric is the one the shim was run from, as the bash found it from its
# own place: abspath keeps the path the shim gave, so a fabric whose tools/
# is a link elsewhere is still itself, not where the link points.
FABRIC_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
import git as gitcmd  # noqa: E402
import workingcopy  # noqa: E402
import workspace_trust  # noqa: E402
import fabric_writes  # noqa: E402

MARKER = b"agent-fabric"
HOOKS_REL = "policies/githooks"
UNIT = "agent-fabric-agentd"
RELAY_UNIT = "gzcoord-relay"
RELAY_STATUS = "http://127.0.0.1:8765/status"
JOURNAL_IMPORT_TIMEOUT = 20
# The marker of ADR-042's migration on this account, under its state.
STORE_BASE_MARKER = "store-trust-base.done"
# Ownership is by the hook path SHAPE (…/runtime/claude-code/hooks/…, and
# the GZCoord inbox entry), not by the current root: an entry written by an
# earlier bootstrap from another checkout (a shared path, before an account
# got its own clone) must be replaced, not kept beside the new one. The
# inbox has two shapes: bin/gzcoord-inbox, and the Node shim path that
# earlier bootstraps wrote and the shim's own callers still carry; both stay
# owned, or an installed hook on the old path would sit beside the new one
# and drain the inbox twice.
OWNED = ("/runtime/claude-code/hooks/", "/bin/gzcoord-inbox", "/communication/gzcoord/scripts/inbox.mjs")
SKILLS = (("subagent-dispatch", "policies/subagent-dispatch/SKILL.md"),
          ("fabric-decisions", "policies/fabric-decisions/SKILL.md"),
          ("branch-hygiene", "policies/branch-hygiene/SKILL.md"),
          ("agent-jobs", "policies/agent-jobs/SKILL.md"),
          ("gzcoord-send", "communication/gzcoord/skills/gzcoord-send/SKILL.md"),
          ("gzcoord-receive", "communication/gzcoord/skills/gzcoord-receive/SKILL.md"))


class Stop(Exception):
    """The run ends here: the message on stderr, the status as the exit."""

    def __init__(self, rc: int, message: str = "") -> None:
        super().__init__(message)
        self.rc, self.message = rc, message


def say(line: str) -> None:
    print(line, flush=True)


def warn(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def marked(path: str) -> bool:
    try:
        return MARKER in _read(path)
    except OSError:
        return False


def login() -> str:
    return pwd.getpwuid(os.geteuid()).pw_name


def run_quiet(argv: list[str]) -> int:
    """A host tool whose output nobody reads: its status, 127 when absent."""
    try:
        return subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode
    except OSError:
        return 127


def answer(argv: list[str]) -> str:
    """A host tool's stdout as a command substitution gives it (trailing
    newlines dropped), its stderr and status ignored; "" when absent."""
    try:
        r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    except OSError:
        return ""
    return r.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def merge_workspace_settings(template: dict, root: str, existing: object) -> dict:
    """The workspace settings: the template with the root substituted, over
    what the file already has. Only statusLine, env and hooks are taken
    from the template, so its _comment never reaches the file."""
    def sub(v: object) -> object:
        if isinstance(v, str):
            return v.replace("$AGENT_FABRIC_ROOT", root)
        if isinstance(v, list):
            return [sub(x) for x in v]
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        return v
    tpl = sub(template)
    # Merge over an existing workspace settings file: keep everything it has,
    # add or refresh only the entries agent-fabric owns (OWNED says by what).
    doc = existing or {}
    if not isinstance(doc, dict):
        raise ValueError("not a JSON object")
    doc["statusLine"] = tpl["statusLine"]
    # env: the template's keys are set, an existing file's other keys kept.
    if tpl.get("env"):
        env = doc.get("env") if isinstance(doc.get("env"), dict) else {}
        env.update(tpl["env"])
        doc["env"] = env
    hooks = doc.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("its hooks are not an object")
    for event, groups in tpl["hooks"].items():
        kept = [g for g in hooks.get(event, []) if not any(o in json.dumps(g) for o in OWNED)]
        hooks[event] = kept + groups
    return doc


def glob_order(names: list[str]) -> list[str]:
    """bash's `"$PROJECTS"/*/` order: each name with its slash, collated by
    the locale (in C, "alpha-wt/" before "alpha/")."""
    try:
        locale.setlocale(locale.LC_COLLATE, "")
    except locale.Error:
        pass
    return sorted(names, key=lambda n: locale.strxfrm(n + "/"))


def relay_holder(uid: int) -> str:
    """The pid holding the relay's port, or "" when nothing names it."""
    # ss is not in the host contract (iproute2 is absent on a minimal image): fall back to the process name.
    m = re.search(r"pid=([0-9]*)", answer(["ss", "-Hltnp", "sport = :8765"]))
    holder = m.group(1) if m else ""
    if not holder:
        holder = answer(["pgrep", "-u", str(uid), "-x", "claude-bridge"]).split("\n", 1)[0]
    return holder


class Bootstrap:
    def __init__(self, projects: str, dry_run: bool, root: str = FABRIC_ROOT) -> None:
        self.root, self.projects, self.dry_run = root, projects, dry_run
        self.home = os.environ.get("HOME") or os.path.expanduser("~")
        self.claude_home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(self.home, ".claude")
        self.units = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(self.home, ".config"),
                                  "systemd", "user")
        self.changed = self.same = self.failed = 0
        self.git_missing_said = False

    def src(self, rel: str) -> str:
        return os.path.join(self.root, rel)

    # --- writing ---------------------------------------------------------

    def put(self, dest: str, content: bytes) -> None:
        if os.path.isfile(dest) and _read(dest) == content:
            self.same += 1
            say(f"  =  {dest}")
            if not self.dry_run:
                fabric_writes.record(dest, content)
            return
        if self.dry_run:
            say(f"  +  {dest} (would write)")
            return
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # A person's version is kept, every time it differs from what the
            # fabric last wrote, under a name of its own (fabric_writes says
            # why each simpler rule lost a file).
            backup = fabric_writes.keep_person_version(dest)
            if backup:
                say(f"     (kept the previous file as {backup})")
            # install(1) replaced the destination rather than writing
            # through it; a rename does the same, and never leaves a
            # half-written file for a session starting at that moment.
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), prefix=".bootstrap-")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(content)
                os.chmod(tmp, 0o644)
                os.replace(tmp, dest)
            except BaseException:
                os.unlink(tmp)
                raise
        except OSError as e:
            raise Stop(1, f"bootstrap: install: cannot write {dest}: {e.strerror or e}") from None
        fabric_writes.record(dest, content)
        self.changed += 1
        say(f"  +  {dest}")

    def put_file(self, dest: str, rel: str) -> None:
        try:
            content = _read(self.src(rel))
        except OSError as e:
            raise Stop(1, f"bootstrap: install: cannot read {self.src(rel)}: {e.strerror or e}") from None
        self.put(dest, content)

    # --- the children ----------------------------------------------------

    def python3(self, script: str, *args: str, capture: bool = False) -> tuple[int, str]:
        """A helper under runtime/, on this interpreter, the fleet's pin."""
        try:
            r = subprocess.run([sys.executable, self.src(script), *args], check=False,
                               stdout=subprocess.PIPE if capture else None)
        except OSError:
            return 127, ""
        out = r.stdout.decode("utf-8", "surrogateescape").rstrip("\n") if capture else ""
        return r.returncode, out

    def identity(self) -> str:
        # A command substitution: whatever it printed, failed or not.
        return self.python3("runtime/identity.py", capture=True)[1]

    def git_get(self, repo: str, key: str) -> str | None:
        try:
            r = gitcmd.run(repo, "config", "--get", key, check=False)
        except gitcmd.GitError as e:
            if e.reason == "git is not installed" and not self.git_missing_said:
                warn("bootstrap: git: command not found")
                self.git_missing_said = True
            return None
        return r.stdout.strip() if r.returncode == 0 else None

    def git_set(self, repo: str, key: str, value: str) -> None:
        try:
            gitcmd.run(repo, "config", key, value)
        except gitcmd.GitError as e:
            if e.reason == "git is not installed":
                raise Stop(127, "bootstrap: git: command not found") from None
            raise Stop(e.code or 1, f"bootstrap: {repo}: {e}") from None

    def common_dir(self, path: str) -> str | None:
        """The repository a work tree belongs to: a linked worktree shares
        its main checkout's, and with it the config core.hooksPath lives in."""
        try:
            r = gitcmd.run(path, "rev-parse", "--git-common-dir", check=False)
        except gitcmd.GitError:
            return None
        if r.returncode != 0 or not r.stdout.strip():
            return None
        return os.path.realpath(os.path.join(path, r.stdout.strip()))

    def is_work_tree(self, path: str) -> bool:
        # git's own answer, not a test for a .git DIRECTORY: a linked worktree
        # carries a .git file and is a working copy like any other.
        try:
            r = gitcmd.run(path, "rev-parse", "--is-inside-work-tree", check=False)
        except gitcmd.GitError:
            return False
        return r.returncode == 0 and r.stdout.strip() == "true"

    # --- the steps -------------------------------------------------------

    def run(self) -> int:
        agent = self.identity()
        say(f"agent-fabric bootstrap for agent {agent} — projects: {self.projects}")
        # 1. The workspace CLAUDE.md: three lines, an import, no instructions of its own.
        self.put_file(os.path.join(self.projects, "CLAUDE.md"), "runtime/claude-code/workspace/CLAUDE.md")
        self.workspace_settings()
        self.retire_role_command()
        self.agent_files()
        # The review class's Bash fence rides with its agent file: the agent runs
        # unisolated in the session's clone, and a review dispatched from
        # projects/ (no .claude/ of its own) found no guard and lost Bash entirely
        # (docs/live-checks/2026-09-13-openrouter-routing.md).
        # The shim and its module, a pair: the shim finds the module beside itself.
        self.put_file(os.path.join(self.claude_home, "hooks", "review-bash-guard.py"),
                      "runtime/claude-code/hooks/review-bash-guard.py")
        self.put_file(os.path.join(self.claude_home, "hooks", "review-bash-guard.sh"),
                      "runtime/claude-code/hooks/review-bash-guard.sh")
        self.link_commands()
        self.user_settings()
        # The dispatch policy is a skill the project CLAUDE.md files tell a session
        # to load (`subagent-dispatch`); user-scope, so no project needs a copy.
        # Talking to other agents is two procedures, each a skill: composing and
        # sending a message, and receiving one (the watch, and what a delivery is).
        for name, rel in SKILLS:
            self.put_file(os.path.join(self.claude_home, "skills", name, "SKILL.md"), rel)
        self.checkout_hooks()
        trusted = self.working_copy_hooks()
        self.trust(trusted)
        self.control_agent()
        self.relay()
        self.langid()
        self.retire_doppler()
        self.journal_import()
        self.store_trust_base()
        if self.failed:
            say(f"bootstrap: {self.changed} written, {self.same} already current, {self.failed} NOT written (above).")
        else:
            say(f"bootstrap: {self.changed} written, {self.same} already current.")
        say(f"Launch from {self.projects}: cd \"{self.projects}\" && claude   — the session starts as {agent}.")
        return 0

    def workspace_settings(self) -> None:
        # 2. The workspace settings: hooks and status line, with the root substituted.
        dest = os.path.join(self.projects, ".claude", "settings.json")
        try:
            with open(self.src("runtime/claude-code/workspace/settings.json"), encoding="utf-8") as f:
                template = json.load(f)
        except (OSError, ValueError) as e:
            raise Stop(1, f"bootstrap: the workspace settings template is unreadable: {e}") from None
        existing: object = {}
        if os.path.exists(dest):
            try:
                with open(dest, encoding="utf-8") as f:
                    existing = json.load(f)
            except ValueError:
                existing = {}
            except OSError as e:
                raise Stop(1, f"bootstrap: {dest}: {e.strerror or e}; the workspace settings are not written") from None
        try:
            doc = merge_workspace_settings(template, self.root, existing)
        except ValueError as e:
            raise Stop(1, f"bootstrap: {dest}: {e}; the workspace settings are not written") from None
        self.put(dest, (json.dumps(doc, indent=2) + "\n").encode())

    def retire_role_command(self) -> None:
        # 3. The /role command is retired (owner, 2026-09-15): a role is bound from
        #    a login shell with bin/fabric-role and reaches the session in its
        #    system prompt at launch; nothing inside a session changes it. An
        #    earlier bootstrap installed ~/.claude/commands/role.md — remove OUR
        #    copy (it names agent-fabric, the test put() uses), never a file the
        #    human wrote; a .before-agent-fabric sibling is theirs and stays.
        retired = os.path.join(self.claude_home, "commands", "role.md")
        if not (os.path.isfile(retired) and marked(retired)):
            return
        if self.dry_run:
            say(f"  -  {retired} (would remove: /role is retired, use bin/fabric-role)")
            return
        try:
            os.remove(retired)
        except FileNotFoundError:
            pass
        except OSError as e:
            raise Stop(1, f"bootstrap: rm: cannot remove {retired}: {e.strerror or e}") from None
        self.changed += 1
        say(f"  -  {retired} (removed: /role is retired, use bin/fabric-role)")

    def agent_files(self) -> None:
        # The capability-class agent files, with the review pin applied for this
        # account: install_agent_files.py (bin/fabric-model re-runs it when the
        # account's local layer changes the pin).
        argv = [sys.executable, "-I", self.src("tools/fabric/install_agent_files.py")]
        if self.dry_run:
            argv.append("--dry-run")
        rc = subprocess.run(argv, check=False).returncode
        if rc != 0:
            raise Stop(rc)

    def link_commands(self) -> None:
        # Every command a session is told to run, on PATH under its own name
        # (runtime/claude-code/commands.json): a skill says `gzcoord-send <file>`,
        # never a path through `$AGENT_FABRIC_ROOT`, because the harness asks before any
        # command carrying a shell expansion (the owner, 2026-09-26). A link this
        # fabric made — to this checkout or another one's same path — is
        # refreshed; anything else at that name is the account's and is refused,
        # never replaced.
        local_bin = os.environ.get("AGENT_FABRIC_LOCAL_BIN") or os.path.join(self.home, ".local", "bin")
        # Read first, then loop: a list that cannot be read inside a process
        # substitution linked nothing and reported success (review of #42).
        try:
            with open(self.src("runtime/claude-code/commands.json"), encoding="utf-8") as f:
                commands = list(json.load(f)["commands"].items())
            if not all(isinstance(v, str) for _, v in commands):
                raise ValueError("a target is not a string")
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            warn("  !  runtime/claude-code/commands.json unreadable — no command linked")
            self.failed += 1
            commands = []
        for name, rel in commands:
            if not name:
                continue
            target, link = self.src(rel), os.path.join(local_bin, name)
            current = os.readlink(link) if os.path.islink(link) else None
            if current == target:
                say(f"  =  {link}")
                self.same += 1
                continue
            if os.path.lexists(link) and not (current is not None and current.endswith("/" + rel)):
                warn(f"  !  {link} is not a link this fabric made — left alone; {name} is not on PATH")
                self.failed += 1
                continue
            if self.dry_run:
                say(f"  +  {link} -> {target} (would link)")
                continue
            try:
                os.makedirs(local_bin, exist_ok=True)
                tmp = os.path.join(local_bin, f".{name}.bootstrap-link")
                if os.path.lexists(tmp):
                    os.unlink(tmp)
                os.symlink(target, tmp)
                os.replace(tmp, link)
            except OSError:
                warn(f"  !  {link}: could not link")
                self.failed += 1
                continue
            say(f"  +  {link} -> {target}")
            self.changed += 1

    def user_settings(self) -> None:
        # Linked BEFORE the settings are written: an allow rule is granted only for
        # a name whose link is the fabric's script (user-settings.py).
        # The login's user settings carry what the fabric wants in every session
        # of the account whatever directory it launches from: the harness's
        # attribution reminder — a system reminder asking for a Co-Authored-By
        # trailer and a "Generated with" footer, sent on the first turn and after
        # every model switch, outside any launch prompt — switched off where it
        # is built (an empty attribution text hides it, and the harness then says
        # the opposite; docs/live-checks/2026-09-18-attribution-reminder-off.md;
        # the guard policies/ban_generated_by_attribution.sh stays as the fence),
        # and the thinking summaries and verbose tool output the operator reads a
        # session by. The writer's docstring has each key's reason.
        # The dry run reports the refusal the same way and goes on, so both
        # paths reach the same summary line.
        path = os.path.join(self.claude_home, "settings.json")
        if self.dry_run:
            rc, _ = self.python3("runtime/claude-code/user-settings.py", path, "--dry-run")
            if rc != 0:
                self.failed += 1
            return
        rc, out = self.python3("runtime/claude-code/user-settings.py", path, capture=True)
        if rc != 0:
            # The writer said why on stderr; an unreadable settings file is
            # the account's to fix, and the run must not report it settled.
            self.failed += 1
            return
        say(out)
        if out.startswith("  +  "):
            self.changed += 1
        else:
            self.same += 1

    def checkout_hooks(self) -> None:
        # 4. The agent-fabric checkout this runs from enforces its own git
        #    discipline at commit time (policies/githooks/commit-msg). A repo
        #    config, so it is per checkout and never committed.
        if self.git_get(self.root, "core.hooksPath") != HOOKS_REL:
            if not self.dry_run:
                self.git_set(self.root, "core.hooksPath", HOOKS_REL)
            say(f"  +  {self.root}: core.hooksPath = {HOOKS_REL}")
        else:
            say(f"  =  {self.root}: core.hooksPath = {HOOKS_REL}")

    def working_copy_hooks(self) -> list[str]:
        # 5. The same hooks in every registered working copy beside this checkout:
        #    they carry the attribution ban and the .agent-fabric/ fence (only a
        #    session holding fabric-coordinator commits under .agent-fabric/, and
        #    the commit records the role). A repo config per working copy, never
        #    committed; a directory that is not a registered project is left alone.
        hooks_abs = os.path.join(self.root, HOOKS_REL)
        own_common = self.common_dir(self.root)
        trusted = [self.projects, self.root]
        try:
            names = [n for n in os.listdir(self.projects)
                     if not n.startswith(".") and os.path.isdir(os.path.join(self.projects, n))]
        except OSError:
            names = []
        for n in glob_order(names):
            wc = os.path.join(self.projects, n)
            if wc == self.root or not self.is_work_tree(wc):
                continue
            try:
                registry = workingcopy.load_registry(self.src("projects/registry.json"))
                pid = workingcopy.resolve(wc, registry).get("project") or ""
            except SystemExit as e:
                warn(f"  !  {wc}: {e.code}; its hooksPath and trust left as they are")
                self.failed += 1
                continue
            except Exception as e:  # noqa: BLE001 — any failure is this copy's, said, and the run goes on
                warn(f"  !  {wc}: not resolved ({type(e).__name__}: {e}); its hooksPath and trust left as they are")
                self.failed += 1
                continue
            if not pid:
                continue
            trusted.append(wc)
            # A linked worktree of this checkout (a contributor's branch, as
            # python-dev's remit has it) shares the checkout's config: an
            # absolute hooksPath written there would replace step 4's relative
            # one, and the two would flip on every run (review of #86). It is
            # trusted, and its hooks are the checkout's.
            if own_common is not None and self.common_dir(wc) == own_common:
                continue
            if self.git_get(wc, "core.hooksPath") != hooks_abs:
                if not self.dry_run:
                    self.git_set(wc, "core.hooksPath", hooks_abs)
                say(f"  +  {wc} ({pid}): core.hooksPath = {hooks_abs}")
                self.changed += 1
            else:
                say(f"  =  {wc} ({pid}): core.hooksPath")
                self.same += 1
        return trusted

    def trust(self, trusted: list[str]) -> None:
        # 5b. Those same folders trusted in Claude Code — the workspace, this
        #     checkout and each registered working copy, which the fabric cloned
        #     from the registry's remotes — so a new account's first session asks
        #     no trust question (tools/fabric/workspace_trust.py says why).
        try:
            rc = workspace_trust.main((["--dry-run"] if self.dry_run else []) + trusted)
        except Exception as e:  # noqa: BLE001 — the trust is best effort, as it was
            warn(f"workspace_trust: {type(e).__name__}: {e}; nothing written")
            rc = 1
        sys.stdout.flush()
        if rc != 0:
            say("  !  workspace trust not recorded (above); a first session asks for it")

    def user_manager(self) -> bool:
        os.environ["XDG_RUNTIME_DIR"] = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.geteuid()}"
        bus = os.path.join(os.environ["XDG_RUNTIME_DIR"], "bus")
        try:
            is_socket = stat.S_ISSOCK(os.stat(bus).st_mode)
        except OSError:
            is_socket = False
        return (is_socket and shutil.which("systemctl") is not None
                and run_quiet(["systemctl", "--user", "daemon-reload"]) == 0)

    def control_agent(self) -> None:
        # 6. The control agent: a systemd user unit that answers the coordinator's
        #    fabric-ctl over the relay (runtime/control/). Enabled and started in
        #    this account's user manager — the one that exists because the account
        #    lingers (persist-accounts.sh); with no manager (a bare `sudo -u`, a
        #    scratch HOME in a test) the unit is only installed, and starts at the
        #    next login. Restarted only when the unit file itself changed: a pull
        #    that changes the daemon's code is the daemon's own business (it exits,
        #    Restart= brings it back).
        before = self.changed
        self.put_file(os.path.join(self.units, f"{UNIT}.service"), f"runtime/control/{UNIT}.service")
        if self.dry_run:
            return
        if not self.user_manager():
            say(f"  !  {UNIT}: installed, not started — no user manager at {os.environ['XDG_RUNTIME_DIR']}/bus "
                f"(loginctl enable-linger {login()}, or the next login starts it)")
            return
        run_quiet(["systemctl", "--user", "enable", "--now", UNIT])
        # Run BY the daemon (`fabric-ctl upgrade fabric`), a restart here would
        # kill the process waiting on this script: it restarts itself after
        # replying instead (runtime/control/upgrade.mjs).
        if self.changed > before:
            if os.environ.get("AGENT_FABRIC_DEFER_AGENTD_RESTART"):
                say(f"  *  {UNIT}: unit changed; restart left to the caller")
            else:
                run_quiet(["systemctl", "--user", "restart", UNIT])
        say(f"  *  {UNIT}: {answer(['systemctl', '--user', 'is-active', UNIT])} (systemctl --user status {UNIT})")

    def relay(self) -> None:
        # 6b. The GZCoord relay as a user unit — ONLY on the account that hosts
        #     it: the one whose workspace runtime dir ($PROJECTS/.gzcoord/) holds
        #     the relay's venv. Every other account is a client and gets nothing
        #     here (BRIDGE-RELAY-SETUP.md §Hosting). Same mechanics as the control
        #     agent above; the unit's own ConditionPathExists is the second fence.
        #     The unit hard-codes %h/projects/.gzcoord (static, like the control
        #     agent's), so it is installed only where $PROJECTS is that path.
        if not os.access(os.path.join(self.projects, ".gzcoord", "venv", "bin", "claude-bridge"), os.X_OK):
            return
        if self.projects != os.path.realpath(os.path.join(self.home, "projects")):
            say(f"  !  {RELAY_UNIT}: not installed — the unit expects the workspace at $HOME/projects, "
                f"this one is {self.projects}")
            return
        before = self.changed
        self.put_file(os.path.join(self.units, f"{RELAY_UNIT}.service"),
                      f"communication/gzcoord/runtime/{RELAY_UNIT}.service")
        if self.dry_run:
            return
        if not self.user_manager():
            say(f"  !  {RELAY_UNIT}: installed, not started — no user manager at {os.environ['XDG_RUNTIME_DIR']}/bus")
            return
        # A relay that is not the unit's — hand-started, or an older session's
        # detached spawn — holds the port: starting the unit against it would
        # crash-loop every three seconds while is-active said "active". Enable
        # for the next boot, say who holds the port, and leave the start to a
        # person who has stopped it.
        state = answer(["systemctl", "--user", "is-active", RELAY_UNIT])
        if state != "active" and run_quiet(["curl", "-sf", "-m", "1", RELAY_STATUS]) == 0:
            holder = relay_holder(os.geteuid()) or "unknown"
            run_quiet(["systemctl", "--user", "enable", RELAY_UNIT])
            if state == "activating":
                say(f"  !  {RELAY_UNIT}: RESTARTING against a relay outside the unit that holds 127.0.0.1:8765 "
                    f"(pid {holder}); stop that relay and the unit takes the port (systemctl --user status {RELAY_UNIT})")
            else:
                say(f"  !  {RELAY_UNIT}: enabled, NOT started — a relay outside the unit holds 127.0.0.1:8765 "
                    f"(pid {holder}); stop it, then: systemctl --user start {RELAY_UNIT}")
            return
        run_quiet(["systemctl", "--user", "enable", "--now", RELAY_UNIT])
        if self.changed > before:
            run_quiet(["systemctl", "--user", "restart", RELAY_UNIT])
        say(f"  *  {RELAY_UNIT} (this workspace hosts the relay): {answer(['systemctl', '--user', 'is-active', RELAY_UNIT])}")

    def langid(self) -> None:
        # 7. The language detector for the control agent's `script` op
        #    (runtime/langid/, pycld2 in its own venv), best effort — offline or
        #    without a C++ compiler, the op reports `language` as unavailable and
        #    nothing else changes.
        argv = ["bash", self.src("runtime/langid/install.sh")] + (["--dry-run"] if self.dry_run else [])
        try:
            rc = subprocess.run(argv, check=False).returncode
        except OSError:
            rc = 127
        if rc != 0 and not self.dry_run:
            say("  !  langid: not installed (above); fabric-ctl <login> script reports language unavailable until it is")

    def retire_doppler(self) -> None:
        # 8. Doppler, retired (ADR-038): what it left in this account goes on the
        #    upgrade that brings the fabric without it (retire-doppler.py).
        rc, _ = self.python3("runtime/claude-code/retire-doppler.py", *(["--dry-run"] if self.dry_run else []))
        if rc != 0:
            self.failed += 1

    def journal_import(self) -> None:
        # 9. This account's GZCoord history into its episodic journal, once
        #    (ADR-041 rule 9): read through the relay as itself, with its own
        #    token; --if-needed makes every later run a local no-op. Best
        #    effort, like langid: no token yet (a new account), a relay down,
        #    a journal that refuses — one line, and the next bootstrap tries
        #    again, since only a run that read every channel to its end marks
        #    it done. 20 s: the whole fleet's history took 1.84 s, and moveto's
        #    enter gives all of bootstrap 30 s.
        if self.dry_run:
            say("  +  episodic journal: would import this account's GZCoord history, once")
            return
        argv = [sys.executable, self.src("tools/fabric/episodic.py"), "gzcoord-import", "--if-needed"]
        try:
            rc = subprocess.run(argv, check=False, timeout=JOURNAL_IMPORT_TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            say(f"  !  episodic journal: the import did not finish in {JOURNAL_IMPORT_TIMEOUT} s; "
                "the next bootstrap tries again")
            return
        except OSError:
            rc = 127
        if rc != 0:
            say("  !  episodic journal: not imported (above); the next bootstrap tries again")


    def stores(self) -> list[str]:
        """This account's own store and its mirrors of its children's, as
        tools/fabric/secret_store.py places them; only those that exist."""
        share = os.path.join(self.home, ".local", "share", "agent-fabric")
        own = os.environ.get("AGENT_FABRIC_SECRET_STORE") or os.path.join(share, "secrets")
        children = os.path.join(share, "children")
        try:
            mirrors = sorted(os.path.join(children, n) for n in os.listdir(children))
        except OSError:
            mirrors = []
        return [d for d in [own, *mirrors] if os.path.isdir(os.path.join(d, ".git"))]

    def store_trust_base(self) -> None:
        # 10. ADR-042's migration, once per account: every store that exists
        #     now takes the head it holds as its trusted base, the history it
        #     has already applied. ONCE, by a marker, and never again by
        #     itself: a mirror deleted and re-made later would otherwise be
        #     trusted whole from its remote. Such a mirror is rebuilt by
        #     store-enroll's seed-child only from its remote's history
        #     verified against the writers on main. A child enrolled before
        #     this migration has unsigned history on its remote, so its
        #     deleted mirror cannot be rebuilt by any command: the rebuild
        #     refuses, and trust-base needs a mirror to act on. That repair is
        #     the owner's, by hand, until an owner-run rebuild exists (#94's
        #     review, round 2). A store
        #     born after the migration gets its base at first contact
        #     (seed-child, take-bundle). One that has a base is left alone.
        marker = os.path.join(fabric_writes.state_dir(), STORE_BASE_MARKER)
        if os.path.exists(marker):
            return
        todo = [d for d in self.stores() if not self.git_get(d, "agent-fabric.trustedbase")]
        if self.dry_run:
            for d in todo:
                say(f"  +  secret store {d}: would trust the head it holds as its base (ADR-042), once")
            return
        failed = 0
        for d in todo:
            rc, _ = self.python3("tools/fabric/secret_store.py", "trust-base", "--store", d)
            if rc != 0:
                failed += 1
                say(f"  !  secret store {d}: no trusted base set (above); the next bootstrap tries again")
            else:
                say(f"  +  secret store {d}: its head is its trusted base (ADR-042)")
        if failed:
            self.failed += 1
            return
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(f"{len(todo)} store(s) based\n")


def parse(argv: list[str]) -> tuple[str, bool]:
    projects, dry_run = os.path.dirname(FABRIC_ROOT), False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--projects":
            if i + 1 >= len(argv):
                raise Stop(1, "bootstrap: --projects needs a directory")
            projects = absolute_dir(argv[i + 1])
            i += 2
        elif a == "--dry-run":
            dry_run, i = True, i + 1
        else:
            raise Stop(2, f"bootstrap: unknown argument {a}")
    return projects, dry_run


def absolute_dir(d: str) -> str:
    """`cd DIR && pwd`: relative to the shell's own idea of where it is
    ($PWD, which keeps a symlinked path), the path made absolute, not resolved."""
    base = os.getcwd()
    pwd_env = os.environ.get("PWD")
    try:
        if pwd_env and os.path.isabs(pwd_env) and os.path.samefile(pwd_env, base):
            base = pwd_env
    except OSError:
        pass
    path = os.path.normpath(os.path.join(base, d))
    if not os.path.isdir(path):
        raise Stop(1, f"bootstrap: --projects {d}: No such directory")
    return path


def main(argv: list[str]) -> int:
    try:
        projects, dry_run = parse(argv)
        return Bootstrap(projects, dry_run).run()
    except Stop as s:
        sys.stdout.flush()
        if s.message:
            warn(s.message)
        return s.rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
