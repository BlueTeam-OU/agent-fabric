#!/usr/bin/env python3
"""tools/fabric/control/deaf_alarm.py — say a deaf session to the coordinator, once per account and episode (j188).

  deaf_alarm.py [--to <host/login>] [--dry-run] [--no-restart]

Run on the coordinator's account by agent-fabric-deaf-alarm.timer. It asks every account's control agent for its `deaf`
section (`fabric-ctl all deaf --json`; the rule is control/deaf.py's) and sends one INFO to --to (default: this login) for each
account that is deaf and whose episode the ledger does not hold. WHY a ledger and not the poll: the section stays true for as
long as the session is deaf, 25 h in the case that made it, and a message per poll is a message per five minutes.

THE LEDGER, <state>/deaf-alarm.json: {account: episode}. An episode is the watch-log line the deafness began at
(deaf.py `episode`), so it is the same on every poll of one deafness and differs after any watch has run in between.
  - recorded only after gzcoord-send took the message: a failed send is retried by the next run, never lost;
  - an account whose section says deaf False is dropped (recovered), so its next deafness is a new episode even if a
    log line were ever repeated;
  - an account that did not answer, or whose section is "unknown", keeps its entry: unknown is not recovered, and an alarm
    already sent is not sent again because the account was unreachable for one poll.

EXIT  0 read; each new episode's message sent (or, with --dry-run, printed)
      3 the accounts could not be read (fabric-ctl failed, timed out or printed no list), or a message could not be confirmed sent
        (the others still went, and the ledger holds what went)
      2 bad command line
STDOUT one line per message sent (or that --dry-run would send); STDERR the reasons for exit 3.
The message carries the account, how the watch ended, how long, and what waits; no secret and no message text of the account's.

THE RESTART (j1061; the owner's word of 2026-11-23). An account that is deaf AND whose `deaf` section says idle true (deaf.py: the
transcript quiet, the last turn ended, no tool call pending) is restarted with `fabric-ctl <login> restart`, then told in the INFO.
  - RECORD BEFORE ACT: <state>/deaf-restart.json {account: {episode, times, outcome}} is written, fsynced, before the restart runs, so a
    crash, a timeout or a failed send never repeats it for one episode (j190's loop must not become a restart loop). If it cannot be
    written nothing is restarted;
  - at most one restart per episode, and MAX_RESTARTS per account in RESTART_WINDOW_S; past the cap the alarm says the restarts did not
    restore a watch. The times outlive a recovery: only the window ages them out;
  - never this login's own account (a session does not stop the one it waits on; the control agent's `yours` is the second guard);
  - idle false or "unknown", or no idle in the row (an older control agent): alarm only, naming why, so the pane is read;
  - --no-restart and --dry-run restart nothing and write nothing.
The INFO of a restarted episode is a message of its own (ledger value `<episode>#restart`): an alarm already sent while the session was
held at a prompt does not stand in for "restarted it".

Not decided here: what the coordinator does about an alarm-only account (reading its pane)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable

CTL_TIMEOUT_S = 180
SEND_TIMEOUT_S = 60
LEDGER = "deaf-alarm.json"
PENDING = "deaf-alarm-pending"
RESTART_LEDGER = "deaf-restart.json"
MAX_RESTARTS = 2
RESTART_WINDOW_S = 24 * 3600
RESTART_TAG = "#restart"


def read_ledger(path: str) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    # A ledger that cannot be read is not an empty one: starting over would send every standing alarm again.
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError(f"{path} is not a map of account to episode")
    return data


def write_ledger(path: str, ledger: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=LEDGER + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(ledger, fh, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_rows(run: Callable[..., Any] = subprocess.run) -> list[dict]:
    try:
        r = run(["fabric-ctl", "all", "deaf", "--json"], capture_output=True, text=True, timeout=CTL_TIMEOUT_S, stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f"fabric-ctl all deaf: {e.__class__.__name__}: {e}") from e
    # fabric-ctl prints one JSON object per account per line, and exits 1 when any account did not answer while still printing
    # that account's row ("no answer"): the rows of the others are the answer, and an unanswering account is what the ledger keeps.
    # Any other code, or output that is not rows, is a failed read.
    if r.returncode not in (0, 1):
        raise RuntimeError(f"fabric-ctl all deaf exited {r.returncode}: {(r.stderr or '').strip()[-200:]}")
    rows = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as e:
            raise RuntimeError(f"fabric-ctl all deaf printed a line that is not JSON ({e})") from e
        if not isinstance(row, dict) or not isinstance(row.get("account"), str):
            raise RuntimeError("fabric-ctl all deaf printed a line that is not an account's row")
        rows.append(row)
    if not rows:
        raise RuntimeError(f"fabric-ctl all deaf printed no rows (exit {r.returncode}: {(r.stderr or '').strip()[-200:]})")
    return rows


def ctl_restart(account: str, run: Callable[..., Any] = subprocess.run) -> tuple[str, str]:
    """(status, reason) of `fabric-ctl <account> restart`: the control agent's own words (restart.py: restarted, no-session, yours, failed,
    refused, busy), or "failed" with why when fabric-ctl itself did not say. Never raises for a command that failed."""
    from control.restart import RESTART_BUDGET_S
    argv = ["fabric-ctl", "--json", "--timeout", str(int(RESTART_BUDGET_S)), account, "restart"]
    try:
        r = run(argv, capture_output=True, text=True, timeout=RESTART_BUDGET_S + 60, stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        return "failed", f"fabric-ctl: {e.__class__.__name__}"
    for line in (r.stdout or "").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("account") == account:
            data = rec.get("restart")
            if isinstance(data, dict) and isinstance(data.get("status"), str):
                why = data.get("reason") or data.get("note") or ""
                return data["status"], str(why)[:200]
            return "failed", f"the account's row has no restart answer (status {str(rec.get('status'))[:40]})"
    return "failed", f"fabric-ctl exited {r.returncode} with no row for the account: {(r.stderr or '').strip()[-120:]}"


class Restarter:
    """The restart half: decides from the row and the restart ledger, and acts only after the ledger holds the attempt."""

    def __init__(self, path: str, own: str, *, ctl: Callable[[str], tuple[str, str]] = ctl_restart, clock: Callable[[], float] = time.time) -> None:
        self.path, self.own, self.ctl, self.clock = path, own, ctl, clock
        self.ledger = self._read()

    def _read(self) -> dict[str, dict]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {}
        # As the alarm ledger: one that cannot be read is not an empty one, or the cap would start again from nothing.
        ok = isinstance(data, dict) and all(
            isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("episode"), str)
            and isinstance(v.get("times"), list) and all(isinstance(t, (int, float)) for t in v["times"])
            and (v.get("outcome") is None or isinstance(v.get("outcome"), str)) for k, v in data.items())
        if not ok:
            raise ValueError(f"{self.path} is not a map of account to restart record")
        return data

    def _write(self) -> None:
        write_ledger(self.path, self.ledger)   # type: ignore[arg-type]  # same atomic write; the values are records here

    def plan(self, account: str, episode: str, d: dict) -> tuple[str, str]:
        """("restart"|"already"|"skip", note). `already`: this episode has been restarted; note is its recorded outcome."""
        rec = self.ledger.get(account)
        if rec and rec["episode"] == episode:
            return "already", rec.get("outcome") or "attempted; its result was not recorded"
        if account == self.own:
            return "skip", "this login's own account is never restarted from here"
        idle = d.get("idle")
        if idle is not True:
            why = d.get("idle_why") if isinstance(d.get("idle_why"), str) else "the section does not say"
            return "skip", f"idle is {json.dumps(idle) if idle is not None else 'absent'} ({why}); read its pane"
        recent = [t for t in (rec["times"] if rec else []) if self.clock() - t < RESTART_WINDOW_S]
        if len(recent) >= MAX_RESTARTS:
            return "skip", (f"{len(recent)} restarts in the last 24 h did not restore a watch; a restart is not repeated, "
                            "read its pane")
        return "restart", ""

    def execute(self, account: str, episode: str) -> str:
        """Record the attempt, then restart, then record the outcome. The outcome text; "not restarted: ..." when the ledger would not take it."""
        times = [t for t in (self.ledger.get(account) or {"times": []})["times"] if self.clock() - t < RESTART_WINDOW_S] + [self.clock()]
        before = self.ledger.get(account)
        self.ledger[account] = {"episode": episode, "times": times, "outcome": None}
        try:
            self._write()
        except OSError as e:
            # Not durable, so not done: a restart that may repeat is the loop this ledger exists to prevent.
            if before is None:
                del self.ledger[account]
            else:
                self.ledger[account] = before
            return f"not restarted: the restart ledger cannot be written ({e.__class__.__name__})"
        try:
            status, reason = self.ctl(account)
        except BaseException as e:   # the entry stays: an attempt that raised is still an attempt
            self.ledger[account]["outcome"] = f"failed: {e.__class__.__name__}"
            try:
                self._write()
            except OSError:
                pass
            raise
        outcome = status + (f": {reason}" if reason else "")
        self.ledger[account]["outcome"] = outcome
        try:
            self._write()
        except OSError:
            pass   # the attempt is on disk already; only the wording of its result is lost
        return outcome


def episode_of(row: dict) -> tuple[str, dict] | None:
    """(episode, section) when the row says deaf, else None."""
    d = row.get("deaf")
    if row.get("status") == "ok" and isinstance(d, dict) and d.get("status") == "ok" and d.get("deaf") is True and isinstance(d.get("episode"), str):
        return d["episode"], d
    return None


def recovered(row: dict) -> bool:
    d = row.get("deaf")
    return row.get("status") == "ok" and isinstance(d, dict) and d.get("status") == "ok" and d.get("deaf") is False


def body(account: str, d: dict) -> tuple[str, str]:
    p = d.get("pending") if isinstance(d.get("pending"), dict) else {}
    unread = p.get("unread")
    waiting = (f"{p.get('queued_requests')} queued job(s) taken from a REQUEST" if unread is None
               else f"{unread} unread message(s) of its own and {p.get('queued_requests')} queued job(s) taken from a REQUEST")
    context = (f"{account} has a session running and no inbox watch. Its watch log's last line is: {d.get('watch')}. "
               f"It has been so since {d.get('since')} ({d.get('age_s')} s) and work waits for it: {waiting}.")
    done = d.get("action")
    if isinstance(done, str):
        notes = (f"{done} One message per episode and action: it is not repeated while this deafness lasts. Rules: "
                 "tools/fabric/control/deaf.py, deaf_alarm.py.")
    else:
        notes = ("An idle session has no turn in which to arm its watch again; this one can be helped only from outside "
                 f"(`fabric-ctl {account} restart`, or a message that makes the session act). One message per episode: "
                 "it is not repeated while this deafness lasts. Rule: tools/fabric/control/deaf.py.")
    return context, notes


def pending_path(pending_dir: str, account: str, episode: str) -> str:
    # Hashed: an account is an address and an episode has "@" and ":" in it; neither belongs in a file name.
    h = lambda x: hashlib.sha256(x.encode("utf-8")).hexdigest()[:16]  # noqa: E731
    return os.path.join(pending_dir, f"{h(account)}-{h(episode)}.txt")


def _post(run: Callable[..., Any], path: str, keep: bool = False, fresh: bool = False) -> None:
    """Post `path`. `keep`: the file is the episode's kept message. It is removed on exit 0, kept on exit 3 (may be delivered
    or unknown), and removed on another non-zero exit only when `fresh`: a file composed in this attempt that sent nothing,
    whose TO would otherwise outlive a corrected --to (review of #718, F1). A file that has already seen an exit 3 is never
    removed by a later failure: its id may be at the addressee, and composing again would be a second message (F3)."""
    r = run(["gzcoord-send", path], capture_output=True, text=True, timeout=SEND_TIMEOUT_S, stdin=subprocess.DEVNULL, check=False)
    if r.returncode == 0:
        if keep:
            os.unlink(path)
        return
    if keep and fresh and r.returncode != 3:
        os.unlink(path)
    raise RuntimeError(f"gzcoord-send exited {r.returncode}: {(r.stderr or '').strip()[-200:]}")


def _kept_to(path: str) -> str | None:
    # A kept file for another addressee (the operator corrected --to since) is not this send's message: it is composed anew.
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("TO:"):
                return line[3:].strip()
    return None


def send(account: str, d: dict, to: str, run: Callable[..., Any] = subprocess.run, pending_dir: str | None = None) -> None:
    """Compose and post the INFO. With `pending_dir` the composed file is kept there while gzcoord-send's last exit was 3, and the
    next attempt for the same episode posts THAT file again instead of composing another.

    WHY: gzcoord-send's exit 3 does not say "not sent": it also means "the relay refused but the carrier delivered it"
    (to one login: send.py `carrier-took-it`) and "outcome unknown", and its only signal for them is a localized stderr line.
    A message composed afresh per attempt is a new MESSAGE-ID each time, so the coordinator got the same alarm every 5 min
    (j190). The file carries the id gzcoord-send wrote into it, so a resend is the same message and a reader discards the
    copy (SPEC 7.2): whichever of the three exit 3 meant, posting the same file again is right."""
    kept = pending_path(pending_dir, account, str(d.get("episode"))) if pending_dir else None
    if kept and os.path.exists(kept) and _kept_to(kept) == to:
        _post(run, kept, keep=True)
        return
    context, notes = body(account, d)
    with tempfile.TemporaryDirectory(prefix="deaf-alarm-") as tmp:
        path = os.path.join(tmp, "message.txt")
        subject = f"{account}: session idle and deaf ({d.get('watch')})"
        r = run(["gzcoord-compose", "INFO", "--to", to, "--subject", subject, "-o", path], capture_output=True, text=True,
                timeout=SEND_TIMEOUT_S, stdin=subprocess.DEVNULL, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"gzcoord-compose exited {r.returncode}: {(r.stderr or '').strip()[-200:]}")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        skeleton = "CONTEXT:\n\nNOTES:\n"
        if skeleton not in text:
            raise RuntimeError("gzcoord-compose's INFO has not the skeleton this expects")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(skeleton, f"CONTEXT:\n{context}\n\nNOTES:\n{notes}\n", 1))
        if kept:
            # An earlier episode of this account is over: its file would otherwise stay for ever.
            os.makedirs(pending_dir, mode=0o700, exist_ok=True)
            drop_pending(pending_dir, account)
            shutil.copyfile(path, kept)
            path = kept
        _post(run, path, keep=bool(kept), fresh=True)


def drop_pending(pending_dir: str, account: str) -> None:
    prefix = os.path.basename(pending_path(pending_dir, account, "")).split("-")[0] + "-"
    try:
        names = os.listdir(pending_dir)
    except FileNotFoundError:
        return
    for name in names:
        if name.startswith(prefix):
            try:
                os.unlink(os.path.join(pending_dir, name))
            except FileNotFoundError:
                pass   # a second run took it first


def alarm(rows: list[dict], ledger: dict[str, str], to: str, dry_run: bool = False,
          send_one: Callable[[str, dict, str], None] = send, pending_dir: str | None = None,
          restarter: Restarter | None = None) -> tuple[dict[str, str], list[str], list[str]]:
    """(the new ledger, the lines said, the failures). Apart from `send_one` and `restarter`, its only effect is removing a recovered account's pending file."""
    new = dict(ledger)
    said: list[str] = []
    failed: list[str] = []
    for row in sorted(rows, key=lambda r: r["account"]):
        account = row["account"]
        hit = episode_of(row)
        if hit is None:
            if recovered(row):
                new.pop(account, None)
                if pending_dir and not dry_run:
                    try:
                        drop_pending(pending_dir, account)
                    except OSError as e:
                        failed.append(f"{account}: its pending file cannot be removed: {e}")
            continue
        episode, d = hit
        kind, note = restarter.plan(account, episode, d) if restarter else ("none", "")
        key = episode + RESTART_TAG if kind in ("restart", "already") else episode
        if new.get(account) == key:
            continue
        what = ""
        if kind == "restart" and dry_run:
            what = " (idle: would restart)"
        elif kind == "restart":
            assert restarter is not None
            try:
                outcome = restarter.execute(account, episode)
            except (OSError, subprocess.SubprocessError, RuntimeError) as e:
                outcome = f"failed: {e.__class__.__name__}"
            if outcome.startswith("not restarted"):
                key = episode   # nothing was done: the alarm-only message is the true one
                d = {**d, "action": f"{outcome}; read its pane."}
                if new.get(account) == key:
                    failed.append(f"{account}: {outcome}")
                    continue
            else:
                d = {**d, "action": f"The session was idle ({d.get('idle_why')}), so `fabric-ctl {account} restart` was run: {outcome}."}
                what = f" (restart: {outcome})"
        elif kind == "already":
            d = {**d, "action": f"The session was idle, so `fabric-ctl {account} restart` was run: {note}."}
            what = f" (restart: {note})"
        elif kind == "skip":
            d = {**d, "action": f"Not restarted: {note}."}
        if not dry_run:
            try:
                send_one(account, {**d, "episode": key}, to)
            except (RuntimeError, OSError, subprocess.SubprocessError) as e:
                failed.append(f"{account}: {e}")
                continue
            new[account] = key
        said.append(f"{account}: deaf since {d.get('since')} ({d.get('watch')}){what} -> {to}")
    return new, said, failed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="deaf_alarm.py", description="One INFO to the coordinator per deaf account and episode.")
    ap.add_argument("--to", help="the address told (default: this login)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-restart", action="store_true", help="alarm only: restart no idle account (the unit restarts them by default)")
    a = ap.parse_args(argv)
    from control.ops import util
    to = a.to
    if not to:
        from gzcoord import gzmsg
        who = gzmsg.whoami()
        to = who.get("address") if isinstance(who, dict) and isinstance(who.get("address"), str) else None
        if not to:
            print("deaf_alarm: this login's address cannot be read; pass --to", file=sys.stderr)
            return 3
    path = os.path.join(util.state_dir(), LEDGER)
    try:
        ledger = read_ledger(path)
        rows = read_rows()
    except (RuntimeError, ValueError, OSError) as e:
        print(f"deaf_alarm: {e}", file=sys.stderr)
        return 3
    pending_dir = os.path.join(util.state_dir(), PENDING)
    restarter = None
    unreadable = []
    if not a.no_restart:
        import pwd
        try:
            restarter = Restarter(os.path.join(util.state_dir(), RESTART_LEDGER), pwd.getpwuid(os.getuid()).pw_name)
        except (ValueError, OSError) as e:
            unreadable.append(f"{e}; nothing is restarted this run")
    new, said, failed = alarm(rows, ledger, to, a.dry_run, lambda acc, d, t: send(acc, d, t, pending_dir=pending_dir), pending_dir, restarter)
    failed += unreadable
    for line in said:
        print(line)
    if new != ledger:
        try:
            write_ledger(path, new)
        except OSError as e:
            print(f"deaf_alarm: the ledger cannot be written ({e}); the next run sends these again", file=sys.stderr)
            return 3
    for f in failed:
        print(f"deaf_alarm: not confirmed sent: {f}", file=sys.stderr)
    return 3 if failed else 0


if __name__ == "__main__":
    # Run as a script, sys.path[0] is control/, whose secrets.py and tools.py would shadow the standard library's (ctl_entry.py says the same).
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    sys.exit(main())
