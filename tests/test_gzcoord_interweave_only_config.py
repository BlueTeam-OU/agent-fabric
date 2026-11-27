#!/usr/bin/env python3
"""The InterWeave-only data plane's config (cutover plan docs/proposals/gzcoord-interweave-only-cutover.md, section 6; since W15
the carrier is the only transport), through the real entry points with a real carrier and a relay that refuses every connection:

  1. no relay is dialled and no relay setting is read, whatever the environment, the project's integration or the account's
     transport-mode file says: with no relay token and no relay section anywhere (no CLAUDE_BRIDGE_*, no GZCOORD_CHANNEL, a
     project integration holding no relay_url) a send, the watch and a replay all work; so they do with a relay named and no
     token, with a malformed token, with a relay-record or carrier-record file (read, and changing nothing), with a damaged file,
     and with any GZCOORD_TRANSPORT_MODE (read only by the presence child: the send and the inbox neither say nor obey it).
  2. an account with no transport-mode.json reads carrier-only, and a read never creates the file.

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
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

SEND = os.path.join(BIN, "gzcoord-send")
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
    n = [40]

    def sends_ok(label: str, force: bool = False, **env: str) -> None:
        """`force` skips the presence ask: its child is the one reader of the mode and the override, and refuses a mode it cannot read."""
        n[0] += 1
        mid, path = send_file(w, n[0])
        before = posted()
        r = w.run([SEND, path, *(["--force"] if force else [])], **env)
        check(f"{label}: send exits 0, `sent INFO <id>`, the peer posted through the carrier, no word of a relay, a token or a mode (the presence child may say its own mode, never the send)",
              r.returncode == 0 and r.stdout == f"sent INFO {mid}\n" and sent_through_carrier(w, before)
              and not any(x in r.stderr.lower() for x in (("for this command",) if force else ("token", "relay", "transport mode", mode.ENV.lower()))),
              f"{r.returncode} {r.stdout!r} {r.stderr!r}")

    with G.AgentdStandIn(w.run_dir) as agentd:
        # (1) a send with no relay token and no relay section. The presence ask above it needs neither.
        mid, path = send_file(w, 20)
        before = posted()
        r = w.run([SEND, path])
        check("no relay token and no relay section: send exits 0, `sent INFO <id>`, the peer posted through the carrier,"
              " presence asked of the agentd, no word of a relay or a token",
              r.returncode == 0 and r.stdout == f"sent INFO {mid}\n" and sent_through_carrier(w, before) and len(agentd.requests) == 1
              and "token" not in r.stderr.lower() and "relay" not in r.stderr.lower(), f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        # The same account with the relay named but still no token: the token is not looked for.
        sends_ok("a relay URL and channel named and no token", **RELAY_NAMED(w))
        # A token that is malformed (a line break) is refused where one is read; none is read, so it is never met.
        sends_ok("a malformed relay token in the environment", CLAUDE_BRIDGE_AUTH_TOKEN="a\nb")

        # The old modes in the state file are read and change nothing: the send is the same one, through the carrier.
        for m in (mode.RELAY_RECORD, mode.CARRIER_RECORD):
            set_mode(w, m)
            sends_ok(f"a {m} state file, no relay section")
            sends_ok(f"a {m} state file, a relay named and no token", **RELAY_NAMED(w))
        # A damaged state file does not stop the send either.
        with open(mode.path(w.agent_dir), "w", encoding="utf-8") as fh:
            fh.write("not json")
        mid, path = send_file(w, 39)
        r = w.run([SEND, path])
        check("a damaged state file: the presence ask, the one reader of the mode, refuses the send (exit 4, nothing posted)",
              r.returncode == 4 and "presence is unknown" in r.stderr and not carried(w, mid),
              f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        sends_ok("a damaged state file, the presence ask skipped by --force", force=True)
        set_mode(w, mode.CARRIER_ONLY)

        # The override is not a send's or an inbox's: no value of it is refused, said or obeyed.
        sends_ok(f"{mode.ENV}=relay-record over a carrier-only state file", **{mode.ENV: mode.RELAY_RECORD})
        for bad in ("carrier", "CARRIER-ONLY", "bogus", ""):
            sends_ok(f"{mode.ENV}={bad!r}, the presence ask skipped by --force", force=True, **{mode.ENV: bad})

    # (1) the watch and replay, no relay anywhere.
    quiet, why = watch(w, None, deadline=4)
    check("no relay: the watch waits to its deadline, exit 0, no word of a relay or token",
          quiet is not None and quiet.returncode == 0 and "relay" not in quiet.stdout.lower() + quiet.stderr.lower()
          and "token" not in quiet.stdout.lower() + quiet.stderr.lower(), f"{quiet and (quiet.returncode, quiet.stdout, quiet.stderr)} {why}")
    wmid, wbody = text("INFO", 28, PEER, ME)
    r, why = watch(w, wbody)
    check("no relay, no token: the watch delivers what the carrier brings, once, exit 0",
          r is not None and not why and r.returncode == 0 and r.stdout.count("subject-28") == 1,
          f"{r and (r.returncode, r.stdout, r.stderr)} {why}")
    r = w.run([INBOX, "--replay", wmid, "--json"])
    check("no relay, no token: replay by MESSAGE-ID answers from the journal",
          r.returncode == 0 and '"addressed":true' in r.stdout, f"{r.returncode} {r.stdout!r} {r.stderr!r}")
    r = w.run([INBOX, "--replay", "01a16dd0-0000-7000-8000-000000009998", "--json"])
    check("  an id the journal lacks is refused (non-zero), not asked of a relay",
          r.returncode != 0 and "Traceback" not in r.stderr and "relay" not in r.stderr.lower(), f"{r.returncode} {r.stdout!r} {r.stderr!r}")
    r = w.run([INBOX, "--history"])
    check("no relay, no token: --history reads the journal, exit 0", r.returncode == 0, f"{r.returncode} {r.stdout!r} {r.stderr!r}")

    # (1) the old modes, a relay named and no token, and an override of any value: the watch and a replay are the same.
    for label, env in ((f"{mode.RELAY_RECORD} state file", None), (f"{mode.CARRIER_RECORD} state file", None),
                       ("a relay named and no token", RELAY_NAMED(w)), (f"{mode.ENV}=bogus", {mode.ENV: "bogus"})):
        if label.endswith("state file"):
            set_mode(w, label.split()[0])
        r = w.run([INBOX, "--until-delivery", "--deadline", "4"], **(env or {}))
        check(f"{label}: the watch waits to its deadline, exit 0, nothing of a relay, a token or a mode said",
              r.returncode == 0 and not any(x in (r.stdout + r.stderr).lower() for x in ("relay", "token", "transport mode")),
              f"{r.returncode} {r.stdout!r} {r.stderr!r}")
        r = w.run([INBOX, "--replay", "01a16dd0-0000-7000-8000-000000009997", "--json"], **(env or {}))
        check(f"{label}: replay of an id the journal lacks is refused as unknown, exit 1, not for want of a relay",
              r.returncode == 1 and "no relay is configured" not in r.stderr, f"{r.returncode} {r.stdout!r} {r.stderr!r}")
    set_mode(w, mode.CARRIER_ONLY)


def unit_default(base: str) -> None:
    """An account with no transport-mode.json reads carrier-only, and the read does not create the file."""
    d = os.path.join(base, "nostate")
    os.makedirs(d)
    got = mode.read(d)
    check("an account with no transport-mode.json reads carrier-only, with no setter", got == {"mode": mode.CARRIER_ONLY, "set_by": None, "set_at": None}
          and mode.DEFAULT == mode.CARRIER_ONLY, f"{got}")
    check("  and the read creates nothing", os.listdir(d) == [], f"{os.listdir(d)}")


def unit_presence() -> None:
    """The presence child reads the command's mode, override included (review of #638, F2): the dual leg would answer anyway, so
    only a direct read shows it. It is the one reader of the override left."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    from control import presence
    old = os.environ.get(mode.ENV)
    try:
        os.environ[mode.ENV] = mode.CARRIER_ONLY
        check("the presence child's mode read is the override", presence._read_mode() == mode.CARRIER_ONLY)
    finally:
        if old is None:
            os.environ.pop(mode.ENV, None)
        else:
            os.environ[mode.ENV] = old


def main() -> int:
    base = tempfile.mkdtemp(prefix="g2c-")
    w = None
    try:
        unit_default(base)
        unit_presence()
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
