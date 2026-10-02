#!/usr/bin/env python3
"""bin/fabric-usage's sudo fallback: the per-account read, run against a
scratch home. A login on a Claude-account template is `setup-token` (its
own sign-in is another account's; the template cannot read usage), and
neither token is ever printed. Ported from tests/test_fabric-usage.sh
(ADR-040 Wave 6), case for case. Plain script: prints ok/FAIL, exit 1 on
any failure."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "bin", "fabric-usage")


def read_heredoc(path: str) -> str:
    """The READ heredoc, exactly as bin/fabric-usage hands it to the executor."""
    body, inside = [], False
    with open(path, encoding="utf-8") as fh:
        for line in fh.read().split("\n"):
            if not inside:
                inside = line.startswith("read -r -d '' READ <<'EOF'")
            elif line == "EOF":
                break
            else:
                body.append(line)
    return "\n".join(body)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    read = read_heredoc(TOOL)
    check("the per-account read is found in bin/fabric-usage", bool(read))

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
        put(os.path.join(sandbox, "bin", "curl"), f'#!/bin/sh\ntouch "{curl_ran}"\nexit 7\n')
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

    print(f"\ntest_fabric_usage_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
