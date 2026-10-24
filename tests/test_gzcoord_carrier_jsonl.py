#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/jsonl.py: a line that a crash left without its
newline is cut before anything is appended, so the next event is a whole line;
a write that is short is finished or raises; and the files that use it
(the arrival log among them) are repaired on open. Plain script: prints
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord.carrier import arrivals, jsonl  # noqa: E402

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gz-jl-") as d:
        p = os.path.join(d, "f.jsonl")
        open(p, "wb").write(b'{"a":1}\n{"b":2}\n{"c"')
        check("a torn last line is cut back to the last newline", jsonl.repair(p) == 4 and open(p, "rb").read() == b'{"a":1}\n{"b":2}\n')
        open(p, "wb").write(b'{"c"')
        check("a file that is only a torn line becomes empty", jsonl.repair(p) == 4 and open(p, "rb").read() == b"")
        open(p, "wb").write(b"x" * 200000 + b"\n" + b"y" * 130000)
        check("a torn line longer than the search chunk is found too", jsonl.repair(p) == 130000 and os.path.getsize(p) == 200001)
        open(p, "wb").write(b"whole\n")
        check("a whole file and a missing one are left alone", jsonl.repair(p) == 0 and jsonl.repair(os.path.join(d, "none")) == 0)

        open(p, "wb").write(b'{"a":1}\n{"to')
        jsonl.repair(p)
        jsonl.append_path(p, {"d": 4})
        check("an append after the repair is a whole line", [json.loads(x) for x in open(p)] == [{"a": 1}, {"d": 4}])

        real = os.write
        calls = []

        def two_bytes(fd, data):
            calls.append(len(data))
            return real(fd, bytes(data[:2]))
        fd = os.open(os.path.join(d, "g.jsonl"), os.O_WRONLY | os.O_CREAT)
        with mock.patch("os.write", two_bytes):
            jsonl.write_all(fd, b"abcdefg")
        os.close(fd)
        check("a short write is finished, byte for byte", open(os.path.join(d, "g.jsonl"), "rb").read() == b"abcdefg" and len(calls) == 4)
        fd = os.open(os.path.join(d, "h.jsonl"), os.O_WRONLY | os.O_CREAT)
        try:
            with mock.patch("os.write", lambda fd, data: 0):
                jsonl.write_all(fd, b"abc")
            raised = False
        except OSError:
            raised = True
        os.close(fd)
        check("a write that makes no progress raises, never loops", raised)

        fd = os.open(os.path.join(d, "t.jsonl"), os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
        jsonl.append(fd, {"a": 1})
        calls2 = []

        def dies_after_two(f, data):
            calls2.append(1)
            if len(calls2) == 1:
                real(f, bytes(data[:2]))
                raise OSError(28, "No space left on device")
            return real(f, data)
        with mock.patch("os.write", dies_after_two):
            try:
                jsonl.append(fd, {"b": 2})
            except OSError:
                pass
            jsonl.append(fd, {"c": 3})
        os.close(fd)
        check("a write that fails part-way is cut back: the next append is not merged into its bytes",
              [json.loads(x) for x in open(os.path.join(d, "t.jsonl"))] == [{"a": 1}, {"c": 3}])

        a = os.path.join(d, "arr.jsonl")
        open(a, "wb").write(b'{"mid":"x"}\n{"mid":"y","addr')
        log = arrivals.ArrivalLog(a, iso_now=lambda: "T")
        log.append("z", "h/me", "relay", "unauthenticated")
        lines = [json.loads(x) for x in open(a)]
        check("the arrival log is repaired on open, and its next line is whole", [x["mid"] for x in lines] == ["x", "z"], str(lines))
    print(f"\ntest_gzcoord_carrier_jsonl: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
