"""tools/fabric/gzcoord/carrier/admit.py — the two halves that PRODUCE a roster
row (ADR-064 rules 2-3); roster.py is the half that judges one.

CONTRACT.
  make_row(...)   runs in the login's own account. Refuses unless the
                  program at ~/.local/bin/transportctl (never a PATH lookup)
                  has the SHA-256 that runtime/interweave/release.json pins
                  as program_sha256.transportctl, checked before the program
                  is run (a release.json without that field refuses), and
                  its `--version` is the one `reports` pins for this machine;
                  refuses before anything is minted unless the account holds
                  the secret half of the committed signing subkey;
                  mints the profile's transport key with `identity init` only
                  when the profile has no identity.key (a key is never
                  overwritten, and never leaves the account, rule 3);
                  captures `identity show` byte for byte; signs those bytes
                  with the signing subkey of the key the lineage commits for
                  this agent id. Returns the row minus port and
                  countersignature. The signature is checked with roster.py's
                  verify_detached before the row leaves, so a key that is not
                  the committed one yields nothing.
  admit_row(...)  runs in the coordinator's account. Adds the port, signs
                  canonical_row with the signing subkey of the lineage's root,
                  and judges the roster WITH the new row through roster.py's
                  valid_rows (its port range, endpoint, signatures and collisions among valid
                  rows included): the row must be among the rows that count. It
                  also refuses any collision with an existing row, valid or
                  not, on agent id, login, PeerId or port: valid_rows ignores
                  an already-refused row when it looks for collisions, and a
                  port or PeerId a refused row still claims must not be
                  handed out again unnoticed. An agent id already in the
                  roster is a re-key, which rule 3 handles by removal, not by
                  admission. Returns the new roster document; write_roster
                  replaces the file atomically.
Nothing here reads a keyring for trust: the committed keys (KeySource) decide.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
from dataclasses import replace

from gzcoord.carrier import roster
from signing import sign as fabric_sign

TRANSPORTCTL_TIMEOUT = 60
GPG_TIMEOUT = 60

class AdmitError(Exception):
    """A refusal with the fact that fixes it; nothing was written, and no transport key is minted after one."""


def _release_entry(release_path: str, machine: str | None = None) -> dict:
    arch = machine or platform.machine()
    try:
        with open(release_path, encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc["releases"][doc["current"]][arch]
    except (OSError, ValueError) as e:
        raise AdmitError(f"{release_path}: {e}") from e
    except (KeyError, TypeError) as e:
        raise AdmitError(f"{release_path} pins no release for {arch}") from e


def pinned_version(release_path: str, machine: str | None = None) -> str:
    """What `transportctl --version` must print: release.json's `reports` for the current release on this machine."""
    try:
        return _release_entry(release_path, machine)["reports"]["transportctl"]
    except (KeyError, TypeError) as e:
        raise AdmitError(f"{release_path} pins no transportctl version") from e


def pinned_digest(release_path: str, machine: str | None = None) -> str:
    """release.json's `program_sha256` for transportctl: the installed program must be the release's, which its
    own --version cannot show (a checkout build of the pinned commit prints the same string, ADR-064 rule 4)."""
    try:
        digest = _release_entry(release_path, machine)["program_sha256"]["transportctl"]
    except (KeyError, TypeError) as e:
        raise AdmitError(f"{release_path} pins no program_sha256 for transportctl") from e
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise AdmitError(f"{release_path}: program_sha256 for transportctl is not lowercase hex SHA-256")
    return digest


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError as e:
        raise AdmitError(f"{path} cannot be read: {e.strerror or type(e).__name__}") from e
    return h.hexdigest()


def _ctl(argv: list[str], env: dict[str, str]) -> str:
    try:
        r = subprocess.run(argv, env=env, capture_output=True, timeout=TRANSPORTCTL_TIMEOUT, check=False)
    except FileNotFoundError:
        raise AdmitError(f"{argv[0]} is not installed") from None
    except (OSError, subprocess.TimeoutExpired) as e:
        raise AdmitError(f"{' '.join(argv)} did not run: {type(e).__name__}") from e
    if r.returncode:
        tail = r.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [f"exit {r.returncode}"]
        raise AdmitError(f"{' '.join(argv)} failed: {tail[0]}")
    try:
        return r.stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise AdmitError(f"{' '.join(argv)} printed bytes that are not UTF-8") from None


def identity_key_path(profile: str, environ: dict[str, str] | None = None) -> str:
    """Where transportctl keeps a profile's transport key (XDG data home, as the
    two-account live run showed); only its presence is read, never its content."""
    env = os.environ if environ is None else environ
    data = env.get("XDG_DATA_HOME", "")
    if not os.path.isabs(data):      # the XDG spec: a relative value is ignored, as the transport's own lookup does
        data = os.path.join(env.get("HOME") or os.path.expanduser("~"), ".local", "share")
    return os.path.join(data, "interweave", "profiles", profile, "identity.key")


def sign_detached(data: bytes, primary: str, env: dict[str, str]) -> str:
    """An armored detached OpenPGP signature over `data` by the signing subkey of `primary`."""
    try:
        sub = fabric_sign.signing_subkey(primary, env)
    except fabric_sign.Failure as e:
        raise AdmitError(str(e)) from None
    argv = [env.get("FABRIC_SIGN_GPG") or "gpg", "--batch", "--no-tty", "--armor", "--detach-sign", "--local-user", sub + "!"]
    try:
        r = subprocess.run(argv, input=data, env=env, capture_output=True, timeout=GPG_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise AdmitError(f"gpg could not sign: {type(e).__name__}") from e
    if r.returncode or not r.stdout:
        tail = r.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [f"exit {r.returncode}"]
        raise AdmitError(f"gpg could not sign with {sub}: {tail[0]}")
    return r.stdout.decode("ascii")


def require_secret_subkey(primary: str, env: dict[str, str]) -> None:
    """The account holds the SECRET half of the signing subkey: `--list-keys` (signing_subkey) lists public keys,
    and an account that imported only the committed public key must refuse before anything is minted."""
    try:
        sub = fabric_sign.signing_subkey(primary, env)
    except fabric_sign.Failure as e:
        raise AdmitError(str(e)) from None
    try:
        r = subprocess.run([env.get("FABRIC_SIGN_GPG") or "gpg", "--batch", "--no-tty", "--list-secret-keys", "--with-colons", sub + "!"],
                           env=env, capture_output=True, timeout=GPG_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise AdmitError(f"gpg could not list the secret keys: {type(e).__name__}") from e
    if r.returncode or not _secret_available(r.stdout.decode("utf-8", "replace"), sub):
        raise AdmitError(f"this account holds no secret key for the signing subkey {sub} of {primary}")


def _secret_available(listing: str, sub: str) -> bool:
    """The `ssb` record whose fingerprint is `sub` is not a stub: gpg lists the whole keyblock when any part of
    it has a secret, and marks a subkey whose secret is absent with `#` in field 15 (`>` is a card, usable)."""
    rows = [l.split(":") for l in listing.splitlines()]
    for i, f in enumerate(rows):
        if f[0] == "ssb" and i + 1 < len(rows) and rows[i + 1][0] == "fpr" and rows[i + 1][9].upper() == sub.upper():
            return len(f) > 14 and f[14] != "#"
    return False


def _committed(keys: roster.KeySource, agent_id: str) -> tuple[dict, bytes]:
    rec = keys.lineage().get(agent_id)
    pub = keys.public_key(agent_id)
    if not isinstance(rec, dict) or not rec.get("fingerprint") or pub is None:
        raise AdmitError(f"the lineage and identities/keys on origin/main hold no key for agent {agent_id}")
    return rec, pub


def make_row(*, rost: roster.Roster, keys: roster.KeySource, agent_id: str, login: str, release_path: str,
             environ: dict[str, str] | None = None, transportctl: str | None = None) -> dict:
    env = dict(os.environ if environ is None else environ)
    # Where the release's install.sh puts it, never a PATH lookup: a program earlier on PATH
    # answers --version as it likes, and what it prints for identity show would be signed.
    transportctl = transportctl or os.path.join(env.get("HOME") or os.path.expanduser("~"), ".local", "bin", "transportctl")
    rec, pub = _committed(keys, agent_id)
    if rec.get("login") != login:
        raise AdmitError(f"the lineage names {rec.get('login')!r} for agent {agent_id}, not {login!r}")
    # Before anything is minted: an account without the committed key must refuse with no key made.
    require_secret_subkey(rec["fingerprint"], env)
    want, digest = pinned_version(release_path), pinned_digest(release_path)
    # Hashed before it is run: what is run must be the release's program, not one that answers --version as it.
    if file_sha256(transportctl) != digest:
        raise AdmitError(f"{transportctl} is not the pinned release's program (SHA-256 differs from release.json): reinstall it")
    have = _ctl([transportctl, "--version"], env).strip()
    if have != want:
        raise AdmitError(f"transportctl reports {have!r}, the pin is {want!r}: install the pinned release first")
    ctl = [transportctl, "--profile", rost.profile]
    if not os.path.lexists(identity_key_path(rost.profile, env)):
        _ctl(ctl + ["identity", "init"], env)
    shown = _ctl(ctl + ["identity", "show"], env)
    peer_id = shown.strip()
    if not roster.peer_id_ok(peer_id):
        raise AdmitError("`identity show` did not print one PeerId: nothing signed")
    sig = sign_detached(shown.encode("utf-8"), rec["fingerprint"], env)
    why = roster.verify_detached(sig, shown.encode("utf-8"), pub, rec["fingerprint"])
    if why:
        raise AdmitError(f"the signature made does not verify against the committed key: {why}")
    return {"agent_id": agent_id, "login": login, "peer_id": peer_id, "endpoint": rost.endpoint,
            "identity_show": shown, "login_signature": sig}


ROW_IN_KEYS = roster.ROW_KEYS - {"port", "countersignature"}


def admit_row(*, doc: dict, rost: roster.Roster, keys: roster.KeySource, row_in: dict, port: int,
              environ: dict[str, str] | None = None) -> dict:
    env = dict(os.environ if environ is None else environ)
    if not isinstance(row_in, dict) or set(row_in) != ROW_IN_KEYS or not all(isinstance(v, str) for v in row_in.values()):
        raise AdmitError("the row must have exactly: " + ", ".join(sorted(ROW_IN_KEYS)) + ", all text")
    if type(port) is not int:
        raise AdmitError(f"port {port!r} is not an integer")
    for field, value in (("agent_id", row_in["agent_id"]), ("login", row_in["login"]),
                         ("peer_id", row_in["peer_id"]), ("port", port)):
        for other in rost.rows:
            if isinstance(other, dict) and other.get(field) == value:
                raise AdmitError(f"the roster already has a row with that {field}: {value!r}")
    lineage = keys.lineage()
    roots = [a for a, r in lineage.items() if isinstance(r, dict) and not r.get("parent")]
    if len(roots) != 1:
        raise AdmitError("the lineage does not have exactly one root: the coordinator's key is unknown")
    root_rec = lineage[roots[0]]
    row = dict(row_in, port=port)
    row["countersignature"] = sign_detached(roster.canonical_row(row), str(root_rec.get("fingerprint", "")), env)
    candidate = replace(rost, rows=rost.rows + (row,))
    good, bad = roster.valid_rows(candidate, keys)
    if row not in good:
        why = next((b.reason for b in bad if b.agent_id == row["agent_id"] and b.login == row["login"]),
                   "it does not count")
        raise AdmitError(f"the row would count for nothing: {why}")
    return dict(doc, rows=list(rost.rows) + [row])


def write_roster(path: str, doc: dict) -> None:
    """Replace the roster atomically; it is a committed file, so it keeps 0644 (mkstemp makes 0600)."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".roster.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
