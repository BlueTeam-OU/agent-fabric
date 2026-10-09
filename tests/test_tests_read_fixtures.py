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
Those are found by running the files on a copy of the tree with the
instance data removed, as the request's acceptance does:
tests/stripped_run.py <tree> <test file>... (seven files it found read the
registry, a role, memory/ or the auto-mode policy through the tools they
run, none of which this scan could flag)."""
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

# Read the live instance files in a way no source scan follows — a whole
# directory of the checkout copied or linked into a fixture — so the scan
# cannot hold them; reviewed by hand, and moved like the rest (review of #128).
UNSCANNABLE = {
    "tests/test_model_profile.py": "links every top-level entry of the checkout and copies routing/: reads routing/profiles.json",
    "tests/test_routing.py": "copies the checkout's routing/: reads routing/profiles.json and routing/policies/",
}
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
    norm: list[str] = []
    for p in (p for s in parts for p in s.split("/") if p not in ("", ".")):
        if p == "..":
            if norm:
                norm.pop()                # x/.. is where it started; above the root stays the root
        else:
            norm.append(p)
    parts = norm
    head = parts[1:] if parts[:1] == ["runtime"] else parts       # runtime/hosts/registry.json
    for a, b in TEST_SEQUENCES:
        if head[:1] == [a] and b in head[1:]:
            return f"{a}/{b}"
    if parts[:1] == ["policies"] and len(parts) == 2 and parts[1].endswith(".json"):
        return "/".join(parts)                     # policies/*.json; policies' scripts and hooks are engine code
    if parts[:1] == ["memory"] or parts[:2] == ["docs", "live-checks"]:
        return "/".join(parts[:2])
    return None


Parts = list  # root-relative path components; "{x}" for one the scan cannot read


def resolve(node: ast.AST, names: dict[str, Parts]) -> Parts | None:
    """The checkout-relative path an expression names, or None when it is not
    built on the checkout's root: __file__ itself, a name bound from it, and
    joins, dirname/abspath/normpath and pathlib's / and .parent over those."""
    if isinstance(node, ast.Name):
        return [] if node.id == "__file__" else names.get(node.id)
    if isinstance(node, ast.Attribute):
        if node.attr in ("parent", "resolve") or isinstance(node.value, ast.Call):
            return resolve(node.value, names)
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        base = resolve(node.left, names)
        if base is None:
            return None
        r = node.right
        return base + ([r.value] if isinstance(r, ast.Constant) and isinstance(r.value, str) else ["{x}"])
    if isinstance(node, ast.Call):
        fn = getattr(node.func, "attr", getattr(node.func, "id", ""))
        if fn in ("join", "joinpath", "Path", "PurePath") and node.args:
            # Path(ROOT, "a", "b") joins as join() does; .joinpath(...) on a path.
            base = resolve(node.func.value, names) if fn == "joinpath" else resolve(node.args[0], names)
            rest = node.args if fn == "joinpath" else node.args[1:]
            if base is None:
                return None
            return base + [a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else "{x}" for a in rest]
        if fn in ("dirname", "abspath", "normpath", "realpath", "resolve") and node.args:
            return resolve(node.args[0], names)
        if fn == "resolve" and isinstance(node.func, ast.Attribute):
            return resolve(node.func.value, names)
        return None
    return None


def checkout_names(tree: ast.Module) -> dict[str, Parts]:
    """Every name the file binds — module, function, annotated or not — to a
    path on the checkout's root, with that path's components."""
    names: dict[str, Parts] = {}
    changed = True
    while changed:
        changed = False
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign):
                targets, value = n.targets, n.value
            elif isinstance(n, ast.AnnAssign) and n.value is not None:
                targets, value = [n.target], n.value
            else:
                continue
            parts = resolve(value, names)
            if parts is None:
                continue
            for t in targets:
                if isinstance(t, ast.Name) and names.get(t.id) != parts and t.id not in names:
                    names[t.id] = parts
                    changed = True
    return names


def findings(src: str) -> list[tuple[int, str]]:
    tree = ast.parse(src)
    names = checkout_names(tree)
    found = []
    for n in ast.walk(tree):
        parts = None
        if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) in ("join", "joinpath", "Path", "PurePath"):
            parts = resolve(n, names)
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
            parts = resolve(n, names)
        elif isinstance(n, ast.JoinedStr) and n.values and isinstance(n.values[0], ast.FormattedValue):
            base = resolve(n.values[0].value, names)
            if base is not None:
                parts = base + ["".join(v.value if isinstance(v, ast.Constant) else "/{x}/" for v in n.values[1:])]
        if parts is None or parts[:1] == ["tests"]:
            continue                                   # not the checkout's, or a fixture under tests/
        what = instance(parts)
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
        if rel in ALLOWED or rel in UNSCANNABLE:
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            bad += [f"{rel}:{ln}: {what}" for ln, what in findings(fh.read())]
    assert not bad, ("the checkout's live instance files read by a test (build a fixture, or export "
                     "AGENT_FABRIC_OPERATOR to one):\n  " + "\n  ".join(bad))


def case_an_allowance_that_no_longer_applies_is_removed() -> None:
    gone = [rel for rel in UNSCANNABLE if not os.path.isfile(os.path.join(ROOT, rel))]
    assert not gone, "named unscannable, but no such file: " + ", ".join(gone)
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
           'g = f"{ROOT}/projects/{pid}/integration/gh/arm.json"\n'
           'PROJ = os.path.join(ROOT, "projects")\n'
           'h = os.path.join(PROJ, "registry.json")\n'
           'from pathlib import Path\n'
           'i = Path(__file__).resolve().parent.parent / "identities" / "roles" / "catalog.json"\n'
           'R2: str = os.path.dirname(os.path.abspath(__file__))\n'
           'j = os.path.join(R2, "policies", "auto-mode.json")\n'
           'def f():\n'
           '    local = os.path.dirname(os.path.dirname(__file__))\n'
           '    return os.path.join(local, "runtime", "hosts", "registry.json")\n'
           'k = Path(ROOT, "policies", "auto-mode.json")\n'
           'm = Path(ROOT, "policies") / "x.json"\n')
    assert {ln for ln, _ in findings(src)} == {5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 20, 21, 22}, findings(src)


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
