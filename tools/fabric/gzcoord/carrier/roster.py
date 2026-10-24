"""tools/fabric/gzcoord/carrier/roster.py — the roster of ADR-064 rules 1-3
and the InterWeave profile rendered from it.

CONTRACT. runtime/interweave/roster.json:
  {"version": 1, "profile": "gzcoord", "endpoint": "gzcoord",
   "port_range": [lo, hi],
   "rows": [{"agent_id", "login", "peer_id", "endpoint", "port",
             "identity_show", "login_signature", "countersignature"}]}
A row is keyed by agent id (ADR-039). `identity_show` is exactly what
`transportctl --profile <p> identity show` printed in the login's account.
It counts only when BOTH hold, judged here and nowhere else:
  - `login_signature`, an armored detached OpenPGP signature over the
    bytes of `identity_show`, made by the signing SUBKEY of the agent's
    key (ADR-038 rule 1) committed at identities/keys/<agent_id>.asc whose
    primary the lineage records for that agent id; and `identity_show` names
    `peer_id`;
  - `countersignature`, the same over the canonical bytes of the whole row
    (canonical_row: agent id, login, PeerId, endpoint, port) by the signing
    subkey of the coordinator's key, the lineage's root (no parent).
A row that fails either, names a login other than the lineage's for that
id, carries a port outside the range, an endpoint other than the roster's,
a malformed PeerId, or collides with another row on login, PeerId or port
renders nothing: it and the rows it collides with are refused, never
guessed between. The keys are read from the fabric's origin/main
(KeySource), never from a keyring the account happens to hold, so only the
committed keys sign. No secret is in the roster: a transport key is minted
in its own account and never leaves it (rule 3).

render_config() produces the profile's config.yaml for one account: every
OTHER valid row's PeerId allowlisted and nothing else (deny by default),
their loopback addresses as static bootstrap, this profile listening on
127.0.0.1 at its row's port, no channels, no connectivity server roles.
It refuses when the account's own row is not valid: an account whose key
is not in the roster has no profile to render.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Protocol

ROW_KEYS = {"agent_id", "login", "peer_id", "endpoint", "port",
            "identity_show", "login_signature", "countersignature"}
SIGNED_KEYS = ("agent_id", "login", "peer_id", "endpoint", "port")
ENDPOINT_RE = re.compile(r"[a-z][a-z0-9._-]{0,63}")
PROFILE_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
AGENT_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
LOGIN_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
LOOPBACK = "127.0.0.1"
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
GPG_TIMEOUT = 60


class RosterError(Exception):
    """The roster file itself cannot be read; a bad row is a refusal, not this."""


class KeySource(Protocol):
    def lineage(self) -> dict: ...
    def public_key(self, agent_id: str) -> bytes | None: ...


class GitMainKeys:
    """identities/keys/ as the fabric's origin/main has it (the same rule as
    secretstore.trust: a checkout with no origin/main is an error, never a
    fallback to the working tree)."""

    def __init__(self, root: str, timeout: float = 30.0) -> None:
        self.root, self.timeout = root, timeout

    def _show(self, rel: str) -> bytes | None:
        def git(*a: str) -> subprocess.CompletedProcess:
            try:
                return subprocess.run(["git", "-C", self.root, *a], capture_output=True, timeout=self.timeout, check=False)
            except (OSError, subprocess.TimeoutExpired) as e:
                # A RosterError, so a stuck or missing git leaves the carrier carrying
                # nothing (rule 2) and does not end it.
                raise RosterError(f"git could not read the committed keys: {type(e).__name__}") from e
        if git("rev-parse", "-q", "--verify", "refs/remotes/origin/main").returncode:
            raise RosterError(f"{self.root} has no origin/main to read the keys from: fetch the fabric")
        r = git("show", f"refs/remotes/origin/main:{rel}")
        return r.stdout if r.returncode == 0 else None

    def lineage(self) -> dict:
        raw = self._show("identities/keys/lineage.json")
        try:
            doc = json.loads(raw) if raw is not None else None
        except ValueError:
            doc = None
        if not isinstance(doc, dict):
            raise RosterError("identities/keys/lineage.json on origin/main is missing or not JSON")
        return doc

    def public_key(self, agent_id: str) -> bytes | None:
        return self._show(f"identities/keys/{agent_id}.asc")


def peer_id_ok(peer_id: str) -> bool:
    """A libp2p Ed25519 PeerId: an identity multihash over the key's protobuf
    (InterWeave's schema says the pattern alone is not sufficient)."""
    if not re.fullmatch(r"12D3KooW[1-9A-HJ-NP-Za-km-z]{44}", peer_id):
        return False
    n = 0
    for ch in peer_id:
        n = n * 58 + _B58.index(ch)
    raw = n.to_bytes(38, "big") if n.bit_length() <= 38 * 8 else b""
    return len(raw) == 38 and raw[:6] == bytes([0x00, 0x24, 0x08, 0x01, 0x12, 0x20])


def canonical_row(row: dict) -> bytes:
    return json.dumps({k: row[k] for k in SIGNED_KEYS}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def verify_detached(armored_sig: str, data: bytes, public_key: bytes, primary_fpr: str) -> str | None:
    """None when `armored_sig` is a good signature over `data` by a signing
    SUBKEY of `public_key`, whose primary is `primary_fpr`; else the reason.
    Only that key is in the keyring the check runs in."""
    with tempfile.TemporaryDirectory(prefix="gz-roster-") as tmp:
        os.chmod(tmp, 0o700)
        base = ["gpg", "--batch", "--no-tty", "--homedir", tmp]
        try:
            imp = subprocess.run(base + ["--import"], input=public_key, capture_output=True,
                                 timeout=GPG_TIMEOUT, check=False)
            if imp.returncode:
                return "the committed public key does not import"
            with open(os.path.join(tmp, "sig.asc"), "w", encoding="ascii") as fh:
                fh.write(armored_sig)
            with open(os.path.join(tmp, "data"), "wb") as fh:
                fh.write(data)
            r = subprocess.run(base + ["--status-fd=1", "--verify", os.path.join(tmp, "sig.asc"),
                                       os.path.join(tmp, "data")],
                               capture_output=True, timeout=GPG_TIMEOUT, check=False)
        except UnicodeEncodeError:
            return "the signature is not ASCII armor"
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"gpg could not run: {type(e).__name__}"
        finally:
            subprocess.run(["gpgconf", "--homedir", tmp, "--kill", "all"], capture_output=True,
                           timeout=30, check=False)
        status = r.stdout.decode("utf-8", "replace").splitlines()
        valid = [l.split() for l in status if l.startswith("[GNUPG:] VALIDSIG ")]
        bad = [l for l in status if l.split(" ")[1:2] in (["BADSIG"], ["EXPKEYSIG"], ["REVKEYSIG"],
                                                              ["ERRSIG"], ["EXPSIG"])]
        if r.returncode or bad or len(valid) != 1:
            return "the signature does not verify"
        fields = valid[0]
        signer, primary = fields[2], fields[-1]
        if primary.upper() != primary_fpr.upper():
            return "signed by a key that is not the committed agent key"
        if signer.upper() == primary.upper():
            return "signed by the primary, not by a signing subkey"
        return None


@dataclass(frozen=True)
class Refusal:
    agent_id: str
    login: str
    reason: str


@dataclass(frozen=True)
class Roster:
    profile: str
    endpoint: str
    port_range: tuple[int, int]
    rows: tuple[dict, ...]


def load(path: str) -> Roster:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        raise RosterError(f"{path}: {e}") from e
    try:
        lo, hi = doc["port_range"]
        ok = (type(doc["version"]) is int and doc["version"] == 1 and PROFILE_RE.fullmatch(doc["profile"])
              and ENDPOINT_RE.fullmatch(doc["endpoint"]) and type(lo) is int and type(hi) is int
              and 1024 <= lo <= hi <= 65535 and isinstance(doc["rows"], list)
              and all(isinstance(r, dict) for r in doc["rows"]))
    except (KeyError, TypeError, ValueError):
        ok = False
    if not ok:
        raise RosterError(f"{path} is not a version 1 roster")
    return Roster(doc["profile"], doc["endpoint"], (lo, hi), tuple(doc["rows"]))


def valid_rows(roster: Roster, keys: KeySource) -> tuple[list[dict], list[Refusal]]:
    """The rows that count, and why each other row does not."""
    lineage = keys.lineage()
    roots = [a for a, r in lineage.items() if isinstance(r, dict) and not r.get("parent")]
    refused: dict[int, str] = {}

    def refuse(i: int, why: str) -> None:
        refused.setdefault(i, why)

    for i, row in enumerate(roster.rows):
        if set(row) != ROW_KEYS or type(row["port"]) is not int or not all(
                isinstance(row[k], str) for k in ROW_KEYS - {"port"}):
            refuse(i, "the row has other fields than the roster's, or of other types")
            continue
        if not AGENT_ID_RE.fullmatch(row["agent_id"]) or not LOGIN_RE.fullmatch(row["login"]):
            refuse(i, "agent id or login is malformed")
        elif not roster.port_range[0] <= row["port"] <= roster.port_range[1]:
            refuse(i, "the port is outside the roster's range")
        elif row["endpoint"] != roster.endpoint:
            refuse(i, "the endpoint is not the roster's")
        elif not peer_id_ok(row["peer_id"]):
            refuse(i, "the PeerId is not a libp2p Ed25519 PeerId")
    # A collision refuses every row in it: which of two rows claiming one
    # port or PeerId is the real one is the coordinator's to say, not ours.
    for field in ("agent_id", "login", "peer_id", "port"):
        seen: dict = {}
        for i, row in enumerate(roster.rows):
            if i in refused or field not in row:
                continue
            seen.setdefault(row[field], []).append(i)
        for idxs in seen.values():
            if len(idxs) > 1:
                for i in idxs:
                    refuse(i, f"another row claims the same {field}")
    if len(roots) != 1:
        raise RosterError("the lineage does not have exactly one root: the coordinator's key is unknown")
    root_id = roots[0]
    for i, row in enumerate(roster.rows):
        if i in refused:
            continue
        rec = lineage.get(row["agent_id"])
        if not isinstance(rec, dict) or rec.get("login") != row["login"]:
            refuse(i, "the lineage has no such agent under that login")
            continue
        if row["peer_id"] not in str(row["identity_show"]).split():
            refuse(i, "identity_show does not print the row's PeerId")
            continue
        agent_key = keys.public_key(row["agent_id"])
        root_key = keys.public_key(root_id)
        if agent_key is None or root_key is None:
            refuse(i, "a committed key is missing")
            continue
        why = verify_detached(str(row["login_signature"]), str(row["identity_show"]).encode("utf-8"),
                              agent_key, str(rec.get("fingerprint", "")))
        if why:
            refuse(i, f"login signature: {why}")
            continue
        why = verify_detached(str(row["countersignature"]), canonical_row(row), root_key,
                              str(lineage[root_id].get("fingerprint", "")))
        if why:
            refuse(i, f"countersignature: {why}")
    good = [dict(r) for i, r in enumerate(roster.rows) if i not in refused]
    bad = [Refusal(str(r.get("agent_id", "")), str(r.get("login", "")), refused[i])
           for i, r in enumerate(roster.rows) if i in refused]
    return good, bad


def render_config(roster: Roster, good: list[dict], agent_id: str) -> str:
    me = next((r for r in good if r["agent_id"] == agent_id), None)
    if me is None:
        raise RosterError("this agent has no valid row in the roster: nothing to render")
    others = sorted((r for r in good if r["agent_id"] != agent_id), key=lambda r: r["port"])
    allowed = json.dumps([r["peer_id"] for r in others])
    boot = json.dumps([f"/ip4/{LOOPBACK}/tcp/{r['port']}/p2p/{r['peer_id']}" for r in others])
    return (
        "# Rendered from runtime/interweave/roster.json by agent-fabric; never hand-edited\n"
        "schema_version: 2\n"
        f"profile: {{ name: {roster.profile} }}\n"
        "trust:\n"
        "  policy: static-allowlist\n"
        f"  allowed_peers: {allowed}\n"
        "endpoints:\n"
        f"  default_direct_endpoint: {roster.endpoint}\n"
        "  entries:\n"
        f"    - {{ id: {roster.endpoint}, enabled: true, advertise: false, "
        "allowed_client_kinds: [automated-client] }\n"
        "channels: { desired: [] }\n"
        "discovery:\n"
        "  providers:\n"
        "    - type: static-bootstrap\n"
        "      enabled: true\n"
        "      priority: 5\n"
        "      config:\n"
        f"        peers: {boot}\n"
        f"transport: {{ listen: {{ addresses: [\"/ip4/{LOOPBACK}/tcp/{me['port']}\"] }} }}\n"
        "observability: { log_level: info }\n"
    )


def write_config(path: str, text: str) -> None:
    """Replace config.yaml atomically, owner-only (mkstemp makes the file 0600):
    the daemon refuses a file another account can change, and a half-written
    one would be read."""
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".config.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
