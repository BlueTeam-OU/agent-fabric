"""tools/fabric/gzcoord/inbox_parts/watch.py — the wait for what is addressed here, and the bypass of the journal.
A part of tools/fabric/gzcoord/inbox.py, whose docstring is the contract."""
from __future__ import annotations

import math
import threading
import time
from typing import Any, Callable
from .. import bypass
from .. import gzmsg
from .. import jsvalues as js
from .records import keyword_hit
from .hold import HOLD_POLL_MS


# THE JOURNAL (ADR-041 rule 4): the messages addressed to this session are
# kept in its journal before the page is acknowledged, so a message is
# never let go by the carrier and then lost between here and the session.
# If the journal cannot take them they are neither acknowledged nor shown:
# the carrier shows them again, after JOURNAL_RETRY_MS so a broken journal
# does not spin. Others' traffic is acknowledged as before, never journaled.
JOURNAL_RETRY_MS = 30000


def bypass_inbound(records: list[dict]) -> dict:
    """GZCOORD_JOURNAL=off, in journal_inbound's place: no journal row, but a
    line per record in journal-bypass.jsonl before any is shown or
    acknowledged, and one warning for the page. A line that cannot be
    written holds the page as a journal that cannot keep it does."""
    try:
        bypass.record([bypass.entry("in", r.get("content") if isinstance(r.get("content"), str) else "",
                                    js.get(r, "seq")) for r in records])
    except bypass.BypassUnrecorded as e:
        return {"ok": False, "reason": str(e)}
    print(f"gzcoord: GZCOORD_JOURNAL=off — {len(records)} message(s) addressed to you are shown without being kept"
          " in your journal (ADR-041)", flush=True)
    return {"ok": True, "said": []}


# ── the wait ─────────────────────────────────────────────────────────

def wait_loop(fetch_page: Callable[[int, threading.Event], Any], ack: Callable[[Any], Any], wait_total: float,
              for_me_fn: Callable[[dict], bool] | None = None, keywords: list[str] | None = None,
              own_address: str | None = None, held: Callable[[], bool] = lambda: False,
              on_hold: Callable[[bool], None] = lambda h: None, hold_poll_ms: int = HOLD_POLL_MS,
              sleep: Callable[[float], None] = lambda ms: time.sleep(ms / 1000),
              journal: Callable[[list[dict]], dict] | None = None,
              on_journal_fail: Callable[[str, int], None] = lambda reason, n: None,
              journal_retry_ms: int = JOURNAL_RETRY_MS) -> dict:
    """One arm of the waiter. `delivered` iff some slice carried a message
    for this session. Every slice's messages are acknowledged before the
    loop continues or returns — an acknowledgement means "shown this
    position", not "read the body". `held` is consulted before every slice,
    once a poll interval during one, and once more when it returns: a hold
    that begins mid-slice abandons the fetch, a page that landed with the
    hold is dropped unread (nothing acknowledged, the relay re-shows it),
    and the loop polls nothing until the hold clears. A retired HELLO or
    GOODBYE (SPEC §8) an old session still sends is acknowledged and never
    delivered, not even listed: presence is the control plane's to answer
    (ADR-030), and on a busy day the announcements were most of what every
    watch printed (the owner, 2026-09-25)."""
    for_me_fn = for_me_fn or (lambda msg: False)
    keywords = keywords or []
    waited = 0.0
    hit = None
    was_held = False
    while True:
        if held():
            if not was_held:
                on_hold(True)
                was_held = True
            sleep(hold_poll_ms)
            continue
        if was_held:
            on_hold(False)
            was_held = False
        slice_ = 1 if wait_total == 0 else min(55, max(1, wait_total - waited))
        abort = threading.Event()
        box: dict = {}

        def fetch() -> None:
            try:
                box["page"] = fetch_page(slice_, abort)
            except BaseException as e:  # noqa: BLE001 — carried to the waiting side
                box["error"] = e

        worker = threading.Thread(target=fetch, daemon=True)
        worker.start()
        while True:
            worker.join(hold_poll_ms / 1000)
            if not worker.is_alive():
                break
            if held():
                abort.set()   # the slice is abandoned: nothing read is acknowledged
                break
        if abort.is_set():
            page = {"messages": []}
        elif "error" in box:
            abort.set()
            raise box["error"]
        else:
            page = box["page"]
        abort.set()
        if held():
            page = {"messages": []}   # landed as the hold began: unread, unacknowledged, re-shown later
        waited += slice_
        classified, retired = [], []
        delivered = False
        for rec in (page.get("messages") if isinstance(page, dict) else None) or []:
            try:
                msg = gzmsg.parse(rec["content"])
            except (gzmsg.NotGzcoord, AttributeError, TypeError, KeyError):
                msg = None   # not GZCOORD/1: never addressed
            if msg and msg["type"] in gzmsg.RETIRED_TYPES:
                retired.append(rec)
                continue
            is_mine = bool(for_me_fn(msg)) if msg else False
            classified.append({"rec": rec, "msg": msg, "isMine": is_mine})
            delivered = delivered or is_mine
        mine = [c for c in classified if c["isMine"]]
        if journal and mine:
            kept = journal([c["rec"] for c in mine])
            if not kept.get("ok"):
                # Held: not shown, not acknowledged — only if nothing after
                # them is acknowledged either. The relay keeps one cursor per
                # consumer and an acknowledgement moves it to that record's
                # seq, so acknowledging a later record would pass the held
                # one for good (review of #78). What precedes the first held
                # record is acknowledged; a seq that cannot be compared
                # acknowledges none.
                on_journal_fail(kept.get("reason"), len(mine))
                seqs = [js.number(js.get(c["rec"], "seq")) for c in mine]
                first_held = math.nan if any(math.isnan(s) for s in seqs) else min(seqs)

                def before(rec: dict) -> bool:
                    return math.isfinite(first_held) and js.number(js.get(rec, "seq")) < first_held

                passed = [c for c in classified if not c["isMine"] and before(c["rec"])]
                for rec in [*[r for r in retired if before(r)], *[c["rec"] for c in passed]]:
                    try:
                        ack(rec.get("id"))
                    except Exception:  # noqa: BLE001 — re-read on the next arm
                        pass
                # Acknowledged now, so never read again: a keyword among them
                # is the exit reason here or nowhere (review of #78).
                passed_hit = next((c["rec"] for c in passed
                                   if c["msg"] and keyword_hit(c["rec"].get("content"), keywords, own_address)), None)
                def held_result(hit: Any = None) -> dict:
                    # Built at each return: `waited` is the count when it returns.
                    return {"classified": passed, "waited": waited, "delivered": False, "keywordHit": hit,
                            "othersPassed": len(passed), "journalFailed": kept.get("reason")}
                if passed_hit:
                    return held_result(passed_hit)
                # A bounded wait ends within its budget, the hold said; the
                # watch retries until the journal takes them.
                if wait_total == 0 or waited >= wait_total:
                    return held_result()
                pause = min(journal_retry_ms, (wait_total - waited) * 1000)
                sleep(pause)
                waited += math.ceil(pause / 1000)
                if waited >= wait_total:
                    return held_result()
                continue
        for rec in retired:
            try:
                ack(rec.get("id"))
            except Exception:  # noqa: BLE001 — re-read on the next arm
                pass
        for c in classified:
            try:
                ack(c["rec"].get("id"))
            except Exception:  # noqa: BLE001 — the next arm re-shows it
                pass
        # A keyword hit stops the wait on a message NOT addressed here; a
        # delivered message wins the exit; a message from this session's own
        # address never hits.
        if not delivered and not hit:
            for c in classified:
                if not c["isMine"] and c["msg"] and keyword_hit(c["rec"].get("content"), keywords, own_address):
                    hit = c["rec"]
                    break
        if delivered or hit or wait_total == 0 or waited >= wait_total:
            return {"classified": classified, "waited": waited, "delivered": delivered, "keywordHit": hit,
                    "othersPassed": len([c for c in classified if not c["isMine"]])}
        # Nothing for this session, no keyword hit: the cursor is past the
        # slice, and the remaining budget keeps waiting.
