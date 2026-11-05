#!/usr/bin/env python3
"""policies/hygiene.json: the CEO's name never reaches a slice, skill or prompt section in any case, and neither does a
handle or account name built from it (a GitHub login, a Claude account, a key's variable). Codex found the joined
lowercase handle in a drained slice on the j553 live check, past a pattern that matched only the capitalised name with
word boundaries (j610). Plain script: prints ok/FAIL, exit 1 on any failure. Kills: dropping the case flag; a \\b that
an underscore defeats; a tail with no separator left unmatched; the name pattern running first and leaving an account's tail behind; a pattern loose enough to
eat a longer word."""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SUBSTITUTED = [
    ("export POSTERS='[\"andreabenetton\"]'", "export POSTERS='[\"the CEO's account\"]'"),
    ("running on andrea-benetton-blueteam-ge a day", "running on the CEO's account a day"),
    ("(claude-pzhuy-8alias-com or andrea-benetton).", "(claude-pzhuy-8alias-com or the CEO's account)."),
    ("key CLAUDE_APIKEY_ANDREA_BENETTON_BLUETEAM_GE here", "key CLAUDE_APIKEY_the CEO's account here"),
    ("asked Andrea Benetton twice", "asked the CEO twice"),
    ("asked andrea twice", "asked the CEO twice"),
    ("signed by Benetton", "signed by the CEO"),
    # A suffix with no separator is an ordinary login or account form (review F1, #488 round 1).
    ("login andreabenetton01 here", "login the CEO's account here"),
    ("gh:AndreaBenetton2 x", "gh:the CEO's account x"),
    ("as Andrea Benetton01 wrote", "as the CEO wrote"),
    ("user andrea1 and benetton7", "user the CEO and the CEO"),
]
FINE = ["Andreas and Benettonia stay", "sandrea and andreab and xbenetton", "a CEO-owned account"]


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    with open(os.path.join(ROOT, "policies", "hygiene.json"), encoding="utf-8") as fh:
        entries = json.load(fh)["patterns"]
    # In file order, as the assembler applies them: the account pattern must
    # run before the bare name, or the name eats "andrea" and leaves the tail.
    named = [(re.compile(e["pattern"], re.I if "i" in (e.get("flags") or "") else 0), e["refer_as"]) for e in entries
             if e["label"].startswith(("person's name", "an account or handle built from a person's name"))]
    check("two patterns, each with a refer_as", len(named) == 2 and all(r for _p, r in named))

    def substitute(text: str) -> str:
        for pattern, refer_as in named:
            text = pattern.sub(refer_as, text)
        return text

    for text, want in SUBSTITUTED:
        got = substitute(text)
        check(f"{text!r} -> {got!r}", got == want)
    for text in FINE:
        check(f"not matched: {text!r}", not any(p.search(text) for p, _r in named))
    print("test_hygiene_person_name:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
