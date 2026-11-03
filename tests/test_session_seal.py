#!/usr/bin/env python3
"""runtime/claude-code/hooks/session-seal.py, the shell seal (agent-fabric ADR-038 rule 9), run each way a session
runs it: directly, as the workspace settings' session-start entry runs it (sh -c, session-start.py loading the seal), and as the managed file runs it
(`python -I -S hook_entry.py session-seal` on a scratch snapshot reached through `current`, from a hostile session
environment: a fake python3 first on PATH, PYTHONPATH naming marker-writing modules, AGENT_FABRIC_ROOT naming a
hostile tree). Each way the env file unsets the harness's credentials and every synced secret's name but the plain
values in env.sh, once per file, writing no value and nothing on stdout, exit 0; the two copies on one file, in
either order, leave one seal. Every check about secrets is asked as set/unset per name in a clean shell, so a
failure prints no value. The scratch snapshot is outside the installed prefix, so hook_entry runs the seal on this
interpreter by its test override.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402
own_instance_tree()

ROOT = os.path.dirname(HERE)
SEAL = os.path.join(ROOT, "runtime", "claude-code", "hooks", "session-seal.py")
ENTRY = os.path.join(ROOT, "runtime", "claude-code", "managed", "hook_entry.py")
WORKSPACE = os.path.join(ROOT, "runtime", "claude-code", "workspace", "settings.json")
sys.path.insert(0, os.path.dirname(ENTRY))
import hook_entry  # noqa: E402

MARKER = "# agent-fabric: no secret in the session shell"
CREDENTIALS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENROUTER_API_KEY",
               "GH_TOKEN", "CLAUDE_BRIDGE_AUTH_TOKEN")
SYNCED = ("OPENAI_API_KEY",)
PLAIN = "DEMO_PORT_OFFSET"
VALUES = ("x-secret-gh", "y z secret")
BASE_PATH = f"{os.path.dirname(sys.executable)}:/usr/local/bin:/usr/bin:/bin"


def write(path: str, text: str, mode: int = 0o644) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, mode)


def scratch() -> str:
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="session-seal-"))
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


def home_with_secrets(tmp: str) -> str:
    home = os.path.join(tmp, "home")
    cfg = os.path.join(home, ".config", "agent-fabric")
    write(os.path.join(cfg, "secrets.env"), f"# agent-fabric secrets\nexport GH_TOKEN={VALUES[0]}\n"
                                            f"export OPENAI_API_KEY='{VALUES[1]}'\nexport {PLAIN}=640\n")
    write(os.path.join(cfg, "env.sh"), f"# agent-fabric secrets\nexport {PLAIN}=640\n")
    return home


def base_env(home: str, env_file: str | None) -> dict:
    env = {"PATH": BASE_PATH, "HOME": home, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    if env_file:
        env["CLAUDE_ENV_FILE"] = env_file
    return env


def probe(env_file: str) -> list[str]:
    """Each name, set or unset, after sourcing the env file in a clean shell where all were planted."""
    names = (*CREDENTIALS, *SYNCED, PLAIN)
    script = "; ".join(f'[ -n "${{{n}+x}}" ] && echo {n}=set || echo {n}=unset' for n in names)
    return subprocess.run(["bash", "-c", f'source "{env_file}"; {script}'], capture_output=True, text=True, timeout=30,
                          env={"PATH": "/usr/bin:/bin", **{n: "planted" for n in names}}).stdout.split()


WANT = [f"{n}=unset" for n in (*CREDENTIALS, *SYNCED)] + [f"{PLAIN}=set"]


def text_of(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def no_value(path: str) -> bool:
    text = text_of(path)
    return not any(v in text for v in VALUES) and "planted" not in text and "=640" not in text


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    tmp = scratch()
    home = home_with_secrets(tmp)

    print("session-seal: run directly")
    env_file = os.path.join(tmp, "direct.env")
    r = subprocess.run([sys.executable, SEAL], input="not json at all", capture_output=True, text=True, timeout=30,
                       env=base_env(home, env_file))
    check("exit 0, nothing on stdout, whatever stdin holds", (r.returncode, r.stdout) == (0, ""), (r.returncode, r.stdout))
    check("the harness's credentials and the synced secrets unset, the plain value kept", probe(env_file) == WANT,
          probe(env_file))
    check("names only: no value of secrets.env in the file", no_value(env_file))
    subprocess.run([sys.executable, SEAL], capture_output=True, timeout=30, env=base_env(home, env_file))
    check("once per file: a second run (resume, compaction) adds nothing", text_of(env_file).count(MARKER) == 1,
          text_of(env_file).count(MARKER))
    with open(env_file, "ab") as f:
        f.write(b"\xff\xfe not utf-8\n")
    subprocess.run([sys.executable, SEAL], capture_output=True, timeout=30, env=base_env(home, env_file))
    check("…a file that is not UTF-8 is still searched", open(env_file, "rb").read().count(MARKER.encode()) == 1)
    latin = os.path.join(tmp, "latin1.env")
    with open(latin, "wb") as f:
        f.write(b"export OTHER=caf\xe9\n")
    for _ in range(2):
        subprocess.run([sys.executable, SEAL], capture_output=True, timeout=30, env=base_env(home, latin))
    check("an env file not UTF-8 before the seal: written, once across two runs",
          open(latin, "rb").read().count(MARKER.encode()) == 1 and probe(latin) == WANT, probe(latin))
    r = subprocess.run([sys.executable, SEAL], capture_output=True, text=True, timeout=30, env=base_env(home, None))
    check("no CLAUDE_ENV_FILE: exit 0, nothing said", (r.returncode, r.stdout, r.stderr) == (0, "", ""), r.stderr)
    r = subprocess.run([sys.executable, SEAL], capture_output=True, text=True, timeout=30,
                       env=base_env(home, os.path.join(tmp, "no-such-dir", "x.env")))
    check("an env file that cannot be written: exit 0, nothing said", (r.returncode, r.stdout) == (0, ""), r.stdout)
    bare = os.path.join(tmp, "bare.env")
    subprocess.run([sys.executable, SEAL], capture_output=True, timeout=30,
                   env=base_env(os.path.join(tmp, "empty-home"), bare))
    check("no secrets.env: the harness's credentials still unset",
          probe(bare)[:len(CREDENTIALS)] == WANT[:len(CREDENTIALS)], probe(bare))
    bad_home = os.path.join(tmp, "bad-home")
    write(os.path.join(bad_home, ".config", "agent-fabric", "env.sh"), "")
    with open(os.path.join(bad_home, ".config", "agent-fabric", "secrets.env"), "wb") as f:
        f.write(b"export GH_TOKEN=x\nexport OTHER=caf\xe9\n")
    bad = os.path.join(tmp, "bad-secrets.env")
    r = subprocess.run([sys.executable, SEAL], capture_output=True, text=True, timeout=30, env=base_env(bad_home, bad))
    check("a secrets.env that is not UTF-8: the harness's credentials still unset, exit 0",
          r.returncode == 0 and probe(bad)[:len(CREDENTIALS)] == WANT[:len(CREDENTIALS)], probe(bad))

    print("session-seal: the workspace copy, session-start.sh as the workspace settings run it")
    ws = json.load(open(WORKSPACE, encoding="utf-8"))
    commands = [h["command"] for g in ws["hooks"]["SessionStart"] for h in g["hooks"]]
    # F1 of #464: a rendered settings file changes only on bootstrap and a launcher pull carries code alone, so the
    # seal needs no settings entry that a settings file rendered before this one lacks.
    check("the seal needs no settings entry that a pre-range rendered file lacks: none names session-seal.py",
          not any("session-seal" in c for c in commands), [c for c in commands if "session-seal" in c])
    starts = [c for c in commands if c.endswith("/hooks/session-start.sh\"")]
    check("one SessionStart entry runs session-start.sh", len(starts) == 1, starts)
    ws_cmd = starts[0] if starts else "false"

    def run_workspace(env_file: str) -> subprocess.CompletedProcess:
        env = {**base_env(home, env_file), "AGENT_FABRIC_ROOT": ROOT, "AGENT_FABRIC_PYTHON": sys.executable,
               "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "ws-state")}
        return subprocess.run(["sh", "-c", ws_cmd], input='{"cwd": "/"}', capture_output=True, text=True, timeout=60,
                              env=env)

    ws_file = os.path.join(tmp, "workspace.env")
    r = run_workspace(ws_file)
    check("that command alone seals: exit 0, the names unset, the plain value kept", r.returncode == 0
          and probe(ws_file) == WANT, (r.returncode, r.stderr, probe(ws_file)))
    check("...names only", no_value(ws_file))
    run_workspace(ws_file)
    check("...once across two runs", text_of(ws_file).count(MARKER) == 1, text_of(ws_file).count(MARKER))

    print("session-seal: the managed hook, through hook_entry from a hostile environment")
    marks = os.path.join(tmp, "marks")
    os.makedirs(marks)
    managed = os.path.join(tmp, "lib", "managed")
    snap = os.path.join(managed, "fabric-" + "b" * 40)
    write(os.path.join(snap, "runtime", "claude-code", "managed", "hook_entry.py"), open(ENTRY, encoding="utf-8").read())
    write(os.path.join(snap, "runtime", "claude-code", "hooks", "session-seal.py"), open(SEAL, encoding="utf-8").read())
    os.symlink(os.path.basename(snap), os.path.join(managed, "current"))
    entry = os.path.join(managed, "current", "runtime", "claude-code", "managed", "hook_entry.py")
    evil = os.path.join(tmp, "evil")
    for prog in ("python3", "python", "bash", "sh", "fabric-python"):
        write(os.path.join(evil, "bin", prog), f"#!/bin/sh\ntouch {marks}/bin-{prog}\nexit 1\n", 0o755)
    for mod in ("sitecustomize", "usercustomize", "re", "os"):
        write(os.path.join(evil, "pylib", f"{mod}.py"), f"open({os.path.join(marks, 'py-' + mod)!r}, 'w').close()\n")
    hostile_root = os.path.join(evil, "fabric")
    write(os.path.join(hostile_root, "runtime", "claude-code", "hooks", "session-seal.py"),
          f"open({os.path.join(marks, 'hostile-root')!r}, 'w').close()\n")

    def run_managed(env_file: str, snapshot_entry: str = entry) -> subprocess.CompletedProcess:
        env = {**base_env(home, env_file), "PATH": f"{evil}/bin:{BASE_PATH}", "PYTHONPATH": f"{evil}/pylib",
               "AGENT_FABRIC_ROOT": hostile_root, "AGENT_FABRIC_PYTHON": f"{evil}/bin/python3",
               "BASH_ENV": f"{evil}/bin/sh", hook_entry.TEST_PY: sys.executable}
        return subprocess.run([sys.executable, "-I", "-S", snapshot_entry, "session-seal"],
                              input=b'{"hook_event_name":"SessionStart","source":"startup"}', capture_output=True,
                              env=env, cwd=os.path.join(evil, "pylib"), timeout=60)

    managed_file = os.path.join(tmp, "managed.env")
    r = run_managed(managed_file)
    check("it seals: exit 0, the names unset, the plain value kept", r.returncode == 0 and probe(managed_file) == WANT,
          (r.returncode, r.stderr, probe(managed_file)))
    check("…and writes nothing to stdout (a SessionStart hook's stdout is the session's context)", r.stdout == b"",
          r.stdout)
    check("…names only", no_value(managed_file))
    check("nothing hostile ran: no fake program, no PYTHONPATH module, not the hostile root's seal",
          os.listdir(marks) == [], os.listdir(marks))
    os.remove(os.path.join(snap, "runtime", "claude-code", "hooks", "session-seal.py"))
    r = run_managed(os.path.join(tmp, "missing.env"))
    check("a snapshot without the seal: silent, exit 0 (it never refuses a start)", (r.returncode, r.stdout) == (0, b""),
          r.stdout)
    write(os.path.join(snap, "runtime", "claude-code", "hooks", "session-seal.py"), open(SEAL, encoding="utf-8").read())

    print("session-seal: both copies on one file")
    for order in (("managed", "workspace"), ("workspace", "managed")):
        both = os.path.join(tmp, f"both-{order[0]}-first.env")
        for which in order:
            (run_managed if which == "managed" else run_workspace)(both)
        check(f"{order[0]} first, then {order[1]}: one seal line, the names unset",
              text_of(both).count(MARKER) == 1 and probe(both) == WANT, (text_of(both).count(MARKER), probe(both)))

    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
