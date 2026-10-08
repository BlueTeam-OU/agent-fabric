#!/usr/bin/env python3
"""bin/fabric-usage — the fleet's Claude usage windows, one line per placed
account, read by the coordinator through the host executor.

  fabric-usage                the fleet: every placement in runtime/hosts/registry.json
  fabric-usage <login>...     those accounts only
  fabric-usage --json         the same as JSON lines

Each account reads its OWN usage: the executor runs the read as that
login, in its home, and the account's OAuth token goes from its
credentials file into one request header and nowhere else — never to
a terminal, never to this output. What comes back is the utilisation
of the five-hour and seven-day windows, when each resets, and the
Claude account the login is signed into (email, from the harness's own
profile record, not a secret). A control-plane read: no message, no
session, no model in the loop (the CEO, 2026-09-17 — the first such
table was made by hand, and only the coordinator's login can make it).

An account with no credentials file, or whose read fails, gets one
line saying so; the table is never silently short. An account running
on a Claude-account template (CLAUDE_CODE_OAUTH_TOKEN in its synced
secrets.env) is `setup-token`: its own sign-in, if any, is another
account's, and the setup-token cannot read usage — the observer's
`fabric-ctl <observer> accounts` has those windows (docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md).

Superseded for everyday use by `bin/fabric-ctl all usage`, which asks
each account's control agent over the relay (docs/adr/ADR-029-the-control-plane-a-control-agent-per-account.md):
no sudo, no per-host loop, a second instead of a minute. This stays as
the fallback for a host whose daemons are down.
"""
# The contract the port keeps (ADR-040 Wave 3, from bin/fabric-usage):
#   - argv: --json anywhere; -h/--help prints the docstring's first six
#     lines, exit 0, where it is met; any other `--…` is exit 2 there;
#     everything else is a login to keep (a login no placement has is
#     simply not shown).
#   - the rows in the registry's placement order; the header line in text
#     mode only; a status row (setup-token, no-credentials, read-failed,
#     unreadable, executor-failed) for every account that has no numbers;
#     exit 0 once the table is out.
#   - the remote read is the shell text in READ, run as `sh -c` by the
#     executor as the account: it never leaves the account's own process,
#     and its token never reaches this one.
# Changed, and said in j31's delivery: a registry that cannot be read as
# a placement map is exit 2 (the bash printed an empty table, which its
# own header promises never to do); jq is no longer needed on this host
# (the remote read still uses jq and curl, as before); an executor that
# has not answered within EXECUTOR_TIMEOUT_S is `executor-failed` (the
# bash waited for ever; the executor is killed, and what it started as
# the account ends at curl's own 20 s bound); an executor that exits
# non-zero is `executor-failed` whatever it printed (the bash read its
# last line as the account's numbers); AGENT_FABRIC_HOSTEXEC names
# another executor, as store_enroll.py reads it, for a test.
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import roots  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
# A minute for curl's own bound (20 s) and the executor's sudo or ssh, twice.
EXECUTOR_TIMEOUT_S = 120
STATUSES = ("no-credentials", "read-failed", "unreadable", "executor-failed", "setup-token")

# The read, as the account. One line of tab-separated fields on stdout:
# email, five-hour %, five-hour reset, seven-day %, seven-day reset — or
# a reason in the first field when there is nothing to read. The token
# reaches curl as a header on its stdin (-H @-), never in its argv: an
# argument is readable by every account on the host in /proc/<pid>/cmdline
# for as long as curl runs (review of j31; the bash had it in argv).
READ = r"""grep -Eq "^export CLAUDE_CODE_OAUTH_TOKEN=[^'\"[:space:]]|^export CLAUDE_CODE_OAUTH_TOKEN='[^']" "$HOME/.config/agent-fabric/secrets.env" 2>/dev/null && { printf 'setup-token\n'; exit 0; }
f="$HOME/.claude/.credentials.json"
[ -s "$f" ] || { printf 'no-credentials\n'; exit 0; }
email="$(jq -r '.oauthAccount.emailAddress // "-"' "$HOME/.claude.json" 2>/dev/null || echo -)"
u="$(jq -r '"Authorization: Bearer " + .claudeAiOauth.accessToken' "$f" 2>/dev/null | curl -sS --max-time 20 -H @- -H "anthropic-beta: oauth-2025-04-20" https://api.anthropic.com/api/oauth/usage 2>/dev/null)" || { printf 'read-failed\t%s\n' "$email"; exit 0; }
printf '%s' "$u" | jq -r --arg e "$email" '[$e, (.five_hour.utilization // "-" | tostring), (.five_hour.resets_at // "-" | tostring | .[0:16]), (.seven_day.utilization // "-" | tostring), (.seven_day.resets_at // "-" | tostring | .[0:16])] | @tsv' 2>/dev/null || printf 'unreadable\t%s\n' "$email"
"""[:-1]  # the heredoc's text; `read -d ''` dropped its last newline


class Refused(Exception):
    """A command line or a registry this cannot use (exit 2)."""


def say(text: str) -> None:
    print(f"fabric-usage: {text}", file=sys.stderr)


def parse(argv: list[str]) -> tuple[bool, list[str]] | None:
    """(json, logins), or None when --help was met (and printed)."""
    as_json, logins = False, []
    for a in argv:
        if a == "--json":
            as_json = True
        elif a in ("-h", "--help"):
            sys.stdout.write("\n".join(__doc__.split("\n")[:6]) + "\n")
            return None
        elif a.startswith("--"):
            raise Refused(f"unknown option {a}")
        else:
            logins.append(a)
    return as_json, logins


def placements(registry: str) -> list[tuple[str, str]]:
    """(login, host, kind) for every placement, in the registry's order."""
    if not os.path.isfile(registry):
        raise Refused(f"no host registry at {registry}")
    try:
        with open(registry, encoding="utf-8") as fh:
            data = json.load(fh)
        placement, kinds = data.get("placement"), data.get("kinds") or {}
    except (OSError, ValueError, AttributeError) as e:
        raise Refused(f"the host registry at {registry} cannot be read: {e}") from None
    if not isinstance(placement, dict) or not all(isinstance(h, str) for h in placement.values()):
        raise Refused(f"the host registry at {registry} has no placement map of login to host")
    if not isinstance(kinds, dict):
        kinds = {}
    return [(l, h, kinds.get(l, "agent")) for l, h in placement.items()]


def last_line(out: str) -> str:
    """What `| tail -1` inside `$(…)` left: the last line, its newline gone."""
    return out.removesuffix("\n").rsplit("\n", 1)[-1]


def fields(line: str) -> list[str]:
    """`IFS=$'\\t' read -r a b c d e`, exactly: a tab is IFS whitespace, so
    runs of tabs are one separator and an edge tab is dropped (an empty
    field shifts the rest left, as it did); the fifth takes the remainder.
    Always five strings, the missing ones empty."""
    got = re.split(r"\t+", line.strip("\t"), maxsplit=4) if line.strip("\t") else []
    if len(got) == 5:
        got[4] = got[4].rstrip("\t")
    return got + [""] * (5 - len(got))


def number(text: str) -> int | float | None:
    """jq's `tonumber? // null`: a JSON number, else null."""
    try:
        value = json.loads(text)
    except ValueError:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def read_account(hx: str, host: str, login: str) -> str:
    """The read's last line, or '' when the executor failed or gave none.

    Every branch of READ exits 0 having printed its line, so a non-zero
    exit is the executor's failure or a read cut short, and whatever it
    printed is no answer."""
    try:
        r = subprocess.run([hx, host, "--as", login, "--", "sh", "-c", READ], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=EXECUTOR_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if r.returncode != 0:
        return ""
    return last_line(r.stdout.decode("utf-8", errors="replace"))


def row(login: str, host: str, line: str, as_json: bool) -> str:
    a, b, c, d, e = fields(line or "executor-failed")
    if a in STATUSES:
        if as_json:
            return _dumps({"account": login, "host": host, "status": a, "email": b or None})
        return f"{login:<22} {b or '-':<34} {a}"
    if as_json:
        return _dumps({"account": login, "host": host, "status": "ok", "email": a,
                       "five_hour": {"utilization": number(b), "resets_at": c},
                       "seven_day": {"utilization": number(d), "resets_at": e}})
    return f"{login:<22} {a:<34} {b:>7}%  {c:<16} {d:>7}%  {e:<16}"


def _dumps(doc: dict) -> str:
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False)


def run(argv: list[str]) -> int:
    try:
        parsed = parse(argv)
        if parsed is None:
            return 0
        as_json, logins = parsed
        placed = placements(roots.hosts_registry())
        # A human login (ADR-044) has no Claude account: all leaves it out,
        # and naming one, or a login not placed, is refused, never an empty
        # table that reads as an answer.
        kind = {l: k for l, _, k in placed}
        for login in logins:
            if login not in kind:
                raise Refused(f"{login} is not a placed account (runtime/hosts/registry.json)")
            if kind[login] != "agent":
                raise Refused(f"{login} is a human login (ADR-044): it has no Claude account to read")
        placed = [(l, h) for l, h, k in placed if k == "agent"]
    except Refused as e:
        say(str(e))
        return 2
    hx = os.environ.get("AGENT_FABRIC_HOSTEXEC") or os.path.join(ROOT, "runtime", "hostexec", "hostexec")
    if not as_json:
        print(f"{'account':<22} {'claude account':<34} {'5h':>8}  {'5h resets (UTC)':<16} {'7d':>8}  {'7d resets (UTC)':<16}",
              flush=True)
    for login, host in placed:
        if logins and login not in logins:
            continue
        print(row(login, host, read_account(hx, host, login), as_json), flush=True)
    return 0


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
