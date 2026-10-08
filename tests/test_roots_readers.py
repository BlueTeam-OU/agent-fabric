#!/usr/bin/env python3
"""The readers moved onto roots (agent-fabric ADR-045 §5 rules 1-3) follow
AGENT_FABRIC_OPERATOR and, with it unset, still read the engine's own tree.
Each case builds its instance files under the test's own temp dir, with
names no engine file carries, so a reader that still joined the engine's tree
could not pass."""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from test_roots_seam import operator  # noqa: E402


def write(path: str, doc: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc if isinstance(doc, str) else json.dumps(doc))


class unset_operator:
    """No operator, no engine override: the readers' own-tree default."""
    def __enter__(self):
        self.saved = {k: os.environ.pop(k, None) for k in ("AGENT_FABRIC_OPERATOR", "AGENT_FABRIC_ROOT")}

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is not None:
                os.environ[k] = v


def case_relay_reads_integrations_from_the_operator() -> None:
    import relay
    with tempfile.TemporaryDirectory() as tmp:
        op = os.path.join(tmp, "op")
        write(os.path.join(op, "projects", "opproj", "integration", "gzcoord", "config.json"),
              {"relay_url": "https://op.example", "channel": "op-chan"})
        with operator(op):
            assert relay.integrated_projects() == ["opproj"], relay.integrated_projects()
            assert relay.channels(["opproj"], {}) == ([("https://op.example", "op-chan")], [])
        with unset_operator():
            assert relay.config_path("agent-fabric").startswith(ROOT + os.sep)
            assert "opproj" not in relay.integrated_projects()


def case_install_agent_files_finds_the_locale_worker_in_the_operator() -> None:
    import install_agent_files
    with tempfile.TemporaryDirectory() as tmp:
        engine, op = os.path.join(tmp, "engine"), os.path.join(tmp, "op")
        rel = os.path.join("identities", "roles", "language-culture", "locale", "xx", "worker.md")
        write(os.path.join(op, rel), "from the operator")
        os.makedirs(engine)
        for root_env, expect in ((operator(op), [b"from the operator"]), (unset_operator(), [])):
            put = []
            inst = install_agent_files.Installer("claude", True, root=engine)
            inst.put = lambda dest, content: put.append(content)
            with root_env:
                inst.locale_worker(os.path.join(tmp, "home"), "language-culture", "xx")
            assert put == expect, (put, expect)
        write(os.path.join(engine, rel), "from the engine")
        put = []
        inst = install_agent_files.Installer("claude", True, root=engine)
        inst.put = lambda dest, content: put.append(content)
        with unset_operator():
            inst.locale_worker(os.path.join(tmp, "home"), "language-culture", "xx")
        assert put == [b"from the engine"], put


def case_routing_reads_policy_and_profiles_from_the_operator() -> None:
    import routing
    with tempfile.TemporaryDirectory() as tmp:
        op = os.path.join(tmp, "op")
        write(os.path.join(op, "routing", "policies", "review-grade.json"), {"capability": "op-cap", "models": ["op/model"]})
        write(os.path.join(op, "routing", "profiles.json"), {"version": 2, "defaults": {"op-provider": {}}})
        with operator(op):
            assert routing.load_review_grade()["capability"] == "op-cap"
            assert "op-provider" in routing.load_profiles()["defaults"]
        with unset_operator():
            assert routing.load_review_grade()["capability"] == "code-review"
            assert "op-provider" not in routing.load_profiles()["defaults"]
            assert routing.load_review_grade(op)["capability"] == "op-cap"     # an explicit root still wins
            assert routing.load_profiles(op)["defaults"].get("op-provider") == {}


def case_adr_reads_records_and_the_registry_from_the_operator() -> None:
    import adr
    with tempfile.TemporaryDirectory() as tmp:
        op = os.path.join(tmp, "op")
        write(os.path.join(op, "docs", "adr", "DIGEST.md"), "| Topic | Record |\n|---|---|\n| opdigest | ADR-000 |\n\n### ADR-000 x\n")
        write(os.path.join(op, "projects", "registry.json"), {"projects": {"opproj": {}, "agent-fabric": {}}})
        with operator(op):
            assert adr.adr_dir() == os.path.join(op, "docs", "adr")
            assert "opdigest" in adr.cmd_lookup(None, [])[0]
            assert adr.foreign_projects(None) == {"opproj"}
            assert adr.tree(None) == op
        with unset_operator():
            assert adr.adr_dir() == os.path.join(ROOT, "docs", "adr")
            assert "opproj" not in adr.foreign_projects(None)
            assert adr.check() == []
            assert adr.adr_dir(op) == os.path.join(op, "docs", "adr")      # --root still names the tree


def case_workingcopy_reads_the_operators_registry_and_arm_follows() -> None:
    import subprocess
    import workingcopy
    from github import arm, local
    with tempfile.TemporaryDirectory() as tmp:
        op = os.path.join(tmp, "op")
        write(os.path.join(op, "projects", "registry.json"), {"version": 1, "projects": {"opproj": {"remotes": ["git@github.com:op-org/op-repo.git"]}}})
        # a working copy beside the "checkout", with a memory dir and a marker naming the operator's project
        checkout, sibling = os.path.join(tmp, "checkout"), os.path.join(tmp, "sibling")
        os.makedirs(checkout)
        write(os.path.join(sibling, ".agent-fabric", "memory", "keep"), "")
        write(os.path.join(sibling, workingcopy.MARKER), "opproj")
        subprocess.run(["git", "-C", sibling, "init", "-q"], check=True)
        with operator(op):
            assert "opproj" in workingcopy.load_registry()["projects"]
            assert workingcopy.sibling_working_copies(checkout) == {"opproj": sibling}
            real = local.toplevel
            local.toplevel = lambda: sibling
            try:
                assert arm.config_path() == os.path.join(op, "projects", "opproj", "integration", "gh", "arm.json")
            finally:
                local.toplevel = real
        with unset_operator():
            assert "opproj" not in workingcopy.load_registry()["projects"]
            assert "agent-fabric" in workingcopy.load_registry()["projects"]
            # an explicit path is still read as given
            assert "opproj" in workingcopy.load_registry(os.path.join(op, "projects", "registry.json"))["projects"]


def case_layout_places_memory_roles_and_registry_in_the_operator() -> None:
    import layout
    with tempfile.TemporaryDirectory() as tmp:
        op = os.path.join(tmp, "op")
        write(os.path.join(op, "projects", "registry.json"), {"projects": {"opproj": {}}})
        write(os.path.join(op, "policies", "hygiene.json"), {})
        with operator(op):
            assert layout.project_ids() == ["opproj"]
            assert layout.roles_dir() == os.path.join(op, "identities", "roles")
            assert layout.catalog_path() == os.path.join(op, "identities", "roles", "catalog.json")
            assert layout.domain_dir("d") == os.path.join(op, "memory", "domains", "d")
            assert layout.shared_dir() == os.path.join(op, "memory", "shared")
            assert layout.agent_memory_dir("a") == os.path.join(op, "memory", "agents", "a")
            assert layout.project_taxonomy_path("opproj") is None
            write(os.path.join(op, "projects", "opproj", "taxonomy.json"), {})
            assert layout.project_taxonomy_path("opproj") == os.path.join(op, "projects", "opproj", "taxonomy.json")
        with unset_operator():
            assert layout.roles_dir() == os.path.join(layout.FABRIC_ROOT, "identities", "roles")
            assert layout.domain_dir("d") == os.path.join(layout.FABRIC_ROOT, "memory", "domains", "d")
            assert "opproj" not in layout.project_ids()


def case_lint_reads_catalogue_and_authority_from_the_operator() -> None:
    import lint
    with tempfile.TemporaryDirectory() as tmp:
        op, engine = os.path.join(tmp, "op"), os.path.join(tmp, "engine")
        os.makedirs(engine)
        write(os.path.join(op, "identities", "roles", "catalog.json"), {"roles": [{"id": "op-role"}]})
        write(os.path.join(op, "policies", "authority.json"), {"contributors": "not a list"})
        with operator(op):
            assert lint._catalog_roles(engine) == {"op-role"}
            assert lint.contributor_findings(engine) == ["policies/authority.json: `contributors` is not a list"]
        with unset_operator():
            assert lint._catalog_roles(engine) is None          # the engine tree given holds no catalogue
            assert lint.contributor_findings(engine) == []
            assert "op-role" not in lint._catalog_roles(ROOT)


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
