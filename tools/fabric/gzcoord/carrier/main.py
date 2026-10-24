"""tools/fabric/gzcoord/carrier/main.py — `gzcoord-carrier`, the InterWeave
carrier of GZCOORD/1 (agent-fabric ADR-064; contract in
communication/gzcoord/docs/CARRIER-CONTRACT.md).

CONTRACT
  argv    run                  the carrier: one long-lived process per
                               account, the program of InterWeave's client
                               unit template (`interweave-client@gzcoord`)
          status               the carrier's outstanding deliveries, counters
                               and connection, as JSON lines on stdout
          abandon <message-id> <recipient-login>
                               the operator ends a delivery (ADR-064 rule 7),
                               recorded with this login as who
          parity --window START END --arrivals FILE... --senders DIR...
                 [--journal DB...] [--drill START END] [--host HOST]
                                 the ADR-064 rule 11 parity report as Markdown
                                 on stdout, computed from the files the
                                 accounts keep (parity.py); START/END are
                                 YYYY-MM-DDTHH:MM:SSZ. It measures, the owner decides
          render-config [--write PATH]
                               the profile's config.yaml rendered from the
                               roster for THIS agent; to stdout, or atomically
                               to PATH (0600). Refuses when this agent has no
                               valid roster row
  env     XDG_RUNTIME_DIR (required: the data socket and the adapter socket
          live under it), GZCOORD_JOURNAL=off (the carrier refuses to run: the
          route is the relay alone, ADR-064 rule 8), AGENT_FABRIC_ROOT /
          AGENT_FABRIC_OPERATOR / AGENT_FABRIC_STATE_DIR (as every GZCoord
          tool reads them), GZCOORD_CARRIER_ROSTER (a roster file other than
          runtime/interweave/roster.json: a test)
  stdout  `status`'s JSON; `render-config`'s YAML
  stderr  every other line, prefixed `gzcoord-carrier:`; no secret, no body
  exit    0 done (run: stopped by SIGTERM/SIGINT); 1 usage; 2 refused to run
          (journal off, no valid roster row, another carrier already holds the
          record or the socket, no XDG_RUNTIME_DIR); 3 the carrier is not
          reachable (status, abandon)

The carrier never opens the admin socket and never carries fabric:control
(ADR-064 rules 5, 12).
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from gzcoord.carrier import arrivals, engine, ipc, record, roster, server  # noqa: E402

USAGE = ("usage: gzcoord-carrier run | status | abandon <message-id> <recipient-login> | "
         "render-config [--write PATH] | parity --window START END --arrivals FILE... --senders DIR... "
         "[--journal DB...] [--drill START END] [--host HOST]")


def say(msg: str) -> None:
    print(f"gzcoord-carrier: {msg}", file=sys.stderr, flush=True)


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _checkout() -> str:
    from gzcoord import paths
    return paths.CHECKOUT


def roster_path() -> str:
    return os.environ.get("GZCOORD_CARRIER_ROSTER") or os.path.join(_checkout(), "runtime", "interweave", "roster.json")


def runtime_dir() -> str:
    rd = os.environ.get("XDG_RUNTIME_DIR")
    if not rd or not os.path.isabs(rd):
        raise SystemExit(_refuse("XDG_RUNTIME_DIR is not set: the sockets have no safe place to live"))
    return rd


def _refuse(why: str) -> int:
    say(why)
    return 2


def _state() -> str:
    import episodic
    return episodic.state_dir()


def make_me() -> engine.Me:
    """Who this agent is NOW. The role is read per call: a relaunch rebinds it
    and the carrier outlives sessions."""
    import episodic
    from gzcoord import gzmsg, paths
    from gzcoord.inbox_parts.tokens import identity
    who = gzmsg.whoami()
    tax_path = gzmsg.find_taxonomy(paths.operator_root())
    taxonomy = gzmsg.load_taxonomy(tax_path) if tax_path else None
    me = identity(who, taxonomy)
    agent_id = episodic.own_agent_id()
    if not agent_id:
        raise roster.RosterError("this account has no agent id (ADR-039): no roster row can be its own")
    return engine.Me(agent_id, me["instance"], me["address"], me.get("slug"))


def verified_roster() -> tuple[roster.Roster, list[dict]]:
    from gzcoord import paths
    r = roster.load(roster_path())
    good, refused = roster.valid_rows(r, roster.GitMainKeys(paths.operator_root()))
    for x in refused:
        say(f"roster row of {x.login or x.agent_id} counts for nothing: {x.reason}")
    return r, good


def journal_inbound(text: str, ts: str) -> str:
    import episodic
    conn = episodic.connect()
    try:
        counts = episodic.inbound(conn, [{"content": text, "seq": None, "ts": ts}], carrier="interweave")
    finally:
        conn.close()
    return "written" if counts["written"] else "same"


def parse(text: str):
    import episodic
    try:
        return episodic.parse_header(text)
    except episodic.JournalError as e:
        raise ValueError(str(e)) from None


def cmd_run() -> int:
    if os.environ.get("GZCOORD_JOURNAL") == "off":
        return _refuse("GZCOORD_JOURNAL=off: with the journal off the route is the relay alone (ADR-064 rule 8)")
    import episodic
    from gzcoord.inbox_parts.tokens import for_me
    rd = runtime_dir()
    try:
        me = make_me()
        state = os.path.join(_state(), "interweave")
        r, good = verified_roster()
    except (roster.RosterError, episodic.JournalError, OSError) as e:
        return _refuse(str(e))
    host = me.address.split("/")[0]
    data_socket = os.path.join(rd, "interweave", f"{r.profile}.sock")
    try:
        box = record.Outbox(state, iso_now=iso_now)
    except record.RecordError as e:
        return _refuse(str(e))
    inbox = arrivals.Inbox(state, iso_now=iso_now)
    log = arrivals.ArrivalLog(os.path.join(_state(), "gzcoord-arrivals.jsonl"), iso_now=iso_now)

    def stamp() -> object:
        try:
            st = os.stat(roster_path())
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    carrier = engine.Carrier(
        me_fn=make_me, roster_fn=verified_roster, outbox=box, inbox=inbox, arrival_log=log,
        connect=lambda: ipc.Session.open(data_socket, endpoint=r.endpoint, kind="automated-client"),
        journal=journal_inbound, parse=parse, for_me=for_me, host=host, iso_now=iso_now, roster_stamp=stamp)
    try:
        srv = server.Server(server.socket_path(rd), carrier.handle_request)
    except OSError as e:
        box.close()
        return _refuse(str(e))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: carrier.stop.set())
    say(f"up as {me.address}, profile {r.profile}, {len(good)} valid roster row(s)")
    try:
        carrier.run()
    finally:
        srv.close()
        box.close()
    return 0


def _call(req: dict) -> dict | None:
    try:
        return server.call(server.socket_path(runtime_dir()), req)
    except OSError as e:
        say(f"the carrier is not reachable: {e}")
        return None


def cmd_status() -> int:
    out = _call({"op": "status"})
    if out is None:
        return 3
    print(json.dumps(out, sort_keys=True))
    return 0 if out.get("ok") else 3


def cmd_abandon(mid: str, recipient: str) -> int:
    import pwd
    out = _call({"op": "abandon", "message_id": mid, "recipient": recipient,
                 "by": pwd.getpwuid(os.getuid()).pw_name})
    if out is None:
        return 3
    print(json.dumps(out, sort_keys=True))
    return 0 if out.get("ok") and out.get("abandoned") else 3


def cmd_render(path: str | None) -> int:
    try:
        r, good = verified_roster()
        text = roster.render_config(r, good, make_me().agent_id)
    except (roster.RosterError, OSError) as e:
        return _refuse(str(e))
    if path:
        roster.write_config(path, text)
    else:
        sys.stdout.write(text)
    return 0


def cmd_parity(args: list[str]) -> int:
    import argparse
    from gzcoord.carrier import parity
    p = argparse.ArgumentParser(prog="gzcoord-carrier parity", add_help=False, allow_abbrev=False)
    p.add_argument("--window", nargs=2, required=True)
    p.add_argument("--arrivals", nargs="+", required=True)
    p.add_argument("--senders", nargs="+", required=True)
    p.add_argument("--journal", nargs="+", default=[])
    p.add_argument("--drill", nargs=2)
    p.add_argument("--host", default="")
    try:
        a = p.parse_args(args)
        window = (parity.parse_t(a.window[0]), parity.parse_t(a.window[1]))
        drill = (parity.parse_t(a.drill[0]), parity.parse_t(a.drill[1])) if a.drill else None
    except (SystemExit, ValueError) as e:
        print(USAGE, file=sys.stderr)
        say(f"bad arguments: {e}")
        return 1
    lines: list[dict] = []
    try:
        for f in a.arrivals:
            with open(f, encoding="utf-8") as fh:
                lines += [json.loads(x) for x in fh if x.strip()]
        kinds: dict[str, str] = {}
        for db in a.journal:
            kinds.update(parity.kinds_from_journal(db))
        senders = {os.path.basename(os.path.dirname(d.rstrip("/"))) or d: record.read_deliveries(d) for d in a.senders}
        rep = parity.compute(lines, senders, kinds, window, drill, host=a.host)
    except (OSError, ValueError, KeyError, sqlite3.Error) as e:
        return _refuse(f"cannot compute the report: {type(e).__name__}: {e}")
    sys.stdout.write(parity.render_markdown(rep))
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE, file=sys.stderr)
        return 0 if argv else 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "run" and not rest:
        return cmd_run()
    if cmd == "status" and not rest:
        return cmd_status()
    if cmd == "abandon" and len(rest) == 2:
        return cmd_abandon(rest[0], rest[1])
    if cmd == "parity":
        return cmd_parity(rest)
    if cmd == "render-config" and (not rest or (len(rest) == 2 and rest[0] == "--write")):
        return cmd_render(rest[1] if rest else None)
    print(USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
