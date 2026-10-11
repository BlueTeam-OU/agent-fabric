#!/usr/bin/env python3
"""A gh for the secrets-sync tests (AGENT_FABRIC_GH): it keeps one token in the
sandbox HOME and never reaches the network or a keyring. A real gh in a test
once read the runner's keyring and tried a login with a fixture token
(2026-10-06).

  gh auth token        prints the stored token and exits 0; exit 1 when there is none
  gh auth login …      stores stdin as the token and exits 0; with FAKE_GH_LOGIN_EXIT
                       set and not 0, it reads stdin, stores nothing and exits with it,
                       as a refused login does
  anything else        "fake gh: unsupported: <args>" on stderr, exit 2
The token file is $GH_CONFIG_DIR/fake-token, else $HOME/.config/gh/fake-token.
"""
import os
import sys


def main(argv: list[str]) -> int:
    base = os.environ.get("GH_CONFIG_DIR") or os.path.join(os.environ.get("HOME", ""), ".config", "gh")
    token = os.path.join(base, "fake-token")
    pair = argv[1:3]
    if pair == ["auth", "token"]:
        try:
            if os.path.getsize(token) > 0:
                with open(token, "rb") as fh:
                    sys.stdout.buffer.write(fh.read())
                return 0
        except OSError:
            pass
        return 1
    if pair == ["auth", "login"]:
        data = sys.stdin.buffer.read()
        refused = os.environ.get("FAKE_GH_LOGIN_EXIT") or "0"
        if refused != "0":
            return int(refused) if refused.lstrip("-").isdigit() else 2   # bash: `exit abc` is 2
        os.makedirs(base, exist_ok=True)
        with open(token, "wb") as fh:
            fh.write(data)
        return 0
    sys.stderr.write(f"fake gh: unsupported: {' '.join(argv[1:])}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
