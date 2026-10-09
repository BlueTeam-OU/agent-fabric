#!/usr/bin/env python3
"""tools/fabric/secret_run.py — one command run with some of this agent's own
secrets in its environment, behind bin/fabric-secret-run.

    fabric-secret-run NAME[,NAME...] -- <command> [args...]

Each NAME is decrypted from this login's own store (secret_store.py: the
store store_dir() names, the account's default keyring) and added to the
environment the command is exec'd with — only that command's, and only the
names asked for. A named variable the caller already has is replaced by the
store's value. Nothing of a value is printed, logged or put in argv.

Only an agent's own entries (secretstore/reserved.py): a name the fabric
manages reaches the tools that read it through `fabric-secrets sync`, and is
refused here. The store is read as it stands locally, with no pull: sync is
what brings it up to its remote, so an entry the parent put appears after
the next sync.

Exit status, the command's own once it runs (this process becomes it):
    2    usage, or a NAME that is malformed, managed, absent, undecryptable
         or not an environment value (it holds a NUL byte), or a registry
         that cannot say whether it is managed — fail closed: nothing runs,
         and the line names the NAME, never the value
    126  the command was found but could not be executed
    127  the command was not found on the caller's PATH

A separate command, not a subcommand of fabric-secrets: fabric-secrets has
an allow rule in every account's settings, and a wrapper that runs whatever
follows `--` must be asked for like any command (runtime/claude-code/
commands.json `not_allowed`, as fabric-lease)."""
from __future__ import annotations

import os
import shutil
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import roots  # noqa: E402
from secretstore.core import NAME_RE, StoreError, gpg, store_dir  # noqa: E402
from secretstore.reserved import RegistryUnreadable, reserved  # noqa: E402

USAGE = "usage: fabric-secret-run NAME[,NAME...] -- <command> [args...]"
# Set by bin/fabric-secret-run to the signals the caller left ignored:
# Python ignores SIGPIPE and SIGXFSZ at start-up, an exec keeps an ignored
# disposition, and the command must get what the caller gave the bash.
IGNORED_ENV = "_FABRIC_SECRET_RUN_IGNORED"
RESTORED = {"PIPE": signal.SIGPIPE, "XFSZ": signal.SIGXFSZ}
# A decryption that hangs (an agent asking for a passphrase no one types)
# is a failure of that name, as fabric-ctl's signingKey() bounds its own.
DECRYPT_TIMEOUT_S = 60


class Refused(Exception):
    """The line to print; exit 2, nothing run."""


def parse(argv: list[str]) -> tuple[list[str], list[str]]:
    if len(argv) < 3 or argv[1] != "--":
        raise Refused(USAGE)
    names = []
    for n in argv[0].split(","):
        if not NAME_RE.fullmatch(n):
            raise Refused(f"{n!r} is not a secret name (UPPER_SNAKE, as an environment variable); nothing run")
        if n not in names:
            names.append(n)
    return names, argv[2:]


def decrypt(names: list[str], store: str, root: str) -> dict[bytes, bytes]:
    """Every name checked before any is decrypted, so a managed name later
    in the list never costs a decryption; then each, failing closed."""
    for n in names:
        try:
            who = reserved(n, root)
        except RegistryUnreadable as e:
            raise Refused(f"cannot tell whether {n} is managed ({e}); nothing run") from None
        if who:
            raise Refused(f"{n} is managed by {who}; it reaches its tools through fabric-secrets sync, "
                          "not fabric-secret-run; nothing run")
    out: dict[bytes, bytes] = {}
    for n in names:
        path = os.path.join(store, "env", f"{n}.gpg")
        if not os.path.isfile(path):
            raise Refused(f"{n}: absent from this login's store ({store}); nothing run")
        try:
            r = gpg("--decrypt", path, check=False, timeout=DECRYPT_TIMEOUT_S)
        except StoreError as e:
            raise Refused(f"{n}: could not be decrypted ({e}); nothing run") from None
        if r.returncode != 0:
            # gpg's last line says why (no secret key, bad data); its stderr
            # never holds the plaintext.
            why = ([l for l in r.stderr.decode(errors="replace").splitlines() if l.strip()] or [f"exit {r.returncode}"])[-1]
            raise Refused(f"{n}: could not be decrypted ({why}); nothing run")
        if b"\0" in r.stdout:
            raise Refused(f"{n}: holds a NUL byte, which no environment value can; nothing run")
        out[n.encode()] = r.stdout
    return out


def run(argv: list[str]) -> int:
    ignored = set(os.environ.pop(IGNORED_ENV, "").split())
    try:
        names, cmd = parse(argv)
        # Resolved on the caller's PATH before a value is added: a secret
        # named PATH changes the command's environment, never which command.
        exe = shutil.which(cmd[0]) if os.sep not in cmd[0] else cmd[0]
        if exe is None or not os.path.exists(exe):
            print(f"fabric-secret-run: {cmd[0]}: command not found", file=sys.stderr)
            return 127
        if os.path.isdir(exe) or not os.access(exe, os.X_OK):
            print(f"fabric-secret-run: {cmd[0]}: not executable", file=sys.stderr)
            return 126
        values = decrypt(names, store_dir(), roots.operator_root())
    except Refused as e:
        print(f"fabric-secret-run: {e}", file=sys.stderr)
        return 2
    env = dict(os.environb)   # without IGNORED_ENV, popped above
    env.update(values)
    for name, sig in RESTORED.items():
        signal.signal(sig, signal.SIG_IGN if name in ignored else signal.SIG_DFL)
    try:
        os.execve(exe, cmd, env)
    except OSError as e:
        print(f"fabric-secret-run: {cmd[0]}: {e.strerror}", file=sys.stderr)
        return 126
    return 126   # not reached: execve returns only by raising


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE)
        print("  each NAME from this login's own store, into the command's environment only; "
              "managed names come through fabric-secrets sync")
        return 0
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
