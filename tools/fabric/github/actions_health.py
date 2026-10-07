#!/usr/bin/env python3
"""runtime/github/actions-health.sh

Is it worth spending CI minutes right now?

Answers in one line and one exit code, before you push, re-run, or
re-trigger anything. It exists because on 2026-08-06 two PRs were
re-run into a GitHub Actions outage that had already been declared —
every job died in "Set up job" or was cancelled with zero steps, and
the only thing that changed was the clock.

It checks the two things that make a run pointless and that the PR
itself cannot tell you:

  * the Actions component on githubstatus.com — unauthenticated, so it
    answers even when the token is the problem;
  * whether the INCLUDED Actions allowance is already spent.

    The billing API reports usage, never the plan's limit, so the limit
    is CONFIGURED, not discovered: $AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES,
    set in .claude/settings.json (or --included N, or the environment).
    A project's forwarder may map its own setting onto it, and name that
    setting in AGENT_FABRIC_ACTIONS_INCLUDED_SETTING, which is the name
    the lines below tell a person to set. No plan size is hardcoded —
    the number lives in that one setting, and changing plan means
    changing it there.

    With the setting present this reports the exact remaining minutes.
    Without it, the allowance size is unknown and the script says so
    rather than guessing: usage alone cannot tell you how much is left.

    netAmount is read too, but it decides the KIND of answer, never the
    block on its own. Money moving means overage is being purchased,
    which is a plan still handing out runners — the plan that stops is
    the one that never bills, where net stays 0 while every job dies.
    So a hard block needs usage past the allowance AND nothing billed;
    usage past the allowance WITH billing is reported as a cost.

Deliberately NOT wired into anything automatically. A network call on
every push would cost more, in latency and in noise, than the rare
outage it guards against. This is a thing you run when CI is behaving
oddly, or before a deliberately expensive action — a full re-run, a
queue re-trigger, a big fan-out.

Usage:
  runtime/github/actions-health.sh              # this repo's owner
  runtime/github/actions-health.sh --org NAME   # explicit owner
  runtime/github/actions-health.sh --quiet      # exit code only
  runtime/github/actions-health.sh --included N # override the configured allowance
  runtime/github/actions-health.sh --json       # one JSON object instead of the line

--json prints, whatever --quiet says, one object on stdout:
  {exit, verdict, reason, public, period, private_minutes, private_net,
   own_net, included, remaining, status, incident}
verdict is ok, degraded, unknown (neither source read) or invalid (a
bad allowance); reason is the line, or the refusal without its prefix;
status is the Actions component's status on githubstatus.com
("operational", "major_outage", ...), and incident the incident name the
outage reason quotes; a value not read or not applicable is null. A usage error is stderr
alone.

Exit codes:
  0  healthy — Actions operational and the allowance not exhausted,
     or this repository is public and none of its own minutes bill
  1  degraded — spending minutes now is wasted or costly (reason on stdout)
  2  invocation problem, or neither source could be read

The distinction between 1 and 2 matters: 1 is a fact about GitHub, 2 is
"this script could not find out", and treating the second as the first
would stop work for no reason.
"""
# The docstring is --help, whole. Ported from a managed project's
# tools/gh/actions-health.sh (its test the oracle, ported case for case to
# tests/test_actions_health_cli.py). Its lines are the bash's byte for
# byte; departures, each a parse failure the bash turned into a plausible
# number: a billing answer that is not a JSON object, or a minute row
# whose quantity or netAmount is not a number, is unreadable (the bash
# summed it as 0); a billing call gh reports failed is unreadable even
# when it printed an error body (the bash read the body as no usage); an
# allowance must be a positive decimal number in ASCII digits (awk read
# "3000abc" as 3000). An error nothing here foresaw is exit 2 with its
# reason: 1 is a fact about GitHub, and a crash is not one. Beyond that: --json; jq is not needed;
# every call is bounded.
from __future__ import annotations

import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402

STATUS_URL = "https://www.githubstatus.com/api/v2/summary.json"
SETTING = "AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES"
NUMBER = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")


class Usage(Exception):
    """A bad command line, or a bad allowance: the message, exit 2. A bad
    command line is stderr alone; an allowance is judged once the line
    parsed, so --json says it too, as verdict invalid."""


def jqnum(x: float | int) -> str:
    """A number as jq prints it: an integral value without its .0."""
    if isinstance(x, float) and x.is_integer() and abs(x) < 1e17:
        return str(int(x))
    return repr(x) if isinstance(x, float) else str(x)


def plain(x):
    """A number for --json as the line prints it: 3220, not 3220.0."""
    return int(x) if isinstance(x, float) and x.is_integer() and abs(x) < 1e17 else x


def finite(value: float | int) -> float | int:
    """`value`, or ValueError when a double cannot hold it: NaN, an
    infinity, or an integer past a double's range (whose float() raises
    OverflowError, not ValueError)."""
    try:
        as_float = float(value)
    except OverflowError:
        raise ValueError(f"{value!r:.40} is past a double's range") from None
    if not math.isfinite(as_float):
        raise ValueError(f"{value!r} is not finite")
    return value


def as_number(text: str) -> float | int:
    """An allowance NUMBER matched, as a finite number, or ValueError."""
    return finite(int(text) if "." not in text else float(text))


def parse(argv: list[str], env) -> dict | None:
    opts = {"org": "", "quiet": False, "json": False, "included": env.get(SETTING, "")}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--org", "--included"):
            value = argv[i + 1] if i + 1 < len(argv) else ""
            if not value:
                raise Usage(f"{a} needs a value")
            opts[a[2:]] = value
            i += 2
            continue
        if a == "--quiet":
            opts["quiet"] = True
        elif a == "--json":
            opts["json"] = True
        elif a in ("-h", "--help"):
            sys.stdout.write(__doc__)
            return None
        else:
            raise Usage(f"unknown option: {a} (try --help)")
        i += 1
    return opts


def actions_status() -> tuple[str, str] | None:
    """(status, first incident) from githubstatus.com, or None when it
    was not read: curl missing or failing, or a body that is not the
    summary with an Actions component. REACHED IS NOT THE SAME AS
    UNDERSTOOD: a captive-portal page, a proxy error, a version bump
    that moved the component parse to nothing, and a script that had
    learned nothing must not report "Actions operational"."""
    if shutil.which("curl") is None:
        return None
    try:
        r = subprocess.run(["curl", "-fsS", "--max-time", "10", STATUS_URL], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    try:
        summary = json.loads(r.stdout)
    except ValueError:
        return None
    if not isinstance(summary, dict):
        return None
    comps = summary.get("components")
    status = next((c.get("status") for c in _items(comps) if isinstance(c, dict) and c.get("name") == "Actions"), None)
    if not isinstance(status, str) or not status:
        return None
    incident = next((x.get("name") for x in _items(summary.get("incidents")) if isinstance(x, dict)), None)
    return _text(status), _text(incident) if isinstance(incident, str) else ""


_SURROGATE = re.compile("[\ud800-\udfff]")


def _text(s: str) -> str:
    """A lone surrogate (a "\\ud800" escape json.loads accepts) as U+FFFD,
    as jq printed it: left in, it fails the print, a crash whose exit 1
    would say "degraded"."""
    return _SURROGATE.sub("\ufffd", s)


def _items(v) -> list:
    """jq's `.[]?`: an array's items, an object's values, else nothing."""
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return list(v.values())
    return []


def _gh_text(args: list[str]) -> str:
    """gh's answer, trimmed, or '' when it failed: what `$(gh … || true)` held."""
    try:
        return gh.run(args).rstrip("\n")
    except gh.GhError:
        return ""


def _in_period(row: dict, period: str) -> bool:
    """The row bills for the period. A row with no date counts: the filter
    excludes OTHER months, it does not demand a field older payloads lack."""
    date = row.get("date")
    if date is None or date is False:   # jq's `.date // $p`
        return True
    text = jqnum(date) if isinstance(date, (int, float)) and not isinstance(date, bool) else (
        date if isinstance(date, str) else json.dumps(date, separators=(",", ":")))
    return text[:7] == period


def _minute_rows(usage: dict, period: str) -> list[dict]:
    # THE MINUTE SKU, not every Actions charge: billed Actions STORAGE
    # read as "runner overage is being paid for" while minute runners had
    # actually stopped.
    return [r for r in _items(usage.get("usageItems")) if isinstance(r, dict) and r.get("product") == "actions"
            and r.get("unitType") == "Minutes" and _in_period(r, period)]


def _sum(rows: list[dict], key: str) -> float | int:
    total: float | int = 0
    for r in rows:
        v = r.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"a minute row's {key} is not a number")
        total += finite(v)
    # Rows each finite can still sum past a double.
    return finite(total)


def private_repos(org: str, usage: dict) -> set[str]:
    """The repositories in the payload that are PRIVATE — the only ones
    whose minutes count toward the included allowance. One lookup per
    distinct repositoryName; a lookup that fails keeps the repository
    (counted — the conservative side). Bare ("app") as an organisation's
    payload sends it, or owner-qualified ("org/app") as GitHub's
    documentation shows: the lookup takes either, and the set keeps the
    name as sent."""
    names = sorted({r["repositoryName"] for r in _items(usage.get("usageItems"))
                    if isinstance(r, dict) and r.get("product") == "actions"
                    and isinstance(r.get("repositoryName"), str) and r["repositoryName"]})
    private = set()
    for name in names:
        bare = name[len(org) + 1:] if name.startswith(f"{org}/") else name
        if _gh_text(["api", f"repos/{org}/{bare}", "--jq", ".private"]) != "false":
            private.add(name)
    return private


def check(opts: dict, env, page: dict | None = None) -> tuple[int, str, dict]:
    """(exit, line, the --json fields). The checks in the bash's order.
    `page` receives status and incident as soon as the status page is
    read, so a later failure does not report a page that was read as
    unread."""
    setting = env.get("AGENT_FABRIC_ACTIONS_INCLUDED_SETTING") or SETTING
    included_text = opts["included"]
    fields: dict = {"public": None, "period": None, "private_minutes": None, "private_net": None,
                    "own_net": None, "included": None, "remaining": None, "status": None, "incident": None}
    page = {} if page is None else page
    # A bad allowance is an invocation problem (exit 2) whatever the network
    # says, so it is judged before any call: validated only once billing had
    # answered, it vanished behind every earlier exit — an unreadable billing
    # API, or a public repository's OK line.
    included = None
    if included_text:
        try:
            included = as_number(included_text) if NUMBER.fullmatch(included_text) else 0
        except ValueError:
            included = 0
        if included <= 0:
            raise Usage(f"{setting} must be a positive number, got '{included_text}'")
        fields["included"] = plain(included)
    reachable = False
    # What the OK lines are entitled to claim. Only source 1 can confirm the
    # platform is up, so every "operational" below is downgraded to an
    # admission when it did not answer — a billing read tells you what you
    # have spent, never whether runners are starting.
    ops_phrase = "Actions status unverified (githubstatus.com unreadable)"

    # ── 1. Is Actions up? ───────────────────────────────────────────────
    got = actions_status()
    if got is not None:
        status, incident = got
        reachable = True
        ops_phrase = "Actions operational"
        fields["status"] = page["status"] = status
        if status != "operational":
            # A program reads the incident here rather than cut it out of
            # the reason, whose wording may change.
            fields["incident"] = page["incident"] = incident or None
            # Name the incident too — "major_outage" alone does not say
            # whether anyone is working on it.
            return 1, (f"DEGRADED — GitHub Actions is {status}{f' ({incident})' if incident else ''}. "
                       "Runs will fail or never start; do not spend minutes."), fields

    # ── 2. Is the included allowance spent? ─────────────────────────────
    public = False
    if shutil.which("gh") is not None:
        # The working copy speaks for a run only in its own organisation: an
        # --org naming another owner asks about that owner's allowance.
        copy_org = _gh_text(["repo", "view", "--json", "owner", "-q", ".owner.login"])
        org = opts["org"] or copy_org
        if org:
            # THE CURRENT BILLING MONTH, and only it: after a rollover the
            # endpoint returns last month's rows beside this month's, and a
            # sum across both read the allowance 80 percent spent when it
            # was half. The request names the month (UTC, as the billing
            # dates are), and the sum keeps only rows dated in it, so a
            # server that ignored the parameters could not put it back.
            now = datetime.datetime.now(datetime.timezone.utc)
            period = now.strftime("%Y-%m")
            fields["period"] = period
            # THIS REPOSITORY'S VISIBILITY decides whether billing can say
            # anything about a run here. A public repository's runs on
            # standard GitHub-hosted runners bill nothing and draw on no
            # allowance, so the organisation's spend is context, never a
            # reason to hold a run there: a copy of this script once held a
            # reviewed PR on "$87 billing as overage" while its run billed
            # 0 ms (2026-10-06). A visibility that cannot be read is
            # private, the conservative side.
            public = org == copy_org and _gh_text(["repo", "view", "--json", "isPrivate", "-q", ".isPrivate"]) == "false"
            fields["public"] = public
            me = _gh_text(["repo", "view", "--json", "name", "-q", ".name"])
            try:
                usage = gh.api(f"/organizations/{org}/settings/billing/usage?year={now.year}&month={now.month}")
            except gh.GhError:
                usage = None
            if isinstance(usage, dict):
                reachable = True
                try:
                    # PRIVATE repositories only. A public repository's
                    # minutes are free and ride in the same payload; summed
                    # in, they read as allowance spent while every job runs
                    # (51 049 of 50 000 reported on 2026-09-18, the private
                    # repositories at 42 406). A row with no repositoryName
                    # counts (older payloads).
                    priv = private_repos(org, usage)
                    rows = [r for r in _minute_rows(usage, period)
                            if r.get("repositoryName") is None or r.get("repositoryName") in priv]
                    net, mins = _sum(rows, "netAmount"), _sum(rows, "quantity")
                    own = [r for r in _minute_rows(usage, period)
                           if me and r.get("repositoryName") in (me, f"{org}/{me}")]
                    selfnet = _sum(own, "netAmount") if public else None
                except ValueError:
                    reachable = got is not None
                    usage = None
            if isinstance(usage, dict):
                fields["private_minutes"], fields["private_net"] = plain(mins), plain(net)
                fields["own_net"] = plain(selfnet)
                # A NONZERO net IS NOT A BLOCK: money moving proves runs are
                # still being served; the plan that blocks is the one that
                # never bills, where net stays 0 while every job dies.
                billed = net > 0
                if public:
                    # The allowance does not apply to a run here, but its
                    # OWN billed minutes do: a larger runner is charged in
                    # a public repository too. Decided on netAmount, not on
                    # sku names, which the live payload does not show for
                    # larger runners.
                    if selfnet > 0:
                        return 1, (f"DEGRADED — this repository is public, yet ${jqnum(selfnet)} of its own minutes "
                                   "bill this period: runners beyond the free standard ones are charged here too. "
                                   "Runs still start, so this blocks nothing; every further minute on them is "
                                   "money."), fields
                    # Its name unread, its own rows were never matched: say
                    # so rather than claim they bill nothing.
                    own_said = "none of its minutes bill" if me else "its own billing could not be checked (name unread)"
                    return 0, (f"OK — {ops_phrase}; this repository is public and {own_said}, so its runs on "
                               "standard runners cost nothing and draw on no allowance. (The organisation's "
                               f"private repositories: {jqnum(mins)} minutes this period"
                               f"{f', ${jqnum(net)} billing as overage' if billed else ''}.)"), fields
                if included is None:
                    # Billed minutes are DEGRADED even here: the remainder
                    # is unknown, the cost is not.
                    if billed:
                        return 1, (f"DEGRADED — {jqnum(mins)} minutes used this period and ${jqnum(net)} of it is "
                                   "billing as overage. Runs still start, so this blocks nothing; every further "
                                   f"minute is money. (Allowance size unknown: set {setting} in "
                                   ".claude/settings.json.)"), fields
                    return 0, (f"OK — {ops_phrase}; {jqnum(mins)} minutes used this period. (Remaining unknown: "
                               f"set {setting} in .claude/settings.json.)"), fields
                left = f"{included - mins:.0f}"
                fields["remaining"] = int(left)
                # BILLED IS DECIDED BEFORE THE REMAINDER IS CONSULTED: money
                # can move while the allowance has room (a separately
                # billable runner), and checking the remainder first fell
                # through to OK without saying every further minute costs.
                if billed:
                    if mins >= included:
                        return 1, (f"DEGRADED — past the included allowance ({jqnum(mins)} of {included_text} "
                                   f"minutes used) and ${jqnum(net)} is billing as overage. Runs still start, so "
                                   "this blocks nothing; every further minute is money."), fields
                    return 1, (f"DEGRADED — {jqnum(mins)} of {included_text} minutes used, so the general allowance "
                               f"has room, and yet ${jqnum(net)} of minutes is billing. Some usage is charged outside "
                               "that allowance. Runs still start, so this blocks nothing; every further minute is "
                               "money."), fields
                if mins >= included:
                    return 1, (f"DEGRADED — the included Actions allowance is spent ({jqnum(mins)} of "
                               f"{included_text} minutes used) and nothing is being billed, so this plan is not "
                               "buying overage. Jobs stop getting runners: they fail in seconds with no steps and "
                               "no logs. Nothing will merge until the period resets."), fields
                return 0, (f"OK — {ops_phrase}; {jqnum(mins)} of {included_text} minutes used this period, "
                           f"{left} remaining."), fields
    if not reachable:
        return 2, "could not read githubstatus.com or the billing API — health unknown", fields
    if public:
        return 0, (f"OK — {ops_phrase}; this repository is public, so its runs on standard runners cost nothing. "
                   "(Billing API unreadable: a larger runner's charges could not be checked.)"), fields
    return 0, f"OK — {ops_phrase}. (Allowance not checked: billing API unreadable.)", fields


def run(argv: list[str], env=None) -> int:
    env = os.environ if env is None else env
    try:
        opts = parse(argv, env)
    except Usage as e:
        print(f"actions-health: {e}", file=sys.stderr)
        return 2
    if opts is None:
        return 0
    page: dict = {}
    try:
        code, line, fields = check(opts, env, page)
    except Usage as e:
        code, line, fields = 2, str(e), None
    except Exception as e:  # noqa: BLE001 — never exit 1, which says GitHub is degraded
        code, line, fields = 2, f"could not decide ({type(e).__name__}: {e}) — health unknown", dict(page)
    verdict = {0: "ok", 1: "degraded"}.get(code) or ("invalid" if fields is None else "unknown")
    fields = fields or {}
    if code == 2:
        print(f"actions-health: {line}", file=sys.stderr)
    if opts["json"]:
        doc = {"exit": code, "verdict": verdict, "reason": line}
        for key in ("public", "period", "private_minutes", "private_net", "own_net", "included", "remaining",
                    "status", "incident"):
            doc[key] = fields.get(key)
        # Every number in it went through finite(): nothing here can fail.
        print(json.dumps(doc, ensure_ascii=False, allow_nan=False))
    elif code != 2 and not opts["quiet"]:
        print(line)
    return code


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
