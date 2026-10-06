"""tools/fabric/gzcoord/inbox_parts/records.py — the relay's records read: replay, history, retransmissions, keywords.
A part of tools/fabric/gzcoord/inbox.py, whose docstring is the contract."""
from __future__ import annotations

import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable
from .. import gzmsg
from .. import i18n
from .. import jsvalues as js
from ..gzmsg import en
from .tokens import for_me
from .relay import api


def _records(page: Any) -> Any:
    """page.messages ?? page — the relay's page, or a bare list."""
    if isinstance(page, dict) and not js.nullish(page.get("messages", js.UNDEFINED)):
        return page["messages"]
    return page


def _when(rec: dict) -> Any:
    return js.coalesce(js.get(rec, "timestamp"), js.get(rec, "ts"), "")


def one_line(msg: dict, t: i18n.Printer | None = None) -> str:
    """The addressing half is the WIRE's vocabulary — TO, TO-ROLE,
    broadcast, the type — matched by name across locales and never
    translated; only the missing-id placeholder is."""
    t = t or en()
    m = msg["metadata"]
    to = f"TO {m['TO']}" if m.get("TO") else f"TO-ROLE {m['TO-ROLE']}" if m.get("TO-ROLE") else "broadcast"
    line = f"{m['MESSAGE-ID'] if 'MESSAGE-ID' in m else t('inbox.no-id')}  {msg['type']}  {to}  {m.get('SUBJECT', '')}"
    return re.sub(f"[{js.JS_SPACE}]+$", "", line)


def _parse_quiet(text: Any) -> dict | None:
    try:
        return gzmsg.parse(gzmsg.normalize(text))
    except (gzmsg.NotGzcoord, AttributeError, TypeError):
        return None


def replay(tok: str, relay_url: str, channel: str, which: str, me: dict, t: i18n.Printer | None = None,
           as_json: bool = False) -> int:
    """Re-read one message already past this session's cursor — the case a
    read was piped through something that dropped the body. The recent
    history, no consumer id, so no cursor moves; the body only when it is
    addressed here: SPEC §17 does not stop applying because it is a replay.
    By relay seq, or by the MESSAGE-ID inside the body (the relay's own id
    is a transport detail nobody quotes)."""
    t = t or en()
    page = api(tok, "/api/messages?" + urllib.parse.urlencode({"channel": channel, "limit": "500", "full": "1"}),
               relay_url)
    lst = _records(page)

    def mid_of(r: dict) -> Any:
        m = _parse_quiet(r.get("content"))
        return m["metadata"].get("MESSAGE-ID") if m else None

    rec = next((r for r in lst if js.string(js.get(r, "seq")) == js.string(which) or r.get("id") == which
                or mid_of(r) == which), None)
    if rec is None:
        print(t("replay.no-message", {"which": which, "n": len(lst), "channel": channel}), file=sys.stderr)
        return 1
    text = gzmsg.normalize(rec["content"])
    when = _when(rec)
    try:
        msg = gzmsg.parse(text)
    except gzmsg.NotGzcoord:
        msg = None
    if as_json:
        addressed = bool(msg and for_me(msg, me))
        print(js.stringify({"addressed": addressed, "seq": rec.get("seq"), "sender": rec.get("sender"), "when": when,
                            "type": msg["type"], "metadata": msg["metadata"], "text": text}
                           if addressed else {"addressed": addressed, "seq": rec.get("seq")}))
        return 0 if addressed else 2
    if not msg or not for_me(msg, me):
        print(t("replay.not-addressed", {"seq": js.get(rec, "seq"), "sender": js.get(rec, "sender"), "when": when,
                                         "address": me["address"]}))
        if msg:
            print(f"  {one_line(msg, t)}")
        return 2
    print(t("replay.title", {"seq": js.get(rec, "seq"), "sender": js.get(rec, "sender"), "when": when}))
    print("```text")
    print(text[:-1] if text.endswith("\n") else text)
    print("```")
    return 0


# The relay pages forward from a message it holds (since_id) and never
# backward, so what can be listed is its newest page — the same window
# --replay reads.
HISTORY_WINDOW = 500


def history(tok: str, relay_url: str, channel: str, from_seq: float | None, me: dict,
            t: i18n.Printer | None = None) -> int:
    t = t or en()
    page = api(tok, "/api/messages?" + urllib.parse.urlencode(
        {"channel": channel, "limit": str(HISTORY_WINDOW), "full": "1"}), relay_url)
    lst = _records(page)
    lines = []
    for rec in lst:
        if from_seq is not None and js.number(js.get(rec, "seq")) < from_seq:
            continue
        msg = _parse_quiet(rec.get("content"))
        if msg is None or not for_me(msg, me):
            continue
        lines.append(f"  {js.string(js.get(rec, 'seq'))}  {js.string(_when(rec))}  {js.string(js.get(rec, 'sender'))}"
                     f"  {one_line(msg, t)}")
    first = js.coalesce(js.get(lst[0], "seq") if lst else js.UNDEFINED, "-")
    print(t("history.head", {"n": len(lines), "window": len(lst), "first": first, "channel": channel,
                             "address": me["address"]}))
    for line in lines:
        print(line)
    if lines:
        print(t("history.replay-hint", {"cmd": REPLAY_CMD}))
    return 0


# SPEC §7.2: a retransmission keeps its MESSAGE-ID, and a recipient holding
# both copies discards one. The watch cannot know what this session read,
# so it shows the copy — the first may have been cut or scrolled past —
# marked with the seq of the earlier one (same FROM, same MESSAGE-ID, a
# lower seq in the recent history). Best effort and bounded: the records
# are already acknowledged, and a relay that hangs must not hold back — or,
# if the session ends meanwhile, lose — a delivery the cursor has passed
# (#57 blind review F2).
RETRANSMISSION_LOOKUP_MS = 2000


def mark_retransmissions(classified: list[dict], fetch_recent: Callable[[threading.Event], Any],
                         timeout_ms: int = RETRANSMISSION_LOOKUP_MS) -> None:
    mine = [c for c in classified if c["isMine"] and c.get("msg") and c["msg"]["metadata"].get("MESSAGE-ID")]
    if not mine:
        return
    done = threading.Event()
    box: dict = {}

    def lookup() -> None:
        try:
            box["page"] = fetch_recent(done)
        except BaseException as e:  # noqa: BLE001 — a lookup that fails marks nothing
            box["error"] = e

    worker = threading.Thread(target=lookup, daemon=True)
    worker.start()
    worker.join(timeout_ms / 1000)
    done.set()
    if worker.is_alive() or "page" not in box:
        return
    page = box["page"]
    lst = page["messages"] if isinstance(page, dict) and isinstance(page.get("messages"), list) else \
        page if isinstance(page, list) else []
    first: dict[str, Any] = {}
    for rec in lst:
        m = _parse_quiet(rec.get("content") if isinstance(rec, dict) else None)
        if m is None:
            continue
        key = f"{js.string(js.get(m['metadata'], 'FROM'))}|{js.string(js.get(m['metadata'], 'MESSAGE-ID'))}"
        if key not in first or js.number(js.get(rec, "seq")) < js.number(first[key]):
            first[key] = js.get(rec, "seq")
    for c in mine:
        meta = c["msg"]["metadata"]
        seq = first.get(f"{js.string(js.get(meta, 'FROM'))}|{js.string(js.get(meta, 'MESSAGE-ID'))}", js.UNDEFINED)
        if seq is not js.UNDEFINED and js.number(seq) < js.number(js.get(c["rec"], "seq")):
            c["retransmitOf"] = seq


# Alert keywords: reasons to stop waiting on a message NOT addressed to this
# session. Whole-token, case-insensitive, over the full text (metadata and
# body — PR numbers live in REFERENCES). 3+ characters (shorter fires on
# nearly everything), at most 8 per arm, and a message from this session's
# own address never counts: a session must not wake on its own echo.
KEYWORD_MIN = 3


KEYWORD_MAX = 8


class KeywordError(ValueError):
    pass


def check_keywords(keywords: list | None = None, t: i18n.Printer | None = None) -> list[str]:
    t = t or en()
    seen: list[str] = []
    for k in keywords or []:
        if not isinstance(k, str) or len(k) < KEYWORD_MIN:
            raise KeywordError(t("keyword.too-short", {"keyword": js.stringify(k), "min": KEYWORD_MIN}))
        if k in seen:
            continue
        if len(seen) >= KEYWORD_MAX:
            raise KeywordError(t("keyword.too-many", {"max": KEYWORD_MAX}))
        seen.append(k)
    return seen


_TOKEN_SPLIT = re.compile(r"[^a-z0-9_-]+")


def keyword_hit(text: str, keywords: list[str], own_address: str | None) -> bool:
    if not keywords or not text:
        return False
    tokens = {x for x in _TOKEN_SPLIT.split(text.lower()) if x}
    if own_address:
        # Each TOKEN of the own address goes: the address is never one
        # token, and a keyword naming another session's instance half must
        # still fire on that session's message.
        for x in _TOKEN_SPLIT.split(own_address.lower()):
            tokens.discard(x)
    return any(k.lower() in tokens for k in keywords)


# The name on PATH, never a path through an expansion: a session told to
# run it is not asked for approval (runtime/claude-code/commands.json).
REPLAY_CMD = "gzcoord-inbox --replay"
