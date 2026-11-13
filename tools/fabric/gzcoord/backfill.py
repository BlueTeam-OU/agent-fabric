"""tools/fabric/gzcoord/backfill.py — put on the relay's record what the second carrier alone delivered.

A message sent while the relay was down reached its addressee through the second carrier, and gzcoord-send exited 3.
Nothing put it on the relay later, so the readers of the relay's record (`fabric-pr arm`'s AUTHORIZES, `gzcoord-inbox
--replay`, fabric-history) never saw it (relay-outage drill, 2026-11-12). This module is the return path: once the relay
answers, each account posts its own such messages, as journaled, under their own MESSAGE-ID.

THE CONTRACT
  who      the account's agentd runs `tick()` on a timer, so an account whose session ended during the outage still
           backfills. A session is not needed and not consulted.
  source   the sender's journal (episodic.db, opened read-only): outbound rows in state `accepted` whose carrier is the
           second carrier. The row's text is posted as stored; a message is never recomposed. A row the relay took first
           carries the relay's name (send.py: the first carrier sets the provenance) and is not a candidate.
  never a second copy
           before a post the relay is asked for the MESSAGE-ID (its newest page, which the relay caps at 500 records), and
           the sender's own sent ledger is trusted as "the relay took it". A row is DONE only when the relay answered 2xx
           to the post, or already held the id. A page that does not reach back to the row's time cannot say "absent":
           the row, and every later one, waits (unknown is not absent).
  order    oldest first within a channel; the first row that cannot be posted ends the pass, so a later message never
           overtakes an earlier one.
  bound    MAX_AGE_S. A row older is reported once and not posted: the addressee has had it for that long, and a relay
           record that appears after the thread moved on would read as news.
  repeat   a relay that is down, or refuses, leaves every row pending; the next tick tries again. A crash between the post
           and the log line is healed by the next tick finding the id on the relay.
  record   gzcoord-backfill.jsonl beside the journal: one line per finished row, {mid, outcome, at, delay_s, channel}.
           outcome is posted, present or over-age. `delay_s` is the time from the send to the line, for the parity report.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from . import gzmsg, paths
from .inbox_parts import relay as _relay
from .inbox_parts.config import integration_config
from .inbox_parts.tokens import synced_token
from .carrier import CARRIER_NAME
from .transport import RelayTransport

LOG_NAME = "gzcoord-backfill.jsonl"
SENT_LEDGER_NAME = "gzcoord-sent.jsonl"
# Twelve hours: an outage the owner's drill sized at half an hour, ten times over, and well inside the 500-record page the
# relay lists (about 34 hours of this fleet's traffic on 2026-11-12).
MAX_AGE_S = 12 * 3600
# The relay's cap on a listing, measured 2026-11-12 on the fleet's relay: limit=500, 2000 and 10000 each answered 500 records
# (docs/live-checks/2026-10-01-episodic-journal.md paged by 500 too). A smaller real cap would read a page as the whole channel.
PAGE = 500


def _parse_time(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(datetime.timezone.utc)


@dataclass(frozen=True)
class Row:
    mid: str
    text: str
    happened_at: datetime.datetime
    project: str | None


@dataclass
class Report:
    posted: list[str] = field(default_factory=list)
    present: list[str] = field(default_factory=list)
    over_age: list[str] = field(default_factory=list)
    waiting: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"gzcoord backfill: {m}" for m in self.notes]
        if self.posted:
            out.append(f"gzcoord backfill: posted {len(self.posted)} message(s) the relay lacked: {', '.join(self.posted)}")
        if self.present:
            out.append(f"gzcoord backfill: {len(self.present)} message(s) already on the relay: {', '.join(self.present)}")
        if self.over_age:
            out.append(f"gzcoord backfill: older than {MAX_AGE_S // 3600} h, reported and not posted: {', '.join(self.over_age)}")
        return out


def candidates(conn: Any) -> list[Row]:
    rows = conn.execute("SELECT message_id, content, happened_at, project FROM episodes "
                        "WHERE source='gzcoord' AND direction='outbound' AND state='accepted' AND carrier=? "
                        "ORDER BY happened_at, rowid", (CARRIER_NAME,)).fetchall()
    return [Row(m, c, _parse_time(h), p) for m, c, h, p in rows]


def finished(log: str) -> set[str]:
    """The ids the log holds a line for. A line that does not parse is passed over: its row is simply tried again, which
    the relay's own answer makes harmless."""
    done: set[str] = set()
    try:
        with open(log, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and isinstance(r.get("mid"), str):
                    done.add(r["mid"])
    except FileNotFoundError:
        pass
    return done


def _append(log: str, entry: dict) -> None:
    # runtime/identity.py owns the write (ADR-003 rule 1): one whole line under the log's flock.
    paths.identity().append_line(log, json.dumps(entry, sort_keys=True))


def on_sent_ledger(path: str) -> set[str]:
    """Ids gzcoord-send wrote only after the relay answered 2xx (send.py record_sent)."""
    ids: set[str] = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and isinstance(r.get("id"), str):
                    ids.add(r["id"])
    except FileNotFoundError:
        pass
    return ids


class Relay:
    """The relay as the backfill needs it: whether it answers, what its newest page holds, a post. A seam for tests."""

    def __init__(self, cfg: dict, address: str, token: str) -> None:
        self.tp = RelayTransport(cfg["relay_url"], cfg["channel"], address, token)
        self.address = address

    def up(self) -> bool:
        return self.tp.health().ok

    def _refreshing(self, call: Callable[[], Any]) -> Any:
        try:
            return call()
        except _relay.RelayError as e:
            if not self.tp.refresh(e):
                raise
            return call()

    def newest(self) -> list[dict]:
        page = self._refreshing(lambda: self.tp.newest(PAGE))
        msgs = page.get("messages") if isinstance(page, dict) else page
        # An answer that is no list of records is an unreadable relay, not an empty channel: read as empty it would make
        # every id absent and post a second copy of whatever the relay holds (as drift.py reads the same endpoint).
        if not isinstance(msgs, list) or not all(isinstance(m, dict) for m in msgs):
            raise ValueError("the relay's answer carries no list of messages")
        return msgs

    def post(self, mid: str, text: str) -> None:
        self.tp.send(mid, text)


def _held(records: list[dict], sender: str) -> tuple[set[str], datetime.datetime | None]:
    """The MESSAGE-IDs the page holds from `sender`, and the time its oldest record reaches back to — None when the page is
    the whole channel (fewer records than the relay's cap), so that nothing older can exist."""
    ids: set[str] = set()
    oldest = None
    for r in records:
        # /api/messages and /api/wait name their time differently (drift.py); the first one that parses is the record's.
        for key in ("ts_full", "timestamp", "ts"):
            try:
                t = _parse_time(r[key])
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            oldest = t if oldest is None or t < oldest else oldest
            break
        try:
            meta = gzmsg.parse(r["content"])["metadata"]
        except (gzmsg.NotGzcoord, AttributeError, TypeError, KeyError):
            continue
        if meta.get("FROM") == sender and meta.get("MESSAGE-ID"):
            ids.add(meta["MESSAGE-ID"])
    if len(records) < PAGE:
        return ids, None
    # A full page with no readable time reaches back nowhere we can tell: every row is older than it.
    return ids, (oldest if oldest is not None else datetime.datetime.max.replace(tzinfo=datetime.timezone.utc))


def _finish(log: str, row: Row, outcome: str, channel: str | None, at: datetime.datetime) -> None:
    _append(log, {"mid": row.mid, "outcome": outcome, "at": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "delay_s": int((at - row.happened_at).total_seconds()), "channel": channel})


def backfill_channel(rows: list[Row], relay: Relay, *, log: str, on_relay: set[str], channel: str,
                     now: Callable[[], datetime.datetime], report: Report) -> None:
    """`rows` are one channel's, oldest first, none over the age bound."""
    def done(row: Row, outcome: str) -> None:
        _finish(log, row, outcome, channel, now())

    live = []
    for row in rows:
        if row.mid in on_relay:
            done(row, "present")
            report.present.append(row.mid)
        else:
            live.append(row)
    if not live:
        return
    if not relay.up():
        report.waiting += [r.mid for r in live]
        return
    try:
        held, reaches = _held(relay.newest(), relay.address)
    except Exception as e:  # noqa: BLE001 — a relay that cannot list leaves the rows pending
        report.notes.append(f"the relay could not be asked ({e.__class__.__name__}: {e}); {len(live)} row(s) stay pending")
        report.waiting += [r.mid for r in live]
        return
    for i, row in enumerate(live):
        if row.mid in held:
            done(row, "present")
            report.present.append(row.mid)
            continue
        if reaches is not None and row.happened_at < reaches:
            report.notes.append(f"{row.mid} is older than the relay's newest page: not known to be absent, not posted")
            report.waiting += [r.mid for r in live[i:]]
            return
        try:
            relay.post(row.mid, row.text)
        except Exception as e:  # noqa: BLE001 — refused or unreachable: this and every later row wait, in order
            report.notes.append(f"the relay did not take {row.mid} ({e.__class__.__name__}: {e}); it stays pending")
            report.waiting += [r.mid for r in live[i:]]
            return
        done(row, "posted")
        report.posted.append(row.mid)


def run(*, state_dir: str, address: str, conn: Any,
        make_relay: Callable[[dict, str], Relay | None],
        config: Callable[[str | None], dict] = integration_config,
        now: Callable[[], datetime.datetime] = lambda: datetime.datetime.now(datetime.timezone.utc)) -> Report:
    report = Report()
    log = os.path.join(state_dir, LOG_NAME)
    skip = finished(log)
    rows = [r for r in candidates(conn) if r.mid not in skip]
    if not rows:
        return report
    on_relay = on_sent_ledger(os.path.join(state_dir, SENT_LEDGER_NAME))
    # The age bound is first and needs no relay: a row that can never be posted is reported whatever else is missing.
    t_now = now()
    live = []
    for r in rows:
        if (t_now - r.happened_at).total_seconds() > MAX_AGE_S:
            # The ledger needs no relay either: a row the sender's own resend put on the relay is present, however old,
            # not "never posted" (the first deployment meets every row a hand resend already took).
            if r.mid in on_relay:
                _finish(log, r, "present", None, t_now)
                report.present.append(r.mid)
            else:
                _finish(log, r, "over-age", None, t_now)
                report.over_age.append(r.mid)
        else:
            live.append(r)
    # One order per relay channel, whatever project a row came from.
    by_channel: dict[tuple[str, str], tuple[dict, list[Row]]] = {}
    for r in live:
        cfg = config(r.project)
        if not cfg.get("configured"):
            report.notes.append(f"project {r.project}: no relay configured; its rows stay pending")
            report.waiting.append(r.mid)
            continue
        by_channel.setdefault((cfg["relay_url"], cfg["channel"]), (cfg, []))[1].append(r)
    for cfg, group in by_channel.values():
        relay = make_relay(cfg, address)
        if relay is None:
            report.notes.append("no relay token; its rows stay pending")
            report.waiting += [r.mid for r in group]
            continue
        backfill_channel(group, relay, log=log, on_relay=on_relay, channel=cfg["channel"], now=now, report=report)
    return report


_said: set[str] = set()   # the standing notes of the last tick: a condition that lasts is said when it begins, not every minute


def tick(say: Callable[[str], None] = lambda m: print(m, file=sys.stderr),
         token: Callable[[], str | None] = synced_token) -> Report | None:
    """The daemon's timer body. A journal that does not exist yet, or that cannot be read, is a line and nothing else.
    `token` is the daemon's own, so the backfill reaches the relay with the credential the daemon does."""
    import episodic
    try:
        conn = episodic.open_readonly()
    except episodic.JournalError as e:
        if "no journal yet" not in str(e):
            _say_new({f"gzcoord backfill: {e}"}, say)
        return None
    try:
        def make(cfg: dict, address: str) -> Relay | None:
            tok = token()
            return Relay(cfg, address, tok) if tok else None
        report = run(state_dir=episodic.state_dir(), address=episodic.own_address(), conn=conn, make_relay=make)
    finally:
        conn.close()
    _say_new(set(report.notes), say)
    for line in report.lines():
        if line.removeprefix("gzcoord backfill: ") not in report.notes:
            say(f"agentd: {line}")
    return report


def _say_new(notes: set[str], say: Callable[[str], None]) -> None:
    global _said
    for n in sorted(notes - _said):
        say(f"agentd: {n if n.startswith('gzcoord backfill') else 'gzcoord backfill: ' + n}")
    _said = notes
