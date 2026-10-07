#!/usr/bin/env bash
# tests/static.sh — the static checks every commit passes before a suite
# runs: every bash script parses (`bash -n`), shellcheck finds no error-
# severity finding, ruff finds no undefined or unused name (ruff.toml).
#
# A missing tool is SAID, never silently a pass: CI installs both; a host
# without one sees the line and knows that check did not run here.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
fail=0
skipped=()

# Every bash script: the .sh files and the shebang'd tools without a suffix.
mapfile -t scripts < <({ git ls-files '*.sh'; git ls-files | while read -r f; do
    [[ -f "$f" && "$f" != *.sh ]] && head -c 64 "$f" 2>/dev/null | head -1 | grep -qE '^#!.*\b(ba)?sh\b' && echo "$f"; done; } | sort -u)
echo "static: ${#scripts[@]} bash script(s)"
# One dialect: a #!/bin/sh script would be checked here as bash and run
# by dash on Debian — every script is bash (runtime/provisioning/platform/README.md).
if grep -lE '^#!/bin/sh|^#!/usr/bin/env sh' "${scripts[@]}" 2>/dev/null | grep -v "^$"; then
    echo "  ✗ a #!/bin/sh script: the repository's scripts are bash"; fail=1
fi
for f in "${scripts[@]}"; do
    bash -n "$f" || { echo "  ✗ bash -n $f"; fail=1; }
done
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -S error "${scripts[@]}" || fail=1
else
    echo "  ! shellcheck not installed: not run here (CI runs it)"; skipped+=(shellcheck)
fi
if command -v ruff >/dev/null 2>&1; then
    ruff check . || fail=1
else
    echo "  ! ruff not installed: not run here (CI runs it)"; skipped+=(ruff)
fi
for f in $(git ls-files '*.py'); do
    python3 -m py_compile "$f" || { echo "  ✗ py_compile $f"; fail=1; }
done
# GitHub's host keys are the committed published set, and provisioning
# never scans for them: the fingerprints beside the file are what a
# reviewer checks against docs.github.com, so the two must agree.
if command -v ssh-keygen >/dev/null 2>&1; then
    want="$(sort runtime/provisioning/github-host-keys.fingerprints)"
    have="$(ssh-keygen -lf runtime/provisioning/github-host-keys | awk '{print $2, $4}' | tr -d '()' | sort)"
    [[ "$want" == "$have" ]] || { echo "  ✗ runtime/provisioning/github-host-keys does not match github-host-keys.fingerprints"; fail=1; }
else
    echo "  ! ssh-keygen not installed: host-key fingerprints not checked here (CI checks them)"
fi
if grep -rn "ssh-keyscan" runtime/provisioning --include='*.sh' | grep -v "test_\|never\|# "; then
    echo "  ✗ ssh-keyscan in provisioning: host keys come from the committed published set"; fail=1
fi
# A node suite's temporary directory is made through tests/scratch.mjs,
# which removes it when the process ends; the inline form was forgotten
# seventy times per run (tests/scratch.mjs has the measurement).
if git ls-files '*.test.mjs' | xargs grep -n "mkdtempSync" 2>/dev/null; then
    echo "  ✗ mkdtempSync in a node suite: use scratch() from tests/scratch.mjs"; fail=1
fi
# A file URL's .pathname is percent-encoded, so handing it to the
# filesystem names a file that does not exist as soon as the checkout
# path contains a space. fileURLToPath is the converter. The rule lived
# only in the modules already fixed: at the branch point the idiom stood
# in twenty places across five suites and one module. The FIRST guard
# written here matched the inline spelling only — not the
# `const f = new URL(..., import.meta.url); … f.pathname` form, which is
# the one that had actually shipped — so it would have guarded nothing
# the fix had just removed. Hence a binding pass rather than a grep.
python3 - <<'PY' || fail=1
import re, subprocess, sys
files = subprocess.run(["git", "ls-files", "*.mjs"], capture_output=True, text=True).stdout.split()
bound = re.compile(r"\b(?:const|let|var)\s+(\w+)\s*=\s*new URL\([^;]*?import\.meta\.url\s*\)")
inline = re.compile(r"import\.meta\.url\s*\)\s*\.pathname")
bad = []
for f in files:
    src = open(f, encoding="utf-8").read()
    names = sorted(set(bound.findall(src)))
    named = re.compile(r"\b(?:%s)\.pathname" % "|".join(map(re.escape, names))) if names else None
    for n, line in enumerate(src.split("\n"), 1):
        if line.lstrip().startswith("//"):
            continue            # a comment may name the idiom to forbid it
        if inline.search(line) or (named and named.search(line)):
            bad.append("  %s:%d: %s" % (f, n, line.strip()))
print("\n".join(bad))
if bad:
    print("  \u2717 a module URL reaching the filesystem as .pathname: use fileURLToPath(new URL(...))")
sys.exit(1 if bad else 0)
PY
if (( fail )); then echo "static: FAILED"; exit 1; fi
# The summary names what did not run: a reader of the last line took a
# skipped ruff for a clean one and delivered two unused imports to CI.
if (( ${#skipped[@]} )); then
    echo "static: passed, but NOT run here: ${skipped[*]} (CI runs it)"
else
    echo "static: all bash scripts parse, shellcheck and ruff clean"
fi
