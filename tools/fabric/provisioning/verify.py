"""tools/fabric/provisioning/verify.py — step 10, the read-back, and the list
of what only a person can do (ADR-040 Wave 5; carried from tools/fabric/
new_agent_worker.py). What the account can do now, read back as the account;
nothing here changes it. Each read-back is a question to the account, bounded
(bounded.py): one that gets no answer is a failure or an unknown, never a pass."""
from __future__ import annotations

import hashlib
import shlex
import subprocess
import sys

from provisioning import bounded
from provisioning.worker_args import CLAUDE_ACCOUNT, HOST_ID  # noqa: F401 — the verify flags' shapes, for callers

class Account:
    """One shell line as the account, in a LOGIN shell (its profile: what
    its installers put on PATH), exactly as the worker's as_login runs it.
    The PATH is re-asserted INSIDE the shell: Debian's /etc/profile assigns
    PATH outright for a non-root login, so what env -i set would be gone
    by the time the line runs (found by the Debian smoke container, which
    then downloaded the real claude in place of the test's fake)."""

    def __init__(self, login: str, home: str, sudo: str):
        self.login, self.home, self.sudo = login, home, sudo.split()

    def run(self, line: str, *, stderr=None) -> bytes:
        p = f"/usr/local/bin:/usr/bin:/bin:{self.home}/.local/bin"
        cmd = [*self.sudo, "-n", "-u", self.login, "-H", "env", "-i", f"HOME={self.home}", f"PATH={p}",
               f"AGENT_FABRIC_PATH={p}", "bash", "-lc", 'export PATH="$AGENT_FABRIC_PATH:$PATH"; cd "$HOME" && eval "$1"',
               "_", line]
        return bounded.quiet_run(cmd, stderr=stderr)


def verify(root: str, login: str, home: str, sudo: str, projects: list[str], *, account: str = "",
           no_account: bool = False, signing_next: bool = False, via: str = "") -> tuple[str, str]:
    """Step 10: what the account can do now, read back as it, then the
    list of what only a person can do; and, when the run named a Claude
    account (`<slug>=<fp12>`), the failure line if its token is not the one
    applied ("" when it is, or when none was named). Nothing here changes
    the account."""
    a = Account(login, home, sudo)
    first = projects[0] if projects else ""
    where = f"~/projects{'/' + first if first else ''}"
    bounded.prefixed("   ", a.run("~/projects/agent-fabric/bin/fabric-secrets status 2>&1 | grep -E 'missing|OK|NOT OK'"))
    bounded.prefixed("   gh: ", a.run("gh auth status 2>&1 | grep -o 'Logged in.*' | head -1"))
    for pid in projects:
        bounded.prefixed(f"   {pid} ", a.run(f"timeout 20 git -C ~/projects/'{pid}' ls-remote --heads origin >/dev/null 2>&1 "
                                      "&& echo 'ssh to origin: ok' || echo 'ssh to origin: FAILED'"))
    bounded.prefixed("   ", a.run("printf 'git: %s <%s> signingkey=%s gpgsign=%s\\n' \"$(git config --global user.name)\" "
                          "\"$(git config --global user.email)\" \"$(git config --global user.signingkey | cut -c1-12)\" "
                          "\"$(git config --global commit.gpgsign)\""))
    # The secret of the key git signs with, not any secret key: since
    # ADR-038 every account holds its own store key, so a count of secret
    # keys was never zero and the hand-off below was never asked for
    # (rust-ui-dev-01 could not commit, 2026-10-03, seq 11160).
    # The listing only when gpg answered 0, as fabric-ctl keys reads it
    # (ops.mjs signingSecret): gpg can list a key and still exit non-zero
    # (a keyring it could not fully read), and that is no clean answer.
    listing = a.run('k="$(git config --global user.signingkey)"; [ -n "$k" ] && '
                    'out="$(gpg --list-secret-keys --with-colons -- "$k")" && printf "%s\\n" "$out"',
                    stderr=subprocess.DEVNULL).decode("utf-8", "replace")
    signing = "present" if signs_with_secret(listing) else "next" if signing_next else "absent"

    def close(*a, **k) -> str:
        return closing(*a, via=via, **k)
    for prov in ("anthropic", "openrouter"):
        bounded.prefixed(f"   launch ({prov}): ", a.run(f"cd {where} && ~/projects/agent-fabric/runtime/openrouter/launch "
                                                  f"--provider {prov} --print 2>&1 | grep -E '^launch:|resolved profile' | head -1"))
    # The control agent bootstrap enabled in the account's user manager
    # answers the coordinator from here on: one ping, as the operator.
    bounded.prefixed("   control plane: ", bounded.quiet_run([f"{root}/bin/fabric-ctl", login, "ping"], stderr=subprocess.STDOUT), skip=1)
    applied = applied_token(home, sudo)
    env_file = f"{home}/.config/agent-fabric/secrets.env"
    if account:
        slug, want = account.split("=", 1)
        if applied == want:
            return close(login, signing, "applied", first, account=account), ""
        got = (f"{env_file} could not be read as sync writes it (no file, no access, or not one export line)"
               if applied is UNREADABLE else f"no token in {env_file}" if applied is None
               else f"token {applied} in {env_file}")
        # A re-run of new-agent cannot repair it before identities/keys/
        # merges: take-bundle refuses every bundle after first contact
        # until the agent's key is on main.
        return (close(login, signing, "not-applied", first, account=account),
                f"new-agent: step failed: Claude account {slug}: CLAUDE_CODE_OAUTH_TOKEN not applied (expected {want}; "
                f"{got}). As {login}: projects/agent-fabric/bin/fabric-secrets sync, then status; a re-run of new-agent "
                "reaches the store only once identities/keys/ is merged\n")
    held = applied if isinstance(applied, str) else ""
    if no_account:
        return close(login, signing, "declined", first, account=f"={held}" if held else ""), ""
    return close(login, signing, "template" if held else "no", first), ""


UNREADABLE = object()


def applied_token(home: str, sudo: str) -> str | None | object:
    """The fingerprint (sha256[:12]) of the CLAUDE_CODE_OAUTH_TOKEN the
    account's sync applied, read as root; None when the file holds no such
    line; UNREADABLE when there was no answer to read — no file, no
    access, or a line sync does not write (two exports, or one that is not
    one shell word). The value stays in this process and only its
    fingerprint leaves it, the one fabric-secrets store templates prints."""
    r = bounded.run_bounded([*sudo.split(), "-n", "sed", "-n", "s/^export CLAUDE_CODE_OAUTH_TOKEN=//p",
                     f"{home}/.config/agent-fabric/secrets.env"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, timeout=bounded.READBACK_TIMEOUT_S)
    lines = r.stdout.decode("utf-8", "surrogateescape").splitlines()
    if r.returncode != 0:
        return UNREADABLE
    if not lines:
        return None
    if len(lines) != 1:
        return UNREADABLE
    try:
        words = shlex.split(lines[0])
    except ValueError:
        return UNREADABLE
    if len(words) != 1 or not words[0]:
        return UNREADABLE
    return hashlib.sha256(words[0].encode("utf-8", "surrogateescape")).hexdigest()[:12]


def signs_with_secret(listing: str) -> bool:
    """Whether a `gpg --list-secret-keys --with-colons` listing holds a key
    or subkey that can sign and whose secret is really here. gpg lists a
    stub (field 15 `#`: the secret is elsewhere, or was exported away) and
    exits 0 for it, so the exit status said present where commits could
    not sign. The rule is tools/fabric/control/ops/ signingSecret's, so
    fabric-ctl keys and this read-back agree."""
    for line in listing.splitlines():
        f = line.split(":")
        capabilities = f[11] if len(f) > 11 else ""
        token = f[14] if len(f) > 14 else None
        if f[0] in ("sec", "ssb") and "s" in capabilities and token != "#":
            return True
    return False


def signing_key_lines(login: str, via: str = "") -> list[str]:
    """The two lines a person runs, as the coordinator, to give an account
    the fleet's signing key: the closing's when new-agent does not import
    it, and step 11's when its import failed. An account on another host
    (`via`, its registry id) is reached through fabric-host, which
    carries stdin: a local `sudo -u` there would name a login this host
    does not have, or another account of the same name (#118, Codex)."""
    if via:
        to = f"fabric-host {via} run --as {login} --"
        return [f'gpg --export-secret-keys "$(git config --get user.signingkey)" | {to} gpg --batch --import',
                f'echo "$(git config --get user.signingkey):6:" | {to} gpg --import-ownertrust']
    return [f'gpg --export-secret-keys "$(git config --get user.signingkey)" | sudo -u {login} gpg --batch --import',
            f"sudo -u {login} bash -c \"echo '$(git config --get user.signingkey):6:' | gpg --import-ownertrust\""]


# What bootstrap, a role binding or a session would leave in an account
# (tools/fabric/bootstrap.py's list, the binding, the launcher's claude):
# none of it is a human's (ADR-044 rule 2). The last line says the probe
# ran to its end, so a shell that did not answer is never "none".
SESSION_PIECES = ("~/.claude/agents ~/.claude/settings.json ~/.claude/hooks ~/.claude/skills ~/projects/CLAUDE.md "
                  "~/projects/.claude ~/.config/systemd/user/agent-fabric-agentd.service ~/.local/bin/claude ~/.local/bin/ori "
                  "~/.local/state/agent-fabric/agents/*/binding.json")
PIECES_PROBE = f'for p in {SESSION_PIECES}; do [ -e "$p" ] && printf "%s\\n" "$p"; done; echo probed'


def verify_human(login: str, home: str, sudo: str) -> tuple[str, str]:
    """Step 10 for a human login (ADR-044): its store applied as the kind
    requires (fabric-secrets status, which reads the kind from the login's
    own clone), and nothing of a session in its home. Each read-back that
    gets no answer is a failure, never a pass."""
    a = Account(login, home, sudo)
    bounded.prefixed("   ", a.run("~/projects/agent-fabric/bin/fabric-secrets status 2>&1 | grep -E 'missing|OK|NOT OK'"))
    status = a.run("~/projects/agent-fabric/bin/fabric-secrets status >/dev/null 2>&1; echo \"status=$?\"")
    said = status.decode("utf-8", "replace").strip()
    pieces = a.run(PIECES_PROBE).decode("utf-8", "surrogateescape").splitlines()
    problems = []
    if said != "status=0":
        problems.append(f"fabric-secrets status as {login} is not OK ({said or 'no answer'}): is runtime/hosts/registry.json "
                        f"kinds[{login}] = human on its clone's main?")
    if pieces[-1:] != ["probed"]:
        problems.append(f"its home could not be read for a session's pieces (no answer as {login})")
    elif pieces[:-1]:
        problems.append(f"it holds a session's pieces, which a human never has (ADR-044 rule 2): {' '.join(pieces[:-1])}")
    else:
        print("new-agent:    nothing of a session: no agent files, hooks, agentd unit, claude or role binding",
              file=sys.stderr)
    head = "new-agent: NOT done (below)." if problems else "new-agent: done."
    text = (f"{head} Left for a person, in a terminal (nothing here can do them):\n"
            "   - moveto's sudo grant for it: the host's operator gives it, never new-agent (ADR-044 rule 5; "
            "runtime/provisioning/moveto/)\n"
            f"   - Fleet Deck, run as {login} (docs/fleet-deck/session-recovery.md)\n"
            "   - no signing key: a human holds none for the control plane (ADR-044 rule 3)\n")
    return text, "".join(f"new-agent: step failed: {p}\n" for p in problems)


def closing(login: str, signing: str, creds: str, first: str, *, account: str = "", via: str = "") -> str:
    """What is left for a person, in a terminal. A Claude account for plain
    claude is a template's token, assigned into the login's store and synced
    into its secrets.env (docs/adr/ADR-031-claude-accounts-assigned-applied-
    and-proved-by-signed-action.md) — the launcher starts no plain-claude
    session without one. Never a copy of another login's .credentials.json:
    a refresh token has one holder, and the first renewal by either signs
    the other out."""
    if signing == "present":
        gpg = "- GPG secret key: the signing key's, present"
    elif signing == "next":
        gpg = "- GPG secret key: the signing key's is not here yet; new-agent imports it next, on this terminal (11)"
    else:
        gpg = ("- GPG secret key: the signing key's is NOT in this account's keyring — commits will fail to "
               "sign. As the coordinator, in a terminal (the key has a passphrase):\n"
               + "\n".join(f"       {line}" for line in signing_key_lines(login, via)))
    slug, _, fp = account.partition("=")
    if creds == "applied":
        claude = f"- Claude account: {slug} (token {fp}), applied (plain-claude path ready)"
    elif creds == "not-applied":
        claude = (f"- Claude account: {slug} (token {fp}) was assigned and is NOT applied — the launcher refuses a "
                  f"plain-claude session until it is. As {login}: projects/agent-fabric/bin/fabric-secrets sync")
    elif creds == "declined" and fp:
        claude = (f"- Claude account: not assigned by this run (--no-claude-account); a template token is already "
                  f"applied (token {fp}), plain-claude path ready")
    elif creds == "template":
        claude = "- Claude account: a template token (plain-claude path ready)"
    else:
        lead = "not assigned (--no-claude-account: the broker path only); " if creds == "declined" else ""
        claude = (f"- Claude account: {lead}no template token — the launcher refuses a plain-claude session (--provider "
                  "anthropic) without one, its own /login included; the broker path does not need one.\n"
                  f"       As the coordinator: fabric-accounts assign {login} <account> (docs/adr/ADR-031-claude-"
                  "accounts-assigned-applied-and-proved-by-signed-action.md). Never copy another login's "
                  ".credentials.json.")
    # "done" only when nothing failed: a Claude account not applied is a
    # failed step, said on the line after this list.
    head = "new-agent: NOT done — the Claude account is not applied (below)." if creds == "not-applied" \
        else "new-agent: 0-10 done; 11, the signing key, follows." if signing == "next" else "new-agent: done."
    return (f"{head} Left for a person, in a terminal (nothing here can do them):\n"
            f"   {gpg}\n"
            f"   {claude}\n"
            "   - first launch (bootstrap has trusted its folders in Claude Code; no trust question):\n"
            f"       moveto {login}{' ' + first if first else ''}   then   runtime/openrouter/launch\n")
