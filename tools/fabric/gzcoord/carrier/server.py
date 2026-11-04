"""tools/fabric/gzcoord/carrier/server.py — the adapter channel of
CARRIER-CONTRACT.md §6: a Unix stream socket, one JSON line in and one out
per connection, for the send and inbox adapters and the operator's
`gzcoord-carrier` commands.

Every connection is checked with SO_PEERCRED before a byte is read: the
peer's uid must be the carrier's own, else the connection is closed unread
(directory and socket modes are the default, not the check). A request line
is bounded; a request that does not parse, names no op or breaks its op's
shape is answered {"ok": false, "error": ...} and changes nothing.
"""
from __future__ import annotations

import json
import os
import socket
import stat
import struct
import threading
from typing import Callable

# Room for the 4 MiB a message may be, doubled by the escaping JSON may need, and the
# envelope (CARRIER-CONTRACT.md §6).
MAX_REQUEST = 9 * 1024 * 1024
READ_TIMEOUT = 15.0


def socket_path(runtime_dir: str) -> str:
    return os.path.join(runtime_dir, "agent-fabric", "gzcoord-carrier.sock")


def peer_uid(conn: socket.socket) -> int:
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)[1]


class Server:
    def __init__(self, path: str, handler: Callable[[dict], dict], *, uid: int | None = None) -> None:
        self.path, self.handler = path, handler
        self.uid = os.getuid() if uid is None else uid
        directory = os.path.dirname(path)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        if os.path.lexists(path):
            if not stat.S_ISSOCK(os.lstat(path).st_mode):
                raise OSError(f"{path} exists and is not a socket")
            self._clear_stale(path)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o177)
        try:
            self._sock.bind(path)
        finally:
            os.umask(old)
        self._sock.listen(16)
        self._thread = threading.Thread(target=self._accept, name="adapter-server", daemon=True)
        self._thread.start()

    @staticmethod
    def _clear_stale(path: str) -> None:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(2)
        try:
            probe.connect(path)
        except (ConnectionRefusedError, FileNotFoundError):
            os.unlink(path)       # nobody is listening: left by a carrier that died
        except OSError:
            raise OSError(f"{path} could not be probed") from None
        else:
            raise OSError(f"another carrier is serving {path}")
        finally:
            probe.close()

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        with conn:
            try:
                if peer_uid(conn) != self.uid:
                    return
                conn.settimeout(READ_TIMEOUT)
                buf = bytearray()
                while b"\n" not in buf:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                    if len(buf) > MAX_REQUEST:
                        self._reply(conn, {"ok": False, "error": "request is too large"})
                        return
                line = bytes(buf).split(b"\n", 1)[0]
                try:
                    req = json.loads(line)
                    if not isinstance(req, dict) or not isinstance(req.get("op"), str):
                        raise ValueError("no op")
                except ValueError:
                    self._reply(conn, {"ok": False, "error": "not a request"})
                    return
                try:
                    out = self.handler(req)
                except (KeyError, TypeError, ValueError) as e:
                    out = {"ok": False, "error": f"bad request: {type(e).__name__}: {e}"}
                self._reply(conn, out)
            except OSError:
                return

    @staticmethod
    def _reply(conn: socket.socket, obj: dict) -> None:
        conn.sendall((json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8"))

    def close(self) -> None:
        try:
            self._sock.close()
        finally:
            try:
                os.unlink(self.path)
            except OSError:
                pass


def call(path: str, req: dict, timeout: float = 15.0) -> dict:
    """The adapters' side: one request, one answer. OSError when the carrier
    is not there; the caller decides what that means (the relay fails open)."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path)
        s.sendall((json.dumps(req, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8"))
        buf = bytearray()
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        out = json.loads(bytes(buf).split(b"\n", 1)[0])
        if not isinstance(out, dict):
            raise ValueError("answer is not an object")
        return out
    except ValueError as e:
        raise OSError(f"the carrier's answer is not JSON: {e}") from e
    finally:
        s.close()
