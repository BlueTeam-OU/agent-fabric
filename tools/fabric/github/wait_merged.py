#!/usr/bin/env python3
"""Block until a PR reaches a terminal state, then exit saying which.

The point is the EXIT, not the waiting: run it in the background and
the exit is a callback. Nothing has to sit in a loop asking "has it
merged yet" between other work, and nobody has to remember to check.

  fabric-pr wait-merged 429      # blocks; exits when decided

GitHub offers a local client no push channel — a webhook needs
somewhere to arrive — so the polling has to happen somewhere. Putting
it in a detached process that exits once is the difference between one
notification and a checking habit.

CLOSED-without-merge exits non-zero deliberately. It is the case that
looks exactly like "still waiting" if you only watch for success, and
it is the one where returning to main would be wrong.

This does NOT touch your working tree. It runs detached, and a
checkout underneath a session that is mid-edit is a race with nothing
to catch it. It tells you the state; moving branches stays a
deliberate act.

Usage:
  fabric-pr wait-merged <pr-number> [options]

Options:
  --interval <duration>  between checks (default 30; the API is rate
                         limited and merges take minutes, not seconds)
  --timeout <duration>   give up after this long (default 2400 = 40m)

Durations take an optional unit — 90, 90s, 10m, 2h. A bare number is
SECONDS, so anything written before units existed still means what it
meant. fabric-pr review-status accepts exactly the same
forms, from the same table.
  -q, --quiet            no progress lines on stderr
  -h, --help             this text

Every run ends with ONE line on stdout naming the outcome and the code
it exits with — `PR #431 MERGED — safe to return to main (exit 0)` —
so the answer is legible to a person and branchable by a caller. Usage
errors still go to stderr; they are not results.

The repository is GH_REPO, else this working copy's origin on
github.com. The project's arm command, which the lines that say to arm
name, is its arm.json's arm_command; the eviction line explains the
evicted PR's green checks only in the project's words, its
eviction_note.

Exit codes:
  0  merged
  2  invocation problem, or the PR could not be read repeatedly
  3  closed WITHOUT merging — do not treat as done
  4  still open when the timeout expired
  5  blocked and going nowhere — a check concluded badly, or the branch
     conflicts with its base. BLOCKED with checks merely PENDING is the
     normal path and keeps waiting.
  6  stalled for a reason the PR itself will not resolve — GitHub
     Actions is degraded, a REQUIRED check has no workflow run to
     report it, the included Actions allowance is spent, or auto-merge
     was armed when the watch began and has since been dropped (a base
     that moves takes it with it). Distinguished from 4 because 4 means
     "nobody knows" and 6 names the cause.

     The missing-run case is scoped to REQUIRED checks that GITHUB
     ACTIONS reports. A head SHA with no run is only a stall if
     something was waiting on it: with no required check on the base
     branch it merges fine, and saying otherwise is a false alarm about
     a PR that is not stuck. With one required and nothing reporting it
     can never merge — and whether a lost webhook or a branch/path
     filter caused that does not change the answer, because a required
     check a filter skips waits forever.

     If any required context comes from a NON-Actions reporter — an
     external CI, a third-party check app — this declines and lets the
     watch expire at 4. The probe reads the Actions runs API, so it
     cannot prove that reporter will not report; 4 says "nobody knows",
     which is honest, where a wrong 6 would be acted on.
"""
# The docstring is --help, whole. Ported from a managed project's
# tools/gh/wait-merged.sh (ADR-040; its test, run unchanged on the real
# clock, the oracle), with the one behaviour another project's copy had
# that it lacked (ADDENDUM A below).
#
# THE CONTRACT, frozen from devex-tooling's port contracts 3/8 and 4/8 and
# its rulings of 2026-10-08:
#   argv    <pr> [--interval D] [--timeout D] [-q|--quiet] [-h|--help], read
#           in order; D is N, Ns, Nm or Nh (review_status.cli.as_seconds,
#           pr-review-status's table), defaults 30 and 2400. Usage errors,
#           stderr "wait-merged: <msg>", exit 2: "<flag> needs a value (try
#           --help)."; the duration refusal; "<flag> must be greater than
#           zero, got '<x>'."; "unknown option '<x>' (try --help)"; "one PR
#           number at a time (got 'a' and 'b')"; "a PR number is required
#           (try --help)"; "'<x>' is not a PR number."; the idle threshold's
#           refusal; "gh is required but not installed."; "cannot read the
#           repository: <why>".
#   env     AGENT_FABRIC_IDLE_READS_BEFORE_STALL (default 2, an integer of 2
#           or more); GH_REPO (through gh.this_repo); AGENT_FABRIC_ARM_CONFIG
#           and AGENT_FABRIC_ROOT, as arm finds arm.json; actions_health's own
#           (AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES and its setting name);
#           AGENT_FABRIC_ACTIONS_HEALTH, a TEST SEAM only — a command run as
#           `bash <it> --json` whose object stands in for actions_health's.
#   stdout  exactly one line, 'PR #<n> <verdict> (exit <code>)', on every
#           path but a usage error; the verdicts are the strings below.
#   stderr  progress lines, "wait-merged: …", unless --quiet; the refused
#           allowance line always.
#   exit    0 merged, 2 usage or unreadable, 3 closed, 4 expired, 5 blocked,
#           6 stalled.
# Departures from the bash, each agreed with devex-tooling (2026-10-08):
# the repository is gh.this_repo(), never `gh repo view`'s default (#109),
# so GH_REPO_OWNER/GH_REPO_NAME are no longer read and a repository that
# cannot be named is a usage error; no jq; every gh call is bounded and a
# timeout is that lookup failing; the arm command is the project's
# arm.json's; the conflict line names the base branch; actions-health runs
# in process; the idle threshold's name is the fabric's.
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
from github import actions_health, arm  # noqa: E402
from github.review_status.base import Die  # noqa: E402
# These stay importable from here, where the unit suite reaches them.
from github.wait_merged_input import (  # noqa: E402, F401
    IDLE_SETTING, allowance_spent, failing_names, outage_line, parse_args)

PROG = "wait-merged"
HEALTH_SEAM = "AGENT_FABRIC_ACTIONS_HEALTH"
HEALTH_TIMEOUT_S = 180
# The Actions app's id and the merge queue's branch shape are GitHub's,
# not any project's.
GITHUB_ACTIONS_INTEGRATION_ID = 15368
# A single failed lookup is a blip — a dropped connection, a rate-limit
# pause — and killing the watch over one would be worse than useless,
# because the caller is asleep and would learn nothing. Several in a row
# is a different thing: a deleted PR, a revoked token, no network. Then
# it has to say so rather than wait out the timeout in silence.
MAX_CONSECUTIVE_FAILURES = 5
# Polls with ZERO required checks before the missing-run diagnosis runs.
# Three is comfortably past the window in which GitHub is simply still
# registering a fresh push, without making the wait pointless.
EMPTY_POLLS_BEFORE_DIAGNOSIS = 3
# The expiry path cannot wait for a third consecutive reading — the watch
# is over — so it substitutes "every poll of the whole watch" for "three
# in a row", while still refusing to diagnose off a single one.
EMPTY_POLLS_AT_EXPIRY = 2
ARMING_QUERY = """query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      state
      autoMergeRequest { enabledAt }
      mergeQueueEntry { state }
    }
  }
}"""


class Verdict(Exception):
    """A terminal answer: one stdout line naming it and its code, then the
    exit. Both halves are load-bearing — the code is what a caller branches
    on, the line what a person reads — and it is stdout for EVERY verdict:
    the expiry and unreadable answers used to go to stderr, so a caller
    capturing stdout lost exactly the failures it most needed to see."""

    def __init__(self, code: int, text: str):
        super().__init__(text)
        self.code, self.text = code, text


# ── invocation ───────────────────────────────────────────────────────


def _arm_json(key: str):
    """One key of the project's arm.json, read leniently — a hint is not
    worth a refusal — None when it cannot be read."""
    try:
        with open(arm.config_path(), encoding="utf-8") as fh:
            return json.load(fh).get(key)
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def arm_command() -> str:
    """The project's arm forwarder, which the lines that say to arm name:
    its arm.json's arm_command; without one the lines name it in words."""
    cmd = _arm_json("arm_command")
    return cmd if isinstance(cmd, str) and cmd else "the project's arm.sh"


def eviction_note() -> str:
    """Why the evicted PR's own checks read green, in the project's words
    (arm.json eviction_note): it depends on how that project's CI builds a
    merge_group run. A project that says nothing gets no sentence, never a
    generic one that would be wrong for it."""
    note = _arm_json("eviction_note")
    return note if isinstance(note, str) else ""


# ── the watch ────────────────────────────────────────────────────────

class Watch:
    def __init__(self, opts: dict, repo: str):
        self.pr, self.repo, self.quiet = opts["pr"], repo, opts["quiet"]
        self.interval, self.timeout, self.idle_threshold = opts["interval"], opts["timeout"], opts["idle_reads"]
        self.arm = arm_command()
        self.eviction_note = eviction_note()
        # THE DEADLINE IS WALL-CLOCK, not a count of the naps taken: whole
        # seconds since the watch began, as bash's SECONDS counted, so it
        # covers everything the watch does, API latency included. An
        # accumulator advanced only by the nap reported "expired after 3s"
        # after 12 real seconds of 2s lookups.
        self.t0 = int(time.time())
        # When this watch began, in the runs API's own format: the eviction
        # probe scopes to it.
        self.started_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def seconds(self) -> int:
        return int(time.time()) - self.t0

    def note(self, msg: str) -> None:
        if not self.quiet:
            print(f"{PROG}: {msg}", file=sys.stderr, flush=True)

    def arm_line(self) -> str:
        return f'{self.arm} {self.pr} --basis "<why>"'

    # ── probes ──

    def arming_state(self) -> str:
        """decided, queued, armed or idle; unknown when the probe failed."""
        owner, name = self.repo.split("/", 1)
        try:
            data = gh.graphql(ARMING_QUERY, owner=owner, repo=name, number=int(self.pr))
            pr = data["repository"]["pullRequest"]
        except (gh.GhError, KeyError, TypeError):
            return "unknown"
        # jq's reading of the same object: a missing pull request's state
        # is null, which is not OPEN.
        pr = pr if isinstance(pr, dict) else {}
        if pr.get("state") != "OPEN":
            return "decided"
        if pr.get("mergeQueueEntry"):
            return "queued"
        if pr.get("autoMergeRequest"):
            return "armed"
        return "idle"

    def pr_field(self, field: str):
        try:
            return gh.pr_view(int(self.pr), [field], repo=self.repo).get(field)
        except (gh.GhError, ValueError, AttributeError):
            return None

    def actions_health(self) -> dict | None:
        """actions-health's --json object, or None when it could not run. A
        refused allowance setting (verdict invalid) is said, and Actions is
        asked again without it: a typo in the setting must not hide an
        outage."""
        doc = self._health(os.environ)
        if isinstance(doc, dict) and doc.get("verdict") == "invalid":
            print(f"{PROG}: actions-health refused the allowance setting ({doc.get('reason')}); Actions is checked"
                  " without it", file=sys.stderr, flush=True)
            env = {k: v for k, v in os.environ.items() if k != actions_health.SETTING}
            doc = self._health(env)
        return doc if isinstance(doc, dict) else None

    def _health(self, env) -> dict | None:
        seam = os.environ.get(HEALTH_SEAM, "")
        if not seam:
            try:
                opts = actions_health.parse(["--json"], env)
                return actions_health.report(opts, env) if opts else None
            except actions_health.Usage:
                return None
        try:
            r = subprocess.run(["bash", seam, "--json"], capture_output=True, text=True, timeout=HEALTH_TIMEOUT_S,
                               env=dict(env), stdin=subprocess.DEVNULL)
            return json.loads(r.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None

    def required_checks_configured(self) -> bool:
        """At least one required context on the base branch's rules, every
        one of them reported by the Actions app. Anything else declines."""
        base = self.pr_field("baseRefName")
        if not isinstance(base, str) or not base:
            return False
        try:
            rules = gh.api(f"repos/{self.repo}/rules/branches/{base}")
            contexts = [c for r in rules if r.get("type") == "required_status_checks"
                        for c in ((r.get("parameters") or {}).get("required_status_checks") or [])]
            actions_n = sum(1 for c in contexts if c.get("integration_id") == GITHUB_ACTIONS_INTEGRATION_ID)
            other_n = len(contexts) - actions_n
        except (gh.GhError, TypeError, KeyError, AttributeError):
            return False
        return other_n == 0 and actions_n > 0

    def head_sha_has_no_run(self) -> bool:
        sha = self.pr_field("headRefOid")
        if not isinstance(sha, str) or not sha:
            return False
        try:
            runs = gh.api(f"repos/{self.repo}/actions/runs?head_sha={sha}&per_page=1")
        except gh.GhError:
            return False
        total = runs.get("total_count") if isinstance(runs, dict) else None
        return type(total) is int and total == 0

    def queue_build_failed(self) -> str:
        """The URL of this PR's merge_group run that completed during this
        watch and did not succeed — an eviction — or "". Matched on the
        queue's own branch name, gh-readonly-queue/<base>/pr-<N>-<sha>, the
        only thing tying a merge_group run to a PR; scoped to this watch,
        or a failure fixed hours ago is named again."""
        try:
            doc = gh.api(f"repos/{self.repo}/actions/runs?event=merge_group&per_page=30")
            runs = doc["workflow_runs"]
            mine = [r for r in runs if re.search(f"/pr-{self.pr}-", r["head_branch"])
                    and r.get("status") == "completed" and str(r.get("updated_at") or "") > self.started_at]
        except (gh.GhError, TypeError, KeyError):
            # jq failed the whole filter on any run it could not read.
            return ""
        if not mine or mine[0].get("conclusion") == "success":
            return ""
        url = mine[0].get("html_url")
        return url if isinstance(url, str) else ""

    # ── why is this PR going nowhere ──

    def diagnose(self, no_checks: bool) -> None:
        """Turns "state unknown" into a named stall wherever the cause is
        knowable; returns when it is not. Lazy on purpose: called only
        where the watch would otherwise give up, or when a PR has
        demonstrably reported no check at all."""
        health = self.actions_health()
        line = outage_line(health)
        if line:
            raise Verdict(6, f"STALLED — {line} (githubstatus.com, read by actions-health); the PR is fine, the"
                             " platform is not")
        # "Is anything required" is cheap and decides whether the run
        # question is worth asking at all.
        if no_checks and self.required_checks_configured() and self.head_sha_has_no_run():
            raise Verdict(6, "STALLED — a status check is REQUIRED on this PR's base branch and no workflow run "
                             "exists for its head commit, so nothing can ever report and the PR cannot merge. Either "
                             "the push webhook was lost, or a branch/path filter excluded the required workflow from "
                             "this commit — a required check that a filter skips waits forever. Re-trigger, or fix "
                             "the filter; if you re-trigger, RE-ARM auto-merge afterwards")
        if allowance_spent(health):
            raise Verdict(6, "STALLED — the included Actions allowance is spent; green code will not merge until it "
                             "resets")

    # ── the loop ──

    def run(self) -> None:
        pr = self.pr
        self.note(f"watching #{pr} (every {self.interval}s, giving up after {self.timeout}s)")
        # Say so IMMEDIATELY if nothing is going to merge this; a note, not
        # an exit — arming just after starting the watch is a fair order.
        arming = self.arming_state()
        if arming == "idle":
            self.note(f"#{pr} is neither queued nor auto-merge-armed — nothing will merge it.")
            self.note(f"  arm it:  {self.arm_line()}")
        # "Never armed" is the caller's choice and already said; "armed,
        # then LOST it" is a different fact nobody performs on purpose.
        was_armed = arming in ("armed", "queued")
        failures = check_failures = unreadable_total = 0
        empty_polls = polls_read = idle_reads = 0
        while True:
            payload = self.view()
            if payload is not None:
                failures = 0
                polls_read += 1
                state = payload.get("state") or ""
                merge_state = payload.get("mergeStateStatus") or ""
                checks = self.required_checks()
                # A LOOKUP THAT FAILED IS NOT "NOTHING IS FAILING": the exit
                # status cannot tell (gh exits non-zero precisely when a
                # check fails), whether the answer is a JSON array can.
                readable = isinstance(checks, list)
                if not readable:
                    check_failures += 1
                    unreadable_total += 1
                    self.note(f"could not read #{pr} checks ({check_failures}/{MAX_CONSECUTIVE_FAILURES})")
                    if check_failures >= MAX_CONSECUTIVE_FAILURES:
                        raise Verdict(2, f"UNREADABLE — {MAX_CONSECUTIVE_FAILURES} checks lookups failed in a row;"
                                         " giving up")
                    failing = ""
                else:
                    check_failures = 0
                    failing = failing_names(checks)
                # A TERMINAL STATE OUTRANKS ANY DIAGNOSIS: a PR can merge on
                # the very poll where checks still read empty.
                if state == "MERGED":
                    raise Verdict(0, "MERGED — safe to return to main")
                if state == "CLOSED":
                    raise Verdict(3, "CLOSED WITHOUT MERGING — do not return to main")
                # AND SO DOES A FACT ABOUT THE PR ITSELF: a check concluded
                # badly, or a base conflict, is true of the PR; a stall
                # diagnosis is only a guess about why nothing happens.
                if failing:
                    raise Verdict(5, f"BLOCKED — these required checks failed: {failing}")
                if merge_state == "DIRTY":
                    # The base it conflicts with, by name; unread, it is not
                    # guessed to be main.
                    base = self.pr_field("baseRefName")
                    fold = f"origin/{base}" if isinstance(base, str) and base else "the base branch"
                    raise Verdict(5, f"BLOCKED — conflicts with the base; fold {fold} in")
                # ZERO required checks is not "checks pending": it is a head
                # with no workflow run, confirmed over several polls because
                # right after a push GitHub may simply not have registered it.
                if readable and len(checks) == 0:
                    empty_polls += 1
                    if empty_polls >= EMPTY_POLLS_BEFORE_DIAGNOSIS:
                        self.note(f"#{pr} has reported no required checks for {empty_polls} polls; diagnosing")
                        self.diagnose(True)
                else:
                    empty_polls = 0
                if merge_state == "BLOCKED":
                    self.note(f"#{pr} blocked, checks still pending")
                # ARMING CAN VANISH WITHOUT ANYONE TOUCHING IT: a base that
                # moves goes DIRTY and GitHub drops auto-merge; folded and
                # pushed, the PR is CLEAN, green, unarmed, forever. Probed
                # only where it SHOULD be merging and is not.
                if was_armed and merge_state == "CLEAN" and not failing:
                    reading = self.arming_state()
                    if reading in ("queued", "armed"):
                        idle_reads = 0
                    elif reading == "idle":
                        # ONE idle reading is not a dropped arming: auto-merge
                        # is CONSUMED when the PR enters the queue, and the
                        # queue entry may not be visible the same instant
                        # (#524 read idle at queue position 1 and merged).
                        idle_reads += 1
                        if idle_reads < self.idle_threshold:
                            self.note(f"#{pr} reads neither queued nor armed — re-checking, the queue may have just"
                                      " consumed the arming")
                        else:
                            # An eviction wants the merge_group failure fixed
                            # FIRST; re-arming into it repeats it.
                            qb = self.queue_build_failed()
                            if qb:
                                note = f"{self.eviction_note} " if self.eviction_note else ""
                                raise Verdict(6, f"STALLED — the merge queue EVICTED #{pr}: its merge_group build "
                                                 f"failed and auto-merge was dropped. {note}Fix it, THEN re-arm: "
                                                 f"{qb}")
                            raise Verdict(6, "STALLED — auto-merge was armed when this watch began and is no longer, "
                                             f"and #{pr} has read neither queued nor armed on {idle_reads} consecutive"
                                             " polls; it is green and CLEAN and nothing will merge it (its base most "
                                             "likely moved). No failed merge_group run for this pr, so re-arming is "
                                             f"the fix: {self.arm_line()}")
                    else:
                        # ANY OTHER READING IS A GAP, NOT A CONTINUATION: a
                        # probe that failed, or a PR that left OPEN between
                        # the two calls, says neither present nor gone.
                        self.note(f"#{pr} arming probe returned no usable reading — this poll does not count")
                        idle_reads = 0
                else:
                    # The probe did not run: readings either side of the gap
                    # are not CONSECUTIVE.
                    idle_reads = 0
            else:
                failures += 1
                # A poll that read nothing observed nothing: it continues no
                # run of idle readings and is not the "LAST poll".
                idle_reads = 0
                self.note(f"could not read #{pr} ({failures}/{MAX_CONSECUTIVE_FAILURES})")
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    raise Verdict(2, f"UNREADABLE — {MAX_CONSECUTIVE_FAILURES} lookups failed in a row; giving up")

            remaining = self.timeout - self.seconds()
            if remaining <= 0:
                self.expire(empty_polls, polls_read, idle_reads, unreadable_total)
            # Never sleep past the deadline, and never cut the watch short
            # of it: the nap is clamped to what is left.
            time.sleep(min(self.interval, remaining))

    def expire(self, empty_polls: int, polls_read: int, idle_reads: int, unreadable_total: int) -> None:
        # The emptiness must describe the WHOLE watch — every poll that read
        # anything read nothing, more than once — or a PR pushed just before
        # the deadline is told its webhook was lost.
        self.diagnose(empty_polls >= EMPTY_POLLS_AT_EXPIRY and empty_polls == polls_read)
        # What it actually waited, API time included — never the timeout.
        head = f"STILL OPEN after {self.seconds()}s — watch expired, state unknown"
        # THE LAST POLL HAS NO SUCCESSOR, so an idle reading on it can never
        # reach the threshold: it is named, unconfirmed, at exit 4 — and an
        # eviction first, since "re-arm" queues straight back into it.
        if idle_reads > 0:
            qb = self.queue_build_failed()
            if qb:
                raise Verdict(4, f"{head}. Its LAST poll read neither queued nor armed, and this pr has a FAILED "
                                 f"merge_group run: the queue most likely evicted it. {idle_reads} reading(s), "
                                 f"unconfirmed — but do NOT simply re-arm, that repeats the failure. Fix it first: {qb}")
            raise Verdict(4, f"{head}. Its LAST poll read neither queued nor armed — {idle_reads} reading(s), "
                             "unconfirmed, and the queue may simply have consumed the arming. Check before acting; if"
                             f" the arming really is gone: {self.arm_line()}")
        # ADDENDUM A: a checks lookup unreadable on any poll may have hidden
        # a failing check for the whole watch; said, after the stalls and
        # the arming lines, before the plain expiry.
        if unreadable_total > 0:
            raise Verdict(4, f"{head}; the required-checks lookup was unreadable on {unreadable_total} poll(s), so a"
                             " failing check may simply never have been visible")
        raise Verdict(4, head)

    def view(self) -> dict | None:
        try:
            doc = gh.pr_view(int(self.pr), ["state", "mergeStateStatus"], repo=self.repo)
        except (gh.GhError, ValueError):
            return None
        return doc if isinstance(doc, dict) and doc else None

    def required_checks(self):
        """REQUIRED checks only, through `gh pr checks` — an optional check
        that fails does not stop the queue, and `bucket` normalises check
        runs and legacy statuses alike. gh exits non-zero while one fails or
        pends: that is an answer, so its stdout is read either way. With none
        reported it prints no JSON at all, and that is an answer too: []."""
        args = ["pr", "checks", self.pr, "--required", "--json", "name,bucket", "--repo", self.repo]
        try:
            out = gh.run(args, what="gh pr checks")
        except gh.GhError as e:
            if gh.no_checks_reported(e):
                return []
            out = e.stdout
        try:
            return json.loads(out)
        except ValueError:
            return None


def run(argv: list[str]) -> int:
    opts = parse_args(argv)
    if opts is None:
        print(__doc__.strip("\n"))
        return 0
    if not shutil.which("gh"):
        raise Die("gh is required but not installed.")
    try:
        repo = gh.this_repo()
    except gh.GhError as e:
        raise Die(f"cannot read the repository: {e.reason}") from None
    try:
        Watch(opts, repo).run()
    except Verdict as v:
        print(f"PR #{opts['pr']} {v.text} (exit {v.code})", flush=True)
        return v.code
    return 2   # unreachable: the loop leaves only by a verdict


def main() -> int:
    # The bash wrote UTF-8 whatever the locale; so does this, or the em
    # dashes in its own lines fail under a non-UTF-8 LANG.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    try:
        return run(sys.argv[1:])
    except Die as e:
        print(f"{PROG}: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
