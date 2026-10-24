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
                          the inbox may show: {"mid","content","ts","sender",
                          "verdict"}, in arrival order, the first copy only;
                          `sender` is the roster's address for the PeerId that
                          sent it (what the inbox shows), not its FROM.
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
import time
from typing import Callable

from . import CARRIER_NAME, jsonl


def _append(path: str, obj: dict) -> None:
    jsonl.append_path(path, obj)


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
        jsonl.repair(path)

    def append(self, mid: str, addressee: str, carrier: str, verdict: str) -> None:
        with self._lock:
            _append(self.path, {"mid": mid, "addressee": addressee, "carrier": carrier,
                                "t": self._iso(), "verdict": verdict})


CLAIM_KEPT_DAYS = 14


def _rewrite(path: str, records: list[dict]) -> None:
    tmp = path + ".new"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        for r in records:
            jsonl.write_all(fd, (json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


class Inbox:
    """The spool and the claims, one lock: a claim and an unseen listing
    must agree on what has been shown. A long-lived carrier must not hold every
    body it ever journaled: a record is dropped from memory and, at the next open,
    from the file once it is settled (shown, and no re-show owed); a claim is kept
    CLAIM_KEPT_DAYS, longer than any relay record stays unacknowledged."""

    def __init__(self, directory: str, *, iso_now: Callable[[], str]) -> None:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        self._iso = iso_now
        self._spool = os.path.join(directory, "inbox.jsonl")
        self._claims_path = os.path.join(directory, "claims.jsonl")
        jsonl.repair(self._spool)
        jsonl.repair(self._claims_path)
        self._lock = threading.Lock()
        raw_claims = [c for c in _read(self._claims_path) if "mid" in c and "via" in c]
        cutoff = _cutoff(self._iso(), CLAIM_KEPT_DAYS)
        fresh = [c for c in raw_claims if str(c.get("t", "")) >= cutoff]
        aged = {c["mid"] for c in raw_claims} - {c["mid"] for c in fresh}
        if len(fresh) != len(raw_claims):
            _rewrite(self._claims_path, fresh)
        self.claims: dict[str, dict] = {}
        for c in fresh:
            prior = self.claims.setdefault(c["mid"], {"via": c["via"], "reshown": False})
            if c.get("reshow"):
                prior["reshown"] = True
        spool = _read(self._spool)
        # A record whose claim has aged out goes with it: without the claim it would be
        # offered as new, and it was shown long ago.
        self.spool = [r for r in spool if r["mid"] not in aged and not self._settled(r)]
        if len(self.spool) != len(spool):
            _rewrite(self._spool, self.spool)
        self._kept = {r["mid"] for r in self.spool}

    def _settled(self, r: dict) -> bool:
        held = self.claims.get(r["mid"])
        if held is None:
            return False
        return not (held["via"] == "relay" and r["verdict"] == "mismatch" and not held["reshown"])

    def keep(self, mid: str, content: str, ts: str, verdict: str, sender: str) -> None:
        with self._lock:
            if mid in self._kept or (mid in self.claims and verdict != "mismatch"):
                return
            rec = {"mid": mid, "content": content, "ts": ts, "verdict": verdict, "sender": sender}
            _append(self._spool, rec)
            self.spool.append(rec)
            self._kept.add(mid)

    def claim(self, mid: str, via: str) -> dict:
        with self._lock:
            out = self._claim(mid, via)
            self.spool = [r for r in self.spool if not self._settled(r)]
            return out

    def _claim(self, mid: str, via: str) -> dict:
        held = self.claims.get(mid)
        if held is None:
            _append(self._claims_path, {"mid": mid, "via": via, "t": self._iso()})
            self.claims[mid] = {"via": via, "reshown": False}
            return {"first": True, "shown_via": None, "reshow": False}
        mismatch = any(r["mid"] == mid and r["verdict"] == "mismatch" for r in self.spool)
        if via == CARRIER_NAME and held["via"] == "relay" and mismatch and not held["reshown"]:
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


def _cutoff(now_iso: str, days: int) -> str:
    """The ISO time `days` before `now_iso` (the lines' own format sorts as text)."""
    import calendar
    try:
        t = calendar.timegm(time.strptime(now_iso, "%Y-%m-%dT%H:%M:%SZ")) - days * 86400
    except ValueError:
        return ""      # a clock that does not say the time prunes nothing
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
