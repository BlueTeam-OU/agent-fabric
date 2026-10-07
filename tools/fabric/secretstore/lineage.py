"""tools/fabric/secretstore/lineage.py — every committed agent key checked against its lineage
(ADR-038 §5 rule 2): verify(), and what it reads.

Standalone on purpose: the corpus lint loads this file by its path to check
identities/keys/ (tools/fabric/lint_rules/docs.py key_lineage_findings),
and it is fenced from contributors (tools/fabric/lint.py CONTRIBUTOR_NEVER,
policies/authority.json) so that no contributor change can make the lint
answer clean. A fence on this file alone holds only if nothing it runs is
outside it: so the standard library only, no package-relative import, and
its own gpg call — core.gpg is a contributor's to change. The rest of the
store imports these definitions from here (core, keys, mirrors), so each
exists once. Nothing here reads or prints a secret: keys, fingerprints,
user ids and the lineage file only."""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import tempfile

LOGIN_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
UID_DOMAIN = "agents.agent-fabric"
AGENT_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
# A key list or a signature check never waits on anyone; a gpg that hangs
# is a failure of the check, not a pass.
GPG_TIMEOUT_S = 60


class StoreError(Exception):
    """A refusal or a failure; the message is the whole answer and never a value."""


def born_of(agent_id: str) -> str:
    ms = int(agent_id.replace("-", "")[:12], 16)
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# The same fixed flags as core.gpg: batch, no tty, and the empty passphrase
# of an agent's key, which no check here needs but no prompt may ask for.
_GPG = ["gpg", "--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback", "--passphrase", ""]


def _gpg(homedir: str | None, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = _GPG + (["--homedir", homedir] if homedir else []) + list(args)
    op = next((a for a in args if a.startswith("--") and a not in ("--with-colons",)), "")
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=GPG_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise StoreError(f"gpg {op}: timed out after {GPG_TIMEOUT_S} s") from None
    except OSError as e:
        raise StoreError(f"gpg {op}: {e.strerror}") from None
    if check and r.returncode != 0:
        lines = [x for x in r.stderr.decode(errors="replace").strip().splitlines() if x.strip()]
        raise StoreError(f"gpg {op}: {(lines or [f'exit {r.returncode}'])[-1]}")
    return r


def _kill_agent(homedir: str) -> None:
    # A throwaway keyring's agent outlives the directory unless told to go.
    try:
        subprocess.run(["gpgconf", "--homedir", homedir, "--kill", "all"], capture_output=True, timeout=GPG_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        pass


def keys_dir(fabric: str) -> str:
    return os.path.join(fabric, "identities", "keys")


def fingerprints(homedir: str | None = None, *, secret: bool = False, query: str | None = None) -> list[str]:
    args = ["--with-colons", "--list-secret-keys" if secret else "--list-keys"] + ([query] if query else [])
    r = _gpg(homedir, *args, check=False)
    out, prev = [], None
    for line in r.stdout.decode().splitlines():
        f = line.split(":")
        if f[0] in ("pub", "sec"):
            prev = f[0]
        elif f[0] == "fpr" and prev:
            out.append(f[9])
            prev = None
    return out


# One key per use (ADR-038 rule 1): the primary certifies only, and each
# use is its own subkey, so a leaked signing key never opens the store and
# each can be rotated alone. The authentication subkey is the one an SSH
# client can use through gpg-agent.
KEY_USES = (("e", "cv25519", "encr", "encryption"), ("s", "ed25519", "sign", "signing"),
            ("a", "ed25519", "auth", "authentication"))


def _key_caps(colons: str) -> tuple[str, set[str]]:
    """From `gpg --with-colons` output for one key: the primary's own
    capabilities and those of its valid subkeys (revoked or expired ones
    excluded)."""
    primary, subs = "", set()
    for l in colons.splitlines():
        f = l.split(":")
        if f[0] == "pub":
            primary = "".join(c for c in f[11] if c.islower())
        elif f[0] == "sub" and f[1] not in ("r", "e", "i"):
            subs |= {c for c in f[11] if c.islower()}
    return primary, subs


def lineage(fabric: str) -> dict:
    try:
        with open(os.path.join(keys_dir(fabric), "lineage.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except ValueError as e:
        raise StoreError(f"identities/keys/lineage.json is not JSON: {e}") from None



def verify(fabric: str) -> list[str]:
    """Every committed key against lineage.json, each on its own:
    - lineage: keyed by agent id (a UUIDv7), each naming a login no other
      agent has, a birth equal to its id's, exactly one root (parent
      null), nobody its own parent, every chain reaching that root;
    - `<id>.asc` holds exactly one primary key, the recorded one, with a
      valid user id addressed to that agent id;
    - a child's key carries a valid certification of that user id by its
      PARENT's recorded key, read in a keyring holding only the child's
      file and the parent's, so a certification found in another file, or
      a swapped or doubled file, never passes.
    Findings, one line each; [] is clean."""
    doc, kd, findings = lineage(fabric), keys_dir(fabric), []
    where = "identities/keys/lineage.json"
    if not os.path.isdir(kd):
        return []
    if not isinstance(doc, dict):
        return [f"{where}: not an object of agent id -> {{login, born, fingerprint, parent}}"]
    for who in [w for w, r in doc.items() if not isinstance(r, dict)]:
        findings.append(f"{where}: the entry for {who} is not an object")
        del doc[who]
    for who in [w for w in doc if not AGENT_ID_RE.match(w)]:
        findings.append(f"{where}: {who} is not an agent id (a UUIDv7, ADR-039)")
        del doc[who]
    logins: dict[str, str] = {}
    for who, rec in sorted(doc.items()):
        name = rec.get("login")
        if not isinstance(name, str) or not LOGIN_RE.match(name):
            findings.append(f"{where}: {who} has no login")
        elif name in logins:
            findings.append(f"{where}: {who} and {logins[name]} both have the login {name}")
        else:
            logins[name] = who
        if rec.get("born") != born_of(who):
            findings.append(f"{where}: {who}'s born is not its id's time ({born_of(who)})")
    files = {f[:-4] for f in os.listdir(kd) if f.endswith(".asc")}
    for extra in sorted(files - set(doc)):
        findings.append(f"identities/keys/{extra}.asc: no lineage.json entry")
    roots = sorted(w for w, r in doc.items() if r.get("parent") is None)
    if doc and len(roots) != 1:
        findings.append(f"{where}: {len(roots)} roots ({', '.join(roots) or 'none'}); "
                        "the chain has exactly one, the coordinator's key")
    for who, rec in sorted(doc.items()):
        parent = rec.get("parent")
        if parent == who:
            findings.append(f"{where}: {who} is its own parent")
            continue
        seen, at = {who}, parent
        while at is not None:
            if at in seen or at not in doc:
                findings.append(f"{where}: {who}'s chain "
                                + ("loops" if at in seen else f"names {at}, who has no entry") + "; it must reach the root")
                break
            seen.add(at)
            at = (doc.get(at) or {}).get("parent")

    def keyring_check(who: str, fpr: str, parent: str | None) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o700)
            try:
                _gpg(tmp, "--import", os.path.join(kd, f"{who}.asc"), check=False)
                held = fingerprints(homedir=tmp)
                if held != [fpr]:
                    findings.append(f"identities/keys/{who}.asc: holds {len(held)} key(s), "
                                    f"{'not the recorded ' + fpr if fpr not in held else 'not only the recorded one'}")
                    return
                primary, subs = _key_caps(_gpg(tmp, "--with-colons", "--list-keys", fpr).stdout.decode())
                lacking = [name for cap, _, _, name in KEY_USES if cap not in subs]
                if lacking:
                    findings.append(f"identities/keys/{who}.asc: no {', '.join(lacking)} subkey; "
                                    "each use has its own key (ADR-038 rule 1)")
                if set(primary) & {"e", "a"}:
                    findings.append(f"identities/keys/{who}.asc: the primary key itself encrypts or authenticates; "
                                    "it certifies, and each use is a subkey (ADR-038 rule 1)")
                addr = f"<{who}@{UID_DOMAIN}>"
                if parent is not None:
                    pfpr = (doc.get(parent) or {}).get("fingerprint")
                    if not pfpr or parent not in files:
                        findings.append(f"identities/keys/{who}.asc: parent {parent} has no recorded, committed key")
                        return
                    _gpg(tmp, "--import", os.path.join(kd, f"{parent}.asc"), check=False)
                    if pfpr not in fingerprints(homedir=tmp):
                        findings.append(f"identities/keys/{parent}.asc: does not hold its recorded key")
                        return
                # Per user id: its validity, and the signatures made on it.
                r = _gpg(tmp, "--with-colons", "--check-sigs", fpr, check=False)
                on_id, has_id, certified = False, False, False
                for l in r.stdout.decode().splitlines():
                    f = l.split(":")
                    if f[0] == "uid":
                        on_id = f[1] not in ("r", "e", "i") and addr in f[9]
                        has_id |= on_id
                    elif f[0] in ("sub", "pub"):
                        on_id = False
                    elif f[0] == "sig" and on_id and parent is not None and f[1] == "!" and f[4] == pfpr[-16:]:
                        certified = True
                if not has_id:
                    findings.append(f"identities/keys/{who}.asc: no valid user id addressed to {who}")
                elif parent is not None and not certified:
                    findings.append(f"identities/keys/{who}.asc: not certified by its parent {parent}'s key")
            finally:
                _kill_agent(tmp)

    for who, rec in sorted(doc.items()):
        if who not in files:
            findings.append(f"{where}: {who} has no committed key")
            continue
        if rec.get("parent") == who:
            continue
        keyring_check(who, rec.get("fingerprint"), rec.get("parent"))
    return findings
