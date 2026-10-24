"""tools/fabric/gzcoord/carrier/arrivals.py — the three small files an
InterWeave arrival leaves beside the journal (ADR-064 rules 9, 11), all JSON
lines, 0600 in the account's runtime state:

  gzcoord-arrivals.jsonl  one line per COPY received, whichever carrier
                          brought it: {"mid","addressee","carrier","t",
                          "verdict"}; written before the journal collapses
                          the copy, so the parity report can count what the
                          journal's one-row-per-MESSAGE-ID hides. A repeat
                          of a message is another line, by design.
  interweave/inbox.jsonl  the InterWeave arrivals the journal now holds and
                          the inbox may show: {"mid","content","ts",
                          "verdict"}, in arrival order, the first copy only.
  interweave/claims.jsonl who showed a MESSAGE-ID first: {"mid","via","t"}.

Claims are what decides that a session sees one message once, whichever
carrier brought it first. The one exception is rule 9: when the relay's
copy was shown first and the InterWeave copy reveals a FROM that is not the
sender's roster address, that copy is offered once more, flagged and naming
the message already shown (`reshow`).
"""
from __future__ import annotations

import json
import os
import threading
from typing import Callable


def _append(path: str, obj: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _read(path: str) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue   # a torn last line from a crash; nothing after it is complete
                if isinstance(o, dict):
                    out.append(o)
    except FileNotFoundError:
        pass
    return out


class ArrivalLog:
    def __init__(self, path: str, *, iso_now: Callable[[], str]) -> None:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        self.path, self._iso = path, iso_now
        self._lock = threading.Lock()

    def append(self, mid: str, addressee: str, carrier: str, verdict: str) -> None:
        with self._lock:
            _append(self.path, {"mid": mid, "addressee": addressee, "carrier": carrier,
                                "t": self._iso(), "verdict": verdict})


class Inbox:
    """The spool and the claims, one lock: a claim and an unseen listing
    must agree on what has been shown."""

    def __init__(self, directory: str, *, iso_now: Callable[[], str]) -> None:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        self._iso = iso_now
        self._spool = os.path.join(directory, "inbox.jsonl")
        self._claims_path = os.path.join(directory, "claims.jsonl")
        self._lock = threading.Lock()
        self.spool = _read(self._spool)
        self.claims: dict[str, dict] = {}
        for c in _read(self._claims_path):
            if "mid" in c and "via" in c:
                prior = self.claims.setdefault(c["mid"], {"via": c["via"], "reshown": False})
                if c.get("reshow"):
                    prior["reshown"] = True

    def keep(self, mid: str, content: str, ts: str, verdict: str) -> None:
        with self._lock:
            if any(r["mid"] == mid for r in self.spool):
                return
            rec = {"mid": mid, "content": content, "ts": ts, "verdict": verdict}
            _append(self._spool, rec)
            self.spool.append(rec)

    def claim(self, mid: str, via: str) -> dict:
        with self._lock:
            held = self.claims.get(mid)
            if held is None:
                _append(self._claims_path, {"mid": mid, "via": via, "t": self._iso()})
                self.claims[mid] = {"via": via, "reshown": False}
                return {"first": True, "shown_via": None, "reshow": False}
            mismatch = any(r["mid"] == mid and r["verdict"] == "mismatch" for r in self.spool)
            if via == "interweave" and held["via"] == "relay" and mismatch and not held["reshown"]:
                _append(self._claims_path, {"mid": mid, "via": via, "t": self._iso(), "reshow": True})
                held["reshown"] = True
                return {"first": True, "shown_via": "relay", "reshow": True}
            return {"first": False, "shown_via": held["via"], "reshow": False}

    def unseen(self) -> list[dict]:
        with self._lock:
            out = []
            for r in self.spool:
                held = self.claims.get(r["mid"])
                if held is None:
                    out.append({**r, "mismatch_of": None})
                elif held["via"] == "relay" and r["verdict"] == "mismatch" and not held["reshown"]:
                    out.append({**r, "mismatch_of": r["mid"]})
            return out
