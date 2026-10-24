"""A fake InterWeave daemon's DATA socket for the carrier's tests: the
frames of LOCAL-IPC.md over a Unix socket in a scratch directory, scripted
by the case. It models only what the carrier relies on (hello with an
endpoint claim and its refusals, direct.send, pushed message.direct events,
ping, close); the real daemon is the live check's (ADR-064 rule 13)."""
from __future__ import annotations

import os
import socket
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "fabric"))
from gzcoord.carrier import ipc  # noqa: E402


class FakeDaemon:
    def __init__(self, directory: str, peer: str = "12D3KooWFakeDaemonPeer", endpoint: str = "gzcoord") -> None:
        self.path = os.path.join(directory, "p.sock")
        self.peer, self.endpoint = peer, endpoint
        self.sends: list[dict] = []          # every direct.send params, in order
        self.send_answers: list = []         # per send: None accepts, else an error code
        self.hello_refusal: str | None = None
        self.answer_pings = True
        self.hellos: list[dict] = []
        self._conns: list[socket.socket] = []
        self._lock = threading.Lock()
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(self.path)
        self._srv.listen(8)
        self.pongs: list[str] = []
        # Where an accepted send is delivered, by destination PeerId, as this
        # daemon's peer; a destination not in the table is accepted and never
        # delivered (AcceptedV2 is not delivery). `forwarded` counts what went across.
        self.routes: "dict[str, FakeDaemon]" = {}
        self.forwarded = 0
        self._t = threading.Thread(target=self._accept, daemon=True)
        self._t.start()

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        try:
            hello = ipc.read_frame(conn)
            self.hellos.append(hello)
            if self.hello_refusal:
                ipc.write_frame(conn, {"type": "close", "code": self.hello_refusal})
                conn.close()
                return
            ipc.write_frame(conn, {"type": "hello_response", "ipc_version": {"major": 2, "minor": 0},
                                   "transport_contract_version": "2.0", "peer": self.peer,
                                   "endpoint": hello["endpoint"]["id"], "endpoint_lease_epoch": "e" * 22,
                                   "event_queue": 256, "granted_capabilities": ["events", "commands"]})
            with self._lock:
                self._conns.append(conn)      # pushes only after the hello_response, as a daemon does
            while True:
                f = ipc.read_frame(conn)
                if f.get("type") == "pong":
                    self.pongs.append(f["nonce"])
                elif f.get("type") == "request" and f["method"] == "direct.send":
                    self.sends.append(f["params"])
                    ans = self.send_answers.pop(0) if self.send_answers else None
                    if ans == "hang":
                        continue
                    if ans is None:
                        p = f["params"]
                        ipc.write_frame(conn, {"type": "response", "id": f["id"], "ok": True,
                                               "result": {"resolved_endpoint": p.get("endpoint", "gzcoord")}})
                        target = self.routes.get(p["peer"])
                        if target is not None:
                            self.forwarded += 1
                            target.push(self.peer, p["message_id"], p["payload"]["media_type"],
                                        ipc.unb64u(p["payload"]["bytes"]))
                    else:
                        ipc.write_frame(conn, {"type": "response", "id": f["id"], "ok": False,
                                               "error": {"code": ans}})
        except (OSError, EOFError, ValueError):
            pass

    def push(self, source_peer: str, message_id: str, media_type: str, data: bytes,
             source_endpoint: str = "gzcoord") -> None:
        frame = {"type": "event", "sequence": 0, "event_type": "message.direct",
                 "data": {"message_id": message_id, "mode": "direct", "source_peer": source_peer,
                          "source_endpoint": source_endpoint, "destination_endpoint": self.endpoint,
                          "payload": {"media_type": media_type, "bytes": ipc.b64u(data)}, "received_at": 0}}
        self.broadcast_frame(frame)

    def broadcast_frame(self, frame: dict) -> None:
        with self._lock:
            conns = list(self._conns)
        for c in conns:
            try:
                ipc.write_frame(c, frame)
            except OSError:
                pass

    def ping(self, nonce: str = "n" * 22) -> None:
        self.broadcast_frame({"type": "ping", "nonce": nonce})

    def drop_connections(self) -> None:
        with self._lock:
            conns, self._conns = self._conns, []
        for c in conns:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            c.close()

    def close(self) -> None:
        self.drop_connections()
        self._srv.close()
