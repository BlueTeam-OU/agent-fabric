#!/usr/bin/env python3
"""Tests read instance fixtures, never this checkout's live instance files
(agent-fabric ADR-045 §5 rule 3): no test joins the checkout's own root
with an instance path. The scan reads source, as tests/test_roots_seam.py
does for engine modules, and shares its list of instance components.

A path is the checkout's when it is built on a name the file binds from
__file__ (ROOT, HERE, FABRIC = ...join(HERE, ...), followed through the
module's own assignments) or on __file__ itself: a join on a temporary
directory is a fixture, and is never flagged. ALLOWED names each file that
still does, with its reason; the guard fails for a file outside it, and for
an entry whose file no longer does (a stale entry hides the next one).

What a source scan cannot see, and this one does not claim to: a path
assembled in a loop from a tuple of strings, a whole directory copied
(shutil.copytree(ROOT/routing) carries routing/profiles.json), and a tool
run with AGENT_FABRIC_ROOT at the checkout that reads instance data itself.
Those are found by running the suite on a copy of the tree with the
instance files moved aside, as the request's acceptance does."""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from test_roots_seam import SEQUENCES  # noqa: E402

SCANNED = ("tests", "communication/gzcoord/tests")

# file -> why it still reads the live tree. The first two check a fact of
# the operator's real data on purpose. The rest are not yet moved to
# fixtures (fabric-coordinator's request 01a11d15-2dc2-7cc9-8e7b-770a36dcf895
# gives them to python-dev-02) and leave this list as they move; it only
# shrinks.
DELIBERATE = {
    "tests/test_hosts_registry.py": "the committed operator key parses as the daemons read it: the operator's own data",
    "tests/test_fabric_status.py": "bin/fabric-status is off the committed bash allowlist: a fact of this tree",
}
PENDING = "not yet on fixtures (request 01a11d15)"
ALLOWED = {**DELIBERATE, **{f"tests/{f}": PENDING for f in (
    "test_arm_cli.py", "test_arm_fabric_config.py", "test_guards_wired.py", "test_gzcoord_i18n.py",
    "test_launch_prompt.py", "test_lint.py", "test_new_agent_cli.py", "test_pr_compliance_cli.py",
    "test_roots_readers.py", "test_roots_seam.py", "test_secret_selftest.py", "test_secret_store.py",
    "test_semantic_collisions.py", "test_session_commands.py", "test_store_signing.py",
    "test_user_settings_auto_mode.py", "test_wait_merged.py")}}


# docs/adr is not counted here, though test_roots_seam's engine scan does:
# the records are a mixed set (ADR-045 §5 rule 4 freezes their numbers),
# and tests/test_adr.py checks the engine's own corpus on purpose.
TEST_SEQUENCES = tuple(s for s in SEQUENCES if s != ("docs", "adr"))


def instance(parts: list[str]) -> str | None:
    """The instance path these root-relative components reach, or None. It
    begins at the root: tests/fixtures/<x>/identities/... is a fixture."""
    parts = [p for s in parts for p in s.split("/") if p not in ("", ".", "..")]
    head = parts[1:] if parts[:1] == ["runtime"] else parts       # runtime/hosts/registry.json
    for a, b in TEST_SEQUENCES:
        if head[:1] == [a] and b in head[1:]:
            return f"{a}/{b}"
    if parts[:1] == ["policies"] and len(parts) == 2 and parts[1].endswith(".json"):
        return "/".join(parts)                     # policies/*.json; policies' scripts and hooks are engine code
    if parts[:1] == ["memory"] or parts[:2] == ["docs", "live-checks"]:
        return "/".join(parts[:2])
    return None


def into_tests(value: ast.AST) -> bool:
    """A join whose first component after its root is tests/."""
    return isinstance(value, ast.Call) and getattr(value.func, "attr", "") == "join" and len(value.args) > 1 \
        and isinstance(value.args[1], ast.Constant) and value.args[1].value == "tests"


def checkout_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for n in tree.body:
            if not isinstance(n, ast.Assign):
                continue
            used = "__file__" in ast.unparse(n.value) or any(isinstance(x, ast.Name) and x.id in names for x in ast.walk(n.value))
            if used and into_tests(n.value):
                continue                       # FIXTURES = join(ROOT, "tests", ...) is a fixture's place, not the root
            for t in n.targets if used else ():
                for x in ast.walk(t):
                    if isinstance(x, ast.Name) and x.id not in names:
                        names.add(x.id)
                        changed = True
    return names


def findings(src: str) -> list[tuple[int, str]]:
    tree = ast.parse(src)
    roots = checkout_names(tree)

    def on_checkout(node: ast.AST) -> bool:
        return (isinstance(node, ast.Name) and node.id in roots) or "__file__" in ast.unparse(node)

    found = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) in ("join", "joinpath", "Path") \
                and n.args and on_checkout(n.args[0]):
            what = instance([a.value for a in n.args[1:] if isinstance(a, ast.Constant) and isinstance(a.value, str)])
            if what:
                found.append((n.lineno, what))
        elif isinstance(n, ast.JoinedStr) and n.values and isinstance(n.values[0], ast.FormattedValue) \
                and on_checkout(n.values[0].value):
            rest = "".join(v.value if isinstance(v, ast.Constant) else "/{x}/" for v in n.values[1:])
            what = instance([rest])
            if what:
                found.append((n.lineno, what))
    return sorted(set(found))


def scanned() -> list[str]:
    out = []
    for d in SCANNED:
        for f in sorted(os.listdir(os.path.join(ROOT, d))):
            if f.endswith(".py"):
                out.append(f"{d}/{f}")
    return out


def case_no_test_reads_the_live_instance_files() -> None:
    bad = []
    for rel in scanned():
        if rel in ALLOWED:
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            bad += [f"{rel}:{ln}: {what}" for ln, what in findings(fh.read())]
    assert not bad, ("the checkout's live instance files read by a test (build a fixture, or export "
                     "AGENT_FABRIC_OPERATOR to one):\n  " + "\n  ".join(bad))


def case_an_allowance_that_no_longer_applies_is_removed() -> None:
    stale = []
    for rel, why in ALLOWED.items():
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            if not findings(fh.read()):
                stale.append(f"{rel} ({why})")
    assert not stale, "allowed, but reads no live instance file now: " + ", ".join(stale)


def case_the_scan_sees_each_form() -> None:
    """Positive controls: the checkout's root by each binding, in each spelling."""
    src = ('import os\n'
           'HERE = os.path.dirname(os.path.abspath(__file__))\n'
           'ROOT = os.path.dirname(HERE)\n'
           'FABRIC = os.path.normpath(os.path.join(ROOT, "x", ".."))\n'
           'a = os.path.join(ROOT, "projects", "registry.json")\n'
           'b = os.path.join(HERE, "..", "runtime", "hosts", "registry.json")\n'
           'c = f"{FABRIC}/identities/roles/catalog.json"\n'
           'd = os.path.join(ROOT, "policies", "hygiene.json")\n'
           'e = os.path.join(os.path.dirname(__file__), "..", "routing", "profiles.json")\n'
           'f = os.path.join(ROOT, "memory", "domains")\n'
           'g = f"{ROOT}/projects/{pid}/integration/gh/arm.json"\n')
    assert {ln for ln, _ in findings(src)} == {5, 6, 7, 8, 9, 10, 11}, findings(src)


def case_the_scan_leaves_fixtures_and_engine_files_alone() -> None:
    src = ('import os, tempfile\n'
           'ROOT = os.path.dirname(os.path.dirname(__file__))\n'
           'tmp = tempfile.mkdtemp()\n'
           'a = os.path.join(tmp, "projects", "registry.json")\n'
           'b = f"{tmp}/identities/roles/catalog.json"\n'
           'c = os.path.join(ROOT, "policies", "githooks", "pre-commit")\n'
           'd = os.path.join(ROOT, "routing", "capabilities.json")\n'
           'e = os.path.join(ROOT, "tests", "fixtures", "gzcoord-operator", "identities", "roles", "catalog.json")\n'
           'f = os.path.join(ROOT, "policies", "check_charter_authority.sh")\n'
           'FIX = os.path.join(ROOT, "tests", "fixtures", "op")\n'
           'g = os.path.join(FIX, "identities", "roles", "catalog.json")\n'
           'h = os.path.join(ROOT, "docs", "adr", "DIGEST.md")\n')
    got = findings(src)
    assert got == [], got


def main() -> int:
    cases = [v for k, v in globals().items() if k.startswith("case_") and callable(v)]
    fails = 0
    for c in cases:
        try:
            c()
            print(f"  ok   {c.__name__}")
        except AssertionError as exc:
            fails += 1
            print(f"  FAIL {c.__name__}: {exc}")
    print(f"\n{len(cases) - fails}/{len(cases)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
