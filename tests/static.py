#!/usr/bin/env python3
"""tests/static.py — the static checks every commit passes before a suite runs: every bash script parses (`bash -n`),
shellcheck finds no error-severity finding, ruff finds no undefined or unused name (ruff.toml), every Python file
compiles. The port of tests/static.sh; its output is the contract tests/run.py's `static` section and CI print.

A missing tool is SAID, never silently a pass: CI installs shellcheck and ruff; a host without one sees the line and
knows that check did not run here. The last line says so too — a reader of it took a skipped ruff for a clean one and
delivered two unused imports to CI.

  stdout/stderr  the findings, one `  ✗ <what>` line each, and the tools' own output. Two details of static.sh are not kept,
                 on purpose: the blank line its .pathname check printed on a clean tree, and Python's compile error on
                 stderr before `✗ py_compile <file>` (here the error follows it, on stdout).
  exit           0 every check passed or was said not to run; 1 a check failed
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# A tool that hangs must not hang the run: none of these takes minutes on this tree.
TOOL_TIMEOUT_S = 600
BASH_SHEBANG = re.compile(rb"^#!.*\b(ba)?sh\b")
SH_DIALECT = re.compile(r"^#!/bin/sh|^#!/usr/bin/env sh", re.MULTILINE)
# A file URL's .pathname is percent-encoded, so handing it to the filesystem names a file that does not exist as soon as
# the checkout path contains a space. fileURLToPath is the converter. The first guard written for this matched the
# inline spelling only — not the `const f = new URL(..., import.meta.url); … f.pathname` form, which is the one that
# had actually shipped — so it would have guarded nothing the fix had just removed. Hence a binding pass, not a grep.
URL_BOUND = re.compile(r"\b(?:const|let|var)\s+(\w+)\s*=\s*new URL\([^;]*?import\.meta\.url\s*\)")
URL_INLINE = re.compile(r"import\.meta\.url\s*\)\s*\.pathname")


def tracked(*patterns: str) -> list[str]:
    """git's tracked paths, matching the pathspecs; NUL-separated, so no name is split or unquoted."""
    p = subprocess.run(["git", "ls-files", "-z", *patterns], cwd=ROOT, capture_output=True, timeout=TOOL_TIMEOUT_S, check=True)
    return [f for f in p.stdout.decode("utf-8", "surrogateescape").split("\0") if f]


def bash_scripts() -> list[str]:
    """The .sh files and the shebang'd tools without a suffix, sorted and unique."""
    found = set(tracked("*.sh"))
    for f in tracked():
        path = os.path.join(ROOT, f)
        if f.endswith(".sh") or not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as fh:
                first = fh.read(64).split(b"\n", 1)[0]
        except OSError:
            continue
        if BASH_SHEBANG.match(first):
            found.add(f)
    return sorted(found)


def tool(argv: list[str]) -> int:
    """A tool's status; one that cannot run or does not finish is a failure said by name, never a pass."""
    try:
        return subprocess.run(argv, cwd=ROOT, stdin=subprocess.DEVNULL, timeout=TOOL_TIMEOUT_S,
                              check=False).returncode
    except subprocess.TimeoutExpired:
        print(f"  ✗ {argv[0]} did not finish within {TOOL_TIMEOUT_S} s")
    except OSError as e:
        print(f"  ✗ {argv[0]} could not run: {e}")
    return 1


def read_text(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8", errors="surrogateescape") as fh:
        return fh.read()


def check_dialect(scripts: list[str]) -> bool:
    """One dialect: a #!/bin/sh script would be checked as bash and run by dash on Debian — every script is bash
    (runtime/provisioning/platform/README.md). Matches the shebang at the start of ANY line, as grep -lE did."""
    wrong = []
    for f in scripts:
        try:
            if SH_DIALECT.search(read_text(f)):
                wrong.append(f)
        except OSError:
            continue
    for f in wrong:
        print(f)
    if wrong:
        print("  ✗ a #!/bin/sh script: the repository's scripts are bash")
    return not wrong


def check_python_compiles() -> bool:
    """compile(), not py_compile: the same syntax check without writing a __pycache__ into the tree (ADR-021)."""
    ok = True
    for f in tracked("*.py"):
        try:
            compile(read_text(f), f, "exec")
        except (SyntaxError, ValueError, OSError) as e:
            print(f"  ✗ py_compile {f}\n{e}")
            ok = False
    return ok


def check_host_keys() -> bool:
    """GitHub's host keys are the committed published set, and provisioning never scans for them: the fingerprints
    beside the file are what a reviewer checks against docs.github.com, so the two must agree."""
    if shutil.which("ssh-keygen") is None:
        print("  ! ssh-keygen not installed: host-key fingerprints not checked here (CI checks them)")
        return True
    want = sorted(read_text("runtime/provisioning/github-host-keys.fingerprints").splitlines())
    p = subprocess.run(["ssh-keygen", "-lf", os.path.join(ROOT, "runtime/provisioning/github-host-keys")],
                       capture_output=True, text=True, timeout=TOOL_TIMEOUT_S, check=False)
    have = []
    for line in p.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 4:
            have.append(f"{fields[1]} {fields[3]}".replace("(", "").replace(")", ""))
    if want != sorted(have):
        print("  ✗ runtime/provisioning/github-host-keys does not match github-host-keys.fingerprints")
        return False
    return True


def check_no_keyscan() -> bool:
    """Host keys come from the committed published set; a scan in provisioning is the thing that rule forbids. A test
    file, a line saying `never`, and a comment may name it."""
    hits = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, "runtime/provisioning")):
        for name in sorted(files):
            if not name.endswith(".sh"):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, ROOT)
            try:
                lines = read_text(rel).splitlines()
            except OSError:
                continue
            for n, text in enumerate(lines, 1):
                shown = f"{rel}:{n}:{text}"
                if "ssh-keyscan" in text and not any(w in shown for w in ("test_", "never", "# ")):
                    hits.append(shown)
    for h in sorted(hits):
        print(h)
    if hits:
        print("  ✗ ssh-keyscan in provisioning: host keys come from the committed published set")
    return not hits


def check_module_urls() -> bool:
    bad = []
    for f in tracked("*.mjs"):
        src = read_text(f)
        names = sorted(set(URL_BOUND.findall(src)))
        named = re.compile(rf"\b(?:{'|'.join(map(re.escape, names))})\.pathname") if names else None
        for n, line in enumerate(src.split("\n"), 1):
            if line.lstrip().startswith("//"):
                continue            # a comment may name the idiom to forbid it
            if URL_INLINE.search(line) or (named and named.search(line)):
                bad.append(f"  {f}:{n}: {line.strip()}")
    if bad:
        print("\n".join(bad))
        print("  ✗ a module URL reaching the filesystem as .pathname: use fileURLToPath(new URL(...))")
    return not bad


def main() -> int:
    os.chdir(ROOT)
    ok = True
    skipped: list[str] = []
    scripts = bash_scripts()
    print(f"static: {len(scripts)} bash script(s)")
    ok &= check_dialect(scripts)
    for f in scripts:
        if tool(["bash", "-n", f]) != 0:
            print(f"  ✗ bash -n {f}")
            ok = False
    if shutil.which("shellcheck"):
        ok &= tool(["shellcheck", "-S", "error", *scripts]) == 0
    else:
        print("  ! shellcheck not installed: not run here (CI runs it)")
        skipped.append("shellcheck")
    if shutil.which("ruff"):
        ok &= tool(["ruff", "check", "."]) == 0
    else:
        print("  ! ruff not installed: not run here (CI runs it)")
        skipped.append("ruff")
    ok &= check_python_compiles()
    ok &= check_host_keys()
    ok &= check_no_keyscan()
    ok &= check_module_urls()
    if not ok:
        print("static: FAILED")
        return 1
    if skipped:
        print(f"static: passed, but NOT run here: {' '.join(skipped)} (CI runs it)")
    else:
        print("static: all bash scripts parse, shellcheck and ruff clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
