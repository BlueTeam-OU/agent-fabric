"""tools/fabric/control/protocol.py — the control plane's four envelopes
(ADR-029): runtime/control/protocol.mjs in Python (ADR-040 Wave 8),
unwired until the cutover.

What ctl and presence send, what agentd accepts and answers with, what it
announces when it comes up, and what its account's sessions are doing.
They ride the relay's control channel as JSON; GZCoord never reads them.
The wire is frozen: these are Node's envelopes, key for key.

CONTRACT, frozen from protocol.mjs:
  ENVELOPE_KEYS               {kind: {"required": (...), "optional": (...)}},
                              protocol.mjs's lists, in its order
  Request, Reply, Up, State   the envelopes as typed dicts, for a reader;
                              tests/test_control_protocol.py holds their
                              keys to ENVELOPE_KEYS and ENVELOPE_KEYS to
                              Node's, so neither drifts

The typed dicts take the functional form because `from` is a Python
keyword, and each splits its optional keys into a total=False base
rather than NotRequired[...]: under `from __future__ import annotations`
a NotRequired annotation is never evaluated and the key silently counts
as required.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import TypedDict


def _kinds(required: tuple, optional: tuple) -> MappingProxyType:
    return MappingProxyType({"required": required, "optional": optional})


ENVELOPE_KEYS = MappingProxyType({
    "request": _kinds(("v", "kind", "id", "from", "to", "op", "ts"), ("ttl_s", "days", "args", "sig")),
    "reply": _kinds(("v", "kind", "id", "in_reply_to", "from", "op", "ts", "ok"), ("data",)),
    "up": _kinds(("v", "kind", "from", "ts"), ()),
    "state": _kinds(("v", "kind", "from", "ts", "sessions"), ("role", "project", "last_session", "resumable", "waits_on")),
})

# A request: an operator's (or, for a public op, a placed account's) ask.
# `to` is an address, a list of them, or "*" for every account; `op` one
# of agentd's OPS; `ts` ISO 8601 UTC. An action op is signed (`sig`,
# control/sign.py) and lives at most sign.ACTION_TTL_MAX_S.
_RequestOptional = TypedDict("_RequestOptional", {"ttl_s": float, "days": float, "args": dict, "sig": str}, total=False)
Request = TypedDict("Request", {"v": int, "kind": str, "id": str, "from": str, "to": object, "op": str, "ts": str})

# A reply: one account's answer to one request; a memory reply is
# followed by more replies, each carrying one part.
_ReplyOptional = TypedDict("_ReplyOptional", {"data": dict}, total=False)
Reply = TypedDict("Reply", {"v": int, "kind": str, "id": str, "in_reply_to": str, "from": str, "op": str, "ts": str,
                            "ok": bool})

# Up: what agentd posts once when it starts, so ctl can tell a restart.
Up = TypedDict("Up", {"v": int, "kind": str, "from": str, "ts": str})

# State: what an account's sessions are doing (sessions.mjs), posted when
# it changes and on a heartbeat (ADR-029 rule 16). `sessions` holds
# {"session", "state": working|blocked|idle, "since"} per live session,
# empty when none runs; `waits_on` the GZCoord ids the account's blocked
# jobs wait on (ADR-037 rule 8).
_StateOptional = TypedDict("_StateOptional", {"role": str, "project": str, "last_session": str, "resumable": bool,
                                              "waits_on": list}, total=False)
State = TypedDict("State", {"v": int, "kind": str, "from": str, "ts": str, "sessions": list})

# Each kind's typed dicts, the required keys' and the optional keys', for
# the test that holds them to ENVELOPE_KEYS.
TYPES = MappingProxyType({"request": (Request, _RequestOptional), "reply": (Reply, _ReplyOptional),
                          "up": (Up, None), "state": (State, _StateOptional)})
