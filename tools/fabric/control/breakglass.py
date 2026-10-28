"""tools/fabric/control/breakglass.py — the control path to an account when
there is no relay: `bin/fabric-op` on the target, and the operator's half of
it (`fabric-ctl <login> <action-op> ... --via hostexec`).

  hostexec <host> --as <login> -- @fabric/bin/fabric-op <op>      one signed
                                      fabric-control/1 request on stdin

WHY. The control plane's actions ride a relay; a host with none (a second
host before its relay exists) is otherwise reached only by a plain
`fabric-host` run, which is no signed action. The owner chose this path on
2026-10-27 (j422, Q6 "option a for now"): the account runs the operator's
signed request as its agentd would have, and the sudo that hostexec needs is
the same gate the operator already holds.

THE TARGET (`fabric-op <op>`). The decision is agentd.accept()'s, never a
copy of it: the operators, their keys, the ttl, the clock skew and the
SAME ActionLedger file (state_dir()/actions-seen.json) as the daemon's, so a
request accepted on either path is a replay on the other. What this path
refuses beyond it, each as a refusal and nothing run:
  - an op that is not an ACTION op (a read over break-glass is a plain
    `fabric-host` run already, and a read carries no signature to check);
  - a `to` that is "*" or does not name this account: a request signed for
    a fleet is not an order to the one account an operator happened to reach;
  - an argv <op> that is not the request's op (the argv is what an operator
    or a log reads; it must not say something the signature does not cover).
The op then runs through agentd.answer(), the code an accepted relay request
reaches, and its reply record is printed as one JSON line.

  stdin    one request, at most MAX_REQUEST_BYTES, UTF-8
  stdout   the reply record, one JSON line (exactly what the relay would have
           carried); nothing else
  stderr   a refusal: `fabric-op: refused: <reason>`, one line
  exit     0 the op's status is a success (ctl.ACTION_OK); 1 the op ran and
           failed, or raised; 2 refused, nothing run

THE ORDER, and why: parse and decide (accept) → the extra refusals → the
journal's first line → claim the ledger → run → the outcome line. The journal
comes before the claim so that a run refused for an unwritable journal has not
spent the request: fixed, the same signed request can be sent again inside its
ttl. The claim is ActionLedger.claim(), an atomic check-and-record under the
ledger's lock; accept()'s floor check is made without it, so two copies of a
request arriving together both pass accept() and exactly one claims.

THE JOURNAL, on both ends: fabric-op.jsonl in the control state dir
(upgrade.state_dir()), append-only, one JSON object a line. A line BEFORE the
run (phase "before": id, op, from, to, host, ts, via) and one after (phase
"after": id, status, exit). A first line that cannot be written refuses the
run: an action nobody could later find is the bypass ADR-041 rule 10 audits
for. A refused request gets its "after" line alone (status "refused", with the
reason), best effort — the refusal stands whether or not it is written.

THE OPERATOR (`--via hostexec`). The request is built and signed exactly as the
relay path builds it (an unsigned action is never sent), the login's host is
the registry's placement, the request goes through runtime/hostexec/hostexec
on stdin (never argv), and the reply record that comes back is the row a relay
reply would have made. The relay and its token are not touched. One account
per command: a request to "*" is refused by the target.
"""
from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from control import agentd, js  # noqa: E402
from control.gzcoord import FABRIC_ROOT, identity, whoami  # noqa: E402
from control.sign import ACTION_OPS, SignError  # noqa: E402
from control.upgrade import state_dir  # noqa: E402

MAX_REQUEST_BYTES = 65536   # an action's request is a few hundred bytes; the relay's own limit is 128 KiB
JOURNAL = "fabric-op.jsonl"
VIA = "hostexec"
EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
USAGE = "usage: fabric-op <op>   (one signed fabric-control/1 request on stdin; run by hostexec --as <login>)"


class Refused(Exception):
    """A request this path will not run, said in one line."""


class JournalError(Exception):
    """The journal's line could not be written."""


# ── the journal ─────────────────────────────────────────────────────────

def journal_file() -> str:
    return os.path.join(state_dir(), JOURNAL)


def _clip(v: Any, n: int = 200) -> Any:
    """What a request says about itself is untrusted and may be any size; the journal keeps the start."""
    if isinstance(v, str):
        return v[:n]
    if isinstance(v, list):
        return [_clip(x, n) for x in v[:16]]
    return v if isinstance(v, (int, float, bool)) or v is None else str(type(v).__name__)


def append(path: str, record: dict) -> None:
    """One line, appended and synced. JournalError carries the errno's name, never a path's content."""
    line = (json.dumps(record, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC, 0o600)
        try:
            if os.write(fd, line) != len(line):
                raise OSError(errno.EIO, "short write")
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as e:
        raise JournalError(f"the journal {path} could not be written ({errno.errorcode.get(e.errno or 0, e.strerror or 'error')})") from None


def _iso(ms: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ms / 1000)) + f".{int(ms % 1000):03d}Z"


def before_line(request: dict, *, host: str, via: str, now_ms: float) -> dict:
    return {"v": 1, "phase": "before", "at": _iso(now_ms), "id": _clip(request.get("id")), "op": _clip(request.get("op")),
            "from": _clip(request.get("from")), "to": _clip(request.get("to")), "host": host, "ts": _clip(request.get("ts")), "via": via}


def after_line(rid: Any, status: str, exit_code: int | None, now_ms: float, reason: str | None = None) -> dict:
    return {"v": 1, "phase": "after", "at": _iso(now_ms), "id": _clip(rid), "status": status, "exit": exit_code,
            **({"reason": reason[:200]} if reason else {})}


def _one_line(text: str) -> str:
    return "".join(c if c.isprintable() else "?" for c in text)[:300]


# ── the target ──────────────────────────────────────────────────────────

def read_request(stream: Any) -> str:
    raw = stream.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        raise Refused(f"the request is larger than {MAX_REQUEST_BYTES} bytes")
    if not raw:
        raise Refused("no request on stdin")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused("the request is not UTF-8") from None


def fence(request: dict, argv_op: str, me: str) -> None:
    """The refusals this path adds to accept()'s; Refused with the reason."""
    op = request["op"]
    if op != argv_op:
        raise Refused(f"{_one_line(argv_op)}: the request is for {_one_line(js.string(op))}, not the op on the command line")
    if op not in ACTION_OPS:
        raise Refused(f"{op}: not an action op; a read does not go over fabric-op (fabric-host run does that)")
    to = request.get("to")
    named = [to] if isinstance(to, str) else to if isinstance(to, list) else []
    # accept() has already refused a `to` that holds neither "*" nor this account, so refusing "*" leaves it naming this account.
    if "*" in named:
        raise Refused(f"{op}: `to` must name {me} explicitly, not \"*\"")


def _id_of(text: str) -> Any:
    """The request's id for the journal's refusal line, when the text has one."""
    try:
        r = js.json_parse(text)
    except ValueError:
        return None
    return r.get("id") if isinstance(r, dict) else None


def decide(text: str, argv_op: str, me: dict, *, ledger: agentd.ActionLedger, now_ms: float | None = None,
           registry: str | None = None) -> dict:
    """The accepted request's record ({request, ts}); Refused with accept()'s own reason otherwise."""
    cfg = agentd.control_config()
    try:
        a = agentd.accept({"content": text}, me=me, operators=agentd.operator_addresses(registry), accounts=agentd.account_addresses(registry),
                          keys=lambda: agentd.operator_keys(registry), ttl_s=cfg["ttl_s"], seen=set(), now=now_ms, action_floor=ledger.floor)
    except SignError as e:
        # openssl could not say whether the signature holds: not a verdict, and not a reason to run.
        raise Refused(f"the signature could not be checked ({_one_line(str(e))})") from None
    if not a["ok"]:
        raise Refused(a["why"])
    fence(a["request"], argv_op, me["address"])
    return a


def _status_ok(op: str, reply: dict) -> bool:
    from control.ctl import ACTION_OK   # ctl imports this module for the operator side; the table stays where the relay path reads it
    section = (reply.get("data") or {}).get(op) if isinstance(reply.get("data"), dict) else None
    return isinstance(section, dict) and section.get("status") in ACTION_OK.get(op, [])


def run_target(argv: list[str], stdin: Any, out: Any, err: Any, *, me: dict | None = None, journal: str | None = None,
               ledger: agentd.ActionLedger | None = None, now: Callable[[], float] = time.time, registry: str | None = None,
               ctx: dict | None = None) -> int:
    def say(text: str) -> None:
        err.write(text + "\n")
        err.flush()
    if len(argv) != 1 or argv[0].startswith("-"):
        if argv in (["-h"], ["--help"]):
            out.write(USAGE + "\n")
            return EXIT_OK
        say(f"fabric-op: refused: {USAGE}")
        return EXIT_REFUSED
    op = argv[0]
    path = journal_file() if journal is None else journal
    rid: Any = None
    try:
        text = read_request(stdin)
        rid = _id_of(text)
        me = me or identity(whoami())
        ledger = ledger or agentd.action_ledger()
        a = decide(text, op, me, ledger=ledger, now_ms=now() * 1000, registry=registry)
        request = a["request"]
        host = me["address"].split("/", 1)[0]
        try:
            append(path, before_line(request, host=host, via="fabric-op", now_ms=now() * 1000))
        except JournalError as e:
            raise Refused(f"{e}; nothing run") from None
        try:
            claimed = ledger.claim(request["from"], a["ts"])
        except OSError as e:
            raise Refused(f"{request['op']}: the action ledger could not be written ({errno.errorcode.get(e.errno or 0, 'error')}); nothing run") from None
        if not claimed:
            raise Refused(f"{request['op']}: not newer than the last action accepted from {_one_line(request['from'])[:40]} (a replay)")
    except Refused as e:
        try:
            append(path, after_line(rid, "refused", EXIT_REFUSED, now() * 1000, reason=str(e)))
        except JournalError:
            pass   # the refusal is the answer; an unwritable journal is already said when it was the reason
        say(f"fabric-op: refused: {_one_line(str(e))}")
        return EXIT_REFUSED
    try:
        reply = agentd.answer(request, ctx if ctx is not None else {"me": me, "started": js.iso_now()})
        reply.pop("_followups", None)
        ok = _status_ok(op, reply)
        out.write(js.stringify(reply) + "\n")
        out.flush()
        status, code, reason = ("ok", EXIT_OK, None) if ok else ("failed", EXIT_FAILED, None)
    except Exception as e:  # noqa: BLE001 — agentd's own catch: the action is said failed, in one line
        say(f"fabric-op: {op} failed: {_one_line(str(e))}")
        status, code, reason = "error", EXIT_FAILED, str(e)
    try:
        append(path, after_line(request["id"], status, code, now() * 1000, reason=reason))
    except JournalError as e:
        say(f"fabric-op: the {op} ran, but its outcome line could not be written: {e}")
    return code


# ── the operator ────────────────────────────────────────────────────────

@dataclass
class Outcome:
    """kind: reply (the target answered; `reply` is its record), refused (the target's fence), no-answer (timeout), failed."""
    kind: str
    reply: dict | None = None
    detail: str = ""
    exit: int | None = None


def _hostexec() -> str:
    return os.path.join(FABRIC_ROOT, "runtime", "hostexec", "hostexec")


def via_hostexec(request: dict, target: dict, *, timeout: float, registry: str | None = None, journal: str | None = None,
                 run: Callable[..., Any] = subprocess.run, now: Callable[[], float] = time.time) -> Outcome:
    """Send one signed request to `target` ({login, host, address}) through hostexec and return what came of it.
    JournalError when the first line cannot be written: nothing was sent."""
    path = journal_file() if journal is None else journal
    rid = request["id"]
    append(path, before_line(request, host=target["host"], via=VIA, now_ms=now() * 1000))
    env = dict(os.environ)
    if registry is not None:
        env["AGENT_FABRIC_HOSTS_REGISTRY"] = registry
    outcome: Outcome
    try:
        body = js.stringify(request).encode("utf-8")
        p = run([_hostexec(), target["host"], "--as", target["login"], "--", "@fabric/bin/fabric-op", request["op"]], input=body,
                capture_output=True, timeout=timeout, env=env, check=False)
        stdout, stderr = p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
        said = next((ln for ln in reversed(stderr.splitlines()) if ln.strip()), "")
        reply = _reply_of(stdout, rid, target["address"])
        if reply is not None:
            outcome = Outcome("reply", reply, exit=p.returncode)
        elif p.returncode == EXIT_REFUSED and said.startswith("fabric-op: refused:"):
            outcome = Outcome("refused", detail=_one_line(said[len("fabric-op: refused:"):].strip()), exit=p.returncode)
        else:
            outcome = Outcome("failed", detail=_one_line(said) or f"exit {p.returncode} with no reply record", exit=p.returncode)
    except subprocess.TimeoutExpired:
        outcome = Outcome("no-answer", detail=f"no answer within {round(timeout)} s; the action may still be running there")
    except FileNotFoundError:
        outcome = Outcome("failed", detail="hostexec not found")
    except (OSError, UnicodeEncodeError) as e:
        outcome = Outcome("failed", detail=_one_line(f"could not run hostexec ({getattr(e, 'strerror', None) or e})"))
    status = {"reply": "ok", "refused": "refused", "no-answer": "no-answer"}.get(outcome.kind, "failed")
    if outcome.kind == "reply" and outcome.exit != EXIT_OK:
        status = "failed"
    try:
        append(path, after_line(rid, status, outcome.exit, now() * 1000, reason=outcome.detail or None))
    except JournalError as e:
        outcome.detail = (outcome.detail + "; " if outcome.detail else "") + f"outcome not journaled: {e}"
    return outcome


def _reply_of(stdout: str, rid: str, address: str) -> dict | None:
    """The reply record for `rid` from `address`, if stdout holds one; anything else on it is not a reply."""
    for ln in stdout.splitlines():
        try:
            r = js.json_parse(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("kind") == "reply" and r.get("in_reply_to") == rid and r.get("from") == address:
            return r
    return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        return run_target(argv, sys.stdin.buffer, sys.stdout, sys.stderr)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001 — one line, never a traceback; whether the op ran is not known, so not the refusal's 2
        sys.stderr.write(f"fabric-op: {_one_line(str(e))}\n")
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
