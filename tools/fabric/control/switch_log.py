"""tools/fabric/control/switch_log.py — the switch controller's move log (agent-fabric ADR-052 §5 rules 11-12).

One file in the coordinator's fabric state, <state>/account-switch.jsonl, beside its other per-account state
(actions-seen.json, memory-pressure.json): append-only, one JSON object a line, mode 0600, never rewritten.
The controller (control/account_switch.py) appends; `fabric-status`, the control agent's `switch` read
(`fabric-ctl <coordinator> switch`) and `fabric-accounts switch --log` read its tail. Standard library only:
tools/fabric/status.py loads it by path.

A LINE (version 1), keys in this order:
  v         1
  at        when it was decided, UTC ISO with milliseconds
  mode      the policy's mode when it was decided: "advise" or "act"
  outcome   "would"  (advise: the move it would make, not made)
            "did"    (act: assign succeeded)
            "failed" (act: assign was run and did not succeed; nothing is assumed moved)
            "held"   (nothing moved, and the owner is told: every account exhausted, or none known)
  pool      the pool's name
  login     the login moved, or to be (a move is the login's: fabric-accounts assign moves a login)
  sessions  the login's session ids from its state record
  rule      4 (exhaustion), 5 (eject) or 7 (perishable)
  reason    "exhausted" | "eject-5h" | "eject-7d" | "perishable"
  relaxed   true when no account was under both land thresholds and the target is the one with the most
            headroom (rule 6): the owner is told
  from, to  {"account": <template slug>, "fingerprint": <setup-token sha256, 12 hex>}; `to` is null when held
  readings  per account the line rests on: five_hour and seven_day {utilization, reset}, status, exhausted,
            read_at, age_s and via ("gateway" or "probe")
  tell      true when the owner is told, not only logged (rule 12: relaxed, all exhausted)
  why       the decision in words
  assign    act only: {"exit": N, "output": [the assign's last lines, its gateway proof among them]}
No token, prompt, body or header the gateway did not parse is ever in a line (rule 11): readings are the
gateway's parsed fields and the probe's, accounts are named by slug and fingerprint.
"""
from __future__ import annotations

import json
import os
from typing import Any

LOG = "account-switch.jsonl"
VERSION = 1
OUTCOMES = ("would", "did", "failed", "held")
REASONS = ("exhausted", "eject-5h", "eject-7d", "perishable")
KEYS = ("v", "at", "mode", "outcome", "pool", "login", "sessions", "rule", "reason", "relaxed", "from", "to",
        "readings", "tell", "why")
TAIL_BYTES = 256 * 1024


def path(state: str) -> str:
    return os.path.join(state, LOG)


def line(**fields: Any) -> dict:
    """A log line in KEYS order; `assign` follows when given. A key missing is a programming error."""
    out = {k: fields[k] for k in KEYS}
    if "assign" in fields:
        out["assign"] = fields["assign"]
    return out


def append(state: str, entries: list[dict]) -> None:
    """Append whole lines in one write (O_APPEND), created 0600. Raises OSError: a move not logged is said."""
    if not entries:
        return
    os.makedirs(state, exist_ok=True)
    data = "".join(json.dumps(e, separators=(",", ":"), ensure_ascii=False) + "\n" for e in entries).encode("utf-8")
    fd = os.open(path(state), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def tail(state: str, n: int = 20) -> list[dict] | None:
    """The last n lines that parse as objects, oldest first; [] when there is no log, None when it cannot
    be read."""
    try:
        with open(path(state), "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_BYTES))
            raw = fh.read()
    except FileNotFoundError:
        return []
    except OSError:
        return None
    lines = raw.decode("utf-8", "replace").split("\n")
    if size > TAIL_BYTES:
        lines = lines[1:]   # the first may be cut
    out = []
    for text in lines:
        try:
            doc = json.loads(text)
        except ValueError:
            continue
        if isinstance(doc, dict):
            out.append(doc)
    return out[-n:] if n > 0 else []


def words(e: dict) -> str:
    """One line as a person reads it."""
    def acct(side: Any) -> str:
        return str(side.get("account")) if isinstance(side, dict) else "-"
    head = f"{e.get('at', '?')}  {e.get('outcome', '?'):<6} {e.get('login', '?')}"
    if e.get("outcome") == "held":
        return f"{head}  held on {acct(e.get('from'))}: {e.get('why', '')}"
    move = f"{acct(e.get('from'))} -> {acct(e.get('to'))}  ({e.get('reason', '?')}{', relaxed' if e.get('relaxed') else ''})"
    return f"{head}  {move}{'  TOLD' if e.get('tell') else ''}"


def section(state: str, mode: str | None, n: int = 20) -> dict:
    """The control agent's `switch` read: the policy's mode and the log's tail."""
    lines = tail(state, n)
    if lines is None:
        return {"status": "unreadable", "mode": mode}
    return {"status": "ok" if lines else "none", "mode": mode, "lines": lines}
