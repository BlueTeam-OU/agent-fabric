#!/usr/bin/env python3
"""Tests for tools/fabric/control/sign.py, the port of runtime/control/sign.mjs.

The first block is runtime/control/tests/sign.test.mjs's own test (its
"canonical: …" case), case for case; its other four test agentd.mjs's
accept and ledger and move with agentd. The rest holds the port to the
wire: the signed bytes against Node's canonical() on the same JSON, the
number layout against Node's on random doubles, a Node signature
verified here and one made here verified by Node, and openssl's
failures kept apart from a verdict. Node is the oracle: without it the
parity cases fail, they are never skipped.
"""
from __future__ import annotations

import base64
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from control import sign  # noqa: E402

SIGN_MJS = os.path.join(HERE, "runtime", "control", "sign.mjs")


def node(js: str, data) -> object:
    """Node's answer, as JSON, to `js` run with `data` (JSON) on stdin as `input`."""
    script = ("const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
              f"import('{SIGN_MJS}').then(sign => {{ const out = (() => {{ {js} }})(); "
              "process.stdout.write(JSON.stringify(out)); });")
    r = subprocess.run(["node", "-e", script], input=json.dumps(data), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"node failed: {r.stderr.strip()[:400]}")
    return json.loads(r.stdout)


def base(**over) -> dict:
    r = {"v": 1, "kind": "request", "id": "id-1", "from": "h/user", "to": "h/db-admin", "op": "upgrade",
         "args": {"piece": "claude"}, "ts": "2026-10-09T02:00:00.000Z", "ttl_s": 300}
    r.update(over)
    return r


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    print("sign.test.mjs: canonical, and the signature over every field but sig")
    check("key order at every depth does not matter",
          sign.canonical({"b": 1, "a": {"d": [2, {"y": 1, "x": 0}], "c": "z"}}) == '{"a":{"c":"z","d":[2,{"x":0,"y":1}]},"b":1}')
    k = sign.generate_operator_key()
    pub = sign.public_key_from(k["publicKeySpec"])
    signed = sign.sign_request(base(id="x"), k["privateKeySpec"])
    reordered = dict(reversed(list(signed.items())))
    check("a re-serialisation that reorders keys still verifies", sign.verify_request(reordered, pub) is True)
    for field, value in (("to", "*"), ("ts", "2030-01-01T00:00:00Z"), ("op", "status"),
                         ("args", {"piece": "claude", "version": "0.0.1"}), ("from", "h/other")):
        check(f"changing {field} breaks the signature", sign.verify_request({**signed, field: value}, pub) is False)
    other = sign.public_key_from(sign.generate_operator_key()["publicKeySpec"])
    check("another key does not verify it", sign.verify_request(signed, other) is False)
    check("a signature that is not one does not verify", sign.verify_request({**signed, "sig": "bm90IGEgc2ln"}, pub) is False)
    check("only the one-line form is a key", sign.private_key_from("-----BEGIN PRIVATE KEY-----") is None)
    check("a public key that is not base64 DER is none", sign.public_key_from("ed25519:not-base64-der") is None)
    check("both halves fit one line of secrets.env and of JSON",
          "\n" not in k["privateKeySpec"] and "\n" not in k["publicKeySpec"])

    print("the rest of the contract")
    check("ACTION_OPS, the ttl cap and the prefixes are Node's",
          node("return [sign.ACTION_OPS, sign.ACTION_TTL_MAX_S, sign.KEY_PREFIX, sign.PRIVATE_PREFIX];", None)
          == [sign.ACTION_OPS, sign.ACTION_TTL_MAX_S, sign.KEY_PREFIX, sign.PRIVATE_PREFIX])
    check("a public key is not a private one, nor the other way",
          sign.private_key_from("ed25519-pkcs8:" + k["publicKeySpec"].split(":", 1)[1]) is None
          and sign.public_key_from("ed25519:" + k["privateKeySpec"].split(":", 1)[1]) is None)
    ec = subprocess.run(["openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-outform", "DER"],
                        capture_output=True, timeout=30, check=True).stdout
    ec_pub = subprocess.run(["openssl", "pkey", "-inform", "DER", "-pubout", "-outform", "DER"], input=ec,
                            capture_output=True, timeout=30, check=True).stdout
    check("a key openssl reads but not Ed25519 is no key here (a P-256 pair)",
          sign.private_key_from("ed25519-pkcs8:" + base64.b64encode(ec).decode()) is None
          and sign.public_key_from("ed25519:" + base64.b64encode(ec_pub).decode()) is None)
    check("no key, no verdict but False", sign.verify_request(signed, None) is False and sign.verify_request(signed, b"") is False)
    check("no sig, an empty one, or one that is not a string: False",
          all(sign.verify_request({**signed, "sig": s}, pub) is False for s in ("", None, 5))
          and sign.verify_request({k2: v for k2, v in signed.items() if k2 != "sig"}, pub) is False)
    check("a request that is not an object: False", sign.verify_request("x", pub) is False)
    try:
        sign.sign_request(base(), "ed25519-pkcs8:####")
        check("signing with no key is refused", False)
    except ValueError:
        check("signing with no key is refused", True)
    check("signing keeps every field and adds sig last", list(signed) == list(base(id="x")) + ["sig"])
    check("a stale sig is not signed over: re-signing gives the same signature",
          sign.sign_request({**signed, "sig": "old"}, k["privateKeySpec"])["sig"] == signed["sig"])

    print("the signed bytes are Node's (JSON.stringify), on the same JSON")
    texts = [
        '{"b":1,"a":2}', '[1,2.5,-0,-0.0,0.1,1e21,1e-7,1e-6,123456789012345678901,5.0,1.5e300,1e400,-1e400]',
        '{"n":9007199254740993,"m":12345678901234567890,"neg":-12.50,"tiny":5e-324,"big":1.7976931348623157e308}',
        '{"s":"ünï ✓ 😀","ctl":"\\u0000\\u0001\\u001f\\u007f\\b\\f\\n\\r\\t","q":"\\"\\\\/","ls":"\\u2028\\u2029"}',
        '{"lone":"\\ud800","low":"\\udfff","pair":"\\ud83d\\ude00","rev":"\\ude00\\ud83d"}',
        '{"😀":1,"\\uffff":2,"\\ue000":3,"a":4,"B":5,"é":6,"":7,"\\ud800":8}',
        '{"t":true,"f":false,"z":null,"e":[],"o":{},"deep":[{"y":[{"b":1,"a":[]}]}]}',
        '{"dup":1,"dup":2}', '"just a string"', '42', 'null', '[0.000001,0.0000001,100,1e20,1e22,0.30000000000000004]',
    ]
    want = node("return input.map(t => sign.canonical(JSON.parse(t)));", texts)
    for t, w in zip(texts, want):
        got = sign.canonical(json.loads(t))
        check(f"canonical({t[:48]}…)", got == w, f"\n      node={w!r}\n      py  ={got!r}")
    rnd = random.Random(20261009)
    doubles = [struct.unpack("<d", struct.pack("<Q", rnd.getrandbits(64)))[0] for _ in range(20000)]
    doubles += [rnd.uniform(-1e6, 1e6) for _ in range(5000)] + [rnd.randint(-2**70, 2**70) * 1.0 for _ in range(2000)]
    finite = [d for d in doubles if d == d and abs(d) != float("inf")]
    want = node("return input.map(x => JSON.stringify(x));", finite)
    bad = [(d, w, sign.js_number(d)) for d, w in zip(finite, want) if sign.js_number(d) != w]
    check(f"js_number equals JSON.stringify on {len(finite)} random doubles", not bad, bad[:5])

    print("across the languages: one wire")
    args = {"piece": "claude", "note": "ünï ✓ 😀\u2028", "n": 5, "f": 0.1, "big": 12345678901234567890, "nested": {"z": [1, {"y": "\ud800"}]}}
    py_signed = sign.sign_request(base(args=args), k["privateKeySpec"])
    nv = node("return sign.verifyRequest(input[0], sign.publicKeyFrom(input[1]));", [py_signed, k["publicKeySpec"]])
    check("a request signed here, non-ASCII and numbers among its arguments, is verified by Node", nv is True, nv)
    nk = node("return sign.generateOperatorKey();", None)
    node_signed = node("return sign.signRequest(input[0], input[1]);", [base(args=args), nk["privateKeySpec"]])
    check("a request Node signed is verified here", sign.verify_request(node_signed, sign.public_key_from(nk["publicKeySpec"])) is True)
    check("...with the same signature bytes this side makes from Node's key",
          sign.sign_request(base(args=args), nk["privateKeySpec"])["sig"] == node_signed["sig"])
    check("a key made here is read by Node, and Node's here",
          node("return [!!sign.privateKeyFrom(input[0]), !!sign.publicKeyFrom(input[1])];", [k["privateKeySpec"], k["publicKeySpec"]]) == [True, True]
          and sign.private_key_from(nk["privateKeySpec"]) is not None and sign.public_key_from(nk["publicKeySpec"]) is not None)
    tampered = {**node_signed, "args": {**args, "n": 6}}
    check("...and a tampered one is refused on both sides",
          sign.verify_request(tampered, sign.public_key_from(nk["publicKeySpec"])) is False
          and node("return sign.verifyRequest(input[0], sign.publicKeyFrom(input[1]));", [tampered, nk["publicKeySpec"]]) is False)
    junk = ["bm90-IGEg_c2ln", "a", "YQ==YQ==", "not-base64-der", "####", "", "ab=c"]
    check("base64 is read as Node's Buffer.from reads it",
          [sign.node_b64decode(s).hex() for s in junk] == node("return input.map(s => Buffer.from(s, 'base64').toString('hex'));", junk))

    print("what the relay can send (review of 73f35649)")
    import time
    t0 = time.monotonic()
    huge = {**signed, "sig": base64.b64encode(b"x" * 70000).decode()}
    check("a sig far longer than 64 bytes is False at once, never a blocked pipe",
          sign.verify_request(huge, pub) is False and time.monotonic() - t0 < 5, time.monotonic() - t0)
    check("63 and 65 bytes are False too",
          all(sign.verify_request({**signed, "sig": base64.b64encode(b"x" * n).decode()}, pub) is False for n in (63, 65)))
    deep: object = "leaf"
    for _ in range(3000):
        deep = [deep]
    try:
        text = sign.canonical(deep)
        check("canonical builds a value nested 3000 deep, as Node's does", text == "[" * 3000 + '"leaf"' + "]" * 3000)
    except RecursionError:
        check("canonical builds a value nested 3000 deep, as Node's does", False, "RecursionError")
    check("a deep request is a verdict, never a RecursionError",
          sign.verify_request({**signed, "args": deep}, pub) is False)
    deep_signed = sign.sign_request(base(args=deep), k["privateKeySpec"])
    check("...and one signed that deep verifies", sign.verify_request(deep_signed, pub) is True)
    want = node("return sign.canonical(JSON.parse(input));", json.dumps([[[[{"b": [1, {"d": 2, "c": [[]]}], "a": {}}]]]]))
    check("the stack builds what Node's recursion builds", sign.canonical([[[[{"b": [1, {"d": 2, "c": [[]]}], "a": {}}]]]]) == want, want)
    loop: list = []
    loop.append(loop)
    try:
        sign.canonical(loop)
        check("a value that contains itself is refused", False)
    except ValueError:
        check("a value that contains itself is refused, never an endless build", True)
    check("...and is False in verify_request, as Node's catch makes it", sign.verify_request({**signed, "args": loop}, pub) is False)
    shared = [1]
    check("the same list twice, not inside itself, is no cycle", sign.canonical({"a": shared, "b": shared}) == '{"a":[1],"b":[1]}')
    wide = ["QUJD" + chr(0x1F600) + "RA", chr(0x141) + "AAA", "QUJD" + chr(0x141) * 2, "QU" + chr(0x100) + "JD", "QUJD" + chr(0xD800)]
    check("base64 beyond Latin-1 is read by the low byte of each code unit, as Node reads it",
          [sign.node_b64decode(w).hex() for w in wide] == node("return input.map(s => Buffer.from(s, 'base64').toString('hex'));", wide),
          [sign.node_b64decode(w).hex() for w in wide])
    enc = subprocess.run(["openssl", "pkcs8", "-topk8", "-inform", "DER", "-outform", "DER", "-v2", "aes-256-cbc", "-passout", "pass:x"],
                         input=sign.private_key_from(k["privateKeySpec"]), capture_output=True, timeout=30, check=True).stdout
    t0 = time.monotonic()
    check("an encrypted key is no key, and asks for no passphrase",
          sign.private_key_from("ed25519-pkcs8:" + base64.b64encode(enc).decode()) is None and time.monotonic() - t0 < 5,
          time.monotonic() - t0)
    # On a terminal, an encrypted key must still be no key and ask nothing:
    # a child on a pseudo-terminal of its own (its controlling tty, which
    # openssl's prompt opens), answered by nobody.
    import pty
    import select
    spec = "ed25519-pkcs8:" + base64.b64encode(enc).decode()
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os._exit(0 if sign.private_key_from(spec) is None else 3)
        except BaseException:
            os._exit(4)
    deadline, status = time.monotonic() + 8, None
    while time.monotonic() < deadline:
        select.select([fd], [], [], 0.2)
        try:
            os.read(fd, 4096)
        except OSError:
            pass
        done, st = os.waitpid(pid, os.WNOHANG)
        if done:
            status = os.waitstatus_to_exitcode(st)
            break
    if status is None:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
    os.close(fd)
    check("...on a terminal too: no passphrase prompt waits out the bound", status == 0, status)
    check("a key spec longer than any key is none, never a blocked pipe",
          sign.public_key_from("ed25519:" + base64.b64encode(b"x" * 70000).decode()) is None)

    print("openssl's failures are not verdicts")
    saved = os.environ.get("PATH", "")
    SLEEP = shutil.which("sleep")
    with tempfile.TemporaryDirectory() as d:
        fake = os.path.join(d, "openssl")
        with open(fake, "w") as fh:
            fh.write("#!/bin/sh\necho 'something else'\nexit 1\n")
        os.chmod(fake, 0o755)
        try:
            os.environ["PATH"] = d
            try:
                sign.verify_request(signed, pub)
                check("an answer that is neither verdict: SignError", False)
            except sign.SignError as e:
                check("an answer that is neither verdict: SignError, never False", "something else" in str(e), str(e))
            with open(fake, "w") as fh:
                fh.write(f"#!/bin/sh\nexec {SLEEP} 30\n")
            saved_timeout, sign.TIMEOUT_S = sign.TIMEOUT_S, 0.5
            try:
                t0 = time.monotonic()
                sign.verify_request(signed, pub)
                check("an openssl that never answers: SignError", False)
            except sign.SignError as e:
                check("an openssl that never answers: SignError within the bound, never False",
                      "no answer within" in str(e) and time.monotonic() - t0 < 5, (str(e), time.monotonic() - t0))
            finally:
                sign.TIMEOUT_S = saved_timeout
            os.remove(fake)
            try:
                sign.verify_request(signed, pub)
                check("no openssl: SignError", False)
            except sign.SignError as e:
                check("no openssl: SignError, never False", "not installed" in str(e), str(e))
            try:
                sign.generate_operator_key()
                check("no openssl: no key is made", False)
            except sign.SignError:
                check("no openssl: no key is made", True)
        finally:
            os.environ["PATH"] = saved
    check("...and the real one still answers after", sign.verify_request(signed, pub) is True)

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
