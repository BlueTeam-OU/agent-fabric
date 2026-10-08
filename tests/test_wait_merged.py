#!/usr/bin/env python3
"""tools/fabric/github/wait_merged.py. Its behaviour's oracle is a managed
project's tools/gh/test_wait-merged.sh, run unchanged against the shim on
the real clock (ADR-040 §5 rule 5); its fast-clock control was retired with
the clock seam it needed, which production code does not carry. So the
deadlines that oracle timed are pinned here, in process, on a clock this
file owns: the watch's expiry and the nap clamped to it, API time counted,
the run of 5 failed reads, the idle-read stall. Then what the port adds or
changes: the arm command from arm.json, the base branch named in the
conflict line, ADDENDUM A's cumulative unreadable count and its precedence,
actions-health's seam and its invalid-setting retry, and the shim's own
contract — usage errors, --help, UTF-8 under the C locale. Plain script:
prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import gh  # noqa: E402
from github import wait_merged as wm  # noqa: E402

TOOL = os.path.join(ROOT, "runtime", "github", "wait-merged.sh")
GZAPP_ARM = os.path.join(ROOT, "projects", "gzapp", "integration", "gh", "arm.json")
PR = "429"


class Clock:
    """time.time and time.sleep for the module: a nap ages the clock, and
    every gh call costs `latency` seconds, as a real one costs real ones."""

    def __init__(self):
        self.now, self.naps = 1_000_000.0, []

    def time(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.naps.append(s)
        self.now += s


class Fake:
    """gh as wait_merged calls it, scripted per poll like the oracle's mock:
    a view is "STATE[:MERGESTATE]" or "FAIL"; a checks answer is a list, or
    None for an unreadable one; an arming answer is a word, "unknown" a
    failed probe. The last of each list repeats."""

    def __init__(self, clock: Clock, views, checks=None, arming=("queued",), base="main", latency=0.0,
                 merge_group=None, rules=None, runs=1):
        self.clock, self.latency = clock, latency
        self.views, self.checks, self.arming = list(views), list(checks or [[{"name": "ci", "bucket": "pass"}]]), \
            list(arming)
        self.base, self.merge_group, self.runs = base, merge_group or [], runs
        self.rules = rules if rules is not None else [{"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "ci", "integration_id": 15368}]}}]
        self.n_view = self.n_arming = 0

    def _tick(self) -> None:
        self.clock.now += self.latency

    @staticmethod
    def _at(seq: list, i: int):
        return seq[min(i, len(seq) - 1)]

    def pr_view(self, number, fields, *, repo=None, timeout=0):
        self._tick()
        if fields == ["baseRefName"]:
            if self.base is None:
                raise gh.GhError("gh pr view", "boom")
            return {"baseRefName": self.base}
        if fields == ["headRefOid"]:
            return {"headRefOid": "deadbeef"}
        line = self._at(self.views, self.n_view)
        self.n_view += 1
        if line == "FAIL":
            raise gh.GhError("gh pr view", "no answer within 60 s", transient=True)
        state, _, merge = line.partition(":")
        return {"state": state, "mergeStateStatus": merge or "CLEAN"}

    def run(self, args, *, input=None, timeout=0, what=None):
        self._tick()
        assert args[:2] == ["pr", "checks"], args
        answer = self._at(self.checks, self.n_view - 1)
        if answer is None:
            raise gh.GhError("gh pr checks", "HTTP 502", stdout="")
        return json.dumps(answer)

    def api(self, path, **kw):
        self._tick()
        if "event=merge_group" in path:
            return {"workflow_runs": self.merge_group}
        if "/actions/runs?" in path:
            return {"total_count": self.runs}
        if "/rules/branches/" in path:
            return self.rules
        raise AssertionError(path)

    def graphql(self, query, **variables):
        self._tick()
        word = self._at(self.arming, self.n_arming)
        self.n_arming += 1
        if word == "unknown":
            raise gh.GhError("gh api graphql", "boom")
        pr = {"decided": {"state": "MERGED"}, "queued": {"state": "OPEN", "mergeQueueEntry": {"state": "QUEUED"}},
              "armed": {"state": "OPEN", "autoMergeRequest": {"enabledAt": "x"}}, "idle": {"state": "OPEN"}}[word]
        return {"repository": {"pullRequest": pr}}


HEALTHY = {"exit": 0, "verdict": "ok", "period": "2026-10", "public": False, "private_minutes": 1,
           "private_net": 0, "included": 50000}


def watch(fake: Fake, clock: Clock, interval=30, timeout=2400, idle=2, health=None, env=None):
    """One watch, in process: (code, verdict text, stderr). Patches only for
    its own duration, and restores what it found."""
    saved = (gh.pr_view, gh.run, gh.api, gh.graphql, wm.time.time, wm.time.sleep, wm.Watch._health)
    old_env = dict(os.environ)
    gh.pr_view, gh.run, gh.api, gh.graphql = fake.pr_view, fake.run, fake.api, fake.graphql
    wm.time.time, wm.time.sleep = clock.time, clock.sleep
    seen = []

    def _health(self, e):
        seen.append(dict(e))
        h = health(e) if callable(health) else health
        return HEALTHY if h is None else h
    wm.Watch._health = _health
    os.environ.update({"AGENT_FABRIC_ARM_CONFIG": GZAPP_ARM, **(env or {})})
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            w = wm.Watch({"pr": PR, "interval": interval, "timeout": timeout, "quiet": False, "idle_reads": idle},
                         "o/r")
            # The eviction probe compares the runs API's timestamps with
            # the watch's start, which is the real clock's: pinned.
            w.started_at = "2026-10-08T00:00:00Z"
            try:
                w.run()
            except wm.Verdict as v:
                return v.code, v.text, err.getvalue(), seen
            return None, "", err.getvalue(), seen
    finally:
        gh.pr_view, gh.run, gh.api, gh.graphql, wm.time.time, wm.time.sleep, wm.Watch._health = saved
        os.environ.clear()
        os.environ.update(old_env)


def evicted(conclusion="failure", pr=PR, at="2026-10-08T01:00:00Z"):
    return [{"head_branch": f"gh-readonly-queue/main/pr-{pr}-abc", "status": "completed", "conclusion": conclusion,
             "updated_at": at, "html_url": "https://gh.test/run/1"}]


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    # ── the deadlines the oracle timed ───────────────────────────────
    print("wait_merged: deadlines on a clock this test owns")
    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:BLOCKED"]), c, interval=30, timeout=100)
    check("the watch expires at its timeout, exit 4", code == 4 and text == "STILL OPEN after 100s — watch expired,"
          " state unknown", f"{code} {text}")
    check("its naps are the interval, the last clamped to what is left", c.naps == [30, 30, 30, 10], str(c.naps))

    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:BLOCKED"]), c, interval=60, timeout=6)
    check("a timeout under the interval: one nap, clamped, then the expiry", c.naps == [6] and code == 4
          and "after 6s" in text, f"{c.naps} {text}")

    # 1s a call: the arming probe, then 2s a poll (view and checks) and a
    # 1s nap. A deadline that counted only the naps would poll six times.
    c = Clock()
    f = Fake(c, ["OPEN:BLOCKED"], latency=1)
    code, text, _, _ = watch(f, c, interval=1, timeout=6)
    check("API time counts against the deadline: two polls, not six", code == 4 and f.n_view == 2
          and "after 6s" in text, f"{f.n_view} {text}")
    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:BLOCKED"], latency=2), c, interval=1, timeout=5)
    check("the expiry names the real elapsed time, not the timeout", "after 6s" in text, text)

    c = Clock()
    code, text, err, _ = watch(Fake(c, ["FAIL"]), c, interval=1, timeout=600)
    check("5 failed reads in a row are exit 2", code == 2 and text == "UNREADABLE — 5 lookups failed in a row;"
          " giving up", text)
    check("each is said with its count", "could not read #429 (4/5)" in err and "(5/5)" in err, err)
    check("after four naps, not a timeout", c.naps == [1, 1, 1, 1], str(c.naps))
    c = Clock()
    code, _, _, _ = watch(Fake(c, ["FAIL"] * 4 + ["MERGED"]), c, interval=1, timeout=600)
    check("four failures then a merge is a merge", code == 0)
    c = Clock()
    code, _, _, _ = watch(Fake(c, ["FAIL"] * 4 + ["OPEN:BLOCKED"] + ["FAIL"] * 4 + ["MERGED"]), c, interval=1,
                          timeout=600)
    check("a read between resets the run", code == 0)

    c = Clock()
    code, text, err, _ = watch(Fake(c, ["OPEN:BLOCKED"], checks=[None]), c, interval=1, timeout=600)
    check("5 unreadable checks lookups in a row are exit 2", code == 2 and text == "UNREADABLE — 5 checks lookups"
          " failed in a row; giving up", text)
    check("each is said with its count", "could not read #429 checks (5/5)" in err, err)
    # The oracle never reads the reset (a mutation removing it survived it).
    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:BLOCKED"] * 9 + ["MERGED"], checks=[None] * 4 + [[]] + [None] * 4 + [[]]),
                             c, interval=1, timeout=600)
    check("a readable checks lookup resets the run of 5", code == 0, text)

    # ── the idle-read stall ──────────────────────────────────────────
    print("wait_merged: arming lost mid-watch")
    c = Clock()
    f = Fake(c, ["OPEN:CLEAN"], arming=["queued", "idle"])
    code, text, err, _ = watch(f, c, interval=30, timeout=2400)
    check("armed, then idle on two adjacent polls, is the lost-arming 6", code == 6 and "on 2 consecutive polls" in text,
          text)
    check("it names the project's arm command from arm.json", text.endswith('tools/gh/arm.sh 429 --basis "<why>"'), text)
    check("the first idle reading is only a re-check", "re-checking, the queue may have just consumed" in err, err)
    check("after one nap between them", c.naps == [30], str(c.naps))
    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:CLEAN"], arming=["queued", "idle"]), c, idle=3)
    check("the threshold is the setting's", code == 6 and "on 3 consecutive polls" in text and c.naps == [30, 30], text)
    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:CLEAN"], arming=["queued", "idle", "queued", "idle", "queued"]), c,
                             interval=30, timeout=120)
    check("idle readings that are not adjacent never stall", code == 4, text)
    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:CLEAN"], arming=["queued", "idle", "unknown", "idle", "queued"]), c,
                             interval=30, timeout=120)
    check("a failed probe breaks the run", code == 4, text)

    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:CLEAN"], arming=["queued", "idle"], merge_group=evicted()), c)
    check("a failed merge_group run during the watch is an eviction, not a re-arm",
          code == 6 and "EVICTED #429" in text and text.endswith("https://gh.test/run/1"), text)
    for label, runs in (("a successful queue run", evicted("success")),
                        ("a failure from before the watch", evicted(at="2026-10-07T00:00:00Z")),
                        ("another pr's failure", evicted(pr="4290"))):
        c = Clock()
        code, text, _, _ = watch(Fake(c, ["OPEN:CLEAN"], arming=["queued", "idle"], merge_group=runs), c)
        check(f"{label} is not an eviction", code == 6 and "No failed merge_group run" in text, text)

    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:CLEAN"], arming=["queued", "queued", "idle"]), c, interval=30, timeout=30)
    check("idle on the LAST poll is the unconfirmed 4, counted",
          code == 4 and "Its LAST poll read neither queued nor armed — 1 reading(s)" in text
          and text.endswith('tools/gh/arm.sh 429 --basis "<why>"'), text)

    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:CLEAN"], arming=["queued", "idle"]), c,
                             env={"AGENT_FABRIC_ARM_CONFIG": os.path.join(ROOT, "no-such-arm.json")})
    check("without an arm.json the lines name the project's arm.sh in words",
          text.endswith('the project\'s arm.sh 429 --basis "<why>"'), text)

    # ── the conflict line ────────────────────────────────────────────
    print("wait_merged: the conflict names its base")
    for base, want in (("main", "fold origin/main in"), ("develop", "fold origin/develop in"),
                       (None, "fold the base branch in")):
        c = Clock()
        code, text, _, _ = watch(Fake(c, ["OPEN:DIRTY"], base=base), c)
        check(f"base {base!r}: {want}", code == 5 and text == f"BLOCKED — conflicts with the base; {want}", text)

    # ── ADDENDUM A ───────────────────────────────────────────────────
    print("wait_merged: unreadable checks over the whole watch")
    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:BLOCKED"] * 10, checks=[None, None, [], None, []]), c, interval=1,
                             timeout=4)
    # Five polls (t=0..4): unreadable on the 1st, 2nd and 4th.
    check("unreadable on any poll is said at expiry, counted, never reset",
          code == 4 and text.endswith("; the required-checks lookup was unreadable on 3 poll(s), so a failing check"
                                      " may simply never have been visible"), text)
    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:CLEAN"], checks=[None, [{"name": "ci", "bucket": "pass"}]],
                                  arming=["queued", "queued", "idle"]), c, interval=30, timeout=30)
    check("the idle-arming line outranks it", code == 4 and "Its LAST poll" in text and "unreadable on" not in text,
          text)
    c = Clock()
    code, text, _, _ = watch(Fake(c, ["OPEN:BLOCKED"], checks=[[]], runs=0), c, interval=30, timeout=60)
    check("a named stall outranks both", code == 6 and "no workflow run exists" in text, text)

    # ── actions-health ───────────────────────────────────────────────
    print("wait_merged: actions-health in process, its retry and its seam")
    invalid = {"exit": 2, "verdict": "invalid", "reason": "the allowance must be a positive number, got 50k"}
    outage = {"exit": 1, "verdict": "degraded", "period": None, "status": "major outage", "incident": "Runs. Delayed"}
    c = Clock()
    code, text, err, seen = watch(Fake(c, ["OPEN:BLOCKED"]), c, interval=30, timeout=30,
                                  health=lambda e: invalid if "AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES" in e else outage,
                                  env={"AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES": "50k"})
    check("a refused allowance setting is said", "actions-health refused the allowance setting (the allowance must be"
          " a positive number, got 50k); Actions is checked without it" in err, err)
    check("and asked again without it", len(seen) == 2 and "AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES" in seen[0]
          and "AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES" not in seen[1])
    check("so the outage it hid is named, its incident whole",
          code == 6 and text == "STALLED — GitHub Actions is major outage (Runs. Delayed) (githubstatus.com, read by"
          " actions-health); the PR is fine, the platform is not", text)

    check("an older checker's reason, cut at its advice",
          wm.outage_line({"exit": 1, "period": None, "reason": "DEGRADED — GitHub Actions is down (A. B). Runs will"
                          " fail or never start."}) == "GitHub Actions is down (A. B)")
    check("a billing read is no outage", wm.outage_line({"exit": 1, "period": "2026-10", "status": "x"}) == "")
    spent = {"exit": 1, "public": False, "included": 100, "private_minutes": 100, "private_net": 0}
    check("allowance at its limit with nothing billed is spent", wm.allowance_spent(spent))
    for label, change in (("billed overage", {"private_net": 3}), ("a public repository", {"public": True}),
                          ("under the limit", {"private_minutes": 99}), ("no setting", {"included": None}),
                          ("a checker that could not find out", {"exit": 2}), ("a boolean count", {"private_net": False})):
        check(f"{label} is not", not wm.allowance_spent({**spent, **change}))

    with tempfile.TemporaryDirectory() as sandbox:
        seam = os.path.join(sandbox, "health.sh")
        with open(seam, "w", encoding="utf-8") as fh:
            fh.write('printf \'{"exit":1,"period":null,"status":"degraded","argv":"%s","m":"%s"}\\n\' "$*"'
                     ' "${AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES:-}"\n')
        old = dict(os.environ)
        os.environ.update({wm.HEALTH_SEAM: seam, "AGENT_FABRIC_ACTIONS_INCLUDED_MINUTES": "7"})
        try:
            w = wm.Watch({"pr": PR, "interval": 1, "timeout": 1, "quiet": True, "idle_reads": 2}, "o/r")
            doc = w.actions_health()
        finally:
            os.environ.clear()
            os.environ.update(old)
        check("the seam runs as `bash <it> --json`, in the caller's environment",
              doc == {"exit": 1, "period": None, "status": "degraded", "argv": "--json", "m": "7"}, str(doc))

    # ── the shim ─────────────────────────────────────────────────────
    print("wait_merged: through runtime/github/wait-merged.sh")
    with tempfile.TemporaryDirectory() as sandbox:
        bin_ = os.path.join(sandbox, "bin")
        os.makedirs(bin_)
        with open(os.path.join(bin_, "gh"), "w", encoding="utf-8") as fh:
            fh.write(f"#!{sys.executable}\n" + r'''import sys
a = sys.argv[1:]
if a[:2] == ["api", "graphql"]:
    print('{"data":{"repository":{"pullRequest":{"state":"MERGED"}}}}')
elif a[:2] == ["pr", "view"]:
    print('{"state":"MERGED","mergeStateStatus":"CLEAN"}')
elif a[:2] == ["pr", "checks"]:
    print("[]")
else:
    sys.exit(1)
''')
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        os.symlink(shutil.which("bash") or "/bin/bash", os.path.join(bin_, "bash"))
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_", "GH_", "GIT_", "LC_", "LANG"))}
        base.update(PATH=bin_, HOME=sandbox, LC_ALL="C", GH_REPO="o/r")
        base.pop("PYTHONUTF8", None)
        if os.environ.get("AGENT_FABRIC_PYTHON"):
            base["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]

        def run(*args: str, **env: str):
            e = {k: v for k, v in dict(base, **env).items() if v is not None}
            r = subprocess.run([TOOL, *args], env=e, cwd=sandbox, capture_output=True, timeout=60)
            return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8")

        # Python coerces the C locale to UTF-8 by itself; an ASCII stream
        # is what proves the tool writes UTF-8 whatever it was handed.
        rc, out, err = run(PR, "--interval", "1", "--timeout", "5", PYTHONIOENCODING="ascii")
        check("a merge: one stdout line, UTF-8 on an ASCII stream, exit 0",
              rc == 0 and out == "PR #429 MERGED — safe to return to main (exit 0)\n", f"{rc} {out!r} {err!r}")
        rc, out, err = run("-h")
        check("--help is the module's text, exit 0", rc == 0 and out.startswith("Block until a PR reaches") and not err)
        for args, env, want in (
                (("x1",), {}, "wait-merged: 'x1' is not a PR number.\n"),
                (("1", "2"), {}, "wait-merged: one PR number at a time (got '1' and '2')\n"),
                ((), {}, "wait-merged: a PR number is required (try --help)\n"),
                (("1", "--bogus"), {}, "wait-merged: unknown option '--bogus' (try --help)\n"),
                (("1", "--timeout"), {}, "wait-merged: --timeout needs a value (try --help).\n"),
                (("1", "--interval", "0"), {}, "wait-merged: --interval must be greater than zero, got '0'.\n"),
                (("1",), {"AGENT_FABRIC_IDLE_READS_BEFORE_STALL": "1"}, "wait-merged: AGENT_FABRIC_IDLE_READS_BEFORE_STALL must be an integer of 2 or more"
                                                 " (one reading is never evidence), got '1'.\n"),
                (("1",), {"GH_REPO": None}, "wait-merged: cannot read the repository: "),
        ):
            rc, out, err = run(*args, **env)
            check(f"usage {args} {env}: exit 2, stderr only", rc == 2 and out == "" and err.startswith(want),
                  f"{rc} {out!r} {err!r}")

    print("ok" if not fails else f"{fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
