#!/usr/bin/env python3
"""Tests for policies/check_actions_pinned_by_sha.py, through the real script
on a planted .github/: the same nineteen cases as devex-tooling's shell
suite it replaces."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "policies", "check_actions_pinned_by_sha.py")
SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
DIGEST = "a" * 64


def step(lines: str) -> str:
    return f"jobs:\n  a:\n    steps:\n{lines}\n"


def run(files: dict[str, str] | None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as root:
        for rel, body in (files or {}).items():
            p = os.path.join(root, ".github", rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="utf-8").write(body)
        r = subprocess.run([sys.executable, TOOL], env={**os.environ, "REPO_ROOT": root}, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


CASES = [
    (0, "a SHA with its version comment passes (list-item form)", step(f"      - uses: actions/checkout@{SHA} # v7.0.1"), None),
    (0, "a SHA with its version comment passes (key form)", step(f"      - if: true\n        uses: actions/checkout@{SHA} # v7.0.1"), None),
    (0, "a sub-path action pinned by SHA passes", step(f"      - uses: github/codeql-action/init@{SHA} # v4.38.2"), None),
    (0, "a quoted SHA pin passes", step(f"      - uses: 'actions/checkout@{SHA}' # v7.0.1"), None),
    (1, "a major tag is rejected", step("      - uses: actions/checkout@v7"), None),
    (1, "an exact release tag is rejected", step("      - uses: github/codeql-action/init@v4.38.2"), None),
    (1, "a branch is rejected", step("      - uses: some/action@main"), None),
    (1, "a short SHA is rejected", step("      - uses: actions/checkout@3d3c42e # v7.0.1"), None),
    (1, "an upper-case SHA is rejected (GitHub's refs are lower-case)", step(f"      - uses: actions/checkout@{SHA.upper()} # v7.0.1"), None),
    (1, "no ref at all is rejected", step("      - uses: actions/checkout"), None),
    (1, "a SHA with no version comment is rejected", step(f"      - uses: actions/checkout@{SHA}"), None),
    (1, "a SHA whose comment is not a version is rejected", step(f"      - uses: actions/checkout@{SHA} # pinned"), None),
    (0, "a local action and a local reusable workflow are exempt",
     "jobs:\n  a:\n    uses: ./.github/workflows/_web.yml\n  b:\n    steps:\n      - uses: ./.github/actions/setup\n", None),
    (0, "a docker action pinned by digest passes", step(f"      - uses: docker://docker.io/library/alpine@sha256:{DIGEST}"), None),
    (1, "a docker action by tag is rejected", step("      - uses: docker://docker.io/library/alpine:3.20"), None),
    (0, "a commented-out tag pin is not a use", step(f"      # - uses: actions/checkout@v4\n      - uses: actions/checkout@{SHA} # v7.0.1"), None),
    (1, "a composite action under .github/actions is checked too",
     "runs:\n  using: composite\n  steps:\n    - uses: actions/setup-node@v7\n", "actions/setup/action.yml"),
    (1, "one bad use among good ones fails the file", step(f"      - uses: actions/checkout@{SHA} # v7.0.1\n      - uses: actions/setup-node@v7"), None),
]


def main() -> int:
    fails = 0
    for want, name, body, path in CASES:
        files = {path or "workflows/ci.yml": body}
        if path:
            files["workflows/ci.yml"] = step(f"      - uses: actions/checkout@{SHA} # v7.0.1")
        got, out = run(files)
        ok = got == want
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name} (exit {got})" + ("" if ok else f"\n        {out[-300:]}"))
    got, out = run(None)
    ok = got == 2
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} no workflow directory is exit 2 (exit {got})")
    got, out = run({"workflows/ci.yml": step("      - uses: actions/checkout@v7")})
    ok = "FAIL: .github/workflows/ci.yml:4 'actions/checkout@v7' is pinned to 'v7'" in out
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} a finding names the file, the line and why" + ("" if ok else f"\n        {out[-300:]}"))
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
