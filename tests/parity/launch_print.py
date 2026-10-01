#!/usr/bin/env python3
"""tests/parity/launch_print.py — the launcher's `--print`, byte for byte,
the bash at a base commit against the Python at this tree, for every role
in identities/roles/catalog.json and both providers (ADR-040 Wave 4: the
launcher starts every session, so its port was compared before the switch,
and the comparison is kept here, with its result beside it in
launch_print-wave4.txt).

    python3 tests/parity/launch_print.py [--base <ref>] [--head <tree-ish>]
                                         # defaults origin/main, HEAD

Not a suite: tests/run.sh does not run it, because after the port merges
no commit ahead of the base still has the bash. --base names a commit that
does (the Wave 4 base, c2949ba, or any before it).

Each case runs in a fabric made from the head's files (git archive
<head>, HEAD unless named — `git write-tree` names the staged tree: the real
routing, profiles, charters and prompt
sections, with no .git, so no launch fetches or pulls), a state directory
binding this login to the role, a scratch HOME and launch directory, and a
fake `ori` and `claude` on PATH (--print execs neither; the launcher
only checks they exist and that ori's auth is from the environment). The
bash launcher is that tree with the base's runtime/openrouter/launch put
back at a second path; nothing else differs between the two runs.
Exit 0 when every case is identical in exit status and stdout bytes;
stderr is reported, not compared (the launcher writes nothing there on a
clean --print).
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
TIMEOUT_S = 120
FAKE_ORI = """#!/usr/bin/env bash
if [[ "${1:-}" == auth ]]; then
    echo '{"ok":true,"data":{"authenticated":true,"source":{"kind":"environment","location":"OPENROUTER_API_KEY"}}}'
    exit 0
fi
echo "parity: ori must not be executed by --print" >&2; exit 99
"""
FAKE_CLAUDE = """#!/usr/bin/env bash
echo "parity: claude must not be executed by --print" >&2; exit 99
"""


def git(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", ROOT, *args], check=True, timeout=TIMEOUT_S, **kw)


def write(path: str, text: str, mode: int = 0o644) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, mode)


def run(launcher: str, provider: str, env: dict, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", launcher, "--print", "--provider", provider], cwd=cwd, env=env,
                          stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT_S)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="origin/main", help="a commit whose runtime/openrouter/launch is the bash")
    ap.add_argument("--head", default="HEAD", help="the tree with the Python launcher (a commit or a tree id)")
    a = ap.parse_args()
    base_launcher = git("show", f"{a.base}:runtime/openrouter/launch", capture_output=True).stdout
    if not base_launcher.startswith(b"#!/usr/bin/env bash") or b"tools/fabric/launch.py" in base_launcher:
        print(f"parity: {a.base}:runtime/openrouter/launch is not the bash launcher", file=sys.stderr)
        return 2
    head = git("rev-parse", "--short", a.head, capture_output=True, text=True).stdout.strip()
    base = git("rev-parse", "--short", a.base, capture_output=True, text=True).stdout.strip()
    login = pwd.getpwuid(os.getuid()).pw_name
    with open(os.path.join(ROOT, "identities", "roles", "catalog.json"), encoding="utf-8") as fh:
        roles = [r["id"] for r in json.load(fh)["roles"]]

    with tempfile.TemporaryDirectory(prefix="launch-parity-") as tmp:
        fabric, state, home, bindir, wc = (os.path.join(tmp, d) for d in ("fabric", "state", "home", "bin", "wc"))
        os.makedirs(fabric)
        archive = git("archive", "--format=tar", a.head, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", fabric], input=archive, check=True, timeout=TIMEOUT_S)
        old = os.path.join(fabric, "runtime", "openrouter", "launch.base")
        with open(old, "wb") as fh:
            fh.write(base_launcher)
        new = os.path.join(fabric, "runtime", "openrouter", "launch")
        write(os.path.join(bindir, "ori"), FAKE_ORI, 0o755)
        write(os.path.join(bindir, "claude"), FAKE_CLAUDE, 0o755)
        os.makedirs(home)
        os.makedirs(wc)
        subprocess.run(["git", "init", "-q", wc], check=True, timeout=TIMEOUT_S)
        env = {"PATH": f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}", "HOME": home,
               "LANG": os.environ.get("LANG", "C.UTF-8"), "AGENT_FABRIC_ROOT": fabric,
               "AGENT_FABRIC_STATE_DIR": state, "TMPDIR": os.path.join(tmp, "t")}
        if "AGENT_FABRIC_PYTHON" in os.environ:
            env["AGENT_FABRIC_PYTHON"] = os.environ["AGENT_FABRIC_PYTHON"]
        os.makedirs(env["TMPDIR"])
        rows, differ = [], 0
        for role in roles:
            write(os.path.join(state, "agents", login, "binding.json"),
                  json.dumps({"agent": login, "host": os.uname().nodename.split(".")[0], "role": role,
                              "updated_at": "x"}) + "\n")
            for provider in ("openrouter", "anthropic"):
                b = run(old, provider, env, wc)
                p = run(new, provider, env, wc)
                same = b.returncode == p.returncode and b.stdout == p.stdout
                differ += not same
                rows.append((role, provider, b.returncode, p.returncode, len(b.stdout), same,
                             b.stderr.decode("utf-8", "replace").strip(), p.stderr.decode("utf-8", "replace").strip()))
                if not same:
                    sys.stderr.write(f"--- {role} {provider}: bash rc={b.returncode}\n{b.stdout.decode('utf-8', 'replace')}"
                                     f"{b.stderr.decode('utf-8', 'replace')}\n+++ python rc={p.returncode}\n"
                                     f"{p.stdout.decode('utf-8', 'replace')}{p.stderr.decode('utf-8', 'replace')}\n")
        if os.listdir(env["TMPDIR"]):
            print(f"parity: the launches left {os.listdir(env['TMPDIR'])} in their TMPDIR", file=sys.stderr)

    print(f"launch --print parity: bash at {base} vs python at {head}, {len(rows)} cases, login {login}")
    print(f"{'role':<20} {'provider':<11} {'rc bash/py':<11} {'stdout bytes':>12}  identical")
    for role, provider, rb, rp, n, same, eb, ep in rows:
        print(f"{role:<20} {provider:<11} {f'{rb}/{rp}':<11} {n:>12}  {'yes' if same else 'NO'}")
        for side, err in (("bash", eb), ("python", ep)):
            if err:
                print(f"    stderr ({side}): {err.splitlines()[-1]}")
    print(f"{len(rows) - differ} identical, {differ} different")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
