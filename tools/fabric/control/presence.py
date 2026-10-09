"""tools/fabric/control/presence.py — whether accounts have a session, asked
of their control agents (the `presence` op) by any placed account:
runtime/control/presence.mjs in Python (ADR-040 Wave 8), unwired until
the cutover.

The sender's check before a message leaves is the caller: a message to a
login with no session waits in the relay until one starts, and the
sender decides whether that is what it wants (the owner, 2026-09-25).
The answer is the process table, not a claim a session made about
itself: a crash, or a launch that never reached the harness, is never
"present".

CONTRACT, frozen from presence.mjs:
  PRESENCE_WAIT_MS   GZCOORD_PRESENCE_WAIT_MS when a number above zero
                     (read as Number()), else 6000
  ask_presence(...)  {address: presence | None} for every address
                     expected; None is a control agent that did not
                     answer within wait_ms — unknown, never "offline"
  check_addressees(metadata, ...)
                     {checked, problems, notes}, as checkAddressees
  exit_code_of(answer)  0 checked, no problem; 4 a definite problem;
                     5 an addressee that did not answer; 6 unavailable
  cli(argv, stdin)   `presence.py check`: the request as one JSON object
                     on stdin {"metadata", "from", "token"} — the token
                     never in argv; stdout one JSON object (the answer,
                     or {"error", "status"}); exit as exit_code_of, or 2
                     for usage or unreadable stdin

The control plane's own pieces this reads — the channel's config, the
placed and operator addresses, a new id — are agentd's (control_config,
account_addresses, operator_addresses, new_id), taken as parameters and
imported only by the CLI.

Requests, pages and replies are read as JavaScript read them, since a
Node sender and a Python one must check alike: the query as
URLSearchParams encodes it, stdin as JSON.parse takes it (no NaN), a
property of a value that is not an object as undefined, `??` as null
only, a template's value as String() writes it.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from control import gzcoord, js  # noqa: E402

_env_wait = js.number(os.environ["GZCOORD_PRESENCE_WAIT_MS"]) if "GZCOORD_PRESENCE_WAIT_MS" in os.environ else math.nan
# How long a sender waits for an answer: a control agent answers within a
# second; the rest is the relay's poll. GZCOORD_PRESENCE_WAIT_MS shortens
# it for a suite's silent-agent case.
PRESENCE_WAIT_MS = _env_wait if _env_wait > 0 else 6000
POLL_S = 0.4

_UNDEFINED = object()   # JavaScript's undefined: what a missing property reads as


def prop(value, key):
    """value[key] as JavaScript reads it on parsed JSON: an object's own
    key, else undefined (None for a caller that needs no difference)."""
    return value.get(key) if isinstance(value, dict) else None


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def ask_presence(*, from_: str, to, expect: list, token: str | None = None, wait_ms: float = PRESENCE_WAIT_MS,
                 cfg: dict, new_id, call=None, sleep=time.sleep, clock=time.monotonic) -> dict:
    """`to` is one address, a list, or "*" (a TO-ROLE is resolved by the
    caller from the roles in the answers)."""
    def default_call(path, method="GET", body=None):
        return gzcoord.api(token, path, relay_url=cfg["relay_url"], method=method, body=body)
    c = call or default_call
    rid = new_id()
    request = {"v": 1, "kind": "request", "id": rid, "from": from_, "to": to, "op": "presence", "ts": js.iso_now(),
               "ttl_s": max(cfg["ttl_s"], math.ceil(wait_ms / 1000))}
    sent = c("/api/send", method="POST",
             body=_compact({"channel": cfg["channel"], "sender": from_, "content": _compact(request)}))
    out = {a: None for a in expect}
    want = set(expect)
    deadline = clock() + wait_ms / 1000
    # A sent record with no id pages from "undefined", as URLSearchParams wrote it.
    since = sent["id"] if isinstance(sent, dict) and "id" in sent else "undefined"
    while want and clock() < deadline:
        page = c("/api/messages?" + js.search_params({"channel": cfg["channel"], "since_id": since, "limit": "500", "full": "1"}))
        if page is None:
            raise TypeError("Cannot read properties of null (reading 'messages')")
        messages = prop(page, "messages")
        for rec in messages if isinstance(messages, list) else []:
            since = rec.get("id") if isinstance(rec, dict) and "id" in rec else "undefined"
            try:
                r = js.json_parse(prop(rec, "content")) if isinstance(prop(rec, "content"), str) else None
            except ValueError:
                continue
            presence = prop(prop(r, "data"), "presence")
            sender = prop(r, "from")
            if (prop(r, "kind") == "reply" and prop(r, "in_reply_to") == rid and isinstance(sender, str) and sender in want
                    and js.truthy(presence)):
                out[sender] = presence
                want.discard(sender)
        if want:
            sleep(POLL_S)
    return out


def check_addressees(metadata, *, from_: str, token: str | None, placed: list, operators: list = (), ask=ask_presence,
                     wait_ms: float = PRESENCE_WAIT_MS, **ask_kw) -> dict:
    """Who a message is for, and which of them has no session now. TO: that
    one address. TO-ROLE: every placed account whose binding holds the
    role — reached if ANY of them is running, since the role is addressed,
    not an instance. BROADCAST, or no addressing field at all: no check;
    everyone is not a set that can be offline."""
    to, to_role = prop(metadata, "TO"), prop(metadata, "TO-ROLE")
    if js.truthy(prop(metadata, "BROADCAST")) or (not js.truthy(to) and not js.truthy(to_role)):
        return {"checked": False}
    if js.truthy(to):
        a = js.trim(to)
        if a not in placed and a not in operators:
            return {"checked": True, "problems": [{"kind": "not-placed", "address": a}]}
        p = ask(from_=from_, to=[a], expect=[a], token=token, wait_ms=wait_ms, **ask_kw)[a]
        # A reply that could not read the process table is unknown, never
        # "no session" (review of #38).
        if p is None:
            return {"checked": True, "problems": [{"kind": "silent", "address": a}]}
        if prop(p, "status") != "ok":
            err = prop(p, "error")
            return {"checked": True, "problems": [{"kind": "unavailable",
                                                   "detail": f"{a}: {js.string(prop(p, 'status') if err is None else err)}"}]}
        # Planning is said, never a refusal: the message waits in the relay
        # for the approved plan, which is what it would do anyway.
        online = js.truthy(prop(p, "online"))
        return {"checked": True, "problems": [] if online else [{"kind": "offline", "address": a, "presence": p}],
                "notes": [{"kind": "planning", "address": a}] if online and js.truthy(prop(p, "planning")) else []}
    role = js.trim(to_role)
    every = ask(from_=from_, to="*", expect=list(placed), token=token, wait_ms=wait_ms, **ask_kw)
    holders = [(a, p) for a, p in every.items() if prop(p, "status") == "ok" and prop(p, "role") == role]
    online = [(a, p) for a, p in holders if js.truthy(prop(p, "online"))]
    # A role is planning only when every running holder is: one that is
    # not will read the message now — and an account that did not answer
    # may be such a holder, so any silence withholds the note.
    unknown = any(p is None or prop(p, "status") != "ok" for p in every.values())
    if online:
        return {"checked": True, "problems": [],
                "notes": [{"kind": "planning", "address": a} for a, _ in online]
                if not unknown and all(js.truthy(prop(p, "planning")) for _, p in online) else []}
    # No answer, or an answer that could not read its process table: either
    # may hide a running holder, and both are said as such.
    silent = [a for a, p in every.items() if p is None or prop(p, "status") != "ok"]
    return {"checked": True, "problems": [{"kind": "no-holder", "role": role, "holders": [a for a, _ in holders], "silent": silent}]}


def exit_code_of(answer: dict) -> int:
    if "error" in answer:
        return 6
    kinds = ["silent" if p.get("kind") == "no-holder" and p.get("silent") else p.get("kind") for p in answer.get("problems") or []]
    if "unavailable" in kinds:
        return 6
    if "silent" in kinds:
        return 5
    return 4 if kinds else 0


def cli(argv: list[str] | None = None, stdin=None, ask=check_addressees, agentd=None, out=sys.stdout, err=sys.stderr) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["check"]:
        print("usage: presence.py check   (the request as JSON on stdin)", file=err)
        return 2
    # Never the parser's message: it quotes the input, and the input carries the token.
    try:
        req = js.json_parse((stdin or sys.stdin).read())
    except (ValueError, UnicodeDecodeError):
        print("presence: stdin is not one JSON object", file=err)
        return 2
    if (not isinstance(req, dict) or not isinstance(req.get("metadata"), (dict, list)) or not isinstance(req.get("from"), str)
            or not isinstance(req.get("token"), str)):
        print('presence: stdin needs {"metadata": {...}, "from": "<host>/<login>", "token": "<relay token>"}', file=err)
        return 2
    if agentd is None:
        from control import agentd   # agentd's port: control_config, account_addresses, operator_addresses, new_id
    try:
        answer = ask(req["metadata"], from_=req["from"], token=req["token"], placed=list(agentd.account_addresses()),
                     operators=list(agentd.operator_addresses()), cfg=agentd.control_config(), new_id=agentd.new_id)
    except Exception as e:  # noqa: BLE001 — presence.mjs's catch: every failure is one {"error"} line, exit 6
        status = getattr(e, "status", None)
        answer = {"error": js.slice(str(e).split("\n")[0], 160), "status": status if isinstance(status, int) and status is not True and status is not False else None}
    print(_compact(answer), file=out)
    return exit_code_of(answer)


def main() -> int:
    try:
        return cli()
    except Exception as e:  # noqa: BLE001 — presence.mjs's last catch: still one JSON line, exit 6
        print(_compact({"error": f"presence: {e}", "status": None}))
        return 6


if __name__ == "__main__":
    sys.exit(main())
