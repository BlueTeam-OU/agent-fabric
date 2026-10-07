#!/usr/bin/env python3
"""Every program the secret store starts — git, gpg, gpg-connect-agent,
proton-drive — goes through secretstore/core.py's one boundary, so a program
that cannot be started is a StoreError naming the operation, never a
traceback (review of the own-secrets range, F2 and its pre-existing note):
the CLI then answers one line and its exit code. Held two ways: no direct
subprocess call is left in the store's modules but the boundary's own and
lineage.py's (which the lint loads alone and so calls gpg itself), and each
kind of call answers StoreError with nothing on PATH."""
from __future__ import annotations

import ast
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "tools", "fabric", "secretstore")
sys.path.insert(0, os.path.dirname(PKG))
from secretstore import backup, core, lineage  # noqa: E402


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:400]}"))
        fails += not good

    direct = []
    for f in sorted(os.listdir(PKG)):
        if not f.endswith(".py") or f in ("core.py", "lineage.py"):
            continue
        for n in ast.walk(ast.parse(open(os.path.join(PKG, f), encoding="utf-8").read())):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "subprocess" \
                    and n.attr in ("run", "Popen", "call", "check_call", "check_output"):
                direct.append(f"{f}:{n.lineno}")
    check("no store module starts a program but through core._run", not direct, direct)

    def answer(fn) -> str:
        try:
            fn()
        except lineage.StoreError as e:
            return f"StoreError: {e}"
        except Exception as e:  # noqa: BLE001 — what is under test is that nothing else escapes
            return f"{type(e).__name__}: {e}"
        return "no error"

    saved = os.environ.get("PATH")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PATH"] = os.path.join(tmp, "nothing")
        try:
            for label, fn in (("git", lambda: core.git(tmp, "status")),
                              ("gpg", lambda: core.gpg("--list-keys")),
                              ("the recovery key's gpg", lambda: backup._make_recovery_key(tmp, "p" * 12)),
                              ("lineage.py's own gpg", lambda: lineage._gpg(tmp, "--list-keys"))):
                got = answer(fn)
                check(f"{label} not installed: a StoreError naming it", got.startswith("StoreError: ") and "gpg" in got
                      or got.startswith("StoreError: git"), got)
            os.environ["PROTON_DRIVE_BIN"] = os.path.join(tmp, "no-proton-drive")
            got = answer(lambda: backup._proton("filesystem", "info", "/x"))
            check("proton-drive that cannot start: a StoreError naming it", got.startswith("StoreError: proton-drive filesystem info"), got)
        finally:
            os.environ.pop("PROTON_DRIVE_BIN", None)
            if saved is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = saved
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
