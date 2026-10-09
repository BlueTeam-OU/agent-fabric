"""Parity cases for control/sign.py against runtime/control/sign.mjs (tests/control_parity.py)."""
import os
import sys
REQUEST = {"v": 1, "kind": "request", "id": "01a11a18-4728-7d8b-afd9-0edb2d30a59c", "from": "h/user", "to": ["h/py"], "op": "upgrade",
           "ts": "2026-10-09T02:00:00.000Z", "ttl_s": 300, "args": {"piece": "claude", "note": "\u00fc \u2713 \U0001F600", "n": 5,
                                                                  "f": 0.1, "big": 12345678901234567890, "lone": "\ud800"}}


def cases() -> list[dict]:
    """One key pair, made when the cases are built and handed to both sides:
    Ed25519 is deterministic, so the same key over the same request is the
    same signature. Made here, never committed."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "fabric"))
    from control import sign
    pair = sign.generate_operator_key()
    KEY, PUB = pair["privateKeySpec"], pair["publicKeySpec"]
    return [
    {"name": "canonical over keys, numbers and strings of every kind", "module": "sign",
     "input": [{"b": 1, "a": [2, {"y": 1, "x": 0}]}, [1e21, 1e-7, -0.0, 5.0, 0.1, 1.5e300], {"\U0001F600": 1, "\uffff": 2, "": 3},
               "\u0000\u001f\u007f\u2028\ud800", 9007199254740993],
     "node": "return input.map(v => m.canonical(v));", "py": "return [m.canonical(v) for v in input]"},
    {"name": "the same key signs a request into the same bytes", "module": "sign", "input": [REQUEST, KEY],
     "node": "return m.signRequest(input[0], input[1]);", "py": "return m.sign_request(input[0], input[1])"},
    {"name": "each side verifies what it signed (the same bytes on both, case above; across the languages: tests/test_control_sign.py)", "module": "sign", "input": [REQUEST, KEY, PUB],
     "node": "return m.verifyRequest(m.signRequest(input[0], input[1]), m.publicKeyFrom(input[2]));",
     "py": "return m.verify_request(m.sign_request(input[0], input[1]), m.public_key_from(input[2]))"},
    {"name": "a tampered request is refused on both sides", "module": "sign", "input": [REQUEST, KEY, PUB],
     "node": "const s = m.signRequest(input[0], input[1]); return m.verifyRequest({ ...s, to: '*' }, m.publicKeyFrom(input[2]));",
     "py": "s = m.sign_request(input[0], input[1])\nreturn m.verify_request({**s, 'to': '*'}, m.public_key_from(input[2]))"},
    {"name": "the constants", "module": "sign", "input": None,
     "node": "return [m.ACTION_OPS, m.ACTION_TTL_MAX_S, m.KEY_PREFIX, m.PRIVATE_PREFIX];",
     "py": "return [m.ACTION_OPS, m.ACTION_TTL_MAX_S, m.KEY_PREFIX, m.PRIVATE_PREFIX]"},
]
