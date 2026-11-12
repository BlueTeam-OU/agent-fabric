#!/usr/bin/env python3
"""A faithful stand-in for `interweave-human --profile P listen --json --input --consume --endpoint E`
(InterWeave 0.2.0), for the control carrier's tests. Faithful to what was measured on the real child,
2026-11-12 (tools/fabric/gzcoord/carrier/control_link.py header):

  stdout   {"event":"session","session":"ready"}, then one line per event;
           a received message:  {"event":"message","author":<PeerId>,"conversation":"<author>/<endpoint>",
             "local_endpoint":<endpoint>,"direction":"in","id":"u<n>","text":...}
           a send, answered TWICE (the real one does):
             {"event":"outbound","id":"p<n>","problem":null,"ref":<ref>,"status":"accepted"}
  stdin    {"send":{"conversation":"<peer>/<endpoint>","text":...,"ref":...,"pending":false}} per line; a line
           that is not a JSON object is answered {"event":"input-refused","reason":..,"ref":null}.
  exit     SIGTERM ends it with 0; end of stdin does NOT end it.

The network is a directory: FAKE_NET/<PeerId>/ holds the messages for that peer, one file each. FAKE_PEER is
this process's own PeerId. Knobs (environment), each for one failure the tests need:
  FAKE_EXIT=<n>        exit <n> at once, printing nothing
  FAKE_SILENT=1        read sends and never answer them (a wedged child)
  FAKE_PROBLEM=<token> answer every send with that problem token
  FAKE_ARGV=<file>     write the argv it was started with, one JSON line (append)
  FAKE_SENDS=<file>    append each send object it is given, one JSON line
  FAKE_DOUBLE_START=1  print `session ready` only after FAKE_READY_FILE exists (a child that comes up late)
"""
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time


def out(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    env = os.environ
    if env.get("FAKE_ARGV"):
        with open(env["FAKE_ARGV"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(sys.argv[1:]) + "\n")
    if env.get("FAKE_EXIT"):
        return int(env["FAKE_EXIT"])
    net, me = env["FAKE_NET"], env["FAKE_PEER"]
    endpoint = sys.argv[sys.argv.index("--endpoint") + 1]
    os.makedirs(os.path.join(net, me), exist_ok=True)
    signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
    if env.get("FAKE_READY_FILE"):
        while not os.path.exists(env["FAKE_READY_FILE"]):
            time.sleep(0.02)
    out({"event": "session", "session": "ready"})
    out({"connectivity": "online-partial", "event": "connectivity"})
    n = {"p": 0, "u": 0, "seq": 0}

    def deliver() -> None:
        mine = os.path.join(net, me)
        while True:
            for name in sorted(os.listdir(mine)):
                if name.startswith("."):
                    continue   # a file still being written
                path = os.path.join(mine, name)
                try:
                    with open(path, encoding="utf-8") as fh:
                        msg = json.load(fh)
                except (OSError, ValueError):
                    continue   # being written
                os.unlink(path)
                n["u"] += 1
                out({"author": msg["author"], "card": None, "conversation": f"{msg['author']}/{endpoint}", "direction": "in",
                     "event": "message", "id": f"u{n['u']}", "kept": False, "local_at_ms": int(time.time() * 1000),
                     "local_endpoint": msg.get("endpoint", endpoint), "reply_to": None, "route_label": endpoint,
                     "sent_at_ms": msg["at"], "status": "unread", "text": msg["text"]})
            time.sleep(0.02)
    threading.Thread(target=deliver, daemon=True).start()
    for raw in sys.stdin.buffer:
        try:
            line = json.loads(raw.decode("utf-8"))
        except ValueError:
            line = None
        if not isinstance(line, dict) or not isinstance(line.get("send"), dict):
            out({"event": "input-refused", "reason": "not a JSON object" if not isinstance(line, dict) else "not a send: {\"send\": {...}}", "ref": None})
            continue
        s = line["send"]
        if env.get("FAKE_SENDS"):
            with open(env["FAKE_SENDS"], "a", encoding="utf-8") as fh:
                fh.write(json.dumps(s) + "\n")
        if env.get("FAKE_SILENT"):
            continue
        peer, _, dest_endpoint = str(s.get("conversation", "")).partition("/")
        n["p"] += 1
        problem = env.get("FAKE_PROBLEM") or (None if dest_endpoint and os.path.isdir(os.path.join(net, peer)) else "route-unavailable")
        if problem is None:
            n["seq"] += 1
            tmp = os.path.join(net, peer, f".{me[-6:]}-{os.getpid()}-{n['seq']}")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"author": me, "text": s.get("text"), "at": int(time.time() * 1000), "endpoint": dest_endpoint}, fh)
            os.rename(tmp, os.path.join(net, peer, f"{time.time_ns()}-{me[-6:]}-{n['seq']}.json"))
        ev = {"event": "outbound", "id": f"p{n['p']}", "problem": problem, "ref": s.get("ref"),
              "status": "needs-attention" if problem else "accepted"}
        out(ev)
        out(ev)
    while True:    # end of input does not end a listen
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
