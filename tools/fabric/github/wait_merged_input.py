"""tools/fabric/github/wait_merged_input.py — what wait_merged is given and
what it reads out of the data it is shown: the command line, and the
failing check names and Actions-health verdicts taken from the JSON the
watch fetched. All plain functions of their input. Split out of
wait_merged.py, unchanged; the contract is that module's header."""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from github.review_status.base import Die  # noqa: E402
from github.review_status.cli import as_seconds  # noqa: E402

IDLE_SETTING = "AGENT_FABRIC_IDLE_READS_BEFORE_STALL"


def parse_args(argv: list[str]) -> dict | None:
    """The options, or None when --help was asked. A refusal is a Die."""
    pr, interval, timeout, quiet = "", "30", "2400", False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--interval", "--timeout"):
            if i + 1 >= len(argv):
                raise Die(f"{a} needs a value (try --help).")
            raw = argv[i + 1]
            value = as_seconds(a, raw)
            if not re.fullmatch(r"[1-9][0-9]*", value):
                raise Die(f"{a} must be greater than zero, got '{raw}'.")
            if a == "--interval":
                interval = value
            else:
                timeout = value
            i += 2
        elif a in ("-q", "--quiet"):
            quiet = True
            i += 1
        elif a in ("-h", "--help"):
            return None
        elif a.startswith("-"):
            raise Die(f"unknown option '{a}' (try --help)")
        else:
            if pr:
                raise Die(f"one PR number at a time (got '{pr}' and '{a}')")
            pr = a
            i += 1
    if not pr:
        raise Die("a PR number is required (try --help)")
    if not re.fullmatch(r"[1-9][0-9]*", pr):
        raise Die(f"'{pr}' is not a PR number.")
    # Consecutive idle readings before the arming is called lost: one
    # reading cannot tell a consumed arming from a dropped one. Validated
    # here, with the other invocation checks and before any API call. The
    # bound is on the VALUE: 10 and 100 are two or more.
    idle = os.environ.get(IDLE_SETTING, "2")
    if not (re.fullmatch(r"[0-9]+", idle) and int(idle) >= 2):
        raise Die(f"{IDLE_SETTING} must be an integer of 2 or more (one reading is never evidence), got '{idle}'.")
    return {"pr": pr, "interval": int(interval), "timeout": int(timeout), "quiet": quiet, "idle_reads": int(idle)}


def failing_names(checks: list) -> str:
    """Required checks that concluded badly: `cancel` beside `fail`, since a
    cancelled required check cannot let the PR merge without a re-run."""
    try:
        return ", ".join(str(c.get("name")) for c in checks if c.get("bucket") in ("fail", "cancel"))
    except AttributeError:
        return ""


def outage_line(health: dict | None) -> str:
    """actions-health's outage, told apart by its fields: degraded before any
    billing was read (no period). Built from its status and incident; from a
    checker older than those fields, its reason cut at the advice for a
    person about to push, never at its first ". "."""
    if not isinstance(health, dict) or health.get("exit") != 1 or health.get("period") is not None:
        return ""
    status, incident = health.get("status"), health.get("incident")
    if isinstance(status, str):
        return f"GitHub Actions is {status}" + (f" ({incident})" if isinstance(incident, str) else "")
    reason = health.get("reason")
    if not isinstance(reason, str):
        return ""
    reason = re.sub(r"^DEGRADED — ", "", reason)
    reason = re.sub(r"\. Runs will fail.*$", "", reason)
    return reason[:-1] if reason.endswith(".") else reason


def allowance_spent(health: dict | None) -> bool:
    """The included allowance spent AND nothing billed: the plan that buys no
    overage, where runners stop. Billed overage and a public repository's
    own runners are costs, not stalls."""
    if not isinstance(health, dict):
        return False

    def num(v) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    minutes, included = health.get("private_minutes"), health.get("included")
    return (health.get("exit") == 1 and health.get("public") is False and num(included) and num(minutes)
            and minutes >= included and num(health.get("private_net")) and health.get("private_net") == 0)
