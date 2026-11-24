"""tools/fabric/gzcoord/carrier/control_parity.py — the control plane's parity computation (agent-fabric
ADR-029 rule 18, §2): for a window, which carriers each account's reply to each `fabric-ctl` request came by, how
long each took, and why the second carrier missed. It measures; whether InterWeave becomes control's record is
the owner's word on a report made from it (docs/live-checks/), never this code's.

INPUT   `control-arrivals.jsonl` of the operator's account (control_link.ArrivalLog), as `LOGIN=FILE`; only that file is
        read for pairs and causes (other accounts' files are accepted and listed, and contribute nothing yet). One JSON line per record that arrived, written by two processes into the
        one file of an account: `who` "ctl" (fabric-ctl: a `sent`/`sent-alone` line per request it made, with its
        `to` and `timeout_s`, one `no-session` or `session-lost` line when its session with agentd was never made or ended under it,
        and a line per reply copy it was shown, by carrier relay|interweave) and "agentd" (the replies its
        carrier routed — verdict ok | no-waiter | held | forged-from — and the requests that came by InterWeave).
        A `sent` line with a `timeout_s` that is present but unusable is counted in `malformed_timeout`.
        `t` has a one-second resolution, so a latency is good to a second either way.
PAIR    (request id, addressee) for every request sent by fabric-ctl in dual (the `sent` line's `to`), whose `t` is
        in [start, end). A reply line whose request has no `sent` line (a fabric-ctl from before it wrote them) is a
        pair too, listed under `unrecorded`: an account that never answered cannot be seen for those requests.
OUTCOME per pair, by the copies fabric-ctl was shown: `both`; `interweave-only` (the relay's copy did not come);
        `relay-only` (the miss of the second carrier, with its CAUSE); `none` (cause `timeout`).
CAUSE   of a relay-only pair, first that the logs show:
          no-session  fabric-ctl found no session with the operator's agentd (its `no-session` line): the accounts' InterWeave
                      replies reached no waiter, and with the carrier alone this run says nothing was sent. No miss; a pair of that run
                      with no copy at all stays a `timeout` and is counted here, not in `missed`.
          late        the reply came to the operator's agentd after fabric-ctl had left, but inside the request's own
                      `timeout_s` (its `sent` line, whole seconds: a reply at the second it ends is a miss): in dual fabric-ctl leaves DUAL_GRACE_S after every account has answered
                      (by either carrier), with the carrier alone it keeps waiting for the replies, so this reply
                      would have been collected. Not counted as a miss; its latency is `interweave_late_s`. A reply later
                      than `timeout_s`, or from a log whose `sent` line has none, stays no-waiter (j160: 680 of 727
                      no-waiter lines of 2026-11-18..22 came 6-99 s after the request, all relay copies in by 8 s).
          no-waiter   the operator's agentd routed the reply and no session was waiting for it: past the timeout, or the
                      session was lost (fabric-ctl's `session-lost` line: the agentd left under it), or the old log has
                      no `timeout_s`
          relay-only  unknown: the operator's log shows no reason the InterWeave reply is missing (a refused request copy is
                      no cause: agentd answers both carriers whichever copy it took). Said so, never guessed.
        `sent-alone` requests (control_carrier names the second carrier alone) have no relay copy to be missed.
DRILL   `--drill START END`: the interval the InterWeave units were stopped. A pair whose request is inside it is
        listed apart and counted in no carrier's delivered or missed: a relay-only answer is what the drill expects.
LATENCY the first copy of a carrier minus the `sent` line's `t`, p50 and p95 by nearest rank, per carrier over the
        pairs that carrier delivered.
UNKNOWN stays unknown: a line that is not JSON, or lacks the keys it is read by, is counted in `skipped` and never
        read as an absence; a window whose lines are not all in the files is the caller's to say.
"""
from __future__ import annotations

import json
import math
import time
from typing import Any, Iterable

CARRIERS = ("relay", "interweave")
CAUSES = ("no-waiter", "late", "no-session", "relay-only", "timeout")


class InputError(Exception):
    """A file that cannot be read: the report is not computed from half a collection."""


def parse_t(t: str) -> float:
    import calendar
    return calendar.timegm(time.strptime(t, "%Y-%m-%dT%H:%M:%SZ"))


def iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def read_lines(path: str) -> tuple[list[dict], int]:
    """(the lines that are objects, how many lines were not). A file that does not exist or cannot be read is an InputError."""
    rows: list[dict] = []
    skipped = 0
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    skipped += 1
                    continue
                if isinstance(r, dict) and isinstance(r.get("t"), str):
                    try:
                        r["_t"] = parse_t(r["t"])
                    except ValueError:
                        skipped += 1
                        continue
                    rows.append(r)
                else:
                    skipped += 1
    except (OSError, UnicodeDecodeError) as e:
        raise InputError(f"{path}: {e}") from e
    return rows, skipped


def percentile(values: list[float], p: float) -> float | None:
    """Nearest rank; None for no values (never 0)."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def _finite(x: int | float) -> bool:
    try:
        return math.isfinite(x)
    except OverflowError:      # an integer too large for a float: json.loads accepts it, math.isfinite does not
        return False


def _is_str(x: Any) -> bool:
    return isinstance(x, str) and bool(x)


def compute(files: dict[str, list[dict]], operator: str, window: tuple[float, float], drill: tuple[float, float] | None = None,
            skipped: int = 0) -> dict:
    """`files` maps a login to the lines of its control-arrivals.jsonl; `operator` is the login whose fabric-ctl made the requests."""
    if operator not in files:
        raise InputError(f"the operator's file ({operator}) is not among the files given")
    start, end = window
    requests: dict[str, dict] = {}
    copies: dict[tuple[str, str], dict[str, float]] = {}          # (id, addressee) -> carrier -> first t
    routed: dict[tuple[str, str], dict[str, float]] = {}          # (id, sender) -> agentd verdict of the reply -> first t
    no_session: set[str] = set()                                  # requests fabric-ctl had no InterWeave session for
    lost_session: set[str] = set()                                # requests whose session fabric-ctl lost before its end
    bad_timeout = 0                                               # `sent` lines whose `timeout_s` is present but unusable
    for login, rows in files.items():
        for r in rows:
            who, kind, rid, verdict, carrier = r.get("who"), r.get("kind"), r.get("id"), r.get("verdict"), r.get("carrier")
            if login != operator:
                continue
            # agentd writes a `forged-from` line with a null kind when the forged record had none; the report reads no such line.
            if who not in ("ctl", "agentd") or (not isinstance(kind, str) and verdict != "forged-from"):
                skipped += 1       # a line whose writer is not ctl/agentd, or whose kind is not a string, cannot be read: counted, never an absence
                continue
            if who == "ctl" and kind == "request" and isinstance(verdict, str) and verdict.startswith("sent"):
                to = r.get("to")
                if not (_is_str(rid) and isinstance(to, list) and to and all(_is_str(x) for x in to)):
                    skipped += 1       # a request that names no addressee leaves the report: said, not read as no request
                    continue
                tmo = r.get("timeout_s")
                valid = isinstance(tmo, (int, float)) and not isinstance(tmo, bool) and _finite(tmo) and tmo > 0
                if rid not in requests:
                    if "timeout_s" in r and not valid:
                        bad_timeout += 1       # kept as "no timeout" (the conservative reading), but said so
                    requests[rid] = {"t": r["_t"], "to": list(to), "alone": verdict == "sent-alone", "op": r.get("op"),
                                     "timeout_s": tmo if valid else None}
            elif who == "ctl" and kind == "request" and verdict in ("no-session", "session-lost"):
                if not _is_str(rid):
                    skipped += 1
                    continue
                (no_session if verdict == "no-session" else lost_session).add(rid)
            elif kind == "reply" and who in ("ctl", "agentd") and not (_is_str(r.get("in_reply_to")) and _is_str(r.get("from")) and carrier in CARRIERS):
                skipped += 1
            elif kind == "reply" and _is_str(r.get("in_reply_to")) and _is_str(r.get("from")) and carrier in CARRIERS:
                key = (r["in_reply_to"], r["from"])
                if who == "ctl" and verdict in ("ok", "unauthenticated"):
                    copies.setdefault(key, {}).setdefault(carrier, r["_t"])
                elif who == "agentd" and carrier == "interweave" and isinstance(verdict, str):
                    routed.setdefault(key, {}).setdefault(verdict, r["_t"])
                elif who == "ctl" or (who == "agentd" and carrier == "interweave"):
                    skipped += 1       # a reply line of a writer the report reads, whose verdict it cannot read
            elif who == "ctl" and kind == "request":
                skipped += 1           # a request line that is neither a sent line nor a session verdict
    unrecorded = sorted({k for k in copies if k[0] not in requests})
    pairs: list[dict] = []
    for rid, q in requests.items():
        for addressee in dict.fromkeys(q["to"]):
            pairs.append({"id": rid, "addressee": addressee, "t": q["t"], "alone": q["alone"], "op": q["op"], "timeout_s": q["timeout_s"]})
    for rid, addressee in unrecorded:
        first = min(copies[(rid, addressee)].values())
        pairs.append({"id": rid, "addressee": addressee, "t": first, "alone": False, "op": None, "unrecorded": True})
    out_pairs: list[dict] = []
    in_drill: list[dict] = []
    stats = {c: {"delivered": 0, "missed": 0, "latency": []} for c in CARRIERS}
    stats["interweave"]["late"] = stats["interweave"]["no_session"] = 0
    causes = {c: 0 for c in CAUSES}
    for p in sorted(pairs, key=lambda x: (x["t"], x["id"], x["addressee"])):
        if not start <= p["t"] < end:
            continue
        key = (p["id"], p["addressee"])
        got = copies.get(key, {})
        row = {"id": p["id"], "addressee": p["addressee"], "t": iso(p["t"]), "op": p["op"], "carriers": sorted(got)}
        if p.get("unrecorded"):
            row["unrecorded"] = True
        if drill and drill[0] <= p["t"] < drill[1]:
            in_drill.append({**row, "outcome": "both" if len(got) == 2 else (f"{next(iter(got))}-only" if got else "none")})
            continue
        for c in CARRIERS:
            if c in got:
                stats[c]["delivered"] += 1
                stats[c]["latency"].append(max(0.0, got[c] - p["t"]))
                row[f"{c}_s"] = max(0.0, got[c] - p["t"])
        if "relay" in got and "interweave" in got:
            row["outcome"] = "both"
        elif "interweave" in got:
            row["outcome"] = "interweave-only"
            if not p["alone"] and not p.get("unrecorded"):
                stats["relay"]["missed"] += 1
        else:
            if "relay" in got:
                row["outcome"] = "relay-only"
                verdicts = routed.get(key, {})
                # The log names the reason whether or not agentd wrote a line about this reply.
                if p["id"] in no_session:
                    row["cause"] = "no-session"
                # A reply still `held` when agentd last wrote about it was never collected: agentd exits drop the held store with no line.
                elif "no-waiter" in verdicts or ("held" in verdicts and "ok" not in verdicts):
                    row["cause"] = "no-waiter"
                    arrived = min(verdicts[v] for v in ("no-waiter", "held") if v in verdicts)
                    if p["id"] not in lost_session and p.get("timeout_s") and arrived - p["t"] < math.floor(p["timeout_s"]):
                        row["cause"] = "late"
                        row["interweave_late_s"] = max(0.0, arrived - p["t"])
                else:
                    row["cause"] = "relay-only"
            else:
                row["outcome"] = "none"
                row["cause"] = "timeout"
                if not p["alone"]:
                    stats["relay"]["missed"] += 1

            # Not for a request that is not on record as sent in dual, or whose relay copy was never to come.
            if not p.get("unrecorded"):
                if row["cause"] == "late":
                    stats["interweave"]["late"] += 1
                elif row["cause"] == "no-session" or p["id"] in no_session:
                    # A run with no session sent nothing by the carrier: its silence is no miss, though a pair with no copy stays a timeout.
                    stats["interweave"]["no_session"] += 1
                else:
                    stats["interweave"]["missed"] += 1
        if row.get("cause") and not p.get("unrecorded"):
            causes[row["cause"]] += 1
        out_pairs.append(row)
    for c in CARRIERS:
        lat = stats[c].pop("latency")
        stats[c]["p50_s"], stats[c]["p95_s"] = percentile(lat, 50), percentile(lat, 95)
    return {"window": [iso(start), iso(end)], "drill": [iso(drill[0]), iso(drill[1])] if drill else None, "operator": operator,
            "logins": sorted(files), "pairs": out_pairs, "in_drill": in_drill, "carriers": stats, "causes": causes,
            "unrecorded": len(unrecorded), "skipped": skipped, "malformed_timeout": bad_timeout}


def _s(x: float | None) -> str:
    return "—" if x is None else f"{x:g} s"


def render_markdown(rep: dict) -> str:
    L = ["# Control parity report", "",
         f"Window [{rep['window'][0]}, {rep['window'][1]}), operator `{rep['operator']}`; arrival logs read: {', '.join(rep['logins'])}.",
         "Latency is a one-second-resolution difference of two logged times. It measures; the owner decides.", ""]
    L += ["| carrier | delivered | missed | p50 | p95 |", "|---|---|---|---|---|"]
    for c in CARRIERS:
        s = rep["carriers"][c]
        L.append(f"| {c} | {s['delivered']} | {s['missed']} | {_s(s['p50_s'])} | {_s(s['p95_s'])} |")
    L += ["", "Causes of the pairs the second carrier did not deliver: " + ", ".join(f"{c} {rep['causes'][c]}" for c in CAUSES),
          f"{rep['carriers']['interweave']['late']} pair(s) were `late` and {rep['carriers']['interweave']['no_session']} belong to a run with no session: "
          "no miss of the carrier alone, and in no `missed` count of the interweave row; see the tool's CAUSE paragraph.", ""]
    if rep["drill"]:
        L += [f"## InterWeave-stop drill [{rep['drill'][0]}, {rep['drill'][1]})", "",
              f"{len(rep['in_drill'])} pair(s) inside it, counted in no carrier's row above:"]
        L += [f"- `{p['id']}` → {p['addressee']}: {p['outcome']}" for p in rep["in_drill"]] or ["- none"]
        L.append("")
    L += ["## Pairs", "", "| request | addressee | carriers | outcome | cause |", "|---|---|---|---|---|"]
    for p in rep["pairs"]:
        L.append(f"| `{p['id']}` | {p['addressee']} | {', '.join(p['carriers']) or '—'} | {p['outcome']} | {p.get('cause', '')} |")
    if rep["unrecorded"]:
        L += ["", f"{rep['unrecorded']} pair(s) have a reply but no `sent` line (a fabric-ctl from before it wrote them): "
                  "an account that never answered cannot be seen for those requests."]
    if rep["malformed_timeout"]:
        L += ["", f"{rep['malformed_timeout']} request(s) have a `timeout_s` that is present but not a positive finite number: "
                  "read as no timeout, so a late reply of theirs stays no-waiter."]
    if rep["skipped"]:
        L += ["", f"{rep['skipped']} line(s) could not be read and are counted nowhere."]
    return "\n".join(L) + "\n"


def parse_files(specs: Iterable[str]) -> tuple[dict[str, list[dict]], int]:
    files: dict[str, list[dict]] = {}
    skipped = 0
    for spec in specs:
        login, sep, path = spec.partition("=")
        if not sep or not login or not path:
            raise InputError(f"{spec!r}: expected LOGIN=FILE")
        if login in files:
            raise InputError(f"{login} is given twice")
        files[login], n = read_lines(path)
        skipped += n
    return files, skipped


def cmd(args: list[str]) -> int:
    """gzcoord-carrier control-parity --window START END --operator LOGIN --arrivals LOGIN=FILE... [--drill START END] [--json]"""
    import argparse
    import sys
    p = argparse.ArgumentParser(prog="gzcoord-carrier control-parity", add_help=False, allow_abbrev=False)
    p.add_argument("--window", nargs=2, required=True)
    p.add_argument("--operator", required=True)
    p.add_argument("--arrivals", nargs="+", required=True)
    p.add_argument("--drill", nargs=2)
    p.add_argument("--json", action="store_true")
    try:
        a = p.parse_args(args)
    except SystemExit:
        return 1
    try:
        window = (parse_t(a.window[0]), parse_t(a.window[1]))
        drill = (parse_t(a.drill[0]), parse_t(a.drill[1])) if a.drill else None
        if window[0] >= window[1] or (drill and drill[0] >= drill[1]):
            raise ValueError("a window ends after it starts")
        files, skipped = parse_files(a.arrivals)
        rep = compute(files, a.operator, window, drill, skipped)
    except (ValueError, InputError) as e:
        print(f"gzcoord-carrier control-parity: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(rep, indent=1, sort_keys=True) + "\n" if a.json else render_markdown(rep))
    return 0
