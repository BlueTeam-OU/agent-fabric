#!/usr/bin/env python3
"""tools/fabric/review_gateway.py through bin/fabric-review --engine codex --gateway chatgpt, with a fake
gateway speaking the READY protocol, a fake `codex` and a fake `gh` on PATH: the review starts a gateway of
its own on a schema-1 openai-responses plan, hands Codex its root and local key, and stops it; the access
token is in a 0600 file in a 0700 directory under the runtime directory and nowhere else, and is gone on
every path (agent-fabric ADR-053 rule 3). Every token here is a fake of the real shape; no real codex or
gateway runs. Plain script: ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import base64
import hashlib
import contextlib
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
import gateway_plan  # noqa: E402
import review_gateway  # noqa: E402

FAKE_GATEWAY = r'''#!%(python)s
import hashlib, json, os, signal, stat, sys, time
S = %(state)r
def note(**rec):
    with open(os.path.join(S, "gw.log"), "a") as fh:
        fh.write(json.dumps(rec) + "\n")
mode = open(os.path.join(S, "gw-mode")).read().strip()
if sys.argv[1:] == ["--version", "--json"]:
    note(event="version")
    print(open(os.path.join(S, "gw-version")).read().strip())
    sys.exit(0)
args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
plan_bytes = open(args["--plan"], "rb").read()
plan = json.loads(plan_bytes)
key = os.read(int(args["--local-key-fd"]), 200).decode()
tf = plan["auth_profiles"][0]["path"]
with open(os.path.join(S, "plan-seen.json"), "wb") as fh:
    fh.write(plan_bytes)
note(event="serve", argv=sys.argv[1:], pid=os.getpid(), key_sha=hashlib.sha256(key.encode()).hexdigest(),
     key_is_64_hex=len(key) == 64 and all(c in "0123456789abcdef" for c in key), token_file=tf,
     token_mode=stat.S_IMODE(os.lstat(tf).st_mode), dir_mode=stat.S_IMODE(os.lstat(os.path.dirname(tf)).st_mode),
     token_sha=hashlib.sha256(open(tf, "rb").read()).hexdigest(), env_has_key=key in json.dumps(dict(os.environ)))
if mode == "exit4":
    print("credential_unavailable: the token file was refused (fake)", file=sys.stderr)
    sys.exit(4)
ready = {"event": "ready", "gateway_version": "0.3.0-fake", "runtime_contract": 1, "plan_schema": plan["schema_version"],
         "listener": "http://127.0.0.1:47011", "plan_digest": "sha256:" + hashlib.sha256(plan_bytes).hexdigest()}
def on_term(*a):
    note(event="term")
    if mode == "drain":   # a slow drain: the reviewer's stop() is still waiting when the next signal comes
        open(os.path.join(S, "gw-draining"), "w").close()
        time.sleep(3)
    sys.exit(0)
signal.signal(signal.SIGTERM, on_term)
os.write(int(args["--ready-fd"]), (json.dumps(ready) + "\n").encode())
os.close(int(args["--ready-fd"]))
while True:
    time.sleep(0.1)
'''

FAKE_CODEX = r'''#!%(python)s
import json, os, subprocess, sys, time
S = %(state)r
argv = sys.argv[1:]
sys.stdin.read()
home = os.environ.get("CODEX_HOME", "/nonexistent")
serve = [json.loads(l) for l in open(os.path.join(S, "gw.log")) if '"serve"' in l]
rec = {"argv": argv, "env": dict(os.environ),
       "config": open(os.path.join(home, "config.toml")).read() if os.path.isfile(os.path.join(home, "config.toml")) else None,
       "token_file_there": bool(serve) and os.path.isfile(serve[-1]["token_file"])}
with open(os.path.join(S, "codex-run.json"), "w") as f:
    json.dump(rec, f)
mode = open(os.path.join(S, "codex-mode")).read().strip()
out = argv[argv.index("--output-last-message") + 1]
if mode == "sleep":
    with open(os.path.join(S, "codex-sleeping"), "w") as f:
        f.write(str(os.getpid()))
    time.sleep(300)
elif mode == "ok":
    with open(out, "w") as f:
        f.write(json.dumps({"findings": [{"level": "P2", "file": "app.py", "line": 1, "scenario": "s", "expected": "e", "fix": "f"}]}))
elif mode == "prose":
    with open(out, "w") as f:
        f.write("Looks fine.")
'''

GH_MOCK = r"""#!/usr/bin/env bash
S="$GH_STATE"
case "$1" in
  repo) echo "fixture-org/fixture"; exit 0 ;;
  pr)   cat "$S/pr.json"; exit 0 ;;
  api)
    env > "$S/gh-env.txt"
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

STAGE6 = '{"gateway_version": "0.3.0-fake", "runtime_contract": 1, "plan_schemas": [0, 1], "protocols": ["anthropic", "openai-responses"]}'
ACCOUNT = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"


def b64(doc: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(doc).encode()).decode().rstrip("=")


def fake_jwt(exp: int) -> str:
    """The shape of the ChatGPT access token (a JWT), with fake claims and a fake signature."""
    return f"{b64({'alg': 'RS256', 'typ': 'JWT'})}.{b64({'exp': exp, 'sub': 'fake-subject'})}.ZmFrZS1zaWduYXR1cmU"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:1500]}"))
        fails += not good

    print("the token's lifetime: exp alone, read without a signature check")
    now = 1_800_000_000
    check("exp is read", review_gateway.jwt_exp(fake_jwt(now + 5)) == now + 5)
    for label, tok in (("two parts", "a.b"), ("a payload that is not JSON", "a.bm90IGpzb24.c"),
                       ("no exp", f"a.{b64({'sub': 'x'})}.c"), ("an exp that is a string", f"a.{b64({'exp': '1'})}.c"),
                       ("an exp that is a bool", f"a.{b64({'exp': True})}.c")):
        try:
            review_gateway.jwt_exp(tok)
            msg = ""
        except ValueError as e:
            msg = str(e)
        check(f"{label}: refused without the token in the message", msg != "" and tok not in msg, msg)

    tmp = tempfile.mkdtemp(prefix="test_review_gateway.")
    try:
        state, fakebin, home, scratch, run_dir = (os.path.join(tmp, d) for d in ("state", "bin", "home", "tmp", "run"))
        for d in (state, fakebin, home, scratch, run_dir, os.path.join(home, ".codex")):
            os.makedirs(d, mode=0o700)
        os.chmod(run_dir, 0o700)
        with open(os.path.join(home, ".codex", "auth.json"), "w") as f:
            f.write('{"auth_mode": "apikey"}')
        signin = os.path.join(home, ".codex-chatgpt")
        os.makedirs(signin, mode=0o700)
        access = fake_jwt(int(time.time()) + 240 * 3600)
        refresh, id_token = "fake-refresh-token-0123456789", fake_jwt(int(time.time()) + 3600).replace("fake-subject", "x")
        secrets_ = (access, refresh, id_token)

        def write_signin(doc: dict | None = None, mode_: int = 0o600) -> None:
            doc = doc if doc is not None else {"auth_mode": "chatgpt", "OPENAI_API_KEY": None, "last_refresh": "2026-10-12T00:00:00Z",
                                               "tokens": {"id_token": id_token, "access_token": access, "refresh_token": refresh,
                                                          "account_id": ACCOUNT}}
            path = os.path.join(signin, "auth.json")
            with open(path, "w") as f:
                json.dump(doc, f)
            os.chmod(path, mode_)

        for name, body in (("fake-gateway", FAKE_GATEWAY), ("codex", FAKE_CODEX), ("gh", GH_MOCK)):
            with open(os.path.join(fakebin, name), "w") as f:
                f.write(body % {"python": sys.executable, "state": state} if name != "gh" else body)
            os.chmod(os.path.join(fakebin, name), 0o755)

        repo = os.path.join(tmp, "work", "fixture")
        os.makedirs(repo)

        def git(*a: str) -> str:
            return subprocess.run(["git", "-C", repo, *a], env=git_env(), check=True, capture_output=True,
                                  text=True, timeout=30).stdout.strip()

        git("init", "-q", "-b", "main")
        git("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "base")
        base = git("rev-parse", "HEAD")
        with open(os.path.join(repo, "app.py"), "w") as f:
            f.write("print(1)\n")
        git("add", "app.py")
        git("commit", "-q", "--no-gpg-sign", "-m", "work")
        head = git("rev-parse", "HEAD")
        req = os.path.join(tmp, "req", "REQUEST.yaml")
        os.makedirs(os.path.dirname(req))
        with open(req, "w") as f:
            f.write(f"mode: review\nrepository: {repo}\nrange: {base[:12]}..{head[:12]}\n"
                    "objective: >-\n  The app prints one line.\nrequirements:\n  - It prints 1.\n")
        host = subprocess.run(["hostname", "-s"], capture_output=True, text=True, check=True).stdout.strip()
        me = f"{host}/{pwd.getpwuid(os.geteuid()).pw_name}"

        def reset(gw_mode: str = "ok", codex_mode: str = "ok", version: str = STAGE6) -> None:
            with open(os.path.join(state, "pr.json"), "w") as f:
                json.dump({"number": 7, "state": "OPEN", "headRefName": f"{me}/feat/thing", "headRefOid": head}, f)
            for n in ("calls", "payload.json", "codex-run.json", "gw.log", "plan-seen.json", "gh-env.txt", "codex-sleeping"):
                if os.path.exists(os.path.join(state, n)):
                    os.remove(os.path.join(state, n))
            open(os.path.join(state, "gw.log"), "w").close()
            for n, v in (("gw-mode", gw_mode), ("codex-mode", codex_mode), ("gw-version", version)):
                with open(os.path.join(state, n), "w") as f:
                    f.write(v)

        env0 = {k: v for k, v in os.environ.items()
                if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "ANTHROPIC_", "CLAUDE", "OPENAI_", "CODEX_", "XDG_RUNTIME"))}
        env0.update(PATH=f"{fakebin}:{env0.get('PATH', '')}", GH_STATE=state, GH_REPO="fixture-org/fixture",
                    HOME=home, TMPDIR=scratch, XDG_RUNTIME_DIR=run_dir, AGENT_FABRIC_ROOT=ROOT,
                    AGENT_FABRIC_GW_BIN=os.path.join(fakebin, "fake-gateway"), AGENT_FABRIC_GW_READY_TIMEOUT_S="10",
                    AGENT_FABRIC_CODEX_MODEL="gpt-test-6",
                    ANTHROPIC_BASE_URL="http://127.0.0.1:9999", ANTHROPIC_API_KEY="sk-ant-session",
                    CODEX_HOME=os.path.join(home, ".codex"))

        def run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
            return subprocess.run([REVIEW, "--engine", "codex", "7", req, "--gateway", "chatgpt", *args], env=env or env0,
                                  capture_output=True, text=True, cwd=repo, timeout=90)

        def events(kind: str) -> list[dict]:
            with open(os.path.join(state, "gw.log")) as f:
                return [json.loads(ln) for ln in f if ln.strip() and json.loads(ln).get("event") == kind]

        def read(name: str) -> str:
            try:
                with open(os.path.join(state, name)) as f:
                    return f.read()
            except OSError:
                return ""

        def codex_ran() -> bool:
            return os.path.exists(os.path.join(state, "codex-run.json"))

        def posted() -> bool:
            return os.path.exists(os.path.join(state, "calls"))

        def runtime_clean() -> bool:
            top = os.path.join(run_dir, "agent-fabric")
            return not os.path.isdir(top) or os.listdir(top) == []

        def gone(pid: int) -> bool:
            for _ in range(50):
                try:
                    with open(f"/proc/{pid}/stat") as f:
                        if f.read().split()[2] == "Z":
                            return True
                except OSError:
                    return True
                time.sleep(0.1)
            return False

        def no_secret_in(text: str) -> bool:
            return not any(s in text for s in secrets_)

        print("success: a gateway of its own, Codex through it, stopped before the post")
        write_signin(); reset()
        r = run()
        check("exit 0", r.returncode == 0, r.stderr + r.stdout)
        serves = events("serve")
        check("the gateway was started once", len(serves) == 1, serves)
        sv = serves[0] if serves else {}
        check("its local key came on a descriptor, 64 hex, never in argv or its environment",
              sv.get("key_is_64_hex") and "--local-key-fd" in sv.get("argv", []) and not sv.get("env_has_key"), sv)
        check("the token file is 0600 in a 0700 directory under the runtime directory",
              sv.get("token_mode") == 0o600 and sv.get("dir_mode") == 0o700
              and sv.get("token_file", "").startswith(os.path.realpath(run_dir) + "/agent-fabric/"), sv)
        check("it holds the access token alone", sv.get("token_sha") == hashlib.sha256(access.encode()).hexdigest())
        plan_text = read("plan-seen.json")
        plan = json.loads(plan_text or "{}")
        check("the plan on disk validates under schema 1", gateway_plan.validate(plan, 1) == [], gateway_plan.validate(plan, 1))
        check("the plan names the token file and holds no token", plan.get("auth_profiles", [{}])[0].get("path") == sv.get("token_file")
              and no_secret_in(plan_text), plan_text[:400])
        check("the plan routes the model to the ChatGPT backend",
              plan.get("routes", [{}])[0].get("source", {}).get("model_selector") == "gpt-test-6"
              and plan.get("backends", [{}])[0].get("base_url") == "https://chatgpt.com/backend-api/codex", plan)
        rec = json.loads(read("codex-run.json") or "{}")
        cenv, cfg = rec.get("env", {}), rec.get("config") or ""
        key = cenv.get("AGENT_FABRIC_CODEX_KEY", "")
        check("Codex was given the gateway's key by environment", hashlib.sha256(key.encode()).hexdigest() == sv.get("key_sha"), cenv)
        check("…and its root as the provider's base URL", 'base_url = "http://127.0.0.1:47011"' in cfg, cfg)
        check("the token file existed while Codex ran", rec.get("token_file_there") is True, rec.get("token_file_there"))
        check("the account id reaches config.toml as the ChatGPT-Account-ID header, and Codex's environment does not carry it",
              f'http_headers = {{ "ChatGPT-Account-ID" = "{ACCOUNT}" }}' in cfg and ACCOUNT not in json.dumps(cenv), cfg)
        check("the key is not in config.toml or Codex's argv", key and key not in cfg and key not in json.dumps(rec.get("argv")))
        check("no token of the sign-in reaches Codex", no_secret_in(json.dumps(rec)))
        check("no session credential reaches Codex", "sk-ant-session" not in json.dumps(cenv))
        check("the effort is high", 'model_reasoning_effort="high"' in rec.get("argv", []), rec.get("argv"))
        check("the gateway was stopped (SIGTERM) and is gone", events("term") != [] and gone(sv.get("pid", 0)), read("gw.log"))
        check("the token file and its directory are removed", not os.path.exists(sv.get("token_file", "/")) and runtime_clean(),
              os.listdir(run_dir))
        check("the review was posted", posted() and "**Engine:** Codex" in read("payload.json"), read("payload.json")[:300])
        gh_env = read("gh-env.txt")
        check("the post's child never saw the local key or a token", gh_env != "" and key not in gh_env and no_secret_in(gh_env))
        check("no token on the review's output", no_secret_in(r.stdout + r.stderr))

        print("a failed review: nothing posted, the gateway stopped, the token gone")
        write_signin(); reset(codex_mode="prose")
        r = run()
        sv = (events("serve") or [{}])[0]
        check("exit 1, nothing posted", r.returncode == 1 and not posted() and "nothing posted" in r.stderr, r.stderr)
        check("the gateway is gone and the token removed", gone(sv.get("pid", 0)) and runtime_clean())

        print("the time budget: the same")
        write_signin(); reset(codex_mode="sleep")
        r = run("--timeout", "0.05")
        sv = (events("serve") or [{}])[0]
        check("exit 1 at the budget, nothing posted", r.returncode == 1 and "did not answer within" in r.stderr and not posted(), r.stderr)
        check("the gateway is gone and the token removed", gone(sv.get("pid", 0)) and runtime_clean())

        print("SIGTERM mid-review: the same")
        write_signin(); reset(codex_mode="sleep")
        p = subprocess.Popen([REVIEW, "--engine", "codex", "7", req, "--gateway", "chatgpt"], env=env0, cwd=repo,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(300):
            if os.path.exists(os.path.join(state, "codex-sleeping")):
                break
            time.sleep(0.05)
        p.send_signal(signal.SIGTERM)
        _, err = p.communicate(timeout=60)
        sv = (events("serve") or [{}])[0]
        check("exit 143, nothing posted", p.returncode == 143 and not posted(), (p.returncode, err))
        check("the gateway is gone and the token removed", gone(sv.get("pid", 0)) and runtime_clean(), os.listdir(run_dir))

        # A signal while the gateway drains used to cut the cleanup short and leave the token (review of #224, F1).
        print("SIGTERM while the gateway is being stopped: the token is still removed")
        write_signin(); reset(gw_mode="drain")
        for n in ("gw-draining",):
            with contextlib.suppress(FileNotFoundError):
                os.unlink(os.path.join(state, n))
        p = subprocess.Popen([REVIEW, "--engine", "codex", "7", req, "--gateway", "chatgpt", "--no-post"], env=env0, cwd=repo,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(400):
            if os.path.exists(os.path.join(state, "gw-draining")):
                break
            time.sleep(0.05)
        drained = os.path.exists(os.path.join(state, "gw-draining"))
        p.send_signal(signal.SIGTERM)
        _, err = p.communicate(timeout=60)
        sv = (events("serve") or [{}])[0]
        check("the signal came while the gateway drained, and the token and scratch are gone",
              drained and gone(sv.get("pid", 0)) and runtime_clean(), (drained, p.returncode, err[-300:], os.listdir(run_dir)))

        print("the gateway fails to start: nothing posted, Codex never ran")
        write_signin(); reset(gw_mode="exit4")
        r = run()
        check("refused, the gateway's own words said", r.returncode == 1 and "refused" in r.stderr
              and "credential source" in r.stderr and "token file was refused (fake)" in r.stderr, r.stderr)
        check("Codex never ran, nothing posted, the token removed", not codex_ran() and not posted() and runtime_clean())

        print("refusals before anything starts")
        for label, version, want in (
                ("a gateway without plan schema 1 (0.2.0)", '{"gateway_version": "0.2.0", "runtime_contract": 1, "plan_schemas": [0]}',
                 "not 1"),
                ("a gateway reading schema 1 without serving openai-responses",
                 '{"gateway_version": "0.2.9", "runtime_contract": 1, "plan_schemas": [0, 1], "protocols": ["anthropic"]}',
                 "not openai-responses")):
            write_signin(); reset(version=version)
            r = run()
            check(f"{label}: refused by name", r.returncode == 1 and want in r.stderr and "Nothing started" in r.stderr, r.stderr)
            check(f"{label}: no gateway served, Codex never ran, nothing written or posted",
                  not events("serve") and not codex_ran() and not posted() and runtime_clean())
        soon = fake_jwt(int(time.time()) + 10 * 60)
        for label, doc, mode_, flag, want in (
                ("a token with 10 minutes left", {"auth_mode": "chatgpt", "tokens": {"access_token": soon, "account_id": ACCOUNT}}, 0o600,
                 None, "minutes left"),
                ("an expired token", {"auth_mode": "chatgpt", "tokens": {"access_token": fake_jwt(1000), "account_id": ACCOUNT}}, 0o600,
                 None, "expired"),
                ("an API-key sign-in", {"auth_mode": "apikey", "OPENAI_API_KEY": "sk-fake"}, 0o600, None, "not a ChatGPT sign-in"),
                ("an account id that is not a UUID", {"auth_mode": "chatgpt", "tokens": {"access_token": access, "account_id": "acct"}},
                 0o600, None, "account_id"),
                ("an access token that is not a JWT", {"auth_mode": "chatgpt", "tokens": {"access_token": "opaque", "account_id": ACCOUNT}},
                 0o600, None, "not a JWT"),
                ("a sign-in others can read", None, 0o644, None, "chmod 600"),
                ("the account's ~/.codex", None, 0o600, os.path.join(home, ".codex"), "never reads"),
                ("no sign-in there", None, 0o600, os.path.join(tmp, "nowhere"), "no ChatGPT sign-in")):
            write_signin(doc, mode_); reset()
            r = run(*(["--codex-home", flag] if flag else []))
            check(f"{label}: refused, named", r.returncode == 1 and "refused" in r.stderr and want in r.stderr, r.stderr)
            check(f"{label}: the gateway was not even asked, nothing written, run or posted",
                  read("gw.log") == "" and not codex_ran() and not posted() and runtime_clean())
            check(f"{label}: no token in the message", no_secret_in(r.stderr) and soon not in r.stderr, r.stderr)
        write_signin({"auth_mode": "chatgpt", "tokens": {"access_token": fake_jwt(int(time.time()) + 2 * 3600), "account_id": ACCOUNT}})
        reset()
        r = run("--timeout", "300")
        check("a token whose life is shorter than a long time budget: refused", r.returncode == 1 and "minutes left" in r.stderr
              and read("gw.log") == "", r.stderr)
        write_signin(); reset()
        r = run(env={**env0, "XDG_RUNTIME_DIR": os.path.join(tmp, "no-such-dir")})
        check("no runtime directory: refused, nothing served or posted", r.returncode == 1 and "runtime directory" in r.stderr
              and not events("serve") and not codex_ran() and not posted(), r.stderr)
        write_signin(); reset()
        r = run(env={k: v for k, v in env0.items() if k != "AGENT_FABRIC_CODEX_MODEL"})
        check("no model: refused before the gateway is asked", r.returncode == 1 and "AGENT_FABRIC_CODEX_MODEL" in r.stderr
              and read("gw.log") == "", r.stderr)
        check("the runtime directory is clean after every case", runtime_clean(), os.listdir(run_dir))
    finally:
        subprocess.run(["chmod", "-R", "u+w", tmp], check=False)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\ntest_review_gateway: {'OK' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
