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
from instance_fixtures import code_tree  # noqa: E402
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
        # No operator: the tree the code is in, here a fixture that holds a project of its own.
        eng = os.path.join(tmp, "engine")
        write(os.path.join(eng, "projects", "registry.json"), {"projects": {"engproj": {}, "agent-fabric": {}}})
        with code_tree(eng, adr), unset_operator():
            assert adr.adr_dir() == os.path.join(eng, "docs", "adr")
            assert adr.foreign_projects(None) == {"engproj"}
            assert adr.check() == [f"{adr.ADR_DIR}: missing"]                # the records are read from the same default tree
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
        eng = os.path.join(tmp, "engine")
        write(os.path.join(eng, "projects", "registry.json"), {"projects": {"engproj": {}}})
        with code_tree(eng, workingcopy, attr="FABRIC_ROOT"), unset_operator():
            assert "opproj" not in workingcopy.load_registry()["projects"]
            assert "engproj" in workingcopy.load_registry()["projects"]
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
            write(os.path.join(engine, "identities", "roles", "catalog.json"), {"roles": [{"id": "engine-role"}]})
            assert lint._catalog_roles(engine) == {"engine-role"}   # the control: the engine's own catalogue, not the operator's


def case_lint_with_an_operator_copy_says_what_it_says_without_one() -> None:
    """The whole corpus lint over an operator tree that is a copy of this
    checkout's instance data prints what it prints with none exported: the
    index links (`../agent-fabric/...`) and labels resolve in the operator's
    tree as in the engine's (review of #125: 183 false drift findings)."""
    import shutil
    import subprocess
    base = {k: v for k, v in os.environ.items() if k not in ("AGENT_FABRIC_ROOT", "AGENT_FABRIC_OPERATOR")}
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("identities/roles", "identities/schemas", "identities/keys", "projects", "policies", "memory",
                  "routing", "docs", "runtime/hosts"):
            shutil.copytree(os.path.join(ROOT, d), os.path.join(tmp, d))
        run = lambda env: subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "lint.py"),  # noqa: E731
                                          "--no-siblings"], capture_output=True, text=True, env=env, timeout=300)
        plain, over = run(base), run({**base, "AGENT_FABRIC_OPERATOR": tmp})
        assert (over.returncode, over.stdout) == (plain.returncode, plain.stdout), \
            f"with the operator: rc {over.returncode}\n{over.stdout[-600:]}\nwithout: rc {plain.returncode}\n{plain.stdout[-300:]}"


def case_fabric_labels_do_not_depend_on_the_checkouts_name() -> None:
    """With an operator exported, a fabric-side slice is labelled relative to
    the tree it lies in, and fabric_path() finds it there, whatever the engine
    checkout is called (review of #125: labels became ../agent-fabric/... and
    lint opened them through the engine checkout's sibling name)."""
    from lint_rules.slices import lint_slices
    from lint_rules import base as rules_base
    layout = rules_base.layout   # the rules load their own copy of layout.py by path
    role = "fixture-role"
    saved = layout.FABRIC_ROOT
    try:
        layout.FABRIC_ROOT = "/nonexistent/checkout-under-another-name"
        with tempfile.TemporaryDirectory() as op, operator(op):
            for name in ("charter.md", "brief.md"):
                os.makedirs(os.path.join(op, "identities", "roles", role), exist_ok=True)
                with open(os.path.join(op, "identities", "roles", role, name), "w", encoding="utf-8") as fh:
                    fh.write(f"# {name}\n")
            labels = lint_slices(os.path.join(op, "identities", "roles", role), f"identities/roles/{role}",
                                 None, [], {}, {})
            assert labels and all(l.startswith(f"identities/roles/{role}/") for l in labels), labels
            assert all(os.path.isfile(layout.fabric_path(l)) for l in labels), labels
    finally:
        layout.FABRIC_ROOT = saved


def case_a_project_whose_working_copy_is_the_operator_links_its_own_slices() -> None:
    """A project registered at the operator's root links its own slices from
    where it stands; only another project reaches the operator's files through
    the sibling prefix (re-review of #125, P3 1)."""
    import layout
    with tempfile.TemporaryDirectory() as tmp:
        op = os.path.join(tmp, "op")
        slice_ = os.path.join(op, ".agent-fabric", "memory", "fabric-coordinator", "x.md")
        write(slice_, "x")
        write(os.path.join(op, "projects", "registry.json"), {"projects": {"opproj": {}, "other": {}}})
        try:
            layout.set_working_copy("opproj", op)
            layout.set_working_copy("other", os.path.join(tmp, "other"))
            with operator(op):
                assert layout.link_rel(slice_, "opproj") == ".agent-fabric/memory/fabric-coordinator/x.md"
                assert layout.link_rel(slice_, "other") == \
                    f"{layout.FABRIC_LINK_PREFIX}/.agent-fabric/memory/fabric-coordinator/x.md"
        finally:
            layout.set_working_copy("opproj", None)
            layout.set_working_copy("other", None)


def case_lint_reads_role_files_only_the_operator_holds() -> None:
    """Lint over an engine that holds no role files, with this checkout as the
    operator: the identity slices and the locales' sources are read from the
    operator's tree (re-review of #125, P3 2). What stays is what an engine
    must hold itself: the prompt templates and the harness text."""
    import subprocess
    base = {k: v for k, v in os.environ.items() if k not in ("AGENT_FABRIC_ROOT", "AGENT_FABRIC_OPERATOR")}
    with tempfile.TemporaryDirectory() as engine:
        os.makedirs(os.path.join(engine, "identities"))
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "lint.py"), "--fabric", engine,
                            "--no-siblings"], capture_output=True, text=True, timeout=300,
                           env={**base, "AGENT_FABRIC_OPERATOR": ROOT})
        out = r.stdout + r.stderr
        assert "Traceback" not in out, out[-1500:]
        assert "identities/roles/" not in "".join(l for l in out.splitlines(keepends=True) if "does not exist" in l
                                                  and "its source identities/roles/" in l), out[-1500:]
        assert "identities/prompt/header.md: missing" in out, out[-1500:]   # the control: the engine's own gap


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
