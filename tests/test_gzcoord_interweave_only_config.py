#!/usr/bin/env python3
"""The InterWeave-only data plane's config (cutover plan docs/proposals/gzcoord-interweave-only-cutover.md, section 6 and W15's
first part), through the real entry points with a real carrier and a relay that refuses every connection:

  1. carrier-only needs no relay token and no relay section: with none anywhere (no CLAUDE_BRIDGE_*, no GZCOORD_CHANNEL, a
     project integration holding no relay_url) a send, the watch and a replay all work; in relay-record and carrier-record the
     same account is refused as before, in one line each (the config line, or with a relay named and no token, the token line).
  2. the one-command override GZCOORD_TRANSPORT_MODE: said on stderr every time, wins over the state file (and over a damaged
     one), is refused when it names no mode, and the watch and its poll (mode.Watcher) honour it.

Plain script: prints ok/FAIL, exit 1 on any failure. The world is test_gzcoord_carrier_only_gate2's."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_gzcoord_carrier_only_gate2 as G  # noqa: E402
from test_gzcoord_carrier_only_gate2 import BIN, INBOX, ME, PEER, check, text, until, watch  # noqa: E402
from gzcoord.carrier import ipc  # noqa: E402
from gzcoord.transport import mode  # noqa: E402

SEND = os.path.join(BIN, "gzcoord-send")
OVERRIDE = {mode.ENV: "carrier-only"}
RELAY_NAMED = lambda w: {"CLAUDE_BRIDGE_URL": w.relay_url, "GZCOORD_CHANNEL": "fixture:chan"}  # noqa: E731 — a relay, no token


def send_file(w: G.World, n: int) -> tuple[str, str]:
    mid, body = text("INFO", n, ME, PEER)
    path = os.path.join(w.base, f"out-{n}.txt")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    return mid, path


def sent_through_carrier(w: G.World, before: int) -> bool:
    return until(lambda: len(w.daemon.sends) > before) and w.daemon.sends[before]["peer"] == G.RT.peer_id("peer")


def carried(w: G.World, mid: str) -> bool:
    """Whether the carrier was handed this MESSAGE-ID (counting sends would miss a retry of an earlier message's)."""
    return any(mid.encode() in ipc.unb64u(p["payload"]["bytes"]) for p in list(w.daemon.sends))


def set_mode(w: G.World, m: str) -> None:
    mode.write(m, "h1/op", w.agent_dir)


def cases(w: G.World) -> None:
    posted = lambda: len(w.daemon.sends)  # noqa: E731
    with G.AgentdStandIn(w.run_dir) as agentd:
        # (1) carrier-only: a send with no relay token and no relay section. The presence ask above it needs neither.
        mid, path = send_file(w, 20)
        before = posted()
        r = w.run([SEND, path])
        check("carrier-only, no relay token and no relay section: send exits 0, `sent INFO <id>`, the peer posted through the carrier,"
              " presence asked of the agentd, no word of a relay or a token",
              r.returncode == 0 and r.stdout == f"sent INFO {mid}\n" and sent_through_carrier(w, before) and len(agentd.requests) == 1
              and "token" not in r.stderr.lower() and "relay" not in r.stderr.lower(), f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        # The same account with the relay named but still no token: still sends (the token is not looked for in this mode).
        mid, path = send_file(w, 21)
        before = posted()
        r = w.run([SEND, path], **RELAY_NAMED(w))
        check("carrier-only with a relay URL and channel named and no token: send still exits 0 through the carrier",
              r.returncode == 0 and r.stdout == f"sent INFO {mid}\n" and sent_through_carrier(w, before),
              f"{r.returncode} {r.stdout!r} {r.stderr!r}")

        # A token that is malformed (a line break) is refused where one is read; carrier-only reads none, so it never meets it.
        mid, path = send_file(w, 30)
        before = posted()
        r = w.run([SEND, path], CLAUDE_BRIDGE_AUTH_TOKEN="a\nb")
        check("carrier-only with a malformed relay token in the environment: the send still goes through (no token is read)",
              r.returncode == 0 and sent_through_carrier(w, before), f"{r.returncode} {r.stdout!r} {r.stderr!r}")

        # (1) the two other modes refuse as today: no relay section, then a relay and no token. Nothing is posted.
        for m in (mode.RELAY_RECORD, mode.CARRIER_RECORD):
            set_mode(w, m)
            mid, path = send_file(w, 22 if m == mode.RELAY_RECORD else 23)
            before = posted()
            r = w.run([SEND, path])
            check(f"{m}, no relay section: send exits 3 with the one configuration line, posts nothing",
                  r.returncode == 3 and r.stdout == "" and "no GZCoord integration configured" in r.stderr
                  and r.stderr.count("\n") == 1 and not carried(w, mid), f"{r.returncode} {r.stdout!r} {r.stderr!r}")
            r = w.run([SEND, path], **RELAY_NAMED(w))
            check(f"{m}, relay named and no token: send exits 3 naming the missing token, posts nothing",
                  r.returncode == 3 and r.stdout == "" and "no CLAUDE_BRIDGE_AUTH_TOKEN" in r.stderr and not carried(w, mid),
                  f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        set_mode(w, mode.CARRIER_ONLY)

        # (2) the override. State file relay-record, override carrier-only: the send is a carrier-only one, and says so.
        set_mode(w, mode.RELAY_RECORD)
        mid, path = send_file(w, 24)
        before = posted()
        r = w.run([SEND, path], **OVERRIDE)
        check("override carrier-only over a relay-record state file: send exits 0 through the carrier, and stderr names"
              f" {mode.ENV} (once)",
              r.returncode == 0 and sent_through_carrier(w, before) and r.stderr.count(mode.ENV) == 1
              and "carrier-only" in r.stderr, f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        # Every time: a second command says it again.
        mid, path = send_file(w, 25)
        r = w.run([SEND, path, "--dry-run"], **OVERRIDE)
        check("  and said again by the next command that uses it", mode.ENV in r.stderr and r.returncode == 0,
              f"{r.returncode} {r.stderr!r}")
        # Wins over the state file the other way: the file says carrier-only, the override says relay-record.
        set_mode(w, mode.CARRIER_ONLY)
        before = posted()
        r = w.run([SEND, path], **{mode.ENV: mode.RELAY_RECORD})
        check("override relay-record over a carrier-only state file: send is refused as a relay mode with no relay section"
              " (exit 3), posts nothing, says the override",
              r.returncode == 3 and "no GZCoord integration configured" in r.stderr and mode.ENV in r.stderr and not carried(w, mid),
              f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        # Unknown value: refused in one line, nothing sent, the file's mode not used as a fallback.
        for bad in ("carrier", "CARRIER-ONLY", "relay"):
            r = w.run([SEND, path], **{mode.ENV: bad})
            check(f"override {bad!r}: refused, exit 2, nothing posted, the line names {mode.ENV} and the modes",
                  r.returncode == 2 and r.stdout == "" and mode.ENV in r.stderr and "carrier-only" in r.stderr
                  and "Traceback" not in r.stderr and not carried(w, mid), f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        # Empty is unset, as `VAR= cmd` is in a shell: the state file decides (carrier-only here).
        mid, path = send_file(w, 26)
        r = w.run([SEND, path], **{mode.ENV: ""})
        check("override empty is read as unset: the state file's mode decides and nothing is said of an override",
              r.returncode == 0 and mode.ENV not in r.stderr, f"{r.returncode} {r.stderr!r}")
        # A damaged state file does not stop the command that overrides it, and without the override it still does.
        with open(mode.path(w.agent_dir), "w", encoding="utf-8") as fh:
            fh.write("not json")
        mid, path = send_file(w, 27)
        before = posted()
        r = w.run([SEND, path])
        check("control: a damaged state file with no relay configured is refused as before (the config line, exit 3), nothing carried", r.returncode == 3 and not carried(w, mid),
              f"{r.returncode} {r.stderr!r}")
        r = w.run([SEND, path], **OVERRIDE)
        check("override carrier-only with a damaged state file: the send goes through", r.returncode == 0 and sent_through_carrier(w, before),
              f"{r.returncode} {r.stderr!r}")
        set_mode(w, mode.CARRIER_ONLY)

    # (1) the watch and replay, carrier-only, no relay anywhere.
    quiet, why = watch(w, None, deadline=4)
    check("carrier-only, no relay: the watch waits to its deadline, exit 0, no word of a relay or token",
          quiet is not None and quiet.returncode == 0 and "relay" not in quiet.stdout.lower() + quiet.stderr.lower()
          and "token" not in quiet.stdout.lower() + quiet.stderr.lower(), f"{quiet and (quiet.returncode, quiet.stdout, quiet.stderr)} {why}")
    wmid, wbody = text("INFO", 28, PEER, ME)
    r, why = watch(w, wbody)
    check("carrier-only, no relay, no token: the watch delivers what the carrier brings, once, exit 0",
          r is not None and not why and r.returncode == 0 and r.stdout.count("subject-28") == 1,
          f"{r and (r.returncode, r.stdout, r.stderr)} {why}")
    r = w.run([INBOX, "--replay", wmid, "--json"])
    check("carrier-only, no relay, no token: replay by MESSAGE-ID answers from the journal",
          r.returncode == 0 and '"addressed":true' in r.stdout, f"{r.returncode} {r.stdout!r} {r.stderr!r}")
    r = w.run([INBOX, "--replay", "01a16dd0-0000-7000-8000-000000009998", "--json"])
    check("  an id the journal lacks is refused (non-zero), not asked of a relay",
          r.returncode != 0 and "Traceback" not in r.stderr, f"{r.returncode} {r.stdout!r} {r.stderr!r}")
    r = w.run([INBOX, "--history"])
    check("carrier-only, no relay, no token: --history reads the journal, exit 0", r.returncode == 0, f"{r.returncode} {r.stdout!r} {r.stderr!r}")

    # (1) the other two modes refuse the watch and a replay of an unknown id with the config line, as today.
    for m in (mode.RELAY_RECORD, mode.CARRIER_RECORD):
        set_mode(w, m)
        r = w.run([INBOX, "--until-delivery", "--deadline", "4"])
        check(f"{m}, no relay section: the watch ends at once with exit 3 and the config line on stdout",
              r.returncode == 3 and "no GZCoord integration configured" in r.stdout, f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        r = w.run([INBOX, "--replay", "01a16dd0-0000-7000-8000-000000009997", "--json"])
        check(f"{m}, no relay section: replay of an id the journal lacks says no relay is configured, exit 1",
              r.returncode == 1 and "no relay is configured" in r.stderr, f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        r = w.run([INBOX, "--until-delivery", "--deadline", "4"], **RELAY_NAMED(w))
        check(f"{m}, relay named and no token: the watch ends at once with exit 3 and the token line on stdout",
              r.returncode == 3 and "CLAUDE_BRIDGE_AUTH_TOKEN" in r.stdout, f"{r.returncode} {r.stdout!r} {r.stderr!r}")

    # (2) the watch sees the override: the state file says relay-record, which the watch refuses with no relay; the override
    # moves it to carrier-only, where it waits and delivers, and says so.
    set_mode(w, mode.RELAY_RECORD)
    wmid, wbody = text("INFO", 29, PEER, ME)
    import subprocess
    p = subprocess.Popen([INBOX, "--until-delivery", "--deadline", "40"], env={**w.env, **OVERRIDE}, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL, cwd=w.base)
    import time
    time.sleep(3)
    early = p.poll()
    w.push(wbody)
    out, err = p.communicate(timeout=100)
    check("override carrier-only over a relay-record state file: the watch waits, delivers the carrier's message, exit 0, and says"
          f" {mode.ENV} on stderr once", early is None and p.returncode == 0 and out.count("subject-29") == 1 and err.count(mode.ENV) == 1,
          f"early={early} {p.returncode} {out!r} {err!r}")
    # A watch started under the override is not moved by the state file's own changes (the override is the command's mode).
    set_mode(w, mode.CARRIER_RECORD)
    p = subprocess.Popen([INBOX, "--until-delivery", "--deadline", "14"], env={**w.env, **OVERRIDE}, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL, cwd=w.base)
    time.sleep(2)
    set_mode(w, mode.CARRIER_ONLY)
    set_mode(w, mode.RELAY_RECORD)
    out, err = p.communicate(timeout=100)
    check("  and a state file that changes under it does not end its arm: no mode change is announced, exit 0",
          p.returncode == 0 and "transport mode is now" not in err, f"{p.returncode} {out!r} {err!r}")
    # An unknown override: the watch refuses with the mode's line and exit 7.
    r = w.run([INBOX, "--until-delivery", "--deadline", "4"], **{mode.ENV: "bogus"})
    check("override 'bogus': the watch is refused, exit 7, the line names the variable and the modes", r.returncode == 7 and mode.ENV in r.stdout
          and "carrier-only" in r.stdout,
          f"{r.returncode} {r.stdout!r} {r.stderr!r}")


def unit_watcher(base: str) -> None:
    """mode.Watcher reads the override too: the poll of a running watch under the override never reports a change the state file
    makes, and reports one when the override is gone."""
    d = os.path.join(base, "wstate")
    mode.write(mode.CARRIER_ONLY, "h1/op", d)
    seen: list[str] = []
    old = os.environ.get(mode.ENV)
    try:
        os.environ[mode.ENV] = mode.CARRIER_RECORD
        w = mode.Watcher(mode.CARRIER_RECORD, d, every=0.0, on_error=seen.append)
        check("Watcher under the override: the file says carrier-only, the override carrier-record: no change",
              w.changed() is False and not seen, f"{seen}")
        os.environ[mode.ENV] = "bogus"
        check("  an unknown override is said (once) and the watch keeps its mode", w.changed() is False and len(seen) == 1
              and mode.ENV in seen[0], f"{seen}")
        del os.environ[mode.ENV]
        check("  with the override gone the file's mode is the change", w.changed() is True and w.current == mode.CARRIER_ONLY)
    finally:
        if old is None:
            os.environ.pop(mode.ENV, None)
        else:
            os.environ[mode.ENV] = old


def main() -> int:
    base = tempfile.mkdtemp(prefix="g2c-")
    w = None
    try:
        unit_watcher(base)
        w = G.World(base, relay=False)
        check("the carrier is up, the account is in carrier-only, the project has no relay section, the environment names no relay"
              " and holds no token, and the relay's port is closed",
              w.up() and mode.read(w.agent_dir)["mode"] == "carrier-only" and "CLAUDE_BRIDGE_URL" not in w.env
              and "CLAUDE_BRIDGE_AUTH_TOKEN" not in w.env, w.proc.stderr.read() if w.proc.poll() is not None else "")
        cases(w)
    finally:
        if w:
            w.close()
        shutil.rmtree(base, ignore_errors=True)
        for d in G.P.SCRATCH:
            shutil.rmtree(d, ignore_errors=True)
    print(f"\ntest_gzcoord_interweave_only_config: {'OK' if not fails() else f'FAILED — {fails()} check(s)'}")
    return 1 if fails() else 0


def fails() -> int:
    return G.fails


if __name__ == "__main__":
    sys.exit(main())
