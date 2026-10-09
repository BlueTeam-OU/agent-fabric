#!/usr/bin/env python3
"""tools/fabric/github/common.py: how a body is read from stdin and where a
project's own tool config is found. The tools' CLI suites cover both through
the tools; these cases pin the helpers' own edges."""
from __future__ import annotations

import io
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import common, local  # noqa: E402
import roots  # noqa: E402
import workingcopy  # noqa: E402


class FakeStdin:
    def __init__(self, data: bytes, tty: bool = False):
        self.buffer = io.BytesIO(data)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    print("read_body")
    real_stdin = sys.stdin
    try:
        sys.stdin = FakeStdin("a\nb\n\n".encode())
        check("bytes decoded, a trailing blank line kept", common.read_body() == "a\nb\n\n")
        sys.stdin = FakeStdin(b"bad \xff byte")
        check("invalid UTF-8 becomes U+FFFD, never a lone surrogate", common.read_body() == "bad � byte")
        sys.stdin = FakeStdin(b"text", tty=True)
        check("a terminal is no body: None, and nothing read", common.read_body() is None)
        sys.stdin = FakeStdin(b"")
        check("an empty pipe is an empty body, not None", common.read_body() == "")
    finally:
        sys.stdin = real_stdin

    print("project_config_path")
    saved = {k: os.environ.pop(k, None) for k in ("T_CFG",)}
    real = (local.toplevel, workingcopy.resolve, roots.project_integration)
    try:
        os.environ["T_CFG"] = "/explicit/x.json"
        local.toplevel = lambda: None
        check("the variable wins, even outside a working copy", common.project_config_path("T_CFG", "x.json") == "/explicit/x.json")
        del os.environ["T_CFG"]
        check("outside a working copy, no variable: empty", common.project_config_path("T_CFG", "x.json") == "")
        local.toplevel = lambda: "/wc"
        workingcopy.resolve = lambda top: {"project": "pid"}
        roots.project_integration = lambda pid, *parts: "/".join(("/proj", pid, *parts))
        check("a registered project: its integration/gh file, whether or not it exists",
              common.project_config_path("T_CFG", "x.json") == "/proj/pid/gh/x.json")
        workingcopy.resolve = lambda top: {}
        check("a working copy with no project: empty", common.project_config_path("T_CFG", "x.json") == "")

        def exits(top):
            raise SystemExit(2)
        workingcopy.resolve = exits
        check("a marker naming nothing the registry knows exits: empty, not an exit", common.project_config_path("T_CFG", "x.json") == "")
        os.environ["T_CFG"] = ""
        check("an empty variable is unset", common.project_config_path("T_CFG", "x.json") == "")
    finally:
        local.toplevel, workingcopy.resolve, roots.project_integration = real
        os.environ.pop("T_CFG", None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v

    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
