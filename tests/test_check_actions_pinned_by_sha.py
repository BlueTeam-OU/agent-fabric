#!/usr/bin/env python3
"""Tests for policies/check_actions_pinned_by_sha.py, through the real script
on a planted .github/: the same nineteen cases as devex-tooling's shell
suite it replaces, and the shapes its review found missing."""
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


def run(files: dict[str, str] | None, argv: list[str] | None = None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as root:
        for rel, body in (files or {}).items():
            p = os.path.join(root, ".github", rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="utf-8").write(body)
        # REPO_ROOT names the planted tree unless the case passes its own argv.
        env = {**os.environ, "REPO_ROOT": root} if argv is None else \
            {k: v for k, v in os.environ.items() if k != "REPO_ROOT"}
        args = [a.replace("{root}", root) for a in (argv or [])]
        r = subprocess.run([sys.executable, TOOL, *args], env=env, capture_output=True, text=True)
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
    # Shapes GitHub reads that an anchored pattern missed (devex-tooling's
    # review of the shell guard this ports).
    (1, "a tag pin under a quoted key is read and rejected", step('      - "uses": actions/checkout@v7'), None),
    (1, "a tag pin with a space before the colon is read and rejected", step("      - uses : actions/checkout@v7"), None),
    (1, "a tag pin in a flow mapping is read and rejected", step("      - {uses: actions/checkout@v7}"), None),
    (1, "a tag pin that is not the flow mapping's first key is read and rejected", step("      - {name: co, uses: actions/checkout@v7}"), None),
    (0, "a SHA pin in a flow mapping, with its version, passes", step(f"      - {{name: co, uses: actions/checkout@{SHA}}} # v7.0.1"), None),
    (1, "a docker digest that is not 64 hex characters is rejected", step(f"      - uses: docker://docker.io/library/alpine@sha256:{'a' * 63}"), None),
    # A value on the key's next line is a plain scalar GitHub reads (review of #68).
    (1, "a tag pin on the line after its uses: key is read and rejected", step("      - uses:\n          actions/checkout@v7"), None),
    (0, "a SHA pin on the line after its uses: key, with its version, passes", step(f"      - uses:\n          actions/checkout@{SHA} # v7.0.1"), None),
    (1, "a uses: key with nothing after it at all is rejected", step("      - uses:\n"), None),
    (0, "a comment line between the key and its value is skipped, and the SHA pin passes",
     step(f"      - uses:\n          # the checkout\n          actions/checkout@{SHA} # v7.0.1"), None),
    (1, "an empty key followed by a sibling key has no value, never the sibling",
     step("      - uses:\n        with:\n          fetch-depth: 0"), None),
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
    # The sibling key is never read as the value: the finding is about
    # the empty key, "(nothing)", not a ref called `with:` (review of #70).
    got, out = run({"workflows/ci.yml": step("      - uses:\n        with:\n          fetch-depth: 0")})
    ok = "'(nothing)'" in out and "'with:'" not in out
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} an empty list-item key reads (nothing), never its sibling" + ("" if ok else f"\n        {out[-300:]}"))
    # Both project copies refuse two uses sharing one comment (devex-tooling,
    # seq 16442): each pin here is well formed, so only that rule refuses.
    two = step(f"      - {{name: a, uses: actions/checkout@{SHA}}} # v7.0.1\n"
               f"      - {{uses: a/b@{SHA}, x: {{uses: c/d@{SHA}}}}} # v1.0.0")
    got, out = run({"workflows/ci.yml": two})
    ok = got == 1 and "2 third-party uses on one line share one version comment" in out
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} two uses on one line: refused, named" + ("" if ok else f"\n        {out[-300:]}"))
    digests = step(f"      - {{uses: docker://a@sha256:{DIGEST}}}\n"
                   f"      - [{{uses: docker://a@sha256:{DIGEST}}}, {{uses: docker://b@sha256:{DIGEST}}}]")
    got, out = run({"workflows/ci.yml": digests})
    ok = got == 0
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} two docker digests on one line pass: a digest needs no version comment"
          + ("" if ok else f"\n        {out[-300:]}"))
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, ".github", "workflows"))
        open(os.path.join(root, ".github", "workflows", "ci.yml"), "wb").write(b"jobs:\n  a: \xff\xfe\n")
        r = subprocess.run([sys.executable, TOOL, "--root", root], capture_output=True, text=True)
    ok = r.returncode == 2 and "could not be read: .github/workflows/ci.yml (UnicodeDecodeError)" in r.stderr
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} a workflow that is not UTF-8: exit 2, not checked, never a finding"
          + ("" if ok else f"\n        rc={r.returncode} {r.stderr[-200:]}"))
    good = {"workflows/ci.yml": step(f"      - uses: actions/checkout@{SHA} # v7.0.1")}
    for want, label, argv, needle in [
        (0, "--root <dir> names the tree", ["--root", "{root}"], "OK"),
        (0, "--root=<dir> too", ["--root={root}"], "OK"),
        (2, "--root without a value", ["--root"], "--root needs a value"),
        (2, "any other argument", ["--nope"], "unexpected argument: --nope"),
        (0, "--help prints the usage", ["--help"], "[--root <dir>]"),
    ]:
        got, out = run(good, argv)
        ok = got == want and needle in out
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {label} (exit {got})" + ("" if ok else f"\n        {out[-300:]}"))
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
