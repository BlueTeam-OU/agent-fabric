#!/usr/bin/env python3
"""tools/fabric/signing/sign.py — `fabric-sign`: git's signing program for
both signature formats, with a timestamp request that must succeed
(agent-fabric ADR-057; bin/fabric-sign is its shim).

CONTRACT
  git calls it as gpg.program (OpenPGP) and as gpg.ssh.program (SSH), the
  argv git builds, frozen here from git's own calls:
    --status-fd=2 -bsau KEY           sign stdin; armored signature on stdout,
                                      gpg's status lines on stderr
    --keyid-format=long --status-fd=1 --verify SIGFILE -
                                      verify; gpg's own words and exit status
    -Y sign -n git -f KEYFILE [-U] BUFFER
                                      writes BUFFER.sig
    -Y find-principals|verify|check-novalidate ...
                                      ssh-keygen's, unchanged
  and for people and hooks:
    fabric-sign note [REV...]         attach each commit's waiting proof as its
                                      note (default HEAD); status per commit on
                                      stdout, `<status> <commit>`
    fabric-sign key openpgp|ssh [PRIMARY]
                                      the value for user.signingkey: the agent
                                      key's signing subkey, `<fpr>!` or
                                      `key::ssh-ed25519 ...` (PRIMARY defaults
                                      to the account's store key)
  env     FABRIC_SIGN_GPG, FABRIC_SIGN_SSH_KEYGEN, FABRIC_SIGN_OTS name the
          programs (gpg, ssh-keygen, ots); FABRIC_SIGN_SPOOL the directory a
          proof waits in (proof.py); GNUPGHOME is gpg's, inherited.
  exit    the signer's own status when it failed; 1 when the timestamp could
          not be obtained (the signature is withheld: OpenPGP stdout stays
          empty and the BUFFER.sig ssh-keygen wrote is removed: git does not
          remove it after a failing signer) or the key is not offered; 127 a
          program is missing; 2 usage. Verification modes exit with the verifier's.

WHY
  The signing subkey of an agent key is Ed25519, which OpenPGP and SSH both
  use, so one key serves GitHub (SSH signatures verify against the
  committer's address, an agent key's OpenPGP address is not on the account)
  and any forge that wants OpenPGP; the format is the forge's, not the
  agent's. SSH signing goes through gpg-agent's ssh support, as `ssh-keygen
  -Y sign -U` does: the private key never leaves gpg-agent and no second key
  exists. A timestamp cannot live inside an SSH signature, so it is a
  separate proof for both formats, kept by proof.py until the commit exists.
  Verification does not look at the proof: the checker (ADR-057 §5 rule 5)
  judges that, and a calendar outage must never decide a signature verdict.
  The old wrapper's reason for failing signing on a stamp error is kept: a
  signed commit without a timestamp request that succeeded is what rule 2
  forbids.
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from signing import notes, proof  # noqa: E402

# Signing waits on gpg-agent, which may wait on a pinentry; a hung agent is a
# failed signature, not a commit that never returns.
SIGN_TIMEOUT_S = 120
HELPER_TIMEOUT_S = 30
USAGE = ("usage: fabric-sign note [REV...] | key openpgp|ssh [PRIMARY]   "
         "(or git's own gpg.program / gpg.ssh.program arguments)")


class Failure(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def _program(env: dict[str, str], var: str, default: str) -> str:
    return env.get(var) or default


def _run(argv: list[str], env: dict[str, str], *, input: bytes | None = None,
         capture: bool = True, timeout: float = HELPER_TIMEOUT_S) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, env=env, input=input, timeout=timeout,
                              capture_output=capture, stdin=None if input is not None else (subprocess.DEVNULL if capture else None))
    except FileNotFoundError:
        raise Failure(f"fabric-sign: {argv[0]} is not installed", 127) from None
    except subprocess.TimeoutExpired:
        raise Failure(f"fabric-sign: {os.path.basename(argv[0])} did not answer within {timeout:g} s") from None


def _checked(argv: list[str], env: dict[str, str], what: str) -> str:
    """stdout of a helper that must succeed: a failed one is said with its last stderr line, never read as empty."""
    p = _run(argv, env)
    if p.returncode != 0:
        tail = p.stderr.decode(errors="replace").strip().splitlines()[-1:] or [f"exit {p.returncode}"]
        raise Failure(f"fabric-sign: {what} failed ({tail[0]})")
    return p.stdout.decode()


def _stamped(signature: bytes, env: dict[str, str]) -> None:
    try:
        key = proof.key_of(signature)
        spool = proof.Spool.of(env)
        spool.prune()
        spool.put(key, proof.stamp(signature, env))
    except proof.StampError as e:
        raise Failure(f"fabric-sign: {e}; the commit is not signed") from None
    except OSError as e:
        raise Failure(f"fabric-sign: cannot keep the timestamp proof ({e}); the commit is not signed") from None


def sign_openpgp(argv: list[str], env: dict[str, str]) -> int:
    gpg = _program(env, "FABRIC_SIGN_GPG", "gpg")
    p = _run([gpg, *argv], env, input=sys.stdin.buffer.read(), timeout=SIGN_TIMEOUT_S)
    if p.returncode != 0 or not p.stdout.strip():
        sys.stderr.buffer.write(p.stderr)
        return p.returncode or 1
    _stamped(p.stdout, env)
    sys.stderr.buffer.write(p.stderr)
    sys.stdout.buffer.write(p.stdout)
    return 0


def _colon_keys(gpg: str, env: dict[str, str]) -> list[tuple[str, str]]:
    """(fingerprint, keygrip) of each Ed25519 key with a secret part that can sign."""
    out = _checked([gpg, "--batch", "--with-colons", "--with-keygrip", "--list-secret-keys"], env, "gpg --list-secret-keys")
    keys, current = [], None
    for line in out.splitlines():
        f = line.split(":")
        if f[0] in ("sec", "ssb"):
            current = {"ok": f[3] == "22" and "s" in f[11].lower() and f[1] not in ("r", "e", "i", "d")}
        elif f[0] == "fpr" and current is not None:
            current["fpr"] = f[9]
        elif f[0] == "grp" and current is not None:
            if current["ok"] and "fpr" in current:
                keys.append((current["fpr"], f[9]))
            current = None
    return keys


def _offered(blob: str, sock: str, env: dict[str, str]) -> bool:
    p = _run(["ssh-add", "-L"], {**env, "SSH_AUTH_SOCK": sock})
    return any(len(l.split()) > 1 and l.split()[1] == blob for l in p.stdout.decode().splitlines())


def gpg_agent_ssh_env(pubkey_file: str, env: dict[str, str]) -> dict[str, str]:
    """`env` aimed at gpg-agent's ssh socket, with the keygrip of the public
    key in pubkey_file listed in sshcontrol (idempotent) so the agent offers it."""
    gpg = _program(env, "FABRIC_SIGN_GPG", "gpg")
    try:
        with open(pubkey_file, encoding="utf-8") as f:
            blob = f.read().split()[1]
    except (OSError, IndexError):
        raise Failure(f"fabric-sign: {pubkey_file} is not an SSH public key") from None
    gpgconf = os.path.join(os.path.dirname(gpg), "gpgconf") if os.sep in gpg else "gpgconf"
    _checked([gpgconf, "--launch", "gpg-agent"], env, "gpgconf --launch gpg-agent")
    sock = _checked([gpgconf, "--list-dirs", "agent-ssh-socket"], env, "gpgconf --list-dirs").strip()
    # An empty home would make sshcontrol a path relative to the working tree.
    home = _checked([gpgconf, "--list-dirs", "homedir"], env, "gpgconf --list-dirs").strip()
    if not sock or not os.path.isabs(home):
        raise Failure("fabric-sign: gpgconf names no agent socket or home directory")
    ssh_env = {**env, "SSH_AUTH_SOCK": sock}
    if _offered(blob, sock, env):
        return ssh_env
    for fpr, grip in _colon_keys(gpg, env):
        exported = _checked([gpg, "--batch", "--export-ssh-key", fpr + "!"], env, "gpg --export-ssh-key").split()
        if len(exported) > 1 and exported[1] == blob:
            break
    else:
        raise Failure("fabric-sign: no signing key of this keyring is that SSH key "
                      f"({pubkey_file}); user.signingkey names a key this account does not hold")
    control = os.path.join(home, "sshcontrol")
    try:
        with open(control, encoding="utf-8") as f:
            listed = {l.split()[0].lstrip("!").upper() for l in f if l.split() and not l.startswith("#")}
    except FileNotFoundError:
        listed = set()
    if grip.upper() not in listed:
        # A hand-edited file may lack its final newline; gluing the grip onto
        # the last entry would disable both keys.
        with open(control, "ab+") as f:
            f.seek(0, os.SEEK_END)
            lead = b""
            if f.tell() > 0:
                f.seek(-1, os.SEEK_END)
                lead = b"" if f.read(1) == b"\n" else b"\n"
            f.write(lead + grip.encode() + b"\n")
    if not _offered(blob, sock, env):
        raise Failure(f"fabric-sign: gpg-agent does not offer that key over ssh (keygrip {grip} is in {control})")
    return ssh_env


def sign_ssh(argv: list[str], env: dict[str, str]) -> int:
    keygen = _program(env, "FABRIC_SIGN_SSH_KEYGEN", "ssh-keygen")
    run_env = env
    if "-U" in argv:
        try:
            run_env = gpg_agent_ssh_env(argv[argv.index("-f") + 1], env)
        except (IndexError, ValueError):
            raise Failure("fabric-sign: -Y sign -U without -f KEYFILE") from None
    p = _run([keygen, *argv], run_env, capture=False, timeout=SIGN_TIMEOUT_S)
    buffer_sig = argv[-1] + ".sig"
    if p.returncode != 0:
        return p.returncode
    try:
        with open(buffer_sig, "rb") as f:
            signature = f.read()
    except OSError as e:
        raise Failure(f"fabric-sign: ssh-keygen wrote no signature ({e})") from None
    try:
        _stamped(signature, env)
    except Failure:
        # git deletes BUFFER.sig only on the path that read it, never after a
        # failing signer, so a withheld signature would stay in TMPDIR whole.
        try:
            os.unlink(buffer_sig)
        except OSError:
            pass
        raise
    return 0


def passthrough(program: str, argv: list[str], env: dict[str, str]) -> int:
    return _run([program, *argv], env, capture=False, timeout=SIGN_TIMEOUT_S).returncode


def cmd_note(revs: list[str], env: dict[str, str]) -> int:
    spool = proof.Spool.of(env)
    worst = 0
    for rev in revs or ["HEAD"]:
        try:
            status, commit = notes.ensure_note(".", rev, spool)
        except notes.NotesError as e:
            raise Failure(f"fabric-sign note: {rev}: {e}") from None
        print(f"{status.name} {commit}")
        if status in (notes.Status.MISSING, notes.Status.STALE):
            print(f"fabric-sign note: {commit}: {status.value}", file=sys.stderr)
            worst = 1
    return worst


def cmd_key(args: list[str], env: dict[str, str]) -> int:
    if not args or args[0] not in ("openpgp", "ssh") or len(args) > 2:
        raise Failure(USAGE, 2)
    gpg = _program(env, "FABRIC_SIGN_GPG", "gpg")
    if len(args) == 2:
        primary = args[1]
    else:
        sys.path.insert(0, HERE)
        from secretstore import keys
        try:
            primary = keys.key_of_store()
        except Exception as e:  # StoreError: the message says what is missing
            raise Failure(f"fabric-sign key: {e}") from None
    listing = _checked([gpg, "--batch", "--with-colons", "--list-keys", primary], env, f"gpg --list-keys {primary}")
    subs, capture = [], None
    for line in listing.splitlines():
        f = line.split(":")
        if f[0] == "sub":
            capture = f if f[3] == "22" and "s" in f[11] and f[1] not in ("r", "e", "i", "d") else None
        elif f[0] == "fpr" and capture is not None:
            subs.append(f[9])
            capture = None
    if len(subs) != 1:
        raise Failure(f"fabric-sign key: {primary} has {len(subs)} usable Ed25519 signing subkeys, not one")
    if args[0] == "openpgp":
        print(subs[0] + "!")
        return 0
    exported = _checked([gpg, "--batch", "--export-ssh-key", subs[0] + "!"], env, "gpg --export-ssh-key").split()
    if len(exported) < 2:
        raise Failure(f"fabric-sign key: gpg cannot export {subs[0]} as an SSH key")
    print(f"key::{exported[0]} {exported[1]}")
    return 0


def main(argv: list[str], env: dict[str, str]) -> int:
    try:
        if not argv or argv[0] in ("-h", "--help"):
            print(USAGE, file=sys.stderr if not argv else sys.stdout)
            return 2 if not argv else 0
        if argv[0] == "note":
            return cmd_note(argv[1:], env)
        if argv[0] == "key":
            return cmd_key(argv[1:], env)
        if argv[0] == "-Y":
            if argv[1:2] == ["sign"]:
                return sign_ssh(argv, env)
            return passthrough(_program(env, "FABRIC_SIGN_SSH_KEYGEN", "ssh-keygen"), argv, env)
        if argv[0].startswith("-"):
            # -bsau wins over --verify: the no-fallback guarantee of signing
            # must not be defeatable by what else is in argv (the old wrapper's rule).
            if "-bsau" in argv:
                return sign_openpgp(argv, env)
            return passthrough(_program(env, "FABRIC_SIGN_GPG", "gpg"), argv, env)
        raise Failure(USAGE, 2)
    except Failure as e:
        print(str(e), file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], dict(os.environ)))
