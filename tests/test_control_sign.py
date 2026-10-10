#!/usr/bin/env python3
"""Tests for tools/fabric/control/sign.py, the port of runtime/control/sign.mjs.

The first block is runtime/control/tests/sign.test.mjs's own test (its
"canonical: …" case), case for case; its other four test agentd.mjs's
accept and ledger and move with agentd. The rest holds the port to the
wire: the signed bytes against what the Node's canonical() gave on the
same JSON, the number layout against the Node's on random doubles (by
digest), a Node signature verified here, and openssl's failures kept
apart from a verdict. The Node signing module was deleted with the Node
control plane (ADR-040 Wave 8, s8); its answers are frozen in
tests/fixtures/node-oracle-sign.json and are the oracle now.
"""
from __future__ import annotations

import base64
import hashlib
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

# What the Node signing module answered, captured before it was deleted (ADR-040
# Wave 8, s8) with the Node of that day: the wire this module must keep
# (tests/fixtures/node-oracle-sign.json). The cases that ran Node beside this
# module now compare against it.
ORACLE = json.load(open(os.path.join(HERE, "tests", "fixtures", "node-oracle-sign.json"), encoding="utf-8"))


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
    # gateway-install joined the actions after the Node was deleted; the Node's list is the rest of it.
    check("ACTION_OPS, the ttl cap and the prefixes are the wire's, as the Node had them",
          ORACLE["consts"] == [[op for op in sign.ACTION_OPS if op != "gateway-install"], sign.ACTION_TTL_MAX_S, sign.KEY_PREFIX,
                               sign.PRIVATE_PREFIX])
    check("…and the one action added since is the last of them", sign.ACTION_OPS[-1] == "gateway-install")
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

    print("the signed bytes are the Node's (JSON.stringify), on the same JSON: frozen in the oracle file")
    texts = ORACLE["texts"]
    for t_, w in zip(texts, ORACLE["canonical"]):
        got = sign.canonical(json.loads(t_))
        check(f"canonical({t_[:48]}…)", got == w, f"\n      node={w!r}\n      py  ={got!r}")
    rnd = random.Random(20261009)
    doubles = [struct.unpack("<d", struct.pack("<Q", rnd.getrandbits(64)))[0] for _ in range(20000)]
    doubles += [rnd.uniform(-1e6, 1e6) for _ in range(5000)] + [rnd.randint(-2**70, 2**70) * 1.0 for _ in range(2000)]
    finite = [d for d in doubles if d == d and abs(d) != float("inf")]
    mine = [sign.js_number(d) for d in finite]
    check(f"js_number equals JSON.stringify on {len(finite)} random doubles (the Node's answers, by digest)",
          len(finite) == ORACLE["js_number"]["count"] and hashlib.sha256(json.dumps(mine).encode()).hexdigest() == ORACLE["js_number"]["sha256"])

    print("across the languages: one wire (a request the Node signed, frozen)")
    args = {"piece": "claude", "note": "ünï ✓ 😀\u2028", "n": 5, "f": 0.1, "big": 12345678901234567890, "nested": {"z": [1, {"y": "\ud800"}]}}
    nk, node_signed = ORACLE["signed"]["key"], ORACLE["signed"]["request"]
    check("a request Node signed is verified here", sign.verify_request(node_signed, sign.public_key_from(nk["publicKeySpec"])) is True)
    check("...with the same signature bytes this side makes from Node's key",
          sign.sign_request(base(args=args), nk["privateKeySpec"])["sig"] == node_signed["sig"])
    check("a key Node made is read here", sign.private_key_from(nk["privateKeySpec"]) is not None and sign.public_key_from(nk["publicKeySpec"]) is not None)
    tampered = {**node_signed, "args": {**args, "n": 6}}
    check("...and a tampered one is refused", sign.verify_request(tampered, sign.public_key_from(nk["publicKeySpec"])) is False)
    check("base64 is read as Node's Buffer.from reads it",
          [sign.node_b64decode(s).hex() for s in ORACLE["junk"]] == ORACLE["junk_hex"])

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
    want = ORACLE["deep"]
    check("the stack builds what Node's recursion built", sign.canonical([[[[{"b": [1, {"d": 2, "c": [[]]}], "a": {}}]]]]) == want, want)
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
    wide = ORACLE["wide"]
    check("base64 beyond Latin-1 is read by the low byte of each code unit, as Node reads it",
          [sign.node_b64decode(w).hex() for w in wide] == ORACLE["wide_hex"],
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
