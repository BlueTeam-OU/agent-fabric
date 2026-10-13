#!/usr/bin/env python3
"""policies/signing.json's reader (tools/fabric/guards/signing_policy.py) and
its lint (tools/fabric/lint_rules/signing.py), on fixture files: the shape
both enforce, the repository a working copy is covered by, and what only the
lint says (a repository no project has, a project named twice).

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric", "guards"))
import signing_policy as sp  # noqa: E402
import workingcopy  # noqa: E402
import lint  # noqa: E402

T = tempfile.mkdtemp(prefix="sigpol.")
POLICY = os.path.join(T, "signing.json")
REGISTRY_PATH = os.path.join(T, "registry.json")
REGISTRY = {"version": 1, "projects": {
    "widget": {"remotes": ["git@github.com:acme/widget.git", "https://github.com/acme/widget"]},
    "moved": {"remotes": ["git@github.com:neworg/thing.git", "git@github.com:oldorg/thing.git"]},
}}
SHA = "a" * 40
fails = 0


def check(label: str, good: bool, detail: object = "") -> None:
    global fails
    if good:
        print(f"  ok   {label}")
        return
    fails += 1
    print(f"  FAIL {label}: {detail}")


def write(doc: object) -> None:
    with open(POLICY, "w", encoding="utf-8") as f:
        f.write(doc if isinstance(doc, str) else json.dumps(doc))


def findings(doc: object) -> list[str]:
    write(doc)
    return lint.signing_findings(HERE, POLICY, REGISTRY_PATH)


def main() -> None:
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(REGISTRY, f)
    good = {"default": {"format": "ssh", "since": None},
            "repositories": {"acme/widget": {"format": "openpgp", "since": SHA}, "oldorg/thing": {"since": None}}}

    print("the reader")
    write(good)
    doc = sp.load(POLICY)
    pr = workingcopy.parse_remote
    check("an entry's own keys win", sp.entry_for(doc, "acme/widget", REGISTRY, pr) ==
          ("acme/widget", {"format": "openpgp", "since": SHA}))
    check("a missing key is the default's; a project is found by any of its names",
          sp.entry_for(doc, "neworg/thing", REGISTRY, pr) == ("oldorg/thing", {"format": "ssh", "since": None}))
    check("case does not matter (GitHub's names do not)",
          sp.entry_for(doc, "ACME/Widget", REGISTRY, pr)[0] == "acme/widget")
    check("a repository no entry names: the default, not covered",
          sp.entry_for(doc, "acme/elsewhere", REGISTRY, pr) == (None, {"format": "ssh", "since": None}))
    check("no repository at all: the default", sp.entry_for(doc, None, REGISTRY, pr)[0] is None)
    check("slug_of reads both remote shapes",
          sp.slug_of("git@github.com:acme/widget.git", pr) == "acme/widget"
          and sp.slug_of("https://github.com/acme/widget", pr) == "acme/widget" and sp.slug_of("/a/path", pr) is None)
    os.remove(POLICY)
    check("an absent policy: the fleet default, nothing covered",
          sp.load(POLICY) == {"default": {"format": "ssh", "since": None}, "repositories": {}})
    for label, bad in (("not JSON", "{oops"), ("a format no forge takes", {**good, "default": {"format": "x509", "since": None}}),
                       ("a since that is not a full sha", {**good, "repositories": {"acme/widget": {"since": "abc123"}}}),
                       ("an unknown key", {**good, "forges": {}}),
                       ("a default without since", {"default": {"format": "ssh"}, "repositories": {}})):
        write(bad)
        try:
            sp.load(POLICY)
            check(f"refused: {label}", False, "loaded")
        except sp.PolicyError as e:
            check(f"refused: {label}", True, e)

    print("the lint")
    check("a good policy: clean", findings(good) == [], findings(good))
    f = findings({**good, "repositories": {"acme/nowhere": {"since": None}}})
    check("a repository the registry does not have", any("acme/nowhere is not the owner/name" in x for x in f), f)
    f = findings({**good, "repositories": {"neworg/thing": {}, "oldorg/thing": {}}})
    check("one project named twice (its old and new names)", any("both name project moved" in x for x in f), f)
    f = findings({**good, "repositories": {"acme/widget": {"since": "HEAD"}}})
    check("a since that is not a sha", any("since" in x for x in f), f)
    f = findings("{oops")
    check("not JSON", any("not valid JSON" in x for x in f), f)
    os.remove(POLICY)
    check("no policy: nothing to judge", lint.signing_findings(HERE, POLICY, REGISTRY_PATH) == [])


try:
    main()
finally:
    shutil.rmtree(T, ignore_errors=True)
print("all passed" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
