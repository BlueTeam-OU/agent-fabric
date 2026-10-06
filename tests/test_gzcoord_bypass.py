#!/usr/bin/env python3
"""GZCOORD_JOURNAL=off is a break-glass with a record (ADR-041): every
message that crosses without the journal leaves one line in the agent's
journal-bypass.jsonl, never its body, and a bypass that cannot be recorded
does not happen. The commands are run by their real paths (the .mjs shims)
against a stub relay, with a scratch state directory. Plain script: prints
ok/FAIL, exit 1 on any failure."""
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
import test_gzcoord_protocol as P  # noqa: E402 — its Stub, scratch and command environment

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


class Relay:
    """The stub relay: sends answered with a seq, one page served once, acks counted."""

    def __init__(self, page: list[dict] | None = None):
        self.posts: list[dict] = []
        self.acks: list[str] = []
        served = [False]

        def answer(_h, _method, path, body):
            if path.startswith("/api/send"):
                self.posts.append(json.loads(body))
                return 200, json.dumps({"seq": 42, "id": "r42"})
            if path.startswith("/api/ack"):
                self.acks.append(json.loads(body).get("message_id"))
                return 200, "{}"
            if path.startswith("/api/wait"):
                if page is not None and not served[0]:
                    served[0] = True
                    return 200, json.dumps({"messages": page, "next_cursor": "c"})
                return 200, json.dumps({"messages": []})
            return 200, "{}"
        self.stub = P.Stub(answer)

    def env(self, state: str, **extra: str) -> dict:
        return P.cmd_env(CLAUDE_BRIDGE_URL=self.stub.url, CLAUDE_BRIDGE_AUTH_TOKEN="tok", GZCOORD_CHANNEL="fixture:chan",
                         AGENT_FABRIC_STATE_DIR=state, **extra)

    def close(self) -> None:
        self.stub.close()


def send(env: dict, text: str, *flags: str) -> subprocess.CompletedProcess:
    f = os.path.join(env["HOME"], "m.txt")
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(text)
    return subprocess.run(["node", P.SEND_CMD, f, *flags], env=env, capture_output=True, text=True, timeout=60)


def drain(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["node", P.INBOX_CMD], env=env, capture_output=True, text=True, timeout=60)


MID = "01a09fc1-0000-7000-8000-0000000000c1"


@case("a bypassed send leaves exactly one line, before the post: id, hash, no seq, 0600, never the body")
def _():
    relay, state = Relay(), P.scratch("bypass-state-")
    try:
        r = send(relay.env(state, GZCOORD_JOURNAL="off"), message(MID))
    finally:
        relay.close()
    eq(r.returncode, 0, r.stderr)
    ok("GZCOORD_JOURNAL=off — this message is sent without being kept" in r.stderr, r.stderr)
    eq(len(relay.posts), 1)
    got = lines_of(record_path(state))
    eq(len(got), 1, got)
    posted = relay.posts[0]["content"]
    eq({k: got[0][k] for k in ("direction", "message_id", "sha256", "seq", "reason")},
       {"direction": "out", "message_id": MID, "sha256": hashlib.sha256(posted.encode()).hexdigest(), "seq": None,
        "reason": "GZCOORD_JOURNAL=off"})
    ok(isinstance(got[0]["at"], str) and got[0]["at"].endswith("Z"), got[0])
    eq(stat.S_IMODE(os.stat(record_path(state)).st_mode), 0o600)


@case("a bypassed page leaves one line per record addressed here, with its seq; others' traffic none; one warning")
def _():
    other = "nowhere/else"
    page = [{"seq": 7, "id": "r7", "ts": "T7", "sender": "x/y", "content": message(MID, frm="x/y")},
            {"seq": 8, "id": "r8", "ts": "T8", "sender": "x/y", "content": message(MID[:-2] + "c2", frm="x/y", to=other)},
            {"seq": 9, "id": "r9", "ts": "T9", "sender": "x/y", "content": message(MID[:-2] + "c3", frm="x/y")}]
    relay, state = Relay(page), P.scratch("bypass-state-")
    try:
        r = drain(relay.env(state, GZCOORD_JOURNAL="off"))
    finally:
        relay.close()
    eq(r.returncode, 0, r.stdout + r.stderr)
    got = lines_of(record_path(state))
    eq([(x["direction"], x["message_id"], x["seq"]) for x in got],
       [("in", MID, 7), ("in", MID[:-2] + "c3", 9)], got)
    eq([x["sha256"] for x in got], [hashlib.sha256(page[i]["content"].encode()).hexdigest() for i in (0, 2)])
    eq(r.stdout.count("GZCOORD_JOURNAL=off — 2 message(s) addressed to you are shown without being kept"), 1, r.stdout)
    eq(sorted(relay.acks), ["r7", "r8", "r9"], "the page is acknowledged once recorded")


@case("a bypass record that cannot be written refuses: no post, exit 2; the page held, neither shown nor acknowledged")
def _():
    state = P.scratch("bypass-state-")
    os.makedirs(record_path(state))   # a directory where the file goes: no write succeeds, root or not
    relay = Relay()
    try:
        r = send(relay.env(state, GZCOORD_JOURNAL="off"), message(MID))
    finally:
        relay.close()
    eq(r.returncode, 2, r.stderr)
    eq(relay.posts, [], "the carrier never saw it")
    ok("not sent: the journal-bypass record" in r.stderr and "only with a record of it" in r.stderr, r.stderr)
    ok("this message is sent without being kept" not in r.stderr, f"a refused send said it is sent: {r.stderr}")
    page = [{"seq": 7, "id": "r7", "ts": "T7", "sender": "x/y", "content": message(MID, frm="x/y")}]
    relay = Relay(page)
    try:
        r = drain(relay.env(state, GZCOORD_JOURNAL="off"))
    finally:
        relay.close()
    eq(r.returncode, 0, r.stdout + r.stderr)
    eq(relay.acks, [], "nothing acknowledged: the relay shows it again")
    ok(BODY not in r.stdout, f"the held message was shown: {r.stdout}")
    ok("1 message(s) addressed to you are held, not shown: the journal-bypass record" in r.stdout, r.stdout)


@case("a symlink where the record goes is not followed: refused, its target untouched")
def _():
    state = P.scratch("bypass-state-")
    os.makedirs(os.path.dirname(record_path(state)))
    target = os.path.join(P.scratch("bypass-elsewhere-"), "victim")
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("untouched\n")
    os.symlink(target, record_path(state))
    relay = Relay()
    try:
        r = send(relay.env(state, GZCOORD_JOURNAL="off"), message(MID))
    finally:
        relay.close()
    eq(r.returncode, 2, r.stderr)
    eq(relay.posts, [])
    with open(target, encoding="utf-8") as fh:
        eq(fh.read(), "untouched\n")


@case("a FIFO where the record goes is refused at once, not waited on with the agent's lock held")
def _():
    state = P.scratch("bypass-state-")
    os.makedirs(os.path.dirname(record_path(state)))
    os.mkfifo(record_path(state), 0o600)
    relay = Relay()
    try:
        r = send(relay.env(state, GZCOORD_JOURNAL="off"), message(MID))   # send() times out at 60 s
    finally:
        relay.close()
    eq(r.returncode, 2, r.stderr)
    eq(relay.posts, [])


@case("a record the relay sends with a lone surrogate crosses the bypass recorded, not as a relay failure")
def _():
    content = message(MID, frm="x/y").replace(BODY, "half \ud800 a pair")
    odd_id = MID[:-2] + "\ud800"   # in a field the line carries, not only in the body it never does
    page = [{"seq": 7, "id": "r7", "ts": "T7", "sender": "x/y", "content": content},
            {"seq": 8, "id": "r8", "ts": "T8", "sender": "x/y", "content": message(odd_id, frm="x/y")}]
    relay, state = Relay(page), P.scratch("bypass-state-")
    try:
        r = drain(relay.env(state, GZCOORD_JOURNAL="off"))
    finally:
        relay.close()
    eq(r.returncode, 0, r.stdout + r.stderr)
    ok("relay unreachable" not in r.stderr, r.stderr)
    got = lines_of(record_path(state))
    eq([(x["message_id"], x["seq"], x["sha256"]) for x in got],
       [(MID, 7, hashlib.sha256(content.encode("utf-8", "surrogatepass")).hexdigest()),
        (odd_id, 8, hashlib.sha256(page[1]["content"].encode("utf-8", "surrogatepass")).hexdigest())], got)
    eq(sorted(relay.acks), ["r7", "r8"])


@case("no bypass, no record: the journal on (a send and a page), or a dry run with it off, writes no line")
def _():
    page = [{"seq": 7, "id": "r7", "ts": "T7", "sender": "x/y", "content": message(MID[:-2] + "c5", frm="x/y")}]
    relay, state = Relay(page), P.scratch("bypass-state-")
    try:
        r = send(relay.env(state), message(MID))
        eq(r.returncode, 0, r.stderr)
        r = send(relay.env(state, GZCOORD_JOURNAL="off"), message(MID[:-2] + "c4"), "--dry-run")
        eq(r.returncode, 0, r.stderr)
        r = drain(relay.env(state))
        eq(r.returncode, 0, r.stdout + r.stderr)
        eq(relay.acks, ["r7"], "the journal kept the page and it was acknowledged")
    finally:
        relay.close()
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
