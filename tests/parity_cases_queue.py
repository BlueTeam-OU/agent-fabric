"""Parity cases for control/queue.py against runtime/control/queue.mjs (tests/control_parity.py)."""
import json

A, B = "01a11a18-4728-7d8b-afd9-0edb2d30a59c", "01a11a19-0bea-70c7-b667-1e1e5a74dbe1"


def rec(sender, waits_on=None, **extra):
    return {"content": json.dumps({"v": 1, "kind": "state", "from": sender, "ts": "2026-10-08T12:00:00Z", "sessions": [],
                                   **({"waits_on": waits_on} if waits_on else {}), **extra})}


ROWS = [rec("h/py", [A, B]), rec("h/web", [B]), rec("h/py", [A]), rec("h/web", ["not-an-id"]), rec("x/unplaced", [B]), {"content": "{broken"},
        rec("h/old", [A], ts="2026-10-08T11:00:00Z"), rec("h/bad", [B], ts="yesterday"), rec("h/py", [A], kind="reply")]
CASES = [
    {"name": "waits_from: the newest record of each placed account, stale ones named", "module": "queue",
     "input": {"rows": ROWS, "placed": ["h/py", "h/web", "h/old", "h/bad"]},
     "node": "return m.waitsFrom(input.rows, new Set(input.placed), Date.parse('2026-10-08T12:05:00Z'));",
     "py": "return m.waits_from(input['rows'], set(input['placed']), 1791461100000)"},
    {"name": "who is placed, from the fixture's registry", "module": "queue", "input": None,
     "node": "return [...m.placedAccounts(home.registry)].sort();", "py": "return sorted(m.placed_accounts(home['registry']))"},
    {"name": "unsent and relay_error on the failures a call can end in", "module": "queue", "input": None,
     "node": "const c = { relay_url: 'http://r' }; return [m.unsent({ status: 403 }), m.unsent({ status: 502 }), m.unsent({ cause: { code: 'ECONNREFUSED' } }),"
             " m.relayError({ timedOut: true, message: '/x -> no answer within 30 s' }, c), m.relayError({ status: 401 }, c), m.relayError(new Error('x'), c)];",
     "py": "from control.gzcoord import ApiError\nc = {'relay_url': 'http://r'}\nreturn [m.unsent(ApiError('x', status=403)), m.unsent(ApiError('x', status=502)),"
           " m.unsent(ApiError('x', connection_refused=True)), m.relay_error(ApiError('/x -> no answer within 30 s', timed_out=True), c),"
           " m.relay_error(ApiError('x', status=401), c), m.relay_error(ValueError('x'), c)]"},
]
