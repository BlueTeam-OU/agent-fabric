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

from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402

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
def answer(text):
    with open(out, "w") as f:
        f.write(text)
if mode == "sleep":
    p = subprocess.Popen(["sleep", "300"])
    with open(os.path.join(S, "grandchild"), "w") as f:
        f.write(str(p.pid))
    time.sleep(300)
elif mode == "ok":
    answer(json.dumps({"findings": [
        {"level": "P3", "file": "app.py", "line": 2, "scenario": "a\nmulti-line scenario", "expected": "e3", "fix": "f3"},
        {"level": "P1", "file": "app.py", "line": 1, "scenario": "s1", "expected": "e1", "fix": "f1"}]}))
elif mode == "empty":
    answer('{"findings": []}')
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
    pass
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
            for n in ("calls", "payload.json", "codex-run.json", "codex-calls", "grandchild"):
                if os.path.exists(os.path.join(state, n)):
                    os.remove(os.path.join(state, n))

        def mode(m: str) -> None:
            with open(os.path.join(state, "mode"), "w") as f:
                f.write(m)

        env0 = {k: v for k, v in os.environ.items()
                if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "ANTHROPIC_", "CLAUDE", "OPENAI_", "CODEX_"))}
        env0.update(PATH=f"{fakebin}:{env0.get('PATH', '')}", GH_STATE=state, GH_REPO="fixture-org/fixture",
                    HOME=home, TMPDIR=scratch, AGENT_FABRIC_ROOT=ROOT,
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

        for m, why in (("prose", "not one JSON object"), ("fence", "not one JSON object"),
                       ("badschema", "codex-answer.schema.json"), ("exit1", "exited 3"),
                       ("noanswer", "wrote no answer")):
            print(f"a failed review ({m}): nothing posted, the reason said")
            set_pr(); mode(m)
            r = run("7", req)
            check("exit 1", r.returncode == 1, r.stderr)
            check("the reason is said", "nothing posted" in r.stderr and why in r.stderr, r.stderr)
            check("nothing posted", not posted())
            check("the scratch is removed", scratch_empty(), os.listdir(scratch))

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

        print("refusals: nothing runs, nothing is posted")
        for label, change, why in (
                ("no base URL", {"AGENT_FABRIC_CODEX_BASE_URL": None}, "AGENT_FABRIC_CODEX_BASE_URL"),
                ("no key", {"AGENT_FABRIC_CODEX_KEY": None}, "AGENT_FABRIC_CODEX_KEY"),
                ("an empty key", {"AGENT_FABRIC_CODEX_KEY": ""}, "AGENT_FABRIC_CODEX_KEY"),
                ("no model", {"AGENT_FABRIC_CODEX_MODEL": None}, "AGENT_FABRIC_CODEX_MODEL"),
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
