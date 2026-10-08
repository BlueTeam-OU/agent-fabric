#!/usr/bin/env python3
"""Tests for tools/fabric/roots.py and its Node twin runtime/control/roots.mjs:
the two roots, every data helper under the operator root, and the twin
answering as the Python does on one matrix of environments."""
from __future__ import annotations

import json
import os
import subprocess
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


def case_the_node_twin_answers_as_the_python_does() -> None:
    names = [n for n, _, _ in HELPERS]
    script = """
import * as r from './runtime/control/roots.mjs';
const envs = JSON.parse(process.argv[1]);
const calls = {
  roleCatalog: e => r.roleCatalog({ env: e }), rolesDir: e => r.rolesDir({ env: e }),
  roleDir: e => r.roleDir('python-dev', { env: e }), localeDir: e => r.localeDir('language-culture', 'it', { env: e }),
  keysDir: e => r.keysDir({ env: e }), recoveryKey: e => r.recoveryKey({ env: e }),
  projectsRegistry: e => r.projectsRegistry({ env: e }), projectsDir: e => r.projectsDir({ env: e }),
  projectIntegration: e => r.projectIntegration('gzapp', ['gh', 'arm.json'], { env: e }),
  hostsRegistry: e => r.hostsRegistry({ env: e }), policy: e => r.policy('hygiene.json', { env: e }),
  policiesDir: e => r.policiesDir({ env: e }), routingProfiles: e => r.routingProfiles({ env: e }),
  routingPolicy: e => r.routingPolicy('review-grade.json', { env: e }), memoryDir: e => r.memoryDir(['domains'], { env: e }),
  adrDir: e => r.adrDir({ env: e }),
};
console.log(JSON.stringify(envs.map(e => ({
  engine: r.engineRoot({ env: e }), engineSet: r.engineRoot({ env: e, emptyIsSet: true }),
  operator: r.operatorRoot({ env: e }), operatorSet: r.operatorRoot({ env: e, emptyIsSet: true }),
  ...Object.fromEntries(Object.entries(calls).map(([k, f]) => [k, f(e)])),
  hostsSet: r.hostsRegistry({ env: e, emptyIsSet: true }),
  explicit: r.policy('p.json', { env: e, root: '/x' }), handed: r.policy('p.json', { env: e, engine: '/g' }),
}))));
"""
    done = subprocess.run(["node", "--input-type=module", "-e", script, json.dumps(ENVS)], cwd=ROOT,
                          capture_output=True, text=True, timeout=60, check=False, env={"PATH": os.environ["PATH"]})
    assert done.returncode == 0, done.stderr
    got = json.loads(done.stdout)
    assert len(got) == len(ENVS)
    for env, node in zip(ENVS, got):
        want = {
            "engine": roots.engine_root(env), "engineSet": roots.engine_root(env, empty_is_set=True),
            "operator": roots.operator_root(env), "operatorSet": roots.operator_root(env, empty_is_set=True),
            "explicit": roots.policy("p.json", root="/x", environ=env),
            "hostsSet": roots.hosts_registry(environ=env, empty_is_set=True),
            "handed": roots.policy("p.json", engine="/g", environ=env),
        }
        for n, call, _ in HELPERS:
            want[n] = call(environ=env)
        assert node == want, (env, {k: (node[k], want[k]) for k in want if node[k] != want[k]})
    assert set(names) <= set(got[0])


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
