#!/usr/bin/env python3
"""tools/fabric/provisioning/github_signing_key.py — an agent's signing subkey,
in SSH form, registered as a signing key on the GitHub account that pushes the
fleet's commits (agent-fabric ADR-057 §5 rule 6): `add` at provisioning,
`remove` when the agent is revoked.

CONTRACT
  argv    add <login> | remove <login> | list      (--dry-run before the verb:
          says what would be sent and sends nothing)
  title   `fabric-agent <login> (<agent id>)`; the title is the key's identity
          here, so `remove` finds an agent's keys by `fabric-agent <login> (`.
  key     the Ed25519 signing subkey of <keys>/<id>.asc (the operator's keys directory, roots.py), which gpg
          exports as an SSH key (live check 2026-10-13: all 26 did); <id> is
          the newest lineage entry of that login.
  add     idempotent: the same title with the same key is "present"; the same
          key under another title, or the same title over another key, is a
          refusal that names both, never an overwrite.
  stdout  one line per verb: `added|present|removed|absent <title>`; `list`
          prints each title.
  stderr  a refusal, with the fact that fixes it.
  exit    0 done; 1 a refusal or a failed call; 2 usage.
  The call is `gh api`, so the token is the operator's own gh login and needs
  the admin:ssh_signing_key scope (read for `list`); without it the refusal
  says so and gives the command that grants it.

WHY the title and not a stored id: the registered key is the only record GitHub
keeps, and a re-run must find it again after anything else was lost.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import roots  # noqa: E402
GH_TIMEOUT_S = 60
GPG_TIMEOUT_S = 60
SCOPE_HINT = "gh auth refresh -h github.com -s admin:ssh_signing_key"


class Refused(Exception):
    """The message is the whole answer."""


def title_of(login: str, agent_id: str) -> str:
    return f"fabric-agent {login} ({agent_id})"


def agent_id_of(login: str, root: str | None = None) -> str:
    path = os.path.join(roots.keys_dir(root), "lineage.json")
    try:
        with open(path, encoding="utf-8") as f:
            lineage = json.load(f)
    except (OSError, ValueError) as e:
        raise Refused(f"{path} cannot be read ({type(e).__name__}: {e})") from None
    mine = [(e.get("born", ""), i) for i, e in lineage.items() if isinstance(e, dict) and e.get("login") == login]
    if not mine:
        raise Refused(f"{login} is not in {path}: its key is made by store-enroll and merged first")
    return max(mine)[1]


def _gpg(home: str, *args: str) -> str:
    try:
        p = subprocess.run(["gpg", "--homedir", home, "--batch", "--no-tty", *args], capture_output=True, text=True,
                           timeout=GPG_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise Refused("gpg is not installed") from None
    except subprocess.TimeoutExpired:
        raise Refused(f"gpg did not answer within {GPG_TIMEOUT_S} s") from None
    if p.returncode != 0:
        raise Refused(f"gpg {args[0]} failed: {(p.stderr.strip().splitlines() or [f'exit {p.returncode}'])[-1]}")
    return p.stdout


def ssh_form(keyfile: str) -> str:
    """`ssh-ed25519 <base64>` of the one usable signing subkey in an armored public key."""
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    # Short parent: gpg's sockets are named under the home, and a path over
    # 107 bytes is refused.
    with tempfile.TemporaryDirectory(prefix="fgsk.", dir=base) as home:
        os.chmod(home, 0o700)
        try:
            _gpg(home, "--import", keyfile)
            subs = []
            lines = _gpg(home, "--with-colons", "--list-keys").splitlines()
            for i, line in enumerate(lines):
                f = line.split(":")
                if f[0] == "sub" and f[3] == "22" and "s" in f[11] and f[1] not in ("r", "e", "i", "d"):
                    subs.append(lines[i + 1].split(":")[9])
            if len(subs) != 1:
                raise Refused(f"{keyfile} has {len(subs)} usable Ed25519 signing subkeys, not one")
            fields = _gpg(home, "--export-ssh-key", subs[0] + "!").split()
        finally:
            try:
                subprocess.run(["gpgconf", "--homedir", home, "--kill", "all"], capture_output=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass  # the throwaway home goes either way; this must not hide the error above
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise Refused(f"gpg cannot export the signing subkey of {keyfile} as an SSH key")
    return f"{fields[0]} {fields[1]}"


def _gh(*args: str) -> str:
    try:
        p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise Refused("gh is not installed") from None
    except subprocess.TimeoutExpired:
        raise Refused(f"gh did not answer within {GH_TIMEOUT_S} s") from None
    if p.returncode != 0:
        said = (p.stderr.strip().splitlines() or [f"exit {p.returncode}"])[-1]
        # gh names the scope and its fix itself when it knows; a 403 or 404 is
        # what GitHub answers a token without the scope otherwise.
        hint = f" (if the token lacks the scope: {SCOPE_HINT})" if "gh auth refresh" not in p.stderr and ("403" in said or "404" in said) else ""
        raise Refused(f"gh {args[0]} failed: {said}{hint}")
    return p.stdout


SCOPE = "admin:ssh_signing_key"


def token_scopes() -> set[str] | None:
    """The OAuth scopes of the gh token in use, from the X-OAuth-Scopes header of `gh api -i user` (the token itself is
    never read or printed); None when the answer has no such header (a fine-grained or app token states none), which is
    not the same as an empty set. Refused when gh cannot answer."""
    head = _gh("api", "-i", "user").split("\n\n", 1)[0].replace("\r", "")
    for line in head.splitlines():
        name, sep, value = line.partition(":")
        if sep and name.strip().lower() == "x-oauth-scopes":
            return {x.strip() for x in value.split(",") if x.strip()}
    return None


def scope_notice() -> str | None:
    """What the operator is told up front about step 12, or None when the token carries the scope. Never a refusal of
    the run: the fabric-secrets sync that writes gh's config from the stored GH_TOKEN is why `gh auth refresh` alone
    does not last, so the new token is stored as GH_TOKEN too."""
    try:
        scopes = token_scopes()
    except Refused as exc:
        return (f"12. the operator's gh token scopes could not be read ({exc}); step 12 may not register the signing "
                f"key. It needs the {SCOPE} scope.")
    if scopes is None:
        return (f"12. the operator's gh token states no scopes (a fine-grained or app token); step 12 needs {SCOPE} "
                "and may not register the signing key.")
    if SCOPE in scopes:
        return None
    return (f"12. the operator's gh token lacks {SCOPE}, so step 12 will NOT register this agent's signing key on "
            f"GitHub (its commits read Unverified until it is). To fix it: run `{SCOPE_HINT}` in a terminal, then store "
            "the new token in the operator's own store as GH_TOKEN (fabric-secrets), because fabric-secrets sync rewrites "
            "gh's config from the stored GH_TOKEN and a refresh alone does not last. The run goes on.")


def registered() -> list[dict]:
    out = _gh("api", "--paginate", "user/ssh_signing_keys?per_page=100", "--jq", ".[] | {id, title, key}")
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def add(login: str, *, dry: bool = False, root: str | None = None) -> str:
    agent_id = agent_id_of(login, root)
    title = title_of(login, agent_id)
    key = ssh_form(os.path.join(roots.keys_dir(root), agent_id + ".asc"))
    blob = key.split()[1]
    for row in registered():
        same_key = row["key"].split()[1] == blob
        if row["title"] == title and same_key:
            return f"present {title}"
        if row["title"] == title or same_key:
            raise Refused(f"GitHub already holds {'this key' if same_key else 'the title'} as '{row['title']}' "
                          f"(id {row['id']}); {title} is not added over it — remove that one first if it is stale")
    if dry:
        return f"would add {title}"
    _gh("api", "-X", "POST", "user/ssh_signing_keys", "-f", f"title={title}", "-f", f"key={key}")
    return f"added {title}"


def remove(login: str, *, dry: bool = False) -> list[str]:
    prefix = f"fabric-agent {login} ("
    out = []
    for row in registered():
        if row["title"].startswith(prefix):
            if not dry:
                _gh("api", "-X", "DELETE", f"user/ssh_signing_keys/{row['id']}")
            out.append(f"{'would remove' if dry else 'removed'} {row['title']}")
    return out or [f"absent {prefix}…)"]


def main(argv: list[str]) -> int:
    dry = argv[:1] == ["--dry-run"]
    args = argv[1:] if dry else argv
    try:
        if len(args) == 2 and args[0] == "add":
            print(add(args[1], dry=dry))
        elif len(args) == 2 and args[0] == "remove":
            print("\n".join(remove(args[1], dry=dry)))
        elif args == ["list"]:
            print("\n".join(r["title"] for r in registered()))
        else:
            print("usage: github_signing_key.py [--dry-run] add <login> | remove <login> | list", file=sys.stderr)
            return 2
    except Refused as e:
        print(f"github_signing_key: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
