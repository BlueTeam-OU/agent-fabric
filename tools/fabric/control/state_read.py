"""tools/fabric/control/state_read.py — the readers' side of the `state` op (state_record.py): each account's newest state
record asked of the account, where the relay's stored history is no longer there to read it from (agent-fabric
ADR-029 rule 16; cutover plan §2.5, row 2).

CONTRACT
  use_op(cfg, env, say)      whether the readers ask the op: cfg["control_carrier"] is the second carrier's name alone, or
                             FABRIC_STATE_READ is "op" (the override that exercises the op under any carrier, said on
                             stderr by `say` each time it decides). Any other FABRIC_STATE_READ value is refused
                             with RuntimeError, not read as "off": a misspelt override would silently leave the relay
                             in use. Under relay and dual without the override the readers read the relay as before.
  ask(addresses, ...)        {address: {"record": <the record as the account posted it>} | {"error": <why none>}},
                             one entry for every address asked, in the order given. An account that does not answer,
                             answers {"state": null}, answers for another address or with a record that is not a v1
                             state record from it is an "error": unknown, never an empty record. The staleness of a
                             record is the caller's, judged on the record's own `ts` as it is on the relay's records.
                             The caller's own address is read from its own file; asking itself through its
                             own socket would wait on the lock that holds the request being answered.
"""
from __future__ import annotations

import os
import re
import sys
import time
from typing import Any, Callable

if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from control import carrier_cfg, js, state_record  # noqa: E402

ENV_OVERRIDE = "FABRIC_STATE_READ"
ASK_WAIT_S = 10.0   # the whole fan-out, however many accounts: they answer at once or not within it
ASK_POLL_S = 0.5


def use_op(cfg: dict, env: dict | None = None, say: Callable[[str], None] | None = None) -> bool:
    env = os.environ if env is None else env
    say = say or (lambda m: print(m, file=sys.stderr))
    override = env.get(ENV_OVERRIDE)
    if override not in (None, "", "op"):
        raise RuntimeError(f"{ENV_OVERRIDE} is {override!r}; the only value it takes is 'op'")
    if override == "op":
        say(f"{ENV_OVERRIDE}=op: state records are asked of the accounts, not read from the relay"
            f" (control_carrier is {cfg.get('control_carrier')!r})")
        return True
    return not carrier_cfg.uses_relay(cfg)


def _open_leg(request: dict, to: list, wait_s: float):
    from gzcoord.carrier import control_link
    return control_link.Leg.open(request, to, wait_s)


def _accepted(address: str, sender: str, reply: dict) -> dict:
    """{"record"} or {"error"} for one reply from `sender`, which the carrier authenticated; the reply's own `from` and
    the address inside its data are claims and must agree with it."""
    if reply.get("kind") != "reply" or reply.get("op") != state_record.STATE_OP or reply.get("from") != address:
        return {"error": f"{address}'s answer is not a state reply"}
    if reply.get("ok") is not True:
        return {"error": f"{address} refused the state op"}
    data = reply.get("data")
    data = data.get(state_record.STATE_OP) if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("address") != address:
        return {"error": f"{address}'s answer does not say it is {address}'s"}
    rec = data.get("state")
    if rec is None:
        return {"error": f"{address} has no state record to give ({_quoted(data.get('why')) or 'no reason given'})"}
    return _record(address, rec)


def _quoted(why: Any) -> str:
    """A peer's own words, kept to what is safe to print: the reason reaches an operator's terminal, so an escape sequence
    (a window title, the clipboard) never does, and a long one is cut."""
    return re.sub("[\u0000-\u001f\u007f-\u009f]", "?", why if isinstance(why, str) else "")[:200]


def _record(address: str, rec: Any) -> dict:
    """{"record"} when `rec` has the shape every reader of it reads, else {"error"}: a record from the account's own file is held
    to it as one from a peer is."""
    if (not isinstance(rec, dict) or rec.get("kind") != "state" or not (js.is_integer(rec.get("v")) and rec["v"] == 1)
            or rec.get("from") != address or not isinstance(rec.get("ts"), str)):
        return {"error": f"{address}'s state record is not a v1 state record from it"}
    return {"record": rec}


def ask(addresses: list[str], *, me: str, own_file: str, new_id: Callable[[], str], open_leg: Callable = _open_leg,
        wait_s: float = ASK_WAIT_S, now: Callable[[], float] = time.monotonic) -> dict:
    out: dict[str, dict] = {}
    others = []
    for a in addresses:
        if a == me:
            try:
                rec = state_record.load(own_file)
            except state_record.StateRecordError as e:
                out[a] = {"error": str(e)}
                continue
            out[a] = _record(a, rec) if rec is not None else {"error": f"{a} has written no state record yet"}
        elif a not in others:
            others.append(a)
    if others:
        out.update(_fan_out(others, me=me, new_id=new_id, open_leg=open_leg, wait_s=wait_s, now=now))
    return {a: out[a] for a in addresses}


def _fan_out(others: list[str], *, me: str, new_id, open_leg, wait_s: float, now) -> dict:
    request = {"v": 1, "kind": "request", "id": new_id(), "from": me, "to": others, "op": state_record.STATE_OP,
               "ts": js.iso_now(), "ttl_s": max(1, int(wait_s) + 1)}
    try:
        leg = open_leg(request, others, wait_s)
    except RuntimeError as e:
        return {a: {"error": f"{a} was not asked: {e}"} for a in others}
    failed = leg.failed_sends if isinstance(getattr(leg, "failed_sends", None), dict) else {}
    answers: dict[str, dict] = {a: {"error": f"{a} was not asked: {why}"} for a, why in failed.items() if a in others}
    try:
        deadline = now() + wait_s
        while len(answers) < len(others) and not leg.lost and now() < deadline:
            for sender, reply in leg.replies(min(ASK_POLL_S, max(0.0, deadline - now()))):
                if sender in others and sender not in answers:
                    answers[sender] = _accepted(sender, sender, reply)
    finally:
        leg.close()
    return {a: answers.get(a) or {"error": f"{a} did not answer within {js.string(wait_s)} s"
                                  + (" (the connection to this account's agentd closed)" if leg.lost else "")}
            for a in others}


def asker(cfg: dict, *, me: str, own_file: str, new_id: Callable[[], str], env: dict | None = None,
          say: Callable[[str], None] | None = None, **inject: Any) -> Callable[[list], dict] | None:
    """`ask` bound to this account when the readers use the op (use_op), else None: the callers' one test of which way
    they read."""
    if not use_op(cfg, env, say):
        return None
    return lambda addresses: ask(addresses, me=me, own_file=own_file, new_id=new_id, **inject)
