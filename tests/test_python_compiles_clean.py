#!/usr/bin/env python3
r"""Every tracked Python source compiles with SyntaxWarning turned into an error (an invalid escape such as "\ " in a
docstring is a warning today and a SyntaxError in a later Python; the owner saw it on 2026-11-12). The corpus is this
checkout's own `git ls-files` — .py files and the extensionless scripts whose shebang names python — never the live
instance tree. Each hit is reported as path:line. Plain script: ok/FAIL, exit 1."""
from __future__ import annotations

import os
import subprocess
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = 0


def check(name: str, ok: bool, detail: object = "") -> None:
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f": {detail}"))
    fails += 0 if ok else 1


def is_python(path: str) -> bool:
    if path.endswith(".py"):
        return True
    if os.path.splitext(path)[1] or os.path.islink(path):
        return False
    try:
        with open(os.path.join(ROOT, path), "rb") as fh:
            first = fh.readline(256)
    except OSError:
        return False
    return first.startswith(b"#!") and b"python" in first


def hit(source: bytes, name: str) -> str | None:
    """path:line: why, or None when the source compiles without a warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        try:
            compile(source, name, "exec", dont_inherit=True)
        except SyntaxError as e:
            return f"{name}:{e.lineno}: {e.msg}"
    return None


def main() -> int:
    tracked = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], capture_output=True, timeout=60, check=True,
                             env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")}).stdout.decode().split("\0")
    sources = sorted(p for p in tracked if p and is_python(p))
    check("the corpus was found (the control for 'none failed')", len(sources) > 100, len(sources))
    check("extensionless python scripts are in the corpus", any("." not in os.path.basename(p) for p in sources))

    # The positive control: the detector must fail on the very thing it is for, and pass on its repair.
    h = hit(b'"""a\n\\ b"""\n', "x.py")
    check("an invalid escape in a docstring is a hit, naming file and line",
          h is not None and h.startswith("x.py:2: ") and "invalid escape sequence" in h, h)
    check("the raw string of the same text is clean", hit(b'r"""a\n\\ b"""\n', "x.py") is None)

    bad = []
    for p in sources:
        with open(os.path.join(ROOT, p), "rb") as fh:
            h = hit(fh.read(), p)
        if h:
            bad.append(h)
    check(f"{len(sources)} tracked Python sources compile with SyntaxWarning as an error", not bad, "\n  " + "\n  ".join(bad))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
