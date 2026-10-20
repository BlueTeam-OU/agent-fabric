#!/usr/bin/env python3
"""tools/fabric/gh_ledger.py — what the fabric spends of GitHub's quota, who
spent it, and how much is left.

The fleet shares ONE GitHub account, so one 5000-call REST hour is shared by
every session on every host; on 2026-10-20 it ran out (core 0/5000) and
nobody could say which tool spent it. gh.py is the one door every Python
call goes through, so it records each call here:

  $STATE/agents/<login>/gh-ledger.jsonl   one line per call:
      {"t": "<UTC>", "login", "kind": "rest|graphql|free", "call": "api GET
       repos/N/N/pulls/N/reviews", "caller": "<module>", "status": "ok" |
       <HTTP status> | "timeout" | "error", "s": <seconds>}
  $STATE/agents/<login>/gh-rate.json      the last `gh api rate_limit` answer

`kind` is the transport gh uses for that subcommand, not a measurement:
`gh api graphql` and `gh pr|issue|repo|project …` ride GraphQL (its own 5000
point budget), `gh api <path>` and the rest ride REST (the core budget).
`rate_limit` itself costs nothing and is recorded as "free".

The ledger is telemetry. A write that fails (full disk, a state directory
that does not exist) never fails or changes the call it describes, and says
nothing: the call's own result is what the caller acts on.

  fabric-gh-ledger [--since 1h] [--all-logins] [--calls]   per-caller counts
  fabric-gh-ledger --rate                                  the budget, now

The summary reads this login's file only; the fleet's total is the sum of
each account's (an account's file is its own, and 700-homed).
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import pwd
import re
import subprocess
import sys
import time

LEDGER = "gh-ledger.jsonl"
RATE = "gh-rate.json"
# A ledger past this is moved to .1 (one generation): the summary asks for an
# hour or a day, and a runaway poller must not fill the state volume.
MAX_BYTES = 8 * 1024 * 1024
# A snapshot younger than this answers `budget()` without a call.
RATE_MAX_AGE_S = 30.0
RATE_TIMEOUT_S = 20

_GRAPHQL_SUBCOMMANDS = {"pr", "issue", "repo", "project", "gist", "search"}
_DIGITS = re.compile(r"\d+")
_SHA = re.compile(r"\b[0-9a-f]{40}\b|\b[0-9a-f]{7,12}\b")


def state_dir() -> str | None:
    """This login's state directory, as runtime/identity.agent_state_dir
    names it (the effective user's login). None when the account has no
    passwd entry: no ledger then."""
    try:
        login = pwd.getpwuid(os.geteuid()).pw_name
    except KeyError:
        return None
    root = os.environ.get("AGENT_FABRIC_STATE_DIR")
    if root:
        root = os.path.abspath(root)
    else:
        root = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"),
                            "agent-fabric")
    return os.path.join(root, "agents", login)


def classify(args: list[str]) -> tuple[str, str]:
    """(kind, call) for a gh argument list: the call with its numbers and
    shas collapsed (`api GET repos/o/r/pulls/N/reviews`), so two polls of
    different PRs count as the same call."""
    if not args:
        return "rest", "gh"
    if args[0] == "api":
        path = next((a for a in args[1:] if not a.startswith("-") and a not in ("GET", "POST", "PUT", "PATCH", "DELETE")), "")
        method = "GET"
        for i, a in enumerate(args):
            if a in ("--method", "-X") and i + 1 < len(args):
                method = args[i + 1]
        path = _SHA.sub("SHA", _DIGITS.sub("N", path.split("?")[0].strip("/")))
        if path == "graphql":
            return "graphql", "api graphql"
        if path == "rate_limit":
            return "free", "api rate_limit"
        return "rest", f"api {method} {path}"
    kind = "graphql" if args[0] in _GRAPHQL_SUBCOMMANDS else "rest"
    words = [a for a in args[:2] if not a.startswith("-")]
    return kind, " ".join(words)


def caller_module(skip_file: str) -> str:
    """The module that asked gh.py for the call: the first frame outside
    gh.py and this file."""
    frame = sys._getframe(1)
    while frame is not None:
        name = frame.f_code.co_filename
        if name not in (skip_file, __file__):
            base = os.path.basename(name)
            return base[:-3] if base.endswith(".py") else base
        frame = frame.f_back
    return "?"


def record(args: list[str], caller: str, status, seconds: float) -> None:
    kind, call = classify(args)
    if status == 304:
        kind = "free"   # not modified: GitHub does not count it against the limit
    directory = state_dir()
    if directory is None:
        return
    line = json.dumps({"t": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "login": os.path.basename(directory), "kind": kind, "call": call, "caller": caller,
                       "status": status, "s": round(seconds, 2)}, separators=(",", ":")) + "\n"
    path = os.path.join(directory, LEDGER)
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        try:
            if os.path.getsize(path) > MAX_BYTES:
                os.replace(path, path + ".1")
        except OSError:
            pass
        # One O_APPEND write of a short line: two processes of this account
        # never interleave inside it.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode())
        finally:
            os.close(fd)
    except OSError:
        return


# ── the budget ─────────────────────────────────────────────────────────

def _read_snapshot(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) and isinstance(doc.get("resources"), dict) else None
    except (OSError, ValueError):
        return None


def rate_limit(*, max_age: float = RATE_MAX_AGE_S, now=time.time) -> dict | None:
    """GitHub's rate-limit resources ({"core": {"limit", "remaining",
    "reset", "used"}, "graphql": …}) as `gh api rate_limit` last said, at
    most `max_age` seconds old; None when it cannot be read. Never a guess:
    a caller that gets None calls as it did before.

    The endpoint is free, so asking costs no quota; the snapshot file only
    saves a process."""
    directory = state_dir()
    path = os.path.join(directory, RATE) if directory else None
    snap = _read_snapshot(path) if path else None
    if snap is not None and now() - float(snap.get("at") or 0) <= max_age:
        return snap["resources"]
    started = time.monotonic()
    try:
        r = subprocess.run(["gh", "api", "rate_limit"], capture_output=True, text=True, timeout=RATE_TIMEOUT_S,
                           stdin=subprocess.DEVNULL)
        status = "ok" if r.returncode == 0 else "error"
        doc = json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        status, doc = "error", None
    record(["api", "rate_limit"], "gh_ledger", status, time.monotonic() - started)
    resources = doc.get("resources") if isinstance(doc, dict) else None
    if not isinstance(resources, dict):
        return None
    if path:
        try:
            os.makedirs(directory, mode=0o700, exist_ok=True)
            tmp = f"{path}.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"at": now(), "resources": resources}, fh)
            os.replace(tmp, path)
        except OSError:
            pass
    return resources


def reset_at(epoch) -> str:
    """HH:MMZ, UTC."""
    return datetime.datetime.fromtimestamp(float(epoch), datetime.timezone.utc).strftime("%H:%MZ")


def wait_seconds(resource: str = "core", floor: int = 100, *, now=time.time, resources: dict | None = None) -> float:
    """How long a poller should wait before its next call so as not to spend
    what is left: 0 while `resource` has more than `floor` calls left, else
    the seconds to its reset. 0 too when the budget cannot be read — unknown
    stays unknown, and the call then fails or succeeds on its own terms."""
    res = resources if resources is not None else rate_limit(now=now)
    entry = (res or {}).get(resource)
    try:
        remaining, reset = int(entry["remaining"]), float(entry["reset"])
    except (TypeError, KeyError, ValueError):
        return 0.0
    if remaining > floor:
        return 0.0
    return max(0.0, reset - now()) + 1.0


def limited_reason(resource: str = "core", *, now=time.time) -> tuple[str, float | None]:
    """The words for a call refused on a rate limit, and the reset epoch
    when the primary limit is what was hit."""
    res = rate_limit(max_age=0, now=now)
    entry = (res or {}).get(resource) if res else None
    try:
        remaining, reset = int(entry["remaining"]), float(entry["reset"])
    except (TypeError, KeyError, ValueError):
        return "rate limited (the reset time could not be read)", None
    if remaining > 0:
        return "rate limited by a secondary limit (the budget itself is not spent); retry in a minute", None
    return f"rate limited until {reset_at(reset)}", reset


# ── the summary ────────────────────────────────────────────────────────

def _parse_since(text: str) -> float:
    m = re.fullmatch(r"(\d+)([smhd]?)", text.strip())
    if not m:
        raise SystemExit(f"fabric-gh-ledger: --since {text!r}: use 90, 90s, 30m, 1h or 2d")
    return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def read_ledger(since_s: float, *, now=time.time) -> list[dict]:
    directory = state_dir()
    rows: list[dict] = []
    if not directory:
        return rows
    cutoff = now() - since_s
    for name in (LEDGER + ".1", LEDGER):
        try:
            with open(os.path.join(directory, name), encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                        t = datetime.datetime.strptime(row["t"], "%Y-%m-%dT%H:%M:%SZ").replace(
                            tzinfo=datetime.timezone.utc).timestamp()
                    except (ValueError, KeyError, TypeError):
                        continue
                    if t >= cutoff and isinstance(row, dict):
                        rows.append(row)
        except OSError:
            continue
    return rows


def summarize(rows: list[dict], *, calls: bool = False) -> str:
    if not rows:
        return "no gh calls recorded in that window"
    by_caller: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    by_call: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    for r in rows:
        by_caller[str(r.get("caller"))][str(r.get("kind"))] += 1
        by_call[(str(r.get("caller")), str(r.get("call")))][str(r.get("kind"))] += 1
    out = [f"{'caller':<28} {'rest':>6} {'graphql':>8} {'free':>5}"]
    for caller, c in sorted(by_caller.items(), key=lambda kv: -(kv[1]["rest"] + kv[1]["graphql"])):
        out.append(f"{caller:<28} {c['rest']:>6} {c['graphql']:>8} {c['free']:>5}")
    total = collections.Counter(str(r.get("kind")) for r in rows)
    out.append(f"{'total':<28} {total['rest']:>6} {total['graphql']:>8} {total['free']:>5}")
    if calls:
        out.append("")
        for (caller, call), c in sorted(by_call.items(), key=lambda kv: -sum(kv[1].values())):
            out.append(f"{sum(c.values()):>6}  {caller}: {call}  [{', '.join(k for k in c)}]")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="fabric-gh-ledger", description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", default="1h", help="window: 90, 90s, 30m, 1h, 2d (default 1h)")
    ap.add_argument("--calls", action="store_true", help="also list each distinct call")
    ap.add_argument("--rate", action="store_true", help="print the budget now (free) and exit")
    args = ap.parse_args(argv)
    if args.rate:
        res = rate_limit(max_age=0)
        if res is None:
            print("fabric-gh-ledger: the rate limit could not be read", file=sys.stderr)
            return 1
        for name in ("core", "graphql"):
            e = res.get(name) or {}
            print(f"{name}: {e.get('remaining')}/{e.get('limit')}, resets {reset_at(e['reset']) if 'reset' in e else '?'}")
        return 0
    print(summarize(read_ledger(_parse_since(args.since)), calls=args.calls))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
