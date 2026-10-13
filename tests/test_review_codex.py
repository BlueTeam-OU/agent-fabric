#!/usr/bin/env python3
"""tools/fabric/review_codex.py through bin/fabric-review --engine codex, with
a fake `codex` and a fake `gh` on PATH: the second engine runs Codex once,
read-only, on an extract of the PR's head, through its own gateway with the
session's credentials scrubbed, and posts a schema-valid answer or nothing
(agent-fabric ADR-053 rules 1-4). No real codex runs here. Plain script:
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import pwd
import signal
import subprocess
import sys
import tempfile
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
mode = open(os.path.join(S, "mode")).read().strip()
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
    ev({"type": "turn.completed", "usage": {"input_tokens": 20, "cached_input_tokens": 0, "output_tokens": 10}})
OK = json.dumps({"findings": [
    {"level": "P3", "file": "app.py", "line": 2, "scenario": "a\nmulti-line scenario", "expected": "e3", "fix": "f3"},
    {"level": "P1", "file": "app.py", "line": 1, "scenario": "s1", "expected": "e1", "fix": "f1"}]})
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
    answer('{"findings": []}')
elif mode == "retried":
    ev({"type": "thread.started", "thread_id": "t"})
    ev({"type": "error", "message": "Reconnecting... 1/5 (stream disconnected before completion: error sending request)"})
    answer('{"findings": []}')
elif mode == "eventonly":
    answer('{"findings": []}', file=False)
elif mode == "nohost":
    # The live defect (2026-10-12): the tool host missing, no command run, an empty answer from the brief alone.
    print("ERROR codex_core::tools::router: error=failed to spawn code-mode host", file=sys.stderr)
    ev({"type": "thread.started", "thread_id": "t"})
    item("error", message=HOST)
    answer('{"findings": []}', commands=0)
elif mode == "nocommand":
    answer('{"findings": []}', commands=0)
elif mode == "cmdfailed":
    ev({"type": "turn.started"})
    command("cat nope", code=1)
    answer('{"findings": []}', commands=0)
elif mode == "othererror":
    item("error", message="something else went wrong")
    answer('{"findings": []}')
elif mode == "turnfailed":
    ev({"type": "turn.started"})
    ev({"type": "error", "message": "stream disconnected before completion: error sending request"})
    ev({"type": "turn.failed", "error": {"message": "stream disconnected before completion: error sending request"}})
    sys.exit(1)
elif mode == "turnfailed-long":
    ev({"type": "turn.failed", "error": {"message": "first line\nsecond line " + "x" * 2000}})
    sys.exit(1)
elif mode == "prose":
    answer("Looks good to me! No findings.")
elif mode == "fence":
    answer('```json\n{"findings": []}\n```')
elif mode == "badschema":
    answer('{"findings": [{"level": "P2", "file": "app.py", "line": 3, "scenario": "s", "expected": "e"}]}')
elif mode == "exit1":
    print("backend said no", file=sys.stderr)
    sys.exit(3)
elif mode == "noanswer":
    ev({"type": "turn.started"})
    command("wc -l app.py")
    ev({"type": "turn.completed", "usage": {}})
elif mode == "noevents":
    with open(out, "w") as f:
        f.write('{"findings": []}')
'''

GH_MOCK = r"""#!/usr/bin/env bash
S="$GH_STATE"
case "$1" in
  repo) echo "fixture-org/fixture"; exit 0 ;;
  pr)   cat "$S/pr.json"; exit 0 ;;
  api)
    for a in "$@"; do
      [ "$prev" = "--input" ] && cp "$a" "$S/payload.json"
      prev="$a"
    done
    echo "POST $2" >> "$S/calls"
    echo "https://github.com/fixture-org/fixture/pull/7#pullrequestreview-1"
    exit 0 ;;
esac
echo "mock gh: unhandled $1" >&2; exit 1
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

    check("a valid answer passes", verdict(json.dumps({"findings": [good]})) == "ok")
    check("no findings is a clean answer", verdict('{"findings": []}') == "ok")
    for label, doc in (("a finding without fix", {"findings": [{k: v for k, v in good.items() if k != "fix"}]}),
                       ("level P4", {"findings": [{**good, "level": "P4"}]}),
                       ("line 0", {"findings": [{**good, "line": 0}]}),
                       ("a line that is a string", {"findings": [{**good, "line": "4"}]}),
                       ("an empty scenario", {"findings": [{**good, "scenario": "  "}]}),
                       ("an extra key on a finding", {"findings": [{**good, "confidence": 1}]}),
                       ("an extra top-level key", {"findings": [], "summary": "fine"}),
                       ("no findings key", {}),
                       ("an absolute file", {"findings": [{**good, "file": "/etc/passwd"}]}),
                       ("a file climbing out", {"findings": [{**good, "file": "../x.py"}]})):
        check(f"refused: {label}", verdict(json.dumps(doc)) != "ok", verdict(json.dumps(doc)))
    for label, text in (("prose", "No findings."), ("a fence", '```json\n{"findings": []}\n```'),
                        ("two objects", '{"findings": []}{"findings": []}'), ("a list", "[]"), ("nothing", ""),
                        ("a duplicate key", '{"findings": [], "findings": []}'),
                        ("NaN", '{"findings": [{"level": "P1", "file": "a", "line": NaN, "scenario": "s", '
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
            f.write(GH_MOCK)
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
                json.dump({"number": 7, "state": "OPEN", "headRefName": f"{me}/feat/thing", "headRefOid": oid}, f)
            for n in ("calls", "payload.json", "codex-run.json", "codex-calls", "grandchild", "sandbox-calls", "sandbox-mode"):
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

        def posted() -> bool:
            return os.path.exists(os.path.join(state, "calls"))

        print("success: Codex runs once, read-only, on the extract, and the review is posted")
        set_pr(); mode("ok")
        r = run("7", req)
        check("exit 0", r.returncode == 0, r.stderr + r.stdout)
        with open(os.path.join(state, "codex-calls")) as f:
            check("codex ran exactly once", f.read() == "run\n")
        rec = record()
        argv = rec["argv"]
        check("codex exec with --sandbox read-only", argv[:1] == ["exec"]
              and argv[argv.index("--sandbox") + 1] == "read-only", argv)
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
        brief = subprocess.run([REVIEW, "brief", req], env=env0, capture_output=True, text=True, timeout=60).stdout
        check("the prompt is the rendered brief, unchanged, then the answer shape",
              bool(brief) and rec["prompt"] == brief.rstrip("\n") + "\n" + review_codex.ANSWER_SHAPE, rec["prompt"][-400:])
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
        check("posted with the review marker and --model codex",
              lines[:2] == ["<!-- agent-fabric-review v1 -->", "<!-- model: codex -->"], lines[:3])
        check("the post names Codex, not the review class", "Codex, the second review engine" in b, b[:400])
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
        check("two probes in the extract, read-only profile: a command starts, a write is refused",
              len(probes) == 2 and all(p[:3] == ["sandbox", "-P", ":read-only"] for p in probes)
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
        time.sleep(0.3)
        alive = []
        for pid in pids:
            try:
                os.kill(pid, 0)
                alive.append(pid)
            except ProcessLookupError:
                pass
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

        print("--no-post prints the review and posts nothing")
        set_pr(); mode("empty")
        r = run("7", req, "--no-post")
        check("exit 0 and the body on stdout", r.returncode == 0 and r.stdout.startswith("**Engine:** Codex")
              and "No findings." in r.stdout, r.stderr + r.stdout)
        check("nothing posted", not posted())

        for m in ("retried", "eventonly"):
            print(f"a run that read the code ({m}) is posted")
            set_pr(); mode(m)
            r = run("7", req)
            check("exit 0, posted, no findings said", r.returncode == 0 and posted() and "No findings." in payload_body(),
                  r.stderr)

        for m, why in (("prose", "not one JSON object"), ("fence", "not one JSON object"),
                       ("badschema", "codex-answer.schema.json"), ("exit1", "exited 3: backend said no"),
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
        print("a signal while posting: it says the review may have been posted")
        import contextlib
        import io

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
        check("…and the review's first line names it", "`gpt-6.1-sol`" in r.stdout.split("\n")[0], r.stdout[:300])
        check("the environment's gateway still gets no level unless one is asked for (review of #224, F2)",
              not any(a.startswith("model_reasoning_effort") for a in rec["argv"]) and "-c" not in rec["argv"]
              and "**effort:** Codex's default" in r.stdout.split("\n")[0], rec["argv"])
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
                  r.returncode == 0 and "`gpt-test`" in r.stdout.split("\n")[0], r.stderr)
        with open(local_layer, "w") as f:
            json.dump({"providers": {"openai": {"capabilities": {"code-review": "gpt-6.1-sol"}}}}, f)
        set_pr(); mode("empty")
        r = run("7", req, "--no-post", env=no_model)
        check("an admitted model in the local layer is what runs", r.returncode == 0
              and "`gpt-6.1-sol`" in r.stdout.split("\n")[0], r.stderr)
        os.remove(local_layer)

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
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\ntest_review_codex: {'OK' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
