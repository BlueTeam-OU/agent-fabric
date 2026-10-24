#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/ipc.py against a fake daemon's data socket
(tests/interweave_fake.py): the hello claims the endpoint and offers
keepalive and no admin capability; a send is answered, refused with the
daemon's code, or never answered; a ping is answered with its nonce; a
dropped connection ends the session and fails what waits on it; a pushed
message arrives decoded and a malformed one does not. Plain script: prints
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from gzcoord.carrier import ipc  # noqa: E402
from interweave_fake import FakeDaemon  # noqa: E402

fails = 0
MID = "0123456789abcdef0123456789abcdef"


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n{detail}"))
    fails += 0 if ok else 1


def until(cond, seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def raised(fn):
    try:
        fn()
    except BaseException as e:  # noqa: BLE001 — the case names the class it expects
        return e
    return None


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="iw-ipc-") as d:
        daemon = FakeDaemon(d)
        s = ipc.Session.open(daemon.path, endpoint="gzcoord", kind="automated-client")
        h = daemon.hellos[0]
        check("hello claims the endpoint, offers keepalive, asks no admin capability",
              h["endpoint"] == {"id": "gzcoord"} and h["features"] == ["keepalive"]
              and h["requested_capabilities"] == ["events", "commands"] and h["ipc_version"]["major"] == 2
              and h["client"]["kind"] == "automated-client")
        check("the session knows the daemon's peer and the leased endpoint",
              s.peer == "12D3KooWFakeDaemonPeer" and s.endpoint == "gzcoord")

        got = s.direct_send("12D3KooWPeerB", "gzcoord", MID, "application/x", b"\x00\xffdata")
        sent = daemon.sends[0]
        check("a send carries peer, endpoint, message_id and unpadded base64url payload",
              got == "gzcoord" and sent["peer"] == "12D3KooWPeerB" and sent["message_id"] == MID
              and sent["payload"] == {"media_type": "application/x", "bytes": ipc.b64u(b"\x00\xffdata")}
              and "=" not in sent["payload"]["bytes"])

        daemon.send_answers = ["Overloaded", "UnauthorizedPeer"]
        e1 = raised(lambda: s.direct_send("p", "gzcoord", MID, "a/b", b"x"))
        e2 = raised(lambda: s.direct_send("p", "gzcoord", MID, "a/b", b"x"))
        check("Overloaded is a retryable refusal", isinstance(e1, ipc.IpcError) and e1.code == "Overloaded" and e1.retryable)
        check("UnauthorizedPeer is the sender's to see, not retried",
              isinstance(e2, ipc.IpcError) and e2.code == "UnauthorizedPeer" and not e2.retryable and not e2.session_lost)

        daemon.send_answers = ["hang"]
        t0 = time.monotonic()
        e = raised(lambda: s.request("direct.send", {"peer": "p", "message_id": MID, "payload": {"bytes": ""}}, timeout=0.3))
        check("a request never answered is a timeout of unknown outcome, in time",
              isinstance(e, ipc.IpcTimeout) and time.monotonic() - t0 < 3)

        daemon.ping("N" * 22)
        check("a ping is answered with its nonce", until(lambda: daemon.pongs == ["N" * 22]))

        daemon.push("12D3KooWPeerB", MID, "application/vnd.x", b"hello")
        ev = s.events.get(timeout=5)
        m = ipc.inbound(ev)
        check("a pushed message arrives decoded", m is not None and m["data"] == b"hello" and m["message_id"] == MID
              and m["source_peer"] == "12D3KooWPeerB" and m["media_type"] == "application/vnd.x")
        check("a malformed message event is dropped, not half-read",
              ipc.inbound({"event_type": "message.direct", "data": {"message_id": MID}}) is None
              and ipc.inbound({"event_type": "message.direct", "data": {
                  "message_id": MID, "source_peer": "p", "source_endpoint": "e", "payload": {"bytes": "***"}}}) is None
              and ipc.inbound({"event_type": "peer.disconnected", "data": {}}) is None)

        daemon.drop_connections()
        check("a dropped connection ends the session", until(lambda: not s.alive) and s.events.get(timeout=5) is None)
        e = raised(lambda: s.direct_send("p", "gzcoord", MID, "a/b", b"x"))
        check("a send on an ended session is SessionLost, retryable on a new one",
              isinstance(e, ipc.SessionLost) and e.session_lost)

        s2 = ipc.Session.open(daemon.path, endpoint="gzcoord", kind="automated-client")
        check("a fresh session after the loss is a fresh hello", len(daemon.hellos) == 2 and s2.alive)
        s2.close()

        daemon.hello_refusal = "EndpointInUse"
        e = raised(lambda: ipc.Session.open(daemon.path, endpoint="gzcoord", kind="automated-client"))
        check("a second holder of the lease is refused with the daemon's code",
              isinstance(e, ipc.IpcError) and e.code == "EndpointInUse")
        daemon.close()

        e = raised(lambda: ipc.Session.open(os.path.join(d, "none.sock"), endpoint="gzcoord", kind="automated-client"))
        check("no daemon is SessionLost, not a traceback", isinstance(e, ipc.SessionLost))

    print(f"\ntest_gzcoord_carrier_ipc: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
