"""tools/fabric/control/agentd.py — the control agent (ADR-040 Wave 8): the
Python port of runtime/control/agentd.mjs, which step s8 deleted; the unit
runs this file under the pinned fabric-python. One process per account, run as the
login: it answers the coordinator's requests on the control channel with
what the account can say about itself (control/ops), and carries out the
signed actions (upgrade, secrets-sync, jobs-add, local-prune,
secrets-selftest, pool-add, tools-install).

  python3 tools/fabric/control/agentd.py          the daemon: block, answer, repeat
  python3 tools/fabric/control/agentd.py --once   answer what is pending, then exit
  python3 tools/fabric/control/agentd.py --self   print this account's status, no relay

THE RULES OF THE CHANNEL, THE READ AND THE FENCE (carried over from the Node's
header, deleted in step s8):

THE CHANNEL. runtime/control/config.json names it (fabric:control) and
the relay — the same one the fleet's GZCoord traffic rides. A control
channel carries JSON records, not GZCOORD/1 messages, and no session
ever drains it (inbox.py refuses a channel ending in :control). There
is no point-to-point delivery: every agent reads every record and
answers the ones addressed to it (`to` its address, a list holding it,
or "*"); the coordinator reads the replies by `in_reply_to`.

THE READ. No consumer cursor and no ack: the relay's `since_id` is an
explicit cursor, so a restart never replays history — the agent primes
from the newest record on the channel and waits after it, 55 s a poll.
A `since_id_not_found` (the relay's history was cleared) re-primes.

THE FENCE, v1. A request is answered only when its `from` is a host
operator's address as runtime/hosts/registry.json places it — except a
PUBLIC op (control/ops PUBLIC_OPS: `presence`, `pool-list` and `pool-claim`), answered for any placed
<host>/<login>, since every sender needs it and a relay-token holder
could already get it by forging an operator's `from` on an unsigned
read op (pool-claim is the one unsigned op that writes: one field, the
claimant, ADR-029 §5 rule 4) — read
again for every record, so a pull that changes the registry counts at
once, and the identity section asks whoami() per request, so a rebind
shows without a restart (review, 2026-09-17) — (a claim,
not a proof — the relay verifies no sender; it stops any other session
from asking), its op is one of the closed set, its `ts` plus `ttl_s` is
not in the past, and its id was not seen before (an LRU of 256). An
ACTION op (sign.ACTION_OPS) additionally needs `sig`, an Ed25519
signature by the operator's committed key, lives at most 10 minutes,
and must be newer than the last action accepted from that operator (a
ledger in the account's fabric state), and no more than a minute in
its future. A read op takes no argument but `tokens`'s `days` (a number
capped at 90), pool-list's `role` and pool-claim's `id`; an action takes
only its closed set (checkArgs in upgrade.mjs and secrets.mjs,
checkJobArgs in jobs.mjs, checkPoolArgs in pool.mjs). No field of a
request ever reaches a shell; the answer carries no secret (control/ops).

Every reply arrives: a section that cannot be read says so inline.
Relay down: one line on stderr, retry every 30 s; a refused token is
re-read once from the synced file (a rotation), then reported.

CONTRACT, frozen from agentd.mjs. Kept byte for byte: every
record posted (key order, ids, timestamps' shape), every refusal's reason
text, every stderr line, the exit codes (0; 1 the relay failed in --once or
an unforeseen error; 3 no token or no host operator; 4 --once and the token
was refused), the order a request is checked in, the LRU of 256 seen ids,
the action ledger's file and shape, the 30 s retry and the 55 s poll.
The names that other modules import are as before: control_config, new_id,
operator_addresses, account_addresses, number_of.

WHERE THE PORT DIFFERS (each listed because a reader of the Node would look):
  - Threads stand where the Node had promises. An action (ACTION_OPS) and a
    disk read run in a thread beside the read loop; --once and a restart
    wait for them. The set of running ones is guarded by the leaver's lock,
    so a restart asked for while one is being started either waits for it or
    comes first, never between.
  - What a restart is: the Node watched the *.mjs and *.json files of its own
    directory. The Python daemon watches the files of the modules it has
    loaded (sys.modules, under the code root) and runtime/control/config.json:
    exactly what a pull can change under it, and nothing the Node alone
    loads. By polling (1 s) where the Node had inotify, after the same 2 s
    quiet period.
  - The ledger file: a file that holds an array is read as a ledger that
    holds nothing, as the Node read it (an array has none of the senders as
    keys), but is then written as the object it should have been; the Node
    wrote back `[]` and so never recorded the action. Its temporary file is
    removed when the write fails.
  - A timer that raises is said on stderr (`agentd: <name> failed: …`) and
    runs again; the Node's would have ended the process.
  - Exit from another thread (a restart) is os._exit after stderr is
    flushed: sys.exit would end the thread only.
  - SIGTERM is not caught, as in the Node: the process ends where it is and
    systemd's Restart= does the rest. SIGINT is an exit 130 without a
    traceback.
  - tools_opts (the `tools` op) and install_opts (the `tools-install` op) are
    two keys of the context; the Node's toolsOpts served both.
"""
from __future__ import annotations

import errno
import math
import os
import sys
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable, Iterable

# Run as a script, this directory would lead sys.path and its queue.py would
# shadow the standard library's for any module importing it (gzcoord.py).
if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from control import gzcoord, js, ops, pressure, sessions, tools as tools_mod  # noqa: E402
from control.gzcoord import FABRIC_ROOT  # noqa: E402
from control.jobs import jobs_add  # noqa: E402
from control.local import local_prune  # noqa: E402
from control.pool import POOL_FILE, pool_add, pool_claim, pool_holder, pool_list, role_from_stream  # noqa: E402
from control.secrets import secrets_sync  # noqa: E402
from control.selftest import secrets_selftest  # noqa: E402
from control.sign import ACTION_OPS, ACTION_TTL_MAX_S, public_key_from, verify_request  # noqa: E402
from control.upgrade import state_dir, upgrade  # noqa: E402
from gzcoord import gzmsg  # noqa: E402
import roots  # noqa: E402

CONFIG = os.path.join(roots.code_root(), "runtime", "control", "config.json")


def number_of(v: Any) -> float:
    """Number(v) for a JSON value."""
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return js.number(js.string(v))


def control_config(env: dict[str, str] | None = None, file: str | None = None) -> dict:
    env = os.environ if env is None else env
    own: Any = {}
    try:
        with open(CONFIG if file is None else file, encoding="utf-8", errors="replace") as fh:
            own = js.json_parse(fh.read())
    except (OSError, ValueError):
        pass   # defaults below
    if own is None:
        # `null` parses: the Node reads `own.relay_url` outside its try and
        # throws. A config that says nothing at all is a defect to see.
        raise TypeError("runtime/control/config.json is null: it holds an object or nothing")
    if not isinstance(own, dict):
        own = {}   # another JSON value has no such keys, and the defaults apply as they do there

    def pick(name: str, key: str, default: str) -> Any:
        if name in env:
            return env[name]
        return own[key] if own.get(key) is not None else default
    ttl = number_of(own.get("ttl_s"))
    return {
        "relay_url": pick("CLAUDE_BRIDGE_URL", "relay_url", "http://127.0.0.1:8765"),
        "channel": pick("FABRIC_CONTROL_CHANNEL", "channel", "fabric:control"),
        # Session state rides its own channel (ADR-029 rule 16), named to end
        # in :control like the control channel, so no inbox ever drains it.
        "state_channel": pick("FABRIC_STATE_CHANNEL", "state_channel", "fabric:state:control"),
        "ttl_s": (int(ttl) if ttl.is_integer() else ttl) if ttl > 0 and ttl != math.inf else (math.inf if ttl > 0 else 30),
    }


def new_id() -> str:
    return gzmsg.mint_id()


def _registry(registry: str | None) -> Any:
    path = roots.hosts_registry(engine=FABRIC_ROOT, empty_is_set=True) if registry is None else registry
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return js.json_parse(fh.read())
    except (OSError, ValueError):
        return None


def _entries(o: Any) -> list[tuple[str, Any]]:
    """Object.entries(o): an array's elements are keyed by their index."""
    if isinstance(o, dict):
        return [(k, o[k]) for k in js.keys(o)]
    if isinstance(o, list):
        return [(str(i), v) for i, v in enumerate(o)]
    return []


def operator_list(registry: str | None = None) -> list[str]:
    """The operators in the registry's order (the Node's Set kept it, and
    the start-up line prints it)."""
    d = _registry(registry)
    out: dict[str, None] = {}
    for h, v in _entries(d.get("hosts") if isinstance(d, dict) else None):
        if v is None:
            return []   # `v.operator` throws on null, inside the Node's try: nobody
        op = v.get("operator") if isinstance(v, dict) else None
        out[f"{h}/{js.string(op) if op is not None else 'user'}"] = None
    return list(out)


def operator_addresses(registry: str | None = None) -> set[str]:
    return set(operator_list(registry))


def account_addresses(registry: str | None = None) -> set[str]:
    d = _registry(registry)
    return {f"{js.string(host)}/{login}" for login, host in _entries(d.get("placement") if isinstance(d, dict) else None)}


SEEN_MAX = 256
USAGE_CACHE_MS = 10000
# An observed account's sign-in lives 8 hours and only a read renews it,
# so the keeper reads every 4 h — twice inside the lifetime, so one failed
# read (the relay down, a harness update mid-run) is not a lapse. A request
# inside ACCOUNTS_CACHE_MS gets the last reading, not a new harness run.
ACCOUNTS_KEEPALIVE_MS = 4 * 3600 * 1000
ACTION_CLOCK_SKEW_MS = 60 * 1000
ACCOUNTS_CACHE_MS = 5 * 60 * 1000
# Reads that run beside the read loop, like the actions: each can take
# minutes, and the loop must keep answering behind it.
BESIDE_LOOP_OPS = ["disk"]
# One disk scan per daemon, shared by every request that arrives while it
# runs, and its answer kept a minute: any placed account may post the read
# unsigned, and fifty requests started a hundred du (review of #92, round 4).
DISK_CACHE_MS = 60000
RETRY_S = 30
POLL_S = 55
QUIET_S = 2          # a pull writes several files; one restart for one pull
WATCH_POLL_S = 1.0
# What is not logged: every reply on the channel (not a request), a request
# for another account (not for me) and a duplicate (seen) — fifteen daemons
# times fifteen replies per fabric-ctl would be noise. Every other refusal
# is one line, so a refused operator can be found.
QUIET = ("not a request", "not for me", "seen")


def _stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _now_ms() -> float:
    return time.monotonic() * 1000


def _round(x: float) -> int:
    """Math.round: halves go up."""
    return math.floor(x + 0.5)


def _is_one(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == 1


def _code(e: BaseException) -> str:
    """The Node's `e.code ?? e.message`."""
    if isinstance(e, OSError) and e.errno:
        return errno.errorcode.get(e.errno) or str(e)
    return str(e)


class AccountsKeeper:
    """One reading at a time, shared: the keeper's timer and a request that
    arrive together wait on the same run, because two harness runs on one
    config directory race for its refresh lock. A failed run reaches every
    caller that joined it and releases the slot for the next."""

    def __init__(self, read: Callable[[], Any], now: Callable[[], float] = _now_ms, cache_ms: float = ACCOUNTS_CACHE_MS):
        self._read, self._now, self._cache_ms = read, now, cache_ms
        self._lock = threading.Lock()
        self._running: Future | None = None
        self._at, self._last = 0.0, None

    def refresh(self) -> Any:
        with self._lock:
            owner = self._running is None
            if owner:
                self._running = Future()
            fut = self._running
        if owner:
            try:
                r = self._read()
                with self._lock:
                    self._last, self._at = r, self._now()
                fut.set_result(r)
            except BaseException as e:  # noqa: BLE001 — every joined caller gets the failure, the slot is released
                fut.set_exception(e)
            finally:
                with self._lock:
                    self._running = None
        return fut.result()

    def cached(self) -> Any:
        with self._lock:
            if self._last is not None and self._now() - self._at < self._cache_ms:
                return self._last
        return self.refresh()


def accounts_keeper(read: Callable[[], Any] | None = None, now: Callable[[], float] = _now_ms,
                    cache_ms: float = ACCOUNTS_CACHE_MS) -> AccountsKeeper:
    return AccountsKeeper(read or (lambda: ops.accounts()), now, cache_ms)


def _registry_file() -> str:
    return roots.hosts_registry(engine=FABRIC_ROOT, empty_is_set=True)


def operator_keys(registry: str | None = None) -> dict[str, bytes]:
    """Each operator's public key (`operator_key`), read like the addresses:
    again for every record, so a rotation committed to the registry counts at
    the next pull. A host with no key, or a malformed one, has none — its
    operator can still ask what an account reports, and can order nothing."""
    out: dict[str, bytes] = {}
    d = _registry(registry)
    for h, v in _entries(d.get("hosts") if isinstance(d, dict) else None):
        if v is None:
            return out   # `v.operator_key` throws on null inside the Node's try, which keeps the keys read before it
        spec = v.get("operator_key") if isinstance(v, dict) else None
        try:
            key = public_key_from(spec) if spec is not None else None
        except Exception:  # noqa: BLE001 — openssl missing or too slow is the Node's null: the operator has no usable key
            key = None
        if key:
            op = v.get("operator") if isinstance(v, dict) else None
            out[f"{h}/{js.string(op) if op is not None else 'user'}"] = key
    return out


class ActionLedger:
    """The replay defence for ACTIONS, persisted: the newest accepted action's
    timestamp per operator, in the account's fabric state. The seen-id LRU is
    in memory — a restart empties it, and 256 unsigned read requests evict
    it — so a signed action copied off the channel could be posted again
    inside its lifetime and stop a session again (review of #34). An action
    is accepted only when strictly newer than the last one from its sender."""

    def __init__(self, file: str | None = None):
        self.file = os.path.join(state_dir(), "actions-seen.json") if file is None else file

    def _read(self) -> dict:
        try:
            with open(self.file, encoding="utf-8", errors="replace") as fh:
                d = js.json_parse(fh.read())
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

    def floor(self, sender: str) -> float:
        n = number_of(self._read().get(sender, js.UNDEFINED))
        return n if n == n and n else 0.0

    def record(self, sender: str, ts: float) -> None:
        d = self._read()
        n = number_of(d.get(sender, js.UNDEFINED))
        if (n if n == n and n else 0.0) >= ts:
            return
        d[sender] = int(ts) if float(ts).is_integer() else ts
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        tmp = f"{self.file}.{os.getpid()}.tmp"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(js.stringify(d) + "\n")
            os.rename(tmp, self.file)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def action_ledger(file: str | None = None) -> ActionLedger:
    return ActionLedger(file)


def accept(rec: dict, *, me: dict, operators: set, accounts: set | None = None, keys: dict | Callable[[], dict] | None = None, ttl_s: float,
           seen: set, now: float | None = None, action_floor: Callable[[str], float] = lambda _from: 0) -> dict:
    """Is this record a request this agent answers? The reason when not, for
    the log; never an error, never a reply."""
    accounts = set() if accounts is None else accounts
    # `keys` is a mapping or a function giving one: parsing a key starts
    # openssl, which only an action's signature check needs.
    keys = {} if keys is None else keys
    now = time.time() * 1000 if now is None else now
    try:
        r = js.json_parse(js.string(rec.get("content", js.UNDEFINED)))
    except ValueError:
        return {"ok": False, "why": "not json"}
    if not isinstance(r, dict) or r.get("kind") != "request":
        return {"ok": False, "why": "not a request"}
    if not _is_one(r.get("v")):
        return {"ok": False, "why": f"v {js.string(r.get('v', js.UNDEFINED))}"}
    rid = r.get("id")
    if not isinstance(rid, str) or not rid:
        return {"ok": False, "why": "no id"}
    if rid in seen:
        return {"ok": False, "why": "seen"}
    to = r.get("to") if isinstance(r.get("to"), list) else [r.get("to", js.UNDEFINED)]
    if "*" not in to and me["address"] not in to:
        return {"ok": False, "why": "not for me"}
    op = r.get("op", js.UNDEFINED)
    if not (isinstance(op, str) and op in ops.OPS):
        return {"ok": False, "why": f"op {js.slice(js.string(op), 20)}"}
    public = op in ops.PUBLIC_OPS
    sender = r.get("from")
    if not (isinstance(sender, str) and (sender in operators or (public and sender in accounts))):
        return {"ok": False, "why": f"from {js.slice(js.string(r.get('from', js.UNDEFINED)), 40)} is not an operator"
                                    f"{' or a placed account' if public else ''}"}
    action = op in ACTION_OPS
    short = js.slice(js.string(sender), 40)
    # An action is ordered, not asked: only a signature by the operator's
    # own key (control/sign.py) proves the operator sent it.
    if action and not verify_request(r, (keys() if callable(keys) else keys).get(sender)):
        return {"ok": False, "why": f"{op}: not signed by {short}'s key"}
    from control.sessions import date_parse
    ts = date_parse(js.string(r.get("ts", js.UNDEFINED)))
    n = number_of(r.get("ttl_s", js.UNDEFINED))
    ttl = min(n, ACTION_TTL_MAX_S if action else 3600) if n > 0 else ttl_s
    if not math.isfinite(ts) or ts + ttl * 1000 < now:
        return {"ok": False, "why": "expired"}
    # An action dated in the future would raise the ledger's floor past
    # every honest action that follows until the clock caught up — one
    # request signed on a fast clock locks the operator out (review of #34).
    if action and ts - now > ACTION_CLOCK_SKEW_MS:
        return {"ok": False, "why": f"{op}: dated {_round((ts - now) / 1000)} s in the future (the operator's clock?)"}
    if action and not ts > action_floor(sender):
        return {"ok": False, "why": f"{op}: not newer than the last action accepted from {short} (a replay)"}
    return {"ok": True, "request": r, "ts": ts}


class Seen(dict):
    """The LRU of ids already answered, oldest first: a Map's order, the one
    remember() evicts by."""

    def add(self, k: str) -> None:
        self.setdefault(k, None)

    def discard(self, k: str) -> None:
        self.pop(k, None)


def remember(seen: Any, rid: str) -> None:
    seen.add(rid)
    if len(seen) > SEEN_MAX:
        seen.discard(next(iter(seen)))


def loaded_sources() -> list[str]:
    """The files a pull can change under this process: the modules it has
    imported from the code root, and the control plane's configuration."""
    root = roots.code_root()
    files = {CONFIG}
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        if isinstance(f, str) and f.endswith(".py") and os.path.realpath(f).startswith(root + os.sep):
            files.add(f)
    return sorted(files)


class SourceWatcher:
    """A pull that changes the daemon's own code must reach the daemon: a
    loaded module never reloads, so the process ends itself (after a quiet
    period, a pull writes several files) and the unit's Restart= starts the
    next one on the new tree. What is watched is what the daemon imports,
    never a file's content: a change to files it does not load must not
    restart it (review of #91). A file that appears, disappears or changes
    is a change."""

    def __init__(self, on_change: Callable[[], None], files: Callable[[], Iterable[str]] = loaded_sources,
                 poll_s: float = WATCH_POLL_S, quiet_s: float = QUIET_S, new_is_change: bool = False):
        self.on_change, self.files, self.poll_s, self.quiet_s = on_change, files, poll_s, quiet_s
        # A fixed directory's new file is a pull; the loaded modules grow by themselves.
        self.new_is_change = new_is_change
        self._stop = threading.Event()
        self._known = self._snapshot()
        self._changed_at: float | None = None
        self._thread = threading.Thread(target=self._run, name="agentd-source-watch", daemon=True)

    def _snapshot(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in self.files():
            try:
                st = os.stat(f)
                out[f] = (st.st_mtime_ns, st.st_size, st.st_ino)
            except OSError:
                out[f] = None
        return out

    def start(self) -> "SourceWatcher":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.poll_s):
            now = self._snapshot()
            if any((f in self._known or self.new_is_change) and self._known.get(f) != v for f, v in now.items()) or any(f not in now for f in self._known):
                self._changed_at = time.monotonic()
            self._known = {**now}
            if self._changed_at is not None and time.monotonic() - self._changed_at >= self.quiet_s:
                self._changed_at = None
                self.on_change()


def watch_source(on_change: Callable[[], None], files: Callable[[], Iterable[str]] = loaded_sources, **kw: Any) -> SourceWatcher:
    return SourceWatcher(on_change, files, **kw).start()


class Leaver:
    """Leaving for new code waits for every running action: the source watch
    fired the moment an `upgrade fabric` pulled this daemon's own code, and
    exiting then killed the process before it posted the reply the operator
    was waiting for. request() asks to leave; settle() is called as each
    action finishes, and leaves once none is left. A disk read runs there
    too (BESIDE_LOOP_OPS), so a restart also waits for a scan in flight.
    `lock` guards `inflight` for everyone who changes it."""

    def __init__(self, inflight: set, exit: Callable[[int], None] | None = None,  # noqa: A002 — the Node's word
                 log: Callable[[str], None] = _stderr):
        self.inflight, self._log = inflight, log
        self._exit = exit or self._leave
        self.why: str | None = None
        self.lock = threading.RLock()

    @staticmethod
    def _leave(code: int) -> None:
        sys.stderr.flush()
        os._exit(code)

    def settle(self) -> bool:
        with self.lock:
            if self.why is None or self.inflight:
                return False
            self._log(f"agentd: {self.why}; exiting for systemd to restart on the new code")
            self._exit(0)
            return True

    def request(self, reason: str) -> bool:
        with self.lock:
            self.why = self.why if self.why is not None else reason
            return self.settle()

    @property
    def pending(self) -> str | None:
        return self.why


def leaver(inflight: set, exit: Callable[[int], None] | None = None, log: Callable[[str], None] = _stderr) -> Leaver:  # noqa: A002
    return Leaver(inflight, exit, log)


def state_poster(call: Callable[..., Any], cfg: dict, address: str) -> Callable[[dict], Any]:
    """How a state record leaves: on the state channel, never the control
    channel, whose replies would push it out of a reader's window (ADR-029
    rule 16)."""
    return lambda content: call("/api/send", method="POST",
                                body=js.stringify({"channel": cfg["state_channel"], "sender": address, "content": js.stringify(content)}))


def up_record(address: str) -> dict:
    """The record agentd posts once when it comes up (protocol.py)."""
    return {"v": 1, "kind": "up", "from": address, "ts": js.iso_now()}


def _only(ctx: dict, key: str, *names: str) -> dict:
    """The options of one op out of a context's bag: the Node spread the same
    bag into all three pool ops, which each took what they know."""
    return {k: v for k, v in (ctx.get(key) or {}).items() if k in names}


def answer(request: dict, ctx: dict) -> dict:
    """A reply is one record; a `memory` reply is several: the first carries
    the bundles' reports and sizes, then one record per part
    ({part, parts, slug, chunk}) — the relay's message limit is 128 KiB and a
    drain is bigger. The coordinator reassembles by slug and part and
    verifies the sha256 the first record names. `_followups` rides on the
    first record in memory and is the caller's to strip."""
    op = request.get("op")
    me = ctx["me"]["address"]
    days = number_of(request.get("days", js.UNDEFINED))
    home, root = ctx.get("home"), ctx.get("root")
    pool_file = lambda: os.path.join(state_dir(), POOL_FILE)  # noqa: E731 — the Node's poolFile()
    if op == "ping":
        data: dict = {}
    elif op == "upgrade":
        data = {"upgrade": upgrade(request, me=me, **(ctx.get("upgrade_opts") or {}))}
    elif op == "secrets-sync":
        data = {"secrets-sync": secrets_sync(request, me=me, **(ctx.get("secrets_opts") or {}))}
    elif op == "jobs-add":
        data = {"jobs-add": jobs_add(request, home=home, root=root, **(ctx.get("jobs_opts") or {}))}
    elif op == "pool-add":
        data = {"pool-add": pool_add(request, me=me, holder=pool_holder(control_config()), file=pool_file(), **_only(ctx, "pool_opts", "known", "now"))}
    elif op == "pool-list":
        data = {"pool-list": pool_list(request, me=me, holder=pool_holder(control_config()), file=pool_file())}
    elif op == "pool-claim":
        data = {"pool-claim": pool_claim(request, me=me, holder=pool_holder(control_config()), file=pool_file(),
                                         **_only(ctx, "pool_opts", "role_of", "now"))}
    elif op == "tools-install":
        data = {"tools-install": tools_mod.tools_install(request, home=home, root=root, **(ctx.get("install_opts") or {}))}
    elif op == "local-prune":
        data = {"local-prune": local_prune(request, home=home, root=root)}
    elif op == "secrets-selftest":
        data = {"secrets-selftest": secrets_selftest(request, home=home, root=root, **(ctx.get("selftest_opts") or {}))}
    else:
        data = ops.collect(op, {**ctx, "days": min(days, 90)} if math.isfinite(days) and days > 0 else ctx)

    def head() -> dict:
        return {"v": 1, "kind": "reply", "id": new_id(), "in_reply_to": request.get("id"), "from": me, "op": op,
                "ts": js.iso_now(), "ok": True}
    started = ctx["started"]
    meta = {"agentd": {"pid": os.getpid(), "started": started,
                       "uptime_s": _round((time.time() * 1000 - sessions.date_parse(started)) / 1000)}}
    memory = data.get("memory") if isinstance(data, dict) else None
    bundles = memory.get("bundles") if isinstance(memory, dict) else None
    if op != "memory" or not js.truthy(bundles):
        return {**head(), "data": {**data, **meta}}
    parts: list[dict] = []
    shown = []
    for b in bundles:
        rest = {k: v for k, v in b.items() if k != "_parts"}
        chunks = b.get("_parts") or []
        for i, chunk in enumerate(chunks):
            parts.append({"slug": b.get("slug"), "part": i + 1, "parts": len(chunks), "chunk": chunk})
        shown.append(rest)
    first = {**head(), "data": {"memory": {**memory, "bundles": shown}, **meta, "parts": len(parts)}}
    return {**first, "_followups": [{**head(), "data": {"part": p}} for p in parts]}


class Ticker:
    """A timer that never keeps the process up: `fn` after `first_s`, then
    every `every_s`. One that raises is said and runs again."""

    def __init__(self, name: str, fn: Callable[[], Any], every_s: float, first_s: float = 0.0, log: Callable[[str], None] = _stderr):
        self.name, self.fn, self.every_s, self.first_s, self.log = name, fn, every_s, first_s, log
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"agentd-{name}", daemon=True)

    def start(self) -> "Ticker":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        wait = self.first_s
        while not self._stop.wait(wait):
            try:
                self.fn()
            except Exception as e:  # noqa: BLE001 — a timer's failure is said; the next tick runs
                self.log(f"agentd: {self.name} failed: {e}")
            wait = self.every_s


def start_tools_report(keeper: tools_mod.ToolsKeeper | None = None, every_ms: float = tools_mod.TOOLS_INTERVAL_MS,
                       binding_file: str | None = None, watch_every_ms: float = tools_mod.BINDING_POLL_MS,
                       stat: Callable[[str], float] = lambda f: os.stat(f).st_mtime * 1000) -> tools_mod.ToolsKeeper:
    """At start, then every `every_ms`, and when the binding file changes
    (tools.mjs startToolsReport). `fabric-tools --all` keeps the tools of
    the account's bound role only, and a rebind (fabric-role bind, then a
    relaunch) does not restart the daemon: the next session would start on
    the previous role's report for up to an hour. The binding file's mtime
    is the signal; an unreadable one is no change."""
    keeper = keeper or tools_mod.ToolsKeeper()
    Ticker("tools report", keeper.refresh, every_ms / 1000).start()
    if binding_file:
        def mtime() -> float | None:
            try:
                return stat(binding_file)
            except OSError:
                return None
        seen = [mtime()]

        def watch() -> None:
            now = mtime()
            if now is not None and now != seen[0]:
                seen[0] = now
                keeper.refresh_again()
        Ticker("tools binding watch", watch, watch_every_ms / 1000, first_s=watch_every_ms / 1000).start()
    return keeper


def _status_of(first: dict, op: str) -> str:
    section = (first.get("data") or {}).get(op)
    status = section.get("status") if isinstance(section, dict) else None
    return "?" if status is None else js.string(status)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    once = "--once" in argv
    self_only = "--self" in argv
    who = gzcoord.whoami()
    me = gzcoord.identity(who)
    cfg = control_config()
    started = js.iso_now()
    usage_lock = threading.Lock()
    usage_state: dict[str, Any] = {"at": None, "last": None}

    def usage_cached() -> Any:
        with usage_lock:
            if usage_state["at"] is None or _now_ms() - usage_state["at"] > USAGE_CACHE_MS:
                usage_state["last"] = ops.usage()
                usage_state["at"] = _now_ms()
            return usage_state["last"]
    keeper = accounts_keeper()
    disk_keeper = accounts_keeper(lambda: ops.disk(), cache_ms=DISK_CACHE_MS)
    # no `who`: identity() resolves it per request
    ctx: dict[str, Any] = {"me": me, "started": started, "usage_cached": usage_cached,
                           "accounts_cached": keeper.cached, "disk_cached": disk_keeper.cached}
    if self_only:
        r = answer({"id": "self", "op": "status"}, ctx)
        r.pop("_followups", None)
        print(js.stringify(r, 2))
        return 0

    root = gzcoord.inbox_root(who)
    gz = gzcoord.integration_config(who.get("project"))
    tok = gzcoord.token(root, gz if gz.get("configured") else None)
    if tok is None:
        tok = gzcoord.synced_token()
    if not tok:
        _stderr("agentd: no CLAUDE_BRIDGE_AUTH_TOKEN (fabric-secrets sync) — nothing to read with")
        return 3
    if not operator_addresses():
        _stderr("agentd: no host operator in runtime/hosts/registry.json — nothing could ever be answered; not starting")
        return 3
    seen = Seen()
    ledger = action_ledger()
    inflight: set = set()   # actions and disk reads running beside the loop; --once and a restart wait for them
    leave = leaver(inflight)
    token_lock = threading.Lock()
    token_box = [tok]

    def call(path_and_query: str, **init: Any) -> Any:
        try:
            return gzcoord.api(token_box[0], path_and_query, relay_url=cfg["relay_url"], **init)
        except gzcoord.ApiError as e:
            fresh = gzcoord.synced_token() if e.status in (401, 403) else None
            with token_lock:
                if fresh and fresh != token_box[0]:
                    token_box[0] = fresh
                    _stderr("agentd: token refused; retrying with the synced value")
                    retry = True
                else:
                    retry = False
            if not retry:
                raise
        return gzcoord.api(token_box[0], path_and_query, relay_url=cfg["relay_url"], **init)

    def post(content: dict) -> Any:
        return call("/api/send", method="POST",
                    body=js.stringify({"channel": cfg["channel"], "sender": me["address"], "content": js.stringify(content)}))
    # A claimant's role is what its own control agent last said on the state channel.
    ctx["pool_opts"] = {"role_of": role_from_stream(call=call, cfg=cfg)}

    state = {"last": None, "down": False}

    def prime() -> None:
        page = call("/api/messages?" + js.search_params({"channel": cfg["channel"], "limit": "1"}))
        rows = page.get("messages") if isinstance(page, dict) and page.get("messages") is not None else page
        if isinstance(rows, list) and rows:
            state["last"] = rows[-1].get("id")
            return
        up = post(up_record(me["address"]))
        state["last"] = up.get("id")
    _stderr(f"agentd: {me['address']} on {cfg['channel']} at {cfg['relay_url']}; operators: {' '.join(operator_list())}")
    if not once:
        watch_source(lambda: leave.request("source changed"))
        # At start too: after a reboot every observed sign-in may have lapsed.

        def keep() -> None:
            if not ops.account_slugs(ops.accounts_dir()):
                return
            try:
                r = keeper.refresh()
            except Exception as e:  # noqa: BLE001
                _stderr(f"agentd: accounts: {e}")
                return
            for a in (r.get("accounts") if isinstance(r, dict) and isinstance(r.get("accounts"), list) else []):
                if a.get("status") != "ok":
                    _stderr(f"agentd: account {a.get('slug')}: {a.get('status')}{' (' + js.string(a['error']) + ')' if js.truthy(a.get('error', js.UNDEFINED)) else ''}")
        Ticker("accounts keeper", keep, ACCOUNTS_KEEPALIVE_MS / 1000, first_s=30).start()
        # The tools report (tools.py): at start, so a reboot or a new registry
        # is answered at once, every hour, and when the role binding changes.
        # The proofs run in the background and never delay a reply.
        start_tools_report(binding_file=who.get("binding"))
        # Only the resident daemon samples: a --once run would add a lone
        # sample with no minute behind it.
        pressure_sampler = pressure.sampler()
        pressure_sampler.tick()
        Ticker("memory pressure", pressure_sampler.tick, pressure.SAMPLE_INTERVAL_MS / 1000, first_s=pressure.SAMPLE_INTERVAL_MS / 1000).start()
        # What the account's sessions are doing, posted when it changes
        # (sessions.py); first at start, so a restart re-says it.
        states = sessions.StateWatcher(address=me["address"], post=state_poster(call, cfg, me["address"]),
                                       file=os.path.join(state_dir(), sessions.STATE_FILE), binding=who.get("binding"),
                                       jobs=os.path.join(state_dir(), "jobs.json"))
        # First at start, in its own thread: the Node did not await it, and a
        # relay that is down must not hold the read loop's start behind the post.
        Ticker("session state", states.tick, sessions.STATE_POLL_MS / 1000).start()

    def beside(rec: dict, ledgered: bool) -> None:
        """An action can take minutes (a session to stop, an install): run
        it beside the loop, so the daemon keeps answering — a request that
        waited behind it would expire unanswered. Its reply is posted when it
        is done; one action at a time is the action's own rule. A read that
        walks a whole home (disk) answers beside the loop too, or every
        request behind it would go unanswered and read as silent."""
        request = rec["request"]
        op, sender, rid = request["op"], request["from"], request["id"]
        moved = [False]

        def work() -> None:
            try:
                reply = answer(request, ctx)
                reply.pop("_followups", None)
                moved[0] = ledgered and ((reply.get("data") or {}).get("upgrade") or {}).get("restart_daemon") is True
                post(reply)
                _stderr(f"agentd: answered {op} for {sender} ({rid[:8]})" + (f": {_status_of(reply, op)}" if ledgered else ""))
            except Exception as e:  # noqa: BLE001 — the Node's .catch: said, the loop goes on
                _stderr(f"agentd: {op} for {sender} failed to answer: {e}")
            finally:
                with leave.lock:
                    inflight.discard(thread)
                    if not once:
                        if moved[0]:
                            leave.request("the fabric moved (upgrade fabric)")
                        else:
                            leave.settle()
        thread = threading.Thread(target=work, name=f"agentd-{op}", daemon=True)
        with leave.lock:
            inflight.add(thread)
        thread.start()

    def finish_inflight() -> None:
        for t in list(inflight):
            t.join()

    while True:
        try:
            if not state["last"]:
                prime()
            page = call("/api/wait?" + js.search_params({"channel": cfg["channel"], "since_id": state["last"],
                                                         "timeout_seconds": "3" if once else str(POLL_S), "limit": "50"}))
            if state["down"]:
                _stderr("agentd: relay is back")
                state["down"] = False
            if isinstance(page, dict) and page.get("warning") == "since_id_not_found":
                state["last"] = None
                continue
            # This daemon's own rule, stricter than the Node's `page.messages ?? []`
            # then `for…of` (which read an array page as empty and iterated a
            # string): a page that is no object, or whose messages are no array,
            # is a failed read, said as the relay's.
            if not isinstance(page, dict):
                raise TypeError("the relay's page is not an object")
            rows = [] if page.get("messages") is None else page["messages"]
            if not isinstance(rows, list):
                raise TypeError("the relay's messages are not an array")
            for rec in rows:
                state["last"] = rec.get("id")
                a = accept(rec, me=me, operators=operator_addresses(), accounts=account_addresses(), keys=operator_keys,
                           ttl_s=cfg["ttl_s"], seen=seen, action_floor=ledger.floor)
                if not a["ok"]:
                    if a["why"] not in QUIET:
                        _stderr(f"agentd: ignored a record {js.stringify(a['why'])}")
                    continue
                request = a["request"]
                remember(seen, request["id"])
                if request["op"] in ACTION_OPS:
                    # Recorded before it runs, so a replay posted while it runs is refused
                    # too; a ledger that cannot be written refuses the action BY NAME —
                    # raised here it read as "relay unreachable" and the action vanished.
                    # Under the leaver's lock from the ledger to the running set: a
                    # restart asked for meanwhile comes before the record or waits
                    # for the action, never between (a recorded action that never
                    # ran is refused as a replay when posted again).
                    with leave.lock:
                        try:
                            ledger.record(request["from"], a["ts"])
                        except Exception as e:  # noqa: BLE001
                            _stderr(f"agentd: {request['op']} for {request['from']} refused: the action ledger could not be written ({_code(e)})")
                            continue
                        _stderr(f"agentd: started {request['op']} for {request['from']} ({request['id'][:8]})")
                        beside(a, True)
                    continue
                if request["op"] in BESIDE_LOOP_OPS:
                    beside(a, False)
                    continue
                reply = answer(request, ctx)
                followups = reply.pop("_followups", None) or []
                post(reply)
                for f in followups:
                    post(f)
                _stderr(f"agentd: answered {request['op']} for {request['from']} ({request['id'][:8]})")
            # An action already started has stopped a session and written a
            # marker: exiting under it would leave the launcher waiting on a
            # pending upgrade and no reply posted (review of #34).
            if once:
                finish_inflight()
                return 0
        except Exception as e:  # noqa: BLE001 — the Node's catch: a failure of the read is the relay's until shown otherwise
            if once:
                finish_inflight()   # every exit of --once, not only the clean one
            status = getattr(e, "status", None)
            if status in (401, 403):
                _stderr(f"agentd: the relay refused this token (HTTP {status}); rotated? run fabric-secrets sync")
                if once:
                    return 4
            elif not state["down"]:
                _stderr(f"agentd: relay unreachable at {cfg['relay_url']} ({e}) — retrying every {RETRY_S} s")
                state["down"] = True
            if once:
                return 1
            time.sleep(RETRY_S)


def _entry() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001 — agentd.mjs's last catch: one line, exit 1
        _stderr(f"agentd: {e}")
        return 1


if __name__ == "__main__":
    code = _entry()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)   # a timer or a beside-the-loop thread must not hold the exit
