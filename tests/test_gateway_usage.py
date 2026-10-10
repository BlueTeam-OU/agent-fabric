#!/usr/bin/env python3
"""tools/fabric/launcher/gateway_usage.py: the launcher's relay of the gateway's {"op":"usage"} to
<state>/gateway-usage.json. The gateway is a fake on the other end of a socketpair, answering from a script,
so every way the channel can go wrong is one scripted reply. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import launch  # noqa: E402,F401  (loads the fabric_launcher package)
from fabric_launcher import gateway_usage as GU  # noqa: E402

ENTRY = {"source": {"token_file": "/run/user/1000/agent-fabric/gateway/claude-subscription.token"},
         "generation": {"device": 1, "inode": 2, "mtime_sec": 3, "mtime_nsec": 4}, "read_at": 1760123460,
         "usage": {"five_hour": {"utilization": 0.42, "reset": 1760130000, "surpassed_threshold": None}, "status": "allowed",
                   "malformed": []}}
EVENT = {"event": "usage", "credentials": [ENTRY]}


class Fake:
    """The gateway's end: answers each line it reads with the next scripted reply (bytes), or nothing for None."""

    def __init__(self, replies: list):
        self.mine, self.theirs = socket.socketpair()
        self.replies, self.asked = list(replies), []
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self) -> None:
        try:
            self.serve()
        except OSError:
            pass   # the test closed its end

    def serve(self) -> None:
        buf = b""
        while True:
            chunk = self.theirs.recv(4096)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self.asked.append(line)
                reply = self.replies.pop(0) if len(self.replies) > 1 else (self.replies[0] if self.replies else None)
                if reply is not None:
                    self.theirs.sendall(reply)

    def close(self) -> None:
        self.mine.close()
        self.theirs.close()


def line(doc) -> bytes:
    return json.dumps(doc).encode() + b"\n"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail!r}"))
        fails += not good

    def ask_error(reply, timeout: float = 0.5) -> str:
        f = Fake([reply])
        try:
            GU.ask(f.mine, timeout)
        except GU.OutOfStep as e:
            return str(e)
        finally:
            f.close()
        return ""

    with tempfile.TemporaryDirectory(prefix="test_gateway_usage.") as tmp:
        print("the ask")
        f = Fake([line(EVENT)])
        got = GU.ask(f.mine, 2)
        check("a usage event: its entries, verbatim", got == [ENTRY], got)
        check("…and the request is exactly {\"op\":\"usage\"} and a newline", f.asked == [b'{"op":"usage"}'], f.asked)
        f.close()
        f = Fake([line({"event": "usage", "credentials": []})])
        check("no source yet is an empty list, not an error", GU.ask(f.mine, 2) == [], "")
        f.close()
        for label, reply, want in (
                ("no reply in time", None, "no reply within"),
                ("not JSON", b"nope\n", "not JSON"),
                ("another event (a refusal)", line({"event": "refused", "reason": "x"}), "not a usage event ('refused')"),
                ("an array", b"[1]\n", "not a usage event"),
                ("credentials that are not a list", line({"event": "usage", "credentials": {}}), "not a list of sources"),
                ("an entry with no source", line({"event": "usage", "credentials": [{"read_at": 1}]}), "not a list of sources"),
                ("two lines for one ask", line(EVENT) + line(EVENT), "more than one line"),
                ("a reply of invalid UTF-8", b'{"event":"\xff"}\n', "not JSON")):
            got = ask_error(reply)
            check(f"{label}: out of step, said ({want})", want in got, got)
        saved = GU.REPLY_MAX_BYTES
        GU.REPLY_MAX_BYTES = 64
        try:
            got = ask_error(line({"event": "usage", "credentials": [], "pad": "x" * 200}))
        finally:
            GU.REPLY_MAX_BYTES = saved
        check("a reply past the bound: out of step, said", "longer than 64 bytes" in got, got)
        f = Fake([line(EVENT)])
        f.theirs.close()
        got = ""
        try:
            GU.ask(f.mine, 0.5)
        except GU.OutOfStep as e:
            got = str(e)
        check("a closed channel: out of step, said", "closed" in got or "failed" in got, got)
        f.mine.close()

        print("the file")
        state = os.path.join(tmp, "state")
        f = Fake([line(EVENT)])
        said: list[str] = []
        relay = GU.Relay(f.mine, 4242, state, now=lambda: "2026-10-10T10:00:00.000Z", say=said.append)
        check("a good poll", relay.poll() is True)
        doc = json.load(open(os.path.join(state, GU.FILE), encoding="utf-8"))
        check("…writes pid, time and the entries, and nothing the gateway sent besides",
              doc == {"version": 1, "gateway_pid": 4242, "fetched_at": "2026-10-10T10:00:00.000Z", "credentials": [ENTRY]}, doc)
        check("…mode 0600, no temporary file left",
              (os.stat(os.path.join(state, GU.FILE)).st_mode & 0o777) == 0o600
              and [n for n in os.listdir(state) if ".tmp-" in n] == [], os.listdir(state))
        f.replies = [b"garbage\n"]
        check("a bad reply stops the relay", relay.poll() is False and relay.stopped_on == "the reply is not JSON", relay.stopped_on)
        doc = json.load(open(os.path.join(state, GU.FILE), encoding="utf-8"))
        check("…and the file then says why and shows no earlier reading beside it",
              "credentials" not in doc and "the relay has stopped asking" in doc["error"] and doc["gateway_pid"] == 4242, doc)
        f.close()

        print("a write that fails")
        ro = os.path.join(tmp, "ro")
        os.makedirs(ro)
        os.chmod(ro, 0o500)
        f = Fake([line(EVENT)])
        said = []
        relay = GU.Relay(f.mine, 1, os.path.join(ro, "sub"), say=said.append)
        relay.poll()
        relay.poll()
        os.chmod(ro, 0o700)
        check("is said once, and does not stop the relay", len(said) == 1 and "could not write" in said[0] and relay.stopped_on is None, said)
        f.close()

        print("forget")
        d = os.path.join(tmp, "forget")
        GU.write(d, {"version": 1, "gateway_pid": 7})
        GU.forget(d, 8)
        check("a file of another gateway (a second launch of the login) is left", os.path.exists(os.path.join(d, GU.FILE)))
        GU.forget(d, 7)
        check("this gateway's is removed", not os.path.exists(os.path.join(d, GU.FILE)))
        GU.forget(d, 7)
        check("…and removing it again is not an error", True)

        print("the thread")
        d = os.path.join(tmp, "thread")
        f = Fake([line(EVENT)])
        relay = GU.Relay(f.mine, 9, d, interval=0.05).start()
        deadline = time.monotonic() + 5
        while len(f.asked) < 3 and time.monotonic() < deadline:
            time.sleep(0.02)
        relay.stop()
        check("asks on the interval until stopped", len(f.asked) >= 3, f.asked)
        n = len(f.asked)
        time.sleep(0.2)
        check("…and not after", len(f.asked) == n)
        f.close()
        f = Fake([None])
        relay = GU.Relay(f.mine, 9, os.path.join(tmp, "silent"), interval=0.05, timeout=30).start()
        time.sleep(0.2)
        t0 = time.monotonic()
        relay.stop()
        check("a gateway that never answers does not hold stop() for the ask's timeout", time.monotonic() - t0 < 3, time.monotonic() - t0)
        f.close()
        f = Fake([b"nope\n"])
        relay = GU.Relay(f.mine, 9, os.path.join(tmp, "oos"), interval=0.01).start()
        time.sleep(0.4)
        relay.stop()
        check("an out-of-step channel is asked once, not again", len(f.asked) == 1, f.asked)
        f.close()

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
