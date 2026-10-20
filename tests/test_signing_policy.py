#!/usr/bin/env python3
"""policies/signing.json's reader (tools/fabric/guards/signing_policy.py) and
its lint (tools/fabric/lint_rules/signing.py), on fixture files: the shape
both enforce, the repository a working copy is covered by, and what only the
lint says (a repository no project has, a project named twice, a forge key
whose file is missing, is another key, or is committed and not listed).

Exit codes: 0 all checks passed, 1 one or more failed."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
from signing_fixture import drop_key, make_key  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric", "guards"))
import signing_policy as sp  # noqa: E402
import workingcopy  # noqa: E402
import lint  # noqa: E402

T = tempfile.mkdtemp(prefix="sigpol.")
POLICY = os.path.join(T, "signing.json")
FORGE_DIR = os.path.join(T, "forge-keys")   # beside the policy, as policies/forge-keys/ is
KEYS: list[str] = []   # the throwaway GNUPGHOMEs, dropped at the end
REGISTRY_PATH = os.path.join(T, "registry.json")
REGISTRY = {"version": 1, "projects": {
    "widget": {"remotes": ["git@github.com:acme/widget.git", "https://github.com/acme/widget"], "default_branch": "main"},
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
                       ("a default since that is a sha", {**good, "default": {"format": "ssh", "since": SHA}}),
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
    f = findings({**good, "default": {"format": "ssh", "since": SHA}})
    check("a default since that is a sha", any("default" in x and "since" in x for x in f), f)
    f = findings("{oops")
    check("not JSON", any("not valid JSON" in x for x in f), f)
    os.remove(POLICY)
    check("no policy: nothing to judge", lint.signing_findings(HERE, POLICY, REGISTRY_PATH) == [])

    print("the lint: the since of the repository it runs in")
    own = os.path.join(T, "own")
    os.makedirs(own)

    def g(*a: str) -> str:
        return subprocess.run(["git", "-C", own, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                               "-c", "commit.gpgsign=false", *a], capture_output=True, text=True, check=True).stdout.strip()
    g("init", "-q", "-b", "main")
    g("remote", "add", "origin", "git@github.com:acme/widget.git")
    g("commit", "-q", "--allow-empty", "-m", "one")
    on_main = g("rev-parse", "HEAD")
    g("checkout", "-q", "-b", "side")
    g("commit", "-q", "--allow-empty", "-m", "two")
    on_side = g("rev-parse", "HEAD")
    g("checkout", "-q", "main")

    def own_findings(since: str, root: str = own) -> list[str]:
        write({**good, "repositories": {"acme/widget": {"since": since}}})
        return lint.signing_findings(root, POLICY, REGISTRY_PATH)
    # HEAD is main here and on_side is on no branch HEAD reaches; with no
    # refs/remotes/origin/main the check is skipped, never made against HEAD.
    check("no tracking ref for the registry's default branch: skipped silently",
          own_findings(on_side) == [], own_findings(on_side))
    g("update-ref", "refs/remotes/origin/main", on_main)
    g("checkout", "-q", "side")
    check("the check is against the tracking ref, not HEAD (HEAD is on the side branch)",
          any("not an ancestor" in x for x in own_findings(on_side)), own_findings(on_side))
    g("checkout", "-q", "main")
    check("a since on the default branch: clean", own_findings(on_main) == [], own_findings(on_main))
    f = own_findings(on_side)
    check("a since on a side branch: refused", any("not an ancestor" in x and on_side in x for x in f), f)
    plain = os.path.join(T, "plain")
    os.makedirs(plain)
    check("no git repository: skipped silently", own_findings(on_side, plain) == [], own_findings(on_side, plain))

    print("forge_keys (ADR-057 §5 rule 8)")
    homes, fprs = [], []
    for n in ("ka", "kb"):
        os.makedirs(os.path.join(T, n))
        home, fpr = make_key(os.path.join(T, n))
        KEYS.append(home)
        homes.append(home)
        fprs.append(fpr.upper())

    def armored(i: int) -> str:
        return subprocess.run(["gpg", "--homedir", homes[i], "--batch", "--armor", "--export", fprs[i]], capture_output=True,
                              text=True, check=True, timeout=60).stdout

    def put_key(name: str, i: int) -> None:
        os.makedirs(FORGE_DIR, exist_ok=True)
        with open(os.path.join(FORGE_DIR, name), "w", encoding="utf-8") as f:
            f.write(armored(i))

    listed = {**good, "forge_keys": {fprs[0]: "the forge"}}
    for label, bad in (("a fingerprint in lower case", {**good, "forge_keys": {fprs[0].lower(): "x"}}),
                       ("a key id, not a fingerprint", {**good, "forge_keys": {fprs[0][-16:]: "x"}}),
                       ("a description that is not a string", {**good, "forge_keys": {fprs[0]: 1}}),
                       ("forge_keys not an object", {**good, "forge_keys": [fprs[0]]})):
        write(bad)
        try:
            sp.load(POLICY)
            check(f"the reader refuses {label}", False, "loaded")
        except sp.PolicyError as e:
            check(f"the reader refuses {label}", "forge_keys" in str(e), e)
        f = findings(bad)
        check(f"  ... and so does the lint", any("forge_keys" in x or "does not match" in x for x in f), f)
    write(listed)
    check("the reader takes a listed forge key", sp.load(POLICY)["forge_keys"] == {fprs[0]: "the forge"})
    f = findings(listed)
    check("a listed forge key with no file beside the policy", any(f"{fprs[0]}.asc is not there" in x for x in f), f)
    put_key(f"{fprs[0]}.asc", 0)
    check("a listed forge key whose file is that key: clean", findings(listed) == [], findings(listed))
    check("sp.key_file_primaries reads the file's primary", sp.key_file_primaries(os.path.join(FORGE_DIR, f"{fprs[0]}.asc"),
                                                                                homes[1]) == [fprs[0]])
    put_key(f"{fprs[0]}.asc", 1)
    f = findings(listed)
    check("a listed forge key whose file is another key", any(f"holds {fprs[1]}" in x for x in f), f)
    with open(os.path.join(FORGE_DIR, f"{fprs[0]}.asc"), "w", encoding="utf-8") as fh:
        fh.write(armored(0) + armored(1))
    f = findings(listed)
    check("a listed forge key whose file carries a second key too", any("not the one key" in x for x in f), f)
    put_key(f"{fprs[0]}.asc", 0)
    put_key(f"{fprs[1]}.asc", 1)
    f = findings(listed)
    check("a key file in forge-keys/ that no entry lists", any(f"{fprs[1]}.asc: no entry in forge_keys lists it" in x for x in f), f)
    os.remove(os.path.join(FORGE_DIR, f"{fprs[1]}.asc"))
    rule = sys.modules["fabric_lint_rules.signing"]
    saved, rule.GPG = rule.GPG, "gpg-is-not-installed-here"
    try:
        f = findings(listed)
        check("no gpg on the host: said as a finding, never passed silently", any("gpg is not installed" in x for x in f), f)
    finally:
        rule.GPG = saved
    check("(control) the same with gpg: clean", findings(listed) == [], findings(listed))


try:
    main()
finally:
    for home in KEYS:
        drop_key(home)
    shutil.rmtree(T, ignore_errors=True)
print("all passed" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
