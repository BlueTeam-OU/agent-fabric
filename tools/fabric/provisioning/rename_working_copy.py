#!/usr/bin/env python3
"""tools/fabric/provisioning/rename_working_copy.py — move an account's
working copy and carry its Claude Code history with it. Host tooling, run
by the coordinator with sudo. Ported from runtime/provisioning/
rename-working-copy.sh (agent-fabric ADR-040, off shell); the history half
is runtime/provisioning/rename_history.py, unchanged.

    rename_working_copy.py <login> <old-name> <new-name> [--dry-run]

Claude Code keys a project's transcripts, memory, settings and prompt history
by the clone's ABSOLUTE PATH. Renaming the directory alone strands all of it
under the old key; this applies the same rename to every place that holds the
path, as the account:
  ~/projects/<old>                      -> ~/projects/<new>   (mv; a tree with
                                           uncommitted changes to tracked
                                           paths is refused — untracked
                                           files and the branch move along)
  ~/.claude/projects/-home-<login>-projects-<old>/
                                        -> …-<new>/  (transcripts, memory),
                                           and the "cwd" field of every
                                           transcript record — that field
                                           only; recorded tool output keeps
                                           the path it saw
  ~/.claude.json  projects["<old path>"] -> projects["<new path>"]
  ~/.claude/history.jsonl "project"      -> the new path
  the agent's binding (working_copy, workspace)
Nothing else holds the path: hooks resolve the fabric from $CLAUDE_PROJECT_DIR,
core.hooksPath is absolute to the fabric checkout, secrets come from the
environment, and a GZCoord address is the login.

Refused when the account has a live `claude` process: a session mid-flight
would keep writing under the old key. Idempotent: a step already done is
skipped. It stops where it fails (review, 2026-09-16): a `mv` that did not
happen, or a prune that failed, ends the run before any history is rewritten
— the history step runs only once the tree is at its new path, so the two
never disagree about where the clone is.

CONTRACT, frozen from the shell
  env     SUDO (sudo; a test puts a fake here, split into words)
  stderr  every line, `rename: <what>`; a usage is the shell's first lines
  exit    0 done (or already done); 1 refused or a step failed; 2 usage or
          no such login
  how     every command is run as an argument list with the platform's own
          tools found on PATH (getent, pgrep, git, mv, test, sudo): a test
          fakes them there. As the account: `sudo -u <login> -H env -i
          HOME=<home> PATH=/usr/local/bin:/usr/bin:/bin bash -c 'cd "$HOME"
          && exec "$@"' -- <command>` — the cd happens as the account, whose
          home the coordinator's cwd cannot enter — or the bare command when
          the caller is the account.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from collections.abc import Mapping

HERE = os.path.dirname(os.path.realpath(__file__))
CALL_TIMEOUT_S = 600            # a git status or a mv of a clone; none waits on a person
USAGE = """# runtime/provisioning/rename-working-copy.sh — move an account's working
# copy and carry its Claude Code history with it. Host tooling, run by the
# coordinator with sudo.
#
#   rename-working-copy.sh <login> <old-name> <new-name> [--dry-run]"""


class Stop(Exception):
    """The run ends here, with this exit status."""
    def __init__(self, code: int):
        self.code = code


def _say(text: str) -> None:
    print(f"rename: {text}", file=sys.stderr, flush=True)


def _die(text: str) -> None:
    _say(text)
    raise Stop(1)


def _run(argv: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(argv, stdout=subprocess.PIPE if capture else None, text=True, timeout=CALL_TIMEOUT_S)


class Renamer:
    def __init__(self, login: str, old: str, new: str, dry: bool, environ: Mapping[str, str]):
        self.login, self.old, self.new, self.dry = login, old, new, dry
        self.sudo = shlex.split(environ.get("SUDO") or "sudo")

    def as_account(self, argv: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
        if self.login == _own_login():
            return _run(argv, capture=capture)
        return _run([*self.sudo, "-u", self.login, "-H", "env", "-i", f"HOME={self.home}",
                     "PATH=/usr/local/bin:/usr/bin:/bin", "bash", "-c", 'cd "$HOME" && exec "$@"', "--", *argv],
                    capture=capture)

    def must(self, argv: list[str]) -> None:
        if self.as_account(argv).returncode != 0:
            _die(f"step failed: as {' '.join(argv)} — nothing after it ran; the tree and the history are as they were")

    def is_dir(self, path: str) -> bool:
        return _run([*self.sudo, "test", "-d", path]).returncode == 0

    def run(self) -> int:
        got = _run(["getent", "passwd", self.login], capture=True)
        fields = (got.stdout or "").strip().split("\n")[0].split(":")
        self.home = fields[5] if len(fields) > 5 else ""
        if not self.home:
            print(f"no such login: {self.login}", file=sys.stderr)
            return 2
        # The account's own copy of the state layer (runtime/identity.py): the coordinator's checkout is not readable to it.
        identity = os.path.join(self.home, "projects", "agent-fabric", "runtime", "identity.py")
        if not os.path.isfile(identity):
            identity = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "runtime", "identity.py")
        history = os.path.join(os.path.dirname(identity), "..", "runtime", "provisioning", "rename_history.py")
        if not os.path.isfile(history):
            history = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "runtime", "provisioning", "rename_history.py")
        if _run(["pgrep", "-u", self.login, "-x", "claude"], capture=True).returncode == 0:
            _die(f"{self.login} has a live claude session; not touching it")
        oldp = os.path.join(self.home, "projects", self.old)
        newp = os.path.join(self.home, "projects", self.new)
        if not self.is_dir(oldp):
            if self.is_dir(newp):
                _say(f"{self.login}: already at {newp}")
            else:
                _die(f"{self.login}: no {oldp}")
        if self.is_dir(oldp):
            if self.is_dir(newp):
                _die(f"{self.login}: both {oldp} and {newp} exist; nothing moved — resolve by hand")
            # A rename loses nothing that is on disk — untracked files and the
            # checked-out branch move with the directory — so only uncommitted
            # changes to TRACKED paths are a reason to stop: they are work in a
            # state the account expects to find exactly where it left it.
            status = self.as_account(["git", "-C", oldp, "status", "--porcelain", "--untracked-files=no"], capture=True)
            if status.returncode != 0:
                _die(f"{self.login}: git status failed in {oldp} (not a repository, or not readable as the account); nothing moved")
            dirty = sum(1 for ln in (status.stdout or "").split("\n") if ln)
            branch = (self.as_account(["git", "-C", oldp, "branch", "--show-current"], capture=True).stdout or "").rstrip("\n")
            if dirty:
                _die(f"{self.login}: {oldp} ('{branch}') has {dirty} uncommitted change(s) to tracked paths; refusing to move a tree mid-work")
            if branch != "main":
                _say(f"{self.login}: on '{branch}' (committed); moving it as is")
            if self.dry:
                _say(f"would: mv {oldp} {newp}")
            else:
                self.must(["mv", oldp, newp])
                self.must(["git", "-C", newp, "worktree", "prune"])
                _say(f"{self.login}: moved to {newp}")
        # The history follows the tree, and only a tree that is where the new key
        # says: a dry run reports; a real run past this line has newp in place.
        if not self.dry and not self.is_dir(newp):
            _die(f"{self.login}: {newp} is not there after the move; history left under its old key")
        self.must(["python3", history, self.home, self.login, oldp, newp, "1" if self.dry else "0", identity])
        return 0


def _own_login() -> str:
    return subprocess.run(["id", "-un"], stdout=subprocess.PIPE, text=True, timeout=30).stdout.strip()


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    login, old, new = (args + ["", "", ""])[:3]
    dry = len(args) > 3 and args[3] == "--dry-run"
    if not (login and old and new):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        return Renamer(login, old, new, dry, os.environ if environ is None else environ).run()
    except Stop as stop:
        return stop.code
    except subprocess.TimeoutExpired as e:
        _say(f"{' '.join(map(str, e.cmd))} did not finish in {CALL_TIMEOUT_S} s; stopped")
        return 1
    except OSError as e:
        _say(f"{e.strerror or e}: {e.filename or ''}".rstrip(": "))
        return 1


if __name__ == "__main__":
    sys.exit(main())
