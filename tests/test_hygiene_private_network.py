#!/usr/bin/env python3
"""policies/hygiene.json: a private-network IPv4 address (10/8, 192.168/16, 172.16/12, also with a placeholder last octet
such as 192.168.100.x) and a /home/<login>/ path never reach a slice, skill or prompt section, and a version or any other
dotted number does. Plain script: prints ok/FAIL, exit 1 on any failure. Kills: dropping a range; a pattern loose enough to
match a four-part version; a lookbehind that lets a longer dotted number through."""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

LEAKS = [
    "Reach it at 10.137.0.2 over the bridge.", "10.0.0.1", "(10.255.255.255)", "The LAN is 192.168.100.x here.",
    "Run 192.168.1.10.", "192.168.0.0 and", "Host 172.16.4.9 and 172.31.255.1.", "172.20.0.5,",
    "It lives in /home/alice/projects/x.", "cd /home/python-dev-03/.cache/", "at /home/_svc/x",
]
FINE = [
    "Version 1.10.0.1 and 2.10.0.0.5 shipped.", "Public 8.8.8.8, 1.1.1.1 and 172.15.0.1 and 172.32.0.1 and 192.169.0.1.",
    "Address 110.1.2.3 and 1.10.2.3 and 10.1.2.3.4.", "192.168.1 is not an address, nor 10.1.2.", "Release 3.10.100.256.",
    "Path /home/<login>/x and ~/projects and /srv/home/alice/x and ./home/alice/x.", "a /home directory and /home/ alone",
    # A section number is no address (a gzapp slice cited §10.2.1.4, 2026-10-14).
    "fix the §10.2.1.4 sites, see §192.168.1.1 and §172.16.0.1",
]


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    with open(os.path.join(ROOT, "policies", "hygiene.json"), encoding="utf-8") as fh:
        entries = json.load(fh)["patterns"]
    fabric = [(re.compile(e["pattern"]), e["label"], e.get("refer_as")) for e in entries
              if e["label"].startswith(("private-network", "a /home/"))]
    check("four patterns, each with a label and a refer_as", len(fabric) == 4 and all(t[1] and t[2] for t in fabric))
    for text in LEAKS:
        check(f"matched: {text!r}", any(t[0].search(text) for t in fabric))
    for text in FINE:
        check(f"not matched: {text!r}", not any(t[0].search(text) for t in fabric))
    for ranges, text in ((("10.0.0.0/8",), "10.1.2.3"), (("192.168.0.0/16",), "192.168.9.9"), (("172.16.0.0/12",), "172.30.1.1")):
        hit = [t for t in fabric if t[0].search(text)]
        check(f"{text} is caught by the {ranges[0]} pattern alone", len(hit) == 1 and ranges[0] in hit[0][1])
    print("test_hygiene_private_network:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
