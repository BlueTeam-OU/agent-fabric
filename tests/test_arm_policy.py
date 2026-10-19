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
from github import arm, arm_policy, pr_gate, repo_policy, repo_settings  # noqa: E402
from lint_rules import schema as lint_schema  # noqa: E402

RULESET = os.path.join(HERE, "tools", "fabric", "github-ruleset-main.json")
# What agent-fabric's policy file in its client's settings repository says, which is what github-ruleset-main.json is today.
FABRIC_POLICY = {"mode": "auto", "method": "merge", "required_checks": [{"context": "ci-ok", "app": "github-actions"}], "signatures": True,
                 "commits": {"min": 1}, "github": {"ruleset": "main protection"}}
REGISTRY = {"projects": {"p": {"client": "c", "remotes": ["git@github.com:O/R.git", "https://github.com/O/R"]},
                         "q": {"client": "nobody", "remotes": ["https://github.com/o/q"]}, "n": {"remotes": ["https://github.com/o/n"]},
                         "b": {"client": "bare", "remotes": ["https://github.com/o/b"]}}}
CLIENTS = {"clients": {"c": {"settings_repo": "o/settings"}, "bare": {}}}


def claude_only(doc: dict | None = None) -> dict:
    """`doc` over the fleet default, requiring the review class's review alone and no additional engine. ArmRun's
    fixture simulates exactly that one review of the head, and its cases are about the counts and the gates; the
    engines' cases name theirs."""
    return arm_policy.validate({"reviews": ["claude"], "boundary_reviews": ["claude"], "additional_reviews": [], **(doc or {})})


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
        self.assertEqual(d["commits"], {"min": 8, "advice_over": 16, "boundary_min": 8, "below_min": "owner-word", "roles": {}, "classes": {}})
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

    def test_the_description_key_is_for_the_reader(self):
        self.assertEqual(arm_policy.validate({"description": "y"}), arm_policy.default())

    def test_values_of_the_wrong_kind_or_range_are_refused(self):
        for bad in ({"mode": "fast"}, {"method": "ff"}, {"commits": {"min": 0}}, {"commits": {"min": True}}, {"commits": {"min": 2.5}},
                    {"commits": {"min": "8"}}, {"commits": {"below_min": "nobody"}},
                    {"commits": {"roles": {"Web Dev": {"min": 2}}}}, {"commits": {"roles": {"web-dev": {"min": 0}}}},
                    {"commits": {"roles": {"web-dev": 2}}}, {"commits": {"roles": []}}, {"commits": []},
                    {"required_checks": [{"context": "a"}, {"context": "a"}]}, {"required_checks": [{"context": ""}]},
                    {"required_checks": "ci-ok"}, {"required_checks": ["ci-ok"]}, {"required_checks": [{"context": "a", "app": 15368}]},
                    {"required_checks": [{"context": "a", "app": ""}]},
                    {"signatures": "yes"}, {"delete_branch_on_merge": 1}, {"protect": {"deletion": 1}}, {"protect": []},
                    {"github": {"ruleset": ""}}, {"github": {"branch": 3}},
                    {"queue": {"grouping": "any"}}, {"queue": {"build": 0}},
                    {"bots": {"dependabot": {"arm": ["huge"]}}}, {"bots": {"dependabot": {"arm": ["patch", "patch"]}}},
                    {"bots": {"dependabot": {"ecosystems": ["pip"]}}}, 7, [], "x", None):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate(bad)

    def test_the_boundary_authority_is_a_role_slug_absent_by_default_and_a_repositorys_to_set(self):
        self.assertNotIn("boundary_authority", arm_policy.default()["commits"])
        self.assertEqual(arm_policy.validate({"commits": {"boundary_authority": "architect-cto"}})["commits"]["boundary_authority"], "architect-cto")
        for bad in ("Architect", "", 3, ["architect-cto"], "a b", None):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate({"commits": {"boundary_authority": bad}})

    def test_every_mode_and_method_the_schema_allows_is_allowed(self):
        for mode in ("queue", "auto", "direct", "owner-only"):
            arm_policy.validate({"mode": mode})
        for method in ("merge", "squash", "rebase"):
            arm_policy.validate({"method": method})
        arm_policy.validate({"commits": {"below_min": "refuse"}, "bots": {"dependabot": {"arm": ["patch", "minor"], "ecosystems": ["pip"]}},
                             "queue": {"grouping": "headgreen", "build": 3}, "github": {"ruleset": "r", "branch": "main"}})

    def test_the_older_arm_json_class_form_is_a_class_with_a_minimum_of_one_and_names_may_have_spaces(self):
        base = arm_policy.validate({"commits": {"classes": {"docs": {"paths": r"\.md$", "min": 3}}}})
        p = arm_policy.with_classes(base, {"Single-Check Tooling": r"^tools/", "x": {"paths": "^x/"}})
        self.assertEqual(p["commits"]["classes"], {"single-check tooling": {"paths": "^tools/", "min": 1}, "x": {"paths": "^x/", "min": 1},
                                                    "docs": {"paths": r"\.md$", "min": 3}})

    def test_a_policy_file_states_a_class_as_the_schema_does_the_older_form_is_arm_jsons_only(self):
        for bad in ({"docs": "^docs/"}, {"docs": {"paths": "^d"}}, {"docs": {"min": 2}}):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate({"commits": {"classes": bad}})
        arm_policy.validate({"commits": {"classes": {" odd name": {"paths": "^d", "min": 1}}}})

    def test_what_the_schema_allows_the_loader_allows(self):
        for doc in ({"commits": {"min": 20}}, {"queue": {"merge_min": 6}}, {"required_checks": [{"context": "c", "app": "Foo"}]},
                    {"github": {"ruleset": " "}}, {"commits": {"min": 1.0, "advice_over": 16.0, "roles": {"web-dev": {"min": 2.0}}}},
                    {"commits": {"classes": {"docs": {"paths": "^d", "min": 3.0}}}}, {"description": "why"}):
            arm_policy.validate(doc)
        self.assertIsInstance(arm_policy.validate({"commits": {"min": 3.0}})["commits"]["min"], int)
        p = arm_policy.validate({"commits": {"roles": {"web-dev": {"min": 2.0}}, "classes": {"docs": {"paths": "^d", "min": 3.0}}},
                                 "queue": {"build": 4.0}})
        for value in (p["commits"]["roles"]["web-dev"]["min"], p["commits"]["classes"]["docs"]["min"], p["queue"]["build"]):
            self.assertIsInstance(value, int)

    def test_what_the_schema_refuses_the_loader_refuses(self):
        for doc in ({"$schema": "x"}, {"description": 5}, {"description": ""}, {"commits": {"min": 1.5}}, {"commits": {"min": float("inf")}},
                    {"commits": {"min": float("nan")}}):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(doc)):
                arm_policy.validate(doc)

    def test_the_rules_the_schema_cannot_say_are_the_loaders_a_regex_that_compiles_class_names_distinct_in_lower_case_and_without_a_newline(self):
        for bad in ({"docs": {"paths": "(", "min": 1}}, {"Docs": {"paths": "a", "min": 1}, "docs": {"paths": "b", "min": 1}},
                    {"a\nb": {"paths": "x", "min": 1}}):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate({"commits": {"classes": bad}})

    def test_a_class_that_is_not_one_is_refused(self):
        for bad in ({"a": {"paths": "(", "min": 1}}, {"a": {"paths": 3, "min": 1}}, {"a": {"min": 2}}, {"a": {"paths": "x", "min": 0}}, {"a": 3},
                    {"A": {"paths": "x", "min": 1}, "a": {"paths": "y", "min": 1}}, {"": {"paths": "x", "min": 1}}):
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

    def test_the_schema_and_the_loader_agree_on_the_documents_where_they_can(self):
        queue = {"mode": "queue", "method": "squash", "queue": {"grouping": "headgreen", "build": 5, "merge_max": 5, "merge_min": 1,
                                                                "wait_minutes": 2, "check_timeout_minutes": 60}}
        valid = [{}, FABRIC_POLICY, queue, {"commits": {"min": 4, "roles": {"devex-tooling": {"min": 2}}, "classes": {"docs": {"paths": "^docs/", "min": 1}}}},
                 {"commits": {"boundary_min": 12}}, {"commits": {"boundary_authority": "architect-cto"}},
                 {"bots": {"dependabot": {"arm": ["patch", "minor"], "ecosystems": ["npm_and_yarn", "pip"]}}},
                 {"github": {"ruleset": "r", "branch": "main"}}, {"mode": "owner-only"}, {"mode": "direct"}, {"commits": {"below_min": "refuse"}},
                 {"commits": {"min": 20}}, {"queue": {"merge_min": 6}}, {"required_checks": [{"context": "c", "app": "Foo"}]},
                 {"github": {"ruleset": " "}}, {"commits": {"min": 1.0}}, {"description": "why"},
                 {"reviews": ["claude", "codex"]}, {"reviews": ["codex"], "boundary_reviews": ["claude", "codex"]}]
        invalid = [{"mode": "auto", "autoo": True}, {"queue": {"depth": 3}}, {"mode": "squash"}, {"method": "fast-forward"},
                   {"reviews": []}, {"reviews": ["gemini"]}, {"reviews": "codex"}, {"reviews": ["codex", "codex"]}, {"boundary_reviews": ["x"]},
                   {"commits": {"below_min": "warn"}}, {"commits": {"min": 0}}, {"commits": {"boundary_min": 0}}, {"commits": {"boundary_min": 2.5}}, {"commits": {"boundary_authority": "Architect"}}, {"commits": {"roles": {"devex-tooling": {"min": 0}}}},
                   {"commits": {"roles": {"Devex Tooling": {"min": 2}}}}, {"commits": {"classes": {"docs": {"min": 1}}}},
                   {"queue": {"grouping": "some"}}, {"queue": {"build": 2.5}}, {"required_checks": [{"app": "github-actions"}]},
                   {"bots": {"renovate": {"arm": ["patch"]}}}, {"bots": {"dependabot": {"arm": ["breaking"]}}}, {"signatures": "yes"},
                   {"protect": {"deletion": 1}}, {"required_checks": ["ci-ok"]}, {"$schema": "x"}, {"description": 5}, {"description": ""},
                   {"commits": {"classes": {"docs": "^docs/"}}}, {"commits": {"classes": {"docs": {"paths": "^d"}}}}]
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


class RemoteSpellings(unittest.TestCase):
    def test_a_registered_project_is_found_by_the_registrys_own_comparison_of_remotes(self):
        for remote in ("https://GitHub.com/O/R", "ssh://git@github.com:22/O/R.git", "git@github.com:O/R.git ", "https://github.com/o/r/",
                       "https://user@github.com/O/R.git", "git@github.com:o/R"):
            registry = {"projects": {"p": {"client": "c", "remotes": [remote]}}}
            found = arm_policy.project_of(registry, "O/R")
            self.assertIsNotNone(found, remote)
            self.assertEqual(arm_policy.settings_repo_of(registry, CLIENTS, "O/R"), "o/settings", remote)

    def test_a_remote_that_is_another_repository_or_another_host_is_not_it(self):
        for remote in ("https://github.com/O/R2", "https://gitlab.com/O/R", "git@github.com:O/other.git", "/srv/git/O/R", "R"):
            self.assertIsNone(arm_policy.project_of({"projects": {"p": {"client": "c", "remotes": [remote]}}}, "O/R"), remote)


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

    def test_a_repository_file_overrides_the_fleets_reviews(self):
        self.assertEqual(self.load(Api(contents({"reviews": ["claude", "codex"]})))["reviews"], ["claude", "codex"])
        self.assertEqual(self.load(Api(contents({"reviews": ["claude"]})))["reviews"], ["claude"])
        self.assertEqual(self.load(Api(error=ghe(404, "Not Found")))["reviews"], ["claude"])

    def test_a_repository_may_raise_the_boundary_minimum_and_never_lower_it_below_the_fleets(self):
        for repo_value, want in ((3, 8), (8, 8), (12, 12)):
            api = Api(contents({"commits": {"boundary_min": repo_value}}))
            self.assertEqual(self.load(api)["commits"]["boundary_min"], want, repo_value)
        self.fleet({"commits": {"boundary_min": 10}})
        self.assertEqual(self.load(Api(contents({"commits": {"boundary_min": 4}})))["commits"]["boundary_min"], 10)
        self.assertEqual(self.load(Api(error=ghe(404, "Not Found")))["commits"]["boundary_min"], 10)

    def test_the_registry_and_the_clients_are_read_when_not_given_and_their_failure_is_unavailable(self):
        import workingcopy
        with mock.patch.object(workingcopy, "load_registry", side_effect=OSError("gone")):
            with self.assertRaises(arm_policy.PolicyUnavailable):
                arm_policy.load("O/R", root=self.dir, clients=CLIENTS, api=Api(contents({})))
        with open(os.path.join(self.dir, "projects", "clients.json"), "w") as fh:
            json.dump(CLIENTS, fh)
        with mock.patch.object(workingcopy, "load_registry", return_value=REGISTRY):
            self.assertEqual(arm_policy.load("O/R", root=self.dir, api=Api(contents({"commits": {"min": 4}})))["commits"]["min"], 4)


class Reviews(Scratch):
    """The `reviews` rule (agent-fabric ADR-053 rule 6): which engines a PR needs. arm.py's refusals are test_arm_cli's."""

    def test_the_default_requires_claude_and_asks_codex_as_an_additional_review(self):
        # The owner, 2026-10-13: codex is more, never a block; on a boundary change too.
        d = arm_policy.default()
        self.assertEqual((d["reviews"], d["boundary_reviews"], d["additional_reviews"]), (["claude"], ["claude"], ["codex"]))
        self.assertEqual((arm_policy.required_engines(d, False), arm_policy.required_engines(d, True)), (["claude"], ["claude"]))
        self.assertEqual((arm_policy.additional_engines(d, False), arm_policy.additional_engines(d, True)), (["codex"], ["codex"]))

    def test_a_list_replaces_the_fleets_and_never_merges(self):
        self.assertEqual(arm_policy.validate({"reviews": ["codex"]})["reviews"], ["codex"])
        self.assertEqual(arm_policy.required_engines(arm_policy.validate({"reviews": ["codex"]}), False), ["codex"])

    def test_the_boundary_adds_its_engines_only_when_it_is_judged(self):
        p = arm_policy.validate({"reviews": ["claude"], "boundary_reviews": ["claude", "codex"]})
        self.assertEqual(arm_policy.required_engines(p, False), ["claude"])
        self.assertEqual(arm_policy.required_engines(p, True), ["claude", "codex"])

    def test_additional_reviews_never_change_the_required_ones(self):
        self.assertEqual(arm_policy.additional_engines(arm_policy.validate({"additional_reviews": []}), False), [])
        p = arm_policy.validate({"reviews": ["claude"], "boundary_reviews": ["claude"], "additional_reviews": ["codex"]})
        self.assertEqual((arm_policy.required_engines(p, False), arm_policy.required_engines(p, True)), (["claude"], ["claude"]))
        self.assertEqual((arm_policy.additional_engines(p, False), arm_policy.additional_engines(p, True)), (["codex"], ["codex"]))

    def test_an_additional_engine_the_boundary_requires_is_required_there(self):
        p = arm_policy.validate({"reviews": ["claude"], "boundary_reviews": ["claude", "codex"], "additional_reviews": ["codex"]})
        self.assertEqual((arm_policy.required_engines(p, False), arm_policy.additional_engines(p, False)), (["claude"], ["codex"]))
        self.assertEqual((arm_policy.required_engines(p, True), arm_policy.additional_engines(p, True)), (["claude", "codex"], []))

    def test_a_required_engine_is_required_whichever_list_also_names_it(self):
        # A repository's file requiring codex over a fleet whose additional_reviews names it (objects merge, lists
        # replace): the merged policy is a policy, and codex is required (review of 47a196e8).
        p = arm_policy.validate(arm_policy.merge({"reviews": ["claude"], "additional_reviews": ["codex"]}, {"reviews": ["claude", "codex"]}))
        self.assertEqual((arm_policy.required_engines(p, False), arm_policy.additional_engines(p, False)), (["claude", "codex"], []))

    def test_additional_reviews_is_a_list_of_distinct_engines(self):
        self.assertEqual(arm_policy.validate({"additional_reviews": []})["additional_reviews"], [])
        for bad in ({"additional_reviews": "codex"}, {"additional_reviews": ["gemini"]}, {"additional_reviews": ["codex", "codex"]}):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate(bad)


class ReviewLine(unittest.TestCase):
    """The line arm, gate and counts print: an additional engine is ✓, unavailable (<reason>) or absent, and none of
    them keeps "head reviewed" off it (#264 F1). The marker stands in only for the exact head it names, on a review of that head."""
    HEAD = "abcdef12" + "3" * 32

    def gone(self, head=None, commit=None, engine="codex", reason="allowance"):
        head = head or self.HEAD
        return {"login": "me", "commit_sha8": (commit or head)[:8], "at": "t", "engine": engine, "head": head, "reason": reason}

    def line(self, have, marks=()):
        return arm_policy.review_summary(set(have), ["claude"], self.HEAD, additional=["codex"],
                                         unavailable=arm_policy.engines_unavailable(list(marks), self.HEAD))

    def test_the_three_states(self):
        self.assertEqual(self.line({"claude", "codex"}), "head reviewed: claude ✓ codex ✓ (head abcdef12)")
        self.assertEqual(self.line({"claude"}, [self.gone()]), "head reviewed: claude ✓ codex unavailable (allowance) (head abcdef12)")
        self.assertEqual(self.line({"claude"}), "head reviewed: claude ✓ codex absent (head abcdef12)")

    def test_an_absent_additional_engine_a_boundary_also_requires_reads_boundary_only(self):
        # The gate passes it as both (pr_gate.engines_required, engines_additional): arm requires it of a boundary.
        line = arm_policy.review_summary({"claude"}, ["claude"], self.HEAD, ["codex"], additional=["codex"])
        self.assertEqual(line, "head reviewed: claude ✓ codex ✗ (boundary only) (head abcdef12)")
        line = arm_policy.review_summary({"claude"}, ["claude"], self.HEAD, ["codex"], additional=["codex"],
                                         unavailable={"codex": "allowance"})
        self.assertEqual(line, "head reviewed: claude ✓ codex unavailable (allowance) ✗ (boundary only) (head abcdef12)")

    def test_an_unavailable_additional_engine_never_stands_in_for_a_required_one(self):
        self.assertEqual(self.line(set(), [self.gone()]), "claude ✗ codex unavailable (allowance) (head abcdef12)")
        self.assertEqual(arm_policy.engines_unavailable([self.gone(engine="claude")], self.HEAD), {"claude": "allowance"})
        self.assertFalse(arm_policy.is_head_reviewed(arm_policy.review_summary(
            {"codex"}, ["claude", "codex"], self.HEAD, unavailable={"claude": "allowance"})))

    def test_a_marker_for_another_head_or_on_a_review_of_another_commit_counts_for_nothing(self):
        other = "0123abcd" + "4" * 32
        for mark in (self.gone(head=other), self.gone(commit=other), self.gone(head=self.HEAD[:39] + "9"), {"engine": "codex"}, "x"):
            self.assertEqual(self.line({"claude"}, [mark]), "head reviewed: claude ✓ codex absent (head abcdef12)", mark)

    def test_a_review_of_the_head_is_the_mark_whatever_marker_is_there_too(self):
        self.assertEqual(self.line({"claude", "codex"}, [self.gone()]), "head reviewed: claude ✓ codex ✓ (head abcdef12)")



class Threshold(unittest.TestCase):
    P = arm_policy.validate({"commits": {"min": 9, "roles": {"web-dev": {"min": 4}, "rust-dev": {"min": 12}},
                                         "classes": {"docs": {"paths": r"\.md$", "min": 2}, "tooling": {"paths": r"^tools/", "min": 1}}}})

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

    def test_the_boundary_minimum_holds_when_the_repository_sets_a_small_minimum(self):
        small = arm_policy.validate({"commits": {"min": 1, "roles": {"web-dev": {"min": 1}}}})
        self.assertEqual(arm_policy.threshold(small, "web-dev", "", True), 8)
        self.assertEqual(arm_policy.threshold(small, None, "", False), 1)

    def test_the_boundary_minimum_is_its_own_key_and_a_repository_may_raise_it(self):
        p = arm_policy.validate({"commits": {"min": 1, "boundary_min": 12}})
        self.assertEqual(arm_policy.threshold(p, None, "", True), 12)
        self.assertEqual(arm_policy.threshold(arm_policy.validate({"commits": {"min": 20, "advice_over": 30, "boundary_min": 3}}), None, "", True), 20,
                         "a boundary change never needs fewer commits than an ordinary one")

    def test_a_class_the_policy_does_not_have_is_an_error_not_the_repositorys_minimum(self):
        with self.assertRaises(arm_policy.PolicyError):
            arm_policy.threshold(self.P, None, "nothing", False)

    def test_classes_from_arm_json_are_added_under_the_policys_own(self):
        p = arm_policy.with_classes(self.P, {"tooling": "^other/", "ddl": "^db/"})
        self.assertEqual(p["commits"]["classes"]["tooling"], {"paths": "^tools/", "min": 1})
        self.assertEqual(p["commits"]["classes"]["ddl"], {"paths": "^db/", "min": 1})
        self.assertNotIn("ddl", self.P["commits"]["classes"], "the policy given is not changed")


class RepoSettings(unittest.TestCase):
    """fabric-repo-settings writes the merge fields fabric-repo-policy compares, from the one function both read: they
    once disagreed, squash and rebase allowed by one and refused by the other, and every arm warned twice (REQUEST
    01a139bb)."""

    def test_the_settings_state_none_of_the_fields_the_policy_decides(self):
        self.assertEqual(set(repo_settings.REPOSITORY) & set(arm_policy.REPOSITORY_FIELDS), set())
        self.assertEqual(set(repo_policy.REPOSITORY_FIELDS), set(arm_policy.REPOSITORY_FIELDS))

    def test_what_the_settings_write_is_what_the_policy_check_wants(self):
        for doc in (FABRIC_POLICY, {"method": "squash", "mode": "owner-only", "delete_branch_on_merge": True}, {}):
            policy = arm_policy.validate(doc)
            with mock.patch.object(arm_policy, "load", return_value=policy) as load:
                written = repo_settings.repository("O/R")
            load.assert_called_once_with("O/R")
            desired = arm_policy.render(policy)
            self.assertEqual({f: written[f] for f in arm_policy.REPOSITORY_FIELDS}, desired["repository"], doc)
            found = repo_policy.differences(desired, {"repository": written, "ruleset": desired["ruleset"]}, "n")
            self.assertEqual([x for x in found if x.startswith("repository ")], [], doc)
        self.assertEqual([written[f] for f in ("allow_merge_commit", "allow_squash_merge", "allow_rebase_merge")], [True, False, False],
                         "the fleet default: merge commits only")

    def test_a_policy_that_cannot_be_read_writes_nothing(self):
        for error in (arm_policy.PolicyUnavailable("o/settings cannot be read (HTTP 403)"), arm_policy.PolicyError("bad")):
            api = mock.Mock()
            with mock.patch.object(arm_policy, "load", side_effect=error), mock.patch.object(gh, "api", api):
                with self.assertRaises(gh.GhError) as e:
                    repo_settings.apply("O/R")
            self.assertIn("the arming policy", str(e.exception))
            self.assertIn(str(error), str(e.exception))
            api.assert_not_called()


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
        return pr_gate.verdict(1, "main", False, commits, self.CLEAR, "head reviewed: claude ✓ codex ✓ (head abcdef01)", [], policy)

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

    def test_the_verdict_names_the_policys_method_and_says_below_min_refuse(self):
        for method in ("merge", "squash", "rebase"):
            self.assertIn(f"gh pr merge 1 --{method} --auto", self.v(9, arm_policy.validate({"method": method})))
        text = self.v(3, arm_policy.validate({"commits": {"min": 8, "below_min": "refuse"}}))
        self.assertIn("refuses below the minimum", text)
        self.assertNotIn("ask the owner", text)

    def test_a_minimum_above_the_advice_size_is_not_too_big_below_the_minimum_as_arm_reads_it(self):
        for policy in ({"commits": {"min": 20}}, {"commits": {"min": 20, "below_min": "refuse"}}):
            text = self.v(18, arm_policy.validate(policy))
            self.assertNotIn("over 16", text)
            self.assertNotIn("arm on the basis", text)
        self.assertIn("ask the owner (18 work commits < 20)", self.v(18, arm_policy.validate({"commits": {"min": 20}})))
        self.assertIn("over 20", self.v(21, arm_policy.validate({"commits": {"min": 20}})))

    def test_owner_only_is_not_armed_by_fabric_pr(self):
        text = self.v(20, arm_policy.validate({"mode": "owner-only"}))
        self.assertIn("only the owner merges", text)
        self.assertNotIn("arm: post", text)

    def test_direct_is_merged_at_once_on_the_count_rule_with_no_auto(self):
        text = self.v(10, arm_policy.validate({"mode": "direct"}))
        self.assertIn("arm: post the basis", text)
        self.assertIn("--merge", text)
        self.assertNotIn("--auto", text)
        self.assertIn("ask the owner", self.v(1, arm_policy.validate({"mode": "direct"})))


class PrGateRun(unittest.TestCase):
    """pr_gate.run() in process, with what it reads replaced: it loads the repository's policy and its verdict says
    the policy's numbers, or that the policy could not be read."""
    HEAD = "abcdef1234567890abcdef1234567890abcdef12"

    def rows(self, policy_load, work=5, review=None):
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
            es.enter_context(mock.patch.object(pr_gate.landed, "origin_is", return_value=True))
            es.enter_context(mock.patch.object(pr_gate, "review_reader", return_value=None))
            es.enter_context(mock.patch.object(pr_gate, "count_commits", return_value=commits))
            es.enter_context(mock.patch.object(pr_gate, "gate_state", return_value=st))
            es.enter_context(mock.patch.object(pr_gate, "review_of_head", review or mock.Mock(return_value="head reviewed: claude ✓ codex ✓ (head abcdef01)")))
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

    def test_the_review_is_judged_against_the_engines_of_the_policy_loaded_for_the_repository(self):
        # Supplier review F2: the gate's engines are the repository's, not every engine nor the default's.
        review = mock.Mock(return_value="claude ✓ (head abcdef12)")
        policy = arm_policy.validate({"reviews": ["claude"], "boundary_reviews": ["claude", "codex"], "additional_reviews": []})
        row = self.rows(lambda r, **k: policy, review=review)[0]
        self.assertEqual((review.call_args.args[2:], review.call_args.kwargs), ((self.HEAD, ["claude"], ["codex"], ""), {"additional": []}))
        self.assertIn("not every required engine has reviewed the head (claude ✓ (head abcdef12))", row["verdict"])

        def unreadable(repo, **kw):
            raise arm_policy.PolicyUnavailable("HTTP 500")
        review.reset_mock()
        self.rows(unreadable, review=review)
        self.assertEqual(review.call_args.args[2:], (self.HEAD, list(arm_policy.ENGINES), [], "HTTP 500"))
        self.assertEqual(review.call_args.kwargs, {"additional": []})

    def test_the_additional_engines_are_the_policys_and_the_gate_reads_their_markers(self):
        review = mock.Mock(return_value="head reviewed: claude ✓ codex unavailable (allowance) (head abcdef12)")
        policy = arm_policy.validate({"reviews": ["claude"], "boundary_reviews": ["claude"], "additional_reviews": ["codex"]})
        row = self.rows(lambda r, **k: policy, work=9, review=review)[0]
        self.assertEqual((review.call_args.args[2:], review.call_args.kwargs), ((self.HEAD, ["claude"], [], ""), {"additional": ["codex"]}))
        self.assertIn("arm: post the basis (9", row["verdict"])

    def test_review_of_head_reads_the_unavailable_rows_of_the_reader(self):
        def reader(doc):
            return [sys.executable, "-c", f"import sys; sys.stdout.write({json.dumps(json.dumps(doc))})"]
        blind = {"rows": [{"login": "me", "commit_sha8": self.HEAD[:8], "at": "t", "engine": "claude"}]}
        gone = {"rows": [{"login": "me", "commit_sha8": self.HEAD[:8], "at": "t", "engine": "codex", "head": self.HEAD, "reason": "allowance"}]}
        self.assertEqual(pr_gate.review_of_head(reader({"blind": blind, "unavailable": gone}), 7, self.HEAD, ["claude"], additional=["codex"]),
                         "head reviewed: claude ✓ codex unavailable (allowance) (head abcdef12)")
        self.assertEqual(pr_gate.review_of_head(reader({"blind": blind}), 7, self.HEAD, ["claude"], additional=["codex"]),
                         "head reviewed: claude ✓ codex absent (head abcdef12)")
        self.assertEqual(pr_gate.review_of_head(reader({"blind": blind, "unavailable": {"rows": "x"}}), 7, self.HEAD, ["claude"]), "?")
        for not_an_object in (None, [], "x"):
            self.assertEqual(pr_gate.review_of_head(reader(not_an_object), 7, self.HEAD, ["claude"], additional=["codex"]), "?", not_an_object)


def grant(sender="h/arch", to="h/me", kind="DECISION", field="AUTHORIZES", target=None, mid="01a12-grant", addressed=True, frm=None):
    """What `gzcoord-inbox --replay --json` prints for a message, as (rc, text)."""
    target = target or f"O/R#7@{ArmRun.HEAD[:12]}"
    meta = {"MESSAGE-ID": mid, "TO": to, "FROM": frm or sender, field: target}
    return (0 if addressed else 2), json.dumps({"addressed": addressed, "type": kind, "sender": sender, "metadata": meta})


def fleet_of(*rows):
    """`fabric-ctl all presence --json` for (login, role, online) rows, as (rc, text)."""
    return 0, "\n".join(json.dumps({"account": login, "host": "h", "status": "ok", "presence": {"status": "ok", "online": online, "role": role}})
                        for login, role, online in rows)


def whoami_of(role="architect-cto", address="h/me"):
    """`fabric-whoami --json` as (rc, text); a session bound to no role carries none."""
    return 0, json.dumps({"address": address, "agent": address.split("/")[1], **({"role": role} if role else {})})


def silent(login: str) -> str:
    """A row `fabric-ctl all presence --json` prints for an account that did not answer."""
    return json.dumps({"account": login, "host": "h", "status": "no answer", "presence": None})


def presence_of(role="architect-cto", login="arch", host="h", status="ok"):
    return 0, json.dumps({"account": login, "host": host, "status": status, "presence": {"status": "ok", "role": role}})


# The run_arm branch's login (h/me/…) bound to the role its commits carry.
HOLDS_WEB_DEV = presence_of(role="web-dev", login="me")


class ArmRun(unittest.TestCase):
    """arm.arm() in process, with everything it reads replaced: the rules are the policy's."""
    HEAD = "abcdef1234567890abcdef1234567890abcdef12"

    def run_arm(self, policy, work, files=("docs/a.md",), basis="reviewed", body="", boundary_re=r"^policies/", classes=None,
                load_error=None, extra=(), load_fn=None, drift=(), drift_error=None, role_trailers=None, checks="green", live=None,
                replay=None, presence=None, unresolved=0, reviewed=True, fleet=None, waiver_role=None, branch="h/me/feat/x",
                whoami=None):
        pr = {"number": 7, "state": "OPEN", "isDraft": False, "headRefName": branch, "headRefOid": self.HEAD, "body": body, "title": "t"}
        gate = [{"commits_known": True, "work_commits": work, "checks": checks}]
        review = {"blind": {"rows": [{"commit_sha8": self.HEAD[:8]}] if reviewed else []}, "unresolved_threads": unresolved}
        self.reads = reads = []
        commits = [{"parents": [{}, {}], "commit": {"message": "Merge branch main"}} if r == "MERGE" else
                   {"parents": [{}], "commit": {"message": "c" + (f"\n\nFabric-Role: {r}" if r else "")}} for r in (role_trailers or [None])]
        ran = []

        def reader(head, args, timeout=600):
            what = " ".join(head)
            if "gzcoord-inbox" in what:
                reads.append(("replay", list(args)))
                return replay if replay is not None else (1, "")
            if "fabric-whoami" in what:
                reads.append(("whoami", list(args)))
                return whoami if whoami is not None else (1, "")
            if "fabric-ctl" in what:
                reads.append(("fleet" if args[:1] == ["all"] else "presence", list(args)))
                if args[:1] == ["all"]:
                    return fleet if fleet is not None else (1, "")
                return presence if presence is not None else (1, "")
            return (0, json.dumps(review if "review-status" in what else gate))

        def api(path, **kw):
            return commits if "/commits" in path else [{"filename": f} for f in files]

        def gh_run(args, **kw):
            # A comment's body goes on stdin: kept as the call's last item, so the basis can be read.
            ran.append([*args, kw["input"]] if args[:2] == ["pr", "comment"] else list(args))
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
            st.enter_context(mock.patch.object(arm, "load_config", return_value=(re.compile(boundary_re), None, classes, waiver_role)))
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

    def test_under_the_fleet_default_the_claude_review_with_no_codex_review_or_marker_arms_with_codex_absent(self):
        rc, out = self.run_arm(arm_policy.default(), 9)
        self.assertEqual(rc, 0, out)
        self.assertIn("codex: absent, no review or marker on abcdef12: arming on the required review(s) alone", out)
        self.assertTrue([c for c in self.ran if c[:2] == ["pr", "merge"]], self.ran)
        basis = [c for c in self.ran if c[:2] == ["pr", "comment"]]
        self.assertTrue(basis and "codex: absent, no review or marker on abcdef12: armed on the claude review alone." in basis[0][-1],
                        self.ran)

    def test_the_minimum_is_the_policys(self):
        p = claude_only({"commits": {"min": 3, "advice_over": 5}})
        rc, out = self.run_arm(p, 3, extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("count rule: 3 work commits — 3 or more, arms at the review gate", out)
        rc, _ = self.run_arm(p, 2)
        self.assertIn("under 3 arms only on the owner's word", str(rc))
        rc, out = self.run_arm(p, 2, basis="the owner's word", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("under 3, on the owner's word", out)

    def test_the_advice_threshold_is_the_policys(self):
        p = claude_only({"commits": {"min": 3, "advice_over": 5}})
        _, out = self.run_arm(p, 6, extra=("--dry-run",))
        self.assertIn("6 work commits — over 5: smaller batches next time", out)
        _, out = self.run_arm(p, 5, extra=("--dry-run",))
        self.assertNotIn("smaller batches", out)

    def test_a_minimum_above_the_default_advice_size_does_not_make_every_pull_request_too_big(self):
        p = claude_only({"commits": {"min": 20}})
        _, out = self.run_arm(p, 18, basis="the owner's word", extra=("--dry-run",))
        self.assertNotIn("smaller batches", out)
        _, out = self.run_arm(p, 21, extra=("--dry-run",))
        self.assertNotIn("over 16", out)
        self.assertIn("21 work commits — over 20: smaller batches next time", out)

    def test_below_min_refuse_is_a_refusal_the_owners_word_does_not_lift(self):
        p = claude_only({"commits": {"min": 3, "below_min": "refuse"}})
        for basis in ("reviewed", "the owner's word"):
            rc, _ = self.run_arm(p, 2, basis=basis)
            self.assertIn("refuses below the minimum", str(rc), basis)
        rc, out = self.run_arm(p, 3, extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_the_boundary_floor_is_not_lowered_by_a_small_repository_minimum(self):
        p = claude_only({"commits": {"min": 1, "advice_over": 20}})
        rc, _ = self.run_arm(p, 7, files=("policies/x.json",))
        self.assertIn("a security-boundary change under 8 arms only on the owner's word", str(rc))
        rc, out = self.run_arm(p, 8, files=("policies/x.json",), extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("Security boundary, armed on the count rule (8 or more work commits) without the owner's word.", out)

    def test_a_stated_class_arms_at_its_own_minimum_and_below_it_asks_for_the_word(self):
        p = claude_only({"commits": {"min": 8, "classes": {"docs": {"paths": r"\.md$", "min": 3}}}})
        body = "Class: docs"
        rc, out = self.run_arm(p, 3, body=body, classes={"docs": r"\.md$"}, extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        rc, _ = self.run_arm(p, 2, body=body, classes={"docs": r"\.md$"})
        self.assertIn("the class docs arms at 3 or more", str(rc))
        rc, out = self.run_arm(p, 2, body=body, classes={"docs": r"\.md$"}, basis="the owner's word", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_a_class_with_a_minimum_of_one_has_no_lower_bound_a_zero_work_pull_request_still_arms(self):
        for p in (claude_only(), claude_only({"commits": {"classes": {"docs": {"paths": r"\.md$", "min": 1}}}})):
            rc, out = self.run_arm(p, 0, body="Class: docs", classes={"docs": r"\.md$"}, extra=("--dry-run",))
            self.assertEqual(rc, 0, out)
            self.assertIn("under 8, arms at the gate as docs", out)

    def test_a_boundary_change_gets_no_exemption_from_a_class_even_at_a_repository_minimum_of_one(self):
        p = claude_only({"commits": {"min": 1, "advice_over": 5, "classes": {"docs": {"paths": r"\.md$", "min": 1}}}})
        rc, _ = self.run_arm(p, 0, files=("policies/a.md",), body="Class: docs", classes={"docs": r"\.md$"})
        self.assertIn("a security-boundary change under 8 arms only on the owner's word", str(rc))
        rc, out = self.run_arm(p, 0, files=("policies/a.md",), body="Class: docs", classes={"docs": r"\.md$"}, basis="the owner's word",
                               extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_the_policys_class_is_applied_whole_its_regex_as_well_as_its_minimum(self):
        p = claude_only({"commits": {"classes": {"docs": {"paths": r"^docs/", "min": 3}}}})
        rc, _ = self.run_arm(p, 3, files=("src/x.py",), body="Class: docs", classes={"docs": r"."})
        self.assertIn("the changed files are not that class", str(rc))
        rc, out = self.run_arm(p, 3, files=("docs/x.md",), body="Class: docs", classes={"docs": r"."}, extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_a_class_only_the_policy_has_can_be_stated(self):
        p = claude_only({"commits": {"classes": {"web": {"paths": r"^web/", "min": 2}}}})
        rc, out = self.run_arm(p, 2, files=("web/a.ts",), body="Class: web", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("class stated and confirmed by the files: web", out)
        rc, _ = self.run_arm(p, 1, files=("web/a.ts",), body="Class: web")
        self.assertIn("the class web arms at 2 or more", str(rc))

    def test_a_class_above_the_repositorys_minimum_is_said_as_the_owners_word_not_as_the_gate(self):
        p = claude_only({"commits": {"min": 8, "classes": {"big": {"paths": r"^x/", "min": 10}}}})
        rc, out = self.run_arm(p, 9, files=("x/a",), body="Class: big", basis="the owner's word", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("count rule: 9 work commits — under 10, on the owner's word", out)
        self.assertNotIn("arms at the review gate", out)

    AUTH = ("--authorization", "ref-1")

    def authorized(self, files=("policies/x.json",), work=3, policy=None, **kw):
        policy = policy or claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}})
        kw.setdefault("replay", grant())
        kw.setdefault("presence", presence_of())
        return self.run_arm(policy, work, files=files, extra=(*self.AUTH, "--dry-run"), **kw)

    def test_the_holder_of_the_boundary_authority_role_arms_a_three_commit_boundary_change_in_the_owners_place(self):
        rc, out = self.authorized()
        self.assertEqual(rc, 0, out)
        self.assertIn("count gate AUTHORIZED by arch, architect-cto (01a12-grant), in the owner's place", out)
        self.assertIn("count rule: 3 work commits — under 8, authorized in the owner's place", out)
        self.assertIn("Boundary count gate authorized by arch, architect-cto (01a12-grant).", out)
        self.assertEqual([r[0] for r in self.reads], ["replay", "presence"])
        self.assertEqual(self.reads[0][1], ["--replay", "ref-1", "--json"])

    def test_an_authorization_from_another_role_a_stale_head_a_broadcast_or_the_wrong_pr_is_refused(self):
        for label, kw, words in (
                ("another role", {"presence": presence_of(role="web-dev")}, "who holds web-dev, not architect-cto"),
                ("a stale head", {"replay": grant(target="O/R#7@0123456789ab")}, "head 0123456789ab"),
                ("a broadcast", {"replay": grant(to="")}, "a broadcast or a role address"),
                ("a role address", {"replay": grant(to="role:architect-cto")}, "not sent TO h/me"),
                ("another pr", {"replay": grant(target=f"O/R#8@{self.HEAD[:12]}")}, "AUTHORIZES O/R#8"),
                ("another repository", {"replay": grant(target=f"O/X#7@{self.HEAD[:12]}")}, "AUTHORIZES O/X#7"),
                ("no AUTHORIZES line", {"replay": grant(field="WAIVES")}, "has no AUTHORIZES"),
                ("a message that is not a decision", {"replay": grant(kind="INFO")}, "not a DECISION or REPLY"),
                ("the arming login itself", {"replay": grant(sender="h/me")}, "the login arming"),
                ("a sender that is not the FROM", {"replay": grant(frm="h/other")}, "but says FROM"),
                ("a message not addressed", {"replay": grant(addressed=False)}, "not addressed to this session")):
            rc, _ = self.authorized(**kw)
            self.assertTrue(str(rc).startswith("refused"), (label, rc))
            self.assertIn(words, str(rc), label)

    def test_what_cannot_be_read_is_unanswered_never_a_pass(self):
        for label, kw, words in (("the relay", {"replay": (1, "")}, "could not be read from the relay"),
                                 ("presence", {"presence": (1, "")}, "could not say which role")):
            rc, _ = self.authorized(**kw)
            self.assertTrue(str(rc).startswith("unanswered"), (label, rc))
            self.assertIn(words, str(rc))

    def test_an_authority_the_policy_does_not_name_or_the_catalogue_does_not_hold_stops_the_arming(self):
        rc, _ = self.authorized(policy=claude_only({"commits": {"min": 1}}))
        self.assertIn("names no boundary_authority", str(rc))
        self.assertIn("ask the owner", str(rc), "the policy names nobody else, so the owner is who to ask")
        self.assertTrue(str(rc).startswith("refused"), rc)
        self.assertEqual(self.reads, [])
        rc, _ = self.authorized(policy=claude_only({"commits": {"min": 1, "boundary_authority": "no-such-role"}}))
        self.assertTrue(str(rc).startswith("unanswered"), rc)
        self.assertIn("not a role of identities/roles/catalog.json", str(rc))

    def test_the_review_gate_still_applies_whatever_the_authorization_says(self):
        for kw in ({"unresolved": 1}, {"reviewed": False}):
            rc, _ = self.authorized(**kw)
            self.assertTrue(str(rc).startswith("refused"), (kw, rc))
            self.assertEqual(self.reads, [], "the authorization is not even read")

    def test_an_authorization_is_not_read_where_the_owners_word_is_not_needed(self):
        for kw in ({"work": 9}, {"files": ("docs/a.md",)}):
            rc, out = self.authorized(**kw)
            self.assertEqual(rc, 0, out)
            self.assertIn("no authorization is needed: the authorization ref-1 is not read, and not recorded", out)
            self.assertNotIn("authorized by", out)
            self.assertEqual(self.reads, [])
        rc, out = self.authorized(basis="the owner's word")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.reads, [])

    def test_below_min_refuse_is_not_lifted_by_an_authorization(self):
        p = claude_only({"commits": {"min": 1, "below_min": "refuse", "boundary_authority": "architect-cto"}})
        rc, _ = self.authorized(policy=p, work=3)
        self.assertIn("refuses below the minimum", str(rc))
        self.assertEqual(self.reads, [])

    def test_an_authorization_stands_in_for_the_owners_word_wherever_it_is_asked_on_a_boundary_change(self):
        p = claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto", "classes": {"docs": {"paths": r"\.md$", "min": 1}}}})
        rc, out = self.authorized(policy=p, files=("policies/a.md",), body="Class: docs", classes={"docs": r"\.md$"})
        self.assertEqual(rc, 0, out)

    def test_the_authorization_is_for_the_boundary_the_waiver_stays_the_waivers(self):
        rc, out = self.run_arm(claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}}), 3,
                               files=("policies/x.json",), extra=("--authorization", "ref-1", "--dry-run"))
        self.assertTrue(str(rc).startswith("unanswered"), rc)
        rc, _ = self.run_arm(claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}}), 3,
                             files=("policies/x.json",), extra=("--dry-run",))
        self.assertIn("arms only on the owner's word", str(rc), "without --authorization the owner's word is still asked")

    def test_authorization_needs_its_reference(self):
        policy = claude_only()
        for extra in (("--authorization",), ("--authorization", "--dry-run")):
            rc, _ = self.run_arm(policy, 9, extra=extra)
            self.assertTrue(str(rc).startswith("unanswered"), (extra, rc))
            self.assertIn("--authorization needs the authorization's MESSAGE-ID or relay seq", str(rc))

    def test_an_authorization_for_a_change_that_needs_the_owners_word_says_so_not_that_none_is_needed(self):
        rc, out = self.run_arm(claude_only({"commits": {"min": 8, "boundary_authority": "architect-cto"}}), 3,
                               extra=(*self.AUTH, "--dry-run"))
        self.assertIn("arms only on the owner's word", str(rc))
        self.assertIn("an authorization stands in only for a security-boundary change, and this one needs the owner's word", out)
        self.assertNotIn("no authorization is needed", out)

    def test_the_pull_requests_own_author_cannot_authorize_it(self):
        policy = claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}})
        rc, _ = self.run_arm(policy, 3, files=("policies/x.json",), branch="h/arch/feat/x", extra=("--any-owner", *self.AUTH, "--dry-run"),
                             replay=grant(sender="h/arch"), presence=presence_of())
        self.assertTrue(str(rc).startswith("refused"), rc)
        self.assertIn("the pull request's own author", str(rc))
        rc, out = self.run_arm(policy, 3, files=("policies/x.json",), branch="h/other/feat/x", extra=("--any-owner", *self.AUTH, "--dry-run"),
                               replay=grant(sender="h/arch"), presence=presence_of())
        self.assertEqual(rc, 0, out)

    BOUNDARY = ("policies/x.json",)

    def refusal(self, policy, work=3, **kw):
        kw.setdefault("files", self.BOUNDARY)
        rc, _ = self.run_arm(policy, work, **kw)
        self.assertTrue(str(rc).startswith("refused"), rc)
        return str(rc)

    def test_a_boundary_refusal_names_the_authority_the_holders_running_now_and_the_line_to_ask_for(self):
        policy = claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}})
        text = self.refusal(policy, fleet=fleet_of(("arch1", "architect-cto", True), ("arch2", "architect-cto", True), ("dev", "web-dev", True)))
        self.assertIn("ask an architect-cto holder with a session running now (arch1, arch2)", text)
        self.assertIn(f"`AUTHORIZES: O/R#7@{self.HEAD[:8]}`", text)
        self.assertIn("--authorization <id>", text)
        self.assertNotIn("dev", text.split("running now")[1].split(")")[0])
        self.assertIn("or ask the owner", text)

    def test_with_no_holder_running_the_refusal_says_so_and_who_knows(self):
        policy = claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}})
        text = self.refusal(policy, fleet=fleet_of(("dev", "web-dev", True), ("arch1", "architect-cto", False)))
        self.assertIn("no holder has a session running now", text)
        self.assertIn("fabric-coordinator knows who holds it", text)
        self.assertNotIn("(arch1", text)

    def test_a_fleet_read_in_part_does_not_say_no_holder_is_running_and_names_who_did_not_answer(self):
        policy = claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}})
        rc, text = fleet_of(("dev", "web-dev", True))
        partial = (1, text + "\n" + silent("arch1"))
        said = self.refusal(policy, fleet=partial)
        self.assertIn("arch1 did not answer and may hold it", said)
        self.assertIn("no holder has a session running now", said)
        rc, text = fleet_of(("arch2", "architect-cto", True))
        said = self.refusal(policy, fleet=(1, text + "\n" + silent("arch1")))
        self.assertIn("with a session running now (arch2); arch1 did not answer and may hold it", said)

    def test_the_login_just_refused_is_not_named_as_someone_to_ask(self):
        policy = claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}})
        fleet = fleet_of(("arch", "architect-cto", True), ("arch2", "architect-cto", True), ("me", "architect-cto", True))
        text = self.refusal(policy, branch="h/arch/feat/x", extra=("--any-owner", *self.AUTH), replay=grant(sender="h/arch"), presence=presence_of(), fleet=fleet)
        self.assertIn("the pull request's own author", text)
        self.assertIn("session running now (arch2)", text)
        text = self.refusal(policy, extra=(*self.AUTH,), replay=grant(sender="h/me"), presence=presence_of(), fleet=fleet)
        self.assertIn("the login arming", text)
        self.assertIn("session running now (arch, arch2)", text)
        only = fleet_of(("arch", "architect-cto", True))
        text = self.refusal(policy, branch="h/arch/feat/x", extra=("--any-owner", *self.AUTH), replay=grant(sender="h/arch"), presence=presence_of(), fleet=only)
        self.assertIn("no other holder has a session running now", text)

    def test_a_boundary_authority_the_catalogue_does_not_hold_is_not_offered_as_someone_to_ask(self):
        policy = claude_only({"commits": {"min": 1, "boundary_authority": "no-such-role"}})
        text = self.refusal(policy, fleet=fleet_of(("x", "no-such-role", True)))
        self.assertIn("the policy names the boundary_authority 'no-such-role', which is not a role of identities/roles/catalog.json", text)
        self.assertIn("ask the owner", text)
        self.assertNotIn("holder", text)
        self.assertEqual([r for r in self.reads if r[0] == "fleet"], [])

    def test_an_authorization_for_a_branch_not_named_for_its_author_is_refused_not_unchecked(self):
        policy = claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}})
        for branch in ("fix-x", "x/y", "UPPER/Case/x"):
            text = self.refusal(policy, branch=branch, extra=("--any-owner", *self.AUTH), replay=grant(), presence=presence_of())
            self.assertIn("the pull request's author cannot be told from its branch", text, branch)
            self.assertEqual(self.reads, [], branch)
        self.assertEqual((arm.author_of("h/me/feat/x"), arm.author_of("h/me/a/b")), ("me", "me"))

    def test_with_the_fleet_unreadable_the_refusal_says_so(self):
        policy = claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}})
        text = self.refusal(policy, fleet=(1, ""))
        self.assertIn("who holds it could not be read", text)

    def test_a_policy_with_no_authority_sends_a_boundary_refusal_to_the_owner_and_names_the_word(self):
        text = self.refusal(claude_only({"commits": {"min": 1}}))
        self.assertIn("ask the owner: their word (\"arm <n>\", relayed to you) goes in the basis as \"the owner's word\"", text)
        self.assertNotIn("AUTHORIZES", text)
        self.assertEqual([r for r in self.reads if r[0] == "fleet"], [])

    def test_a_pull_request_under_the_minimum_that_is_no_boundary_change_names_the_owner_and_the_word(self):
        text = self.refusal(claude_only({"commits": {"min": 8}}), files=("docs/a.md",))
        self.assertIn("ask the owner", text)
        self.assertIn("arm <n>", text)
        text = self.refusal(claude_only({"commits": {"min": 8, "classes": {"big": {"paths": r"^x/", "min": 10}}}}), work=9,
                            files=("x/a",), body="Class: big", classes={"big": r"^x/"})
        self.assertIn("ask the owner", text)

    def test_a_rejected_authorization_says_whom_to_ask_for_another(self):
        policy = claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}})
        text = self.refusal(policy, extra=(*self.AUTH,), replay=grant(target="O/R#7@0123456789ab"), presence=presence_of(),
                            fleet=fleet_of(("arch1", "architect-cto", True)))
        self.assertIn("head 0123456789ab", text)
        self.assertIn("ask an architect-cto holder with a session running now (arch1)", text)
        self.assertIn(f"`AUTHORIZES: O/R#7@{self.HEAD[:8]}`", text)

    def test_a_rejected_waiver_says_the_waiver_role_its_holders_and_the_waives_line(self):
        text = self.refusal(claude_only({"commits": {"min": 1}}), extra=("--no-boundary", "why", "--waiver", "w-1"), waiver_role="architect-cto",
                            replay=grant(field="WAIVES"), presence=presence_of(role="web-dev"), fleet=fleet_of(("arch1", "architect-cto", True)))
        self.assertIn("who holds web-dev, not architect-cto", text)
        self.assertIn("ask an architect-cto holder with a session running now (arch1)", text)
        self.assertIn(f"`WAIVES: O/R#7@{self.HEAD[:8]}`", text)
        self.assertIn("--waiver <id>", text)

    def test_a_refusal_no_word_can_lift_says_what_must_change_and_names_no_person_to_ask(self):
        policy = claude_only({"commits": {"min": 1}})
        for label, kw, words, p in (
                ("no review of the head", {"reviewed": False}, "dispatch the review class on", policy),
                ("an open thread", {"unresolved": 2}, "answer and resolve them first", policy),
                ("a red check", {"checks": "red:ci", "files": ("docs/a.md",)}, "every check on the head must be green first", policy),
                ("drift", {"drift": ["ruleset 'x' is missing"], "files": ("docs/a.md",)}, "fabric-repo-policy plan", policy),
                ("owner-only", {"files": ("docs/a.md",)}, "the mode must change in the repository's file", claude_only({"mode": "owner-only"})),
                ("below_min refuse", {"files": ("docs/a.md",)}, "refuses below the minimum", claude_only({"commits": {"min": 8, "below_min": "refuse"}}))):
            text = self.refusal(p, **kw) if label != "below_min refuse" else self.refusal(p, work=3, **kw)
            self.assertIn(words, text, label)
            self.assertNotIn("ask the owner", text, label)
            self.assertNotIn("ask a ", text, label)

    def test_the_holders_come_from_one_fleet_read_by_a_program_with_an_argument_list(self):
        policy = claude_only({"commits": {"min": 1, "boundary_authority": "architect-cto"}})
        self.refusal(policy, fleet=fleet_of(("arch1", "architect-cto", True)))
        self.assertEqual([r for r in self.reads if r[0] == "fleet"], [("fleet", ["all", "presence", "--json"])])

    def test_the_authors_role_minimum_applies_when_every_commit_is_stamped_with_it(self):
        p = claude_only({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}}}})
        rc, out = self.run_arm(p, 2, role_trailers=["web-dev", "web-dev"], presence=HOLDS_WEB_DEV, extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        rc, _ = self.run_arm(p, 1, role_trailers=["web-dev"], presence=HOLDS_WEB_DEV)
        self.assertIn("under 2 arms only on the owner's word", str(rc))

    def test_a_merge_commit_has_no_role_of_its_own_and_does_not_hide_the_authors(self):
        p = claude_only({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}}}})
        rc, out = self.run_arm(p, 2, role_trailers=["web-dev", "MERGE", "web-dev"], presence=HOLDS_WEB_DEV, extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_no_role_several_roles_or_an_unstamped_commit_is_the_repositorys_minimum(self):
        p = claude_only({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}, "rust-dev": {"min": 2}}}})
        for trailers in (None, ["web-dev", "rust-dev"], ["web-dev", None], ["unknown-role"]):
            rc, _ = self.run_arm(p, 2, role_trailers=trailers)
            self.assertIn("under 8 arms only on the owner's word", str(rc), trailers)

    def test_a_typed_role_the_branchs_login_does_not_hold_is_the_repositorys_minimum(self):
        p = claude_only({"commits": {"min": 8, "roles": {"brand-comms": {"min": 1}}}})
        for label, kw, said in (
                ("another role", {"presence": presence_of(role="devex-tooling", login="me")}, "me, whose branch it is, holds devex-tooling"),
                ("no role", {"presence": presence_of(role="", login="me")}, "me, whose branch it is, holds no role"),
                ("another host", {"presence": presence_of(role="brand-comms", login="me"), "branch": "elsewhere/me/feat/x", "extra": ("--any-owner",)}, "names elsewhere/me, but presence places me on h"),
                ("a branch named for nobody", {"branch": "fix-x", "extra": ("--any-owner",)}, "names no <host>/<login>/")):
            rc, out = self.run_arm(p, 2, role_trailers=["brand-comms"], **kw)
            self.assertIn("under 8 arms only on the owner's word", str(rc), label)
            self.assertIn(said, out, label)
        rc, out = self.run_arm(p, 2, role_trailers=["brand-comms"], presence=presence_of(role="brand-comms", login="me"), extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertEqual([r for r in self.reads if r[0] == "presence"], [("presence", ["me", "presence", "--json"])])

    def test_presence_that_cannot_say_stops_an_arm_the_role_would_lower_and_no_other(self):
        p = claude_only({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}}}})
        rc, _ = self.run_arm(p, 2, role_trailers=["web-dev"], presence=(1, ""))
        self.assertIn("unanswered: fabric-ctl could not say which role me holds", str(rc))
        self.assertIn("the role web-dev the commits carry cannot be checked", str(rc))
        # A role the floor does not turn on is never checked: a boundary, a role the policy does not name, a class.
        for kw in ({"files": ("policies/x.json",)}, {"role_trailers": ["rust-dev"]}):
            self.run_arm(p, 2, **{"role_trailers": ["web-dev"], **kw})
            self.assertEqual([r for r in self.reads if r[0] == "presence"], [], kw)
        rc, out = self.run_arm(claude_only({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}}, "classes": {"docs": {"paths": r"\.md$", "min": 1}}}}),
                               2, role_trailers=["web-dev"], body="Class: docs", classes={"docs": r"\.md$"}, extra=("--dry-run",))
        self.assertEqual((rc, [r for r in self.reads if r[0] == "presence"]), (0, []), out)

    def test_a_role_minimum_above_the_repositorys_stands_with_no_presence_read(self):
        # #312 review F1: presence was asked whenever the role's minimum differed, so a login presence placed in
        # another role armed at the repository's 8 where the role's 12 stood, and presence that could not answer
        # stopped an arm the role only raised.
        p = claude_only({"commits": {"min": 8, "roles": {"web-dev": {"min": 12}}}})
        for label, presence in (("another role", presence_of(role="devex-tooling", login="me")), ("no answer", (1, ""))):
            rc, _ = self.run_arm(p, 9, role_trailers=["web-dev"] * 9, presence=presence)
            self.assertIn("under 12 arms only on the owner's word", str(rc), label)
            self.assertEqual([r for r in self.reads if r[0] in ("presence", "fleet")], [], label)

    def test_a_role_only_lowers_a_non_boundary_pull_request(self):
        p = claude_only({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}}}})
        rc, _ = self.run_arm(p, 2, files=("policies/x.json",), role_trailers=["web-dev"])
        self.assertIn("a security-boundary change under 8", str(rc))

    def test_owner_only_is_refused_before_anything_else_is_read(self):
        rc, _ = self.run_arm(claude_only({"mode": "owner-only"}), 20, basis="the owner's word")
        self.assertIn("owner-only", str(rc))
        self.assertTrue(str(rc).startswith("refused"), rc)

    def test_direct_merges_at_once_pinned_to_the_head_with_no_auto(self):
        merged = {"state": "MERGED", "autoMergeRequest": None}
        p = claude_only({"mode": "direct", "commits": {"min": 1}})
        rc, out = self.run_arm(p, 1, live=merged)
        self.assertEqual(rc, 0, out)
        self.assertIn("MERGED #7", out)
        self.assertIn(["pr", "merge", "7", "--merge", "--match-head-commit", self.HEAD], self.ran)
        self.assertFalse([r for r in self.ran if "--auto" in r], self.ran)
        _, out = self.run_arm(p, 1, extra=("--dry-run",))
        self.assertIn(f"would run: gh pr merge 7 --merge --match-head-commit {self.HEAD}", out)
        self.assertFalse([r for r in self.ran if r[:2] == ["pr", "merge"]], self.ran)

    def test_direct_keeps_every_gate(self):
        p = claude_only({"mode": "direct", "commits": {"min": 8}})
        merged = {"state": "MERGED", "autoMergeRequest": None}
        for label, kw, words in (
                ("a red check", {"checks": "red:ci", "basis": "the owner's word"}, "every check on the head must be green first"),
                # A command the operator can run as written: the PR and the head are in it (#283 round 5).
                ("no review of a boundary head", {"reviewed": False, "basis": "the owner's word", "files": ("policies/x.json",)},
                 f"dispatch the review class on a brief of a range ending at {self.HEAD}, then `fabric-pr post-review 7`"),
                ("an open thread on a boundary", {"unresolved": 1, "basis": "the owner's word", "files": ("policies/x.json",)},
                 "answer and resolve them first"),
                # Not a boundary file: a direct repository merges at once, so the head's review and its
                # threads are gated for every PR there (review of #212, F1).
                ("no review of a non-boundary head", {"reviewed": False, "basis": "the owner's word"},
                 "a PR on a direct repository (merged at once) with no review-class review"),
                ("an open thread on a non-boundary PR", {"unresolved": 1, "basis": "the owner's word"},
                 "a PR on a direct repository (merged at once) with 1 unresolved"),
                ("under the minimum without the word", {}, "on the owner's word")):
            rc, _ = self.run_arm(p, 3, live=merged, **kw)
            self.assertTrue(str(rc).startswith("refused"), (label, rc))
            self.assertIn(words, str(rc), label)
            self.assertFalse([r for r in self.ran if r[:2] == ["pr", "merge"]], label)
        rc, out = self.run_arm(p, 3, basis="the owner's word", live=merged)
        self.assertEqual(rc, 0, out)
        # A required check named in a direct policy holds nothing on GitHub (no ruleset): green is still waited for.
        with_checks = claude_only({"mode": "direct", "commits": {"min": 1}, "required_checks": [{"context": "ci"}]})
        # A waiver lifts the boundary's gate, never a direct repository's review gate (re-review of #212, 1).
        with mock.patch.object(arm, "verify_waiver", return_value=("h/holder", "m1")):
            rc, _ = self.run_arm(p, 9, files=("policies/x.json",), reviewed=False, live=merged, waiver_role="architect-cto",
                                 extra=("--no-boundary", "not a boundary", "--waiver", "m1"))
        self.assertTrue(str(rc).startswith("refused"), rc)
        self.assertFalse([r for r in self.ran if r[:2] == ["pr", "merge"]], "waived")
        # ...and still lifts the boundary minimum: a waived, reviewed boundary PR under 8 merges on a direct repository.
        low = claude_only({"mode": "direct", "commits": {"min": 1}})
        with mock.patch.object(arm, "verify_waiver", return_value=("h/holder", "m1")):
            rc, out = self.run_arm(low, 1, files=("policies/x.json",), live=merged, waiver_role="architect-cto",
                                   extra=("--no-boundary", "not a boundary", "--waiver", "m1"))
        self.assertEqual(rc, 0, out)
        # No check at all on a direct head: it merges on the head's review (the owner's rule for CI-less repositories).
        no_ci = claude_only({"mode": "direct", "commits": {"min": 1}})
        rc, out = self.run_arm(no_ci, 1, checks="none-yet", live=merged)
        self.assertEqual(rc, 0, out)
        self.assertIn("no check on the head", out)
        rc, _ = self.run_arm(no_ci, 1, checks="none-yet", reviewed=False, live=merged)
        self.assertTrue(str(rc).startswith("refused"), rc)
        # A repository with no required check that is not direct still waits for green.
        auto_none = claude_only({"mode": "auto", "commits": {"min": 1}})
        rc, _ = self.run_arm(auto_none, 1, checks="none-yet", live=merged)
        self.assertTrue(str(rc).startswith("refused"), rc)
        for checks in ("red:ci", "pending", "none-yet"):
            rc, _ = self.run_arm(with_checks, 3, checks=checks, live=merged)
            self.assertTrue(str(rc).startswith("refused"), (checks, rc))
            self.assertIn("is direct", str(rc))
            self.assertFalse([r for r in self.ran if r[:2] == ["pr", "merge"]], checks)

    def test_direct_that_does_not_read_back_merged_is_unanswered(self):
        p = claude_only({"mode": "direct", "commits": {"min": 1}})
        for live in ({"autoMergeRequest": None}, {"autoMergeRequest": {"enabledAt": "x"}}):
            rc, _ = self.run_arm(p, 1, live=live)
            self.assertTrue(str(rc).startswith("unanswered"), rc)
            self.assertIn("direct repository, not merged", str(rc))

    def test_the_merge_command_uses_the_policys_method(self):
        for method in ("merge", "squash", "rebase"):
            _, out = self.run_arm(claude_only({"method": method, "commits": {"min": 1}}), 3, extra=("--dry-run",))
            self.assertIn(f"gh pr merge 7 --{method} --auto --match-head-commit", out)
            self.run_arm(claude_only({"method": method, "commits": {"min": 1}}), 3)
            self.assertIn(["pr", "merge", "7", f"--{method}", "--auto", "--match-head-commit", self.HEAD], self.ran)

    def test_a_drift_that_bears_on_how_the_merge_is_held_refuses_and_names_it(self):
        p = claude_only({"commits": {"min": 1}})
        rc, _ = self.run_arm(p, 3, drift=["ruleset 'x' is missing"])
        self.assertIn("differ from its arming policy — ruleset 'x' is missing", str(rc))
        self.assertTrue(str(rc).startswith("refused"), rc)
        self.assertFalse([c for c in self.ran if c[:2] == ["pr", "merge"]])

    def test_an_advisory_drift_is_said_and_does_not_refuse(self):
        p = claude_only({"commits": {"min": 1}})
        rc, out = self.run_arm(p, 3, drift=["repository allow_squash_merge is True, the policy wants False (advisory)"], extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("arming policy, advisory: repository allow_squash_merge is True, the policy wants False", out)

    def test_settings_that_cannot_be_read_stop_the_arming_never_read_as_no_drift(self):
        rc, _ = self.run_arm(claude_only(), 9, drift_error="HTTP 403")
        self.assertIn("unanswered: O/R's GitHub settings cannot be compared with its arming policy (HTTP 403)", str(rc))

    def test_a_repository_with_no_required_check_waits_for_green_checks_on_the_head(self):
        p = claude_only({"commits": {"min": 1}})
        for checks in ("red:ci", "pending:2", "none-yet", "?"):
            rc, _ = self.run_arm(p, 3, checks=checks)
            self.assertIn("has no required check", str(rc), checks)
            self.assertIn(checks, str(rc))
        rc, out = self.run_arm(p, 3, checks="green", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)
        self.assertIn("no required check on this repository: every check on the head is green", out)

    def test_a_repository_with_a_required_check_leaves_the_checks_to_github(self):
        p = claude_only({"commits": {"min": 1}, "required_checks": [{"context": "ci-ok", "app": "github-actions"}]})
        rc, out = self.run_arm(p, 3, checks="pending:2", extra=("--dry-run",))
        self.assertEqual(rc, 0, out)

    def test_the_read_back_follows_the_mode(self):
        queued = {"mergeQueueEntry": {"position": 2}, "autoMergeRequest": None}
        _, out = self.run_arm(claude_only({"mode": "auto", "commits": {"min": 1}}), 3, live=queued)
        self.assertIn("note: the policy's mode is auto and GitHub put #7 in a merge queue", out)
        _, out = self.run_arm(claude_only({"mode": "queue", "commits": {"min": 1}}), 3, live=queued)
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
            return claude_only()
        real_with = arm_policy.with_classes
        seen = []
        with mock.patch.object(arm.arm_policy, "with_classes", lambda p, c: (seen.append(c), real_with(p, c))[1]):
            rc, out = self.run_arm(None, 9, classes={"docs": r"\.md$"}, load_fn=spy, extra=("--dry-run",))
        self.assertEqual((rc, loaded, seen), (0, ["O/R"], [{"docs": r"\.md$"}]), out)

    def test_the_role_is_read_from_the_trailer_block_only_not_from_any_line_of_the_message(self):
        p = claude_only({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}}}})
        stamped = [{"parents": [{}], "commit": {"message": "subject\n\nbody\n\nKind: work\nFabric-Role: web-dev"}}]
        quoted = [{"parents": [{}], "commit": {"message": "subject\n\nFabric-Role: web-dev\n\nand then prose follows"}}]
        for commits, role in ((stamped, "web-dev"), (quoted, None)):
            with mock.patch.object(arm.gh, "api", return_value=commits):
                self.assertEqual(arm.author_role("O/R", "7"), role)
        self.assertIsNotNone(p)

    def test_a_pull_request_at_githubs_listing_cap_has_no_role_read_from_a_part_of_it(self):
        commits = [{"parents": [{}], "commit": {"message": "c\n\nFabric-Role: web-dev"}}] * arm.PR_COMMITS_CAP
        with mock.patch.object(arm.gh, "api", return_value=commits):
            self.assertIsNone(arm.author_role("O/R", "7"))
        with mock.patch.object(arm.gh, "api", return_value=commits[:-1]):
            self.assertEqual(arm.author_role("O/R", "7"), "web-dev")

    def test_a_role_that_armed_below_the_repositorys_minimum_is_said_in_the_log_and_the_comment(self):
        p = claude_only({"commits": {"min": 8, "roles": {"web-dev": {"min": 2}}}})
        _, out = self.run_arm(p, 3, role_trailers=["web-dev"], presence=HOLDS_WEB_DEV, extra=("--dry-run",))
        self.assertIn("count rule: 3 work commits — the role web-dev's minimum is 2, arms at the review gate", out)
        self.assertNotIn("on the owner's word", out)
        self.assertIn("3 work commits, role: web-dev, head", out)
        _, out = self.run_arm(p, 9, role_trailers=["web-dev"], extra=("--dry-run",))
        self.assertNotIn("role: web-dev", out)
        _, out = self.run_arm(claude_only({"commits": {"min": 8}}), 3, role_trailers=["web-dev"], basis="the owner's word", extra=("--dry-run",))
        self.assertNotIn("role: web-dev", out)

    def test_the_mode_is_judged_before_the_settings_are_compared_or_the_commits_listed(self):
        called = []
        for mode in ("owner-only",):
            with mock.patch.object(arm, "author_role", side_effect=lambda *a, **k: called.append("role")):
                # The comparison stub fails: were it made first, the run would end unanswered, not refused.
                rc, _ = self.run_arm(claude_only({"mode": mode}), 20, basis="the owner's word", drift_error="HTTP 403")
            self.assertTrue(str(rc).startswith("refused"), rc)
        self.assertEqual(called, [])

    def test_the_merge_flag_is_a_fixed_table_not_the_policys_text(self):
        self.assertEqual(arm.MERGE_FLAGS, {"merge": "--merge", "squash": "--squash", "rebase": "--rebase"})
        self.assertEqual(set(arm.MERGE_FLAGS), set(arm_policy.METHODS))

    def test_an_author_whose_commits_cannot_be_listed_stops_the_arming(self):
        with mock.patch.object(arm.gh, "api", side_effect=gh.GhError("x", "boom")):
            with self.assertRaises(arm.Unanswered):
                arm.author_role("O/R", "7")

    # ── the word under the minimum from a role (commits.below_min_authority; the owner, 2026-10-19) ──
    BM = {"min": 8, "below_min_authority": "architect-cto"}

    def below(self, policy_extra=None, work=3, **kw):
        policy = claude_only({"commits": {**self.BM, **(policy_extra or {})}})
        kw.setdefault("files", ("docs/a.md",))
        return self.run_arm(policy, work, **kw)

    def test_below_min_authority_is_a_role_slug_absent_by_default(self):
        self.assertNotIn("below_min_authority", arm_policy.default()["commits"])
        self.assertEqual(arm_policy.validate({"commits": {"below_min_authority": "architect-cto"}})["commits"]["below_min_authority"], "architect-cto")
        for bad in ("Architect", "", 3, None, ["architect-cto"]):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate({"commits": {"below_min_authority": bad}})

    def test_authority_own_prs_is_a_boolean_absent_by_default(self):
        self.assertNotIn("authority_own_prs", arm_policy.default()["commits"])
        for good in (True, False):
            self.assertIs(arm_policy.validate({"commits": {"authority_own_prs": good}})["commits"]["authority_own_prs"], good)
        for bad in ("true", 1, 0, None):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate({"commits": {"authority_own_prs": bad}})

    def test_an_authorization_from_the_below_min_authority_arms_a_pr_under_the_minimum(self):
        rc, out = self.below(extra=(*self.AUTH, "--dry-run"), replay=grant(), presence=presence_of())
        self.assertEqual(rc, 0, out)
        self.assertIn("count gate AUTHORIZED by arch, architect-cto (01a12-grant), in the owner's place", out)
        self.assertIn("count rule: 3 work commits — under 8, authorized in the owner's place", out)
        self.assertIn(" Count gate authorized by arch, architect-cto (01a12-grant).", out)
        self.assertNotIn("Boundary count gate", out)

    def test_the_below_min_authority_does_not_lift_a_security_boundary_change(self):
        rc, _ = self.below(files=self.BOUNDARY, extra=(*self.AUTH, "--dry-run"), replay=grant(), presence=presence_of())
        self.assertIn("names no boundary_authority", str(rc))
        self.assertTrue(str(rc).startswith("refused"), rc)

    def test_a_boundary_authority_does_not_lift_a_plain_pr_under_the_minimum(self):
        policy = claude_only({"commits": {"min": 8, "boundary_authority": "architect-cto"}})
        rc, out = self.run_arm(policy, 3, extra=(*self.AUTH, "--dry-run"), replay=grant(), presence=presence_of())
        self.assertTrue(str(rc).startswith("refused"), rc)
        self.assertIn("is not read: an authorization stands in only for a security-boundary change", out)
        self.assertEqual(self.reads, [])

    def test_a_below_min_authority_authorization_is_refused_as_the_boundary_one_is(self):
        for label, kw, words in (
                ("another role", {"presence": presence_of(role="web-dev")}, "who holds web-dev, not architect-cto"),
                ("a stale head", {"replay": grant(target="O/R#7@0123456789ab")}, "head 0123456789ab"),
                ("a broadcast", {"replay": grant(to="")}, "a broadcast or a role address"),
                ("the arming login itself", {"replay": grant(sender="h/me")}, "the login arming"),
                ("the pull request's author", {"replay": grant(sender="h/arch"), "branch": "h/arch/feat/x"}, "the pull request's own author")):
            kw.setdefault("replay", grant())
            kw.setdefault("presence", presence_of())
            rc, _ = self.below(extra=("--any-owner", *self.AUTH, "--dry-run"), **kw)
            self.assertTrue(str(rc).startswith("refused"), (label, rc))
            self.assertIn(words, str(rc), label)

    def test_a_session_holding_the_authority_role_arms_on_its_word_by_its_binding(self):
        for label, kw in (("a plain PR", {}), ("a boundary change", {"files": self.BOUNDARY, "policy_extra": {"boundary_authority": "architect-cto"}})):
            rc, out = self.below(basis="architect-cto's word", extra=("--any-owner", "--dry-run"), whoami=whoami_of(), branch="h/dev/feat/x", **kw)
            self.assertEqual(rc, 0, (label, out))
            self.assertIn("count gate lifted by me, who holds architect-cto by its binding, in the owner's place", out)
            self.assertIn("lifted by me, holding architect-cto by its binding.", out)
            self.assertEqual([r[0] for r in self.reads], ["whoami"], label)
            self.assertEqual(self.reads[0][1], ["--json"])
        self.assertIn("Boundary count gate lifted by me", out)

    def test_a_policy_with_only_boundary_authority_lets_its_holder_arm_a_boundary_change_by_the_binding_and_nothing_else(self):
        policy = claude_only({"commits": {"min": 8, "boundary_authority": "architect-cto"}})
        common = dict(extra=("--any-owner", "--dry-run"), whoami=whoami_of(), branch="h/dev/feat/x", basis="architect-cto's word")
        rc, out = self.run_arm(policy, 3, files=self.BOUNDARY, **common)
        self.assertEqual(rc, 0, out)
        rc, _ = self.run_arm(policy, 3, files=("docs/a.md",), **common)
        self.assertTrue(str(rc).startswith("refused"), rc)

    def test_the_binding_is_what_counts_not_the_basis_or_a_message(self):
        for label, who in (("another role", whoami_of(role="web-dev")), ("no role", whoami_of(role=None))):
            rc, _ = self.below(basis="architect-cto's word", extra=("--any-owner", "--dry-run"), whoami=who, branch="h/dev/feat/x")
            self.assertTrue(str(rc).startswith("refused"), (label, rc))
            self.assertIn(f"this session holds {'web-dev' if who is not None and 'web-dev' in who[1] else 'no role'} by its binding, not architect-cto", str(rc))
            self.assertIn("ask an architect-cto holder", str(rc))
        for label, who in (("unreadable", (1, "")), ("not json", (0, "x")), ("another address", whoami_of(address="h/other"))):
            rc, _ = self.below(basis="architect-cto's word", extra=("--any-owner", "--dry-run"), whoami=who, branch="h/dev/feat/x")
            self.assertTrue(str(rc).startswith("unanswered"), (label, rc))

    def test_the_basis_must_say_the_authoritys_word_and_not_another_roles(self):
        for basis in ("reviewed", "web-dev's word", "not-architect-cto's word", "architect-cto asked"):
            # not the author's own session, so only the phrase can be what refuses
            rc, _ = self.below(basis=basis, extra=("--any-owner", "--dry-run"), whoami=whoami_of(), branch="h/dev/feat/x")
            self.assertTrue(str(rc).startswith("refused"), (basis, rc))
            self.assertEqual([r for r in self.reads if r[0] == "whoami"], [], basis)
        rc, out = self.below(basis="Architect-CTO’s word", extra=("--any-owner", "--dry-run"), whoami=whoami_of(), branch="h/dev/feat/x")
        self.assertEqual(rc, 0, out)

    def test_an_authority_never_arms_its_own_pr_unless_the_policy_says_so(self):
        for basis, extra, kw in (("architect-cto's word", ("--dry-run",), {"whoami": whoami_of()}),
                                 ("reviewed", (*self.AUTH, "--any-owner", "--dry-run"), {"replay": grant(sender="h/arch"), "presence": presence_of()})):
            branch = "h/me/feat/x" if "--any-owner" not in extra else "h/arch/feat/x"
            rc, _ = self.below(basis=basis, extra=extra, branch=branch, **kw)
            self.assertTrue(str(rc).startswith("refused"), (basis, rc))
            self.assertIn("own author", str(rc))
            rc, out = self.below({"authority_own_prs": True}, basis=basis, extra=extra, branch=branch, **kw)
            self.assertEqual(rc, 0, (basis, out))
        # the boundary path keeps the same constant
        rc, _ = self.below({"boundary_authority": "architect-cto"}, basis="architect-cto's word", files=self.BOUNDARY, extra=("--dry-run",), whoami=whoami_of())
        self.assertIn("own author", str(rc))
        rc, out = self.below({"boundary_authority": "architect-cto", "authority_own_prs": True}, basis="architect-cto's word", files=self.BOUNDARY,
                             extra=("--dry-run",), whoami=whoami_of())
        self.assertEqual(rc, 0, out)

    def test_authority_own_prs_does_not_let_the_arming_login_send_itself_the_authorization(self):
        rc, _ = self.below({"authority_own_prs": True}, extra=(*self.AUTH, "--dry-run"), replay=grant(sender="h/me"), presence=presence_of())
        self.assertIn("the login arming", str(rc))

    def test_a_branch_not_named_for_its_author_is_refused_unless_own_prs_makes_the_author_moot(self):
        rc, _ = self.below(basis="architect-cto's word", extra=("--any-owner", "--dry-run"), whoami=whoami_of(), branch="fix-x")
        self.assertIn("the pull request's author cannot be told from its branch", str(rc))
        rc, out = self.below({"authority_own_prs": True}, basis="architect-cto's word", extra=("--any-owner", "--dry-run"), whoami=whoami_of(), branch="fix-x")
        self.assertEqual(rc, 0, out)

    def test_the_refusal_names_the_authority_its_running_holder_and_the_basis_before_the_owner(self):
        text = self.refusal(claude_only({"commits": self.BM}), files=("docs/a.md",), fleet=fleet_of(("arch1", "architect-cto", True), ("dev", "web-dev", True)))
        self.assertIn("ask an architect-cto holder with a session running now (arch1)", text)
        self.assertIn(f"`AUTHORIZES: O/R#7@{self.HEAD[:8]}`", text)
        self.assertIn("--basis \"architect-cto's word\"", text)
        self.assertLess(text.index("architect-cto's word"), text.index("ask the owner"))
        text = self.refusal(claude_only({"commits": {**self.BM, "classes": {"big": {"paths": r"^docs/", "min": 10}}}}), files=("docs/a.md",),
                            body="Class: big", work=9, classes={"big": r"^docs/"},
                            fleet=fleet_of(("arch1", "architect-cto", True)))
        self.assertIn("ask an architect-cto holder", text)

    def test_an_author_who_may_arm_its_own_pr_is_named_as_a_holder_to_ask_and_one_who_may_not_is_not(self):
        fleet = fleet_of(("arch", "architect-cto", True), ("arch2", "architect-cto", True))
        text = self.refusal(claude_only({"commits": self.BM}), files=("docs/a.md",), branch="h/arch/feat/x", extra=("--any-owner",), fleet=fleet)
        self.assertIn("session running now (arch2)", text)
        text = self.refusal(claude_only({"commits": {**self.BM, "authority_own_prs": True}}), files=("docs/a.md",), branch="h/arch/feat/x",
                            extra=("--any-owner",), fleet=fleet)
        self.assertIn("session running now (arch, arch2)", text)

    def test_the_authority_is_not_offered_when_the_catalogue_does_not_hold_it(self):
        text = self.refusal(claude_only({"commits": {"min": 8, "below_min_authority": "no-such-role"}}), files=("docs/a.md",))
        self.assertIn("the policy names the below_min_authority 'no-such-role', which is not a role of identities/roles/catalog.json", text)
        rc, _ = self.below({"below_min_authority": "no-such-role"}, basis="no-such-role's word", extra=("--dry-run",), whoami=whoami_of(role="no-such-role"))
        self.assertTrue(str(rc).startswith("unanswered"), rc)

    def test_the_owners_word_still_arms_and_the_authority_is_not_read(self):
        rc, out = self.below(basis="the owner's word", extra=(*self.AUTH, "--dry-run"))
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.reads, [])

    def test_below_min_refuse_is_not_lifted_by_the_below_min_authority(self):
        rc, _ = self.below({"below_min": "refuse"}, basis="architect-cto's word", extra=("--any-owner", "--dry-run"), whoami=whoami_of(), branch="h/dev/feat/x")
        self.assertIn("refuses below the minimum", str(rc))

    def test_the_review_gate_stands_under_the_binding_word_on_a_boundary_change(self):
        for kw in ({"unresolved": 1}, {"reviewed": False}):
            rc, _ = self.below({"boundary_authority": "architect-cto"}, basis="architect-cto's word", files=self.BOUNDARY, extra=("--dry-run",),
                               whoami=whoami_of(), branch="h/dev/feat/x", **kw)
            self.assertTrue(str(rc).startswith("refused"), (kw, rc))
            self.assertEqual(self.reads, [])


if __name__ == "__main__":
    unittest.main()
