"""tools/fabric/control/queue.py — what bin/fabric-jobs asks of the control
plane to order a queue (agent-fabric ADR-037 rules 8 and 9): which
requests some account waits on, read from the state stream; and the
role's pool, asked of the control agent that holds it (control/pool.py).
ported from runtime/control/queue.mjs (ADR-040 Wave 8; deleted in step s8).
tools/fabric/jobs.py (jobsparts/queue.py) runs this module as a script on its
own interpreter.

CONTRACT, carried over from queue.mjs's header (the CLI of
tools/fabric/jobs.py; `python3 tools/fabric/control/queue.py` answers the
same argv, stdout and exits). Env read: CLAUDE_BRIDGE_URL,
FABRIC_CONTROL_CHANNEL, FABRIC_STATE_CHANNEL, FABRIC_CONTROL_CONFIG (another
control config file, so another pool_holder; agentd's control_config),
AGENT_FABRIC_HOSTS_REGISTRY (who is placed, who holds the pool),
FABRIC_QUEUE_WAIT_MS (how long the holder may take to answer, 10 s):
  waits                 {"waits": {<message id>: [<address>, …]}, "accounts": n,
                         "stale": {<address>: <age s, or null>}}; exit 0, 2, 3
  pool-list [<role>]    {"holder", "answer"}; exit 0, 2, 3, 4
  pool-claim <pool id>  the same; "sent" true / false / absent on exit 3
  job-state <login> <j<n>|message id>
                        {"operator": true} when this login is a host operator (the caller reads the board
                        through fabric-ctl, which answers it more), else {"target", "answer"}: the public op
                        `job-state` (control/jobs.py) asked of that login's control agent; exit 0, 3, 4
  waits_from, read_waits, budget_left, relay, bound_call, budget_spent,
  placed_accounts, relay_error, unsent, ask_holder   as queue.mjs's

The run's budget is counted from this module's import, where Node counted
from the process's start (performance.timeOrigin); for the CLI the two
are milliseconds apart. This login's identity and relay token are
resolved here, as agentd resolves its own: the token never crosses a
pipe or an argv. agentd's config and id (control_config, new_id) are
parameters, imported by the CLI from agentd's port; when that import
fails the CLI answers every valid command with exit 3 and
{"error": "the CLI needs tools/fabric/control/agentd.py …", "sent":
false} — nothing asked, nothing sent.

A state record is any relay-token holder's post: one without agentd's
shape, or from no placed address, is skipped. A forged one can make a job
look waited on — an ordering, never a permission — and the waiter it
names is shown.
"""
from __future__ import annotations

import math
import os
import re
import sys
import time

# Run as a script, this file's own directory leads sys.path and would
# shadow the standard library's `queue` for any module that imports it
# (concurrent.futures, logging.handlers): it is replaced by tools/fabric.
if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
else:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import roots  # noqa: E402
from control import gzcoord, js  # noqa: E402
from control.jobs import JOB_ID  # noqa: E402
from control.pool import POOL_ID, ROLE_SLUG, STATES_REPLAY, STATES_STALE_MS, pool_holder  # noqa: E402
from control.sessions import MESSAGE_ID, date_parse  # noqa: E402

QUEUE_CALL_TIMEOUT_MS = 15000
QUEUE_BUDGET_MS = 25000
# THE BUDGET. tools/fabric/jobs.py kills the run QUEUE_TIMEOUT_S (30 s) after
# it starts it, whatever the run is doing. So the run has one budget, under
# that kill, and every relay call — and the wait for the holder — takes at
# most what is left of it, and no call more than QUEUE_CALL_TIMEOUT_MS: a
# relay that does not answer is said by this side, never cut off by that
# one. No call here is a long poll.
_BUDGET_END = time.monotonic() * 1000 + QUEUE_BUDGET_MS
_env_wait = js.number(os.environ["FABRIC_QUEUE_WAIT_MS"]) if "FABRIC_QUEUE_WAIT_MS" in os.environ else math.nan
QUEUE_WAIT_MS = _env_wait if _env_wait > 0 else 10000
POLL_S = 0.4


class Unreadable(Exception):
    """The relay or the registry cannot be read: no token, no placement."""


class BudgetSpent(Exception):
    """A spent budget asks nothing: the call is not made, so nothing left
    this account, and the run's budget is named, never the relay."""
    sent = False


def budget_left(now_ms: float | None = None) -> int:
    now_ms = time.monotonic() * 1000 if now_ms is None else now_ms
    return math.floor(_BUDGET_END - now_ms)


def waits_from(rows: list, placed: set, now_ms: float | None = None) -> dict:
    """The message ids each placed account waits on: {id: [address, …]}."""
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    newest: dict = {}
    for rec in rows:
        content = rec.get("content") if isinstance(rec, dict) else None
        try:
            r = js.json_parse(content) if isinstance(content, str) else None
        except ValueError:
            continue
        if (not isinstance(r, dict) or r.get("kind") != "state" or not (js.is_integer(r.get("v")) and r["v"] == 1)
                or not isinstance(r.get("from"), str) or r["from"] not in placed or not isinstance(r.get("ts"), str)):
            continue
        w = r.get("waits_on", js.UNDEFINED)
        if w is not js.UNDEFINED and not (isinstance(w, list) and all(isinstance(m, str) and MESSAGE_ID.fullmatch(m) for m in w)):
            continue
        # The channel's order is the relay's; a record later on it is newer.
        newest.pop(r["from"], None)
        newest[r["from"]] = r
    waits: dict = {}
    stale: dict = {}
    for sender in sorted(newest, key=lambda a: a.encode("utf-16-be", "surrogatepass")):
        r = newest[sender]
        w = r.get("waits_on") or []
        for m in w:
            waits.setdefault(m, []).append(sender)
        age = now_ms - date_parse(r["ts"])
        if w and not (age <= STATES_STALE_MS):
            stale[sender] = math.floor(age / 1000) if math.isfinite(age) else None
    return {"waits": waits, "accounts": len(newest), "stale": stale}


def read_waits(*, call, cfg: dict, placed: set) -> dict:
    page = call("/api/messages?" + js.search_params({"channel": cfg["state_channel"], "limit": js.string(STATES_REPLAY), "full": "1"}))
    messages = page.get("messages") if isinstance(page, dict) else None
    return waits_from(messages if isinstance(messages, list) else [], placed)


def budget_spent(path: str) -> BudgetSpent:
    return BudgetSpent(f"{js.string(path).split('?')[0]}: not asked, this run's {js.string(QUEUE_BUDGET_MS / 1000)} s budget is spent")


def bound_call(tok: str, cfg: dict, call=gzcoord.api, left=budget_left):
    def bound(path: str, method: str = "GET", body: str | None = None):
        ms = min(QUEUE_CALL_TIMEOUT_MS, left())
        if not ms > 0:
            raise budget_spent(path)
        return call(tok, path, relay_url=cfg.get("relay_url"), method=method, body=body, timeout_s=ms / 1000)
    return bound


def relay(who: dict | None = None, cfg: dict | None = None, *, call=gzcoord.api, left=budget_left, agentd=None) -> dict:
    """The relay as this login reaches it, or Unreadable saying why not."""
    who = gzcoord.whoami() if who is None else who
    if cfg is None:
        cfg = (agentd or _agentd()).control_config()
    gz = gzcoord.integration_config(who.get("project"))
    tok = gzcoord.token(gzcoord.inbox_root(who), gz if gz.get("configured") else None) or gzcoord.synced_token()
    if not tok:
        raise Unreadable("no CLAUDE_BRIDGE_AUTH_TOKEN (fabric-secrets sync)")
    return {"who": who, "cfg": cfg, "call": bound_call(tok, cfg, call, left)}


def placed_accounts(registry: str | None = None) -> set:
    """Who is placed, read here rather than through agentd's
    account_addresses, which takes an unreadable registry for nobody: here
    that would read as "nobody waits on anything" and say nothing."""
    registry = roots.hosts_registry(engine=gzcoord.FABRIC_ROOT, empty_is_set=True) if registry is None else registry
    try:
        with open(registry, encoding="utf-8", errors="replace") as fh:
            d = js.json_parse(fh.read())
    except OSError as e:
        import errno
        raise Unreadable(f"the hosts registry cannot be read ({errno.errorcode.get(e.errno, 'not JSON')})") from None
    except ValueError:
        raise Unreadable("the hosts registry cannot be read (not JSON)") from None
    placement = d.get("placement") if isinstance(d, dict) else None
    if not isinstance(placement, dict):
        raise Unreadable("the hosts registry has no placement")
    return {f"{js.string(host)}/{login}" for login, host in placement.items()}


def relay_error(e: BaseException, cfg: dict) -> str:
    if isinstance(e, (Unreadable, BudgetSpent)):
        return str(e)
    if getattr(e, "worded", False):   # control_link.Down: both carriers' failures, already said in full
        return str(e)
    return gzcoord.relay_failure(e, cfg.get("relay_url"))


def unsent(e: BaseException) -> bool:
    """Whether a failed post certainly left nothing at the relay: refused
    with a 4xx, or never connected. Anything else (a reset, a 5xx after the
    write) is unknown, and said as such by leaving `sent` out."""
    status = getattr(e, "status", None)
    return (isinstance(e, BudgetSpent) or (isinstance(status, int) and not isinstance(status, bool) and 400 <= status < 500)
            or getattr(e, "connection_refused", False) is True)


def _open_leg(request: dict, to: list, wait_s: float):
    from gzcoord.carrier import control_link
    return control_link.Leg.open(request, to, wait_s)


def _say(message: str) -> None:
    print(f"queue: {message}", file=sys.stderr)


def ask_holder(*, call, cfg: dict, from_: str, holder: str, op: str, args: dict, new_id, wait_ms: float = QUEUE_WAIT_MS,
               left=budget_left, sleep=time.sleep, clock=lambda: time.monotonic() * 1000, open_leg=_open_leg, say=_say):
    """One request to the holder, its one reply's data[op], or None when none
    came within wait_ms. The request carries only what the op reads: a role
    for a list, an id for a claim — never the claimant's role.

    With cfg["control_carrier"] "dual" (ADR-029 rule 18) the request also goes
    to this account's own agentd, which sends it to the holder over the second carrier,
    and the holder's reply on either carrier answers it: a relay that is down
    no longer leaves the holder unreachable. Under any other control_carrier
    nothing differs."""
    rid = new_id()
    # The wait, fixed once before anything is posted: wait_ms, or what the
    # run's budget has left when that is less.
    wait = min(wait_ms, left())
    if not wait > 0:
        raise budget_spent("/api/send")
    # The request lives as long as the asker waits, and no longer: a claim
    # the holder took after the asker gave up would be recorded for nobody.
    request = {"v": 1, "kind": "request", "id": rid, "from": from_, "to": [holder], "op": op, "ts": js.iso_now(),
               "ttl_s": math.ceil(wait / 1000), "args": args}
    dual = cfg.get("control_carrier") == "dual"
    relay_error = None
    sent = None
    try:
        sent = call("/api/send", method="POST", body=js.stringify({"channel": cfg["channel"], "sender": from_, "content": js.stringify(request)}))
    except Exception as e:  # noqa: BLE001 — a failed post is the second carrier's to make up for, or the caller's to say
        if not dual:
            raise
        relay_error = e
    leg = None
    if dual:
        # An account has no second-carrier path to itself: a holder that is this account is reached by the relay.
        if holder != from_:
            try:
                leg = open_leg(request, [holder], min(wait, left()) / 1000)
            except RuntimeError as e:
                if relay_error is not None:
                    from gzcoord.carrier import control_link
                    raise control_link.Down(f"{gzcoord.relay_failure(relay_error, cfg.get('relay_url'))}; the second carrier: {e}", relay_error,
                                            handed=bool(getattr(e, "handed", False))) from None
                say(f"the second carrier: {e}; the relay carries alone")
        if relay_error is not None and leg is None:
            raise relay_error
    relay_up = relay_error is None
    if not relay_up:
        say(f"the relay post failed ({gzcoord.relay_failure(relay_error, cfg.get('relay_url'))}); the second carrier carries alone")
    lost_said = False
    deadline = clock() + min(wait, left())
    since = sent["id"] if isinstance(sent, dict) and "id" in sent else "undefined"

    def taken(r, sender):
        data = r.get("data") if isinstance(r, dict) else None
        answer = data.get(op) if isinstance(data, dict) else None
        # Only the holder's reply to this request: anyone may post on the channel.
        if (isinstance(r, dict) and r.get("kind") == "reply" and r.get("in_reply_to") == rid and sender == holder
                and js.truthy(answer) and isinstance(answer, dict) and isinstance(answer.get("status"), str)):
            return answer
        return None
    try:
        while clock() < deadline:
            if relay_up:
                try:
                    page = call("/api/messages?" + js.search_params({"channel": cfg["channel"], "since_id": since, "limit": "500", "full": "1"}))
                except Exception as e:  # noqa: BLE001 — queue.mjs marks every failure here as after the post
                    if leg is None or leg.lost:
                        e.sent = True
                        raise
                    say("the relay stopped answering; the second carrier carries alone")
                    relay_up, page = False, None
                messages = page.get("messages") if isinstance(page, dict) else None
                for rec in messages if isinstance(messages, list) else []:
                    since = rec.get("id", js.UNDEFINED) if isinstance(rec, dict) else js.UNDEFINED
                    since = js.string(since)
                    content = rec.get("content") if isinstance(rec, dict) else None
                    try:
                        r = js.json_parse(content) if isinstance(content, str) else None
                    except ValueError:
                        continue
                    answer = taken(r, r.get("from") if isinstance(r, dict) else None)
                    if answer is not None:
                        return answer
            if leg is not None and not leg.lost:
                for sender, record in leg.replies(0.0 if relay_up else POLL_S):
                    # The roster's address for the PeerId, which the record must also claim.
                    answer = taken(record, sender) if record.get("from") == sender else None
                    if answer is not None:
                        return answer
            if leg is not None and leg.lost and not lost_said:
                lost_said = True
                say("the second carrier's connection to this account's agentd closed before the holder answered")
            if relay_up:
                sleep(POLL_S)
            elif leg is None or leg.lost:
                break   # no carrier is left to answer
    finally:
        if leg is not None:
            leg.close()
    return None


class NoAgentd(Exception):
    """agentd's port (control_config, new_id) is not in this tree yet."""


def _agentd():
    # Only an absent agentd.py is "not here yet": one that fails its own
    # import is a defect, and its traceback is what a person needs.
    if not os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), "agentd.py")):
        raise NoAgentd("the CLI needs tools/fabric/control/agentd.py (control_config, new_id), "
                       "agentd's port, which is not in this tree yet")
    from control import agentd   # agentd's port: control_config, new_id
    return agentd


def cli(argv: list[str] | None = None, out=print, err=lambda m: print(m, file=sys.stderr), *, agentd=None,
        who: dict | None = None, call=gzcoord.api, registry: str | None = None, wait_ms: float | None = None,
        clock=lambda: time.monotonic() * 1000) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else None
    arg = argv[1] if len(argv) > 1 else None
    usage = "usage: queue.mjs waits | pool-list [<role>] | pool-claim <pool id> | job-state <login> <job id|message id>"
    if cmd == "job-state":
        return job_state_cli(argv[1:], out, err, agentd=agentd, who=who, call=call, registry=registry, wait_ms=wait_ms, usage=usage)
    if (len(argv) > 2 or cmd not in ("waits", "pool-list", "pool-claim") or (cmd == "waits" and arg is not None)
            or (cmd == "pool-claim" and not POOL_ID.fullmatch(arg or "")) or (cmd == "pool-list" and arg is not None and not ROLE_SLUG.fullmatch(arg))):
        err(usage)
        return 2
    try:
        agentd = agentd or _agentd()
    except NoAgentd as e:
        out(js.stringify({"error": str(e), "sent": False}))
        return 3
    cfg = agentd.control_config()
    try:
        r = relay(who, cfg, call=call)
    except Unreadable as e:
        out(js.stringify({"error": relay_error(e, cfg), "sent": False}))
        return 3
    if cmd == "waits":
        try:
            out(js.stringify(read_waits(call=r["call"], cfg=cfg, placed=placed_accounts(registry))))
            return 0
        except Exception as e:  # noqa: BLE001 — every failure is one {"error"} line, exit 3, as queue.mjs's catch
            out(js.stringify({"error": relay_error(e, cfg)}))
            return 3
    holder = pool_holder(cfg, registry)
    if not holder:
        out(js.stringify({"error": "no account holds the pool: several hosts and no pool_holder in runtime/control/config.json", "sent": False}))
        return 4
    me = gzcoord.identity(r["who"])
    role = (arg if arg is not None else r["who"].get("role")) if cmd == "pool-list" else None
    if cmd == "pool-list" and not (isinstance(role, str) and ROLE_SLUG.fullmatch(role)):
        out(js.stringify({"error": "this login has no bound role: name the role whose pool to list", "sent": False}))
        return 4
    asked = clock()
    try:
        answer = ask_holder(call=r["call"], cfg=cfg, from_=me["address"], holder=holder, op=cmd,
                            args={"role": role} if cmd == "pool-list" else {"id": arg}, new_id=agentd.new_id,
                            **({"wait_ms": wait_ms} if wait_ms is not None else {}))
    except Exception as e:  # noqa: BLE001 — as queue.mjs's catch: said, with what is known of the post
        sent = {"sent": True} if getattr(e, "sent", False) is True else ({"sent": False} if unsent(e) else {})
        out(js.stringify({"error": relay_error(e, cfg), "holder": holder, **sent}))
        return 3
    if not answer:
        # Math.round: a half rounds up, where Python's round() takes the even one.
        out(js.stringify({"error": f"{holder} did not answer within {js.string(math.floor((clock() - asked) / 1000 + 0.5))} s", "holder": holder, "sent": True}))
        return 3
    out(js.stringify({"holder": holder, "answer": answer}))
    return 0


LOGIN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}", re.ASCII)


def job_state_cli(argv: list[str], out, err, *, agentd, who, call, registry, wait_ms, usage: str) -> int:
    """job-state <login> <j<n>|message id>: see the header. A registry that cannot be read is exit 3, never "not an
    operator" and never "not placed": the caller then reads the board as it did before the op existed."""
    if len(argv) != 2 or not LOGIN.fullmatch(argv[0]) or not (JOB_ID.fullmatch(argv[1]) or MESSAGE_ID.fullmatch(argv[1].lower())):
        err(usage)
        return 2
    login, what = argv
    try:
        agentd = agentd or _agentd()
    except NoAgentd as e:
        out(js.stringify({"error": str(e), "sent": False}))
        return 3
    cfg = agentd.control_config()
    try:
        r = relay(who, cfg, call=call)
        placed = placed_accounts(registry)
    except Unreadable as e:
        out(js.stringify({"error": relay_error(e, cfg), "sent": False}))
        return 3
    me = gzcoord.identity(r["who"])
    if me["address"] in agentd.operator_addresses(registry):
        out(js.stringify({"operator": True}))
        return 0
    if me["address"] not in placed:
        out(js.stringify({"error": f"{me['address']} is not placed in the hosts registry: no agent would answer", "sent": False}))
        return 4
    target = next((a for a in sorted(placed) if a.rsplit("/", 1)[-1] == login), None)
    if target is None:
        out(js.stringify({"error": f"{login} is not placed in the hosts registry", "sent": False}))
        return 4
    try:
        answer = ask_holder(call=r["call"], cfg=cfg, from_=me["address"], holder=target, op="job-state", new_id=agentd.new_id,
                            args={"job": what} if JOB_ID.fullmatch(what) else {"request": what.lower()},
                            **({"wait_ms": wait_ms} if wait_ms is not None else {}))
    except Exception as e:  # noqa: BLE001 — as pool-list's catch: said, with what is known of the post
        sent = {"sent": True} if getattr(e, "sent", False) is True else ({"sent": False} if unsent(e) else {})
        out(js.stringify({"error": relay_error(e, cfg), "target": target, **sent}))
        return 3
    if not answer:
        out(js.stringify({"error": f"{target} did not answer", "target": target, "sent": True}))
        return 3
    out(js.stringify({"target": target, "answer": answer}))
    return 0


def main() -> int:
    try:
        return cli()
    except Exception as e:  # noqa: BLE001 — queue.mjs's last catch: one JSON line, exit 3
        print(js.stringify({"error": f"queue: {str(e).split(chr(10))[0]}"}))
        return 3


if __name__ == "__main__":
    sys.exit(main())
