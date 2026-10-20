#!/usr/bin/env python3
"""gh_ledger and its use in gh.run: every call the fabric makes to GitHub is
recorded (who asked, which call, how it ended), a rate-limited call says when
the limit ends instead of "could not read", and a poller can ask how long to
wait. Against a fake `gh` on PATH, with the state directory in a scratch
directory: nothing here reaches GitHub or this login's real ledger."""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
import gh_ledger  # noqa: E402

# The fake answers `api rate_limit` from $FAKE_RATE (a JSON file), refuses
# `api limited/*` as GitHub does on the primary limit and `api secondary/*` as
# on a secondary one, 404s `api missing/*`, and prints `{}` for any other call.
# Every call's argv is appended to $FAKE_LOG.
FAKE = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
if [[ "$1 $2" == "api -i" ]]; then
  # A conditional list read: 304 when the validator is the current one.
  etag="$(cat "$FAKE_ETAG")"
  if [[ "$*" == *"If-None-Match: $etag"* ]]; then
    if [[ -e "$FAKE_304_AS_ERROR" ]]; then echo "gh: HTTP 304" >&2; exit 1; fi
    printf 'HTTP/2.0 304 Not Modified\r\nEtag: %s\r\n\r\n' "$etag"; exit 0
  fi
  printf 'HTTP/2.0 200 OK\r\nEtag: %s\r\nContent-Type: application/json\r\n' "$etag"
  [[ -e "$FAKE_NEXT" ]] && printf 'Link: <https://api.github.com/x?page=2>; rel="next"\r\n'
  printf '\r\n'; cat "$FAKE_ITEMS"; exit 0
fi
case "$1 $2" in
  "api rate_limit") cat "$FAKE_RATE" ;;
  "api repos/o/r/lists/"*) echo '[[{"n":1}],[{"n":2}]]' ;;
  "api limited/"*) echo "gh: API rate limit exceeded for user ID 1. (HTTP 403)" >&2; exit 1 ;;
  "api secondary/"*) echo "gh: You have exceeded a secondary rate limit. (HTTP 403)" >&2; exit 1 ;;
  "api missing/"*) echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
  *) echo '{}' ;;
esac
'''
NOW = 1_800_000_000.0
RESET = NOW + 600


def rate(core_remaining: int) -> str:
    return json.dumps({"resources": {"core": {"limit": 5000, "remaining": core_remaining, "reset": int(RESET),
                                              "used": 5000 - core_remaining},
                                     "graphql": {"limit": 5000, "remaining": 4000, "reset": int(RESET), "used": 1000}}})


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good or not detail else f"\n        {detail}"))
        fails += not good

    FAKE_ENV = ("FAKE_ETAG", "FAKE_ITEMS", "FAKE_NEXT", "FAKE_304_AS_ERROR")
    saved = {k: os.environ.get(k) for k in ("PATH", "AGENT_FABRIC_STATE_DIR", "FAKE_LOG", "FAKE_RATE", "GH_REPO", *FAKE_ENV)}
    with tempfile.TemporaryDirectory() as tmp:
        bindir = os.path.join(tmp, "bin")
        os.mkdir(bindir)
        fake = os.path.join(bindir, "gh")
        with open(fake, "w") as fh:
            fh.write(FAKE)
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
        log, ratefile, state = (os.path.join(tmp, n) for n in ("calls.log", "rate.json", "state"))
        os.environ.update(PATH=bindir + os.pathsep + os.environ["PATH"], AGENT_FABRIC_STATE_DIR=state, FAKE_LOG=log,
                          FAKE_RATE=ratefile, GH_REPO="o/r")
        etag, items, nxt, as_err = (os.path.join(tmp, n) for n in ("etag", "items.json", "next", "304-as-error"))
        os.environ.update(FAKE_ETAG=etag, FAKE_ITEMS=items, FAKE_NEXT=nxt, FAKE_304_AS_ERROR=as_err)

        def rows() -> list[dict]:
            path = os.path.join(gh_ledger.state_dir(), gh_ledger.LEDGER)
            try:
                return [json.loads(l) for l in open(path)]
            except OSError:
                return []

        def fake_calls() -> list[str]:
            try:
                return open(log).read().splitlines()
            except OSError:
                return []

        open(ratefile, "w").write(rate(4000))

        print("the ledger: one line per call")
        gh.api("repos/o/r/pulls/7/reviews")
        got = rows()
        check("a successful call is one line", len(got) == 1, str(got))
        row = got[0] if got else {}
        check("…naming the caller module, the transport and the call with its numbers collapsed",
              row.get("caller") == "test_gh_ledger" and row.get("kind") == "rest"
              and row.get("call") == "api GET repos/o/r/pulls/N/reviews" and row.get("status") == "ok", str(row))
        gh.graphql("query { viewer { login } }")
        gh.pr_view(7, ["number"], repo="o/r")
        got = rows()
        check("a graphql query and a pr view are graphql",
              [r["kind"] for r in got[1:]] == ["graphql", "graphql"], str(got[1:]))
        try:
            gh.api("missing/x")
        except gh.GhError:
            pass
        check("a refused call records the HTTP status it ended with", rows()[-1]["status"] == 404, str(rows()[-1]))

        print("a rate-limited call says when the limit ends")
        open(ratefile, "w").write(rate(0))
        try:
            gh.api("limited/x")
            e = None
        except gh.GhError as err:
            e = err
        want = f"rate limited until {gh_ledger.reset_at(RESET)}"
        check("the reason is the reset time, not gh's text", e is not None and e.reason == want, str(e and e.reason))
        check("…transient, with the reset epoch for a poller", e is not None and e.transient and e.reset == int(RESET),
              str(e and (e.transient, e.reset)))
        open(ratefile, "w").write(rate(3000))
        try:
            gh.api("secondary/x")
            e = None
        except gh.GhError as err:
            e = err
        check("a secondary limit (budget not spent) is not given a reset time",
              e is not None and "secondary" in e.reason and e.reset is None, str(e and e.reason))
        try:
            gh.api("missing/x")
            e = None
        except gh.GhError as err:
            e = err
        check("(control) a plain 404 keeps gh's own reason and is not transient",
              e is not None and e.reason == "gh: Not Found (HTTP 404)" and not e.transient and e.reset is None, str(e and e.reason))

        print("the budget")
        open(ratefile, "w").write(rate(4000))
        os.remove(os.path.join(gh_ledger.state_dir(), gh_ledger.RATE))
        before = len(fake_calls())
        gh_ledger.rate_limit(max_age=30, now=lambda: NOW)
        gh_ledger.rate_limit(max_age=30, now=lambda: NOW + 5)
        asked = [c for c in fake_calls()[before:] if c == "api rate_limit"]
        check("a snapshot younger than max_age answers without a second call", len(asked) == 1, str(asked))
        gh_ledger.rate_limit(max_age=30, now=lambda: NOW + 100)
        asked = [c for c in fake_calls()[before:] if c == "api rate_limit"]
        check("…an older one is read again", len(asked) == 2, str(asked))
        check("the rate_limit read is recorded as free",
              {r["kind"] for r in rows() if r["call"] == "api rate_limit"} == {"free"},
              str([r for r in rows() if r["call"] == "api rate_limit"]))
        res = json.loads(rate(4000))["resources"]
        check("plenty left: no wait", gh_ledger.wait_seconds(now=lambda: NOW, resources=res) == 0)
        res = json.loads(rate(50))["resources"]
        check("below the floor: wait until the reset (and a second past it)",
              gh_ledger.wait_seconds(now=lambda: NOW, resources=res) == 601.0)
        res = json.loads(rate(0))["resources"]
        check("exhausted: the same", gh_ledger.wait_seconds(now=lambda: NOW + 100, resources=res) == 501.0)
        check("an unreadable budget is no wait, never a guess",
              gh_ledger.wait_seconds(resources={}) == 0 and gh_ledger.wait_seconds(resources={"core": {"remaining": "x"}}) == 0)

        print("a list read that polls cheaply")
        open(etag, "w").write('W/"a"')
        open(items, "w").write('[{"id": 1}]')

        def listing() -> tuple[list, int, list[dict]]:
            before_rows = len(rows())
            before_calls = len(fake_calls())
            got_items = gh.api_list("repos/o/r/pulls/7/reviews")
            return got_items, len(fake_calls()) - before_calls, rows()[before_rows:]

        got, n, new = listing()
        check("the first read is full, and asks for 100 a page", got == [{"id": 1}] and n == 1
              and "per_page=100" in fake_calls()[-1] and "If-None-Match" not in fake_calls()[-1], str(fake_calls()[-1:]))
        got, n, new = listing()
        check("the second sends the validator and a 304 answers from the cache",
              got == [{"id": 1}] and 'If-None-Match: W/"a"' in fake_calls()[-1], str(fake_calls()[-1:]))
        check("…recorded as a free call with status 304, so the summary does not count it as spend",
              [(r["kind"], r["status"]) for r in new] == [("free", 304)], str(new))
        open(etag, "w").write('W/"b"')
        open(items, "w").write('[{"id": 1}, {"id": 2}]')
        got, n, new = listing()
        check("a changed list is read in full (control: the 304 path is not a stuck cache)",
              got == [{"id": 1}, {"id": 2}] and [r["status"] for r in new] == ["ok"], str((got, new)))
        got, n, new = listing()
        check("…and is then the cached one", got == [{"id": 1}, {"id": 2}] and [r["status"] for r in new] == [304], str(new))
        open(as_err, "w").write("")
        got, n, new = listing()
        check("a gh that reports the 304 as an error is the same answer", got == [{"id": 1}, {"id": 2}], str(got))
        os.remove(as_err)
        cachefile = gh._etag_file("repos/o/r/pulls/7/reviews?per_page=100")
        open(cachefile, "w").write("{damaged")
        got, n, new = listing()
        check("a damaged cache is a full read, not an error", got == [{"id": 1}, {"id": 2}] and "If-None-Match" not in fake_calls()[-1],
              str(fake_calls()[-1:]))
        open(nxt, "w").write("")
        got = gh.api_list("repos/o/r/lists/x")
        check("a first page with a next link is read in full, page by page", got == [{"n": 1}, {"n": 2}], str(got))
        check("…and not cached: page one's validator says nothing of page two",
              not os.path.exists(gh._etag_file("repos/o/r/lists/x?per_page=100")))
        os.remove(nxt)

        print("the ledger is telemetry")
        blocked = os.path.join(tmp, "a-file")
        open(blocked, "w").write("x")
        os.environ["AGENT_FABRIC_STATE_DIR"] = blocked
        try:
            out = gh.api("repos/o/r/pulls/9")
        except Exception as ex:  # noqa: BLE001 — the point is that nothing escapes
            out = f"raised {ex!r}"
        check("a state directory that cannot be written never fails the call", out == {}, str(out))
        os.environ["AGENT_FABRIC_STATE_DIR"] = state

        print("the pace between looks")
        import poll_pace
        pace = poll_pace.Pace(30)
        got = [pace.nap(i == 0) for i in range(9)]
        check("an unchanged reading grows the wait by half, to five minutes and no further",
              got == [30, 45, 68, 101, 152, 228, 300, 300, 300], str(got))
        check("a change falls back to the interval", pace.nap(True) == 30 and pace.nap(False) == 45)
        check("a limit that ended is no wait; one still on is the seconds to its reset and a second",
              poll_pace.until_reset(NOW - 5, NOW) is None and poll_pace.until_reset(NOW + 599, NOW) == 600
              and poll_pace.until_reset(None, NOW) is None)

        print("the summary")
        text = gh_ledger.summarize(gh_ledger.read_ledger(3600, now=time.time), calls=True)
        check("per caller, rest and graphql counted apart",
              "test_gh_ledger" in text and "total" in text and "api GET repos/N/N/pulls/N/reviews" not in text.split("total")[0],
              text)
        check("--calls lists each distinct call", "api GET repos/o/r/pulls/N/reviews" in text, text)
        check("a window with nothing says so", gh_ledger.summarize([]) == "no gh calls recorded in that window")
        with open(os.path.join(gh_ledger.state_dir(), gh_ledger.LEDGER), "a") as fh:
            fh.write("not json\n")
        check("a malformed ledger line is skipped, not fatal", len(gh_ledger.read_ledger(3600)) >= 4)

    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    print("\nall passed" if not fails else f"\ntest_gh_ledger: {fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
