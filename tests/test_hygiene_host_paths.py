#!/usr/bin/env python3
"""policies/hygiene.json: a recorded host artifact path, under /var/tmp/ or one account's ~/scratch/, never reaches a
slice, skill or prompt section, while a path with a placeholder in it (a convention, /var/tmp/agent-fabric-<login>,
~/scratch/<job>/) and /var/tmp named alone do. The InterWeave drain of 2026-10-18 carried nine such paths, most of them
already gone in a wipe of the volume (review of InterWeave #302). Plain script: prints ok/FAIL, exit 1 on any failure.
Kills: dropping either pattern; a pattern without the placeholder lookahead; one that matches /var/tmp alone."""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

LEAKS = [
    "The APK is at `/var/tmp/j94-292/j94-292-0057924e.apk`, sha256 91819bbe.",
    "evidence in /var/tmp/j88-swipe-review (README.txt)", "keep /var/tmp/agent-fabric-python-dev-02/cienv.sh", "/var/tmp/agent-fabric-user/.cache/x",
    "a backup at /var/tmp/w.bak, then", "heads under /var/tmp/review-*",
    "rebuilt into ~/scratch/j97 for later", "(~/scratch/look-compare/both.png, and", "~/scratch/j97/*.orig",
]
FINE = [
    "Not /var/tmp, where that decision put it.", "the old /var/tmp/agent-fabric-<login> filled it",
    "keep artifacts in ~/scratch/<job>/ so they survive",
    # A login's TMPDIR root named whole is the account, not an artifact; a file under it is one (herdr, 2026-10-19).
    "sweeping /var/tmp/agent-fabric-rust-ui-dev-02 test leftovers", "TMPDIR is /var/tmp/agent-fabric-user.", "/var/tmp/agent-fabric-user/ is the TMPDIR",
    "TMPDIR is /var/tmp/agent-fabric-user/.", "it was /var/tmp/agent-fabric-user...", "/var/tmp alone, and /var/tmpfs/x", "~/scratchpad/x and ~/scratch",
]
# The path ends before a sentence's period or colon: what the slice says stays one sentence (review of #310, round 3).
REFER_AS = {"/var/tmp/x.apk was": "a host scratch path was", "~/scratch/j97 was": "a scratch path was",
            "in /var/tmp/j9/out. Next": "in a host scratch path. Next", "at ~/scratch/x: then": "at a scratch path: then",
            "(/var/tmp/review-*)": "(a host scratch path)", "at /var/tmp/j9/out: then": "at a host scratch path: then"}


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    with open(os.path.join(ROOT, "policies", "hygiene.json"), encoding="utf-8") as fh:
        entries = json.load(fh)["patterns"]
    host = [(re.compile(e["pattern"]), e["label"], e.get("refer_as")) for e in entries
            if e["label"].startswith(("host scratch path", "one account's scratch path"))]
    check("two patterns, each with a label and a refer_as", len(host) == 2 and all(t[1] and t[2] for t in host))
    for text in LEAKS:
        check(f"matched: {text!r}", any(t[0].search(text) for t in host))
    for text in FINE:
        check(f"not matched: {text!r}", not any(t[0].search(text) for t in host))
    for text, want in REFER_AS.items():
        got = text
        for pat, _label, refer in host:
            got = pat.sub(refer, got)
        check(f"{text!r} reads {want!r}", got == want)
    print("test_hygiene_host_paths:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
