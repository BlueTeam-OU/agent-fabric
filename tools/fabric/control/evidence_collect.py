"""tools/fabric/control/evidence_collect.py — what `fabric-ctl <login|all> <carrier>-evidence
--since T --until T` does with the pages the accounts answer (control/carrier_evidence.py): asks
for the rest of a window until no account says `next`, and files the result in the form
`gzcoord-carrier parity --collected` reads.

CONTRACT
  collect()  per account, per section, pages until the reply has no `next`. An account
             that stops answering, answers a refusal, or does not advance its cursor ends
             there with a reason, and the account is `incomplete`: parity refuses an
             incomplete account, because a report computed from half a log would read as
             carrier misses. At most MAX_PAGES pages of one section of one account.
             The relay-outage drill's two sections (shown, acks) are paged the same way but
             a failure of theirs ends only them: the account stays `complete` for the report
             it already had and its meta says `relay_outage` {complete, reason}, which only
             `parity --relay-drill` reads (an account whose daemon predates the sections
             must not turn every rollback report into a refusal). Unknown stays unknown:
             that account has no drill evidence, never an empty one.
             The backfill log's section (backfills) is paged the same way and fails on its own: its
             meta says `backfill_log` {complete, reason, skipped} and neither the report nor the
             drill's other sections are touched (an account whose daemon predates it must still
             yield the 11-12 drill's collection). No rows are claimed for it: the file is not written.
  write_dir  <out>/<login>/arrivals.jsonl, deliveries.jsonl, shown.jsonl, acks.jsonl, backfills.jsonl
             (only when the section was collected whole), kinds.json and
             meta.json ({login, since, until, margin_s, complete, journal, pages, counts,
             relay_outage, backfill_log}), the
             directories 0700 and the files 0600 (other accounts' traffic is not for
             everyone), each replaced atomically; a login's directory is written whole or
             not touched. Every account asked has one, an account that never answered with
             `complete: false`; <out>/collection.json names them, written last.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Callable

from control import carrier_evidence as ev

MAX_PAGES = 2000

# send(logins, section, since, until) -> {login: the section's dict of the reply, or {"status": "no answer"}}; `since` is where this page starts
Send = Callable[[list[str], str, str, str], dict]


def _fresh() -> dict:
    return {"arrivals": [], "deliveries": [], "shown": [], "acks": [], "backfills": [], "kinds": {}, "journal": "ok",
            "pages": {s: 0 for s in ev.ALL_SECTIONS}, "skipped": 0, "undated": 0, "complete": True, "reason": None,
            "answered": False, "relay_outage": {"complete": True, "reason": None, "skipped": 0},
            "drill_skipped": {s: 0 for s in ev.DRILL_SECTIONS},
            "backfill_log": {"complete": True, "reason": None, "skipped": 0}}


def collect(logins: list[str], since: str, until: str, send: Send, max_pages: int = MAX_PAGES) -> dict[str, dict]:
    got = {login: _fresh() for login in logins}
    for section in ev.ALL_SECTIONS:
        start, end = ev.window_for(section, since, until)
        own = got_meta(section)
        at: dict[str, str] = {login: start for login in logins if got[login]["complete"] and own(got[login])["complete"]}
        for _ in range(max_pages):
            if not at:
                break
            groups: dict[str, list[str]] = {}
            for login, c in at.items():
                groups.setdefault(c, []).append(login)
            at = _round(got, groups, section, end, send)
        for login in at:
            _stop(got[login], f"{section}: more than {max_pages} pages")
    return got


def got_meta(section: str) -> Callable[[dict], dict]:
    """Where a section's failure is kept: the drill's two share one record, the backfill log has its own, the
    report's two (which the account's `complete` is) have none."""
    if section in ev.DRILL_SECTIONS:
        return lambda acct: acct["relay_outage"]
    if section == ev.BACKFILL_SECTION:
        return lambda acct: acct["backfill_log"]
    return lambda acct: {"complete": True}


def _round(got: dict, groups: dict, section: str, until: str, send: Send) -> dict:
    nxt: dict[str, str] = {}
    for c, group in groups.items():
        replies = send(sorted(group), section, c, until)
        for login in group:
            r = replies.get(login)
            acct = got[login]
            acct["answered"] = acct["answered"] or (isinstance(r, dict) and r.get("status") in ("ok", "refused"))
            if not isinstance(r, dict) or r.get("status") != "ok":
                why = r.get("reason") or r.get("status") if isinstance(r, dict) else None
                _stop(acct, f"{section}: {why or 'no answer'}")
                continue
            acct["pages"][section] += 1
            acct[section] += r.get("rows") or []
            if section == "arrivals":
                acct["kinds"].update(r.get("kinds") or {})
                acct["skipped"] += int(r.get("skipped") or 0)
                if r.get("journal") != "ok":
                    acct["journal"] = r.get("journal") or "unreadable"
            elif section == "deliveries":
                acct["undated"] += int(r.get("undated") or 0)
            elif section == ev.BACKFILL_SECTION:
                acct["backfill_log"]["skipped"] = int(r.get("skipped") or 0)      # every page repeats the one file's count
            else:
                # Unreadable lines of the drill's files: carried to meta, where parity refuses a drill it cannot judge.
                # Every page of a section reports its whole file's count: the largest is that file's count, their sum is
                # not; the two files' counts are added, since they are two files.
                acct["drill_skipped"][section] = max(acct["drill_skipped"][section], int(r.get("skipped") or 0))
                acct["relay_outage"]["skipped"] = sum(acct["drill_skipped"].values())
            n = r.get("next")
            if n is None:
                continue
            if not (isinstance(n, str) and ev.ISO_RE.fullmatch(n) and c < n < until):
                _stop(acct, f"{section}: the cursor {n!r} does not advance")
                continue
            nxt[login] = n
    return nxt


def _stop(acct: dict, reason: str) -> None:
    section = reason.split(":", 1)[0]
    if section == ev.BACKFILL_SECTION:
        acct["backfill_log"]["complete"], acct["backfill_log"]["reason"] = False, acct["backfill_log"]["reason"] or reason
        return
    if section in ev.DRILL_SECTIONS:
        acct["relay_outage"]["complete"], acct["relay_outage"]["reason"] = False, acct["relay_outage"]["reason"] or reason
        return
    acct["complete"], acct["reason"] = False, acct["reason"] or reason


def counts(acct: dict) -> dict:
    return {"arrivals": len(acct["arrivals"]), "deliveries": len(acct["deliveries"]), "kinds": len(acct["kinds"]),
            "shown": len(acct["shown"]), "acks": len(acct["acks"]), "backfills": len(acct["backfills"])}


def _atomic(path: str, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".evidence.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _lines(rows: list[dict]) -> bytes:
    return "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows).encode("utf-8")


def write_dir(out: str, login: str, acct: dict, since: str, until: str) -> str:
    """The account's directory under `out`; returns its path."""
    os.makedirs(out, mode=0o700, exist_ok=True)
    d = os.path.join(out, login)
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    meta = {"login": login, "since": since, "until": until, "margin_s": ev.LOOKBACK_S, "complete": acct["complete"],
            "reason": acct["reason"], "journal": acct["journal"], "pages": acct["pages"], "counts": counts(acct),
            "skipped": acct["skipped"], "undated": acct["undated"], "relay_outage": acct["relay_outage"],
            "backfill_log": acct["backfill_log"]}
    # meta.json last: a reader that finds it finds the files it describes (a crash between leaves no meta, and parity refuses that).
    for name in ("meta.json",):
        try:
            os.unlink(os.path.join(d, name))
        except FileNotFoundError:
            pass
    _atomic(os.path.join(d, "arrivals.jsonl"), _lines(acct["arrivals"]))
    _atomic(os.path.join(d, "deliveries.jsonl"), _lines(acct["deliveries"]))
    _atomic(os.path.join(d, "shown.jsonl"), _lines(acct["shown"]))
    _atomic(os.path.join(d, "acks.jsonl"), _lines(acct["acks"]))
    if acct["backfill_log"]["complete"]:
        _atomic(os.path.join(d, "backfills.jsonl"), _lines(acct["backfills"]))
    else:
        # An earlier run's file must not outlive a run that could not collect it: an absent file reads "not collected".
        try:
            os.unlink(os.path.join(d, "backfills.jsonl"))
        except FileNotFoundError:
            pass
    _atomic(os.path.join(d, "kinds.json"), (json.dumps(acct["kinds"], sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    _atomic(os.path.join(d, "meta.json"), (json.dumps(meta, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    return d


def write_manifest(out: str, logins: list[str]) -> None:
    """Last: the accounts the run asked, which parity checks the directories against (a silent account's
    directory says so in its meta; a directory left by an earlier run is not in the list)."""
    _atomic(os.path.join(out, "collection.json"), (json.dumps({"logins": sorted(logins)}, indent=1) + "\n").encode("utf-8"))


def clear_manifest(out: str) -> None:
    try:
        os.unlink(os.path.join(out, "collection.json"))
    except FileNotFoundError:
        pass


def row_of(login: str, host: Any, acct: dict, since: str, until: str, *, full: bool) -> dict:
    """The row `--json` prints: the whole collection when it is not filed, its counts when it is."""
    body = {"since": since, "until": until, "margin_s": ev.LOOKBACK_S, "complete": acct["complete"], "reason": acct["reason"],
            "journal": acct["journal"], "pages": acct["pages"], "counts": counts(acct), "skipped": acct["skipped"], "undated": acct["undated"],
            "relay_outage": acct["relay_outage"], "backfill_log": acct["backfill_log"]}
    if full:
        body.update(arrivals=acct["arrivals"], deliveries=acct["deliveries"], shown=acct["shown"], acks=acct["acks"], kinds=acct["kinds"])
        if acct["backfill_log"]["complete"]:      # absent, as in the filed form, when it was not collected
            body["backfills"] = acct["backfills"]
    return {"account": login, "host": host, "status": "ok" if acct["answered"] else "no answer",
            f"{ev.CARRIER_NAME}Evidence": body}
