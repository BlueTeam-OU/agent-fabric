#!/usr/bin/env python3
"""The seam holds (agent-fabric ADR-045 rule 1): no module of the engine joins an
instance-data path itself — it asks tools/fabric/roots.py (runtime/control/roots.mjs).

The scan reads source, so it fails for the line that would break the split, not for
a behaviour a fixture happens to cover. EXEMPT names what does not yet go through
roots, each with its reason; a file leaves the list when it moves, and the test
fails if an exempt file no longer has the pattern (a stale exemption hides a
future regression)."""
from __future__ import annotations

import ast
import os
import re
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Path components that, joined, are instance data (ADR-045 rule 2).
SEQUENCES = (
    ("projects", "registry.json"), ("projects", "integration"), ("hosts", "registry.json"),
    ("identities", "roles"), ("identities", "keys"), ("identities", "recovery.asc"),
    ("routing", "profiles.json"), ("routing", "policies"),
    ("docs", "adr"),
)
SINGLE = ("policies", "memory")           # one component after a root: policies/<x>, memory/<x>
SCANNED_DIRS = ("tools", "runtime", "communication/gzcoord/scripts", "projects/gzapp/integration/gh", "bin")
SKIP_PARTS = ("/tests/", "/__pycache__/", "/claude-code/", "/lint_rules/", "/guards/")

# path -> why it does not go through roots yet
EXEMPT = {
    "tools/fabric/roots.py": "the seam itself",
    "runtime/control/roots.mjs": "the seam itself",
    "tools/fabric/layout.py": "fabric-coordinator's (authority.json excluding)",
    "tools/fabric/workingcopy.py": "fabric-coordinator's (authority.json excluding)",
    "tools/fabric/adr.py": "fabric-coordinator's (authority.json excluding)",
    "tools/fabric/lint.py": "fabric-coordinator's (authority.json excluding)",
    "tools/fabric/routing.py": "fabric-coordinator's (authority.json excluding): routing/policies/review-grade.json",
    "tools/fabric/relay.py": "fabric-coordinator's (authority.json excluding): projects/<id>/integration/gzcoord",
    "tools/fabric/install_agent_files.py": "fabric-coordinator's (authority.json excluding): locale files",
    "tools/fabric/secretstore/lineage.py": "fabric-coordinator's (authority.json excluding): keys_dir",
    "tools/fabric/secretstore/trust.py": "git-shows identities/keys/ from the keys' checkout (origin/main), a path inside that repository; moves with the keys (ADR-045 §6)",
    "bin/fabric-host": "bash: reads the registry before any Python runs",
}

# Spelled as plain strings handed to git (`git show origin/main:identities/keys/…`), which no
# join-shaped scan can tell from a message; reviewed by hand.
NOT_SCANNABLE = {"tools/fabric/roots.py", "runtime/control/roots.mjs", "tools/fabric/secretstore/trust.py"}


def sources() -> list[str]:
    out = []
    for d in SCANNED_DIRS:
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, d)):
            norm = dirpath.replace(os.sep, "/") + "/"
            if any(p in norm for p in SKIP_PARTS):
                continue
            for f in files:
                if f.endswith((".py", ".mjs")) or (d == "bin" and not f.endswith(".md")):
                    out.append(os.path.relpath(os.path.join(dirpath, f), ROOT))
    return sorted(out)


def _consts(node: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


# f"{root}/identities/..." and "{root}/..." spelled as one string: a join in disguise.
SPELLED = re.compile(r"^\{[^}]+\}/(projects/|identities/|policies/|memory/|routing/(profiles|policies)|runtime/hosts/|docs/adr)")


def python_findings(src: str) -> list[tuple[int, str]]:
    """Lines where a path is JOINED out of instance components: a join call's
    string arguments, or one f-string that spells a root-relative path."""
    found: list[tuple[int, str]] = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) in ("join", "joinpath", "Path"):
            parts = [a.value for a in n.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if ".agent-fabric" in parts:
                continue                # a project's own memory, not the operator's
            for a, b in SEQUENCES:
                if a in parts and b in parts[parts.index(a) + 1:]:
                    found.append((n.lineno, f"{a}/{b}"))
            if len(n.args) >= 2 and any(s in parts for s in SINGLE):
                found.append((n.lineno, "/".join(parts)))
        elif isinstance(n, ast.JoinedStr):
            text = "".join(_consts(n)) if not n.values or isinstance(n.values[0], ast.Constant) else \
                "{x}" + "".join(_consts(n))
            if SPELLED.match(text):
                found.append((n.lineno, text))
    return found


MJS = re.compile(r"""['"](registry|catalog|profiles|lineage)\.json['"]|"""
                 r"""path\.join\([^)]*['"](identities|policies)['"]|"""
                 r"""['"]projects['"][^)]*['"]integration['"]""")


def mjs_findings(src: str) -> list[tuple[int, str]]:
    return [(i, m.group(0)) for i, line in enumerate(src.splitlines(), 1)
            if not line.lstrip().startswith("//") for m in [MJS.search(line)] if m]


def findings(rel: str, src: str) -> list[tuple[int, str]]:
    if rel.endswith(".mjs"):
        return mjs_findings(src)
    if rel.endswith(".py"):
        return python_findings(src)
    return [(i, line.strip()) for i, line in enumerate(src.splitlines(), 1)
            if re.search(r"runtime/hosts/registry\.json|projects/registry\.json", line) and not line.lstrip().startswith("#")]


def case_no_engine_module_joins_an_instance_path_itself() -> None:
    bad = []
    for rel in sources():
        if rel in EXEMPT:
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            src = fh.read()
        bad += [f"{rel}:{ln}: {what}" for ln, what in findings(rel, src)]
    assert not bad, "instance paths joined outside roots:\n  " + "\n  ".join(bad)


def case_an_exemption_that_no_longer_applies_is_removed() -> None:
    stale = []
    for rel, why in EXEMPT.items():
        if rel in NOT_SCANNABLE:
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            if not findings(rel, fh.read()):
                stale.append(f"{rel} ({why})")
    assert not stale, "exempt, but clean now: " + ", ".join(stale)


def case_the_scan_fires_on_each_style_it_guards_against() -> None:
    """The positive controls: a join that the scan must see, in each form."""
    py = ('import os\n'
          'a = os.path.join(root, "projects", "registry.json")\n'
          'b = os.path.join(root, "runtime", "hosts", "registry.json")\n'
          'c = os.path.join(root, "identities", "roles", role, "charter.md")\n'
          'd = f"{fabric}/identities/roles/language-culture/locale/{suffix}"\n'
          'e = os.path.join(root, "policies", "hygiene.json")\n'
          'f = os.path.join(root, "memory", "domains")\n'
          'g = os.path.join(root, "projects", pid, "integration", "gh", "arm.json")\n')
    lines = {ln for ln, _ in python_findings(py)}
    assert lines == {2, 3, 4, 5, 6, 7, 8}, lines
    mjs = "const f = path.join(FABRIC_ROOT, 'runtime', 'hosts', 'registry.json');\nconst c = 'catalog.json';\n"
    assert {ln for ln, _ in mjs_findings(mjs)} == {1, 2}


def case_the_scan_leaves_alone_what_is_not_instance_data() -> None:
    clean = ('import os\n'
             'a = os.path.join(root, "runtime", "identity.py")\n'
             'b = os.path.join(home, "projects", "agent-fabric")\n'
             'c = os.path.join(root, "routing", "capabilities.json")\n'
             'd = os.path.join(root, "identities", "schemas", "claims.schema.json")\n'
             'e = os.path.join(root, "bin", "fabric-ctl")\n')
    got = python_findings(clean)
    assert got == [], got


# ── the moved readers read the operator root ─────────────────────────────

def operator_fixture(tmp: str) -> str:
    """An operator tree holding only what the readers below ask for, with names no
    engine file carries, so a reader that still joined the engine's own would find
    the live data (or nothing) and the assertion would fail."""
    import json
    op = os.path.join(tmp, "operator")
    for rel, doc in (
        ("projects/registry.json", {"agent_env": {"OP_ONLY": "x"}, "projects": {"opproj": {
            "remotes": ["git@github.com:op-org/op-repo.git"], "agent_env": {"OP_PROJECT_NAME": "y"}}}}),
        ("runtime/hosts/registry.json", {"hosts": {}, "placement": {"op-login": "op-host"}}),
        ("identities/roles/catalog.json", {"roles": [{"id": "op-role"}]}),
    ):
        os.makedirs(os.path.dirname(os.path.join(op, rel)), exist_ok=True)
        with open(os.path.join(op, rel), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    return op


class operator:
    """AGENT_FABRIC_OPERATOR (and nothing else of the session's) for a block."""
    def __init__(self, root: str):
        self.root = root

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in ("AGENT_FABRIC_OPERATOR", "AGENT_FABRIC_ROOT", "AGENT_FABRIC_HOSTS_REGISTRY")}
        os.environ["AGENT_FABRIC_OPERATOR"] = self.root
        os.environ.pop("AGENT_FABRIC_ROOT", None)
        os.environ.pop("AGENT_FABRIC_HOSTS_REGISTRY", None)

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def case_the_projects_registry_readers_follow_the_operator_root() -> None:
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    import results
    from github import commit_class
    from secretstore import reserved
    with tempfile.TemporaryDirectory() as tmp, operator(operator_fixture(tmp)):
        assert results.registered_repos() == ["op-org/op-repo"], results.registered_repos()
        assert "opproj" in commit_class.known_repos() and "op-repo" in commit_class.known_repos()
        assert set(reserved.registry_agent_env()) == {"OP_ONLY", "OP_PROJECT_NAME"}


def case_the_hosts_registry_readers_follow_the_operator_root() -> None:
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    import status
    import store_provision
    with tempfile.TemporaryDirectory() as tmp, operator(operator_fixture(tmp)):
        assert store_provision.placed_logins() == ["op-login"]
        placement, drift = status.placement_of({"agent": "op-login", "host": "op-host"}, ROOT, dict(os.environ))
        assert placement == "op-host" and drift is None, (placement, drift)


def case_the_role_catalogue_readers_follow_the_operator_root() -> None:
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    from github import arm
    from gzcoord import gzmsg
    with tempfile.TemporaryDirectory() as tmp, operator(operator_fixture(tmp)):
        assert arm.waiver_role_checked("op-role") == "op-role"
        assert gzmsg.find_taxonomy() == os.path.join(tmp, "operator", "identities", "roles", "catalog.json")


def case_enrol_i18n_and_query_follow_the_operator_root() -> None:
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    import store_enroll
    from gzcoord import i18n
    with tempfile.TemporaryDirectory() as tmp:
        op = operator_fixture(tmp)
        os.makedirs(os.path.join(op, "memory", "domains"))
        locale = os.path.join(op, "identities", "roles", "op-role", "locale", "xx")
        os.makedirs(locale)
        with open(os.path.join(locale, "locale.json"), "w", encoding="utf-8") as fh:
            fh.write('{"reminder": "from the operator"}')
        with operator(op):
            assert store_enroll.Enrol(dry=True, born_now=False, host_flag="").hosts == os.path.join(op, "runtime", "hosts", "registry.json")
            assert i18n.locale_reminder({"role": "op-role", "agent": "agent-xx", "binding": "b"}, env={}) == "from the operator"
            import query
            query.run(["roles"])           # the operator's (empty) corpus is found
        bare = os.path.join(tmp, "bare")
        os.makedirs(bare)
        with operator(bare):
            try:
                query.run(["roles"])
            except query.Failure as e:
                assert os.path.join(bare, "memory") in str(e), str(e)
            else:
                raise AssertionError("a corpus-less operator root was answered from the engine's memory/")


def main() -> int:
    cases = [v for k, v in globals().items() if k.startswith("case_")]
    failures = 0
    for case in cases:
        try:
            case()
            print(f"  ok   {case.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
