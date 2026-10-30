"""tools/fabric/control/hold.py — `hold` and `unhold`, the fleet hold's signed
actions (agent-fabric ADR-037 rule 13, ADR-029).

`hold` writes this login's hold.json, `unhold` removes it, both through
runtime/identity.py (set_hold, clear_hold) as the login the control agent
runs as. The record names the operator who signed the action (`from`), never
a field the request chose. Unlike jobs-add they may name `all`: a hold is
fleet-wide by purpose, and fabric-ctl names every account that did not answer.

CONTRACT
  hold(request)    args {"reason": one line of 1..HOLD_REASON_MAX characters,
                   "decision": optional MESSAGE-ID}, no other key. Answers
                   {"status": "held", "hold": <record>} or {"status":
                   "refused", "reason"}; a second hold restates the first.
  unhold(request)  no args. {"status": "released"} when a hold was removed,
                   {"status": "none"} when the login was not held. A hold.json
                   that cannot be read is removed all the same: unhold is how
                   a corrupt one is lifted.
"""
from __future__ import annotations

import os
import sys

if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import importlib.util  # noqa: E402

from control import js  # noqa: E402
import roots  # noqa: E402

_identity = None


def identity_module():
    """runtime/identity.py of the checkout this code runs from, loaded by path as the job tool loads it (gzcoord's `identity` is a function)."""
    global _identity
    if _identity is None:
        spec = importlib.util.spec_from_file_location("fabric_identity", os.path.join(roots.code_root(), "runtime", "identity.py"))
        _identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_identity)
    return _identity


def check_args(args) -> str | None:
    if not isinstance(args, dict):
        return "hold takes { reason, decision }"
    extra = [k for k in js.keys(args) if k not in ("reason", "decision")]
    if extra:
        return f"hold takes only reason and decision, not {', '.join(extra)}"
    if not isinstance(args.get("reason"), str):
        return "hold takes a reason: one line"
    if "decision" in args and not isinstance(args["decision"], str):
        return "decision is a MESSAGE-ID"
    return None


def check_hold(reason, decision) -> str | None:
    """Why fabric-ctl refuses these before anything is sent: identity.set_hold's own rule, so the two cannot differ."""
    identity = identity_module()
    if not isinstance(reason, str) or not reason.strip() or "\n" in reason or "\r" in reason or len(reason) > identity.HOLD_REASON_MAX:
        return f"the reason is one non-empty line of at most {identity.HOLD_REASON_MAX} characters"
    if decision is not None and not identity.HOLD_DECISION.fullmatch(decision):
        return "the decision is a MESSAGE-ID (a lowercase UUID)"
    return None


def hold(request: dict, identity=None, **_: object) -> dict:
    identity = identity or identity_module()
    args = request.get("args")
    bad = check_args(args)
    if bad:
        return {"status": "refused", "reason": bad}
    sender = request.get("from")
    if not isinstance(sender, str) or not sender:
        return {"status": "refused", "reason": "the request does not say who signed it"}
    try:
        record = identity.set_hold(args["reason"], set_by=sender, decision=args.get("decision"))
    except ValueError as e:
        return {"status": "refused", "reason": str(e)}
    except (OSError, SystemExit) as e:
        return {"status": "failed", "reason": f"hold.json was not written: {getattr(e, 'strerror', None) or e}"}
    return {"status": "held", "hold": record}


def unhold(request: dict, identity=None, **_: object) -> dict:
    identity = identity or identity_module()
    args = request.get("args")
    if args not in (None, {}):
        return {"status": "refused", "reason": "unhold takes no arguments"}
    try:
        removed = identity.clear_hold()
    except (OSError, SystemExit) as e:
        return {"status": "failed", "reason": f"hold.json was not removed: {getattr(e, 'strerror', None) or e}"}
    return {"status": "released" if removed else "none"}
