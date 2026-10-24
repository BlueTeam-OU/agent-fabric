"""review_check: one argv from the reviewer, run in a proved read-only sandbox over the head worktree (agent-fabric ADR-065 §2 B, §5 rule 3).

The argv is code from the pull request, so the fence is the kernel's: bubblewrap with every namespace unshared, no network, the
filesystem bound read-only from an allowlist (the system trees, the toolchain, the head worktree and what git reads of the clone's git
directory to show history: objects, refs, HEADs), a
tmpfs over the home so nothing of the login's is there to read, and a fresh /tmp. Before the first check of a review the sandbox is
proved with the same argv builder the checks use: it must start, and it must refuse a write at a fresh random path in the head
worktree. An unproved sandbox runs nothing and says why in one line; nothing in this module names a wider one (the codebase's
ADR-053 rule for Codex, review_codex.prove_sandbox, is the model).
"""
from __future__ import annotations

import os
import secrets
import shutil
import sys

from review_mcp import gittools, runner, scope
from review_mcp.scope import ToolError

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import python_pin  # noqa: E402
import review_brief  # noqa: E402

CAP_BYTES = 100_000
DEFAULT_BUDGET_S, MAX_BUDGET_S = 120, 300
PROOF_BUDGET_S = 30
# The same three answers review_codex.prove_sandbox wants; a sandbox that exits 0 without running the command proves nothing.
START_PROBE_EXIT, REFUSED_PROBE_EXIT, WRITTEN_PROBE_EXIT = 42, 43, 7
# The system trees a check needs to run a program. /opt is not among them: it holds vendor SDKs and their credentials, no check needs one, and
# the pinned toolchain is bound by name (toolchain_paths). /usr is bound whole but for /usr/local, which is put down empty (SYSTEM_MASKED) and
# given back only the toolchain: it is where an administrator keeps what is local to the machine, and a bind keeps the host's modes and the
# caller's groups, so whatever is readable to the login out there would be readable to the pull request's code.
SYSTEM_RO = ("/usr",)
SYSTEM_MASKED = ("/usr/local",)
# Private-key directories that sit inside a tree bound whole: covered by an empty tmpfs where they exist.
KEY_DIRS = ("lib/ssl/private",)   # relative to /usr, so a test can stand a fixture /usr in (bwrap_argv's usr=)
SYSTEM_LINKED = ("/bin", "/sbin", "/lib", "/lib64", "/lib32", "/libx32")
# No bound path may hold key material: /etc/ssl is not bound whole (its private/ is readable to the ssl-cert group on Debian, and a bind
# keeps that), only the certificates and the openssl configuration git and Python read, on the Debian and the Fedora layout.
ETC_RO = ("alternatives", "ld.so.cache", "ld.so.conf", "ld.so.conf.d", "passwd", "group", "nsswitch.conf", "localtime", "mime.types",
          "ssl/certs", "ssl/cert.pem", "ssl/openssl.cnf", "ca-certificates", "ca-certificates.conf",
          "pki/tls/certs", "pki/tls/cert.pem", "pki/tls/openssl.cnf", "pki/ca-trust/extracted")
# What git needs of the common git directory to read history. Everything else there is not bound, so it does not exist inside: config and
# config.worktree (a remote's credential, a program-naming key), hooks/, logs/, info/, FETCH_HEAD, the other worktrees' directories.
GIT_COMMON_TREES = ("objects", "refs")
GIT_COMMON_FILES = ("HEAD", "packed-refs", "shallow")
# And of the head worktree's own git directory (common/worktrees/<name>, or the common directory itself for a main worktree).
GIT_OWN_FILES = ("HEAD", "commondir", "gitdir", "index")
# What a check keeps of the environment: the guard's names that are not paths of this login (HOME and TMPDIR are the sandbox's own).
ENV_KEEP = ("PATH", "USER", "LOGNAME", "TERM", "TZ", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES")


def toolchain_paths() -> list[str]:
    """The install prefix of runtime/python.json's build (tools/fabric/python_pin.py), the only part of /usr/local a check is given; its
    link is made again inside by bwrap_argv, since binding the link's directory would bind every other program there."""
    return [os.path.realpath(p) for p in (python_pin.PREFIX,) if os.path.exists(p)]


def bound_under(path: str, roots: tuple[str, ...]) -> bool:
    return any(path == r or path.startswith(r + "/") for r in roots)


def bwrap_argv(bwrap: str, worktree: str, common_dir: str, git_dir: str, command: list[str], source_env: dict[str, str] | None = None,
               etc: str = "/etc", usr: str = "/usr") -> list[str]:
    """The sandbox around `command`. One builder for the proof and the checks: a proof of another argv would prove nothing."""
    home = os.path.realpath(os.path.expanduser("~"))
    # /tmp and the home are tmpfs, put down before anything is bound into them (the head worktree may sit under either, and a tmpfs mounted
    # after the bind would hide it). The login's home: the secret stores, ssh and gpg keys and the runtime state
    # have no path in the sandbox at all, and the worktree and the object store are bound at their own places on top of it.
    argv = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv", "--tmpfs", "/tmp", "--perms", "0555", "--tmpfs", home]
    for path in SYSTEM_RO:
        if os.path.isdir(path):
            argv += ["--ro-bind", path, path]
    for path in SYSTEM_LINKED:
        if os.path.islink(path):
            argv += ["--symlink", os.readlink(path), path]
        elif os.path.isdir(path):
            argv += ["--ro-bind", path, path]
    for path in SYSTEM_MASKED:
        if os.path.isdir(path):
            argv += ["--perms", "0555", "--tmpfs", path]
    for rel in KEY_DIRS:
        if os.path.isdir(os.path.join(usr, rel)):
            argv += ["--perms", "0555", "--tmpfs", "/usr/" + rel]
    for name in ETC_RO:
        if os.path.exists(os.path.join(etc, name)):
            argv += ["--ro-bind", os.path.join(etc, name), "/etc/" + name]
    for path in toolchain_paths():
        argv += ["--ro-bind", path, path]
    if os.path.islink(python_pin.LINK) and bound_under(python_pin.LINK, SYSTEM_MASKED):
        argv += ["--symlink", os.readlink(python_pin.LINK), python_pin.LINK]
    # An allowlist of the git directory, not a mask over a denylist: a file git grows or a pull request's tooling adds there is unreadable
    # until named here. A path that is absent is not bound (a repository without packed-refs or shallow).
    argv += ["--ro-bind", worktree, worktree]
    wanted = [(common_dir, n) for n in GIT_COMMON_TREES + GIT_COMMON_FILES] + ([(git_dir, n) for n in GIT_OWN_FILES] if git_dir != common_dir
                                                                              else [])
    for directory, name in wanted:
        path = os.path.join(directory, name)
        if os.path.exists(path):
            argv += ["--ro-bind", path, path]
    argv += ["--remount-ro", home, "--dev", "/dev", "--proc", "/proc", "--chdir", worktree]
    source = os.environ if source_env is None else source_env
    env = {"TMPDIR": "/tmp", "HOME": home, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0",
           **{n: source[n] for n in ENV_KEEP if n in source}}
    for name, value in env.items():
        argv += ["--setenv", name, value]
    return argv + ["--", *command]


class Unproved(ToolError):
    pass


class Sandbox:
    """The proofs of one server's life: a head whose sandbox was proved is not proved again, and one that was not is tried afresh on the next call."""

    def __init__(self) -> None:
        self.proved: set[tuple[str, str, str]] = set()      # (bwrap, worktree, head): another binary is another sandbox

    def worktree_of(self, repository: str, sha: str) -> tuple[str, str, str]:
        """(worktree, common git dir, the worktree's own git dir): the detached worktree of `sha` the dispatcher made at
        review_brief.evidence_path, checked to be a worktree of this clone at that commit. Anything else is refused: a check runs over exactly the head the review was dispatched for."""
        path = review_brief.evidence_path(review_brief.repo_name_of(repository), sha)
        if not os.path.isdir(path) or os.path.islink(path):
            raise ToolError(f"there is no checkout of {sha[:12]} at {path}; the dispatcher makes it, and no check is run")
        env = scope.git_env()

        def ask(where: str, *args: str) -> str:
            ran = gittools.run_git(where, *args, env=env)
            if ran.returncode != 0:
                raise ToolError(f"{path} is not a worktree of this clone ({gittools.first_line(ran)}); no check is run")
            return ran.out.decode("utf-8", "replace").strip()
        top, head = ask(path, "rev-parse", "--show-toplevel"), ask(path, "rev-parse", "HEAD")
        common = ask(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
        own = ask(path, "rev-parse", "--path-format=absolute", "--git-dir")
        clone_common = ask(repository, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if os.path.realpath(top) != os.path.realpath(path) or head != sha or os.path.realpath(common) != os.path.realpath(clone_common):
            raise ToolError(f"{path} is not the worktree of {sha[:12]} of this clone; no check is run")
        return os.path.realpath(path), os.path.realpath(common), os.path.realpath(own)

    @staticmethod
    def run(bwrap: str, worktree: str, common_dir: str, git_dir: str, command: list[str], budget: float, cap: int) -> runner.Ran:
        return runner.run_bounded(bwrap_argv(bwrap, worktree, common_dir, git_dir, command), {"PATH": os.environ.get("PATH", "")}, worktree, budget, cap)

    def prove(self, bwrap: str, worktree: str, common_dir: str, git_dir: str, sha: str) -> None:
        if (bwrap, worktree, sha) in self.proved:
            return
        probe = os.path.join(worktree, f".fabric-write-probe-{secrets.token_hex(8)}")
        try:
            for label, command, wanted in (
                    ("start", ["/bin/sh", "-c", f"exit {START_PROBE_EXIT}"], START_PROBE_EXIT),
                    ("refuse a write", ["/bin/sh", "-c", f'touch "$1" 2>/dev/null && exit {WRITTEN_PROBE_EXIT}; exit {REFUSED_PROBE_EXIT}', "sh", probe],
                     REFUSED_PROBE_EXIT)):
                ran = self.run(bwrap, worktree, common_dir, git_dir, command, PROOF_BUDGET_S, 4096)
                if ran.timed_out:
                    raise Unproved(f"the sandbox did not {label} within {PROOF_BUDGET_S} s; no check is run and no wider sandbox is used")
                if ran.returncode != wanted:
                    why = " ".join(ran.err.decode("utf-8", "replace").split())[-200:]
                    if ran.returncode == WRITTEN_PROBE_EXIT:
                        raise Unproved("the sandbox cannot refuse a write (exit 7); no check is run and no wider sandbox is used")
                    ran_what = "ran nothing it was asked" if ran.returncode == 0 else f"exit {ran.returncode}"
                    raise Unproved(f"the sandbox cannot {label} ({ran_what}: {why}); no check is run and no wider sandbox is used")
            if os.path.lexists(probe):
                raise Unproved("the sandbox let a write through; no check is run and no wider sandbox is used")
        finally:
            # The probe is the proof's own scratch in a tree it must not leave written; a sandbox that did write it is the case that leaves one.
            if os.path.lexists(probe):
                os.unlink(probe)
        self.proved.add((bwrap, worktree, sha))

    def check(self, args: dict) -> str:
        repository = gittools.repository_of(args)
        sha = gittools.resolve(repository, "head", args.get("head"))
        command = args.get("argv")
        if (not isinstance(command, list) or not command or len(command) > 256 or not all(isinstance(a, str) for a in command)
                or sum(len(a) for a in command) > 65536):
            raise ToolError("argv must be a list of one to 256 strings: a program and its arguments, not a shell line")
        if command[0].startswith("-") or any("\0" in a for a in command):
            raise ToolError("argv[0] is a program name: it may not start with \"-\", and no argument may hold a NUL")
        budget = scope.whole("timeout_s", args.get("timeout_s"), 1, MAX_BUDGET_S, DEFAULT_BUDGET_S)
        bwrap = shutil.which("bwrap", path=os.environ.get("PATH", ""))
        if bwrap is None:
            raise Unproved("bubblewrap (bwrap) is not installed; no check is run and no wider sandbox is used")
        worktree, common_dir, git_dir = self.worktree_of(repository, sha)
        self.prove(bwrap, worktree, common_dir, git_dir, sha)
        ran = self.run(bwrap, worktree, common_dir, git_dir, command, budget, CAP_BYTES)
        head = (f"ended at the budget of {budget} s" if ran.timed_out else "output cut" if ran.cut else f"exit {ran.returncode}")
        return "\n".join([head, "--- stdout ---", runner.text_of(ran.out, CAP_BYTES, ran.cut), "--- stderr ---",
                          runner.text_of(ran.err, runner.STDERR_CAP, ran.err_cut)])
