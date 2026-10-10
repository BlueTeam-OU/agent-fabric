"""tools/fabric/provisioning/signing.py — step 11, the fleet's signing key into the
account's keyring, with a person at this terminal (carried from
tools/fabric/new_agent.py): exported by this login's gpg, imported by the
account's on a pipe, never a file; the passphrase is pinentry's, never read,
echoed or passed here."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

from provisioning import config as cfg
from provisioning.bounded import run_bounded, stop_tree
from provisioning.new_agent_args import say
from provisioning.verify import signing_key_lines, signs_with_secret


# What the account's shell runs for the test signature: its terminal
# named for pinentry before the pipe takes stdin, then one detached
# signature of a fixed line, thrown away. The key is "$1", never spliced.
SIGN_TEST = ('t="$(tty)" || t=""; printf "%s\\n" "new-agent: a test signature" '
             '| GPG_TTY="$t" gpg --batch --local-user "$1" --detach-sign >/dev/null')


TERM_VALUE = re.compile(r"[A-Za-z0-9._+-]{1,64}")


def primary_fingerprint(listing: str) -> str:
    """The primary key's fingerprint in a `--with-colons` secret listing:
    the first fpr record after the first sec record; "" when there is none."""
    seen_sec = False
    for line in listing.splitlines():
        f = line.split(":")
        if f[0] == "sec":
            seen_sec = True
        elif f[0] == "fpr" and seen_sec and len(f) > 9 and re.fullmatch(r"[0-9A-F]{40,64}", f[9]):
            return f[9]
    return ""


def last_line(err, silent: str = "(gpg said nothing)") -> str:
    err.seek(0)
    lines = [ln for ln in err.read().decode("utf-8", "replace").splitlines() if ln.strip()]
    return lines[-1].strip() if lines else silent


def signing_key(login: str, host: str, *, via: str = "") -> int:
    """11. The fleet's signing key into the account's keyring, with a person
    at this terminal: exported by this login's gpg and imported by the
    account's on a pipe, never a file; the passphrase is pinentry's
    (GPG_TTY names this terminal for it), never read, echoed or passed
    here. Its ownertrust set, then proved by a signature made as the
    account — on every run: a key already there skips only the import, so
    a re-run repairs an ownertrust an earlier run did not set and proves
    the key again (#118 review, F2). A failure is said with gpg's last line
    and the two lines a person runs; 0-10 stay done, and this step alone
    exits 1."""
    def failed(why: str) -> int:
        say(f"11. the signing key: FAILED — {why}")
        say("    by hand, as this login, in a terminal (the key has a passphrase):")
        for line in signing_key_lines(login, via):
            print(f"new-agent: {line}", file=sys.stderr)
        return 1

    def ask(cmd: list[str], *, stdin=subprocess.DEVNULL, data: bytes | None = None, env=None,
            stdout=subprocess.PIPE, silent: str = "(gpg said nothing)") -> tuple[int, str]:
        with tempfile.TemporaryFile() as err:
            try:
                r = run_bounded(cmd, stdin=subprocess.PIPE if data is not None else stdin, input=data,
                                stdout=stdout, stderr=err, env=env, timeout=cfg.STEP_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                return 124, f"no answer within {cfg.STEP_TIMEOUT_S} s"
            except OSError as exc:
                return 127, f"{cmd[0]}: {exc.strerror or exc}"
            if r.returncode != 0:
                return r.returncode, last_line(err, silent)
            return 0, r.stdout.decode("utf-8", "replace") if r.stdout is not None else ""

    sys.stderr.flush()
    rc, key = ask(["git", "-C", cfg.ROOT, "config", "--get", "user.signingkey"])
    key = key.strip() if rc == 0 else ""
    if not key:
        return failed("this login's git config names no user.signingkey")
    rc, listing = ask(["gpg", "--list-secret-keys", "--with-colons", "--", key])
    fpr = primary_fingerprint(listing) if rc == 0 and signs_with_secret(listing) else ""
    if not fpr:
        return failed(f"this login's keyring holds no signing secret for {key}" + ("" if rc == 0 else f": {listing}"))
    as_account = [cfg.HX, host, "--as", login, "--"]
    rc, theirs = ask([*as_account, "gpg", "--list-secret-keys", "--with-colons", "--", fpr])
    if rc == 0 and signs_with_secret(theirs):
        say(f"11. the signing key {fpr[-16:]}: already in {login}'s keyring; its ownertrust and a test signature follow")
    else:
        why = import_key(login, fpr, as_account)
        if why:
            return failed(why)
    rc, why = ask([*as_account, "gpg", "--batch", "--import-ownertrust"], data=f"{fpr}:6:\n".encode())
    if rc != 0:
        return failed(f"its ownertrust as {login}: {why}")
    term = os.environ.get("TERM", "")
    term_env = ["env", f"TERM={term}"] if TERM_VALUE.fullmatch(term) else []
    sys.stderr.flush()
    # stdout is the person's terminal, never a pipe: over ssh (`hostexec
    # --tty` is `ssh -t`) the remote pty — the one pinentry draws on, and
    # gpg's stderr with it — comes back on ssh's stdout, and a captured
    # stdout hid the prompt (#118 review, F1). So on that backend gpg's
    # words are on the terminal, not in the stderr file.
    rc, why = ask([cfg.HX, host, "--tty", "--as", login, "--", *term_env, "sh", "-c", SIGN_TEST, "_", fpr], stdin=None,
                  stdout=None, silent="gpg's words are above, on the terminal")
    if rc != 0:
        return failed(f"the test signature as {login}: {why}")
    say(f"11. the signing key: in {login}'s keyring, trusted, and a test signature made as it — done.")
    return 0


def import_key(login: str, fpr: str, as_account: list[str]) -> str:
    """The export here piped into the import as the account; "" when both
    exited 0, else what failed, with gpg's last line."""
    say(f"11. the signing key {fpr[-16:]}: exported here, imported as {login}; gpg's pinentry asks for its passphrase")
    env = dict(os.environ)
    if not env.get("GPG_TTY") and os.isatty(0):
        env["GPG_TTY"] = os.ttyname(0)
    with tempfile.TemporaryFile() as exp_err, tempfile.TemporaryFile() as imp_err:
        exp = subprocess.Popen(["gpg", "--export-secret-keys", "--", fpr], stdout=subprocess.PIPE, stderr=exp_err, env=env)
        try:
            imp = subprocess.Popen([*as_account, "gpg", "--batch", "--import"], stdin=exp.stdout,
                                   stdout=subprocess.DEVNULL, stderr=imp_err)
        except OSError as exc:
            stop_tree(exp)
            return f"import as {login}: {exc.strerror or exc}"
        finally:
            exp.stdout.close()
        try:
            imp.wait(timeout=cfg.STEP_TIMEOUT_S)
            exp.wait(timeout=60)
        except subprocess.TimeoutExpired:
            for p in (exp, imp):
                if p.poll() is None:
                    stop_tree(p)
            return f"the export or the import gave no answer within {cfg.STEP_TIMEOUT_S} s"
        # The export first: an import that read nothing says so, and the
        # export's own line is the cause.
        if exp.returncode != 0:
            return f"the export here: {last_line(exp_err)}"
        if imp.returncode != 0:
            return f"the import as {login}: {last_line(imp_err)}"
    return ""
