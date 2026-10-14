#!/usr/bin/env python3
"""identities/schemas/arming.schema.json: the fleet default (policies/arming.json
itself, and DEFAULT below, the first fleet default written as a fixture)
and a repository's own policy validate against it, and a policy that
could not be applied (an unknown key, a value out of range) does not.
Judged by lint's validator both ways: jsonschema when present, and the
structural fallback the pinned interpreter runs (ADR-040); the real file
is also read by arm_policy.validate, the reader that applies it."""
from __future__ import annotations

import copy
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric", "github"))
from lint_rules import schema as lint_schema  # noqa: E402
import arm_policy  # noqa: E402

SCHEMA = json.load(open(os.path.join(ROOT, "identities", "schemas", "arming.schema.json"), encoding="utf-8"))

# The fleet default as first written, kept as a fixture; the committed policies/arming.json is loaded below.
DEFAULT = {
    "mode": "auto",
    "method": "merge",
    "required_checks": [],
    "signatures": True,
    "protect": {"deletion": True, "force_push": True},
    "delete_branch_on_merge": False,
    "commits": {"min": 8, "advice_over": 16, "below_min": "owner-word", "roles": {}, "classes": {}},
    "bots": {},
    "github": {"ruleset": "fabric arming policy"},
}

# A queue repository with per-role and per-class minimums and a bot rule,
# as gzapp's hand-made queue would be written.
QUEUE = {
    "mode": "queue",
    "method": "squash",
    "required_checks": [{"context": "ci-ok", "app": "github-actions"}],
    "queue": {"grouping": "allgreen", "build": 5, "merge_max": 5, "merge_min": 1,
              "wait_minutes": 2, "check_timeout_minutes": 60},
    "delete_branch_on_merge": True,
    "commits": {"min": 4, "roles": {"devex-tooling": {"min": 2}},
                "classes": {"docs": {"paths": "^docs/.*\\.md$", "min": 1}}},
    "bots": {"dependabot": {"arm": ["patch", "minor"], "ecosystems": ["npm_and_yarn", "pip"]}},
    "github": {"ruleset": "fabric arming policy", "branch": "main"},
}

failures = 0


def check(name: str, doc: object, valid: bool, needle: str = "") -> None:
    global failures
    for label, found in (("validate_json", lint_schema.validate_json(SCHEMA, doc, name)),
                         ("structural", lint_schema._structural_check(SCHEMA, doc, name))):
        ok = (not found) if valid else (bool(found) and needle in " ".join(found))
        print(f"  {'ok  ' if ok else 'FAIL'} {name} [{label}]" + ("" if ok else f": {found}"))
        failures += not ok


def mutated(base: dict, *path: str, value: object) -> dict:
    doc = copy.deepcopy(base)
    node = doc
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value
    return doc


check("the fleet default", DEFAULT, True)
check("a queue policy", QUEUE, True)
REAL = json.load(open(os.path.join(ROOT, "policies", "arming.json"), encoding="utf-8"))
check("the committed policies/arming.json", REAL, True)
try:
    applied = arm_policy.validate(REAL, "policies/arming.json")
    # The file equals the built-in default on today's keys, so a reader that ignored its document would answer the same
    # for the file itself: the control is a copy with one value moved, which only a reader that applies it reflects.
    moved = arm_policy.validate({**REAL, "commits": {**REAL["commits"], "min": REAL["commits"]["min"] + 1}}, "moved")
    ok = (applied["mode"] == REAL["mode"] and applied["commits"]["min"] == REAL["commits"]["min"]
          and moved["commits"]["min"] == REAL["commits"]["min"] + 1)
    detail = {"applied": applied, "moved": moved}
except arm_policy.PolicyError as e:
    ok, detail = False, e
print(f"  {'ok  ' if ok else 'FAIL'} the committed policies/arming.json [arm_policy.validate]" + ("" if ok else f": {detail}"))
failures += not ok
try:   # the control: the reader refuses what the schema refuses, so the line above can fail
    arm_policy.validate({**REAL, "autoo": True}, "policies/arming.json")
    ok = False
except arm_policy.PolicyError as e:
    ok = "autoo" in str(e)
print(f"  {'ok  ' if ok else 'FAIL'} arm_policy.validate refuses an unknown key in the committed policy")
failures += not ok
check("an empty policy (every field optional)", {}, True)
check("auto with an unknown key", {"mode": "auto", "autoo": True}, False, "autoo")
check("an unknown key nested", mutated(QUEUE, "queue", "depth", value=3), False, "depth")
check("an unknown mode", {"mode": "squash"}, False, "")
check("an unknown method", {"method": "fast-forward"}, False, "")
check("below_min is a word", mutated(DEFAULT, "commits", "below_min", value="warn"), False, "")
check("a zero minimum", mutated(DEFAULT, "commits", "min", value=0), False, "")
check("a role minimum of zero", mutated(DEFAULT, "commits", "roles", value={"devex-tooling": {"min": 0}}), False, "")
check("a role that is not a slug", mutated(DEFAULT, "commits", "roles", value={"Devex Tooling": {"min": 2}}), False, "")
check("a class with no paths", mutated(DEFAULT, "commits", "classes", value={"docs": {"min": 1}}), False, "paths")
check("an unknown grouping", mutated(QUEUE, "queue", "grouping", value="some"), False, "")
check("a fractional queue size", mutated(QUEUE, "queue", "build", value=2.5), False, "")
check("a check with no context", mutated(DEFAULT, "required_checks", value=[{"app": "github-actions"}]), False, "context")
check("an unknown bot", mutated(DEFAULT, "bots", "renovate", value={"arm": ["patch"]}), False, "renovate")
check("an unknown update type", mutated(DEFAULT, "bots", "dependabot", value={"arm": ["breaking"]}), False, "")
check("signatures as a word", mutated(DEFAULT, "signatures", value="yes"), False, "")

print(f"\n{'all passed' if not failures else f'{failures} failed'}")
sys.exit(1 if failures else 0)
