#!/usr/bin/env python3
"""GZCOORD_JOURNAL=off is a break-glass with a record (ADR-041): every
message that crosses without the journal leaves one line in the agent's
journal-bypass.jsonl, never its body, and a bypass that cannot be recorded
does not happen. The commands are run by their real paths against a carrier
stand-in (tests/test_gzcoord_protocol.py `Carrier`), with a scratch state directory. Since
the relay left send and inbox (W15) the carrier numbers nothing, so an accepted line has no seq,
and receiving with the journal off is refused (exit 7), so the cases that bypassed a page went with
the relay. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import subprocess
import sys
import traceback
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_gzcoord_protocol as P  # noqa: E402 — its Carrier, scratch and command environment

CASES: list[tuple[str, Callable[[], None]]] = []
eq, ok, Failed = P.eq, P.ok, P.Failed
BODY = "THE-BODY-NEVER-IN-THE-RECORD"


def case(name: str) -> Callable:
    def add(fn: Callable[[], None]) -> Callable[[], None]:
        CASES.append((name, fn))
        return fn
    return add


def message(mid: str, frm: str | None = None, to: str | None = None) -> str:
    me = P.gzmsg.whoami()
    frm = frm or f"{me['host']}/{me['agent']}"
    addressing = f"TO: {to}\n" if to else "BROADCAST: true\n"
    return (f"[GZCOORD/1] INFO\nFROM: {frm}\nROLE: backend-dev\nPROJECT: fixture\n{addressing}"
            f"MESSAGE-ID: {mid}\nSUBJECT: s\n\nNOTES:\n{BODY}\n")


def record_path(state: str) -> str:
    return os.path.join(state, "agents", P.LOGIN, "journal-bypass.jsonl")


def lines_of(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    ok(BODY not in text, f"a body reached the record: {text}")
    return [json.loads(x) for x in text.split("\n") if x]


def env_of(carrier: "P.Carrier | None", state: str, **extra: str) -> dict:
    return P.inbox_env(carrier, AGENT_FABRIC_STATE_DIR=state, **extra)


def send(env: dict, text: str, *flags: str) -> subprocess.CompletedProcess:
    f = os.path.join(env["HOME"], "m.txt")
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(text)
    return subprocess.run([P.SEND_CMD, f, *flags], env=env, capture_output=True, text=True, timeout=60)


def refused_send(**extra: object) -> dict:
    return {"ok": False, "error": "disk full", "carried": 1, "queued": 0, **extra}


MID = "01a09fc1-0000-7000-8000-0000000000c1"


@case("a bypassed send leaves a pending line before the post and an accepted one after: 0600, no body, no seq")
def _():
    carrier, state = P.Carrier(), P.scratch("bypass-state-")
    try:
        r = send(env_of(carrier, state, GZCOORD_JOURNAL="off"), message(MID))
    finally:
        carrier.close()
    eq(r.returncode, 0, r.stderr)
    ok("GZCOORD_JOURNAL=off — this message is sent without being kept" in r.stderr, r.stderr)
    eq(len(carrier.posts), 1)
    got = lines_of(record_path(state))
    posted = carrier.posts[0]["text"]
    sha = hashlib.sha256(posted.encode()).hexdigest()
    eq([{k: x[k] for k in ("direction", "message_id", "sha256", "seq", "reason", "outcome")} for x in got],
       [{"direction": "out", "message_id": MID, "sha256": sha, "seq": None, "reason": "GZCOORD_JOURNAL=off",
         "outcome": "pending"},
        {"direction": "out", "message_id": MID, "sha256": sha, "seq": None, "reason": "GZCOORD_JOURNAL=off",
         "outcome": "accepted"}])
    ok(all(isinstance(x["at"], str) and x["at"].endswith("Z") for x in got), got)
    with open(record_path(state), "rb") as fh:
        raw = fh.read()
    ok(raw.endswith(b"\n") and b"\n\n" not in raw, f"the record holds a blank line: {raw!r}")
    eq(stat.S_IMODE(os.stat(record_path(state)).st_mode), 0o600)


@case("receiving with the journal off is refused: exit 7, the carrier not asked, no line written")
def _():
    carrier, state = P.Carrier(records=[P.record(message(MID, frm="x/y"))]), P.scratch("bypass-state-")
    try:
        r = subprocess.run([P.INBOX_CMD], env=env_of(carrier, state, GZCOORD_JOURNAL="off"), capture_output=True, text=True, timeout=60)
        r2 = subprocess.run([P.INBOX_CMD, "--until-delivery", "--deadline", "3"], env=env_of(carrier, state, GZCOORD_JOURNAL="off"),
                            capture_output=True, text=True, timeout=60)
    finally:
        carrier.close()
    eq(r.returncode, 7, r.stdout + r.stderr)
    eq(r2.returncode, 7, r2.stdout + r2.stderr)
    ok(BODY not in r.stdout + r2.stdout, "a message was shown with the journal off")
    eq(carrier.requests, [], "the carrier was not asked")
    ok(not os.path.exists(record_path(state)), "a line was written for a page that never crossed")


@case("a bypass record that cannot be written refuses: no post, exit 2")
def _():
    state = P.scratch("bypass-state-")
    os.makedirs(record_path(state))   # a directory where the file goes: no write succeeds, root or not
    carrier = P.Carrier()
    try:
        r = send(env_of(carrier, state, GZCOORD_JOURNAL="off"), message(MID))
    finally:
        carrier.close()
    eq(r.returncode, 2, r.stderr)
    eq(carrier.posts, [], "the carrier never saw it")
    ok("not sent: the journal-bypass record" in r.stderr and "only with a record of it" in r.stderr, r.stderr)
    ok("this message is sent without being kept" not in r.stderr, f"a refused send said it is sent: {r.stderr}")


@case("a symlink where the record goes is not followed: refused, its target untouched")
def _():
    state = P.scratch("bypass-state-")
    os.makedirs(os.path.dirname(record_path(state)))
    target = os.path.join(P.scratch("bypass-elsewhere-"), "victim")
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("untouched\n")
    os.symlink(target, record_path(state))
    carrier = P.Carrier()
    try:
        r = send(env_of(carrier, state, GZCOORD_JOURNAL="off"), message(MID))
    finally:
        carrier.close()
    eq(r.returncode, 2, r.stderr)
    eq(carrier.posts, [])
    with open(target, encoding="utf-8") as fh:
        eq(fh.read(), "untouched\n")


@case("a FIFO where the record goes is refused at once, not waited on with the agent's lock held")
def _():
    state = P.scratch("bypass-state-")
    os.makedirs(os.path.dirname(record_path(state)))
    os.mkfifo(record_path(state), 0o600)
    carrier = P.Carrier()
    try:
        r = send(env_of(carrier, state, GZCOORD_JOURNAL="off"), message(MID))   # send() times out at 60 s
    finally:
        carrier.close()
    eq(r.returncode, 2, r.stderr)
    eq(carrier.posts, [])


@case("no bypass, no record: the journal on, or a dry run with it off, writes no line")
def _():
    carrier, state = P.Carrier(), P.scratch("bypass-state-")
    try:
        r = send(env_of(carrier, state), message(MID))
        eq(r.returncode, 0, r.stderr)
        r = send(env_of(carrier, state, GZCOORD_JOURNAL="off"), message(MID[:-2] + "c4"), "--dry-run")
        eq(r.returncode, 0, r.stderr)
    finally:
        carrier.close()
    ok(not os.path.exists(record_path(state)), "a line was written with nothing bypassed")


@case("a write that lands short, or fails after landing, is truncated back: refused, the record byte-identical")
def _():
    from gzcoord import bypass
    state = P.scratch("bypass-state-")
    saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
    os.environ["AGENT_FABRIC_STATE_DIR"] = state
    real_write, real_fsync, real_ftruncate = os.write, os.fsync, os.ftruncate

    def raising(*_a):
        raise OSError(errno.EIO, "Input/output error")

    def refused(why: str) -> str:
        try:
            bypass.record([bypass.entry("out", message(MID[:-2] + "d1"))])
        except bypass.BypassUnrecorded as e:
            return str(e)
        raise Failed(f"{why}: not refused")

    def raw() -> bytes:
        with open(record_path(state), "rb") as fh:
            return fh.read()
    try:
        bypass.record([bypass.entry("out", message(MID))])
        before = raw()
        os.write = lambda fd, data: real_write(fd, data[:7])   # a full disk takes a prefix
        try:
            said = refused("a short write")
        finally:
            os.write = real_write
        ok("wrote 7 of" in said, said)
        eq(raw(), before, "the short write's bytes stayed")
        os.fsync = raising   # every byte landed, then the write fails
        try:
            refused("an fsync that fails")
        finally:
            os.fsync = real_fsync
        eq(raw(), before, "a refused crossing's line stayed")
        bypass.record([bypass.entry("out", message(MID[:-2] + "d2"))])
        eq([x["message_id"] for x in lines_of(record_path(state))], [MID, MID[:-2] + "d2"], "the next record appends cleanly")
        os.write, os.ftruncate = (lambda fd, data: real_write(fd, data[:7])), raising
        try:
            said = refused("a short write whose undo fails")
        finally:
            os.write, os.ftruncate = real_write, real_ftruncate
        ok("the partial line could not be removed" in said and "may end in a fragment" in said, said)
    finally:
        os.write, os.fsync, os.ftruncate = real_write, real_fsync, real_ftruncate
        if saved is None:
            os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
        else:
            os.environ["AGENT_FABRIC_STATE_DIR"] = saved


@case("a bypassed send the carrier refuses leaves pending then failed: an auditor tells sent from refused")
def _():
    carrier, state = P.Carrier(send=refused_send()), P.scratch("bypass-state-")
    try:
        r = send(env_of(carrier, state, GZCOORD_JOURNAL="off"), message(MID))
    finally:
        carrier.close()
    eq(r.returncode, 3, r.stderr)
    eq([(x["outcome"], x["seq"]) for x in lines_of(record_path(state))], [("pending", None), ("failed", None)])


@case("a record that ends in a fragment: the next line starts on a fresh line, readable after it")
def _():
    state = P.scratch("bypass-state-")
    os.makedirs(os.path.dirname(record_path(state)))
    with open(record_path(state), "w", encoding="ascii") as fh:
        fh.write('{"at":"2026-10-06T00:00:00.000Z","direction":"out","messa')   # a kill mid-write left this
    carrier = P.Carrier()
    try:
        r = send(env_of(carrier, state, GZCOORD_JOURNAL="off"), message(MID))
    finally:
        carrier.close()
    eq(r.returncode, 0, r.stderr)
    with open(record_path(state), encoding="ascii") as fh:
        lines = fh.read().split("\n")
    ok(lines[0].endswith('"messa'), lines)
    eq([json.loads(x)["outcome"] for x in lines[1:] if x], ["pending", "accepted"], lines)


@case("--replay under the bypass shows the record and leaves no line: the journal's, the carrier asked nothing")
def _():
    carrier, state = P.Carrier(), P.scratch("bypass-state-")
    env = env_of(carrier, state, GZCOORD_JOURNAL="off")
    P.seed_journal(env, (message(MID, frm="x/y"), 7))
    try:
        r = subprocess.run([P.INBOX_CMD, "--replay", MID], env=env, capture_output=True, text=True, timeout=60)
    finally:
        carrier.close()
    eq(r.returncode, 0, r.stdout + r.stderr)
    ok(BODY in r.stdout, f"the record was not shown: {r.stdout}{r.stderr}")
    eq(carrier.requests, [])
    ok(not os.path.exists(record_path(state)), "a replay wrote a bypass line")


@case("a carrier that took only some recipients, or refused with no count, is \"unknown\", never \"failed\": it may hold it")
def _():
    for kw in (refused_send(carried=3, queued=1), {"ok": False, "error": "bad request"}):
        carrier, state = P.Carrier(send=kw), P.scratch("bypass-state-")
        try:
            r = send(env_of(carrier, state, GZCOORD_JOURNAL="off"), message(MID))
        finally:
            carrier.close()
        eq(r.returncode, 3, f"{kw}: {r.stderr}")
        eq([x["outcome"] for x in lines_of(record_path(state))], ["pending", "unknown"], str(kw))


@case("a send's second line that cannot be written is said, never a refusal: the message has left")
def _():
    state = P.scratch("bypass-state-")

    def swap(_req: dict) -> dict:   # mid-post: the record becomes a directory, so the second line fails
        os.remove(record_path(state))
        os.makedirs(record_path(state))
        return {"ok": True, "carried": 1, "queued": 1}
    carrier = P.Carrier(send=swap)
    try:
        r = send(env_of(carrier, state, GZCOORD_JOURNAL="off"), message(MID))
    finally:
        carrier.close()
    eq(r.returncode, 0, r.stderr)
    ok(r.stdout.startswith("sent INFO "), r.stdout)
    ok("the send's outcome (accepted) is not in the bypass record" in r.stderr, r.stderr)


@case("a FIFO where the ledger of sent ids goes never hangs a send: the check and the record are said, the send goes")
def _():
    state = P.scratch("ledger-fifo-")
    ledger = os.path.join(state, "agents", P.LOGIN, "gzcoord-sent.jsonl")
    os.makedirs(os.path.dirname(ledger))
    os.mkfifo(ledger, 0o600)
    carrier = P.Carrier()
    try:
        r = send(env_of(carrier, state), message(MID))   # send() times out at 60 s: a blocking open would hang here
    finally:
        carrier.close()
    eq(r.returncode, 0, r.stderr)
    eq(len(carrier.posts), 1)
    ok("is not a regular file" in r.stderr and "a reused id is not checked" in r.stderr, r.stderr)


@case("a bypassed send with no carrier running is failed: it provably never arrived")
def _():
    state = P.scratch("bypass-state-")
    r = send(env_of(None, state, GZCOORD_JOURNAL="off"), message(MID))
    eq(r.returncode, 3, r.stderr)
    eq([x["outcome"] for x in lines_of(record_path(state))], ["pending", "failed"])


@case("an unknown outcome from stdin never promises a safe resend: a new id is minted unless the text carries it")
def _():
    carrier, state = P.Carrier(send=refused_send(carried=3, queued=1)), P.scratch("bypass-state-")
    try:
        env = env_of(carrier, state)
        text = message(MID).replace(f"MESSAGE-ID: {MID}\n", "")
        r = subprocess.run([P.SEND_CMD, "-"], env=env, input=text, capture_output=True, text=True, timeout=60)
    finally:
        carrier.close()
    eq(r.returncode, 3, r.stderr)
    ok("outcome unknown" in r.stderr and "a resend from stdin mints a new id" in r.stderr, r.stderr)
    ok("sending the same file again is safe" not in r.stderr, r.stderr)


def main() -> int:
    fails = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001 — a case that raises is a failure, reported
            fails += 1
            print(f"  FAIL {name}: {e}")
            if not isinstance(e, Failed):
                traceback.print_exc()
    import shutil
    for d in P.SCRATCH:
        shutil.rmtree(d, ignore_errors=True)
    print(f"test_gzcoord_bypass: {'OK' if not fails else f'FAILED — {fails}'} ({len(CASES)} cases)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
