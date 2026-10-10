#!/usr/bin/env python3
"""Tests for tools/fabric/roots.py: the two roots and every data helper under
the operator root. (A Node twin, runtime/control/roots.mjs, was held to the
same matrix of environments until the Node control plane was deleted.)"""
from __future__ import annotations

import os
import sys

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import roots  # noqa: E402

J = os.path.join
E, O = "/e", "/o"

# (helper, python call, the path under the operator root)
HELPERS = (
    ("roleCatalog", lambda **k: roots.role_catalog(**k), "identities/roles/catalog.json"),
    ("rolesDir", lambda **k: roots.roles_dir(**k), "identities/roles"),
    ("roleDir", lambda **k: roots.role_dir("python-dev", **k), "identities/roles/python-dev"),
    ("localeDir", lambda **k: roots.locale_dir("language-culture", "it", **k), "identities/roles/language-culture/locale/it"),
    ("keysDir", lambda **k: roots.keys_dir(**k), "identities/keys"),
    ("recoveryKey", lambda **k: roots.recovery_key(**k), "identities/recovery.asc"),
    ("projectsRegistry", lambda **k: roots.projects_registry(**k), "projects/registry.json"),
    ("projectsDir", lambda **k: roots.projects_dir(**k), "projects"),
    ("projectIntegration", lambda **k: roots.project_integration("gzapp", "gh", "arm.json", **k), "projects/gzapp/integration/gh/arm.json"),
    ("hostsRegistry", lambda **k: roots.hosts_registry(**k), "runtime/hosts/registry.json"),
    ("policy", lambda **k: roots.policy("hygiene.json", **k), "policies/hygiene.json"),
    ("policiesDir", lambda **k: roots.policies_dir(**k), "policies"),
    ("routingProfiles", lambda **k: roots.routing_profiles(**k), "routing/profiles.json"),
    ("routingPolicy", lambda **k: roots.routing_policy("review-grade.json", **k), "routing/policies/review-grade.json"),
    ("memoryDir", lambda **k: roots.memory_dir("domains", **k), "memory/domains"),
    ("adrDir", lambda **k: roots.adr_dir(**k), "docs/adr"),
)

ENVS = (
    {},
    {"AGENT_FABRIC_ROOT": E},
    {"AGENT_FABRIC_ROOT": ""},
    {"AGENT_FABRIC_OPERATOR": O},
    {"AGENT_FABRIC_OPERATOR": ""},
    {"AGENT_FABRIC_ROOT": E, "AGENT_FABRIC_OPERATOR": O},
    {"AGENT_FABRIC_ROOT": E, "AGENT_FABRIC_OPERATOR": ""},
    {"AGENT_FABRIC_ROOT": "", "AGENT_FABRIC_OPERATOR": O},
    {"AGENT_FABRIC_HOSTS_REGISTRY": "/h/reg.json", "AGENT_FABRIC_OPERATOR": O},
    {"AGENT_FABRIC_HOSTS_REGISTRY": ""},
)


def case_engine_root_is_the_checkout_unless_exported() -> None:
    assert roots.code_root() == ROOT
    assert roots.engine_root({}) == ROOT
    assert roots.engine_root({"AGENT_FABRIC_ROOT": E}) == E
    assert roots.engine_root({"AGENT_FABRIC_ROOT": ""}) == ROOT
    assert roots.engine_root({"AGENT_FABRIC_ROOT": ""}, empty_is_set=True) == ""


def case_operator_root_is_the_engine_root_unless_exported() -> None:
    assert roots.operator_root({}) == ROOT
    assert roots.operator_root({"AGENT_FABRIC_ROOT": E}) == E
    assert roots.operator_root({"AGENT_FABRIC_OPERATOR": O}) == O
    assert roots.operator_root({"AGENT_FABRIC_OPERATOR": O, "AGENT_FABRIC_ROOT": E}) == O
    assert roots.operator_root({"AGENT_FABRIC_OPERATOR": "", "AGENT_FABRIC_ROOT": E}) == E
    assert roots.operator_root({"AGENT_FABRIC_ROOT": ""}, empty_is_set=True) == ""


def case_every_helper_is_under_the_operator_root() -> None:
    for name, call, rel in HELPERS:
        if name == "hostsRegistry":
            continue
        assert call(environ={"AGENT_FABRIC_OPERATOR": O, "AGENT_FABRIC_ROOT": E}) == J(O, rel), name
        assert call(environ={"AGENT_FABRIC_ROOT": E}) == J(E, rel), name
        assert call(environ={}) == J(ROOT, rel), name


def case_an_explicit_root_wins_over_both_roots() -> None:
    env = {"AGENT_FABRIC_OPERATOR": O, "AGENT_FABRIC_ROOT": E}
    for name, call, rel in HELPERS:
        if name == "hostsRegistry":
            continue
        assert call(root="/x", environ=env) == J("/x", rel), name


def case_an_engine_tree_handed_in_stands_for_the_environments_engine_root() -> None:
    assert roots.policy("x.json", engine="/g", environ={"AGENT_FABRIC_ROOT": E}) == "/g/policies/x.json"
    assert roots.policy("x.json", engine="/g", environ={"AGENT_FABRIC_OPERATOR": O}) == "/o/policies/x.json"
    assert roots.policy("x.json", engine="/g", root="/x", environ={"AGENT_FABRIC_OPERATOR": O}) == "/x/policies/x.json"
    assert roots.hosts_registry(engine="/g", environ={}) == "/g/runtime/hosts/registry.json"
    assert roots.operator_root({}, engine="/g") == "/g"


def case_the_hosts_registry_override_outranks_the_tree() -> None:
    assert roots.hosts_registry(environ={"AGENT_FABRIC_HOSTS_REGISTRY": "/h/r.json", "AGENT_FABRIC_OPERATOR": O}) == "/h/r.json"
    assert roots.hosts_registry(root="/x", environ={"AGENT_FABRIC_HOSTS_REGISTRY": "/h/r.json"}) == "/h/r.json"
    assert roots.hosts_registry(environ={"AGENT_FABRIC_HOSTS_REGISTRY": "", "AGENT_FABRIC_OPERATOR": O}) == J(O, "runtime/hosts/registry.json")
    assert roots.hosts_registry(environ={"AGENT_FABRIC_HOSTS_REGISTRY": ""}, empty_is_set=True) == ""


def case_the_environment_read_is_the_one_given_not_the_process_s() -> None:
    saved = os.environ.get("AGENT_FABRIC_OPERATOR")
    os.environ["AGENT_FABRIC_OPERATOR"] = "/process"
    try:
        assert roots.operator_root({}) == ROOT
        assert roots.policy("x.json", environ={}) == J(ROOT, "policies", "x.json")
        assert roots.policy("x.json") == "/process/policies/x.json"
    finally:
        if saved is None:
            del os.environ["AGENT_FABRIC_OPERATOR"]
        else:
            os.environ["AGENT_FABRIC_OPERATOR"] = saved


def case_live_checks_dir_is_python_only_and_follows_the_operator_root() -> None:
    assert roots.live_checks_dir(environ={"AGENT_FABRIC_OPERATOR": O, "AGENT_FABRIC_ROOT": E}) == J(O, "docs", "live-checks")
    assert roots.live_checks_dir(environ={"AGENT_FABRIC_ROOT": E}) == J(E, "docs", "live-checks")
    assert roots.live_checks_dir(root="/x", environ={"AGENT_FABRIC_OPERATOR": O}) == J("/x", "docs", "live-checks")
    assert roots.live_checks_dir(environ={"AGENT_FABRIC_OPERATOR": O}, engine="/g") == J(O, "docs", "live-checks")
    assert roots.live_checks_dir(environ={}, engine="/g") == J("/g", "docs", "live-checks")


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
