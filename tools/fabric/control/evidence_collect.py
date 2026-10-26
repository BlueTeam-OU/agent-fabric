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
  write_dir  <out>/<login>/arrivals.jsonl, deliveries.jsonl, kinds.json and meta.json
             ({login, since, until, lookback_s, complete, journal, pages, counts}), the
             directories 0700 and the files 0600 (other accounts' traffic is not for
             everyone), each replaced atomically; a login's directory is written whole or
             not touched.
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
    return {"arrivals": [], "deliveries": [], "kinds": {}, "journal": "ok", "pages": {"arrivals": 0, "deliveries": 0},
            "skipped": 0, "undated": 0, "complete": True, "reason": None}


def collect(logins: list[str], since: str, until: str, send: Send, max_pages: int = MAX_PAGES) -> dict[str, dict]:
    got = {login: _fresh() for login in logins}
    for section in ev.SECTIONS:
        start, _ = ev.window_for(section, since, until)
        at: dict[str, str] = {login: start for login in logins if got[login]["complete"]}
        for _ in range(max_pages):
            if not at:
                break
            groups: dict[str, list[str]] = {}
            for login, c in at.items():
                groups.setdefault(c, []).append(login)
            at = _round(got, groups, section, until, send)
        for login in at:
            _stop(got[login], f"{section}: more than {max_pages} pages")
    return got


def _round(got: dict, groups: dict, section: str, until: str, send: Send) -> dict:
    nxt: dict[str, str] = {}
    for c, group in groups.items():
        replies = send(sorted(group), section, c, until)
        for login in group:
            r = replies.get(login)
            acct = got[login]
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
            else:
                acct["undated"] += int(r.get("undated") or 0)
            n = r.get("next")
            if n is None:
                continue
            if not (isinstance(n, str) and ev.ISO_RE.fullmatch(n) and c < n < until):
                _stop(acct, f"{section}: the cursor {n!r} does not advance")
                continue
            nxt[login] = n
    return nxt


def _stop(acct: dict, reason: str) -> None:
    acct["complete"], acct["reason"] = False, acct["reason"] or reason


def counts(acct: dict) -> dict:
    return {"arrivals": len(acct["arrivals"]), "deliveries": len(acct["deliveries"]), "kinds": len(acct["kinds"])}


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
    meta = {"login": login, "since": since, "until": until, "lookback_s": ev.LOOKBACK_S, "complete": acct["complete"],
            "reason": acct["reason"], "journal": acct["journal"], "pages": acct["pages"], "counts": counts(acct),
            "skipped": acct["skipped"], "undated": acct["undated"]}
    # meta.json last: a reader that finds it finds the files it describes (a crash between leaves no meta, and parity refuses that).
    for name in ("meta.json",):
        try:
            os.unlink(os.path.join(d, name))
        except FileNotFoundError:
            pass
    _atomic(os.path.join(d, "arrivals.jsonl"), _lines(acct["arrivals"]))
    _atomic(os.path.join(d, "deliveries.jsonl"), _lines(acct["deliveries"]))
    _atomic(os.path.join(d, "kinds.json"), (json.dumps(acct["kinds"], sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    _atomic(os.path.join(d, "meta.json"), (json.dumps(meta, sort_keys=True, indent=1) + "\n").encode("utf-8"))
    return d


def row_of(login: str, host: Any, acct: dict, since: str, until: str, *, full: bool) -> dict:
    """The row `--json` prints: the whole collection when it is not filed, its counts when it is."""
    body = {"since": since, "until": until, "lookback_s": ev.LOOKBACK_S, "complete": acct["complete"], "reason": acct["reason"],
            "journal": acct["journal"], "pages": acct["pages"], "counts": counts(acct), "skipped": acct["skipped"], "undated": acct["undated"]}
    if full:
        body.update(arrivals=acct["arrivals"], deliveries=acct["deliveries"], kinds=acct["kinds"])
    return {"account": login, "host": host, "status": "ok" if sum(acct["pages"].values()) else "no answer",
            f"{ev.CARRIER_NAME}Evidence": body}
