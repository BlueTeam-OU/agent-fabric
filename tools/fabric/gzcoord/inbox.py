"""tools/fabric/gzcoord/inbox.py — GZCoord's inbox: what the relay holds for
THIS session, delivered the way SPEC §17 says a recipient receives — a
body read only when it is addressed to it. Ported from
communication/gzcoord/scripts/inbox.mjs (agent-fabric ADR-040 §7, Wave
7); that path is now a shim that runs this.

CONTRACT, frozen from the Node:
  argv      (none)              drain: one cursor page, return at once
            --follow            the watch: block for the life of the
                                session, print each delivery as it lands,
                                never return on a quiet spell
            --wait [S]          block up to S seconds (Number(S), else
                                1800) and return the moment a message
                                addressed here lands; --keyword K
                                (repeatable, 3+ characters, at most 8)
                                also ends it on a passing message
            --replay <seq|message-id> [--json]
                                re-read ONE message; the cursor does not
                                move; a body not addressed here is not
                                shown. --json: one object (addressed,
                                seq, sender, when, type, metadata, text),
                                or {"addressed": false, "seq": N}
            --history [<seq>]   one line per message addressed here in the
                                relay's recent history; bodies stay with
                                --replay; the cursor does not move
            --held              is this account's inbox held (planning)?
  env       CLAUDE_BRIDGE_URL and GZCOORD_CHANNEL (together, or over a
            project's integration), CLAUDE_BRIDGE_AUTH_TOKEN (after the
            synced file), AGENT_FABRIC_ROOT, AGENT_FABRIC_STATE_DIR,
            AGENT_FABRIC_HOLD_DIR, GZCOORD_JOURNAL=off, GZCOORD_RELAY_UNIT,
            GZCOORD_TEST_BUS_ANY=1, XDG_RUNTIME_DIR, HOME,
            GZCOORD_DEFAULT_LOCALE_ONLY
  stdout    deliveries (below one, a `queued as jN: <title>` line for each
            REQUEST to this login it put on the job list, intake.py), the
            drain's listing, replay/history output, the
            keyword hit, the watch's relay-down/back lines, the
            journal's held-messages line and, under GZCOORD_JOURNAL=off,
            one bypass warning per page — what the Monitor turns into
            notifications
  stderr    every start-up and refusal line; the hold's held/released
  exit      0 drained, delivered, nothing for you, not configured, no
            token, relay unreachable on a drain or wait; 1 a usage line,
            replay of no such message, the --held "not held"; 2 a control
            channel named, replay not addressed (--json too); 3 a keyword
            hit; 4 a refused token (the watch ends with it). Anything
            unforeseen is `gzcoord inbox: <why>` and exit 0: the whole
            contract of a session start is one line and exit 0.

The rest of the Node's header — the modes, the hold, the addressee rule,
why the watch is one process under a Monitor — is kept where each
applies: below, or in the part that holds it (inbox_parts/). Never blocks a session start: relay down, no token, no
catalogue — each is one line on stderr and exit 0.

THE JOURNAL (ADR-041 rule 4), in this process now: a page's messages
addressed to this session are kept in its own journal before the page is
acknowledged; one the journal cannot take is neither acknowledged nor
shown. The Node ran episodic.py as a process per page, and that crossing
is where the journal's edge cases kept appearing (#78, #84, #88) — the
reason Wave 7 moved this file. The order is the protocol's and is kept.
GZCOORD_JOURNAL=off skips the journal, never the record: each of those
messages gets a line in journal-bypass.jsonl (gzcoord/bypass.py) before it
is shown or acknowledged, and a line that cannot be written holds the page
as a journal that cannot keep it does. --replay and --history leave no
bypass line, journal on or off: they show what the relay already holds and
acknowledge nothing, and the journal is not written by them in either mode.
A replay ahead of the drain shows a record no line or row records yet: it
is logged when the drain or the watch delivers it.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import threading
import time
import urllib.parse
from typing import Any, Callable

from . import bypass, gzmsg, i18n, intake
from . import jsvalues as js
from .gzmsg import en  # noqa: F401 — send.py calls inbox.en()

# The default dictionary's printer for a caller that passes none: a test,
# another tool. main() resolves the login's once and passes it down.

# Every name the parts define, from here as before: the GZCoord tools and
# tests reach them as inbox.<name>. _episodic, which tests replace, stays
# here with run_episodic and journal_inbound, which call it; it is the one
# name a test can replace here: the parts call one another directly, so
# replacing any other name on inbox changes main() and nothing it calls.
from .inbox_parts.config import workspace, relay_runtime_dir, integration_config, default_relay  # noqa: F401
from .inbox_parts.config import ControlChannel, assert_not_control_channel, git_toplevel  # noqa: F401
from .inbox_parts.config import inbox_root  # noqa: F401
from .inbox_parts.tokens import synced_var, TokenRefused, checked_token, synced_token, token  # noqa: F401
from .inbox_parts.tokens import _token, identity, for_me  # noqa: F401
from .inbox_parts.relay import _relay_up, ensure_relay, RelayError, API_TIMEOUT  # noqa: F401
from .inbox_parts.relay import _OPENER, api, explain_relay_error  # noqa: F401
from .inbox_parts.records import _records, _when, one_line, _parse_quiet, replay, HISTORY_WINDOW  # noqa: F401
from .inbox_parts.records import history, RETRANSMISSION_LOOKUP_MS, mark_retransmissions  # noqa: F401
from .inbox_parts.records import KEYWORD_MIN, KEYWORD_MAX, KeywordError, check_keywords  # noqa: F401
from .inbox_parts.records import _TOKEN_SPLIT, keyword_hit, REPLAY_CMD  # noqa: F401
from .inbox_parts.hold import hold_dir, pid_start, pid_alive, hold_status, HOLD_POLL_MS  # noqa: F401
from .inbox_parts.render import NOTIFICATION_CAP, MAX_FLAG_LINES, _SECTION, cut_at_line  # noqa: F401
from .inbox_parts.render import _drop_final_newline, split_message, render  # noqa: F401
from .inbox_parts.watch import JOURNAL_RETRY_MS, bypass_inbound, wait_loop  # noqa: F401


def _episodic():
    """tools/fabric/episodic.py — its own CLI, run in this process: the
    same exit codes and the same one-line reasons it gave as a process."""
    tools = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import episodic  # noqa: E402 — the sibling module, loaded when a page needs it
    return episodic


def run_episodic(args: list[str], stdin: str) -> dict:
    """{status, stdout, stderr} of `episodic.py <args>` with stdin, in this
    process. An exception that escapes it is a journal that did not answer;
    an interrupt or an exit is not."""
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdin
    try:
        sys.stdin = io.StringIO(stdin)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = _episodic().main(args)
    except (KeyboardInterrupt, SystemExit):
        # Read as "journal failed", a forwarded SIGINT left the watch running.
        raise
    except BaseException as e:  # noqa: BLE001 — anything the journal raised is its non-answer
        status, err = 1, io.StringIO(err.getvalue() + f"episodic: {type(e).__name__}: {e}\n")
    finally:
        sys.stdin = saved
    return {"status": status if isinstance(status, int) else 1, "stdout": out.getvalue(), "stderr": err.getvalue()}


def journal_inbound(records: list[dict], who: dict | None, run: Callable[[list[str], str], dict] = run_episodic) -> dict:
    where = [*(["--project", who["project"]] if who and who.get("project") else []),
             *(["--working-copy", who["working_copy"]] if who and who.get("working_copy") else [])]
    lines = [js.stringify({"content": r.get("content"),
                           "seq": js.coalesce(js.get(r, "seq"), None),
                           "ts": js.coalesce(js.get(r, "ts_full"), js.get(r, "timestamp"), js.get(r, "ts"), None)})
             for r in records]
    r = run(["gzcoord-in", *where], "\n".join(lines) + "\n")
    said = [x for x in str(r.get("stderr") or "").strip().split("\n") if x]
    if r.get("status") != 0:
        return {"ok": False, "reason": said[-1] if said else f"episodic: the journal did not answer (exit {r.get('status')})"}
    return {"ok": True, "said": said}


# ── the command ──────────────────────────────────────────────────────

class _Exit(Exception):
    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


def _arg_after(argv: list[str], flag: str) -> Any:
    i = argv.index(flag) if flag in argv else -1
    return (argv[i + 1] if i + 1 < len(argv) else js.UNDEFINED) if i >= 0 else None


def with_queued(shown: str, classified: list[dict], me: dict) -> str:
    """A delivery, and below it a line for each REQUEST to this login it put
    on the job list (intake.py). After the journal and the acknowledgement:
    a job the list could not take is a line on stderr, never an unshown message."""
    lines = intake.queue_received(classified, me)
    return shown + "".join(f"\n{x}" for x in lines)


def main(argv: list[str]) -> int:
    wait_given = "--wait" in argv
    follow = "--follow" in argv
    replay_given = "--replay" in argv
    replay_which = _arg_after(argv, "--replay")
    history_given = "--history" in argv
    history_arg = _arg_after(argv, "--history")
    history_from = js.number(history_arg) if history_given and history_arg is not js.UNDEFINED \
        and not history_arg.startswith("--") else None
    wait_total = 0.0
    if wait_given:
        n = js.number(_arg_after(argv, "--wait"))
        wait_total = n if js.truthy_number(n) else 1800.0
    # Who this session is (the login) and which project it works in — the
    # second selects the integration: relay, channel, where the token and
    # runtime live, in the project's WORKING COPY.
    who = gzmsg.whoami()
    # From here every line is this login's: English, or the locale its name
    # ends in when that locale has an active dictionary (i18n).
    t = i18n.t_for(who)
    reminder = i18n.locale_reminder(who)
    # --keyword K, validated BEFORE the arm starts (a bad one refused at arm
    # time costs nothing), after `t` so the refusal reads in the login's
    # language (blind review F3 on PR #28).
    keywords = check_keywords([argv[i + 1] if i + 1 < len(argv) else js.UNDEFINED
                               for i, a in enumerate(argv) if a == "--keyword"], t)
    if replay_given and not replay_which:
        print(t("replay.usage"), file=sys.stderr)
        return 1
    if history_given and history_from is not None and not js.is_integer(history_from):
        print(t("history.usage"), file=sys.stderr)
        return 1
    if "--held" in argv:
        h = hold_status(t=t)
        unknown = t("held.unknown")
        if h["held"]:
            sessions = ", ".join(t("held.session", {"session": x["session_id"] if x["session_id"] is not None else unknown,
                                                    "pid": x["pid"],
                                                    "since": x["since"] if x["since"] is not None else unknown})
                                 for x in h["sessions"])
            print(t("held.held", {"agent": who["agent"], "sessions": sessions}))
        else:
            print(t("held.not-held", {"reason": h["reason"]}))
        return 0 if h["held"] else 1
    root = inbox_root(who)
    cfg = integration_config(who.get("project"), os.environ, t)
    # Not configured is not an error at a session start, and not a guess.
    if not cfg["configured"]:
        print(t("start.skipping", {"reason": cfg["reason"]}), file=sys.stderr)
        return 0
    try:
        assert_not_control_channel(cfg["channel"], t)
    except ControlChannel as e:
        print(t("start.error", {"detail": str(e)}), file=sys.stderr)
        return 2
    relay_url, channel = cfg["relay_url"], cfg["channel"]
    # What this session owns first: the hosting working copy starts its
    # relay here, so a session restart is also the relay's.
    up = ensure_relay(relay_runtime_dir(cfg), relay_url, t)
    if up.get("started"):
        print(t("start.relay-started-unit", {"unit": up["unit"]}) if up.get("unit")
              else t("start.relay-started-pid", {"pid": up.get("pid")}), file=sys.stderr)
    elif up.get("note"):
        print(t("start.error", {"detail": up["note"]}), file=sys.stderr)
    tok = token(root, cfg)
    if not tok:
        print(t("start.no-token", {"token_file": cfg["token_env_file"] if cfg.get("token_env_file") is not None
                                   else t("config.no-token-file")}), file=sys.stderr)
        return 0
    tax_path = gzmsg.find_taxonomy(root)
    taxonomy = gzmsg.load_taxonomy(tax_path) if tax_path else None
    me = identity(who, taxonomy)
    if me.get("roleError"):
        print(t("start.error", {"detail": me["roleError"]}), file=sys.stderr)
    state = {"tok": tok}

    def with_fresh_token(fn: Callable[[str], Any]) -> Any:
        """Once: a refused token is retried with the synced file's value
        when that differs from what the environment carried."""
        try:
            return fn(state["tok"])
        except RelayError as e:
            fresh = synced_token() if e.status in (401, 403) else None
            if fresh and fresh != state["tok"]:
                state["tok"] = fresh
                print(t("start.token-retry"), file=sys.stderr)
                return fn(state["tok"])
            raise

    if history_given:
        try:
            return with_fresh_token(lambda tk: history(tk, relay_url, channel, history_from, me, t))
        except Exception as e:  # noqa: BLE001 — any failure of the read is the relay's line
            x = explain_relay_error(e, relay_url, t)
            print(x["line"], file=sys.stderr)
            return x["code"] or 1
    if replay_which:
        try:
            return with_fresh_token(lambda tk: replay(tk, relay_url, channel, replay_which, me, t, "--json" in argv))
        except Exception as e:  # noqa: BLE001
            x = explain_relay_error(e, relay_url, t)
            print(x["line"], file=sys.stderr)
            return x["code"] or 1

    # Drain mode spends 1 s on the cursor page and lists everything; wait
    # mode chains slices until a message ADDRESSED TO THIS SESSION lands,
    # passing others' traffic through acknowledged and unprinted.
    def ack(message_id: Any) -> Any:
        return api(state["tok"], "/api/ack", relay_url, method="POST",
                   body=js.stringify({"consumer_id": me["address"], "channel": channel, "message_id": message_id}))

    def fetch_page(slice_: float, abort: threading.Event) -> Any:
        q = urllib.parse.urlencode({"channel": channel, "consumer_id": me["address"],
                                    "timeout_seconds": js.string(slice_), "limit": "50"})
        return api(state["tok"], f"/api/wait?{q}", relay_url, timeout=slice_ + API_TIMEOUT)

    def held() -> bool:
        return hold_status(t=t)["held"]

    # Each key literally beside its t(: the i18n suite reads the source for
    # them, and a key built in an expression is one its guard cannot see.
    def on_hold(h: bool) -> None:
        print(t("watch.held") if h else t("watch.hold-released"), file=sys.stderr, flush=True)

    off = bypass.is_off()
    journal = bypass_inbound if off else (lambda recs: journal_inbound(recs, who))
    cause = {"reason": None}

    def on_journal_fail(reason: str, n: int) -> None:
        # The journal speaks for itself, untranslated, on stdout in the
        # watch, so the held messages reach the session.
        if reason == cause["reason"]:
            return
        cause["reason"] = reason
        if off:
            print(f"gzcoord: {n} message(s) addressed to you are held, not shown: {reason}; the journal is"
                  " bypassed only with a record of it, and they are shown once it can be written (ADR-041)",
                  flush=True)
            return
        print(f"gzcoord: {n} message(s) addressed to you are held, not shown: your journal could not keep them"
              f" ({reason}); they are shown once it can (ADR-041), or with GZCOORD_JOURNAL=off", flush=True)

    def fetch_recent(_done: threading.Event) -> Any:
        return api(state["tok"], "/api/messages?" + urllib.parse.urlencode(
            {"channel": channel, "limit": str(HISTORY_WINDOW), "full": "1"}), relay_url,
            timeout=RETRANSMISSION_LOOKUP_MS / 1000)

    def mine_fn(msg: dict) -> bool:
        return for_me(msg, me)

    if follow:
        # The watch. Each arm waits an hour of slices; a delivery is printed
        # and the next arm starts at once; a quiet hour starts the next arm
        # silently. Transport trouble is one line each way; a refused token
        # ends the watch with exit 4 so the harness reports it once.
        down = False
        while True:
            try:
                r = with_fresh_token(lambda _tk: wait_loop(fetch_page, ack, 3600, mine_fn, [], me["address"], held,
                                                           on_hold, journal=journal, on_journal_fail=on_journal_fail))
            except Exception as e:  # noqa: BLE001 — every failure of an arm is the relay's, said once
                x = explain_relay_error(e, relay_url, t)
                if x["code"] == 4:
                    print(x["line"], file=sys.stderr)
                    return 4
                if not down:
                    print(t("watch.relay-down", {"relay_url": relay_url}), flush=True)
                    down = True
                time.sleep(30)
                continue
            if down:
                print(t("watch.relay-back"), flush=True)
                down = False
            if r["delivered"]:
                cause["reason"] = None
                mark_retransmissions(r["classified"], fetch_recent)
                print(with_queued(render(r, me, channel, taxonomy, cap=NOTIFICATION_CAP, t=t, reminder=reminder),
                                  r["classified"], me), flush=True)

    try:
        res = with_fresh_token(lambda _tk: wait_loop(fetch_page, ack, wait_total, mine_fn, keywords, me["address"],
                                                     journal=journal, on_journal_fail=on_journal_fail))
    except Exception as e:  # noqa: BLE001
        x = explain_relay_error(e, relay_url, t)
        print(x["line"], file=sys.stderr)
        return x["code"]
    if res.get("keywordHit") and wait_given:
        hit = res["keywordHit"]
        m = next((c for c in res["classified"] if c["rec"].get("id") == hit.get("id")), None)
        print(t("keyword.hit", {"channel": channel, "keywords": ", ".join(keywords)}))
        print(f"  {one_line(m['msg'], t) if m and m.get('msg') else t('keyword.unparsable', {'id': js.get(hit, 'id'), 'sender': js.get(hit, 'sender')})}")
        raise _Exit(3)
    if not res["delivered"] and wait_given:
        print(t("wait.nothing", {"channel": channel, "waited": res["waited"], "others_passed": res["othersPassed"]}))
    if not res["delivered"]:
        return 0
    mark_retransmissions(res["classified"], fetch_recent)
    print(with_queued(render(res, me, channel, taxonomy, t=t, reminder=reminder), res["classified"], me))
    # The cursor is already past everything shown: wait_loop acknowledges
    # every slice it sees, delivered or passed.
    return 0


def run(argv: list[str]) -> int:
    """The command: main(), with the Node's last resort — NOT through the
    dictionary, since what failed may BE the dictionary — one line and exit
    0, on a path whose whole contract is one line and exit 0 (blind review
    F1 on PR #28)."""
    try:
        return main(argv)
    except _Exit as e:
        return e.code
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001 — the contract's last resort
        print(f"gzcoord inbox: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
