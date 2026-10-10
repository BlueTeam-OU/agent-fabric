#!/usr/bin/env python3
"""Two facts about the operator's own data, read as it is: the committed
operator keys parse as the daemons read them, and every language-culture
locale other than the default carries its reminder. Both are checked on
purpose against the checkout's live files, so a stripped run
(tests/stripped_run.py) reports this file as red on purpose
(tests/test_tests_read_fixtures.py STRIPPED_RED); the readers' behaviour
is tested on fixtures in tests/test_hosts_registry.py and
tests/test_gzcoord_i18n.py.

Why each is not a lint finding: lint admits an operator_key by its shape
(an ed25519: prefix and 59 base64 characters), which a key publicKeyFrom
refuses can match, and treats a locale's reminder as optional."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))


def test_the_committed_key_parses_as_a_daemon_reads_it() -> None:
    """A key the schema admitted but publicKeyFrom refused would disable
    every action with a refusal that blames the signature, not the registry."""
    from control import agentd  # the daemons' own parser (sign.public_key_from)
    keys = sorted(agentd.operator_keys(os.path.join(ROOT, "runtime", "hosts", "registry.json")))
    with open(os.path.join(ROOT, "runtime", "hosts", "registry.json"), encoding="utf-8") as fh:
        reg = json.load(fh)
    keyed = sorted(f"{h}/{e.get('operator', 'user')}" for h, e in reg["hosts"].items() if e.get("operator_key"))
    assert keyed, "no host carries an operator_key: this case would compare two empty lists and exercise no parser"
    assert keys == keyed, (keys, keyed)


def test_every_language_culture_locale_carries_its_reminder() -> None:
    base = os.path.join(ROOT, "identities", "roles", "language-culture", "locale")
    locales = sorted(d for d in os.listdir(base) if d != "en" and os.path.isdir(os.path.join(base, d)))
    assert locales, "no locale besides the default: this case would check nothing"
    for s in locales:
        with open(os.path.join(base, s, "locale.json"), encoding="utf-8") as fh:
            r = json.load(fh).get("reminder")
        assert isinstance(r, str) and r.startswith(" - ") and any(ord(c) > 0x24F for c in r), (s, r)


def main() -> int:
    fails = 0
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)):
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001 — a failed check is reported, the next runs
            fails += 1
            print(f"  FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
