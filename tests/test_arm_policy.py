#!/usr/bin/env python3
"""tools/fabric/github/arm_policy.py (arming policy, steps A and C): the schema's document and its validation, the
two layers and their merge, the fetch of a repository's file from its client's settings repository (and what an
absent file, an unreadable one and a bad one each mean), the order of specificity of threshold(), render() against
GitHub's ruleset as agent-fabric has it, and arm.py's and pr_gate.py's rules reading their numbers and modes through
it. The count rule at the default numbers is test_arm_cli's, and fabric-repo-policy is test_repo_policy's. No
network: the contents API is a function that records what it was asked; arm.py runs in process with its calls to
gh, the readers and the settings comparison replaced."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
from github import arm, arm_policy, pr_gate, repo_policy  # noqa: E402
from lint_rules import schema as lint_schema  # noqa: E402

RULESET = os.path.join(HERE, "tools", "fabric", "github-ruleset-main.json")
# What agent-fabric's policy file in its client's settings repository says, which is what github-ruleset-main.json is today.
FABRIC_POLICY = {"mode": "auto", "method": "merge", "required_checks": [{"context": "ci-ok", "app": "github-actions"}], "signatures": True,
                 "commits": {"min": 1}, "github": {"ruleset": "main protection"}}
REGISTRY = {"projects": {"p": {"client": "c", "remotes": ["git@github.com:O/R.git", "https://github.com/O/R"]},
                         "q": {"client": "nobody", "remotes": ["https://github.com/o/q"]}, "n": {"remotes": ["https://github.com/o/n"]},
                         "b": {"client": "bare", "remotes": ["https://github.com/o/b"]}}}
CLIENTS = {"clients": {"c": {"settings_repo": "o/settings"}, "bare": {}}}


def contents(doc) -> dict:
    """The contents API's answer for a file holding `doc` (text, or JSON of it)."""
    text = doc if isinstance(doc, str) else json.dumps(doc)
    return {"type": "file", "encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


class Api:
    """A fake gh.api: answers by path, records every path it was asked, raises what it is told to."""

    def __init__(self, answer=None, error: gh.GhError | None = None, repo_error: gh.GhError | None = None):
        self.answer, self.error, self.repo_error, self.asked = answer, error, repo_error, []

    def __call__(self, path, **kw):
        self.asked.append(path)
        if path.count("/") == 2 and path.startswith("repos/"):     # the settings repository itself
            if self.repo_error:
                raise self.repo_error
            return {"full_name": path[len("repos/"):]}
        if self.error:
            raise self.error
        return self.answer


def ghe(status: int | None, reason: str = "x") -> gh.GhError:
    return gh.GhError("gh api GET x", reason, status=status)


class Scratch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="arm-policy-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        os.makedirs(os.path.join(self.dir, "policies"))
        os.makedirs(os.path.join(self.dir, "projects"))

    def fleet(self, doc) -> None:
        with open(os.path.join(self.dir, "policies", "arming.json"), "w") as fh:
            fh.write(doc if isinstance(doc, str) else json.dumps(doc))


class Document(unittest.TestCase):
    def test_the_default_is_the_behaviour_before_the_policy(self):
        d = arm_policy.default()
        self.assertEqual(d["commits"], {"min": 8, "advice_over": 16, "below_min": "owner-word", "roles": {}, "classes": {}})
        self.assertEqual((d["mode"], d["method"]), ("auto", "merge"))

    def test_a_partial_document_is_completed_from_the_default_and_the_default_is_not_changed(self):
        p = arm_policy.validate({"commits": {"min": 3}})
        self.assertEqual(p["commits"]["advice_over"], 16)
        self.assertEqual(arm_policy.DEFAULT["commits"]["min"], 8)

    def test_an_unknown_key_anywhere_it_is_checked_is_refused_not_ignored(self):
        for bad in ({"colour": 1}, {"commits": {"mn": 3}}, {"queue": {"x": 1}}, {"protect": {"force": True}}, {"github": {"x": "y"}},
                    {"bots": {"renovate": {}}}, {"bots": {"dependabot": {"arm": [], "x": 1}}}, {"commits": {"roles": {"web-dev": {"min": 2, "x": 1}}}},
                    {"commits": {"classes": {"docs": {"paths": "x", "min": 1, "x": 1}}}}, {"required_checks": [{"context": "a", "x": 1}]}):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate(bad)

    def test_the_schema_and_description_keys_are_for_the_reader(self):
        self.assertEqual(arm_policy.validate({"$schema": "x", "description": "y"}), arm_policy.default())

    def test_values_of_the_wrong_kind_or_range_are_refused(self):
        for bad in ({"mode": "fast"}, {"method": "ff"}, {"commits": {"min": 0}}, {"commits": {"min": True}}, {"commits": {"min": 2.5}},
                    {"commits": {"min": "8"}}, {"commits": {"min": 9, "advice_over": 8}}, {"commits": {"below_min": "nobody"}},
                    {"commits": {"roles": {"Web Dev": {"min": 2}}}}, {"commits": {"roles": {"web-dev": {"min": 0}}}},
                    {"commits": {"roles": {"web-dev": 2}}}, {"commits": {"roles": []}}, {"commits": []},
                    {"required_checks": [{"context": "a"}, {"context": "a"}]}, {"required_checks": [{"context": ""}]},
                    {"required_checks": "ci-ok"}, {"required_checks": ["ci-ok"]}, {"required_checks": [{"context": "a", "app": 15368}]},
                    {"required_checks": [{"context": "a", "app": "Github Actions"}]},
                    {"signatures": "yes"}, {"delete_branch_on_merge": 1}, {"protect": {"deletion": 1}}, {"protect": []},
                    {"github": {"ruleset": " "}}, {"github": {"branch": 3}},
                    {"queue": {"grouping": "any"}}, {"queue": {"build": 0}}, {"queue": {"merge_min": 9, "merge_max": 2}},
                    {"bots": {"dependabot": {"arm": ["huge"]}}}, {"bots": {"dependabot": {"arm": ["patch", "patch"]}}},
                    {"bots": {"dependabot": {"ecosystems": ["pip"]}}}, 7, [], "x", None):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate(bad)

    def test_every_mode_and_method_the_schema_allows_is_allowed(self):
        for mode in ("queue", "auto", "direct", "owner-only"):
            arm_policy.validate({"mode": mode})
        for method in ("merge", "squash", "rebase"):
            arm_policy.validate({"method": method})
        arm_policy.validate({"commits": {"below_min": "refuse"}, "bots": {"dependabot": {"arm": ["patch", "minor"], "ecosystems": ["pip"]}},
                             "queue": {"grouping": "headgreen", "build": 3}, "github": {"ruleset": "r", "branch": "main"}})

    def test_the_older_class_form_is_a_class_with_a_minimum_of_one_and_names_may_have_spaces(self):
        p = arm_policy.validate({"commits": {"classes": {"Single-Check Tooling": r"^tools/", "docs": {"paths": r"\.md$", "min": 3}}}})
        self.assertEqual(p["commits"]["classes"], {"single-check tooling": {"paths": "^tools/", "min": 1}, "docs": {"paths": r"\.md$", "min": 3}})

    def test_a_class_that_is_not_one_is_refused(self):
        for bad in ({"a": {"paths": "("}}, {"a": {"paths": 3}}, {"a": {"min": 2}}, {"a": {"paths": "x", "min": 0}}, {"a": 3},
                    {"A": "x", "a": "y"}, {" a": "x"}, {"": "x"}):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate({"commits": {"classes": bad}})


class RealFiles(unittest.TestCase):
    """The operator's own files, read on purpose (tests/test_tests_read_fixtures.py names this file): the fleet
    default loads through arm_policy and is the built-in default, and the schema file and arm_policy.validate say the
    same of every document below, so the schema's test and the loader are one judgement."""

    SCHEMA = None

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(HERE, "identities", "schemas", "arming.schema.json"), encoding="utf-8") as fh:
            cls.SCHEMA = json.load(fh)

    def test_the_fleet_default_file_loads_through_arm_policy_and_is_the_built_in_default(self):
        self.assertEqual(arm_policy.fleet_policy(HERE), arm_policy.default())

    def test_the_schema_and_the_loader_agree_on_every_document(self):
        queue = {"mode": "queue", "method": "squash", "queue": {"grouping": "headgreen", "build": 5, "merge_max": 5, "merge_min": 1,
                                                                "wait_minutes": 2, "check_timeout_minutes": 60}}
        valid = [{}, FABRIC_POLICY, queue, {"commits": {"min": 4, "roles": {"devex-tooling": {"min": 2}}, "classes": {"docs": {"paths": "^docs/", "min": 1}}}},
                 {"bots": {"dependabot": {"arm": ["patch", "minor"], "ecosystems": ["npm_and_yarn", "pip"]}}},
                 {"github": {"ruleset": "r", "branch": "main"}}, {"mode": "owner-only"}, {"mode": "direct"}, {"commits": {"below_min": "refuse"}}]
        invalid = [{"mode": "auto", "autoo": True}, {"queue": {"depth": 3}}, {"mode": "squash"}, {"method": "fast-forward"},
                   {"commits": {"below_min": "warn"}}, {"commits": {"min": 0}}, {"commits": {"roles": {"devex-tooling": {"min": 0}}}},
                   {"commits": {"roles": {"Devex Tooling": {"min": 2}}}}, {"commits": {"classes": {"docs": {"min": 1}}}},
                   {"queue": {"grouping": "some"}}, {"queue": {"build": 2.5}}, {"required_checks": [{"app": "github-actions"}]},
                   {"bots": {"renovate": {"arm": ["patch"]}}}, {"bots": {"dependabot": {"arm": ["breaking"]}}}, {"signatures": "yes"},
                   {"protect": {"deletion": 1}}, {"required_checks": ["ci-ok"]}]
        with open(os.path.join(HERE, "policies", "arming.json"), encoding="utf-8") as fh:
            valid.append(json.load(fh))
        for doc in valid:
            self.assertEqual(lint_schema.validate_json(self.SCHEMA, doc, "x"), [], doc)
            arm_policy.validate(doc)
        for doc in invalid:
            self.assertTrue(lint_schema.validate_json(self.SCHEMA, doc, "x"), f"the schema accepts {doc}")
            with self.assertRaises(arm_policy.PolicyError, msg=repr(doc)):
                arm_policy.validate(doc)


class Layers(Scratch):
    def test_no_fleet_file_is_the_default_and_a_fleet_file_is_over_it(self):
        self.assertEqual(arm_policy.fleet_policy(self.dir), arm_policy.default())
        self.fleet({"commits": {"min": 5}, "method": "squash"})
        p = arm_policy.fleet_policy(self.dir)
        self.assertEqual((p["commits"]["min"], p["commits"]["advice_over"], p["method"]), (5, 16, "squash"))

    def test_a_fleet_file_that_is_not_a_policy_is_an_error_not_the_default(self):
        for bad in ("{not json", "[]", '{"colour": 1}', '{"commits": {"min": 0}}'):
            self.fleet(bad)
            with self.assertRaises(arm_policy.PolicyError, msg=bad):
                arm_policy.fleet_policy(self.dir)

    def test_objects_merge_recursively_and_scalars_and_lists_replace(self):
        self.fleet({"commits": {"roles": {"web-dev": {"min": 2}}, "min": 5}, "required_checks": [{"context": "a"}, {"context": "b"}]})
        api = Api(contents({"commits": {"roles": {"rust-dev": {"min": 3}}, "advice_over": 20}, "required_checks": [{"context": "c"}]}))
        p = arm_policy.load("O/R", root=self.dir, registry=REGISTRY, clients=CLIENTS, api=api)
        self.assertEqual(p["commits"]["roles"], {"web-dev": {"min": 2}, "rust-dev": {"min": 3}})
        self.assertEqual(p["required_checks"], [{"context": "c"}])
        self.assertEqual({k: p["commits"][k] for k in ("min", "advice_over")}, {"min": 5, "advice_over": 20})


class Client(unittest.TestCase):
    def test_the_settings_repository_is_the_clients_of_the_project_whose_remote_is_the_repository(self):
        for repo in ("O/R", "o/r", "O/r"):
            self.assertEqual(arm_policy.settings_repo_of(REGISTRY, CLIENTS, repo), "o/settings", repo)

    def test_a_repository_that_is_no_registered_projects_is_none_and_the_fleet_policy_applies(self):
        self.assertIsNone(arm_policy.settings_repo_of(REGISTRY, CLIENTS, "x/unknown"))

    def test_a_registered_project_with_no_client_an_unknown_client_or_no_settings_repo_fails_loudly(self):
        for repo, words in (("o/n", "names no client"), ("o/q", "has no client 'nobody'"), ("o/b", "has no settings_repo")):
            with self.assertRaises(arm_policy.PolicyError, msg=repo) as cm:
                arm_policy.settings_repo_of(REGISTRY, CLIENTS, repo)
            self.assertIn(words, str(cm.exception))
            self.assertIn(repo, str(cm.exception))

    def test_a_settings_repository_that_is_not_a_name_is_an_error(self):
        for bad in ("x", "a/b/c", 3, ["a/b"], "", "../x"):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.settings_repo_of(REGISTRY, {"clients": {"c": {"settings_repo": bad}}}, "O/R")

    def test_a_registry_without_projects_is_unavailable(self):
        with self.assertRaises(arm_policy.PolicyUnavailable):
            arm_policy.settings_repo_of({}, CLIENTS, "O/R")


class Load(Scratch):
    def load(self, api, repo="O/R", registry=None, clients=None, cache=None):
        return arm_policy.load(repo, root=self.dir, registry=REGISTRY if registry is None else registry,
                               clients=CLIENTS if clients is None else clients, api=api, cache=cache)

    def test_a_repository_that_is_no_registered_projects_is_the_fleet_policy_and_no_call_is_made(self):
        api = Api(error=ghe(500))
        self.assertEqual(self.load(api, repo="x/unknown"), arm_policy.default())
        self.assertEqual(api.asked, [])

    def test_a_registered_project_whose_client_has_no_settings_repository_is_an_error_not_the_fleet_policy(self):
        api = Api(contents({}))
        with self.assertRaises(arm_policy.PolicyError):
            self.load(api, repo="o/b")
        self.assertEqual(api.asked, [])

    def test_no_repository_is_the_fleet_policy(self):
        self.assertEqual(arm_policy.load(None, root=self.dir, registry=REGISTRY, clients=CLIENTS, api=Api(error=ghe(500))), arm_policy.default())

    def test_the_file_is_asked_for_by_the_repository_name_from_the_default_branch_never_a_ref(self):
        api = Api(contents({"commits": {"min": 2}}))
        p = self.load(api)
        self.assertEqual(api.asked, ["repos/o/settings/contents/repos/R.json"])
        self.assertEqual(p["commits"]["min"], 2)

    def test_no_file_for_the_repository_is_the_fleet_policy_when_the_settings_repository_answers(self):
        api = Api(error=ghe(404, "Not Found"))
        self.assertEqual(self.load(api), arm_policy.default())
        self.assertEqual(api.asked, ["repos/o/settings/contents/repos/R.json", "repos/o/settings"])

    def test_a_404_with_the_settings_repository_unreadable_is_not_an_absence(self):
        for e in (ghe(404, "Not Found"), ghe(403), ghe(None, "i/o timeout")):
            with self.assertRaises(arm_policy.PolicyUnavailable, msg=repr(e.status)):
                self.load(Api(error=ghe(404, "Not Found"), repo_error=e))

    def test_a_failure_that_is_not_an_absence_is_unavailable_never_the_default(self):
        for e in (ghe(500), ghe(403), ghe(401), ghe(None, "i/o timeout"), ghe(422)):
            with self.assertRaises(arm_policy.PolicyUnavailable, msg=repr(e.status)):
                self.load(Api(error=e))

    def test_a_file_that_is_not_a_policy_file_is_unavailable_or_an_error_never_the_default(self):
        for answer in (None, [], {"type": "dir"}, {"type": "file", "encoding": "none", "content": ""}, contents("{not json"),
                       contents("[]"), contents("\xff"), {"type": "file", "encoding": "base64", "content": "!!!"},
                       {"type": "file", "encoding": "base64"}):
            with self.assertRaises(arm_policy.PolicyUnavailable, msg=repr(answer)):
                self.load(Api(answer))
        for doc in ({"colour": 1}, {"commits": {"min": 0}}):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(doc)):
                self.load(Api(contents(doc)))

    def test_the_error_names_the_file(self):
        with self.assertRaises(arm_policy.PolicyError) as cm:
            self.load(Api(contents({"commits": {"min": 0}})))
        self.assertIn("o/settings repos/R.json", str(cm.exception))

    def test_a_repository_name_that_could_walk_the_path_is_refused_before_any_call(self):
        api = Api(contents({}))
        for bad in ("../x", "o/r/../../x", "o/r?ref=evil", "o", "o/r r"):
            with self.assertRaises(arm_policy.PolicyUnavailable, msg=bad):
                arm_policy.fetch_repo_policy("o/settings", bad, api)
        self.assertEqual(api.asked, [])

    def test_the_cache_makes_one_call_per_run_and_hands_out_copies(self):
        api, cache = Api(contents({"commits": {"min": 2}})), {}
        a = self.load(api, cache=cache)
        a["commits"]["min"] = 99
        b = self.load(api, cache=cache)
        b["commits"]["min"] = 77
        c = self.load(api, cache=cache)
        self.assertEqual((len(api.asked), c["commits"]["min"]), (1, 2))
        self.load(api)
        self.assertEqual(len(api.asked), 2, "no cache, no reuse: nothing is kept between runs")

    def test_the_registry_and_the_clients_are_read_when_not_given_and_their_failure_is_unavailable(self):
        import workingcopy
        with mock.patch.object(workingcopy, "load_registry", side_effect=OSError("gone")):
            with self.assertRaises(arm_policy.PolicyUnavailable):
                arm_policy.load("O/R", root=self.dir, clients=CLIENTS, api=Api(contents({})))
        with open(os.path.join(self.dir, "projects", "clients.json"), "w") as fh:
            json.dump(CLIENTS, fh)
        with mock.patch.object(workingcopy, "load_registry", return_value=REGISTRY):
            self.assertEqual(arm_policy.load("O/R", root=self.dir, api=Api(contents({"commits": {"min": 4}})))["commits"]["min"], 4)


class Threshold(unittest.TestCase):
    P = arm_policy.validate({"commits": {"min": 9, "roles": {"web-dev": {"min": 4}, "rust-dev": {"min": 12}},
                                         "classes": {"docs": {"paths": r"\.md$", "min": 2}, "tooling": r"^tools/"}}})

    def test_the_repositorys_minimum_when_nothing_more_specific_applies(self):
        self.assertEqual(arm_policy.threshold(self.P, None, "", False), 9)
        self.assertEqual(arm_policy.threshold(self.P, "python-dev", "", False), 9)

    def test_the_role_over_the_repository_and_the_class_over_the_role(self):
        self.assertEqual(arm_policy.threshold(self.P, "web-dev", "", False), 4)
        self.assertEqual(arm_policy.threshold(self.P, "rust-dev", "", False), 12)
        self.assertEqual(arm_policy.threshold(self.P, "rust-dev", "docs", False), 2)
        self.assertEqual(arm_policy.threshold(self.P, "web-dev", "tooling", False), 1, "the older form is a minimum of one")

    def test_a_boundary_not_waived_is_the_repositorys_minimum_or_the_floor_whatever_the_role_or_the_class(self):
        for role, cls in ((None, ""), ("web-dev", ""), ("rust-dev", ""), ("web-dev", "docs"), ("rust-dev", "tooling")):
            self.assertEqual(arm_policy.threshold(self.P, role, cls, True), 9, (role, cls))

    def test_the_boundary_floor_holds_when_the_repository_sets_a_small_minimum(self):
        small = arm_policy.validate({"commits": {"min": 1, "roles": {"web-dev": {"min": 1}}}})
        self.assertEqual(arm_policy.BOUNDARY_FLOOR, 8)
        self.assertEqual(arm_policy.threshold(small, "web-dev", "", True), 8)
        self.assertEqual(arm_policy.threshold(small, None, "", False), 1)

    def test_a_class_the_policy_does_not_have_is_an_error_not_the_repositorys_minimum(self):
        with self.assertRaises(arm_policy.PolicyError):
            arm_policy.threshold(self.P, None, "nothing", False)

    def test_classes_from_arm_json_are_added_under_the_policys_own(self):
        p = arm_policy.with_classes(self.P, {"tooling": "^other/", "ddl": "^db/"})
        self.assertEqual(p["commits"]["classes"]["tooling"], {"paths": "^tools/", "min": 1})
        self.assertEqual(p["commits"]["classes"]["ddl"], {"paths": "^db/", "min": 1})
        self.assertNotIn("ddl", self.P["commits"]["classes"], "the policy given is not changed")


class Render(unittest.TestCase):
    def test_agent_fabrics_policy_renders_the_ruleset_it_has(self):
        with open(RULESET, encoding="utf-8") as fh:
            want = json.load(fh)
        self.assertEqual(arm_policy.render(arm_policy.validate(FABRIC_POLICY))["ruleset"], want)

    def test_the_repository_fields_follow_the_method_and_the_mode(self):
        for method, field in (("merge", "allow_merge_commit"), ("squash", "allow_squash_merge"), ("rebase", "allow_rebase_merge")):
            r = arm_policy.render(arm_policy.validate({"method": method, "delete_branch_on_merge": True}))
            self.assertEqual(r["repository"], {"allow_auto_merge": True, "delete_branch_on_merge": True,
                                               **{f: f == field for f in ("allow_merge_commit", "allow_squash_merge", "allow_rebase_merge")}})
            pull_request = next(x for x in r["ruleset"]["rules"] if x["type"] == "pull_request")
            self.assertEqual(pull_request["parameters"]["allowed_merge_methods"], [method])
        for mode, auto in (("auto", True), ("queue", True), ("owner-only", False), ("direct", False)):
            self.assertEqual(arm_policy.render(arm_policy.validate({"mode": mode}))["repository"]["allow_auto_merge"], auto, mode)

    def test_direct_has_no_server_side_rule_and_owner_only_keeps_the_ruleset(self):
        self.assertIsNone(arm_policy.render(arm_policy.validate({"mode": "direct"}))["ruleset"])
        self.assertIsNotNone(arm_policy.render(arm_policy.validate({"mode": "owner-only"}))["ruleset"])

    def test_a_queue_adds_the_merge_queue_rule_with_the_schemas_names_mapped_and_auto_does_not(self):
        queue = {"grouping": "headgreen", "build": 3, "merge_max": 4, "merge_min": 2, "wait_minutes": 10, "check_timeout_minutes": 30}
        rules = arm_policy.render(arm_policy.validate({"mode": "queue", "method": "squash", "queue": queue}))["ruleset"]["rules"]
        self.assertEqual([x["parameters"] for x in rules if x["type"] == "merge_queue"],
                         [{"merge_method": "SQUASH", "grouping_strategy": "HEADGREEN", "max_entries_to_build": 3, "max_entries_to_merge": 4,
                           "min_entries_to_merge": 2, "min_entries_to_merge_wait_minutes": 10, "check_response_timeout_minutes": 30}])
        defaults = arm_policy.render(arm_policy.validate({"mode": "queue"}))["ruleset"]["rules"]
        self.assertEqual(next(x for x in defaults if x["type"] == "merge_queue")["parameters"]["grouping_strategy"], "ALLGREEN")
        self.assertNotIn("merge_queue", [x["type"] for x in arm_policy.render(arm_policy.default())["ruleset"]["rules"]])

    def test_checks_apps_signatures_and_protection_are_each_a_rule_only_when_asked(self):
        types = lambda doc: [x["type"] for x in arm_policy.render(arm_policy.validate(doc))["ruleset"]["rules"]]  # noqa: E731
        self.assertEqual(types({}), ["deletion", "non_fast_forward", "pull_request", "required_signatures"])
        self.assertEqual(types({"protect": {"deletion": False, "force_push": False}, "signatures": False}), ["pull_request"])
        self.assertEqual(types({"protect": {"force_push": False}, "required_checks": [{"context": "a"}], "signatures": False}),
                         ["deletion", "pull_request", "required_status_checks"])
        rule = next(x for x in arm_policy.render(arm_policy.validate({"required_checks": [{"context": "a"}, {"context": "b"}]}))["ruleset"]["rules"]
                    if x["type"] == "required_status_checks")
        self.assertEqual(rule["parameters"]["required_status_checks"], [{"context": "a"}, {"context": "b"}], "no app: any, no integration id")

    def test_an_app_is_its_integration_id_and_one_not_known_is_an_error_unless_given(self):
        policy = arm_policy.validate({"required_checks": [{"context": "a", "app": "github-actions"}, {"context": "b", "app": "circleci"}]})
        with self.assertRaises(arm_policy.PolicyError):
            arm_policy.render(policy)
        rule = next(x for x in arm_policy.render(policy, {"circleci": 18001})["ruleset"]["rules"] if x["type"] == "required_status_checks")
        self.assertEqual(rule["parameters"]["required_status_checks"],
                         [{"context": "a", "integration_id": 15368}, {"context": "b", "integration_id": 18001}])

    def test_the_ruleset_is_named_and_aimed_at_the_default_branch_or_the_one_named(self):
        rs = arm_policy.render(arm_policy.validate({"github": {"ruleset": "protect"}}))["ruleset"]
        self.assertEqual((rs["name"], rs["conditions"]["ref_name"]["include"], rs["bypass_actors"], rs["enforcement"]),
                         ("protect", ["~DEFAULT_BRANCH"], [], "active"))
        rs = arm_policy.render(arm_policy.validate({"github": {"branch": "master"}}))["ruleset"]
        self.assertEqual(rs["conditions"]["ref_name"]["include"], ["refs/heads/master"])

    def test_a_policy_that_is_not_one_is_not_rendered(self):
        with self.assertRaises(arm_policy.PolicyError):
            arm_policy.render({"mode": "fast"})

    def test_render_does_not_change_the_policy_given(self):
        p = arm_policy.validate(FABRIC_POLICY)
        before = json.dumps(p, sort_keys=True)
        arm_policy.render(p)
        self.assertEqual(json.dumps(p, sort_keys=True), before)


class PrGate(unittest.TestCase):
    CLEAR = {"mergeable": "MERGEABLE", "checks": "green", "unresolved": "0", "armed": "no", "queue": "", "mstate": "CLEAN"}

    def v(self, work, policy=None):
        commits = {"work": work, "fix": 0, "merge": 0, "netted": 0, "fix_subjects": [], "netted_subjects": []}
        return pr_gate.verdict(1, "main", False, commits, self.CLEAR, "head reviewed", [], policy)

    def test_at_the_default_numbers_the_verdicts_are_the_ones_before(self):
        self.assertIn("ask the owner (7 work commits < 8)", self.v(7))
        self.assertIn("arm: post the basis (8 work commits", self.v(8))
        self.assertIn("arm: post the basis (16 work commits", self.v(16))
        self.assertIn("17 work commits, over 16", self.v(17))

    def test_the_numbers_are_the_policys(self):
        p = arm_policy.validate({"commits": {"min": 3, "advice_over": 5}})
        self.assertIn("ask the owner (2 work commits < 3)", self.v(2, p))
        self.assertIn("arm: post the basis (3 work commits", self.v(3, p))
        self.assertIn("6 work commits, over 5", self.v(6, p))

    def test_a_policy_that_could_not_be_read_is_said_and_no_number_is_assumed(self):
        text = self.v(9, "o/settings repos/R.json could not be read (HTTP 500)")
        self.assertIn("the arming policy cannot be read (o/settings repos/R.json could not be read (HTTP 500))", text)
        self.assertNotIn("arm: post", text)

    def test_owner_only_and_direct_are_not_armed_by_fabric_pr(self):
        for mode, words in (("owner-only", "only the owner merges"), ("direct", "nothing to arm")):
            text = self.v(20, arm_policy.validate({"mode": mode}))
            self.assertIn(words, text)
            self.assertNotIn("arm: post", text)


class PrGateRun(unittest.TestCase):
    """pr_gate.run() in process, with what it reads replaced: it loads the repository's policy and its verdict says
    the policy's numbers, or that the policy could not be read."""
    HEAD = "abcdef1234567890abcdef1234567890abcdef12"

    def rows(self, policy_load, work=5):
        pr = {"number": 7, "title": "t", "headRefName": "h/me/feat/x", "headRefOid": self.HEAD, "baseRefName": "main", "state": "OPEN",
              "isDraft": False, "body": ""}
        commits = {"work": work, "fix": 0, "merge": 0, "netted": 0, "fix_subjects": [], "netted_subjects": []}
        st = {"mergeable": "MERGEABLE", "checks": "green", "unresolved": "0", "armed": "no", "queue": "", "mstate": "CLEAN"}
        out = io.StringIO()
        with contextlib.ExitStack() as es:
            es.enter_context(mock.patch.object(pr_gate.shutil, "which", return_value="/bin/x"))
            es.enter_context(mock.patch.object(pr_gate.gh, "this_repo", return_value="O/R"))
            es.enter_context(mock.patch.object(pr_gate.gh, "run", return_value=json.dumps(pr)))
            es.enter_context(mock.patch.object(pr_gate, "session_prefix", return_value="h/me"))
            es.enter_context(mock.patch.object(pr_gate, "succeeds", return_value=True))
            es.enter_context(mock.patch.object(pr_gate, "review_reader", return_value=None))
            es.enter_context(mock.patch.object(pr_gate, "count_commits", return_value=commits))
            es.enter_context(mock.patch.object(pr_gate, "gate_state", return_value=st))
            es.enter_context(mock.patch.object(pr_gate, "review_of_head", return_value="head reviewed"))
            es.enter_context(mock.patch.object(pr_gate.arm_policy, "load", policy_load))
            es.enter_context(contextlib.redirect_stdout(out))
            self.assertEqual(pr_gate.run(["--json", "7"]), 0)
        return json.loads(out.getvalue())

    def test_the_verdict_says_the_numbers_of_the_policy_loaded_for_the_repository(self):
        asked = []

        def load(repo, **kw):
            asked.append(repo)
            return arm_policy.validate({"commits": {"min": 3, "advice_over": 4}})
        row = self.rows(load, work=5)[0]
        self.assertEqual(asked, ["O/R"])
        self.assertIn("5 work commits, over 4", row["verdict"])
        self.assertIn("arm: post the basis (5", self.rows(lambda r, **k: arm_policy.validate({"commits": {"min": 3, "advice_over": 9}}))[0]["verdict"])

    def test_the_default_is_the_verdict_before_the_policy(self):
        self.assertIn("ask the owner (5 work commits < 8)", self.rows(lambda r, **k: arm_policy.default())[0]["verdict"])

    def test_an_unreadable_policy_is_said_in_the_verdict_and_stops_nothing_else(self):
        def load(repo, **kw):
            raise arm_policy.PolicyUnavailable("o/settings repos/R.json could not be read (HTTP 500)")
        row = self.rows(load)[0]
        self.assertIn("the arming policy cannot be read (o/settings repos/R.json could not be read (HTTP 500))", row["verdict"])
        self.assertEqual((row["work_commits"], row["checks"]), (5, "green"))

        def bad(repo, **kw):
            raise arm_policy.PolicyError("o/settings repos/R.json: unknown key(s) colour")
        self.assertIn("unknown key(s) colour", self.rows(bad)[0]["verdict"])


class ArmRun(unittest.TestCase):
    """arm.arm() in process, with everything it reads replaced: the rules are the policy's."""
    HEAD = "abcdef1234567890abcdef1234567890abcdef12"

    def run_arm(self, policy, work, files=("docs/a.md",), basis="reviewed", body="", boundary_re=r"^policies/", classes=None,
                load_error=None, extra=(), load_fn=None, drift=(), drift_error=None, role_trailers=None, checks="green", live=None):
        pr = {"number": 7, "state": "OPEN", "isDraft": False, "headRefName": "h/me/feat/x", "headRefOid": self.HEAD, "body": body, "title": "t"}
        gate = [{"commits_known": True, "work_commits": work, "checks": checks}]
        review = {"blind": {"rows": [{"commit_sha8": self.HEAD[:8]}]}, "unresolved_threads": 0}
        commits = [{"parents": [{}, {}], "commit": {"message": "Merge branch main"}} if r == "MERGE" else
                   {"parents": [{}], "commit": {"message": "c" + (f"\n\nFabric-Role: {r}" if r else "")}} for r in (role_trailers or [None])]
        ran = []

        def reader(head, args, timeout=600):
            return (0, json.dumps(review if "review-status" in " ".join(head) else gate))

        def api(path, **kw):
            return commits if "/commits" in path else [{"filename": f} for f in files]

        def gh_run(args, **kw):
            ran.append(list(args))
            return json.dumps(pr)

        def check(repo, pol, api=None):
            if drift_error:
                raise repo_policy.Unreadable(drift_error)
            return list(drift)
        classes = {k: re.compile(v) for k, v in (classes or {}).items()}
        load = load_fn or (mock.Mock(side_effect=load_error) if load_error else mock.Mock(return_value=policy))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(arm.shutil, "which", return_value="/bin/gh"))
            st.enter_context(mock.patch.object(arm.gh, "run", gh_run))
            st.enter_context(mock.patch.object(arm.gh, "this_repo", return_value="O/R"))
            st.enter_context(mock.patch.object(arm.gh, "api", api))
            st.enter_context(mock.patch.object(arm.gh, "graphql", return_value={"repository": {"pullRequest": {
                "state": "OPEN", "headRefOid": self.HEAD, "autoMergeRequest": {"enabledAt": "x"}, "mergeQueueEntry": None, **(live or {})}}}))
            st.enter_context(mock.patch.object(arm.pr_gate, "session_prefix", return_value="h/me"))
            st.enter_context(mock.patch.object(arm, "config_path", return_value="x"))
            st.enter_context(mock.patch.object(arm, "load_config", return_value=(re.compile(boundary_re), None, classes, None)))
            st.enter_context(mock.patch.object(arm, "run_reader", side_effect=reader))
            st.enter_context(mock.patch.object(arm.arm_policy, "load", load))
            st.enter_context(mock.patch.object(arm.repo_policy, "check", check))
            st.enter_context(contextlib.redirect_stdout(out))
            st.enter_context(contextlib.redirect_stderr(err))
            try:
                rc = arm.arm(["7", "--basis", basis, *extra])
            except arm.Refused as e:
                rc = f"refused: {e}"
            except arm.Unanswered as e:
                rc = f"unanswered: {e}"
        self.ran = ran
        return rc, out.getvalue()

    def test_the_minimum_is_the_policys(self):
        p = arm_policy.validate({"commits": {"min": 3, "advice_over": 5}})
        rc, out = self.run_arm(p, 3, extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("count rule: 3 work commits — 3 or more, arms at the review gate", out)
        rc, _ = self.run_arm(p, 2)
        self.assertIn("under 3 arms only on the owner's word", str(rc))
        rc, out = self.run_arm(p, 2, basis="the owner's word", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("under 3, on the owner's word", out)

    def test_the_advice_threshold_is_the_policys(self):
        p = arm_policy.validate({"commits": {"min": 3, "advice_over": 5}})
        _, out = self.run_arm(p, 6, extra=("--dry-run",))
        self.assertIn("6 work commits — over 5: smaller batches next time", out)
        _, out = self.run_arm(p, 5, extra=("--dry-run",))
        self.assertNotIn("smaller batches", out)

    def test_below_min_refuse_is_a_refusal_the_owners_word_does_not_lift(self):
        p = arm_policy.validate({"commits": {"min": 3, "below_min": "refuse"}})
        for basis in ("reviewed", "the owner's word"):
            rc, _ = self.run_arm(p, 2, basis=basis)
            self.assertIn("refuses below the minimum", str(rc), basis)
        rc, out = self.run_arm(p, 3, extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_the_boundary_floor_is_not_lowered_by_a_small_repository_minimum(self):
        p = arm_policy.validate({"commits": {"min": 1, "advice_over": 20}})
        rc, _ = self.run_arm(p, 7, files=("policies/x.json",))
        self.assertIn("a security-boundary change under 8 arms only on the owner's word", str(rc))
        rc, out = self.run_arm(p, 8, files=("policies/x.json",), extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("Security boundary, armed on the count rule (8 or more work commits) without the owner's word.", out)

    def test_a_stated_class_arms_at_its_own_minimum_and_below_it_asks_for_the_word(self):
        p = arm_policy.validate({"commits": {"min": 8, "classes": {"docs": {"paths": r"\.md$", "min": 3}}}})
        body = "Class: docs"
        rc, out = self.run_arm(p, 3, body=body, classes={"docs": r"\.md$"}, extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        rc, _ = self.run_arm(p, 2, body=body, classes={"docs": r"\.md$"})
        self.assertIn("the class docs arms at 3 or more", str(rc))
        rc, out = self.run_arm(p, 2, body=body, classes={"docs": r"\.md$"}, basis="the owner's word", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_a_class_with_a_minimum_of_one_has_no_lower_bound_a_zero_work_pull_request_still_arms(self):
        for p in (arm_policy.default(), arm_policy.validate({"commits": {"classes": {"docs": {"paths": r"\.md$", "min": 1}}}})):
            rc, out = self.run_arm(p, 0, body="Class: docs", classes={"docs": r"\.md$"}, extra=("--dry-run",))
            self.assertEqual(rc, 0, out)
            self.assertIn("under 8, arms at the gate as docs", out)

    def test_a_boundary_change_gets_no_exemption_from_a_class_even_at_a_repository_minimum_of_one(self):
        p = arm_policy.validate({"commits": {"min": 1, "advice_over": 5, "classes": {"docs": {"paths": r"\.md$", "min": 1}}}})
        rc, _ = self.run_arm(p, 0, files=("policies/a.md",), body="Class: docs", classes={"docs": r"\.md$"})
        self.assertIn("a security-boundary change under 8 arms only on the owner's word", str(rc))
        rc, out = self.run_arm(p, 0, files=("policies/a.md",), body="Class: docs", classes={"docs": r"\.md$"}, basis="the owner's word",
                               extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_the_policys_class_is_applied_whole_its_regex_as_well_as_its_minimum(self):
        p = arm_policy.validate({"commits": {"classes": {"docs": {"paths": r"^docs/", "min": 3}}}})
        rc, _ = self.run_arm(p, 3, files=("src/x.py",), body="Class: docs", classes={"docs": r"."})
        self.assertIn("the changed files are not that class", str(rc))
        rc, out = self.run_arm(p, 3, files=("docs/x.md",), body="Class: docs", classes={"docs": r"."}, extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_a_class_only_the_policy_has_can_be_stated(self):
        p = arm_policy.validate({"commits": {"classes": {"web": {"paths": r"^web/", "min": 2}}}})
        rc, out = self.run_arm(p, 2, files=("web/a.ts",), body="Class: web", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("class stated and confirmed by the files: web", out)
        rc, _ = self.run_arm(p, 1, files=("web/a.ts",), body="Class: web")
        self.assertIn("the class web arms at 2 or more", str(rc))

    def test_a_class_above_the_repositorys_minimum_is_said_as_the_owners_word_not_as_the_gate(self):
        p = arm_policy.validate({"commits": {"min": 8, "classes": {"big": {"paths": r"^x/", "min": 10}}}})
        rc, out = self.run_arm(p, 9, files=("x/a",), body="Class: big", basis="the owner's word", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("count rule: 9 work commits — under 10, on the owner's word", out)
        self.assertNotIn("arms at the review gate", out)

    def test_the_authors_role_minimum_applies_when_every_commit_is_stamped_with_it(self):
        p = arm_policy.validate({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}}}})
        rc, out = self.run_arm(p, 2, role_trailers=["web-dev", "web-dev"], extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        rc, _ = self.run_arm(p, 1, role_trailers=["web-dev"])
        self.assertIn("under 2 arms only on the owner's word", str(rc))

    def test_a_merge_commit_has_no_role_of_its_own_and_does_not_hide_the_authors(self):
        p = arm_policy.validate({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}}}})
        rc, out = self.run_arm(p, 2, role_trailers=["web-dev", "MERGE", "web-dev"], extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_no_role_several_roles_or_an_unstamped_commit_is_the_repositorys_minimum(self):
        p = arm_policy.validate({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}, "rust-dev": {"min": 2}}}})
        for trailers in (None, ["web-dev", "rust-dev"], ["web-dev", None], ["unknown-role"]):
            rc, _ = self.run_arm(p, 2, role_trailers=trailers)
            self.assertIn("under 8 arms only on the owner's word", str(rc), trailers)

    def test_a_role_only_lowers_a_non_boundary_pull_request(self):
        p = arm_policy.validate({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}}}})
        rc, _ = self.run_arm(p, 2, files=("policies/x.json",), role_trailers=["web-dev"])
        self.assertIn("a security-boundary change under 8", str(rc))

    def test_owner_only_and_direct_are_refused_before_anything_else_is_read(self):
        for mode, words in (("owner-only", "owner-only"), ("direct", "direct")):
            rc, _ = self.run_arm(arm_policy.validate({"mode": mode}), 20, basis="the owner's word")
            self.assertIn(words, str(rc))
            self.assertTrue(str(rc).startswith("refused"), rc)

    def test_the_merge_command_uses_the_policys_method(self):
        for method in ("merge", "squash", "rebase"):
            _, out = self.run_arm(arm_policy.validate({"method": method, "commits": {"min": 1}}), 3, extra=("--dry-run",))
            self.assertIn(f"gh pr merge 7 --{method} --auto --match-head-commit", out)
            self.run_arm(arm_policy.validate({"method": method, "commits": {"min": 1}}), 3)
            self.assertIn(["pr", "merge", "7", f"--{method}", "--auto", "--match-head-commit", self.HEAD], self.ran)

    def test_a_drift_that_bears_on_how_the_merge_is_held_refuses_and_names_it(self):
        p = arm_policy.validate({"commits": {"min": 1}})
        rc, _ = self.run_arm(p, 3, drift=["ruleset 'x' is missing"])
        self.assertIn("differ from its arming policy — ruleset 'x' is missing", str(rc))
        self.assertTrue(str(rc).startswith("refused"), rc)
        self.assertFalse([c for c in self.ran if c[:2] == ["pr", "merge"]])

    def test_an_advisory_drift_is_said_and_does_not_refuse(self):
        p = arm_policy.validate({"commits": {"min": 1}})
        rc, out = self.run_arm(p, 3, drift=["repository allow_squash_merge is True, the policy wants False (advisory)"], extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("arming policy, advisory: repository allow_squash_merge is True, the policy wants False", out)

    def test_settings_that_cannot_be_read_stop_the_arming_never_read_as_no_drift(self):
        rc, _ = self.run_arm(arm_policy.default(), 9, drift_error="HTTP 403")
        self.assertIn("unanswered: O/R's GitHub settings cannot be compared with its arming policy (HTTP 403)", str(rc))

    def test_a_repository_with_no_required_check_waits_for_green_checks_on_the_head(self):
        p = arm_policy.validate({"commits": {"min": 1}})
        for checks in ("red:ci", "pending:2", "none-yet", "?"):
            rc, _ = self.run_arm(p, 3, checks=checks)
            self.assertIn("has no required check", str(rc), checks)
            self.assertIn(checks, str(rc))
        rc, out = self.run_arm(p, 3, checks="green", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("no required check on this repository: every check on the head is green", out)

    def test_a_repository_with_a_required_check_leaves_the_checks_to_github(self):
        p = arm_policy.validate({"commits": {"min": 1}, "required_checks": [{"context": "ci-ok", "app": "github-actions"}]})
        rc, out = self.run_arm(p, 3, checks="pending:2", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_the_read_back_follows_the_mode(self):
        queued = {"mergeQueueEntry": {"position": 2}, "autoMergeRequest": None}
        _, out = self.run_arm(arm_policy.validate({"mode": "auto", "commits": {"min": 1}}), 3, live=queued)
        self.assertIn("note: the policy's mode is auto and GitHub put #7 in a merge queue", out)
        _, out = self.run_arm(arm_policy.validate({"mode": "queue", "commits": {"min": 1}}), 3, live=queued)
        self.assertNotIn("note: the policy's mode", out)
        self.assertIn("ARMED #7", out)

    def test_a_policy_that_cannot_be_read_stops_the_arming_and_is_never_the_default(self):
        for e in (arm_policy.PolicyUnavailable("o/settings repos/R.json could not be read (HTTP 500)"), arm_policy.PolicyError("bad")):
            rc, out = self.run_arm(None, 9, load_error=e)
            self.assertIn("unanswered: the arming policy for O/R cannot be read", str(rc))
            self.assertNotIn("count rule", out)

    def test_the_policy_is_asked_for_the_repository_the_pull_request_is_in_and_the_arm_json_classes_ride_with_it(self):
        loaded = []

        def spy(repo, **kw):
            loaded.append(repo)
            return arm_policy.default()
        real_with = arm_policy.with_classes
        seen = []
        with mock.patch.object(arm.arm_policy, "with_classes", lambda p, c: (seen.append(c), real_with(p, c))[1]):
            rc, out = self.run_arm(None, 9, classes={"docs": r"\.md$"}, load_fn=spy, extra=("--dry-run",))
        self.assertEqual((rc, loaded, seen), (0, ["O/R"], [{"docs": r"\.md$"}]), out)

    def test_an_author_whose_commits_cannot_be_listed_stops_the_arming(self):
        with mock.patch.object(arm.gh, "api", side_effect=gh.GhError("x", "boom")):
            with self.assertRaises(arm.Unanswered):
                arm.author_role("O/R", "7")


if __name__ == "__main__":
    unittest.main()
