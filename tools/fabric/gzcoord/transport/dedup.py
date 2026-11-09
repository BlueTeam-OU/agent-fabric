"""tools/fabric/gzcoord/transport/dedup.py — what a session is shown when more than one transport brought a message: the
shown ledger (carrier/ledger.py) decides, by MESSAGE-ID and the hash of the text, whichever transport delivered first and
with or without a mirror at all. The decision per record, taken while the ledger's lock is held by the caller
(inbox_parts/watch.py), is the whole of this module."""
from __future__ import annotations

import hashlib
from typing import Any

from .. import gzmsg
from ..carrier import ledger as _ledger_mod
from . import carrier
from .relay import NAME as PRIMARY_NAME


def ledger_key(rec: dict, msg: dict) -> str:
    """The id the ledger and the journal key a message by: its MESSAGE-ID, else its body's hash."""
    mid = (msg.get("metadata") or {}).get("MESSAGE-ID")
    return mid or "sha256:" + hashlib.sha256(str(rec.get("content", "")).encode("utf-8", "surrogatepass")).hexdigest()


def body_hash(content: str) -> str:
    """What tells two messages that share a MESSAGE-ID apart in the ledger (see ledger.py)."""
    return _ledger_mod.body_hash(content)


def record(held: Any, d: Any, mid: str, via: str, h: str) -> None:
    """The ledger line a showing starts with: a pending one, or, for a repeat, none (its final line is all)."""
    if d.append_pending:
        held.pending(mid, via, d.flagged, h)
    else:
        held.finish_repeat(mid, via, d.flagged, h)


def admit(lock: Any, classified: list[dict], primary_mine: list[dict], mirror_recs: list[dict]) -> None:
    """The ledger's decision on one page, in place: a primary's record shown before is marked `quiet` (journaled and
    acknowledged, not shown twice) and the others carry `may_repeat`; a mirror's record not shown before is appended to
    `classified` as a message of its own, flagged when its sender disagrees with its FROM. Raises what the ledger raises
    (OSError for a write that failed); the caller releases the lock."""
    for c in primary_mine:
        mid = ledger_key(c["rec"], c["msg"])
        d = lock.decide(mid, PRIMARY_NAME, "unauthenticated", body_hash(c["rec"]["content"]))
        if not d.show:
            c["quiet"] = True     # shown before: journaled and acknowledged, not shown twice
            continue
        c["may_repeat"] = d.may_repeat
        record(lock, d, mid, PRIMARY_NAME, body_hash(c["rec"]["content"]))
    for u in mirror_recs:
        try:
            msg = gzmsg.parse(u["content"])
        except (gzmsg.NotGzcoord, AttributeError, TypeError, KeyError):
            continue
        if msg["type"] in gzmsg.RETIRED_TYPES:
            continue      # presence is never shown (SPEC §8), whichever transport brings it
        d = lock.decide(u["message_id"], carrier.NAME, u["verdict"], body_hash(u["content"]))
        if not d.show:
            continue
        classified.append({"rec": {"id": None, "seq": carrier.NAME, "sender": u.get("sender") or u["message_id"],
                                   "timestamp": u["ts"], "content": u["content"]},
                           "msg": msg, "isMine": True, "iw": {**u, "mid": u["message_id"]},
                           "flagged": d.flagged, "may_repeat": d.may_repeat})
        record(lock, d, u["message_id"], carrier.NAME, body_hash(u["content"]))
