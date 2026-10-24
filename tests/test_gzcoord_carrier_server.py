#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/server.py (CARRIER-CONTRACT.md §6): the
adapter channel answers one JSON line per connection; a peer whose uid is not
the carrier's is closed before a byte is read (SO_PEERCRED; the control is the
same call from the right uid); a bad request changes nothing; a stale socket
of a dead carrier is replaced and a live one's is not; the socket is 0600 in a
0700 directory. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import socket
import stat
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from gzcoord.carrier import server as S  # noqa: E402

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def raw(path: str, data: bytes) -> bytes:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(path)
    try:
        s.sendall(data)
        out = bytearray()
        while True:
            chunk = s.recv(65536)
            if not chunk:
                return bytes(out)
            out += chunk
            if b"\n" in out:
                return bytes(out)
    except (ConnectionResetError, BrokenPipeError):
        return b""      # closed on us, unread: what a refused peer sees
    finally:
        s.close()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gz-srv-") as d:
        path = S.socket_path(d)
        seen: list[dict] = []

        def handler(req: dict) -> dict:
            seen.append(req)
            if req["op"] == "boom":
                raise KeyError("x")
            return {"ok": True, "echo": req["op"]}

        srv = S.Server(path, handler)
        check("the directory is 0700 and the socket 0600",
              stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode) == 0o700
              and stat.S_IMODE(os.lstat(path).st_mode) == 0o600)
        check("a request from the carrier's own uid is answered", S.call(path, {"op": "status"}) == {"ok": True, "echo": "status"})
        check("a request that is not JSON is refused and reaches no handler",
              b'"ok":false' in raw(path, b"nope\n") and not [r for r in seen if r.get("op") not in ("status",)])
        check("JSON that is not an object with an op is refused", b'"ok":false' in raw(path, b'[1]\n') and b'"ok":false' in raw(path, b'{"x":1}\n'))
        out = raw(path, b'{"op":"boom"}\n')
        check("a handler's bad-request error is an answer, not a dead server",
              b'"ok":false' in out and S.call(path, {"op": "again"})["echo"] == "again")
        big = raw(path, b'{"op":"send","text":"' + b"a" * (S.MAX_REQUEST + 10) + b'"}\n')
        check("a request past the bound is refused", b'"ok":false' in big and b"too large" in big)
        srv.close()

        wrong = S.Server(path, handler, uid=os.getuid() + 1)
        before = len(seen)
        got = raw(path, b'{"op":"status"}\n')
        check("a peer of another uid is closed unread: no answer, no handler call",
              got == b"" and len(seen) == before)
        wrong.close()

        # a stale socket: left by a carrier that died without unlinking
        dead = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        dead.bind(path)
        dead.close()
        check("the dead carrier's socket file is there", os.path.exists(path))
        srv = S.Server(path, handler)
        check("a stale socket is replaced", S.call(path, {"op": "status"})["ok"] is True)
        try:
            S.Server(path, handler)
            second = False
        except OSError:
            second = True
        check("a live carrier's socket is never taken over", second and S.call(path, {"op": "status"})["ok"])
        srv.close()
        with open(path, "w") as fh:
            fh.write("not a socket")
        try:
            S.Server(path, handler)
            refused = False
        except OSError:
            refused = True
        check("a path that is a file is never unlinked", refused and open(path).read() == "not a socket")
        os.unlink(path)
        try:
            S.call(path, {"op": "status"})
            gone = False
        except OSError:
            gone = True
        check("with no carrier the call raises OSError for the adapter to fail open on", gone)
    print(f"\ntest_gzcoord_carrier_server: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
