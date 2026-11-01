#!/usr/bin/env python3
"""tools/fabric/review_codex.py through bin/fabric-review --engine codex, with
a fake `codex` and a fake `gh` on PATH: the second engine runs Codex once,
read-only, on an extract of the PR's head, through its own gateway with the
session's credentials scrubbed, and posts a schema-valid answer or nothing
(agent-fabric ADR-053 rules 1-4). No real codex runs here. Plain script:
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import contextlib
import io
import json
import re
import os
import pwd
import http.server
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

# Its own imports would write __pycache__ into the checkout (ADR-021): this file's run is a test's.
sys.dont_write_bytecode = True

from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree, write_routing_overlay  # noqa: E402

own_instance_tree()
scrub_process_env()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW = os.path.join(ROOT, "bin", "fabric-review")
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import review_codex  # noqa: E402
from github.review_status.config import REVIEW_MARKER  # noqa: E402
from github.review_status.verdicts import unavailable_of  # noqa: E402 — the one parser, the arm's


def parsed(text):
    return unavailable_of({"body": text})

# The fake codex sees only the environment the engine gives it, so its
# behaviour and its records go through files at paths written into it.
FAKE_CODEX = r'''#!%(python)s
import json, os, subprocess, sys, time
S = %(state)r
argv = sys.argv[1:]
if argv[:1] == ["sandbox"]:
    with open(os.path.join(S, "sandbox-calls"), "a") as f:
        f.write(json.dumps(argv) + "\n")
    smode = open(os.path.join(S, "sandbox-mode")).read().strip() if os.path.exists(os.path.join(S, "sandbox-mode")) else "ok"
    cmd = argv[argv.index("--") + 1:]
    is_write_probe = "touch" in " ".join(cmd)
    is_read_probe = "cat" in " ".join(cmd)
    if smode == "fail":
        print("bwrap: No permissions to create a new namespace " + os.environ.get("AGENT_FABRIC_CODEX_KEY", ""), file=sys.stderr)
        sys.exit(1)
    if smode == "sleep":
        gc = subprocess.Popen(["sleep", "300"])
        with open(os.path.join(S, "sandbox-grandchild"), "w") as f:
            f.write(f"{os.getpid()} {gc.pid}")
        time.sleep(300)
    if smode == "noop":
        sys.exit(0)                                   # a "sandbox" that runs nothing and says all is well
    if smode == "writable":
        sys.exit(subprocess.run(cmd).returncode)      # nothing refuses the write: the probe's touch succeeds and says 7
    if is_read_probe and smode == "readable":
        sys.exit(subprocess.run(cmd).returncode)      # nothing confines a read: the canary is read, and the probe says 9
    if is_read_probe and smode == "blind":
        # the extract's own file cannot be read (the canary can, as nothing confines it): the probe's own script must see that first
        sys.exit(subprocess.run(cmd[:-1] + ["/nonexistent-control"]).returncode)
    if is_read_probe and smode in ("ok", "leaky"):
        sys.exit(43)                                  # the canary is outside the allowlist: refused
    if smode == "leaky":
        subprocess.run(cmd)                           # the write happens, and the sandbox still answers as if it were refused
        sys.exit(43 if is_write_probe else 42)
    # ok: a sandbox that starts the command (the start probe's own exit status comes back) and refuses the write
    sys.exit(43 if is_write_probe else subprocess.run(cmd).returncode)
prompt = sys.stdin.read()
rec = {"argv": argv, "env": dict(os.environ), "cwd": os.getcwd(), "prompt": prompt,
       "cwd_files": sorted(os.listdir(".")),
       "config": open(os.path.join(os.environ.get("CODEX_HOME", "/nonexistent"), "config.toml")).read()
                 if os.path.isfile(os.path.join(os.environ.get("CODEX_HOME", "/nonexistent"), "config.toml")) else None}
with open(os.path.join(S, "codex-run.json"), "w") as f:
    json.dump(rec, f)
with open(os.path.join(S, "codex-calls"), "a") as f:
    f.write("run\n")
# One mode per run, in order: the file holds a line for each run still to come, the last one kept for every run after.
lines = open(os.path.join(S, "mode")).read().split()
mode = lines[0]
if len(lines) > 1:
    with open(os.path.join(S, "mode"), "w") as f:
        f.write(" ".join(lines[1:]))
out = argv[argv.index("--output-last-message") + 1]
# The JSONL events of `codex exec --json` (codex 0.162.1), as a run against a stand-in Responses endpoint
# printed them: stdout carries only these; Codex's own log lines go to stderr.
n = [0]
def ev(doc):
    print(json.dumps(doc), flush=True)
def item(kind, **kw):
    n[0] += 1
    ev({"type": "item.completed", "item": {"id": f"item_{n[0]}", "type": kind, **kw}})
def command(cmd, code=0):
    full = "/bin/bash -lc '" + cmd + "'"
    ev({"type": "item.started", "item": {"id": f"item_{n[0] + 1}", "type": "command_execution", "command": full,
                                         "aggregated_output": "", "exit_code": None, "status": "in_progress"}})
    item("command_execution", command=full, aggregated_output="2 app.py\n" if code == 0 else "no such file\n",
         exit_code=code, status="completed" if code == 0 else "failed")
def answer(text, file=True, commands=1):
    ev({"type": "thread.started", "thread_id": "01a13195-6c03-7e02-94f7-7a304e1e64d6"})
    ev({"type": "turn.started"})
    for _ in range(commands):
        command("wc -l app.py")
    if file:
        with open(out, "w") as f:
            f.write(text)
    item("agent_message", text=text)
    usage_file = os.path.join(S, "usage.json")   # a case that means other counts writes them here
    ev({"type": "turn.completed", "usage": json.load(open(usage_file)) if os.path.exists(usage_file)
        else {"input_tokens": 20, "cached_input_tokens": 0, "output_tokens": 10}})
COV = {"paths": [{"path": "app.py", "status": "read", "reason": ""}], "lenses": [], "default": None}
EMPTY = json.dumps({"findings": [], "coverage": COV})
OK = json.dumps({"coverage": COV, "findings": [
    {"level": "P3", "file": "app.py", "line": 2, "scenario": "a\nmulti-line scenario", "expected": "e3", "fix": "f3"},
    {"level": "P1", "file": "app.py", "line": 1, "scenario": "s1", "expected": "e1", "fix": "f1"}]})
HEADSUP = ("Heads up: Long threads and multiple compactions can cause the model to be less accurate. "
           "Start a new thread when possible to keep threads small and targeted.")
HOST = ("Code Mode is unavailable because failed to spawn code-mode host /home/u/.local/bin/codex-code-mode-host: "
        "host executable was not found. Code mode will fail closed; enable `features.code_mode_host` and install "
        "`codex-code-mode-host`.")
if mode == "sleep":
    p = subprocess.Popen(["sleep", "300"])
    with open(os.path.join(S, "grandchild"), "w") as f:
        f.write(str(p.pid))
    time.sleep(300)
elif mode == "ok":
    print("2026-10-12T10:00:00Z  WARN codex_core: a log line, on stderr", file=sys.stderr)
    answer(OK)
elif mode == "empty":
    answer(EMPTY)
elif mode == "retried":
    ev({"type": "thread.started", "thread_id": "t"})
    ev({"type": "error", "message": "Reconnecting... 1/5 (stream disconnected before completion: error sending request)"})
    answer(EMPTY)
elif mode == "eventonly":
    answer(EMPTY, file=False)
elif mode == "nohost":
    # The live defect (2026-10-12): the tool host missing, no command run, an empty answer from the brief alone.
    print("ERROR codex_core::tools::router: error=failed to spawn code-mode host", file=sys.stderr)
    ev({"type": "thread.started", "thread_id": "t"})
    item("error", message=HOST)
    answer(EMPTY, commands=0)
elif mode == "nocommand":
    answer(EMPTY, commands=0)
elif mode == "cmdfailed":
    ev({"type": "turn.started"})
    command("cat nope", code=1)
    answer(EMPTY, commands=0)
elif mode == "othererror":
    item("error", message="something else went wrong")
    answer(EMPTY)
elif mode in ("compaction", "compaction-nocommand", "compaction-other"):
    item("error", message=HEADSUP)
    if mode == "compaction-other":
        item("error", message="something else went wrong")
    answer(EMPTY, commands=0 if mode == "compaction-nocommand" else 1)
elif mode == "turnfailed":
    ev({"type": "turn.started"})
    ev({"type": "error", "message": "stream disconnected before completion: error sending request"})
    ev({"type": "turn.failed", "error": {"message": "stream disconnected before completion: error sending request"}})
    sys.exit(1)
elif mode == "turnfailed-long":
    ev({"type": "turn.failed", "error": {"message": "first line\nsecond line " + "x" * 2000}})
    sys.exit(1)
elif mode in ("capacity", "allowance", "allowance-notime", "capacity-lookalike"):
    # The failed turns of codex 0.162.1: its message strings, from the pinned binary; a top-level error, turn.failed, exit 1.
    text = {"capacity": "Selected model is at capacity. Please try a different model.",
            "allowance": "You\u2019ve hit your usage limit. Upgrade to Plus to continue using Codex "
                         "(https://chatgpt.com/explore/plus), or try again at Oct 14th, 2026 3:12 PM.",
            "allowance-notime": "You\u2019ve hit your usage limit. Visit https://chatgpt.com/settings/usage to purchase more credits",
            "capacity-lookalike": "the scratch disk is at capacity"}[mode]
    ev({"type": "turn.started"})
    ev({"type": "error", "message": text})
    ev({"type": "turn.failed", "error": {"message": text}})
    sys.exit(1)
elif mode == "capacity-item":
    item("error", message="Selected model is at capacity. Please try a different model.")
    answer(EMPTY)
elif mode == "prose":
    answer("Looks good to me! No findings.")
elif mode == "fence":
    answer('```json\n' + EMPTY + '\n```')
elif mode == "badschema":
    answer('{"findings": [{"level": "P2", "file": "app.py", "line": 3, "scenario": "s", "expected": "e"}]}')
elif mode == "nocoverage":
    answer('{"findings": []}')
elif mode == "partialcov":
    answer(json.dumps({"findings": [], "coverage": {"paths": [{"path": "app.py", "status": "not read", "reason": "too long"}], "lenses": [], "default": None}}))
elif mode == "wrongpaths":
    answer(json.dumps({"findings": [], "coverage": {"paths": [{"path": "other.py", "status": "read", "reason": ""}], "lenses": [], "default": None}}))
elif mode == "exit1":
    print("backend said no", file=sys.stderr)
    sys.exit(3)
elif mode == "noanswer":
    ev({"type": "turn.started"})
    command("wc -l app.py")
    ev({"type": "turn.completed", "usage": {}})
elif mode == "noevents":
    with open(out, "w") as f:
        f.write(EMPTY)
'''

GH_MOCK = r"""#!%(python)s
import json, os, sys
S = os.environ["GH_STATE"]
a = sys.argv[1:]
def state(n, default):
    try:
        return json.load(open(os.path.join(S, n)))
    except OSError:
        return default
if a[:1] == ["repo"]:
    print("fixture-org/fixture"); sys.exit(0)
if a[:1] == ["pr"]:
    sys.stdout.write(open(os.path.join(S, "pr.json")).read()); sys.exit(0)
if a[:1] == ["api"]:
    path = a[1]
    method = a[a.index("--method") + 1] if "--method" in a else "POST" if "--input" in a else "GET"  # gh's own default
    if method == "GET" and "/compare/" in path:   # post-review ties the range's base to the PR: --jq .merge_base_commit.sha
        sys.stdout.write(open(os.path.join(S, "mergebase")).read()); sys.exit(0)
    if method == "GET":
        with open(os.path.join(S, "reads"), "a") as f:
            f.write(path + "\\n")
        if os.path.exists(os.path.join(S, "read-fails")):
            print("gh: HTTP 502: Bad Gateway", file=sys.stderr); sys.exit(1)
        if "-i" in a:   # gh.api_list: the status line and headers, a blank line, one page of the list
            sys.stdout.write("HTTP/2.0 200 OK\r\n\r\n" + json.dumps(state("reviews.json", []))); sys.exit(0)
        if path.split("?")[0].endswith("/reviews"):
            print(json.dumps([state("reviews.json", [])]))
        else:
            print(json.dumps({"user": {"login": "fleet-account"}}))   # the PR; every session is its author's account
        sys.exit(0)
    src = a[a.index("--input") + 1]
    raw = sys.stdin.read() if src == "-" else open(src).read()
    payload = json.loads(raw)
    json.dump(payload, open(os.path.join(S, "payload.json"), "w"))
    kind = "unavailable" if payload.get("body", "").startswith("<!-- agent-fabric-engine-unavailable") else "review"
    with open(os.path.join(S, "calls"), "a") as f:
        f.write(f"POST {path} {kind}\n")
    if os.path.exists(os.path.join(S, "post-fails")):
        print("gh: HTTP 502: Bad Gateway", file=sys.stderr); sys.exit(1)
    reviews = state("reviews.json", [])
    reviews.append({"commit_id": payload.get("commit_id"), "body": payload.get("body"), "user": {"login": "fleet-account"},
                    "author_association": "OWNER"})
    json.dump(reviews, open(os.path.join(S, "reviews.json"), "w"))
    print("https://github.com/fixture-org/fixture/pull/7#pullrequestreview-1" if "--jq" in a
          else json.dumps({"html_url": "https://github.com/fixture-org/fixture/pull/7#pullrequestreview-1"}))
    sys.exit(0)
print("mock gh: unhandled " + " ".join(a), file=sys.stderr); sys.exit(1)
"""


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:1500]}"))
        fails += not good

    print("the answer: one JSON object valid against the schema, or a failed review")
    good = {"level": "P2", "file": "a/b.py", "line": 4, "scenario": "s", "expected": "e", "fix": "f"}

    def verdict(text: str) -> str:
        try:
            review_codex.parse_answer(text)
            return "ok"
        except review_codex.FailedReview as e:
            return str(e)

    cov0 = {"paths": [{"path": "a/b.py", "status": "read", "reason": ""}], "lenses": [{"lens": "security", "status": "applied"}], "default": None}
    cov_json = json.dumps(cov0)
    wc = lambda doc: {"coverage": cov0, **doc}  # noqa: E731  # the schema requires coverage: an answer is built with it, so a refusal below is about its one defect
    check("a valid answer passes", verdict(json.dumps(wc({"findings": [good]}))) == "ok")
    check("no findings is a clean answer", verdict(json.dumps(wc({"findings": []}))) == "ok")
    for label, doc in (("a finding without fix", wc({"findings": [{k: v for k, v in good.items() if k != "fix"}]})),
                       ("level P4", wc({"findings": [{**good, "level": "P4"}]})),
                       ("line 0", wc({"findings": [{**good, "line": 0}]})),
                       ("a line that is a string", wc({"findings": [{**good, "line": "4"}]})),
                       ("an empty scenario", wc({"findings": [{**good, "scenario": "  "}]})),
                       ("an extra key on a finding", wc({"findings": [{**good, "confidence": 1}]})),
                       ("an extra top-level key", wc({"findings": [], "summary": "fine"})),
                       ("no findings key", wc({})),
                       ("an absolute file", wc({"findings": [{**good, "file": "/etc/passwd"}]})),
                       ("a file climbing out", wc({"findings": [{**good, "file": "../x.py"}]}))):
        check(f"refused: {label}", verdict(json.dumps(doc)) != "ok", verdict(json.dumps(doc)))
    ok_text = '{"findings": [], "coverage": ' + cov_json + '}'
    for label, text in (("prose", "No findings."), ("a fence", "```json\n" + ok_text + "\n```"),
                        ("two objects", ok_text + ok_text), ("a list", "[]"), ("nothing", ""),
                        ("a duplicate key", '{"findings": [], "findings": [], "coverage": ' + cov_json + '}'),
                        ("NaN", '{"coverage": ' + cov_json + ', "findings": [{"level": "P1", "file": "a", "line": NaN, "scenario": "s", '
                                '"expected": "e", "fix": "f"}]}')):
        check(f"refused: {label}", verdict(text) != "ok", verdict(text))

    print("the run: what codex exec --json printed, judged (streams captured from codex 0.162.1, stand-in endpoint)")
    real_ok = (
        '{"type":"thread.started","thread_id":"01a13195-6c03-7e02-94f7-7a304e1e64d6"}\n{"type":"turn.started"}\n'
        '{"type":"item.started","item":{"id":"item_0","type":"command_execution","command":"/bin/bash -lc \'wc -l a.txt\'",'
        '"aggregated_output":"","exit_code":null,"status":"in_progress"}}\n'
        '{"type":"item.completed","item":{"id":"item_0","type":"command_execution","command":"/bin/bash -lc \'wc -l a.txt\'",'
        '"aggregated_output":"1 a.txt\\n","exit_code":0,"status":"completed"}}\n'
        '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"{\\"findings\\": []}"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":20,"cached_input_tokens":0,"cache_write_input_tokens":0,'
        '"output_tokens":10,"reasoning_output_tokens":0}}\n')
    real_nohost = (
        '{"type":"thread.started","thread_id":"01a13193-6df1-7772-8636-3ea789abff73"}\n'
        '{"type":"item.completed","item":{"id":"item_0","type":"error","message":"Code Mode is unavailable because failed '
        'to spawn code-mode host /home/u/.local/bin/codex-code-mode-host: host executable was not found. Code mode will '
        'fail closed; enable `features.code_mode_host` and install `codex-code-mode-host`."}}\n{"type":"turn.started"}\n'
        '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"{\\"findings\\": []}"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":0,"cache_write_input_tokens":0,'
        '"output_tokens":5,"reasoning_output_tokens":0}}\n')

    def judged(stream: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write(stream)
        try:
            review_codex.judge_run(review_codex.read_events(fh.name))
            return "ok"
        except review_codex.FailedReview as e:
            return str(e)
        finally:
            os.unlink(fh.name)
    check("a run that ran a command and answered is accepted", judged(real_ok) == "ok", judged(real_ok))
    check("the live defect: the tool host missing is refused, and named",
          "its tool host is missing (codex-code-mode-host)" in judged(real_nohost), judged(real_nohost))
    heads_up = ("Heads up: Long threads and multiple compactions can cause the model to be less accurate. "
                "Start a new thread when possible to keep threads small and targeted.")
    check("the advisory's phrase is pinned to Codex 0.162.1's message",
          review_codex.COMPACTION_ADVISORY == "Long threads and multiple compactions"
          and review_codex.COMPACTION_ADVISORY in heads_up)
    advisory_item = ('{"type":"item.completed","item":{"id":"item_9","type":"error","message":"' + heads_up + '"}}\n')
    other_item = '{"type":"item.completed","item":{"id":"item_8","type":"error","message":"something else went wrong"}}\n'

    def read_stream(stream: str) -> "review_codex.CodexRun":
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write(stream)
        try:
            return review_codex.read_events(fh.name)
        finally:
            os.unlink(fh.name)
    with_advisory = real_ok.replace('{"type":"turn.started"}\n', '{"type":"turn.started"}\n' + advisory_item, 1)
    check("the heads-up is counted as an advisory, not as an error",
          (r := read_stream(with_advisory)).advisories == 1 and r.errors == [], (r.advisories, r.errors))
    check("a run with the heads-up, a command and an answer is accepted", judged(with_advisory) == "ok", judged(with_advisory))
    mixed = with_advisory.replace(advisory_item, advisory_item + other_item, 1)
    check("any other error item beside it still refuses", "something else went wrong" in judged(mixed)
          and "Long threads" not in judged(mixed), judged(mixed))
    no_cmd_adv = "\n".join(ln for ln in with_advisory.splitlines() if "command_execution" not in ln)
    check("the heads-up without a command is still 'ran no command'", "ran no command" in judged(no_cmd_adv), judged(no_cmd_adv))
    check("the capacity message as an error item is not an advisory",
          "at capacity" in judged(real_ok.replace('{"type":"turn.started"}\n', '{"type":"turn.started"}\n' + advisory_item.replace(
              heads_up, "Selected model is at capacity"), 1)))
    no_cmd = "\n".join(ln for ln in real_ok.splitlines() if "command_execution" not in ln)
    check("a run with no command is refused", "ran no command" in judged(no_cmd), judged(no_cmd))
    check("a stream that is not JSON shows nothing, and is refused", "printed no events" in judged("not json\n"))

    print("the posted body: engine and model on its first line, findings P1 first")
    body = review_codex.render_review("gpt-x", "a" * 40, "b..c", [
        {**good, "level": "P3", "scenario": "two\nlines"}, {**good, "level": "P1"}])
    first = body.split("\n")[0]
    check("the first line names the engine and the model", "Codex" in first and "`gpt-x`" in first
          and "ADR-053" in first, first)
    check("findings are ordered P1 first and counted",
          body.index("**P1**") < body.index("**P3**") and "Findings: 1 P1, 1 P3." in body, body)
    check("a multi-line field stays on its item's line", "**Scenario:** two lines" in body, body)
    check("no findings is said", "No findings." in review_codex.render_review("m", "a" * 40, "b..c", []))
    check("the first line names the level sent", "**effort:** `high`" in review_codex.render_review(
        "m", "a" * 40, "b..c", [], "high").split("\n")[0])
    check("…or that none was", "**effort:** Codex's default" in review_codex.render_review(
        "m", "a" * 40, "b..c", []).split("\n")[0])
    check("no advisory, no advisory line", "compacted" not in review_codex.render_review("m", "a" * 40, "b..c", []))
    adv_lines = review_codex.render_review("m", "a" * 40, "b..c", [], None, 2).split("\n")
    check("the advisory is one line right after the header lines",
          adv_lines[2].startswith("Each finding is judged") and adv_lines[3] == "" and adv_lines[4]
          == "Codex compacted its context during the run (2 heads-up), so its reading of early files may be less exact."
          and adv_lines[5] == "" and adv_lines[6] == "No findings.", adv_lines[:6])
    check("the prompt tells a cut-off file to be read in parts", "sed -n 'a,bp'" in review_codex.answer_shape()
          and "only then marked \"read\"" in review_codex.answer_shape())

    print("the coverage of the answer: the shipped schema requires it, and the post is a v2 review (agent-fabric ADR-065 §2 C)")
    from github import post_review, review_coverage  # noqa: E402
    real_schema = json.load(open(review_codex.SCHEMA_PATH, encoding="utf-8"))

    def cov_answer(paths, lenses=(("security", "applied"),), findings=()):
        return json.dumps({"findings": list(findings), "coverage": {
            "paths": [{"path": p, "status": st, "reason": r} for p, st, r in paths],
            "lenses": [{"lens": l, "status": st} for l, st in lenses], "default": None}})

    check("the schema as shipped requires coverage", "coverage" in real_schema["required"] and "coverage" in real_schema["properties"])
    found, cov = review_codex.parse_answer_full(cov_answer([("a.py", "read", ""), ("b.py", "not read", "binary")]))
    check("the answer's coverage becomes the block's data", cov.paths == {"a.py": ("read", ""), "b.py": ("not read", "binary")}
          and cov.lenses == {"security": "applied"} and found == [], cov)
    check("parse_answer still gives the findings alone", review_codex.parse_answer(cov_answer([("a.py", "read", "")], findings=[good])) == [good])
    check("the prompt asks for coverage", review_codex.COVERAGE_SHAPE in review_codex.answer_shape()
          and review_codex.answer_shape().startswith(review_codex.ANSWER_SHAPE))
    check("positive control: the same answer with coverage passes", verdict(cov_answer([("a.py", "read", "")], findings=[good])) == "ok")
    full = {"findings": [], "coverage": {"paths": [{"path": "a.py", "status": "read", "reason": ""}], "lenses": [], "default": None}}
    for label, doc in (("no coverage", {"findings": []}),
                       ("coverage null", {**full, "coverage": None}),
                       ("coverage without paths", {**full, "coverage": {"lenses": [], "default": None}}),
                       ("coverage without its default (required, null when not given)", {**full, "coverage": {"paths": full["coverage"]["paths"], "lenses": []}}),
                       ("coverage without lenses", {**full, "coverage": {"paths": full["coverage"]["paths"], "default": None}}),
                       ("a path entry without its reason", {**full, "coverage": {"paths": [{"path": "a.py", "status": "read"}], "lenses": [], "default": None}}),
                       ("a lens entry that carries a reason", {**full, "coverage": {"paths": [], "lenses": [
                           {"lens": "l", "status": "applied", "reason": "x"}], "default": None}}),
                       ("an empty path", {**full, "coverage": {"paths": [{"path": " ", "status": "read", "reason": ""}], "lenses": [], "default": None}})):
        check(f"refused: {label}", verdict(json.dumps(doc)) != "ok", verdict(json.dumps(doc)))
    for label, text in (("a path given twice", cov_answer([("a.py", "read", ""), ("a.py", "read", "")])),
                        ("a status that is neither", cov_answer([("a.py", "skimmed", "")])),
                        ("not read without a reason", cov_answer([("a.py", "not read", "")])),
                        ("a lens state that is neither", cov_answer([("a.py", "read", "")], lenses=(("l", "maybe"),))),
                        ("a lens given twice", cov_answer([], lenses=(("l", "applied"), ("l", "applied"))))):
        check(f"refused: {label}", verdict(text) != "ok" and "coverage" in verdict(text), verdict(text))

    # The dormant path, on a fixture schema without the field: a schema the shipped file no longer is, kept so that the
    # v1 fallback a coverage-less schema takes stays pinned.
    no_cov = json.loads(json.dumps(real_schema))
    del no_cov["properties"]["coverage"]
    no_cov["required"].remove("coverage")
    schema_file = os.path.join(tempfile.mkdtemp(prefix="schema.", dir=os.environ.get("TMPDIR")), "answer.schema.json")
    with open(schema_file, "w", encoding="utf-8") as fh:
        json.dump(no_cov, fh)
    real_path = review_codex.SCHEMA_PATH
    review_codex.SCHEMA_PATH = schema_file
    try:
        check("a schema without the field: the answer's coverage is None and the prompt is the shape alone",
              review_codex.parse_answer_full(json.dumps({"findings": [good]}))[1] is None
              and review_codex.answer_shape() == review_codex.ANSWER_SHAPE)
    finally:
        review_codex.SCHEMA_PATH = real_path
        os.unlink(schema_file)
        os.rmdir(os.path.dirname(schema_file))

    print("the default entry: a range too large to list (the shipped schema: default required, nullable)")
    check("the schema as shipped has the nullable default, required", "default" in real_schema["properties"]["coverage"]["required"]
          and {"type": "null"} in real_schema["properties"]["coverage"]["properties"]["default"]["anyOf"])
    def default_answer(default, paths=(("a.py", "read", ""),)):
        return json.dumps({"findings": [], "coverage": {
            "paths": [{"path": p, "status": st, "reason": r} for p, st, r in paths], "lenses": [], "default": default}})
    check("the prompt offers the default after the coverage shape, in the brief's terms",
          review_codex.answer_shape().endswith(review_codex.COVERAGE_SHAPE + "\n" + review_codex.DEFAULT_SHAPE + "\n")
          and "memory drain" in review_codex.DEFAULT_SHAPE)
    thousand = [(f"memory/slices/{'d' * 40}/{i:04d}-{'x' * 60}.md", "read", "") for i in range(1242)]
    _, cov = review_codex.parse_answer_full(default_answer(None, thousand[:3]))
    check("an answer with \"default\": null is the block it always was: no default key", cov.default is None
          and "default" not in json.loads(review_coverage.render_block(cov).split("\n", 1)[1].rsplit("\n```", 1)[0]), cov)
    try:
        review_coverage.parse_block(json.dumps({"paths": {p: {"status": "read"} for p, _, _ in thousand}, "lenses": {}}))
        listed = "parsed"
    except review_coverage.CoverageError as e:
        listed = str(e)
    check("positive control: listing all 1242 paths is over the block's cap", "over the" in listed, listed)
    _, cov = review_codex.parse_answer_full(default_answer({"status": "read", "reason": ""}, [("special.py", "not read", "binary")]))
    check("a read default is carried into the block next to the one path named",
          cov.default == ("read", "") and cov.paths == {"special.py": ("not read", "binary")}, cov)
    check("…and its rendered block is far under the cap", len(review_coverage.render_block(cov)) < 2000)
    _, cov = review_codex.parse_answer_full(default_answer({"status": "not read", "reason": "generated"}))
    check("a not-read default is carried, and posts as partial", cov.default == ("not read", "generated") and not cov.complete, cov)
    for label, d in (("a default with a key the schema does not list", {"status": "read", "reason": "", "extra": "x"}),
                     ("a not-read default without a reason", {"status": "not read", "reason": ""}),
                     ("a default with a status that is neither", {"status": "skimmed", "reason": ""})):
        try:
            review_codex.parse_answer_full(default_answer(d))
            got = "accepted"
        except review_codex.FailedReview as e:
            got = str(e)
        check(f"refused: {label}", got != "accepted" and "coverage" in got, got)
    # The pinned interpreter has no jsonschema: the stdlib validator must refuse what the schema does not allow.
    real_jsonschema = sys.modules.get("jsonschema", False)
    sys.modules["jsonschema"] = None   # an import then raises ImportError
    try:
        for label, d in (("a default with a key the schema does not list", {"status": "read", "reason": "", "extra": "x"}),
                         ("a default whose reason is not a string", {"status": "read", "reason": 0}),
                         ("a default with a status that is neither", {"status": "skimmed", "reason": ""})):
            try:
                review_codex.parse_answer_full(default_answer(d))
                got = "accepted"
            except review_codex.FailedReview as e:
                got = str(e)
            check(f"without jsonschema, refused: {label}", got != "accepted", got)
        check("positive control: without jsonschema a valid default is still accepted",
              review_codex.parse_answer_full(default_answer({"status": "read", "reason": ""}))[1].default == ("read", ""))
    finally:
        if real_jsonschema is False:
            del sys.modules["jsonschema"]
        else:
            sys.modules["jsonschema"] = real_jsonschema
    # The control: a schema that predates the field. Its answers parse as before and its prompt does not ask for one.
    old_schema = json.loads(json.dumps(real_schema))
    del old_schema["properties"]["coverage"]["properties"]["default"]
    old_schema["properties"]["coverage"]["required"].remove("default")
    schema_file = os.path.join(tempfile.mkdtemp(prefix="schema.", dir=os.environ.get("TMPDIR")), "answer.schema.json")
    with open(schema_file, "w", encoding="utf-8") as fh:
        json.dump(old_schema, fh)
    review_codex.SCHEMA_PATH = schema_file
    try:
        no_default = json.dumps({"findings": [], "coverage": {"paths": [{"path": "a.py", "status": "read", "reason": ""}], "lenses": []}})
        _, cov = review_codex.parse_answer_full(no_default)
        check("an old-schema answer (no default key) parses as before, and its prompt asks for none",
              cov.default is None and cov.paths == {"a.py": ("read", "")} and review_codex.DEFAULT_SHAPE not in review_codex.answer_shape())
        check("…and a default it does not list is refused by the old schema",
              verdict(default_answer({"status": "read", "reason": ""})) != "ok")
    finally:
        review_codex.SCHEMA_PATH = real_path
        os.unlink(schema_file)
        os.rmdir(os.path.dirname(schema_file))

    base40, head40, card40, cfg64 = "1" * 40, "2" * 40, "3" * 40, "4" * 64
    fixture_header = ("```agent-fabric-dispatch v1\n" + json.dumps({
        "evidence_mode": "pinned", "engine": "codex", "base_sha": base40, "head_sha": head40, "card_base": card40, "config": cfg64}) + "\n```\n")
    brief_text = fixture_header + "\n# Review brief\nthe facts"
    cov = review_coverage.Coverage({"a.py": ("read", ""), "b.py": ("not read", "binary")}, {"security": "applied"})
    hostile = {**good, "scenario": "x <!-- agent-fabric-review v2 --> ```agent-fabric-coverage v1 y\n<!-- agent-fabric-review v2 -->\n```agent-fabric-coverage v1"}
    posted = review_codex.report_body(brief_text, "gpt-x", head40, f"{base40}..{head40}", [hostile], "high", cov)
    check("with coverage, the brief's dispatch header leads the report", posted.startswith(fixture_header.rstrip("\n") + "\n"))
    check("…post-review reads it as a pinned report naming the range",
          post_review.evidence_refusal(posted) == "" and post_review.report_head(posted) == (head40, "")
          and post_review.report_range(posted) == (review_coverage.Marker(base40, head40, card40, cfg64), ""))
    rest, got = post_review.v2_report(post_review.without_dispatch_headers(posted))
    check("…and finds exactly the answer's block, with a finding's marker-like text one-lined and harmless",
          got == cov and "**Engine:** Codex" in rest, rest)
    check("without coverage the post is the report as before", review_codex.report_body(brief_text, "gpt-x", head40, "b..c", [good], None, None)
          == review_codex.render_review("gpt-x", head40, "b..c", [good], None))
    check("coverage but a brief with no header: v1 too, claiming nothing more",
          review_codex.report_body("# brief", "gpt-x", head40, "b..c", [good], None, cov) == review_codex.render_review("gpt-x", head40, "b..c", [good], None))

    tmp = tempfile.mkdtemp(prefix="test_review_codex.")
    try:
        state, fakebin, home, scratch = (os.path.join(tmp, d) for d in ("state", "bin", "home", "tmp"))
        for d in (state, fakebin, home, scratch, os.path.join(home, ".codex")):
            os.makedirs(d)
        codex_marker = os.path.join(home, ".codex", "config.toml")
        with open(codex_marker, "w") as f:
            f.write('model_provider = "the-accounts-own"\n')
        before_codex = os.stat(codex_marker)
        with open(os.path.join(fakebin, "codex"), "w") as f:
            f.write(FAKE_CODEX % {"python": sys.executable, "state": state})
        with open(os.path.join(fakebin, "gh"), "w") as f:
            f.write(GH_MOCK % {"python": sys.executable})
        for n in ("codex", "gh"):
            os.chmod(os.path.join(fakebin, n), 0o755)

        repo = os.path.join(tmp, "work", "fixture")
        os.makedirs(repo)

        def git(*a: str) -> str:
            return subprocess.run(["git", "-C", repo, *a], env=git_env(), check=True, capture_output=True,
                                  text=True, timeout=30).stdout.strip()

        git("init", "-q", "-b", "main")
        git("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "base")
        base = git("rev-parse", "HEAD")
        with open(os.path.join(repo, "app.py"), "w") as f:
            f.write("print(1)\nprint(2)\n")
        git("add", "app.py")
        git("commit", "-q", "--no-gpg-sign", "-m", "work")
        head = git("rev-parse", "HEAD")
        # An uncommitted file: the extract is the head, never the working copy.
        with open(os.path.join(repo, "wip.txt"), "w") as f:
            f.write("not committed\n")
        status_before = git("status", "--porcelain")

        req = os.path.join(tmp, "req", "REQUEST.yaml")
        os.makedirs(os.path.dirname(req))
        with open(req, "w") as f:
            f.write(f"mode: review\nrepository: {repo}\nrange: {base[:12]}..{head[:12]}\n"
                    "objective: >-\n  The app prints two lines.\nrequirements:\n  - It prints 1 then 2.\n")

        host = subprocess.run(["hostname", "-s"], capture_output=True, text=True, check=True).stdout.strip()
        me = f"{host}/{pwd.getpwuid(os.geteuid()).pw_name}"

        def set_pr(oid: str = head) -> None:
            with open(os.path.join(state, "pr.json"), "w") as f:
                json.dump({"number": 7, "state": "OPEN", "headRefName": f"{me}/feat/thing", "headRefOid": oid,
                           "baseRefName": "main", "author": {"login": "fleet-account"}}, f)
            with open(os.path.join(state, "mergebase"), "w") as f:
                f.write(base)
            for n in ("calls", "payload.json", "codex-run.json", "codex-calls", "grandchild", "sandbox-calls", "sandbox-mode",
                      "reviews.json", "read-fails", "post-fails", "reads"):
                if os.path.exists(os.path.join(state, n)):
                    os.remove(os.path.join(state, n))

        def mode(m: str) -> None:
            with open(os.path.join(state, "mode"), "w") as f:
                f.write(m)

        # The routing overlay and the review grade are the fixture's (instance data, ADR-045), and this login's
        # state (its binding, its local layer) a directory of the test's own: routing answers from the engine's
        # committed column, the openai one included, and nothing the real account has set.
        operator = os.path.join(tmp, "operator")
        os.makedirs(os.path.join(operator, "routing"))
        write_routing_overlay(os.path.join(operator, "routing"))
        fabric_state = os.path.join(tmp, "fabric-state")
        local_layer = os.path.join(fabric_state, "agents", pwd.getpwuid(os.geteuid()).pw_name, "model-profile.local.json")
        os.makedirs(os.path.dirname(local_layer))
        env0 = {k: v for k, v in os.environ.items()
                if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "ANTHROPIC_", "CLAUDE", "OPENAI_", "CODEX_"))}
        env0["PYTHONDONTWRITEBYTECODE"] = "1"      # the engine's children import the real tools/fabric modules: no __pycache__ into the checkout
        env0.update(PATH=f"{fakebin}:{env0.get('PATH', '')}", GH_STATE=state, GH_REPO="fixture-org/fixture",
                    HOME=home, TMPDIR=scratch, AGENT_FABRIC_ROOT=ROOT, AGENT_FABRIC_OPERATOR=operator,
                    AGENT_FABRIC_STATE_DIR=fabric_state,
                    AGENT_FABRIC_CODEX_BASE_URL="http://127.0.0.1:18080",
                    AGENT_FABRIC_CODEX_KEY="gw-local-key-123", AGENT_FABRIC_CODEX_MODEL="gpt-test",
                    # What a session carries and Codex must never see.
                    ANTHROPIC_BASE_URL="http://127.0.0.1:9999", ANTHROPIC_API_KEY="sk-ant-session",
                    ANTHROPIC_AUTH_TOKEN="sk-ant-token", CLAUDE_CODE_OAUTH_TOKEN="oauth-session",
                    OPENAI_API_KEY="sk-openai-account", OPENAI_BASE_URL="https://api.openai.com/v1",
                    CODEX_HOME=os.path.join(home, ".codex"), FABRIC_SESSION_SECRET="s3cret")

        def run(*args: str, env: dict | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
            return subprocess.run([REVIEW, "--engine", "codex", *args], env=env or env0, capture_output=True,
                                  text=True, cwd=repo, timeout=timeout)

        def shown(text: str) -> str:
            """--no-post prints the report as post-review is given it, the brief's dispatch header first (a v2 report)."""
            return post_review.without_dispatch_headers(text)

        def scratch_empty() -> bool:
            return os.listdir(scratch) == []

        def codex_ran() -> bool:
            return os.path.exists(os.path.join(state, "codex-calls"))

        def record() -> dict:
            with open(os.path.join(state, "codex-run.json")) as f:
                return json.load(f)

        def payload_body() -> str:
            try:
                with open(os.path.join(state, "payload.json")) as f:
                    return json.load(f).get("body", "")
            except (OSError, ValueError):
                return ""

        def post_lines() -> list[str]:
            try:
                with open(os.path.join(state, "calls")) as f:
                    return f.read().splitlines()
            except OSError:
                return []

        def posts() -> int:
            return sum(1 for ln in post_lines() if not ln.endswith(" unavailable"))

        def unavailables() -> int:
            return sum(1 for ln in post_lines() if ln.endswith(" unavailable"))

        def posted() -> bool:
            return posts() > 0

        print("success: Codex runs once, read-only, on the extract, and the review is posted")
        set_pr(); mode("ok")
        r = run("7", req)
        check("exit 0", r.returncode == 0, r.stderr + r.stdout)
        with open(os.path.join(state, "codex-calls")) as f:
            check("codex ran exactly once", f.read() == "run\n")
        rec = record()
        argv = rec["argv"]
        check("codex exec names no --sandbox: the profile in CODEX_HOME's config.toml is the sandbox (audit F01)",
              argv[:1] == ["exec"] and "--sandbox" not in argv and "-s" not in argv and "--dangerously-bypass-approvals-and-sandbox" not in argv, argv)
        check("--json: the event stream is what shows the run read the code", "--json" in argv, argv)
        check("--output-schema hands it the answer schema",
              argv[argv.index("--output-schema") + 1] == review_codex.SCHEMA_PATH, argv)
        check("the model is asked for by name", argv[argv.index("--model") + 1] == "gpt-test", argv)
        check("the prompt is read from stdin", argv[-1] == "-", argv)
        check("it runs in the extract of the head, outside the working copy",
              rec["cwd"].startswith(os.path.realpath(scratch) + "/") and argv[argv.index("--cd") + 1] == rec["cwd"],
              rec["cwd"])
        check("the extract holds the head's files and not the uncommitted one",
              rec["cwd_files"] == ["app.py"], rec["cwd_files"])
        # In process, not through `fabric-review brief`: the CLI also checks the head out and names that worktree,
        # which the second engine does not (it reads its own extract, so the brief it sends names none).
        with open(req, encoding="utf-8") as fh:
            brief = review_codex.review_brief.render(review_codex.review_brief.parse_request(fh.read()), engine="codex")
        # The dispatch header differs per render (its id, its time) and per engine
        # (codex, second-engine-review); everything after it is the brief unchanged.
        def after_header(text: str) -> str:
            return text.split("\n```\n", 1)[1] if text.startswith("```agent-fabric-dispatch v1\n") else text
        sent_header = rec["prompt"].split("\n```\n", 1)[0]
        check("the prompt opens with a dispatch header naming the second engine",
              '"engine": "codex"' in sent_header and '"purpose": "second-engine-review"' in sent_header, sent_header)
        check("the prompt is the rendered brief, unchanged, then the answer shape",
              bool(brief) and after_header(rec["prompt"]) == after_header(brief).rstrip("\n") + "\n" + review_codex.answer_shape(), rec["prompt"][-400:])
        cenv = rec["env"]
        leaked = sorted(k for k in cenv if k.startswith(("ANTHROPIC_", "CLAUDE", "OPENAI_"))
                        or k in ("FABRIC_SESSION_SECRET", "GH_STATE", "AGENT_FABRIC_CODEX_BASE_URL"))
        check("no session credential or unlisted variable reaches Codex", not leaked, leaked)
        check("no session secret value reaches Codex",
              not any(v in json.dumps(cenv) for v in ("sk-ant-session", "sk-ant-token", "oauth-session",
                                                      "sk-openai-account", "s3cret", "127.0.0.1:9999")), cenv)
        check("the gateway key reaches it by environment variable", cenv.get("AGENT_FABRIC_CODEX_KEY") == "gw-local-key-123")
        check("CODEX_HOME and HOME are the scratch's, never ~/.codex",
              cenv.get("CODEX_HOME", "").startswith(os.path.realpath(scratch) + "/")
              and cenv.get("HOME", "").startswith(os.path.realpath(scratch) + "/"), cenv)
        cfg = rec["config"] or ""
        check("config.toml names the gateway's root as a Responses provider",
              'model_provider = "fabric-gateway"' in cfg and "[model_providers.fabric-gateway]" in cfg
              and 'base_url = "http://127.0.0.1:18080"' in cfg and 'wire_api = "responses"' in cfg
              and 'env_key = "AGENT_FABRIC_CODEX_KEY"' in cfg, cfg)
        check("…and never the key itself", "gw-local-key-123" not in cfg, cfg)
        check("no account id set: no http_headers in config.toml", "http_headers" not in cfg and "ChatGPT-Account-ID" not in cfg, cfg)
        check("the environment's gateway: no reasoning level unless one is asked for, as before (review of #224, F2)",
              not any(a.startswith("model_reasoning_effort") for a in argv) and "-c" not in argv, argv)

        after_codex = os.stat(codex_marker)
        check("~/.codex is untouched", (after_codex.st_mtime_ns, after_codex.st_size)
              == (before_codex.st_mtime_ns, before_codex.st_size))
        check("the scratch is removed", scratch_empty(), os.listdir(scratch))
        check("the working copy is untouched", git("status", "--porcelain") == status_before
              and git("rev-parse", "HEAD") == head)
        b = payload_body()
        lines = b.split("\n")
        check("posted with the v2 review marker and --model codex",
              re.fullmatch(r"<!-- agent-fabric-review v2 base=[0-9a-f]{40} head=%s card=[0-9a-f]{40} config=[0-9a-f]{64} -->" % head, lines[0])
              is not None and lines[1] == "<!-- model: codex -->", lines[:3])
        rest_v2, block = post_review.v2_report("\n".join(lines[2:]))
        check("…the answer's coverage is the posted block, and the dispatch header is not in the body",
              block == review_coverage.Coverage({"app.py": ("read", "")}, {}) and "agent-fabric-dispatch" not in b, b[-500:])
        check("the post names Codex, not the review class", "Codex, the second review engine" in b, b[:400])
        check("recorded on the head Codex read (post-review --head, ADR-020 §5 rule 6)",
              json.load(open(os.path.join(state, "payload.json"))).get("commit_id") == head)
        body_first = next((ln for ln in lines if ln.startswith("**Engine:**")), "")
        check("the review's own first line names engine and model, after post-review's header",
              "Codex" in body_first and "`gpt-test`" in body_first and head[:12] in body_first, b)
        check("the findings are there, P1 first",
              "**P1** `app.py:1`" in b and b.index("**P1**") < b.index("**P3**"), b)

        # run_codex itself, its scratch kept: the CLI removes the scratch, so only here can the two files be read
        # (review of #229, F2).
        print("Codex's stdout is the event stream alone; its log lines on stderr are kept apart")
        set_pr(); mode("ok")
        kept = tempfile.mkdtemp(prefix="run-codex.", dir=tmp)
        os.makedirs(os.path.join(kept, "head"))
        answer_text = review_codex.run_codex(os.path.join(fakebin, "codex"), "gpt-test", os.path.join(kept, "head"), kept,
                                             {"PATH": os.environ.get("PATH", "")}, "brief", 60)
        with open(os.path.join(kept, "codex-events.jsonl"), encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]

        def is_json(line: str) -> bool:
            try:
                return isinstance(json.loads(line), dict)
            except ValueError:
                return False
        check("every line of the events file is one JSON event, and there are some",
              bool(lines) and all(is_json(ln) for ln in lines), lines)
        with open(os.path.join(kept, "codex.log"), encoding="utf-8") as fh:
            check("the log line went to codex.log", "WARN codex_core: a log line" in fh.read())
        check("…and the run, which read the code, gives its answer", '"P1"' in answer_text, answer_text)

        print("the sandbox is proved before the run, no wider one is used, Codex's own egress is off")
        set_pr(); mode("ok")
        r = run("7", req)
        check("a review runs", r.returncode == 0, r.stderr + r.stdout)
        with open(os.path.join(state, "sandbox-calls")) as f:
            probes = [json.loads(line) for line in f]
        check("three probes in the extract, the reviewer profile: a command starts, a write is refused, a read outside is refused",
              len(probes) == 3 and all(p[:3] == ["sandbox", "-P", "reviewer"] for p in probes)
              and probes[0][-1] == "exit 42" and "touch" in probes[1][-3] and probes[1][-3].endswith("exit 43")
              and probes[0][probes[0].index("-C") + 1] == record()["cwd"], probes)
        probe_path = probes[1][-1]
        check("the write is tried at a fresh random name inside the extract (a pull request cannot plant it)",
              probe_path.startswith(record()["cwd"] + os.sep) and os.path.basename(probe_path).startswith(".fabric-write-probe-")
              and len(os.path.basename(probe_path)) > len(".fabric-write-probe-") + 8, probe_path)
        cfg = record()["config"] or ""
        check("config.toml switches off the plugin, app and update features (Codex's own fetch from GitHub)",
              "[features]\n" in cfg and all(f"{name} = false\n" in cfg.split("[features]\n", 1)[1] for name in review_codex.EGRESS_FEATURES)
              and "plugins = false\n" in cfg, cfg)
        with open(review_codex.__file__, encoding="utf-8") as fh:
            module_source = fh.read()
        check("the module names no wider sandbox mode",
              not any(w in module_source for w in ("danger", "workspace-write", "full-access", "--yolo", "bypass")))
        for label, smode, text in (("a sandbox that cannot start", "fail",
                                    "the read-only sandbox cannot start (exit 1: bwrap: No permissions to create a new namespace [key]); no wider one is used"),
                                   ("a sandbox that lets a write through", "writable", "the read-only sandbox cannot refuse a write (exit 7")):
            set_pr(); mode("ok")
            with open(os.path.join(state, "sandbox-mode"), "w") as f:
                f.write(smode)
            r = run("7", req)
            check(f"{label}: exit 1, said in one line, codex exec never started, nothing posted, the scratch removed",
                  r.returncode == 1 and text in r.stderr and not codex_ran() and not posted() and scratch_empty(),
                  (r.returncode, r.stderr[-400:], codex_ran(), posted(), os.listdir(scratch)))
            check(f"{label}: the key is not in the message", "gw-local-key-123" not in r.stderr, r.stderr)
        set_pr(); mode("ok")
        with open(os.path.join(state, "sandbox-mode"), "w") as f:
            f.write("ok")
        check("the positive control: with a sandbox that behaves, the same review is posted", run("7", req).returncode == 0 and posted())

        print("prove_sandbox called directly: the probes that need no whole review (review of #231, F4 F5)")
        fake_codex = os.path.join(fakebin, "codex")
        proof_env = {"PATH": os.environ.get("PATH", ""), review_codex.ENV_KEY: "gw-local-key-123"}

        def prove(smode: str, work: str | None = None) -> str:
            """prove_sandbox against the fake in `smode`: "ok", or the FailedReview's message."""
            with open(os.path.join(state, "sandbox-mode"), "w") as f:
                f.write(smode)
            for n in ("sandbox-calls", "sandbox-grandchild"):
                if os.path.exists(os.path.join(state, n)):
                    os.remove(os.path.join(state, n))
            work = work or tempfile.mkdtemp(prefix="extract.", dir=tmp)
            try:
                review_codex.prove_sandbox(fake_codex, work, proof_env)
                return "ok"
            except review_codex.FailedReview as e:
                return str(e)

        check("a sandbox that behaves passes", prove("ok") == "ok")
        verdict_noop = prove("noop")
        check("a sandbox that exits 0 without running anything proves nothing (the start probe has an exit status of its own)",
              "cannot start (ran nothing it was asked" in verdict_noop, verdict_noop)
        work = tempfile.mkdtemp(prefix="extract.", dir=tmp)
        verdict_leaky = prove("leaky", work)
        check("a sandbox that lets the write happen and still answers 'refused' is caught by the file left behind",
              "let a write through" in verdict_leaky, verdict_leaky)
        for label, plant in (("a file", lambda path: open(path, "w").close()),
                             ("a dangling link", lambda path: os.symlink("/nonexistent/target", path)),
                             ("a link to /dev/null", lambda path: os.symlink("/dev/null", path))):
            work = tempfile.mkdtemp(prefix="extract.", dir=tmp)
            plant(os.path.join(work, ".fabric-write-probe"))
            check(f"{label} at the old fixed probe name, planted by the PR, does not make a sound sandbox look broken",
                  prove("ok", work) == "ok", prove("ok", work))
        names = set()
        for _ in range(3):
            prove("ok")
            with open(os.path.join(state, "sandbox-calls")) as f:
                names.add(json.loads(f.read().splitlines()[1])[-1])
        check("every proof tries the write at a name of its own", len(names) == 3, names)
        saved_timeout = review_codex.SANDBOX_PROOF_TIMEOUT_S
        review_codex.SANDBOX_PROOF_TIMEOUT_S = 1
        try:
            started = time.time()
            verdict_slow = prove("sleep")
        finally:
            review_codex.SANDBOX_PROOF_TIMEOUT_S = saved_timeout
        check("a probe that outlives its time budget fails the proof, in about that time",
              "the read-only sandbox did not start within 1 s; no wider one is used" in verdict_slow and time.time() - started < 30, verdict_slow)
        with open(os.path.join(state, "sandbox-grandchild")) as f:
            pids = [int(x) for x in f.read().split()]
        def running(pid):
            # A killed orphan is a zombie until PID 1 reaps it, and a container's PID 1 may never: dead for this check.
            try:
                with open(f"/proc/{pid}/stat", "rb") as f:
                    return f.read().rsplit(b")", 1)[1].split()[0] != b"Z"
            except (FileNotFoundError, ProcessLookupError):
                return False
        deadline = time.time() + 10
        alive = list(pids)
        while alive and time.time() < deadline:
            alive = [pid for pid in alive if running(pid)]
            if alive:
                time.sleep(0.05)
        check("…and the probe's whole process group is ended, the grandchild too", not alive, alive)

        print("the account id and the effort")
        acct = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
        set_pr(); mode("empty")
        r = run("7", req, "--no-post", "--effort", "xhigh", env={**env0, "AGENT_FABRIC_CODEX_ACCOUNT_ID": acct})
        rec = record()
        cfg = rec["config"] or ""
        check("exit 0", r.returncode == 0, r.stderr)
        check("the account id reaches config.toml as the provider's ChatGPT-Account-ID header",
              f'http_headers = {{ "ChatGPT-Account-ID" = "{acct}" }}' in cfg
              and cfg.index("http_headers") > cfg.index("[model_providers.fabric-gateway]"), cfg)
        check("…and only there: not in Codex's environment or argv",
              acct not in json.dumps(rec["env"]) and acct not in json.dumps(rec["argv"]), rec["env"])
        check("--effort sets the level", 'model_reasoning_effort="xhigh"' in rec["argv"], rec["argv"])
        set_pr(); mode("empty")
        r = run("7", req, "--no-post", env={**env0, "AGENT_FABRIC_CODEX_EFFORT": "low"})
        check("AGENT_FABRIC_CODEX_EFFORT sets it too", 'model_reasoning_effort="low"' in record()["argv"], r.stderr)
        set_pr(); mode("ok")
        r = run("7", req, "--effort", "extreme")
        check("an unknown --effort is a usage error, nothing runs", r.returncode == 2 and not codex_ran(), r.stderr)
        r = run("7", req, "--codex-home", home)
        check("--codex-home without --gateway is a usage error", r.returncode == 2 and not codex_ran(), r.stderr)
        r = run("7", req, "--gateway", "openai")
        check("an unknown --gateway is a usage error", r.returncode == 2 and "chatgpt" in r.stderr and not codex_ran(), r.stderr)

        print("coverage that post-review checks against the range: partial posts as partial, a wrong path set posts nothing")
        set_pr(); mode("partialcov")
        r = run("7", req)
        pb = payload_body().split("\n")
        check("a path not read: exit 0, posted v2 with the partial line after the marker",
              r.returncode == 0 and posted() and pb[0].startswith("<!-- agent-fabric-review v2 ")
              and pb[1] == "partial coverage: 1 path(s) not read", (r.stderr, pb[:3]))
        set_pr(); mode("wrongpaths")
        r = run("7", req)
        check("a path set that is not the range's: refused by post-review, nothing posted",
              r.returncode != 0 and not posted() and "not posting this report" in r.stderr, (r.returncode, r.stderr))

        print("--no-post prints the review and posts nothing")
        set_pr(); mode("empty")
        r = run("7", req, "--no-post")
        check("exit 0 and the body on stdout", r.returncode == 0 and shown(r.stdout).startswith("**Engine:** Codex")
              and "No findings." in r.stdout, r.stderr + r.stdout)
        check("nothing posted", not posted())

        print("labels: a full review numbers its findings past every label the PR's reviews used (ADR-065 §5 rule 5)")
        def labels(text: str) -> list[str]:
            return re.findall(r"^Finding: (F\d+) ", text, re.M)

        def seed_reviews(*reviews: dict) -> None:
            with open(os.path.join(state, "reviews.json"), "w") as f:
                json.dump([{"user": {"login": "fleet-account"}, "author_association": "OWNER", **r} for r in reviews], f)

        def earlier(rid: int, *lines: str) -> dict:
            # A v2 report of an earlier head, as the Claude reviews are: the reader skips a review with no marker.
            marker = review_coverage.format_marker(chr(96 + rid) * 40, chr(97 + rid) * 40, "d" * 40, "e" * 64)
            return {"id": rid, "submitted_at": f"2026-10-3{rid}T00:00:00Z", "body": marker + "\nreport\n" + "\n".join(lines) + "\n"}

        set_pr(); mode("ok")
        r = run("7", req, "--no-post")
        check("control: a PR with no reviews starts at F1", r.returncode == 0 and labels(r.stdout) == ["F1", "F2"],
              (r.stderr, r.stdout))
        set_pr(); mode("ok")
        seed_reviews(earlier(1, *(f"Finding: F{n} | P3 | likely | a.txt:1 | s{n}" for n in range(1, 6))),
                     earlier(2, *(f"Judgement: F{n} | fixed | gone" for n in range(1, 6)),
                             *(f"Finding: F{n} | P2 | certain | a.txt:1 | s{n}" for n in range(6, 10))))
        r = run("7", req, "--no-post")
        check("a PR whose reviews used up to F9: the Codex findings are F10 and F11", r.returncode == 0
              and labels(r.stdout) == ["F10", "F11"], (r.stderr, r.stdout))
        check("…and the prose list carries the same labels as the machine lines",
              re.findall(r"^(F\d+)\. \*\*P\d\*\*", r.stdout, re.M) == ["F10", "F11"], r.stdout)
        asked: list = []
        saved_cf = review_codex.review_brief.carried_findings
        review_codex.review_brief.carried_findings = lambda pr, head, repo: (asked.append(pr), ({"findings": [], "next": 4}, []))[1]
        try:
            check("the labels are read from the PR the review is posted to, not the one the request names",
                  review_codex.label_start({"mode": "review", "pr": 12, "repository": "r"}, "h", "7") == 4 and asked == [7], asked)
            check("a request that is no full review is not asked", review_codex.label_start({"mode": "re-review", "repository": "r"}, "h", "7") == 1
                  and asked == [7], asked)
        finally:
            review_codex.review_brief.carried_findings = saved_cf
        set_pr(); mode("ok")
        seed_reviews(earlier(1, "Finding: F9 | P2 | certain | a.txt:1 | s9"))
        r = run("7", req)
        check("…and the posted review carries the same labels", r.returncode == 0 and posted()
              and labels(payload_body()) == ["F10", "F11"], (r.stderr, payload_body()))
        set_pr(); mode("ok"); open(os.path.join(state, "read-fails"), "w").close()
        r = run("7", req)
        check("reviews that cannot be listed: refused, exit 1, nothing posted", r.returncode == 1 and not posted()
              and "cannot be listed" in r.stderr and "leave pr out" not in r.stderr and "carried" not in r.stderr, (r.returncode, r.stderr))
        set_pr(); mode("ok"); open(os.path.join(state, "read-fails"), "w").close()
        r = run("7", req, "--no-post")
        check("…--no-post prints no report either", r.returncode == 1 and r.stdout == "", (r.returncode, r.stdout))
        set_pr(); mode("ok")
        seed_reviews(earlier(1, "Finding: F9 | P2 | certain | a.txt:1 | s9"), {"id": 2, "submitted_at": "2026-10-32T00:00:00Z", "body": None})
        r = run("7", req)
        check("a listed review that cannot be read: refused, exit 1, nothing posted", r.returncode == 1 and not posted()
              and "cannot be read" in r.stderr and "review 2" in r.stderr and "leave pr out" not in r.stderr
              and "re-post" not in r.stderr, (r.returncode, r.stderr))

        print("the compaction heads-up: posted with the advisory line; with any other error or no command, a failed review")
        set_pr(); mode("compaction")
        r = run("7", req)
        pbody = payload_body()
        check("exit 0, posted, the report says Codex compacted", r.returncode == 0 and posted()
              and "Codex compacted its context during the run (1 heads-up)" in pbody, r.stderr)
        for m, why in (("compaction-other", "something else went wrong"),
                       ("compaction-nocommand", "ran no command that succeeded (0 failed)")):
            set_pr(); mode(m)
            r = run("7", req)
            check(f"{m}: exit 1, nothing posted, the reason said", r.returncode == 1 and not posted() and why in r.stderr, r.stderr)

        for m in ("retried", "eventonly"):
            print(f"a run that read the code ({m}) is posted")
            set_pr(); mode(m)
            r = run("7", req)
            check("exit 0, posted, no findings said", r.returncode == 0 and posted() and "No findings." in payload_body(),
                  r.stderr)

        for m, why in (("prose", "not one JSON object"), ("fence", "not one JSON object"),
                       ("badschema", "codex-answer.schema.json"), ("nocoverage", "missing required 'coverage'"),
                       ("exit1", "exited 3: backend said no"),
                       ("noanswer", "without an agent message"),
                       ("nohost", "Codex ran no command: its tool host is missing (codex-code-mode-host)"),
                       ("nocommand", "ran no command that succeeded (0 failed)"),
                       ("cmdfailed", "ran no command that succeeded (1 failed)"),
                       ("othererror", "something else went wrong"),
                       ("turnfailed", "exited 1: stream disconnected"),
                       ("noevents", "printed no events")):
            print(f"a failed review ({m}): nothing posted, the reason said")
            set_pr(); mode(m)
            r = run("7", req)
            check("exit 1", r.returncode == 1, r.stderr)
            check("the reason is said", "nothing posted" in r.stderr and why in r.stderr, r.stderr)
            check("nothing posted", not posted())
            check("the scratch is removed", scratch_empty(), os.listdir(scratch))

        print("a failed turn's message is the backend's text: said on one line, bounded (review of #229, F3)")
        set_pr(); mode("turnfailed-long")
        r = run("7", req)
        said = next((ln for ln in r.stderr.splitlines() if "codex exited 1" in ln), "")
        check("exit 1, nothing posted, the message on the reason's line and cut",
              r.returncode == 1 and not posted() and "first line second line" in said and "x" * 600 not in r.stderr
              and "second line" not in r.stderr.replace(said, ""), r.stderr[:800])

        print("the model is unavailable: at capacity is retried after 10, 20, 60 s; the allowance is reported, not retried")

        def inproc(*args: str) -> tuple[int, str, str, list[float]]:
            """main() in this process, so the waits can be replaced: the environment, directory and handlers are
            the run()'s own, and put back."""
            sleeps: list[float] = []
            saved_env, saved_cwd = dict(os.environ), os.getcwd()
            saved_sig = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}
            saved_sleep = review_codex._sleep
            review_codex._sleep = sleeps.append
            out, err = io.StringIO(), io.StringIO()
            try:
                os.environ.clear()
                os.environ.update(env0)
                os.chdir(repo)
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = review_codex.main(["codex", *args])
            finally:
                review_codex._sleep = saved_sleep
                os.chdir(saved_cwd)
                os.environ.clear()
                os.environ.update(saved_env)
                for s, h in saved_sig.items():
                    signal.signal(s, h)
            return rc, out.getvalue(), err.getvalue(), sleeps

        def runs_made() -> int:
            try:
                with open(os.path.join(state, "codex-calls")) as f:
                    return len(f.read().split())
            except OSError:
                return 0

        set_pr(); mode("capacity ok")
        rc, out, err, sleeps = inproc("7", req)
        check("capacity once, then success: exit 0, one wait of 10 s, two runs, posted once",
              rc == 0 and sleeps == [10] and runs_made() == 2 and posts() == 1, (rc, sleeps, runs_made(), posts(), err))
        check("…the scratch is removed", scratch_empty(), os.listdir(scratch))
        set_pr(); mode("capacity capacity capacity ok")
        rc, out, err, sleeps = inproc("7", req)
        check("capacity three times, then success: waits 10, 20, 60 s, four runs, posted once",
              rc == 0 and sleeps == [10, 20, 60] and runs_made() == 4 and posts() == 1, (rc, sleeps, runs_made(), posts(), err))
        set_pr(); mode("capacity")
        rc, out, err, sleeps = inproc("7", req)
        check("capacity on every run: exit 3, the same three waits, four runs, nothing posted",
              rc == 3 and sleeps == [10, 20, 60] and runs_made() == 4 and posts() == 0, (rc, sleeps, runs_made(), posts(), err))
        check("…it says the model is unavailable, at capacity, the provider's, and what Codex said",
              "model is unavailable: at capacity" in err and "transient" in err and "after 4 run(s)" in err
              and "Selected model is at capacity" in err and "no review posted" in err, err)
        check("…the scratch is removed", scratch_empty(), os.listdir(scratch))
        set_pr(); mode("allowance")
        rc, out, err, sleeps = inproc("7", req)
        check("over the allowance: exit 3 at once — no wait, one run, nothing posted",
              rc == 3 and sleeps == [] and runs_made() == 1 and posts() == 0, (rc, sleeps, runs_made(), posts(), err))
        check("…it says the allowance, ours, with the reset time the message gave",
              "over the allowance" in err and "Oct 14th, 2026 3:12 PM" in err and "not retried" in err, err)
        check("…the outcome is one stderr line: posted", "unavailable statement on PR #7: posted" in err, err)
        mode("allowance")
        rc, out, err, sleeps = inproc("7", req)
        check("…and the second run says one already stands", "unavailable statement on PR #7: an unavailable statement for this head stands" in err, err)
        set_pr(); mode("allowance-notime")
        rc, out, err, sleeps = inproc("7", req)
        check("…a message without a time says there is none, and invents none",
              rc == 3 and "over the allowance" in err and "no reset time" in err and "2026" not in err, err)
        set_pr(); mode("capacity allowance")
        rc, out, err, sleeps = inproc("7", req)
        check("capacity, then the allowance: one wait, then stopped as the allowance",
              rc == 3 and sleeps == [10] and runs_made() == 2 and "over the allowance" in err, (rc, sleeps, err))
        for m, why in (("turnfailed", "an ordinary failed turn"), ("capacity-lookalike", "'at capacity' in another sentence"),
                       ("capacity-item", "the capacity text in an error item of a turn that went on"),
                       ("exit1", "a non-zero exit with no failed turn")):
            set_pr(); mode(m)
            rc, out, err, sleeps = inproc("7", req)
            check(f"{why}: a failed review, exit 1, never retried",
                  rc == 1 and sleeps == [] and runs_made() == 1 and posts() == 0 and "unavailable" not in err,
                  (rc, sleeps, runs_made(), err))
        set_pr(); mode("allowance")
        r = run("7", req)
        check("through the installed entry point: exit 3, the kind said on stderr, nothing on stdout, nothing posted",
              r.returncode == 3 and "over the allowance" in r.stderr and r.stdout == "" and not posted(), (r.returncode, r.stderr))
        for label, msg, want in (
                ("capacity", "Selected model is at capacity. Please try a different model.", ("capacity", None)),
                ("usage limit with a time", "You\u2019ve hit your usage limit. Upgrade to Plus to continue using Codex "
                 "(https://chatgpt.com/explore/plus), or try again at Oct 14th, 2026 3:12 PM.", ("allowance", "Oct 14th, 2026 3:12 PM")),
                ("usage limit, 'Try again at'", "You\u2019ve hit your usage limit. Try again at Nov 2nd, 2026 9:00 AM.",
                 ("allowance", "Nov 2nd, 2026 9:00 AM")),
                ("usage limit for a model", "You\u2019ve hit your usage limit for gpt-6.1-sol. Switch to another model now,",
                 ("allowance", None)),
                ("quota", "Quota exceeded. Check your plan and billing details.", ("allowance", None)),
                ("workspace credits", "Your workspace is out of credits. Add credits to continue.", ("allowance", None)),
                ("spend cap", "You hit your spend cap set in your workspace. Increase your spend cap to continue.",
                 ("allowance", None))):
            got = review_codex.unavailable(msg)
            check(f"Codex 0.162.1's message is read: {label}", got is not None and (got.kind, got.reset) == want,
                  got and (got.kind, got.reset))
        for label, msg in (("a stream failure", "stream disconnected before completion: error sending request"),
                           ("the same words with a plain apostrophe", "You've hit your usage limit."),
                           ("a disk", "no space left: the volume is at capacity"), ("nothing", "")):
            check(f"not read as unavailable: {label}", review_codex.unavailable(msg) is None)

        print("an unavailable model leaves one marked statement per head, for the arm (the owner's policy: Codex never blocks)")

        def seed_reviews(*reviews: dict) -> None:
            """By default the PR author's account, which is what every session posts as; a case that wants another
            names a "user"."""
            with open(os.path.join(state, "reviews.json"), "w") as f:
                json.dump([{"user": {"login": "fleet-account"}, "author_association": "OWNER", **r} for r in reviews], f)

        stranger = {"user": {"login": "stranger"}, "author_association": "NONE"}

        def touch(n: str) -> None:
            open(os.path.join(state, n), "w").close()

        def statement() -> tuple[dict | None, str]:
            body = payload_body()
            return parsed(body), body

        set_pr(); mode("allowance")
        rc, out, err, sleeps = inproc("7", req)
        m, body = statement()
        check("over the allowance: exit 3 as before, exactly one statement and no review", rc == 3 and unavailables() == 1
              and posts() == 0, (rc, post_lines(), err))
        check("…a COMMENT review pinned to the head, to the PR's reviews endpoint", post_lines() == ["POST repos/fixture-org/fixture/pulls/7/reviews unavailable"]
              and json.load(open(os.path.join(state, "payload.json"))).get("event") == "COMMENT"
              and json.load(open(os.path.join(state, "payload.json"))).get("commit_id") == head, post_lines())
        check("…its first line parses back: engine, the full head, the reason",
              m is not None and (m["engine"], m["head"], m["reason"]) == ("codex", head, "allowance"), body)
        check("…the time is UTC ISO", m is not None and time.strptime(m["at"], "%Y-%m-%dT%H:%M:%SZ"), body)
        human = body.split("\n")[1] if body.count("\n") >= 1 else ""
        check("…one human line: the short sha, the allowance and its reset time, the policy",
              human == f"Codex could not review `{head[:12]}`: over the ChatGPT allowance (Oct 14th, 2026 3:12 PM); "
              "the claude review alone arms, per the owner's policy.", human)
        check("…it is not the review marker, so it is never taken for coverage",
              not body.startswith(REVIEW_MARKER) and REVIEW_MARKER not in body, body)
        mode("allowance")
        rc, out, err, sleeps = inproc("7", req)
        check("a second run on the same head posts none (the one stands)", rc == 3 and unavailables() == 1, post_lines())
        set_pr(); mode("allowance-notime")
        rc, out, err, sleeps = inproc("7", req)
        m, body = statement()
        check("an allowance message without a time says there is none and invents none",
              unavailables() == 1 and "the backend gave no reset time" in body and "2026" not in body.split("\n")[1], body)
        set_pr(); mode("capacity")
        rc, out, err, sleeps = inproc("7", req)
        m, body = statement()
        check("at capacity after the retries: exit 3, one statement, reason capacity",
              rc == 3 and unavailables() == 1 and m is not None and m["reason"] == "capacity"
              and "stayed at capacity after 4 run(s)" in body, (rc, post_lines(), body))
        mode("capacity")
        inproc("7", req)
        check("…and again on the same head: none", unavailables() == 1, post_lines())
        set_pr(); mode("allowance")
        seed_reviews({"commit_id": "d" * 40, "body": review_codex.format_marker("d" * 40, "allowance", "2026-10-13T10:00:00Z") + "\nx\n"})
        inproc("7", req)
        check("a statement for another head does not suppress this head's", unavailables() == 1, post_lines())
        for label, seed, expect in (
                ("a Codex review of the head stands", {"commit_id": head, "body": REVIEW_MARKER + "\n<!-- model: codex -->\nbody"}, 0),
                ("the positive control: a claude review of the head stands", {"commit_id": head, "body": REVIEW_MARKER + "\nbody"}, 1),
                ("a statement whose marker names another head, on a review of this one",
                 {"commit_id": head, "body": review_codex.format_marker("d" * 40, "allowance", "2026-10-13T10:00:00Z") + "\nx\n"}, 1),
                ("the author's statement for this head stands",
                 {"commit_id": head, "body": review_codex.format_marker(head, "allowance", "2026-10-13T10:00:00Z") + "\nx\n"}, 0),
                ("a stranger's statement for this head (it does not count for the arm, so it must not stop ours)",
                 {**stranger, "commit_id": head, "body": review_codex.format_marker(head, "allowance", "2026-10-13T10:00:00Z") + "\nx\n"}, 1),
                ("a stranger's copy of a Codex review of this head",
                 {**stranger, "commit_id": head, "body": REVIEW_MARKER + "\n<!-- model: codex -->\nbody"}, 1),
                ("a Codex review of another head stands", {"commit_id": "d" * 40, "body": REVIEW_MARKER + "\n<!-- model: codex -->\nbody"}, 1),
                ("a body that only quotes the codex model line, below the header", {"commit_id": head, "body": REVIEW_MARKER + "\nx\ny\n<!-- model: codex -->"}, 1)):
            set_pr(); mode("allowance"); seed_reviews(seed)
            rc, out, err, sleeps = inproc("7", req)
            check(f"{label}: {'none posted' if not expect else 'the statement is posted'}", rc == 3 and unavailables() == expect,
                  post_lines())
        for m_, why in (("turnfailed", "an ordinary failed turn"), ("capacity-lookalike", "'at capacity' in another sentence"),
                        ("capacity-item", "the capacity text in an error item of a turn that went on"),
                        ("exit1", "a non-zero exit"), ("sleep", "a time budget spent")):
            set_pr(); mode(m_)
            rc, out, err, sleeps = inproc("7", req, *(["--timeout", "0.05"] if m_ == "sleep" else []))
            check(f"{why}: a failed review, exit 1, no statement (a crash says nothing of availability)",
                  rc == 1 and not post_lines(), (rc, post_lines(), err))
        set_pr(); mode("allowance")
        rc, out, err, sleeps = inproc("7", req, "--no-post")
        m = parsed(out)
        check("--no-post: exit 3, the statement printed on stdout, nothing read from or posted to the PR",
              rc == 3 and m is not None and m["head"] == head and not post_lines()
              and not os.path.exists(os.path.join(state, "reads")), (rc, out, post_lines()))
        set_pr(); mode("allowance"); touch("read-fails")
        rc, out, err, sleeps = inproc("7", req)
        check("the PR cannot be read: exit 3 still, nothing posted (unknown stays unknown), a warning says so",
              rc == 3 and not post_lines() and "could not post or check the unavailable statement" in err and "502" in err, (rc, err))
        set_pr(); mode("allowance"); touch("post-fails")
        rc, out, err, sleeps = inproc("7", req)
        check("the post is rejected: exit 3 still, a warning, no claim of success",
              rc == 3 and "could not post or check the unavailable statement" in err, (rc, err))
        set_pr(); mode("allowance")
        r = run("7", req)
        check("through the installed entry point: exit 3 and one statement", r.returncode == 3 and unavailables() == 1
              and r.stdout == "", (r.returncode, r.stderr, post_lines()))

        print("the marker: formatted and parsed back, strictly")
        good_line = review_codex.format_marker(head, "capacity", "2026-10-13T19:52:10Z")
        check("the line is the spelled contract", good_line == f"<!-- agent-fabric-engine-unavailable v1 engine=codex head={head} "
              "reason=capacity at=2026-10-13T19:52:10Z -->", good_line)
        check("it parses back to its fields", parsed(good_line + "\nCodex could not review.\n")
              == {"engine": "codex", "head": head, "reason": "capacity", "at": "2026-10-13T19:52:10Z"})
        # The head field alone: replacing head[:1] anywhere hit "codex" (c, d, e) when the head began with one.
        for label, text in (("a marker below the first line", "hello\n" + good_line), ("text after the marker", good_line + " x"),
                            ("a short sha", good_line.replace(head, head[:12])),
                            ("a version 2", good_line.replace(" v1 ", " v2 ")),
                            ("a non-hex head", good_line.replace(f"head={head}", f"head=g{head[1:]}")),
                            ("empty", ""), ("None", None)):
            check(f"not a marker: {label}", parsed(text) is None, text)
        for label, args in (("a short head", (head[:12], "capacity", "2026-10-13T19:52:10Z")),
                            ("a reason this engine never emits", (head, "crash", "2026-10-13T19:52:10Z"))):
            try:
                review_codex.format_marker(*args)
                refused = False
            except ValueError:
                refused = True
            check(f"the writer refuses {label}", refused, args)

        print("the time budget: Codex and what it started are ended, the scratch removed")
        set_pr(); mode("sleep")
        t0 = time.monotonic()
        r = run("7", req, "--timeout", "0.05")
        check("exit 1 within the budget", r.returncode == 1 and time.monotonic() - t0 < 30, r.stderr)
        check("the reason names the budget", "did not answer within" in r.stderr, r.stderr)
        check("nothing posted", not posted())
        check("the scratch is removed", scratch_empty(), os.listdir(scratch))
        gc = int(open(os.path.join(state, "grandchild")).read())
        time.sleep(0.2)
        check("Codex's own children are ended", not os.path.exists(f"/proc/{gc}")
              or open(f"/proc/{gc}/stat").read().split()[2] == "Z", gc)

        print("SIGTERM mid-review: the scratch is removed, nothing posted")
        set_pr(); mode("sleep")
        p = subprocess.Popen([REVIEW, "--engine", "codex", "7", req], env=env0, cwd=repo,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(200):
            if os.path.exists(os.path.join(state, "grandchild")):
                break
            time.sleep(0.05)
        p.send_signal(signal.SIGTERM)
        _, err = p.communicate(timeout=30)
        check("exit 143", p.returncode == 143, (p.returncode, err))
        check("the scratch is removed", scratch_empty(), os.listdir(scratch))
        check("nothing posted", not posted())
        gc = int(open(os.path.join(state, "grandchild")).read())
        time.sleep(0.2)
        check("Codex's own children are ended", not os.path.exists(f"/proc/{gc}")
              or open(f"/proc/{gc}/stat").read().split()[2] == "Z", gc)

        # A signal after the post's child started cannot claim "nothing posted" (review of #220, F4): main() itself,
        # with review() standing in for a run that was signalled once posting began.
        print("a signal while posting the unavailable statement: it may have been posted; while reading: nothing was")

        def signalled_in_gh(on_post: bool):
            real = review_codex.gh.api

            def fake(path, **kw):
                if on_post == (kw.get("method") == "POST"):
                    raise review_codex._Signalled(15)
                return real(path, **kw)
            return fake
        real_api = review_codex.gh.api
        try:
            for on_post, want, refuse in ((True, "may have been posted", "nothing posted"), (False, "nothing posted", "may have")):
                set_pr(); mode("allowance")
                review_codex.gh.api = signalled_in_gh(on_post)
                review_codex._posting = False        # a process starts with it off; in-process runs keep what the last left
                rc, out, err, sleeps = inproc("7", req)
                check(f"a signal in the {'POST' if on_post else 'read'}: exit 143, the words follow",
                      rc == 143 and want in err and refuse not in err, (rc, err))
        finally:
            review_codex.gh.api = real_api

        print("a signal while posting: it says the review may have been posted")

        def signalled_after(posting):
            def fake(*a, **k):
                review_codex._posting = posting
                raise review_codex._Signalled(15)
            return fake
        saved_review, saved_posting = review_codex.review, review_codex._posting
        old_handlers = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}
        try:
            for posting, want, refuse in ((True, "may have been posted", "nothing posted"), (False, "nothing posted", "may have")):
                review_codex.review = signalled_after(posting)
                buf = io.StringIO()
                with contextlib.redirect_stderr(buf):
                    rc = review_codex.main(["codex", "7", req])
                check(f"posting={posting}: exit 143 and the words follow the flag",
                      rc == 143 and want in buf.getvalue() and refuse not in buf.getvalue(), (rc, buf.getvalue()))
        finally:
            review_codex.review, review_codex._posting = saved_review, saved_posting
            for s_, h in old_handlers.items():
                signal.signal(s_, h)

        print("the model and its level from routing: the openai column's code-review")
        no_model = {k: v for k, v in env0.items() if k != "AGENT_FABRIC_CODEX_MODEL"}
        set_pr(); mode("empty")
        r = run("7", req, "--no-post", env=no_model)
        rec = record() if codex_ran() else {"argv": []}
        check("no --model and no AGENT_FABRIC_CODEX_MODEL: routing's model runs (gpt-6.1-sol, the owner, 2026-10-12)",
              r.returncode == 0 and rec["argv"][rec["argv"].index("--model") + 1] == "gpt-6.1-sol", r.stderr)
        check("…and the review's first line names it", "`gpt-6.1-sol`" in shown(r.stdout).split("\n")[0], r.stdout[:300])
        check("the environment's gateway still gets no level unless one is asked for (review of #224, F2)",
              not any(a.startswith("model_reasoning_effort") for a in rec["argv"]) and "-c" not in rec["argv"]
              and "**effort:** Codex's default" in shown(r.stdout).split("\n")[0], rec["argv"])
        set_pr(); mode("empty")
        r = run("7", req, "--no-post", "--effort", "medium", env=no_model)
        check("--effort still names the level beside a routed model",
              'model_reasoning_effort="medium"' in record()["argv"], r.stderr)
        for label, layer, why in (
                ("a local layer naming a model routing does not take on openai",
                 {"providers": {"openai": {"capabilities": {"code-review": "claude-opus-5-5"}}}}, "not an OpenAI model id"),
                ("a local layer giving openai a class it does not serve",
                 {"providers": {"openai": {"capabilities": {"code-low": "gpt-6.1-sol"}}}}, "not served on openai"),
                ("a routed model outside the review grade",
                 {"providers": {"openai": {"capabilities": {"code-review": "gpt-unadmitted"}}}}, "review-grade.json")):
            with open(local_layer, "w") as f:
                json.dump(layer, f)
            set_pr(); mode("ok")
            r = run("7", req, env=no_model)
            check(f"{label}: refused, naming why", r.returncode == 1 and "refused" in r.stderr
                  and "routing answer" in r.stderr and why in r.stderr, r.stderr)
            check(f"{label}: codex never ran, nothing posted", not codex_ran() and not posted())
            set_pr(); mode("empty")
            r = run("7", req, "--no-post")
            check(f"{label}: an explicit model does not read routing on the environment's gateway",
                  r.returncode == 0 and "`gpt-test`" in shown(r.stdout).split("\n")[0], r.stderr)
        with open(local_layer, "w") as f:
            json.dump({"providers": {"openai": {"capabilities": {"code-review": "gpt-6.1-sol"}}}}, f)
        set_pr(); mode("empty")
        r = run("7", req, "--no-post", env=no_model)
        check("an admitted model in the local layer is what runs", r.returncode == 0
              and "`gpt-6.1-sol`" in shown(r.stdout).split("\n")[0], r.stderr)
        os.remove(local_layer)

        print("the ledger: one row v1 per review that started Codex, on every way out (review economics P1)")
        ledger_file = os.path.join(fabric_state, "agents", pwd.getpwuid(os.geteuid()).pw_name, "ledger.jsonl")
        usage_json = os.path.join(state, "usage.json")

        def ledger_rows() -> list[dict]:
            try:
                with open(ledger_file) as f:
                    return [json.loads(ln) for ln in f.read().splitlines()]
            except OSError:
                return []

        def fresh_ledger() -> None:
            for f in (ledger_file, usage_json):
                if os.path.exists(f):
                    os.unlink(f)

        V1 = {"schema_version", "engine", "attribution", "purpose", "description", "dispatch_id", "parent_session_id",
              "job_id", "project", "repository", "pr", "review_id", "review_round", "evidence", "base_sha", "head_sha",
              "started_at", "session_id", "agent_id", "agent_type", "tool_use_id", "status", "status_source",
              "completed_at", "wall_time", "turns", "input", "cache_write", "cache_read", "output", "reasoning",
              "first_turn_context", "model", "provider", "effort"}
        fresh_ledger(); set_pr(); mode("ok")
        with open(usage_json, "w") as f:
            json.dump({"input_tokens": 1000, "cached_input_tokens": 600, "cache_write_input_tokens": 100,
                       "output_tokens": 50, "reasoning_output_tokens": 30}, f)
        r = run("7", req)
        rows = ledger_rows()
        row = rows[0] if len(rows) == 1 else {}
        check("a review: exit 0 and exactly one row", r.returncode == 0 and len(rows) == 1, (r.stderr, rows))
        check("…holding every v1 key and no other", set(row) == V1, sorted(set(row) ^ V1))
        check("…engine codex, completed, the model and provider that ran",
              (row.get("schema_version"), row.get("engine"), row.get("status"), row.get("status_source"), row.get("model"),
               row.get("provider")) == (1, "codex", "completed", "codex:answer:usage-unverified", "gpt-test", "openai"),
              row)
        check("…a row carrying a usage figure says in its status_source that the figure's semantics are unverified; one without does not "
              "(the allowance case below)", row.get("status_source", "").endswith(review_codex.USAGE_UNVERIFIED))
        check("…the tokens: input is what is left after the cached and the cache-write tokens; reasoning inside output",
              (row.get("input"), row.get("cache_read"), row.get("cache_write"), row.get("output"), row.get("reasoning"))
              == (300, 600, 100, 50, 30), row)
        check("…what the events do not give is unknown, not 0 or a guess: turns, first_turn_context, agent ids",
              all(row.get(k) is None for k in ("turns", "first_turn_context", "agent_id", "agent_type", "tool_use_id",
                                               "repository", "description")), row)
        check("…the brief carries the dispatch header: attribution dispatch, its purpose, evidence and shas copied, and the PR "
              "this review was told (the request named none), so the cost reaches that PR",
              (row.get("attribution"), row.get("purpose"), row.get("evidence"), row.get("pr"), row.get("review_id"),
               row.get("dispatch_id") is not None, row.get("base_sha") is not None, len(str(row.get("head_sha"))))
              == ("dispatch", "second-engine-review", "pinned", 7, "fixture#7", True, True, 40), row)
        check("…the thread id is the session, the times are UTC and the wall time a number",
              row.get("session_id") == "01a13195-6c03-7e02-94f7-7a304e1e64d6"
              and str(row.get("started_at", "")).endswith("Z") and str(row.get("completed_at", "")).endswith("Z")
              and isinstance(row.get("wall_time"), float) and row["wall_time"] >= 0, row)
        check("…no brief or answer text in it", "app.py" not in json.dumps(row) and "scenario" not in json.dumps(row), row)
        check("…the ledger file is private", os.stat(ledger_file).st_mode & 0o777 == 0o600, oct(os.stat(ledger_file).st_mode))

        # The row builder on its own: two runs (a capacity retry) sum; a brief with the dispatch header gives the header's.
        streams: list[str] = []

        def stream(*turns: dict) -> str:
            with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, dir=scratch) as fh:
                streams.append(fh.name)
                fh.write('{"type":"thread.started","thread_id":"th-1"}\n'
                         + "".join(json.dumps({"type": "turn.completed", "usage": u}) + "\n" for u in turns))
            return fh.name
        r1 = review_codex.read_events(stream({"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 5},
                                             {"input_tokens": 10, "output_tokens": "x", "bogus": 1}))
        check("read_events: usage summed over the turns, a field no turn reported stays unknown, a non-count is left out",
              r1.usage == {"input_tokens": 110, "cached_input_tokens": 40, "cache_write_input_tokens": None,
                           "output_tokens": 5, "reasoning_output_tokens": None} and r1.thread_id == "th-1", r1.usage)
        obs = review_codex.Observed()
        obs.add(r1, "2026-10-14T10:00:00Z", 1.5)
        obs.add(review_codex.read_events(stream({"input_tokens": 7, "output_tokens": 3})), "2026-10-14T10:01:00Z", 2.0)
        obs.status = ("completed", "codex:answer")
        hdr = ('```agent-fabric-dispatch v1\n{"dispatch_id": "d-9", "purpose": "re-review", "repository": "o/r", "pr": 7, '
               '"review_round": 2, "head_sha": "' + "a" * 40 + '", "engine": "claude", "job_id": "j9"}\n```\n# brief\n')
        two = review_codex.ledger_row(obs, brief=hdr, pr="7", head="b" * 40, model="m", level="high", now="2026-10-14T10:02:00Z")
        check("two runs: tokens summed (input 117 less 40 cached = 77), wall time summed, started_at the first run's",
              (two["input"], two["cache_read"], two["output"], two["wall_time"], two["started_at"])
              == (77, 40, 8, 3.5, "2026-10-14T10:00:00Z"), two)
        check("a brief with the header: attribution dispatch, the header's purpose and fields (not this review's head), engine codex",
              (two["attribution"], two["purpose"], two["dispatch_id"], two["repository"], two["review_round"], two["job_id"],
               two["head_sha"], two["engine"], two["effort"]) == ("dispatch", "re-review", "d-9", "o/r", 2, "j9", "a" * 40, "codex", "high"), two)
        named = os.path.join(tmp, "req", "NAMED.yaml")
        with open(named, "w") as f:
            f.write(open(req).read() + "pr: 9\n")
        def header_pr(brief: str) -> object:
            return json.loads(brief.split("\n", 1)[1].split("\n```\n", 1)[0])["pr"]
        told, mine = review_codex.load_request(req, False, "7"), review_codex.load_request(named, False, "7")
        check("load_request: a request that names no PR is told this review's; one that names its own keeps it",
              (told[0]["pr"], header_pr(told[1]), mine[0]["pr"], header_pr(mine[1]), header_pr(review_codex.load_request(req, False)[1]))
              == ("7", 7, "9", 9, None), (told[0]["pr"], header_pr(told[1]), mine[0]["pr"], header_pr(mine[1])))
        bare = review_codex.ledger_row(obs, brief="# brief\n", pr="7", head="b" * 40, model="m", level=None, now="n")
        check("a brief without the header: attribution inferred, the PR and head this review holds, the repository unknown",
              (bare["attribution"], bare["pr"], bare["head_sha"], bare["repository"], bare["evidence"])
              == ("inferred", 7, "b" * 40, None, None), bare)
        sparse = review_codex.ledger_row(obs, brief=hdr.replace("a" * 40, "zz"), pr="7", head="b" * 40, model="m", level=None, now="n")
        check("…a header field in the wrong shape is unknown, never filled from the review's own head (a row's head_sha is "
              "what a reproduction is checked against)", sparse["head_sha"] is None and sparse["effort"] is None, sparse)
        for name in streams:
            os.unlink(name)
        fresh_ledger(); set_pr(); mode("capacity ok")
        inproc("7", req)
        rows = ledger_rows()
        check("capacity once, then success: one row for the review, completed",
              len(rows) == 1 and rows[0]["status"] == "completed", rows)
        fresh_ledger(); set_pr(); mode("capacity")
        rc, out, err, sleeps = inproc("7", req)
        rows = ledger_rows()
        check("at capacity on every run: one row, failed, source codex:capacity — not the allowance's status",
              rc == 3 and len(rows) == 1 and (rows[0]["status"], rows[0]["status_source"]) == ("failed", "codex:capacity"), (rc, rows))
        fresh_ledger(); set_pr(); mode("allowance")
        rc, out, err, sleeps = inproc("7", req)
        rows = ledger_rows()
        check("over the allowance: one row, allowance-exhausted, apart from every other failure",
              rc == 3 and len(rows) == 1 and (rows[0]["status"], rows[0]["status_source"]) == ("allowance-exhausted", "codex:usage-limit")
              and rows[0]["output"] is None, (rc, rows))
        for m, why, source in (("turnfailed", "an ordinary failed turn", "codex:failed-review"),
                               ("nohost", "a run that read nothing", "codex:failed-review:usage-unverified")):
            fresh_ledger(); set_pr(); mode(m)
            r = run("7", req)
            rows = ledger_rows()
            check(f"{why}: exit 1, one row, failed", r.returncode == 1 and len(rows) == 1
                  and (rows[0]["status"], rows[0]["status_source"]) == ("failed", source), (r.returncode, rows))
        fresh_ledger(); set_pr(); mode("sleep")
        r = run("7", req, "--timeout", "0.05")
        rows = ledger_rows()
        check("the time budget: one row, timeout, a wall time near the budget not the sleep",
              r.returncode == 1 and len(rows) == 1 and rows[0]["status"] == "timeout" and rows[0]["status_source"] == "codex:timeout"
              and 0 < rows[0]["wall_time"] < 30, (r.returncode, rows))
        fresh_ledger(); set_pr(); mode("sleep")
        p = subprocess.Popen([REVIEW, "--engine", "codex", "7", req], env=env0, cwd=repo,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(200):
            if os.path.exists(os.path.join(state, "grandchild")):
                break
            time.sleep(0.05)
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=30)
        rows = ledger_rows()
        check("SIGTERM mid-run: one row, cancelled", p.returncode == 143 and len(rows) == 1
              and (rows[0]["status"], rows[0]["status_source"]) == ("cancelled", "codex:signal"), (p.returncode, rows))
        fresh_ledger(); set_pr(); mode("ok")
        r = run("7", req, env={**env0, "AGENT_FABRIC_CODEX_KEY": ""})
        check("a refusal before Codex started writes no row (positive control above: the same file takes rows)",
              r.returncode == 1 and not codex_ran() and ledger_rows() == [], (r.stderr, ledger_rows()))
        fresh_ledger(); set_pr(); mode("ok")
        with open(os.path.join(state, "sandbox-mode"), "w") as f:
            f.write("fail")
        r = run("7", req)
        check("a sandbox that cannot start (the facts known, Codex never run): no row either",
              r.returncode == 1 and not codex_ran() and ledger_rows() == [], (r.stderr, ledger_rows()))
        fresh_ledger(); set_pr(); mode("ok")
        os.makedirs(ledger_file)   # a ledger that cannot be written: the path is a directory
        r = run("7", req)
        check("a ledger that cannot be written warns and changes neither the review nor its exit",
              r.returncode == 0 and posted() and "ledger row could not be written" in r.stderr, (r.returncode, r.stderr))
        os.rmdir(ledger_file)
        fresh_ledger()

        print("the reviewer reads only an allowlisted tree (audit F01): the profile, the canary probe, the refusals")
        set_pr(); mode("ok")
        with open(os.path.join(state, "sandbox-mode"), "w") as f:
            f.write("ok")
        r = run("7", req)
        check("a review runs", r.returncode == 0, r.stderr + r.stdout)
        cfg = record()["config"] or ""
        cwd = record()["cwd"]
        check("config.toml sets the reviewer profile as default and no sandbox_mode (the two cannot be set together)",
              'default_permissions = "reviewer"\n' in cfg and "sandbox_mode" not in cfg and "[permissions.reviewer.filesystem]\n" in cfg, cfg)
        granted = re.findall(r'^"([^"]+)" = "read"$', cfg.split("[permissions.reviewer.filesystem]\n", 1)[1].split("\n\n", 1)[0], re.M)
        common = os.path.join(os.path.realpath(repo), ".git")
        check("the profile reads the extract, the repository's history and nothing else of the repository or the account",
              os.path.realpath(cwd) in granted and os.path.join(common, "objects") in granted and os.path.join(common, "refs") in granted
              and not any(g == os.path.realpath(repo) or g.startswith(os.path.join(os.path.realpath(repo), "app.py"))
                          or g in (os.path.join(common, "config"), os.path.join(common, "hooks"), os.path.realpath(home), os.path.realpath(tmp))
                          for g in granted), granted)
        check("…and the platform defaults", '":minimal" = "read"\n' in cfg, cfg)
        with open(os.path.join(state, "sandbox-calls")) as f:
            probes = [json.loads(line) for line in f]
        read_probe = probes[2]
        canary_path, control_path = read_probe[-2], read_probe[-1]
        check("the read probe's canary lies beside the extract, outside every granted path, under a fresh random name",
              os.path.dirname(canary_path) == os.path.dirname(cwd) and os.path.basename(canary_path).startswith(".fabric-read-canary-")
              and not any(canary_path == g or canary_path.startswith(g.rstrip("/") + "/") for g in granted), (canary_path, granted))
        check("…and its control is a file of the extract, which the same command must read",
              os.path.dirname(control_path) == cwd and os.path.basename(control_path).startswith(".fabric-read-control-"), control_path)
        check("the review's scratch is gone, canary included", scratch_empty(), os.listdir(scratch))
        for label, smode, text in (("a sandbox that lets the canary be read", "readable", "lets a file outside its allowlist be read"),
                                   ("a sandbox that cannot read the extract either", "blind", "its refusal of a read proves nothing")):
            set_pr(); mode("ok")
            with open(os.path.join(state, "sandbox-mode"), "w") as f:
                f.write(smode)
            r = run("7", req)
            check(f"{label}: exit 1, said in one line, codex exec never started, nothing posted, the scratch removed",
                  r.returncode == 1 and text in r.stderr and not codex_ran() and not posted() and scratch_empty(),
                  (r.returncode, r.stderr[-400:], codex_ran(), posted(), os.listdir(scratch)))
        work = tempfile.mkdtemp(prefix="extract.", dir=tmp)
        verdict = prove("readable", work)
        check("prove_sandbox called directly refuses a readable canary and leaves neither probe file behind",
              "lets a file outside its allowlist be read" in verdict and not [n for n in os.listdir(work) if n.startswith(".fabric-read")]
              and not [n for n in os.listdir(os.path.dirname(work)) if n.startswith(".fabric-read")], (verdict, os.listdir(work)))
        check("positive control: the same proof passes where the canary is refused", prove("ok") == "ok")

        print("the real Codex sandbox refuses a read outside the allowlist (skipped where no codex runs a sandbox here)")
        real_codex = shutil.which("codex", path=os.environ.get("PATH", ""))
        real_ok = False
        if real_codex:
            real_scratch = tempfile.mkdtemp(prefix="real.", dir=tmp)
            real_work = os.path.join(real_scratch, "head")
            review_codex.extract(repo, head, real_work)
            real_home = review_codex.codex_home(real_scratch, "http://127.0.0.1:1", None,
                                                review_codex.readable_paths(real_codex, real_work, repo))
            real_env = review_codex.child_env({"PATH": os.environ.get("PATH", "")}, real_scratch, real_home, "k")
            try:
                review_codex.prove_sandbox(real_codex, real_work, real_env)
                real_ok = True
            except review_codex.FailedReview as e:
                if "cannot start" not in str(e) and "did not start" not in str(e):
                    check("the real sandbox passes the proof", False, str(e))   # only a sandbox that will not start is a reason to skip
                else:
                    print(f"  skip the real sandbox does not start here: {e}")
        else:
            print("  skip no codex on PATH")
        if real_ok:
            check("the real sandbox passes the proof, canary probe included", True)
            saved_profile = review_codex.PROFILE
            review_codex.PROFILE = ":read-only"   # the profile main shipped: read access to the whole filesystem
            try:
                try:
                    review_codex.prove_sandbox(real_codex, real_work, real_env)
                    old = "proved"
                except review_codex.FailedReview as e:
                    old = str(e)
            finally:
                review_codex.PROFILE = saved_profile
            check("negative control: under the old `:read-only` profile the same proof refuses the review, the canary being readable",
                  "lets a file outside its allowlist be read" in old, old)

            # A command the reviewer's model asks Codex to run, through the real `codex exec` and a stand-in Responses endpoint.
            secret_dir = tempfile.mkdtemp(prefix="secrets.", dir=tmp)
            secret = os.path.join(secret_dir, "id_ed25519")
            with open(secret, "w") as f:
                f.write("PRIVATE-KEY-MATERIAL\n")
            wip = os.path.join(repo, "wip.txt")
            command = (f"cat {secret}; echo ==; cat {wip}; echo ==; ls {os.path.realpath(home)}; echo ==; cat app.py; echo ==; "
                       f"git -C {repo} log --oneline -1 | wc -l; echo ==; cat {repo}/.git/config; true")
            asked: list[int] = []

            class Responses(http.server.BaseHTTPRequestHandler):
                def log_message(self, *a):
                    pass

                def do_POST(self):
                    self.rfile.read(int(self.headers.get("content-length", 0)))
                    asked.append(1)
                    sse = lambda ev, d: f"event: {ev}\ndata: {json.dumps(d)}\n\n".encode()  # noqa: E731
                    self.send_response(200)
                    self.send_header("content-type", "text/event-stream")
                    self.end_headers()
                    self.wfile.write(sse("response.created", {"type": "response.created", "response": {"id": f"r{len(asked)}"}}))
                    item = ({"type": "function_call", "call_id": "c1", "id": "fc1", "name": "exec_command",
                             "arguments": json.dumps({"cmd": command})} if len(asked) == 1 else
                            {"type": "message", "role": "assistant", "id": "m1",
                             "content": [{"type": "output_text", "text": '{"findings": []}'}]})
                    self.wfile.write(sse("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}))
                    self.wfile.write(sse("response.completed", {"type": "response.completed", "response": {"id": f"r{len(asked)}", "usage": {
                        "input_tokens": 1, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 1,
                        "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 2}}}))

            server = http.server.HTTPServer(("127.0.0.1", 0), Responses)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                exec_scratch = tempfile.mkdtemp(prefix="exec.", dir=tmp)
                exec_work = os.path.join(exec_scratch, "head")
                review_codex.extract(repo, head, exec_work)
                exec_home = review_codex.codex_home(exec_scratch, f"http://127.0.0.1:{server.server_port}", None,
                                                    review_codex.readable_paths(real_codex, exec_work, repo))
                exec_env = review_codex.child_env({"PATH": os.environ.get("PATH", "")}, exec_scratch, exec_home, "k")
                try:
                    review_codex.run_codex(real_codex, "gpt-test", exec_work, exec_scratch, exec_env, "review\n", 120)
                except review_codex.FailedReview as e:   # Codex's complaint that a stand-in's model has no metadata; the run is what is read
                    check("…the only thing Codex complained of is the stand-in's model name", "Model metadata for `gpt-test` not found" in str(e), str(e))
                events = review_codex.read_events(os.path.join(exec_scratch, "codex-events.jsonl"))
                with open(os.path.join(exec_scratch, "codex-events.jsonl"), encoding="utf-8") as f:
                    outputs = [e["item"].get("aggregated_output", "") for e in map(json.loads, f.read().splitlines())
                               if e.get("item", {}).get("type") == "command_execution" and e.get("type") == "item.completed"]
            finally:
                server.shutdown()
            out = "".join(outputs)
            check("the model's command ran in the real sandbox and finished", events.commands == 1 and out.count("==") == 5, (events.commands, out))
            check("the account's key file, by absolute path, is not there for it to read",
                  "PRIVATE-KEY-MATERIAL" not in out and "id_ed25519: No such file" in out, out)
            refused = [ln for ln in out.splitlines() if "No such file" in ln]
            check("neither are the repository's uncommitted files, its config, nor the home: each is as if absent",
                  "not committed" not in out and "[core]" not in out
                  and all(any(path in ln for ln in refused) for path in (wip, f"{repo}/.git/config", os.path.realpath(home))), out)
            check("positive control: the extract's own file reads, and the repository's history is there to be read",
                  "print(1)\nprint(2)\n==\n1\n==" in out, out)

        print("the extract is the committed tree, byte for byte, verified against ls-tree (audit F13)")
        fx = os.path.join(tmp, "work", "attrs")
        os.makedirs(fx)

        def fxgit(*a: str, data: bytes | None = None) -> str:
            return subprocess.run(["git", "-C", fx, *a], env=git_env(), check=True, capture_output=True, input=data,
                                  timeout=30).stdout.decode("utf-8", "surrogateescape").strip()

        fxgit("init", "-q", "-b", "main")
        files = {".gitattributes": b"skip.txt export-ignore\nstamp.txt export-subst\nvendored export-ignore\n",
                 "skip.txt": b"tracked, and export-ignore'd\n", "stamp.txt": b"commit $Format:%H$ and $Format:%s$\n",
                 "vendored/inner.txt": b"inside an export-ignore'd directory\n", "src/run.sh": b"#!/bin/sh\necho hi\n",
                 "src/empty": b"", "caf\xc3\xa9 \xe2\x9c\x93.txt": b"non-ASCII name\n", "two\nlines.txt": b"a newline in the name\n",
                 "bin.dat": bytes(range(256)) + b"\r\n\0\n"}
        for name, data in files.items():
            path = os.path.join(os.fsencode(fx), name.encode() if isinstance(name, str) else name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        os.chmod(os.path.join(fx, "src/run.sh"), 0o755)
        os.symlink("run.sh", os.path.join(fx, "src/link"))
        fxgit("add", "-A")
        fxgit("update-index", "--add", "--cacheinfo", f"160000,{head},sub")   # a submodule: a commit id with no checkout
        fxgit("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--no-gpg-sign", "-m", "attrs fixture")
        fxhead = fxgit("rev-parse", "HEAD")
        listing = fxgit("ls-tree", "-r", "-z", "--full-tree", fxhead).split("\0")
        archived = tarfile.open(fileobj=io.BytesIO(subprocess.run(["git", "-C", fx, "archive", fxhead], env=git_env(), capture_output=True,
                                                                 check=True, timeout=30).stdout)).getnames()
        check("positive control: `git archive` of this commit really drops the export-ignore'd files",
              "skip.txt" not in archived and "vendored/inner.txt" not in archived and "stamp.txt" in archived, archived)
        dest = os.path.join(tmp, "fx-extract")
        review_codex.extract(fx, fxhead, dest)
        got = {}
        for top, dirs, names in os.walk(dest):
            for n in names + [d for d in dirs if os.path.islink(os.path.join(top, d))]:
                got[os.path.relpath(os.path.join(top, n), dest)] = None
        want_paths = [rec.split("\t", 1)[1] for rec in listing if rec and not rec.startswith("160000")]
        check("every tracked file is in the extract, the export-ignore'd ones too (nothing vanishes)",
              sorted(got) == sorted(want_paths) and "skip.txt" in got and "vendored/inner.txt" in got, (sorted(got), want_paths))
        mismatches = []
        for rec in listing:
            if not rec or rec.startswith("160000"):
                continue
            meta, name = rec.split("\t", 1)
            fmode, _kind, oid = meta.split(" ")
            blob = subprocess.run(["git", "-C", fx, "cat-file", "blob", oid], env=git_env(), capture_output=True, check=True, timeout=30).stdout
            target = os.path.join(dest, name)
            if fmode == "120000":
                same = os.path.islink(target) and os.fsencode(os.readlink(target)) == blob
            else:
                with open(target, "rb") as f:
                    same = f.read() == blob and bool(os.stat(target).st_mode & 0o111) == (fmode == "100755")
            if not same:
                mismatches.append(name)
        check("every file is the committed blob byte for byte, with the committed mode (export-subst expands nothing)", not mismatches, mismatches)
        with open(os.path.join(dest, "stamp.txt"), "rb") as f:
            check("the export-subst placeholder is left as committed", f.read() == files["stamp.txt"])
        check("a submodule is an empty directory", os.path.isdir(os.path.join(dest, "sub")) and os.listdir(os.path.join(dest, "sub")) == [])
        entries = review_codex._tree(fx, fxhead)

        def tampered(change) -> str:
            copy = os.path.join(tmp, "fx-tamper")
            shutil.rmtree(copy, ignore_errors=True)
            shutil.copytree(dest, copy, symlinks=True)
            change(copy)
            try:
                review_codex.verify_extract(copy, entries)
                return "verified"
            except review_codex.Refused as e:
                return str(e)

        def rewrite(path):
            def change(root):
                with open(os.path.join(root, path), "r+b") as f:
                    data = f.read()
                    f.seek(0)
                    f.write(data[:-1] + bytes([data[-1] ^ 1]))
            return change
        check("positive control: the untouched extract verifies", tampered(lambda root: None) == "verified")
        check("a byte changed in a file is caught", "differs from the head's" in tampered(rewrite("src/run.sh")))
        check("a file removed is caught", "missing" in tampered(lambda root: os.unlink(os.path.join(root, "skip.txt"))))
        check("a file added is caught", "extra" in tampered(lambda root: open(os.path.join(root, "new.txt"), "w").close()))
        check("a directory added is caught", "extra" in tampered(lambda root: os.mkdir(os.path.join(root, "src", "stray"))))
        check("an executable bit flipped is caught", "differs from the head's" in tampered(lambda root: os.chmod(os.path.join(root, "src/run.sh"), 0o644)))
        check("a link retargeted is caught", "differs from the head's" in tampered(
            lambda root: (os.unlink(os.path.join(root, "src/link")), os.symlink("empty", os.path.join(root, "src/link")))))
        check("a file turned into a link is caught", "differs from the head's" in tampered(
            lambda root: (os.unlink(os.path.join(root, "src/empty")), os.symlink("run.sh", os.path.join(root, "src/empty")))))

        def hostile(name_tree: str) -> tuple[str, str]:
            """A commit whose tree holds a path git's own tools refuse to add but a pushed tree can carry, and what extract says to it."""
            blob = fxgit("hash-object", "-w", "--stdin", data=b"payload\n")
            inner = subprocess.run(["git", "-C", fx, "mktree"], env=git_env(), input=f"100644 blob {blob}\tconfig\n".encode(), capture_output=True,
                                   check=True, timeout=30).stdout.decode().strip()
            root_tree = subprocess.run(["git", "-C", fx, "mktree"], env=git_env(), input=f"040000 tree {inner}\t{name_tree}\n".encode(),
                                       capture_output=True, check=True, timeout=30).stdout.decode().strip()
            commit = fxgit("-c", "user.name=t", "-c", "user.email=t@t", "commit-tree", root_tree, "-m", "hostile")
            out = os.path.join(tmp, "fx-hostile")
            shutil.rmtree(out, ignore_errors=True)
            try:
                review_codex.extract(fx, commit, out)
                return "extracted", out
            except review_codex.Refused as e:
                return str(e), out
        verdict, out = hostile(".git")
        check("a tree with a .git directory is refused, not written (the extract could carry a git config the reviewer's tools would read)",
              "cannot be extracted" in verdict and not os.path.exists(os.path.join(out, ".git")), verdict)
        verdict, out = hostile(".GIT")
        check("…in any case", "cannot be extracted" in verdict, verdict)
        verdict, out = hostile("sub")
        check("positive control: the same shape under an ordinary name is extracted", verdict == "extracted" and os.path.isfile(os.path.join(out, "sub", "config")), verdict)
        blob = fxgit("hash-object", "-w", "--stdin", data=b"/etc/passwd")
        tree = subprocess.run(["git", "-C", fx, "mktree"], env=git_env(), input=f"120000 blob {blob}\tpasswd\n".encode(), capture_output=True,
                              check=True, timeout=30).stdout.decode().strip()
        link_commit = fxgit("-c", "user.name=t", "-c", "user.email=t@t", "commit-tree", tree, "-m", "link out")
        try:
            review_codex.extract(fx, link_commit, os.path.join(tmp, "fx-link"))
            verdict = "extracted"
        except review_codex.Refused as e:
            verdict = str(e)
        real_blobs = review_codex._blobs
        review_codex._blobs = lambda repo_, oids: ((oid, data + b"x") for oid, data in real_blobs(repo_, oids))
        try:
            review_codex.extract(fx, fxhead, os.path.join(tmp, "fx-wrong"))
            wrong = "extracted"
        except review_codex.Refused as e:
            wrong = str(e)
        finally:
            review_codex._blobs = real_blobs
        check("extract itself verifies what it wrote: bytes that are not the blob's are refused", "differs from the head's" in wrong, wrong)
        check("a link out of the head is refused, as it was under `git archive`", "is a link out of the head" in verdict, verdict)
        def link_tree(links: dict[str, str]) -> str:
            def build(flat: dict[str, str]) -> str:
                lines, subdirs = "", {}
                for name, target in flat.items():
                    head_, _, rest = name.partition("/")
                    if rest:
                        subdirs.setdefault(head_, {})[rest] = target
                    else:
                        b = fxgit("hash-object", "-w", "--stdin", data=target.encode())
                        lines += f"120000 blob {b}\t{name}\n"
                for name, inner in subdirs.items():
                    lines += f"040000 tree {build(inner)}\t{name}\n"
                return subprocess.run(["git", "-C", fx, "mktree"], env=git_env(), input=lines.encode(), capture_output=True, check=True,
                                      timeout=30).stdout.decode().strip()
            return fxgit("-c", "user.name=t", "-c", "user.email=t@t", "commit-tree", build(links), "-m", "links")

        def extracted_links(links: dict[str, str], label: str) -> str:
            try:
                review_codex.extract(fx, link_tree(links), os.path.join(tmp, "work", f"fx-{label}", "head"))
                return "extracted"
            except review_codex.Refused as e:
                return str(e)
        # Each target is lexically inside the head; the escape is only through the chain (p/q is the head itself).
        chain_verdict = extracted_links({"p/q": "..", "AGENTS.md": "p/q/p/q/../../canary"}, "chain")
        check("a link that leaves the head only by way of another link of the tree is refused, and the refusal names that link",
              "'AGENTS.md' is a link out of the head" in chain_verdict, chain_verdict)
        old_lexical = [os.path.normpath(os.path.join(os.path.dirname(p), t)).startswith("..")
                       for p, t in (("p/q", ".."), ("AGENTS.md", "p/q/p/q/../../canary"))]
        check("positive control: a check of each target's text alone passes both of those links", old_lexical == [False, False], old_lexical)
        # d is a link to a directory outside, and d/evil a file: written through the link, it would land outside.
        target_dir = os.path.join(tmp, "work", "fx-dup-outside")
        os.makedirs(target_dir, exist_ok=True)
        dup_blob = fxgit("hash-object", "-w", "--stdin", data=b"evil\n")
        dup_link = fxgit("hash-object", "-w", "--stdin", data=target_dir.encode())
        dup_inner = subprocess.run(["git", "-C", fx, "mktree"], env=git_env(), input=f"100644 blob {dup_blob}\tevil\n".encode(),
                                   capture_output=True, check=True, timeout=30).stdout.decode().strip()
        dup_tree = subprocess.run(["git", "-C", fx, "mktree", "--missing"], env=git_env(), capture_output=True, check=True, timeout=30,
                                  input=f"120000 blob {dup_link}\td\n040000 tree {dup_inner}\td\n".encode()).stdout.decode().strip()
        dup_commit = fxgit("-c", "user.name=t", "-c", "user.email=t@t", "commit-tree", dup_tree, "-m", "dup")
        try:
            review_codex.extract(fx, dup_commit, os.path.join(tmp, "work", "fx-dup", "head"))
            dup_verdict = "extracted"
        except review_codex.Refused as e:
            dup_verdict = str(e)
        check("a name that is both a link and a directory is refused, and nothing is written outside the head",
              "both an entry and a directory" in dup_verdict and os.listdir(target_dir) == [], (dup_verdict, os.listdir(target_dir)))
        chain_verdict = extracted_links({"..data/f": "x", "x": "..data/f", "y": "x"}, "dots")
        check("positive control: a target that merely begins with two dots, and a link to a link inside the head, are extracted", chain_verdict == "extracted", chain_verdict)

        print("refusals: nothing runs, nothing is posted")
        for label, change, why in (
                ("no base URL", {"AGENT_FABRIC_CODEX_BASE_URL": None}, "AGENT_FABRIC_CODEX_BASE_URL"),
                ("no key", {"AGENT_FABRIC_CODEX_KEY": None}, "AGENT_FABRIC_CODEX_KEY"),
                ("an empty key", {"AGENT_FABRIC_CODEX_KEY": ""}, "AGENT_FABRIC_CODEX_KEY"),
                ("a base URL with a path", {"AGENT_FABRIC_CODEX_BASE_URL": "http://127.0.0.1:18080/v1"}, "root"),
                ("the session's Anthropic base URL", {"AGENT_FABRIC_CODEX_BASE_URL": "http://127.0.0.1:9999/"},
                 "ANTHROPIC_BASE_URL"),
                ("the session's Anthropic key", {"AGENT_FABRIC_CODEX_KEY": "sk-ant-session"}, "Anthropic credential"),
                ("no codex binary", {"AGENT_FABRIC_CODEX_BIN": os.path.join(tmp, "no-codex")}, "no codex binary"),
                ("an account id that is not a UUID", {"AGENT_FABRIC_CODEX_ACCOUNT_ID": 'x" }\nmodel = "evil'},
                 "AGENT_FABRIC_CODEX_ACCOUNT_ID"),
                ("an unknown effort level", {"AGENT_FABRIC_CODEX_EFFORT": "max"}, "reasoning effort")):
            set_pr(); mode("ok")
            env = {k: v for k, v in env0.items() if not (k in change and change[k] is None)}
            env.update({k: v for k, v in change.items() if v is not None})
            r = run("7", req, env=env)
            check(f"{label}: refused, named", r.returncode == 1 and "refused" in r.stderr and why in r.stderr, r.stderr)
            check(f"{label}: codex never ran, nothing posted", not codex_ran() and not posted())
        set_pr("f" * 40); mode("ok")
        r = run("7", req)
        check("a request whose head is not the PR's head is refused", r.returncode == 1
              and "not PR #7's head" in r.stderr and not codex_ran() and not posted(), r.stderr)
        set_pr(); mode("ok")
        r = run("7", req, "--timeout", "0")
        check("a zero time budget is a usage error", r.returncode == 2 and not codex_ran(), r.stderr)
        r = subprocess.run([REVIEW, "--engine", "claude", "7", req], env=env0, capture_output=True, text=True,
                           cwd=repo, timeout=60)
        check("an unknown engine is a usage error", r.returncode == 2 and "codex" in r.stderr, r.stderr)
        check("the scratch is empty after every case", scratch_empty(), os.listdir(scratch))
        check("the working copy is untouched after every case", git("status", "--porcelain") == status_before)
    finally:
        subprocess.run(["chmod", "-R", "u+w", tmp], check=False)
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\ntest_review_codex: {'OK' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
