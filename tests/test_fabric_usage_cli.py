#!/usr/bin/env python3
"""bin/fabric-usage's sudo fallback: the per-account read, run against a
scratch home. A login on a Claude-account template is `setup-token` (its
own sign-in is another account's; the template cannot read usage), and
neither token is ever printed. Ported from tests/test_fabric-usage.sh
(ADR-040 Wave 6), case for case. Then the table around it, through the
shim with a fake executor: never silently short, a registry it cannot
read refused (tools/fabric/usage.py, ADR-040 Wave 3). Plain script:
prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.abspath(os.environ.get("FABRIC_USAGE") or os.path.join(ROOT, "bin", "fabric-usage"))
if not os.path.isfile(TOOL):
    sys.exit(f"test: script under test not found at {TOOL}")


def read_text() -> str:
    """The READ text, exactly as tools/fabric/usage.py hands it to the executor."""
    spec = importlib.util.spec_from_file_location("fabric_usage", os.path.join(ROOT, "tools", "fabric", "usage.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.READ


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    read = read_text()
    check("the per-account read is found in tools/fabric/usage.py", bool(read))

    with tempfile.TemporaryDirectory() as sandbox:
        home = os.path.join(sandbox, "h")
        os.makedirs(os.path.join(home, ".claude"))
        os.makedirs(os.path.join(home, ".config", "agent-fabric"))
        secrets = os.path.join(home, ".config", "agent-fabric", "secrets.env")

        def put(path: str, text: str) -> None:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

        put(os.path.join(home, ".claude", ".credentials.json"),
            '{"claudeAiOauth":{"accessToken":"sk-ant-oat01-OWN-SIGNIN"}}')
        put(os.path.join(home, ".claude.json"), '{"oauthAccount":{"emailAddress":"old@example.org"}}')
        put(secrets, "export CLAUDE_CODE_OAUTH_TOKEN='sk-ant-oat01-TEMPLATE'\n")
        # curl must never run for a template login: a fake that records it.
        curl_ran = os.path.join(sandbox, "curl-ran")
        os.makedirs(os.path.join(sandbox, "bin"))
        # It keeps its argv and its stdin, to show where the token went.
        put(os.path.join(sandbox, "bin", "curl"),
            f'#!/bin/sh\ntouch "{curl_ran}"\nprintf "%s\\n" "$@" > "{curl_ran}.argv"\ncat > "{curl_ran}.stdin"\nexit 7\n')
        os.chmod(os.path.join(sandbox, "bin", "curl"), 0o755)
        env = {"HOME": home, "PATH": os.path.join(sandbox, "bin") + os.pathsep + os.environ.get("PATH", "")}

        def run() -> str:
            r = subprocess.run(["sh", "-c", read], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=30)
            return r.stdout.rstrip("\n")

        out = run()
        check("a login on a template reads as setup-token, not as its old account",
              out == "setup-token" and not os.path.exists(curl_ran), out)
        check("…with neither its old email nor any token in the output",
              "old@example.org" not in out and "sk-ant-" not in out, out)

        put(secrets, "export CLAUDE_CODE_OAUTH_TOKEN=''\n")
        out = run()
        check("an empty synced value is no template, as syncedVar reads it", out != "setup-token", out)

        os.remove(secrets)
        if os.path.exists(curl_ran):
            os.remove(curl_ran)
        out = run()
        check("no template: the login's own sign-in is read, as before",
              os.path.exists(curl_ran) and re.search(r"^read-failed\told@example\.org$", out, re.M) is not None, out)
        check("…and its token stays out of the output", "sk-ant-" not in out, out)
        argv, stdin = "", ""
        if os.path.exists(curl_ran + ".argv"):
            with open(curl_ran + ".argv", encoding="utf-8") as fh:
                argv = fh.read()
            with open(curl_ran + ".stdin", encoding="utf-8") as fh:
                stdin = fh.read()
        check("…sent as a header on curl's stdin, never in its argv",
              "sk-ant-" not in argv and stdin == "Authorization: Bearer sk-ant-oat01-OWN-SIGNIN\n"
              and "@-" in argv.split("\n"), f"argv: {argv!r}\nstdin: {stdin!r}")

    print("fabric-usage: the table, one row for every placed account")
    with tempfile.TemporaryDirectory() as t:
        calls = os.path.join(t, "calls")
        hx = os.path.join(t, "hostexec")
        # The executor's answer per account; "!fail" prints a line that
        # looks like numbers and exits non-zero: a read cut short is no answer.
        lines = {"ok-one": "a@x.org\t45.5\t2026-10-06T10:00\t12\t2026-10-09T00:00",
                 "down-one": "!fail", "bare-one": "no-credentials", "late-one": "read-failed\tl@x.org"}
        with open(os.path.join(t, "lines.json"), "w", encoding="utf-8") as fh:
            json.dump(lines, fh)
        with open(hx, "w", encoding="utf-8") as fh:
            fh.write(f"#!{sys.executable}\nimport json, sys\n"
                     f"open({calls!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
                     "login = sys.argv[sys.argv.index('--as') + 1]\n"
                     f"line = json.load(open({os.path.join(t, 'lines.json')!r}))[login]\n"
                     "print('x@x.org\\t1\\t2\\t3\\t4' if line == '!fail' else line)\n"
                     "sys.exit(3 if line == '!fail' else 0)\n")
        os.chmod(hx, 0o755)
        registry = os.path.join(t, "registry.json")
        with open(registry, "w", encoding="utf-8") as fh:
            # deck-human is a human login (ADR-044): never asked, never a row.
            json.dump({"placement": {"ok-one": "h1", "down-one": "h2", "deck-human": "h1", "bare-one": "h1", "late-one": "h2"},
                       "kinds": {"deck-human": "human"}}, fh)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        env.update(AGENT_FABRIC_HOSTS_REGISTRY=registry, AGENT_FABRIC_HOSTEXEC=hx)

        def usage(*args: str) -> tuple[int, str, str]:
            r = subprocess.run([TOOL, *args], env=env, capture_output=True, text=True, timeout=60)
            return r.returncode, r.stdout, r.stderr

        for named, why in (("deck-human", "is a human login (ADR-044)"), ("nobody", "is not a placed account")):
            rc, out, err = usage(named)
            check(f"{named} named: refused, exit 2, no table", rc == 2 and out == "" and why in err, f"rc={rc}\n{out}{err}")
        rc, out, err = usage()
        rows = out.splitlines()
        check("text: a header and every placement, in the registry's order, exit 0",
              rc == 0 and len(rows) == 5 and rows[0].startswith("account ")
              and [r.split()[0] for r in rows[1:]] == ["ok-one", "down-one", "bare-one", "late-one"],
              f"rc={rc}\n{out}{err}")
        check("…numbers where the read had them, a status where it had none",
              len(rows) == 5 and "45.5%" in rows[1] and "12%" in rows[1]
              and rows[2].split()[1:] == ["-", "executor-failed"]
              and rows[3].split()[1:] == ["-", "no-credentials"] and rows[4].split()[1:] == ["l@x.org", "read-failed"],
              out)
        argvs = []
        if os.path.exists(calls):
            with open(calls, encoding="utf-8") as fh:
                argvs = [json.loads(line) for line in fh]
        check("…each read handed to the executor as the account: `sh -c` and the read itself",
              [a[:4] for a in argvs] == [["h1", "--as", "ok-one", "--"], ["h2", "--as", "down-one", "--"],
                                         ["h1", "--as", "bare-one", "--"], ["h2", "--as", "late-one", "--"]]
              and all(a[4:] == ["sh", "-c", read] for a in argvs), json.dumps(argvs)[:400])

        rc, out, err = usage("--json", "late-one", "ok-one")
        try:
            docs = [json.loads(line) for line in out.splitlines()]
        except ValueError:
            docs = []
        check("--json with logins: those accounts only, in the registry's order, numbers as numbers",
              rc == 0 and [d.get("account") for d in docs] == ["ok-one", "late-one"]
              and docs[0]["five_hour"] == {"utilization": 45.5, "resets_at": "2026-10-06T10:00"}
              and docs[0]["seven_day"]["utilization"] == 12
              and docs[1] == {"account": "late-one", "host": "h2", "status": "read-failed", "email": "l@x.org"},
              f"rc={rc}\n{out}{err}")

        with open(registry, "w", encoding="utf-8") as fh:
            fh.write("{")
        rc, out, err = usage()
        check("a registry it cannot read: exit 2, no table", rc == 2 and out == "" and "host registry" in err,
              f"rc={rc}\n{out}{err}")
        for text in ('{"hosts": {}}', '{"placement": null}', '{"placement": {"a": ["h1"]}}'):
            with open(registry, "w", encoding="utf-8") as fh:
                fh.write(text)
            rc, out, err = usage()
            check(f"a registry with no placement map of login to host ({text}): exit 2, no table",
                  rc == 2 and out == "" and "placement map" in err, f"rc={rc}\n{out}{err}")
        rc, out, err = usage("--bogus")
        check("an unknown option: exit 2, named", rc == 2 and "--bogus" in err, f"rc={rc}\n{err}")
        rc, out, err = usage("--help")
        check("--help: the usage lines only, exit 0",
              rc == 0 and "fabric-usage --json" in out and "OAuth" not in out, f"rc={rc}\n{out}")

    print(f"\ntest_fabric_usage_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
