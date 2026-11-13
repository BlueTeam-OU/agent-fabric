"""tools/fabric/gzcoord/carrier/control_link.py — the control plane's second carrier:
InterWeave, through `interweave-human` on the profile's `fabric-control`
endpoint (agent-fabric ADR-029 rule 18; ADR-064 rule 12). Off unless
runtime/control/config.json `control_carrier` is "dual" (agentd.control_config).

CONTRACT (ADR-029 rule 18, line for line):
  child      agentd runs ONE supervised long-lived child,
               interweave-human --profile gzcoord listen --json --input
                 --consume --endpoint fabric-control
             from ~/.local/bin (where the pinned release's install.sh puts
             it), and sends through its stdin. Nothing else runs
             interweave-human on that profile, and no admin-changing verb
             is ever driven: the argv above is the only one this module builds.
  framing    a record is `fabric-control/1 ` + its JSON, one text message,
             sent to `<peer>/fabric-control`. Anything arriving without the
             prefix is dropped; the GZCoord carrier refuses the prefix on
             gzcoord (gzcoord/carrier/engine.py).
  authority  a request counts only when its `from` is the address the roster
             maps the message's author PeerId to; a reply reaches fabric-ctl
             only from the PeerId of its own `from`. A PeerId the roster does
             not hold is never admitted. The roster is the only source: the
             rows that verify (ADR-064 rule 2), re-verified when the file moves.
  one seen-set  the request is decided by agentd's own accept(), whichever
             carrier brought it, so a request on both is answered once.
  budgets    a send is `"pending": false`: when its wait runs out the child
             cancels it, so nothing is left in the human store for a later
             run to send. A send is never retried here. A request's send is
             bounded by the request's ttl_s.
  ops        RELAY_ONLY_OPS (`interweave`, `-install`, `-start`,
             `-stop`) are never sent by this carrier, and one that arrives on
             it is dropped: they take this channel down or ask about it.
  parts      an account on both splits once, at PART_BYTES, the bound this
             path was measured to carry (see below), and sends those parts by
             both carriers.
  socket     fabric-ctl holds no lease: it hands its sends to the operator's
             own agentd over $XDG_RUNTIME_DIR/agent-fabric/control.sock
             (mode 0600, same uid, SO_PEERCRED checked) and reads back the
             replies agentd routes to it by `in_reply_to`, with the carrier
             and the authenticated sender. One direct send per target.

PART_BYTES. Measured 2026-11-12 on two scratch profiles of one host with the
pinned 0.2.0 programs: random base64 texts of 32 768, 49 152 and 60 000 bytes
were accepted and received whole; 66 000 and over got no `outbound`. The
facade refuses what is over 48 KiB after compression (ADR-064 §3), and
base64 of gzip does not compress, so 32 KiB per part keeps a margin for the
record's own fields and the JSON escaping of an evidence page.

WHAT THE CHILD DOES NOT TELL US, said so a reader does not look for it:
the `outbound` event is printed twice per send (same ref, id and status), and
`accepted` is the daemon taking the message, not the peer receiving it: the
reply is the receipt (ADR-029 rule 18's source, docs/proposals/j422 §4.3).
interweave-human is not in release.json `reports` or `program_sha256` yet
(j422 F1), so its digest is not checked here; its `--version` is logged.
"""
from __future__ import annotations

import collections
import contextlib
import os
import select
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Iterable

from control import js
from control.carrier_install import CARRIER_NAME, INSTALL_OP, START_OP, STOP_OP
from gzcoord.carrier import framing, roster as roster_mod

PREFIX = framing.CONTROL_PREFIX
ENDPOINT = roster_mod.CONTROL_ENDPOINT
PROFILE = "gzcoord"
# What the arrival log, the logs and agentd's `via` call this carrier: the package's own name for it.
VIA = CARRIER_NAME
PROGRAM_NAME = "interweave-human"
LISTEN_ARGS = ("--profile", PROFILE, "listen", "--json", "--input", "--consume", "--endpoint", ENDPOINT)
PART_BYTES = 32 * 1024
RELAY_ONLY_OPS = frozenset({CARRIER_NAME, INSTALL_OP, START_OP, STOP_OP})
INBOUND_MAX = 256          # the daemon's per-client queue (InterWeave ADR-0055 decision 2)
BACKOFF_S = (1, 2, 4, 8, 16, 32, 60)
SEND_WAIT_S = 10.0         # a reply's send; a request's is its ttl_s
WRITE_WAIT_S = 5.0         # a line the child's pipe cannot take in this long: the child is not reading
WEDGED_AFTER = 3           # consecutive sends that got no outbound at all: the child is not draining
SOCKET_NAME = "control.sock"
SOCKET_SEND_S = 5.0        # a reply written to fabric-ctl's socket
MAX_WAIT_S = 86400        # fabric-ctl's own --timeout is any number of seconds; a day is a bound, not an expectation
MAX_SOCKET_LINE = 1 << 20  # a request line from fabric-ctl; the largest record is far under it
EXIT_WORDS = {3: "no daemon answered for the profile", 4: "another client holds the profile's message store",
              5: "the message store cannot be used"}
# Exit codes after which the channel is `off` rather than merely restarting (j422 §4.1).
OFF_EXITS = (3, 5)


class Refused(Exception):
    """A record this carrier will not take, with the reason a log line gives."""


def say(message: str) -> None:
    sys.stderr.write(f"agentd: {CARRIER_NAME}: {message}\n")
    sys.stderr.flush()


# ── framing ──────────────────────────────────────────────────────────

def frame(record: dict) -> str:
    return PREFIX + js.stringify(record)


def unframe(text: Any) -> dict:
    if not isinstance(text, str) or not text.startswith(PREFIX):
        raise Refused(f"no {PREFIX.strip()} prefix")
    try:
        record = js.json_parse(text[len(PREFIX):])
    except ValueError as e:
        raise Refused(f"not JSON ({js.slice(str(e), 80)})") from e
    if not isinstance(record, dict):
        raise Refused("not a JSON object")
    return record


def socket_path(env: dict[str, str] | None = None) -> str | None:
    """None when there is no runtime directory to keep a 0600 socket in: the caller says so and the relay carries."""
    env = os.environ if env is None else env
    rd = env.get("XDG_RUNTIME_DIR")
    if not rd or not os.path.isabs(rd):
        return None
    return os.path.join(rd, "agent-fabric", SOCKET_NAME)


# ── who sent it: the roster ──────────────────────────────────────────

class Directory:
    """PeerId <-> address, from the roster rows that verify (ADR-064 rule 2). The rows are asked for again
    when `stamp()` changes (verification runs gpg: not per message). A roster that does not verify, or a row
    whose address no host places, maps nothing: nobody is admitted on a guess."""

    def __init__(self, rows: Callable[[], list[dict]], host: str, placed: Callable[[], set[str]],
                 stamp: Callable[[], Any] = lambda: None, log: Callable[[str], None] = say) -> None:
        self._rows, self._host, self._placed, self._stamp, self._log = rows, host, placed, stamp, log
        self._lock = threading.Lock()
        self._seen: Any = object()
        self._by_peer: dict[str, str] = {}
        self._by_address: dict[str, str] = {}

    def _load(self) -> None:
        stamp = (self._stamp(), tuple(sorted(self._placed())))
        with self._lock:
            if stamp == self._seen:
                return
            by_peer: dict[str, str] = {}
            try:
                rows = self._rows()
                placed = self._placed()
            except Exception as e:  # noqa: BLE001 — whatever stops the roster verifying, the answer is the same: nothing is mapped
                self._log(f"the roster does not verify, admitting nobody: {type(e).__name__}: {e}")
                rows, placed = [], set()
            for r in rows:
                address = f"{r.get('host') or self._host}/{r['login']}"
                if address in placed and isinstance(r.get("peer_id"), str):
                    by_peer[r["peer_id"]] = address
            self._by_peer = by_peer
            self._by_address = {a: p for p, a in by_peer.items()}
            self._seen = stamp

    def address_of(self, peer_id: Any) -> str | None:
        self._load()
        return self._by_peer.get(peer_id) if isinstance(peer_id, str) else None

    def peer_of(self, address: Any) -> str | None:
        self._load()
        return self._by_address.get(address) if isinstance(address, str) else None

    def addresses(self) -> list[str]:
        self._load()
        return sorted(self._by_address)


# ── arrivals ─────────────────────────────────────────────────────────

class ArrivalLog:
    """One JSON line per record that arrived, with its carrier and the verdict, for the parity report
    (ADR-029 rule 18: every arrival is logged with its carrier). Owner-only; a line that cannot be
    written is said once and never stops the answer."""

    def __init__(self, path: str, who: str, clock: Callable[[], float] = time.time, log: Callable[[str], None] = say) -> None:
        self.path, self.who, self._clock, self._log = path, who, clock, log
        self._lock = threading.Lock()
        self._said = False

    def add(self, carrier: str, record: Any, verdict: str, sender: str | None = None) -> None:
        r = record if isinstance(record, dict) else {}
        line = {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._clock())), "who": self.who, "carrier": carrier,
                "kind": r.get("kind") if isinstance(r.get("kind"), str) else None, "id": r.get("id") if isinstance(r.get("id"), str) else None,
                "in_reply_to": r.get("in_reply_to") if isinstance(r.get("in_reply_to"), str) else None,
                "from": sender if sender is not None else (r.get("from") if isinstance(r.get("from"), str) else None),
                "op": r.get("op") if isinstance(r.get("op"), str) else None, "verdict": verdict}
        part = (r.get("data") or {}).get("part") if isinstance(r.get("data"), dict) else None
        if isinstance(part, dict):
            line["part"] = f"{part.get('slug')}/{part.get('part')}"
        data = (js.stringify(line) + "\n").encode("utf-8")
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
                fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    os.write(fd, data)
                finally:
                    os.close(fd)
            except OSError as e:
                if not self._said:
                    self._said = True
                    self._log(f"arrival log {self.path} cannot be written ({e}); arrivals are not recorded")


# ── the child ────────────────────────────────────────────────────────

class Send:
    """One send handed to the child: done when the child reports its `outbound` (or refuses the line)."""

    def __init__(self, ref: str) -> None:
        self.ref = ref
        self._done = threading.Event()
        self.ok = False
        self.why = ""

    def finish(self, ok: bool, why: str = "") -> None:
        if not self._done.is_set():
            self.ok, self.why = ok, why
            self._done.set()

    def wait(self, timeout_s: float) -> tuple[bool, str]:
        if not self._done.wait(max(0.0, timeout_s)):
            return False, f"no answer from the child in {timeout_s:g} s"
        return self.ok, self.why


def failed(why: str) -> Send:
    s = Send("-")
    s.finish(False, why)
    return s


class Inbox:
    """Messages read from the child, bounded at INBOUND_MAX: the reader only enqueues, so a slow handler never
    stops the child's stdout. Full: the OLDEST is dropped with a line (a request is stale after ttl_s anyway)."""

    def __init__(self, handle: Callable[[dict], None], log: Callable[[str], None] = say, limit: int = INBOUND_MAX) -> None:
        self._q: collections.deque = collections.deque()
        self._cv = threading.Condition()
        self._handle, self._log, self._limit = handle, log, limit
        self._stop = False
        self.dropped = 0
        self._thread = threading.Thread(target=self._run, name="control-carrier-inbox", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def put(self, event: dict) -> None:
        with self._cv:
            if len(self._q) >= self._limit:
                self._q.popleft()
                self.dropped += 1
                self._log(f"inbound queue full ({self._limit}): dropped the oldest message ({self.dropped} so far)")
            self._q.append(event)
            self._cv.notify()

    def close(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify()

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._q and not self._stop:
                    self._cv.wait()
                if self._stop and not self._q:
                    return
                event = self._q.popleft()
            try:
                self._handle(event)
            except Exception as e:  # noqa: BLE001 — one message that breaks the handler is that message's fault
                self._log(f"a message broke the handler ({type(e).__name__}: {js.slice(str(e), 200)})")


class Child:
    """`interweave-human … listen --json --input --consume --endpoint fabric-control`, supervised: restarted with
    backoff 1, 2, 4 … 60 s however it ends (the exit code only says what the log line and `state` say), its
    stderr read into the log so it never blocks, its stdout read line by line. State is `off` (no daemon, or the
    store cannot be used), `restarting`, or `ok` (a `session ready` was read)."""

    def __init__(self, argv: list[str], env: dict[str, str], on_message: Callable[[dict], None], *,
                 log: Callable[[str], None] = say, popen: Callable[..., Any] = subprocess.Popen,
                 backoff: tuple[float, ...] = BACKOFF_S, wait_stop: Callable[[float], bool] | None = None) -> None:
        self.argv, self.env, self._on_message, self._log, self._popen, self._backoff = argv, env, on_message, log, popen, backoff
        self.stopped = threading.Event()
        self._wait = wait_stop or self.stopped.wait
        self.state = "restarting"
        self.restarts = 0
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._proc: Any = None
        self._pending: dict[str, Send] = {}
        self._n = 0
        self._timeouts = 0
        self._thread = threading.Thread(target=self._supervise, name="control-carrier-child", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.stopped.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            self._terminate(proc)
        self._thread.join(timeout=10)

    @staticmethod
    def _terminate(proc: Any) -> None:
        with contextlib.suppress(OSError):
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                proc.kill()

    # -- supervision ---------------------------------------------------
    def _supervise(self) -> None:
        failures = 0
        while not self.stopped.is_set():
            ready = False
            try:
                proc = self._popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env)
            except OSError as e:
                self.state = "off"
                self._log(f"cannot start {self.argv[0]} ({e}); channel off")
                rc = None
            else:
                os.set_blocking(proc.stdin.fileno(), False)   # a write that cannot finish is bounded, see _write
                with self._lock:
                    self._proc = proc
                threading.Thread(target=self._read_stderr, args=(proc,), name="control-carrier-stderr", daemon=True).start()
                ready = self._read_stdout(proc)
                rc = proc.wait()
                with self._lock:
                    self._proc = None
                for pipe in (proc.stdin, proc.stdout, proc.stderr):
                    with contextlib.suppress(OSError, ValueError, AttributeError):
                        pipe.close()
                self._fail_pending("the child ended")
                if not self.stopped.is_set():
                    self.state = "off" if rc in OFF_EXITS else "restarting"
                    self._log(f"the child exited {rc}" + (f": {EXIT_WORDS[rc]}" if rc in EXIT_WORDS else "")
                              + ("" if rc != 4 else " (it is not killed here)") + "; restarting")
            if self.stopped.is_set():
                return
            failures = 0 if ready else failures + 1
            self.restarts += 1
            if self._wait(self._backoff[min(max(failures - 1, 0), len(self._backoff) - 1)]):
                return

    def _read_stderr(self, proc: Any) -> None:
        for raw in proc.stderr:
            line = raw.decode("utf-8", "replace").strip()
            if line:
                self._log(f"interweave-human: {js.slice(line, 300)}")

    def _read_stdout(self, proc: Any) -> bool:
        ready = False
        for raw in proc.stdout:
            try:
                ev = js.json_parse(raw.decode("utf-8", "replace"))
            except ValueError:
                self._log(f"a line that is not JSON: {js.slice(raw.decode('utf-8', 'replace').strip(), 120)}")
                continue
            if not isinstance(ev, dict):
                continue
            try:
                ready = self._event(ev) or ready
            except Exception as e:  # noqa: BLE001 — one event that breaks a handler must not end the supervisor's reader
                self._log(f"an event broke its handler ({type(e).__name__}: {js.slice(str(e), 200)})")
        return ready

    def _event(self, ev: dict) -> bool:
        """One line of the child's stdout; True when it was `session ready`."""
        kind = ev.get("event")
        if kind == "session":
            if ev.get("session") == "ready":
                self.state = "ok"
                self._timeouts = 0
                return True
            self.state = "restarting"
            self._log(f"session {js.string(ev.get('session'))}")
        elif kind == "message":
            self._on_message(ev)
        elif kind == "outbound":
            self._outbound(ev)
        elif kind == "input-refused":
            self._resolve(ev.get("ref"), False, f"the child refused the line: {js.string(ev.get('reason'))}")
        return False

    # -- sends ---------------------------------------------------------
    def _resolve(self, ref: Any, ok: bool, why: str = "") -> None:
        with self._lock:
            send = self._pending.pop(ref, None) if isinstance(ref, str) else None
        if send is not None:   # the child prints each outbound twice: the second finds nothing, and is ignored
            send.finish(ok, why)

    def _outbound(self, ev: dict) -> None:
        status, problem = ev.get("status"), ev.get("problem")
        if problem is not None:
            self._resolve(ev.get("ref"), False, f"the daemon refused it: {js.string(problem)}")
        elif status == "accepted":
            self._resolve(ev.get("ref"), True)
        elif status in ("cancelled", "needs-attention"):
            self._resolve(ev.get("ref"), False, f"the send ended {status}")

    def _fail_pending(self, why: str) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
        for s in pending.values():
            s.finish(False, why)

    def send(self, conversation: str, text: str) -> Send:
        """One direct send, never pending: handed to the child now, or failed now when it is not ready. A send is
        never queued here for a later child: a request that waited past its ttl_s would only be refused."""
        with self._lock:
            proc = self._proc
            if self.state != "ok" or proc is None or proc.stdin is None:
                return failed(f"the InterWeave channel is {self.state}")
            self._n += 1
            ref = f"{os.getpid()}-{self._n}"
            send = Send(ref)
            self._pending[ref] = send
        line = js.stringify({"send": {"conversation": conversation, "text": text, "ref": ref, "pending": False}}) + "\n"
        # Outside `_lock`: the reader resolves outbound events under it, and a write that blocks must not stop it.
        problem = self._write(proc, line.encode("utf-8"))
        if problem:
            with self._lock:
                self._pending.pop(ref, None)
            return failed(problem)
        return send

    def _write(self, proc: Any, data: bytes) -> str | None:
        """The whole line or none of it is a line the child can read: a write the child does not drain within
        WRITE_WAIT_S leaves half a line in its pipe, so the child is ended as wedged (the supervisor restarts it)
        and the send fails; it is never left blocking the callers behind it."""
        with self._write_lock:
            end = time.monotonic() + WRITE_WAIT_S
            view = memoryview(data)
            try:
                fd = proc.stdin.fileno()   # inside the try: the supervisor closes it when the child has ended
                while view:
                    try:
                        view = view[os.write(fd, view):]
                    except BlockingIOError:
                        left = end - time.monotonic()
                        if left <= 0 or not select.select([], [fd], [], left)[1]:
                            self._log(f"the child did not drain its input in {WRITE_WAIT_S:g} s: ended as wedged")
                            self.state = "restarting"   # later sends fail at once, before the supervisor has seen the exit
                            self._terminate(proc)
                            return "the child does not drain its input"
            except (OSError, ValueError) as e:
                return f"the child's input is closed ({e})"
        return None

    def settle(self, send: Send, wait_s: float) -> tuple[bool, str]:
        """Wait for a send's outcome; a child that answers nothing three sends running is wedged and ended (the
        supervisor restarts it), a restart that costs the lease only for a moment."""
        ok, why = send.wait(wait_s)
        if ok or send.ref == "-" or send._done.is_set():
            if ok:
                self._timeouts = 0
            return ok, why
        with self._lock:
            self._pending.pop(send.ref, None)
            self._timeouts += 1
            wedged, proc = self._timeouts >= WEDGED_AFTER, self._proc
        if wedged and proc is not None:
            self._log(f"the child answered nothing for {WEDGED_AFTER} sends: ended as wedged")
            self._timeouts = 0
            self.state = "restarting"
            self._terminate(proc)
        return False, why


# ── the router ───────────────────────────────────────────────────────

class Carrier:
    """Inbound records are judged (prefix, roster, `from`, op) and handed to `on_request` or to the fabric-ctl
    waiting for the reply; outbound ones go to `<peer>/fabric-control`."""

    def __init__(self, *, directory: Directory, child: Child, me: str, on_request: Callable[[dict, str], None],
                 arrivals: ArrivalLog, log: Callable[[str], None] = say) -> None:
        self.directory, self.child, self.me, self._on_request, self.arrivals, self._log = directory, child, me, on_request, arrivals, log
        self._waiters: dict[str, Callable[[dict, str], None]] = {}
        self._lock = threading.Lock()
        self.inbox = Inbox(self.inbound, log)
        child._on_message = self.inbox.put

    def start(self) -> None:
        self.inbox.start()
        self.child.start()

    def stop(self) -> None:
        self.child.stop()
        self.inbox.close()

    # -- in ------------------------------------------------------------
    def inbound(self, ev: dict) -> None:
        if ev.get("direction") not in (None, "in"):
            return
        # A row drained from the store at session open names no endpoint; fabric-control is the profile's only
        # human endpoint (the render, R3), so null is ours. Another endpoint's is not.
        if ev.get("local_endpoint") not in (None, ENDPOINT):
            return
        author, text = ev.get("author"), ev.get("text")
        sender = self.directory.address_of(author)
        if sender is None:
            self._log(f"dropped a message from a PeerId the roster does not hold ({js.slice(js.string(author), 60)})")
            return
        try:
            record = unframe(text)
        except Refused as e:
            self._log(f"dropped a message from {sender}: {e}")
            return
        kind, frm = record.get("kind"), record.get("from")
        if frm != sender:
            self.arrivals.add(VIA, record, "forged-from", sender)
            self._log(f"dropped a {js.string(kind)} from {sender} that says it is from {js.slice(js.string(frm), 60)}")
            return
        if isinstance(record.get("op"), str) and record["op"] in RELAY_ONLY_OPS:
            self.arrivals.add(VIA, record, "relay-only-op", sender)
            self._log(f"dropped {record['op']} from {sender}: that op goes on the relay only")
            return
        if kind == "request":
            self.arrivals.add(VIA, record, "ok", sender)
            self._on_request(record, sender)
        elif kind == "reply":
            with self._lock:
                waiter = self._waiters.get(record.get("in_reply_to")) if isinstance(record.get("in_reply_to"), str) else None
            self.arrivals.add(VIA, record, "ok" if waiter else "no-waiter", sender)
            if waiter is not None:
                waiter(record, sender)
        else:
            self._log(f"dropped a {js.slice(js.string(kind), 20)} record from {sender}")

    def watch(self, request_id: str, waiter: Callable[[dict, str], None]) -> None:
        with self._lock:
            self._waiters[request_id] = waiter

    def unwatch(self, request_id: str) -> None:
        with self._lock:
            self._waiters.pop(request_id, None)

    # -- out -----------------------------------------------------------
    def start_send(self, address: str, record: dict) -> Send:
        if address == self.me:
            return failed("this account (the relay carries it)")
        peer = self.directory.peer_of(address)
        if peer is None:
            return failed("no roster row")
        return self.child.send(f"{peer}/{ENDPOINT}", frame(record))

    def send_to(self, addresses: Iterable[str], record: dict, wait_s: float) -> dict[str, tuple[bool, str]]:
        """One direct send per address, all handed to the child before any is waited on."""
        started = [(a, self.start_send(a, record)) for a in addresses]
        deadline = time.monotonic() + wait_s
        return {a: self.child.settle(s, deadline - time.monotonic()) for a, s in started}

    def reply(self, request: dict, reply: dict) -> None:
        """The same reply a relay copy was posted for, to the sender's own PeerId. Nothing here raises: the relay
        copy is posted first and is the record."""
        op = request.get("op")
        if isinstance(op, str) and op in RELAY_ONLY_OPS:
            return
        to = request.get("from")
        ok, why = self.send_to([to], reply, SEND_WAIT_S)[to] if isinstance(to, str) else (False, "no sender")
        if not ok:
            self._log(f"reply {js.slice(js.string(reply.get('id')), 8)} to {js.slice(js.string(to), 60)} not sent: {why}")


# ── fabric-ctl's socket ──────────────────────────────────────────────

def _peer_uid(conn: socket.socket) -> int:
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)[1]


class Server:
    """The operator's agentd end of fabric-ctl's sends. One connection is one request: a line
    {"v":1,"op":"send","to":[addresses],"record":{request},"wait_s":N}; the answer is a line {"event":"sent",
    "to":a,"ok":b,"why":s} per target, {"event":"sent-all"}, then {"event":"reply","carrier":"interweave",
    "from":sender,"record":{...}} for each verified reply to that request until `wait_s` or until the client
    closes. The socket is the account's own, mode 0600, in a 0700 directory, and a peer of another uid is
    closed unread; nothing here signs or decides: the record is the operator's, signed as fabric-ctl built it."""

    def __init__(self, path: str, carrier: Carrier, me: str, log: Callable[[str], None] = say) -> None:
        self.path, self.carrier, self.me, self._log = path, carrier, me, log
        self._sock: socket.socket | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        directory = os.path.dirname(self.path)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        if len(os.fsencode(self.path)) >= 104:
            raise OSError(f"{self.path} is too long for a socket path")
        with contextlib.suppress(FileNotFoundError):
            probe = socket.socket(socket.AF_UNIX)
            try:
                probe.settimeout(1)
                probe.connect(self.path)
            except OSError:
                os.unlink(self.path)   # nobody answers there: a stale socket of a dead daemon
            else:
                raise OSError(f"{self.path} is held by a running agentd")
            finally:
                probe.close()
        s = socket.socket(socket.AF_UNIX)
        old = os.umask(0o177)
        try:
            s.bind(self.path)
        finally:
            os.umask(old)
        os.chmod(self.path, 0o600)
        s.listen(8)
        self._sock = s
        threading.Thread(target=self._accept, name="control-carrier-socket", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            with contextlib.suppress(OSError):
                self._sock.close()
        with contextlib.suppress(OSError):
            os.unlink(self.path)

    def _accept(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), name="control-carrier-ctl", daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        with contextlib.closing(conn):
            try:
                if _peer_uid(conn) != os.getuid():
                    self._log("closed a connection from another user")
                    return
                request = self._read_request(conn)
            except (OSError, Refused) as e:
                self._log(f"ctl request refused: {e}")
                with contextlib.suppress(OSError):
                    conn.sendall((js.stringify({"event": "refused", "why": str(e)}) + "\n").encode())
                return
            self._run(conn, request)

    @staticmethod
    def _read_request(conn: socket.socket) -> dict:
        conn.settimeout(5)
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                raise Refused("closed before a request")
            buf += chunk
            if len(buf) > MAX_SOCKET_LINE:
                raise Refused("request line too long")
        try:
            req = js.json_parse(buf.split(b"\n", 1)[0].decode("utf-8", "replace"))
        except ValueError as e:
            raise Refused("not JSON") from e
        if not isinstance(req, dict) or req.get("op") != "send" or not isinstance(req.get("record"), dict):
            raise Refused("not a send")
        to = req.get("to")
        if not isinstance(to, list) or not all(isinstance(a, str) for a in to):
            raise Refused("`to` is a list of addresses")
        wait = req.get("wait_s")
        if isinstance(wait, bool) or not isinstance(wait, (int, float)) or not 0 < wait <= MAX_WAIT_S:
            raise Refused("`wait_s` is a number of seconds")
        rec = req["record"]
        if rec.get("kind") != "request" or not isinstance(rec.get("id"), str) or not rec["id"]:
            raise Refused("the record is not a request with an id")
        if isinstance(rec.get("op"), str) and rec["op"] in RELAY_ONLY_OPS:
            raise Refused(f"{rec['op']} goes on the relay only")
        return req

    def _run(self, conn: socket.socket, req: dict) -> None:
        rec, rid, lock = req["record"], req["record"]["id"], threading.Lock()

        def put(obj: dict) -> None:
            # Called on the inbox thread: a fabric-ctl that stopped reading must not stop every other message, so a
            # write that cannot finish in SOCKET_SEND_S drops this connection and its waiter instead.
            with lock:
                try:
                    conn.sendall((js.stringify(obj) + "\n").encode("utf-8"))
                except OSError as e:
                    self._log(f"fabric-ctl's connection for {rid[:8]} is not reading ({e}): dropped")
                    self.carrier.unwatch(rid)
                    with contextlib.suppress(OSError):
                        conn.shutdown(socket.SHUT_RDWR)

        if rec.get("from") != self.me:
            put({"event": "refused", "why": f"the record is from {js.string(rec.get('from'))}, this agentd is {self.me}'s"})
            return
        self.carrier.watch(rid, lambda record, sender: put({"event": "reply", "carrier": VIA, "from": sender, "record": record}))
        try:
            wait_s = float(req["wait_s"])
            # A request's send never outlives its own ttl_s (rule 18): the budget of the sends is the smaller.
            ttl = rec.get("ttl_s")
            budget = min(wait_s, float(ttl)) if isinstance(ttl, (int, float)) and not isinstance(ttl, bool) and ttl > 0 else wait_s
            targets = list(dict.fromkeys(req["to"]))
            for address, (ok, why) in self.carrier.send_to(targets, rec, budget).items():
                put({"event": "sent", "to": address, "ok": ok, "why": why})
            put({"event": "sent-all"})
            end = time.monotonic() + wait_s
            conn.settimeout(SOCKET_SEND_S)   # bounds put(); the loop below reads only what select says is there
            while not self._stop.is_set() and (left := end - time.monotonic()) > 0:
                try:
                    readable, _, _ = select.select([conn], [], [], min(left, 0.5))
                    if readable and not conn.recv(4096):
                        break   # fabric-ctl is done
                except (OSError, ValueError):
                    break       # the connection was reset or dropped by put()
        finally:
            self.carrier.unwatch(rid)


class Session:
    """fabric-ctl's end: connect, hand over the request, read the sends' outcomes, then take replies as they
    come. Any failure to reach the operator's agentd is a RuntimeError the caller says in one line; the relay
    has the request already, so it is "relay only", never a failed command."""

    def __init__(self, path: str, record: dict, to: list[str], wait_s: float, *, connect_s: float = 5.0) -> None:
        self._buf = b""
        self.sent: dict[str, tuple[bool, str]] = {}
        self._conn = socket.socket(socket.AF_UNIX)
        try:
            self._conn.settimeout(connect_s)
            self._conn.connect(path)
            self._conn.sendall((js.stringify({"v": 1, "op": "send", "to": to, "record": record, "wait_s": wait_s}) + "\n").encode("utf-8"))
        except OSError as e:
            self._conn.close()
            raise RuntimeError(f"the operator's agentd does not answer on {path} ({e})") from e

    def _lines(self, timeout_s: float) -> list[dict]:
        """Whole lines available within the time; [] on none. A closed connection is a RuntimeError."""
        out: list[dict] = []
        end = time.monotonic() + timeout_s
        while True:
            while b"\n" in self._buf:
                raw, self._buf = self._buf.split(b"\n", 1)
                try:
                    ev = js.json_parse(raw.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if isinstance(ev, dict):
                    out.append(ev)
            if out:
                return out
            readable, _, _ = select.select([self._conn], [], [], max(0.0, end - time.monotonic()))
            if not readable:
                return out
            chunk = self._conn.recv(262144)
            if not chunk:
                raise RuntimeError("the operator's agentd closed the connection")
            self._buf += chunk

    def wait_sent(self, timeout_s: float) -> list[dict]:
        """Read until `sent-all` (or `refused`), returning any reply that came with them."""
        replies: list[dict] = []
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            for ev in self._lines(end - time.monotonic()):
                if ev.get("event") == "sent" and isinstance(ev.get("to"), str):
                    self.sent[ev["to"]] = (ev.get("ok") is True, js.string(ev.get("why")))
                elif ev.get("event") == "sent-all":
                    return replies
                elif ev.get("event") == "refused":
                    raise RuntimeError(f"the operator's agentd refused the sends: {js.string(ev.get('why'))}")
                elif ev.get("event") == "reply":
                    replies.append(ev)
        raise RuntimeError("the operator's agentd did not finish the sends in time")

    def poll(self, timeout_s: float) -> list[dict]:
        return [ev for ev in self._lines(timeout_s) if ev.get("event") == "reply"]

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._conn.close()


class Down(Exception):
    """Neither carrier took a request: the relay's failure and why the other carrier was not there to carry it.
    It keeps what the relay's own error said about the post (`status`, `connection_refused`, `sent`), so a caller
    that classifies a failed post — certainly nothing left, or unknown — classifies it as before; when the socket
    may have been handed the request, `handed` is true and those are cleared, because then nothing is certain."""

    worded = True   # its message already says both failures; a caller does not re-word it from the relay's alone

    def __init__(self, message: str, relay_error: BaseException | None = None, handed: bool = False) -> None:
        super().__init__(message)
        self.status = None if handed else getattr(relay_error, "status", None)
        self.connection_refused = False if handed else getattr(relay_error, "connection_refused", False)
        self.timed_out = getattr(relay_error, "timed_out", False)
        if getattr(relay_error, "sent", False) is True:
            self.sent = True


class LegFailed(RuntimeError):
    """The InterWeave leg of a request could not be had; `handed` says whether the request may have left anyway."""

    def __init__(self, message: str, handed: bool = False) -> None:
        super().__init__(message)
        self.handed = handed


class Leg:
    """The InterWeave half of one request this process asks of its account's own agentd (the 0600 socket above):
    the presence check and the job queue's holder, which a relay that is down must not stop (ADR-029 rule 18).
    The relay post stays the record and goes first; this is the second way the same request travels, and a
    reply on either answers it. What comes back is the roster-authenticated sender with the record, so a reply
    is attributed to the PeerId's address, never to the `from` it claims."""

    def __init__(self, session: Session, rid: str, early: list[dict] | None = None) -> None:
        # `early`: replies that came with the sends' outcomes, before anyone polled.
        self._session, self._rid, self.lost, self._early = session, rid, False, list(early or [])

    @classmethod
    def open(cls, record: dict, to: list[str], wait_s: float, *, env: dict[str, str] | None = None) -> "Leg":
        path = socket_path(env)
        if path is None:
            raise LegFailed("XDG_RUNTIME_DIR is not set, so there is no socket to this account's agentd")
        session = None
        try:
            session = Session(path, record, to, wait_s)
            early = session.wait_sent(wait_s + 2)
        except RuntimeError as e:
            # A session that was made had the request handed to it: whether it left is unknown. One that was not
            # made (the socket absent, refused) sent nothing.
            if session is not None:
                session.close()
            raise LegFailed(str(e), handed=session is not None) from e
        lost = sorted(a for a, (ok, _why) in session.sent.items() if not ok)
        if len(lost) == len(session.sent):
            session.close()
            raise LegFailed(f"not sent to {', '.join(f'{a} ({session.sent[a][1]})' for a in lost)}")
        return cls(session, record["id"], early)

    def replies(self, timeout_s: float) -> list[tuple[str, dict]]:
        """(sender, record) for each reply to this request that arrived within the time. A connection that
        closed ends the leg (`lost`): nothing more will come by it."""
        events, self._early = self._early, []
        if not events and not self.lost:
            try:
                events = self._session.poll(timeout_s)
            except RuntimeError:
                self.lost = True
        return [(ev["from"], ev["record"]) for ev in events
                if isinstance(ev.get("from"), str) and isinstance(ev.get("record"), dict) and ev["record"].get("in_reply_to") == self._rid]

    def close(self) -> None:
        self._session.close()


# ── agentd's side ────────────────────────────────────────────────────

def child_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Only what interweave-human reads to find the profile and its daemon: never the session's tokens or proxy."""
    env = os.environ if env is None else env
    keep = ("PATH", "HOME", "LANG", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME")
    return {k: env[k] for k in keep if k in env}


def program_path(env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return os.path.join(env.get("HOME") or os.path.expanduser("~"), ".local", "bin", PROGRAM_NAME)


class Running:
    """What agentd holds while it carries on InterWeave: the router, fabric-ctl's socket, and the way out."""

    def __init__(self, carrier: Carrier, server: Server | None) -> None:
        self.carrier, self.server = carrier, server

    def reply(self, request: dict, reply: dict) -> None:
        self.carrier.reply(request, reply)

    def stop(self) -> None:
        if self.server is not None:
            self.server.stop()
        self.carrier.stop()


def default_directory(host: str, placed: Callable[[], set[str]], log: Callable[[str], None] = say) -> Directory:
    from gzcoord.carrier import main as carrier_main

    def rows() -> list[dict]:
        return carrier_main.verified_roster()[1]

    def stamp() -> tuple:
        out = []
        for path in (carrier_main.roster_path(), carrier_main.hosts_registry_path()):
            try:
                st = os.stat(path)
                out.append((st.st_mtime_ns, st.st_size))
            except OSError:
                out.append(None)
        return tuple(out)
    return Directory(rows, host, placed, stamp, log)


def start_for_agentd(*, me: str, on_request: Callable[[dict, str], None], placed: Callable[[], set[str]],
                     env: dict[str, str] | None = None, log: Callable[[str], None] = say,
                     directory: Directory | None = None, argv: list[str] | None = None) -> Running:
    """Start the child, the router and fabric-ctl's socket. Nothing here can stop agentd answering on the relay:
    a program that is not installed, a roster that does not verify and a socket that cannot be bound are each
    said and the account is on the relay alone until they are mended."""
    env = os.environ if env is None else env
    from control.upgrade import state_dir
    host = me.partition("/")[0]
    carrier = Carrier(directory=directory or default_directory(host, placed, log),
                      child=Child(argv or [program_path(env), *LISTEN_ARGS], child_env(env), lambda ev: None, log=log),
                      me=me, on_request=on_request, arrivals=ArrivalLog(os.path.join(state_dir(), "control-arrivals.jsonl"), "agentd", log=log), log=log)
    server: Server | None = None
    path = socket_path(env)
    if path is None:
        log("XDG_RUNTIME_DIR is not set: fabric-ctl has no socket to hand its sends to, and sends by the relay alone")
    else:
        server = Server(path, carrier, me, log)
        try:
            server.start()
        except OSError as e:
            log(f"fabric-ctl's socket cannot be served ({e}); fabric-ctl sends by the relay alone")
            server = None
    carrier.start()
    return Running(carrier, server)


# ── fabric-ctl's merge of the two carriers' copies ───────────────────

class Merge:
    """The copies of each reply and each reply part that arrived by each carrier, and the one that counts: the
    InterWeave copy wherever both arrive (its sender is authenticated by PeerId; the relay's `from` is a claim,
    ADR-033 §6), the relay's otherwise. A relay copy that differs from the InterWeave one is flagged, never shown
    as the account's answer. A copy is compared as it arrived, before fabric-ctl adds its own fields."""

    def __init__(self) -> None:
        self._replies: dict[str, dict[str, tuple[dict, str]]] = {}
        self._parts: dict[tuple[str, str], dict[str, tuple[Any, str]]] = {}

    @staticmethod
    def _pick(copies: dict[str, tuple]) -> tuple:
        return copies["interweave"] if "interweave" in copies else copies["relay"]

    def add_reply(self, carrier: str, sender: str, record: dict) -> dict:
        """Keep the first copy per carrier; returns the record that counts now."""
        self._replies.setdefault(sender, {}).setdefault(carrier, (record, js.stringify(record)))
        return self._pick(self._replies[sender])[0]

    def add_part(self, carrier: str, sender: str, key: str, part: Any) -> Any:
        self._parts.setdefault((sender, key), {}).setdefault(carrier, (part, js.stringify(part)))
        return self._pick(self._parts[(sender, key)])[0]

    def has_reply(self, sender: str) -> bool:
        return sender in self._replies

    def carriers_of(self, sender: str) -> set[str]:
        return set(self._replies.get(sender, {}))

    def verdict(self, sender: str) -> dict:
        """The row's carrier fields for an account that answered: which copy counts, whether the relay's agreed."""
        copies = self._replies.get(sender, {})
        pieces = [c for (s, _k), c in self._parts.items() if s == sender]
        if "interweave" not in copies:
            return {"carrier": "relay only"}
        relay_copy = "missing" if "relay" not in copies else (
            "same" if copies["relay"][1] == copies["interweave"][1] else "differs")
        for c in pieces:
            if "relay" in c and "interweave" in c and c["relay"][1] != c["interweave"][1]:
                relay_copy = "differs"
        out = {"carrier": VIA, "relay_copy": relay_copy}
        if relay_copy == "differs":
            out["relay_differs"] = True
        return out

    def waiting_for_other(self, senders: Iterable[str], interweave_expected: set[str]) -> bool:
        """An answered account still has a copy to come: its InterWeave copy (the send went out) or its relay copy."""
        for s in senders:
            have = self.carriers_of(s)
            if (s in interweave_expected and "interweave" not in have) or "relay" not in have:
                return True
        return False
