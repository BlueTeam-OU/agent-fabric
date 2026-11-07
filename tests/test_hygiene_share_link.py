#!/usr/bin/env python3
"""policies/hygiene.json: a claude.ai artifact, share, chat, project or session link never reaches a slice, skill or prompt
section. It is one account's and private by default, so every other reader of a slice finds a dead link; the gzapi.ge #27
review found one in a drained slice that no pattern caught (j554). A ~/ path is not refused: it reads the same on every
account, and the /home/<login>/ and ~/scratch/ patterns already take the paths that name one account.
Plain script: prints ok/FAIL, exit 1 on any failure.
Kills: dropping the pattern; one that matches the gallery or claude.ai alone; one that keeps the scheme or eats the
sentence's period in the drain's substitution; one that reads a host that only ends in claude.ai; a lost case-insensitivity."""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

LEAKS = [
    "explored in Claude Design: https://claude.ai/artifact/4vFfDYtCHgcsYLTiEmBJgM).", "claude.ai/share/0b1c2d3e-aaaa-bbbb",
    "https://claude.ai/code/artifact/5f0e3c2a-1111-2222-3333-444455556666", "http://claude.ai/chat/abc-123",
    "https://claude.ai/public/artifacts/abc-123", "https://claude.ai/project/0193-abc", "(https://claude.ai/code/session_01AbCdEf)",
    # A host and a scheme are case-insensitive, and prose capitalises the product (#497 round 7 F11).
    "Claude.ai/share/abc-1", "HTTPS://claude.ai/chat/x", "https://CLAUDE.AI/artifact/abc",
]
FINE = [
    "the gallery at claude.ai/code/artifacts lists them", "https://claude.ai/", "log in at claude.ai", "claude.ai/artifact alone",
    "https://notclaude.ai/artifact/abc", "https://docs.claude.ai/artifact/abc", "https://Docs.Claude.ai/share/abc", "~/.local/bin and ~/projects/agent-fabric",
]
# The drain substitutes refer_as for the whole link, scheme included; the sentence around it survives.
SUBSTITUTED = {
    "three explored in https://claude.ai/artifact/4vFfDYtCHgcsYLTiEmBJgM). Content": "three explored in a claude.ai link). Content",
    "see claude.ai/share/abc-123. Then": "see a claude.ai link. Then",
}


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    from fabric.assembler.core import hygiene_substitute

    with open(os.path.join(ROOT, "policies", "hygiene.json"), encoding="utf-8") as fh:
        entries = json.load(fh)["patterns"]
    share = [(re.compile(e["pattern"], re.I if e.get("flags") == "i" else 0), e["label"], e.get("refer_as"))
             for e in entries if e["label"].startswith("a claude.ai ")]
    check("one pattern, with a label and a refer_as", len(share) == 1 and all(t[1] and t[2] for t in share))
    for text in LEAKS:
        check(f"matched: {text!r}", any(t[0].search(text) for t in share))
    for text in FINE:
        check(f"not matched: {text!r}", not any(t[0].search(text) for t in share))
    for text, want in SUBSTITUTED.items():
        got, _ = hygiene_substitute(text, "test", share)
        check(f"{text!r} reads {want!r}", got == want)
    print("test_hygiene_share_link:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
