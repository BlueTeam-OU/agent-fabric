"""tools/fabric/control/account_switch.py — the switch controller: which Claude account a gateway session's
login runs on, decided by the committed policy (agent-fabric ADR-052 §5; the policy is
routing/policies/account-switch.json, judged by control/switch_policy.py).

Run in the coordinator's account, which alone holds the account templates:

  fabric-accounts switch            what the controller would do now: gathers, decides, prints; logs nothing,
                                    moves nothing, whatever the mode (it may probe a stale account, rule 1)
  fabric-accounts switch --tick     one controller run: decides, logs, and in `act` moves (the agentd timer
                                    runs exactly this every interval_s)
  fabric-accounts switch --log [N]  the move log's last N lines (20)

THE SHAPE. `gather` asks the fleet (three control-channel reads: `identity` for each login's setup-token
fingerprint, `gateway` for each live gateway's relayed usage, its entries' joined fingerprints and its sessions'
kinds, `states` for each session's working/blocked/idle) and probes a stale pool account by ADR-031 rule 9
(`fabric-ctl <a login on it> usage`). `decide` is pure: readings, logins, the policy, the clock and the move
history in, decisions out — the table the tests drive. `would` and `act` take decisions to the log; only `act`
can move, and it is the only function that is handed the assign path: `run` builds that path only when the
policy's mode is `act`, so advise cannot reach it (tested).

THE RULES, as §5 numbers them. Readings are per Claude account (a template slug), from the gateway's entries
joined to the account by generation (rule 1); the freshest one counts, and one older than reading_max_age_s,
or whose window has reset since, is stale: its utilisation is unknown, and the account is probed at most once
per probe_min_interval_s. Unknown is never 0: a decision that needs an unknown field is not taken.
  2  exhausted: status rejected or rate_limited, a utilisation at 1 or above, or a 429 the gateway classified
     exhausted; each until its reset, and one with no reset only while its reading is fresh. A transient 429
     (the entry's transient_429 count) moves nothing.
  3  sticky: a session moves only by 4, 5 or 7.
  4  exhaustion: at once, any state, not rate-limited.
  5  eject: at eject.five_hour or eject.seven_day, at the next idle (rule 8).
  6  target: pool accounts other than the session's, under both land thresholds and not exhausted, soonest
     seven-day reset, tie to the lower seven-day use; else the non-exhausted one with the most headroom, logged
     `relaxed`, owner told; none: nothing moves, owner told. Never an account outside the pool, never a
     login's own sign-in: a target is a pool slug that is a template in the coordinator's store.
  7  perishable: onto a pool account whose seven-day window resets within perishable.within_hours at or below
     perishable.max_utilization and under both land thresholds; one per pool per perishable.min_interval_s; not
     a session moved in the last min_stay_s.
  8  boundary: rules 5 and 7 move a login only when every session in its state record is `idle`; the one idle
     longest first; unknown state moves nothing.
  13 scope: only a login whose gateway is live and whose every running session is on it. A plain-claude (or
     broker) session beside it, or sessions that cannot be told, and the login is not moved.

WHERE ADR-052 IS SILENT, chosen here (and said in the policy's `why` where it is a number):
  * A move is a login's: `fabric-accounts assign` moves a login, so every session of the login moves with it.
  * An eject move with a relaxed target is made only when the target has more headroom than the session's own
    account: a "move" to an account as full is no move (held, and the owner told). An exhaustion move takes any
    non-exhausted target: the session cannot run where it is.
  * A probe's reading is kept in the controller's state and counts until a fresher reading replaces it or it
    goes stale, since the account is probed only once per probe_min_interval_s.
  * A perishable move takes a session only from an account whose own seven-day window resets later than the
    target's: moving a session off quota that perishes sooner would spend the wrong quota.
  * In advise, rule 7's rate limit and min_stay_s count the `would` lines, so the log shows what act would do,
    the rate limit holding back a second candidate included; in act they count `did`.
  * A decision that holds (the same mode, login, rule, from and to as the last logged for it) is logged once,
    not every run; it is logged again once it stops holding and comes back. The mode is part of it, so a
    `would` of advise is made after the switch to act; a `failed` move is not recorded, so it is tried again;
    a `did` is, so a run whose identity read still shows the old account does not assign it a second time.
  * The owner is told by a `tell: true` line in the log, which fabric-status and `fabric-ctl ... switch` show.
  * act runs `fabric-accounts assign <login> <account> --no-restart`: a gateway session needs no restart (the
    sync replaces its token file), and --no-restart guarantees no plain-claude session is ever stopped by it.
  * Only one run at a time: an exclusive flock on <state>/account-switch.lock; a second run finds it held and
    does nothing.
"""
from __future__ import annotations

import datetime
import fcntl
import json
import math
import os
import re
import subprocess
import sys
import time
from typing import Any, Callable, Iterable, Sequence

if sys.path and os.path.realpath(sys.path[0] or ".") == os.path.dirname(os.path.realpath(__file__)):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
elif os.path.dirname(os.path.dirname(os.path.realpath(__file__))) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from control import switch_log, switch_policy  # noqa: E402

STATE = "account-switch-state.json"
LOCK = "account-switch.lock"
EXHAUSTED_STATUSES = ("rejected", "rate_limited")
FINGERPRINT = re.compile(r"setup-token ([0-9a-f]{12})")
# fabric-ctl waits up to its own --timeout per read; the probe is one account's usage op.
CTL_TIMEOUT_S = 120
ASSIGN_TIMEOUT_S = 2700
OUTPUT_LINES = 12
FIRST_TICK_S = 120


# ── readings ────────────────────────────────────────────────────────

# What another account relayed is data, not trusted: a value outside these is unknown (None), never a number
# the rules act on. A utilisation is a share, 1 all of it, above 1 surpassed (the gateway's contract): past
# UTIL_MAX it is no reading. A timestamp outside 2001..2100 is no time: it would overflow a date or make an
# account "reset soonest" for ever.
UTIL_MAX = 100.0
# A stamp this far ahead of the controller's clock is no time: clamped to age 0 it would read fresh for ever,
# never be probed, and outrank every real reading. The hosts keep NTP time; a minute covers their drift.
SKEW_S = 60.0
EPOCH_MIN_S, EPOCH_MAX_S = 1e9, 4.1e9


def _num(v: Any) -> float | None:
    """A finite JSON number, else None: inf, NaN, a bool or a string is unknown."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except OverflowError:
        return None   # an integer past a double
    return f if math.isfinite(f) else None


def share(v: Any) -> float | None:
    """A utilisation: finite, from 0 to UTIL_MAX; else unknown."""
    n = _num(v)
    return n if n is not None and 0 <= n <= UTIL_MAX else None


def epoch_s(v: Any) -> float | None:
    """A gateway timestamp (Unix seconds; milliseconds told by size) or an ISO time, as seconds, within
    EPOCH_MIN_S..EPOCH_MAX_S; anything else is None."""
    n = _num(v)
    if n is not None:
        n = n / 1000 if n > 1e11 else n
    elif isinstance(v, str) and v:
        try:
            t = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=datetime.timezone.utc)
            n = t.timestamp()
        except (ValueError, OverflowError):
            return None
    return n if n is not None and EPOCH_MIN_S <= n <= EPOCH_MAX_S else None


def iso(s: float) -> str:
    return datetime.datetime.fromtimestamp(s, datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def reading_from_gateway(entry: dict, login: str) -> dict:
    """One relayed entry (the gateway's plan-v0 "Usage (s11)" shape) as the controller's reading."""
    u = entry.get("usage") if isinstance(entry.get("usage"), dict) else {}

    def win(k: str) -> dict:
        w = u.get(k) if isinstance(u.get(k), dict) else {}
        return {"utilization": share(w.get("utilization")), "reset": epoch_s(w.get("reset"))}
    mark = entry.get("exhausted")
    mark = {"at": epoch_s(mark.get("at")), "reset": epoch_s(mark.get("reset"))} if isinstance(mark, dict) else None
    status = u.get("status") if isinstance(u.get("status"), str) else None
    return {"five_hour": win("five_hour"), "seven_day": win("seven_day"), "status": status,
            "status_reset": epoch_s(u.get("reset")), "exhausted": mark,
            "transient_429": entry.get("transient_429") if isinstance(entry.get("transient_429"), int) else None,
            "read_at": epoch_s(entry.get("read_at")) if u else None, "via": "gateway", "from": login}


def reading_from_probe(row: dict, login: str, now: float) -> dict | None:
    """A `fabric-ctl <login> usage --json` row (ADR-031 rule 9's one-token read): percentages to shares."""
    if row.get("status") != "ok" or row.get("usage_status") != "ok":
        return None

    def win(w: Any) -> dict:
        w = w if isinstance(w, dict) else {}
        pct = _num(w.get("utilization"))
        return {"utilization": None if pct is None else share(round(pct / 100, 4)), "reset": epoch_s(w.get("resets_at"))}
    five, seven = win(row.get("five_hour")), win(row.get("seven_day"))
    if five["utilization"] is None and seven["utilization"] is None:
        return None
    return {"five_hour": five, "seven_day": seven, "status": None, "status_reset": None, "exhausted": None,
            "transient_429": None, "read_at": now, "via": "probe", "from": login}


def ahead(stamp: float | None, now: float) -> bool:
    return stamp is not None and stamp > now + SKEW_S


def freshest(readings: Iterable[dict], now: float) -> dict | None:
    """Per account: the reading taken last, with the newest exhaustion mark of any of its entries that is no
    older than that reading. A reading or a mark stamped ahead of `now` is no reading (the account is then
    probed).

    Exhaustion is the account's, not the entry's: the gateway's contract (plan-v0 README, "Usage (s11)")
    marks a 429 exhausted "when its neutral reading says the account's limit is spent", and keeps the mark
    per entry only because it knows no accounts, clearing it on that entry's own next 2xx. So a mark counts
    for the whole account until a later reading of the same account, from any entry, answers otherwise: a
    reading taken after the mark is the account being served, and outranks it. The best reading's own mark
    always stands (its entry has not been cleared); a later reading that is itself spent is exhaustion by
    its own status or utilisation (rule 2)."""
    rs = [r for r in readings if r and not ahead(r.get("read_at"), now)]
    rs = [{**r, "exhausted": None} if r.get("exhausted") and ahead(r["exhausted"].get("at"), now) else r for r in rs]
    if not rs:
        return None
    best = max(rs, key=lambda r: r["read_at"] if r["read_at"] is not None else float("-inf"))
    if best.get("exhausted"):
        return best
    after = best["read_at"] if best["read_at"] is not None else float("-inf")
    marks = [r["exhausted"] for r in rs if r.get("exhausted") and r["exhausted"].get("at") is not None
             and r["exhausted"]["at"] >= after]
    return {**best, "exhausted": max(marks, key=lambda m: m["at"])} if marks else best


class View:
    """What one account's reading lets the rules know now; None wherever it is unknown."""

    def __init__(self, slug: str, reading: dict | None, now: float, max_age: float):
        if reading and (ahead(reading.get("read_at"), now)
                        or (reading.get("exhausted") and ahead(reading["exhausted"].get("at"), now))):
            reading = None   # stamped in the future: unknown, never fresh for ever
        self.slug, self.reading, self.now, self.max_age = slug, reading, now, max_age
        r = reading or {}
        read_at = r.get("read_at")
        self.age = None if read_at is None else max(0.0, now - read_at)
        self.fresh = self.age is not None and self.age <= max_age

        def util(k: str) -> float | None:
            w = r.get(k) or {}
            reset = w.get("reset")
            if not self.fresh or (reset is not None and reset <= now):
                return None   # stale, or the window it measured has ended: unknown, never 0
            return w.get("utilization")

        def reset_of(k: str) -> float | None:
            reset = (r.get(k) or {}).get("reset")
            return reset if reset is not None and reset > now else None
        self.u5, self.u7 = util("five_hour"), util("seven_day")
        self.r7 = reset_of("seven_day")
        self.exhausted, self.exhausted_why = self._exhausted(r)

    @property
    def stale(self) -> bool:
        r = self.reading or {}
        rolled = any((r.get(k) or {}).get("reset") is not None and r[k]["reset"] <= self.now for k in ("five_hour", "seven_day"))
        return not self.fresh or rolled

    def _exhausted(self, r: dict) -> tuple[bool, str | None]:
        """Rule 2. Each signal holds until its reset; one with no reset only while the reading is fresh."""
        def holds(reset: float | None, fresh: bool) -> bool:
            return reset > self.now if reset is not None else fresh
        if r.get("status") in EXHAUSTED_STATUSES and holds(r.get("status_reset"), self.fresh):
            return True, f"status {r['status']}"
        for k, name in (("five_hour", "5h"), ("seven_day", "7d")):
            w = r.get(k) or {}
            if w.get("utilization") is not None and w["utilization"] >= 1 and holds(w.get("reset"), self.fresh):
                return True, f"{name} utilisation {w['utilization']:g}"
        mark = r.get("exhausted")
        if mark:
            # The gateway clears a mark on the next 2xx, not at its reset: one with no reset is believed as
            # long as a reading would be.
            mark_fresh = mark.get("at") is not None and self.now - mark["at"] <= self.max_age
            if holds(mark.get("reset"), mark_fresh):
                return True, "a 429 classified exhausted"
        return False, None

    def under_land(self, land: dict) -> bool | None:
        if self.u5 is None or self.u7 is None:
            return None
        return self.u5 < land["five_hour"] and self.u7 < land["seven_day"]

    def headroom(self) -> float | None:
        if self.u5 is None or self.u7 is None:
            return None
        return min(1 - self.u5, 1 - self.u7)

    def logged(self) -> dict:
        """The reading as the log keeps it (rule 11): parsed fields and ages, nothing else."""
        r = self.reading
        if not r:
            return {"known": False}

        def win(k: str) -> dict:
            w = r.get(k) or {}
            return {"utilization": w.get("utilization"), "reset": iso(w["reset"]) if w.get("reset") is not None else None}
        return {"five_hour": win("five_hour"), "seven_day": win("seven_day"), "status": r.get("status"),
                "exhausted": self.exhausted, "read_at": iso(r["read_at"]) if r.get("read_at") is not None else None,
                "age_s": None if self.age is None else int(self.age), "via": r.get("via")}


# ── the decision (pure) ─────────────────────────────────────────────

def choose_target(views: dict[str, View], pool: Sequence[str], exclude: str, land: dict) -> tuple[str | None, str]:
    """Rule 6: (account, "soonest-reset" | "relaxed"), or (None, "all-exhausted" | "no-target-known")."""
    others = [a for a in pool if a != exclude]
    qualified = [a for a in others if views[a].exhausted is False and views[a].under_land(land) and views[a].r7 is not None]
    if qualified:
        return min(qualified, key=lambda a: (views[a].r7, views[a].u7, others.index(a))), "soonest-reset"
    roomy = [a for a in others if views[a].exhausted is False and views[a].headroom() is not None]
    if roomy:
        return max(roomy, key=lambda a: (views[a].headroom(), -others.index(a))), "relaxed"
    if others and all(views[a].exhausted for a in others):
        return None, "all-exhausted"
    return None, "no-target-known"


def _idle_since(login: dict) -> float | None:
    """When the login's last session went idle, if every session is idle (rule 8); else None."""
    ss = login.get("sessions")
    if not login.get("state_known") or not ss or any(s.get("state") != "idle" for s in ss):
        return None
    times = [epoch_s(s.get("since")) for s in ss]
    return None if any(t is None for t in times) else max(times)


def _last_move(history: list[dict], *, login: str | None = None, reason: str | None = None, pool: str | None = None) -> float | None:
    ts = [epoch_s(h.get("at")) for h in history
          if (login is None or h.get("login") == login) and (reason is None or h.get("reason") == reason)
          and (pool is None or h.get("pool") == pool)]
    ts = [t for t in ts if t is not None]
    return max(ts) if ts else None


def decide(policy: dict, views: dict[str, View], logins: list[dict], history: list[dict], now: float) -> list[dict]:
    """Every login's decision, in the order logins are given: dicts with login, outcome ("move", "defer",
    "hold", "skip"), and for a move or hold the rule, reason, from, to, relaxed, tell and why. `history` is the
    log's lines this mode counts (`would` in advise, `did` in act)."""
    pool, land, eject = policy["pool"]["accounts"], policy["land"], policy["eject"]
    out: list[dict] = []
    eligible: list[dict] = []

    def skip(lg: dict, why: str) -> None:
        out.append({"login": lg["login"], "outcome": "skip", "from": lg.get("account"), "why": why})

    for lg in logins:
        kinds = lg.get("kinds") or {}
        if not lg.get("gateway"):
            skip(lg, "not a gateway session: moved only by hand (rule 13)")
            continue
        if kinds.get("status") != "ok":
            skip(lg, "its sessions cannot be told apart: not moved (rule 13)")
            continue
        if kinds.get("other"):
            skip(lg, "a plain-claude or broker session runs beside its gateway: not moved (rule 13)")
            continue
        if lg.get("account") not in pool:
            skip(lg, "its account is not a pool template" if lg.get("account") else "its account is unknown")
            continue
        if not lg.get("sessions"):
            skip(lg, "no session in its state record")
            continue
        eligible.append(lg)

    moved: set[str] = set()
    for lg in eligible:
        a = lg["account"]
        v = views[a]
        base = {"login": lg["login"], "sessions": [s["session"] for s in lg["sessions"]], "from": a}
        if v.exhausted:
            target, how = choose_target(views, pool, a, land)
            if target is None:
                out.append({**base, "outcome": "hold", "rule": 4, "reason": "exhausted", "to": None, "relaxed": False,
                            "tell": True, "why": f"{a} is exhausted ({v.exhausted_why}) and "
                            + ("every other pool account is too" if how == "all-exhausted" else "no other pool account is known to have room")
                            + ": the session waits; never its own sign-in (rule 6)"})
                continue
            out.append({**base, "outcome": "move", "rule": 4, "reason": "exhausted", "to": target, "relaxed": how == "relaxed",
                        "tell": how == "relaxed", "why": f"{a} is exhausted ({v.exhausted_why}): moved at once (rule 4)"})
            moved.add(lg["login"])
            continue
        reason = ("eject-5h" if v.u5 is not None and v.u5 >= eject["five_hour"]
                  else "eject-7d" if v.u7 is not None and v.u7 >= eject["seven_day"] else None)
        if reason:
            if _idle_since(lg) is None:
                out.append({**base, "outcome": "defer", "rule": 5, "reason": reason, "to": None,
                            "why": f"{a} crossed its {reason[6:]} eject threshold; the login is not idle: it moves at its next idle (rule 8)"})
                continue
            target, how = choose_target(views, pool, a, land)
            if target is None or (how == "relaxed" and not _roomier(views[target], v)):
                out.append({**base, "outcome": "hold", "rule": 5, "reason": reason, "to": None, "relaxed": how == "relaxed",
                            "tell": True, "why": f"{a} crossed its {reason[6:]} eject threshold and no other pool account has more room"})
                continue
            out.append({**base, "outcome": "move", "rule": 5, "reason": reason, "to": target, "relaxed": how == "relaxed",
                        "tell": how == "relaxed", "why": f"{a} crossed its {reason[6:]} eject threshold: moved at idle (rule 5)"})
            moved.add(lg["login"])
    out += _perishable(policy, views, [lg for lg in eligible if lg["login"] not in moved
                                       and not any(d["login"] == lg["login"] and d["outcome"] in ("hold", "defer") for d in out)],
                       history, now)
    return out


def _roomier(target: View, own: View) -> bool:
    t, o = target.headroom(), own.headroom()
    return t is not None and (o is None or t > o)


def _perishable(policy: dict, views: dict[str, View], logins: list[dict], history: list[dict], now: float) -> list[dict]:
    """Rule 7, for one pool: at most one move."""
    p, land, name = policy["perishable"], policy["land"], policy["pool"]["name"]
    pool = policy["pool"]["accounts"]
    targets = [a for a in pool if views[a].exhausted is False and views[a].r7 is not None
               and views[a].r7 - now <= p["within_hours"] * 3600 and views[a].u7 is not None
               and views[a].u7 <= p["max_utilization"] and views[a].under_land(land)]
    if not targets:
        return []
    t = min(targets, key=lambda a: (views[a].r7, views[a].u7, pool.index(a)))
    out: list[dict] = []
    candidates = []
    for lg in logins:
        a = lg["account"]
        if a == t:
            continue
        base = {"login": lg["login"], "sessions": [s["session"] for s in lg["sessions"]], "from": a, "rule": 7,
                "reason": "perishable", "to": t}
        own = views[a]
        if own.r7 is None or own.r7 <= views[t].r7:
            continue   # its own quota perishes as soon, or is unknown: no reason to move it (not a candidate)
        last = _last_move(history, login=lg["login"])
        if last is not None and now - last < policy["min_stay_s"]:
            out.append({**base, "outcome": "skip", "why": f"moved {int(now - last)} s ago, within min_stay_s (rule 7)"})
            continue
        since = _idle_since(lg)
        if since is None:
            out.append({**base, "outcome": "defer", "why": f"{t} resets soon largely unused; the login is not idle (rule 8)"})
            continue
        candidates.append((since, lg, base))
    if not candidates:
        return out
    candidates.sort(key=lambda c: c[0])   # the one idle longest first (rule 8)
    last = _last_move(history, reason="perishable", pool=name)
    limited = last is not None and now - last < p["min_interval_s"]
    for i, (_since, lg, base) in enumerate(candidates):
        if i == 0 and not limited:
            out.append({**base, "outcome": "move", "relaxed": False, "tell": False,
                        "why": f"{t}'s seven-day window resets in {int((views[t].r7 - now) / 3600)} h at {views[t].u7:g} used: "
                               "one idle session moved onto it (rule 7)"})
        else:
            wait = int(p["min_interval_s"] - (now - last)) if limited else int(p["min_interval_s"])
            out.append({**base, "outcome": "hold", "relaxed": False, "tell": False,
                        "why": f"one perishable move per pool per {int(p['min_interval_s'])} s: held (next in {wait} s)"})
    return out


# ── the fleet's readings ────────────────────────────────────────────

def _login_of(address: Any) -> str | None:
    return address.rsplit("/", 1)[-1] if isinstance(address, str) and address else None


def gather(ctl: Callable[[list[str]], list[dict]], templates: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """(readings per template slug, logins) from the three fleet reads. `ctl(args)` returns fabric-ctl's --json rows."""
    by_fp = {t["token_sha256_12"]: t["account"] for t in templates if t.get("token_sha256_12")}
    identity = {r.get("account"): r for r in ctl(["all", "identity"])}
    gateways = {r.get("account"): r for r in ctl(["all", "gateway"])}
    states = {_login_of(r.get("address")): r for r in ctl(["all", "states"])}
    readings: dict[str, list[dict]] = {}
    logins = []
    for login, row in identity.items():
        if not isinstance(login, str):
            continue
        m = FINGERPRINT.fullmatch(str(row.get("email") or "")) if row.get("status") == "ok" else None
        account = by_fp.get(m.group(1)) if m else None
        g = (gateways.get(login) or {}).get("gateway")
        g = g if isinstance(g, dict) else {}
        usage = g.get("usage") if isinstance(g.get("usage"), dict) else {}
        live = usage.get("status") == "ok"
        if live:
            prints = g.get("setup_tokens") if isinstance(g.get("setup_tokens"), list) else []
            for i, e in enumerate(usage.get("credentials") or []):
                slug = by_fp.get(prints[i]) if i < len(prints) and isinstance(prints[i], str) else None
                if slug and isinstance(e, dict):
                    readings.setdefault(slug, []).append(reading_from_gateway(e, login))
        st = states.get(login) or {}
        known = st.get("state") not in (None, "unknown")
        logins.append({"login": login, "account": account, "fingerprint": m.group(1) if m else None, "gateway": live,
                       "kinds": g.get("sessions") if isinstance(g.get("sessions"), dict) else {"status": "unknown"},
                       "sessions": [s for s in (st.get("sessions") or []) if isinstance(s, dict) and isinstance(s.get("session"), str)],
                       "state_known": known})
    return readings, logins


def probe_due(views: dict[str, View], pool: Sequence[str], probes: dict, now: float, every: float) -> list[str]:
    return [a for a in pool if views[a].stale and now - float(probes.get(a, 0)) >= every]


def probe(slug: str, logins: list[dict], ctl: Callable[[list[str]], list[dict]], now: float) -> dict | None:
    """ADR-031 rule 9's read of `slug`, through a login that runs on it (one on its gateway first): one output
    token of that account. None when no login runs on it or the read gave nothing."""
    on = sorted((lg for lg in logins if lg["account"] == slug), key=lambda lg: not lg["gateway"])
    if not on:
        return None
    rows = ctl([on[0]["login"], "usage"])
    return reading_from_probe(rows[0], on[0]["login"], now) if rows else None


# ── state, lock, the log ────────────────────────────────────────────

def read_state(state: str) -> dict:
    try:
        with open(os.path.join(state, STATE), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    doc = doc if isinstance(doc, dict) else {}
    return {k: doc.get(k) if isinstance(doc.get(k), dict) else {} for k in ("probes", "probed", "last")}


def write_state(state: str, doc: dict) -> None:
    os.makedirs(state, exist_ok=True)
    p = os.path.join(state, STATE)
    tmp = f"{p}.tmp-{os.getpid()}"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    os.replace(tmp, p)


def take_lock(state: str) -> int | None:
    """One run at a time (the agentd timer and a person's --tick): an exclusive flock, never waited on."""
    os.makedirs(state, exist_ok=True)
    fd = os.open(os.path.join(state, LOCK), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def _key(d: dict, mode: str) -> str:
    """What makes two runs' decisions for a login the same one. The mode is in it: a move logged `would` in
    advise is a new decision once the policy says act, and is made."""
    return json.dumps([mode, d["rule"], d["reason"], d["from"], d.get("to"), d["outcome"]])


def _side(slug: str | None, fps: dict[str, str]) -> dict | None:
    return None if slug is None else {"account": slug, "fingerprint": fps.get(slug)}


def to_lines(decisions: list[dict], *, mode: str, policy: dict, views: dict[str, View], fps: dict[str, str],
             at: float, last: dict) -> tuple[list[tuple[dict, dict, str]], set[str]]:
    """([(decision, log line, key)] for each move and each told hold that is not the same one as the last
    recorded for its login, the logins that had one). Nothing is recorded here: `remember` does, after the
    lines were made, so a move that failed is never recorded and is tried again at the next run."""
    out = []
    seen = set()
    for d in decisions:
        if d["outcome"] == "move" or (d["outcome"] == "hold" and d.get("tell")):
            seen.add(d["login"])
            k = _key(d, mode)
            if last.get(d["login"]) == k:
                continue   # logged (and in act, made) already: a lagging identity read must not assign again
            accounts = [a for a in (d["from"], d.get("to")) if a] if d["outcome"] == "move" else list(policy["pool"]["accounts"])
            out.append((d, switch_log.line(
                v=switch_log.VERSION, at=iso(at), mode=mode, outcome="would" if d["outcome"] == "move" else "held",
                pool=policy["pool"]["name"], login=d["login"], sessions=d.get("sessions", []), rule=d["rule"],
                reason=d["reason"], relaxed=bool(d.get("relaxed")), **{"from": _side(d["from"], fps)},
                to=_side(d.get("to"), fps), readings={a: views[a].logged() for a in accounts},
                tell=bool(d.get("tell")), why=d["why"]), k))
    return out, seen


def remember(last: dict, pending: list[tuple[dict, dict, str]], logged: list[dict], seen: set[str]) -> None:
    """Record each logged line's key for its login, except a `failed` one; forget a login with nothing to log."""
    for (d, _line, k), line in zip(pending, logged):
        if line["outcome"] != "failed":
            last[d["login"]] = k
    for login in [lg for lg in last if lg not in seen]:
        del last[login]


def would(lines: list[tuple[dict, dict]]) -> list[dict]:
    """advise: the lines as decided. Takes no assign path; nothing here can move a login."""
    return [line for _d, line in lines]


def act(lines: list[tuple[dict, dict]], assign: Callable[[str, str], dict]) -> list[dict]:
    """act: each move by the assign path, its verdict and proof in the line; a told hold as it is."""
    out = []
    for d, line in lines:
        if line["outcome"] != "would":
            out.append(line)
            continue
        verdict = assign(d["login"], d["to"])
        out.append({**line, "outcome": "did" if verdict.get("exit") == 0 else "failed", "assign": verdict})
    return out


def assign_path(root: str, run: Callable[..., Any] = subprocess.run) -> Callable[[str, str], dict]:
    """The move, as ADR-031 makes it: `fabric-accounts assign <login> <account> --no-restart` (the store write,
    the signed secrets-sync with the template's fingerprint expected, the reply's gateway proof). --no-restart:
    a gateway session takes the new token file with no restart, and no plain-claude session is ever stopped."""
    def assign(login: str, account: str) -> dict:
        cmd = [os.path.join(root, "bin", "fabric-accounts"), "assign", login, account, "--no-restart"]
        try:
            r = run(cmd, capture_output=True, timeout=ASSIGN_TIMEOUT_S, check=False, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"exit": None, "output": [f"{type(e).__name__}: {str(e)[:160]}"]}
        text = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
        return {"exit": r.returncode, "output": [ln[:240] for ln in text.splitlines() if ln.strip()][-OUTPUT_LINES:]}
    return assign


def ctl_path(root: str, run: Callable[..., Any] = subprocess.run) -> Callable[[list[str]], list[dict]]:
    """fabric-ctl's --json rows for one read; [] when it gave none (a silent account is its own row)."""
    def ctl(args: list[str]) -> list[dict]:
        try:
            r = run([os.path.join(root, "bin", "fabric-ctl"), *args, "--json"], capture_output=True,
                    timeout=CTL_TIMEOUT_S, check=False, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            return []
        rows = []
        for text in (r.stdout or b"").decode("utf-8", "replace").splitlines():
            try:
                doc = json.loads(text)
            except ValueError:
                continue
            if isinstance(doc, dict):
                rows.append(doc)
        return rows
    return ctl


# ── one run ─────────────────────────────────────────────────────────

def _fabric_root() -> str:
    return os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))


def _policy_file(root: str) -> str:
    import roots
    return roots.routing_policy(switch_policy.NAME, engine=root)


def _state_dir() -> str:
    from control.ops import util
    return util.state_dir()


def _templates() -> list[dict]:
    from control import accounts
    return accounts.store_templates()


def run(*, record: bool, root: str | None = None, state: str | None = None, policy_file: str | None = None,
        ctl: Callable[[list[str]], list[dict]] | None = None, templates: Callable[[], list[dict]] | None = None,
        make_assign: Callable[[str], Callable[[str, str], dict]] = assign_path,
        now: Callable[[], float] = time.time, say: Callable[[str], None] = print) -> int:
    """One controller run. record=False is `fabric-accounts switch`: decided and printed, nothing logged or
    moved. record=True is a tick: the log, and in act the moves. Exit 0 done, 1 another run holds the lock or
    a step failed, 2 the policy cannot be run on."""
    root = root or _fabric_root()
    try:
        policy = switch_policy.load(policy_file or _policy_file(root))
    except switch_policy.PolicyError as e:
        say(f"account switch: {e}; nothing decided")
        return 2
    mode = policy["mode"]
    if record and mode == "off":
        return 0
    state = state or _state_dir()
    fd = take_lock(state)
    if fd is None:
        say("account switch: another run holds the lock; nothing done")
        return 1
    try:
        t = now()
        ts = (templates or _templates)()
        fps = {x["account"]: x.get("token_sha256_12") for x in ts}
        missing = [a for a in policy["pool"]["accounts"] if not fps.get(a)]
        # A pool account with no template in this store cannot be assigned (fabric-accounts assign refuses it):
        # it leaves the pool for this run, so no rule reads it, targets it or probes it, a reading kept from
        # before included.
        pool = [a for a in policy["pool"]["accounts"] if fps.get(a)]
        policy = {**policy, "pool": {**policy["pool"], "accounts": pool}}
        ask = ctl or ctl_path(root)
        readings, logins = gather(ask, ts)
        st = read_state(state)
        # A probe's reading is kept until a fresher one replaces it: it is read once per probe_min_interval_s and
        # must count for the runs between.
        for a, kept in st["probed"].items():
            if a in pool and isinstance(kept, dict):
                readings.setdefault(a, []).append(kept)
        views = {a: View(a, freshest(readings.get(a, []), t), t, policy["reading_max_age_s"]) for a in pool}
        for a in probe_due(views, pool, st["probes"], t, policy["probe_min_interval_s"]):
            got = probe(a, logins, ask, t)
            st["probes"][a] = t
            if got:
                st["probed"][a] = got
                views[a] = View(a, freshest([*readings.get(a, []), got], t), t, policy["reading_max_age_s"])
        history = [h for h in (switch_log.tail(state, 500) or []) if h.get("outcome") == ("did" if mode == "act" else "would")]
        decisions = decide(policy, views, logins, history, t)
        say(f"  mode {mode}, pool {policy['pool']['name']}")
        if missing:
            say(f"account switch: no template for {', '.join(missing)} (fabric-accounts templates): never a target")
        for a in pool:
            v = views[a]
            say(f"  {a:<34} 5h {_pct(v.u5)}  7d {_pct(v.u7)}  7d resets {iso(v.r7)[:16] if v.r7 else '-'}"
                f"{'  EXHAUSTED (' + str(v.exhausted_why) + ')' if v.exhausted else ''}"
                f"  {'read ' + str(int(v.age)) + ' s ago via ' + str(v.reading.get('via')) if v.age is not None and v.reading else 'no reading'}")
        for d in decisions:
            say(f"  {d['login']:<22} {d['outcome']:<5} {d.get('from') or '-'}"
                f"{' -> ' + d['to'] if d.get('to') else ''}  {d['why']}{'  (owner told)' if d.get('tell') else ''}")
        if not record:
            write_state(state, {**read_state(state), "probes": st["probes"], "probed": st["probed"]})
            return 0
        pending, seen = to_lines(decisions, mode=mode, policy=policy, views=views, fps=fps, at=t, last=st["last"])
        lines = [(d, line) for d, line, _k in pending]
        if mode == "act":
            # The only place the assign path is built: advise never holds it.
            logged = act(lines, make_assign(root))
        else:
            logged = would(lines)
        switch_log.append(state, logged)
        remember(st["last"], pending, logged, seen)
        write_state(state, st)
        return 1 if any(x["outcome"] == "failed" for x in logged) else 0
    finally:
        os.close(fd)


def _pct(x: float | None) -> str:
    return "   -" if x is None else f"{x * 100:3.0f}%"


def start(ticker: Callable[..., Any], log: Callable[[str], None]) -> None:
    """agentd's timer, on the coordinator's account: a tick every interval_s, the first after FIRST_TICK_S.
    The policy is read at each tick (mode and numbers); its interval when the daemon starts."""
    root = _fabric_root()
    try:
        every = switch_policy.load(_policy_file(root))["interval_s"]
    except switch_policy.PolicyError as e:
        log(f"agentd: account switch not started: {e}")
        return

    def tick() -> None:
        # The table a run prints is for a person; the daemon's log gets only what went wrong.
        run(record=True, root=root, say=lambda m: None if m.startswith("  ") else log(f"agentd: {m}"))
    ticker("account switch", tick, every, first_s=FIRST_TICK_S).start()


def main(argv: Sequence[str] | None = None, **kw: Any) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--log"]:
        n = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 20
        state = kw.get("state") or _state_dir()
        lines = switch_log.tail(state, n)
        if lines is None:
            print(f"account switch: {switch_log.path(state)} cannot be read", file=sys.stderr)
            return 1
        print("\n".join(switch_log.words(e) for e in lines) if lines else "account switch: no move logged yet")
        return 0
    if argv not in ([], ["--tick"]):
        print("usage: fabric-accounts switch [--tick | --log [N]]", file=sys.stderr)
        return 2
    return run(record=argv == ["--tick"], **kw)
