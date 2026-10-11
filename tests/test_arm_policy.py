#!/usr/bin/env python3
"""tools/fabric/github/arm_policy.py (arming policy, step A): the document and its validation, the two layers
and their merge, the fetch of a repository's file from the settings repository (and what an absent file, an
unreadable one and a bad one each mean), the order of specificity of threshold(), render() against GitHub's ruleset
as agent-fabric has it, and arm.py's and pr_gate.py's count rules reading their numbers through it. The count
rule at the default numbers is test_arm_cli's, unchanged. No network: the contents API is a function that records
what it was asked; arm.py runs in process with its calls to gh and the readers replaced."""
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
from github import arm, arm_policy, pr_gate  # noqa: E402

RULESET = os.path.join(HERE, "tools", "fabric", "github-ruleset-main.json")
# What agent-fabric's policy file in the settings repository says, which is what github-ruleset-main.json is today.
FABRIC_POLICY = {"required_checks": ["ci-ok"], "app": 15368, "signatures": True}


def contents(doc) -> dict:
    """The contents API's answer for a file holding `doc` (text, or JSON of it)."""
    text = doc if isinstance(doc, str) else json.dumps(doc)
    return {"type": "file", "encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


class Api:
    """A fake gh.api: answers by path, records every path it was asked, raises what it is told to."""

    def __init__(self, answer=None, error: gh.GhError | None = None):
        self.answer, self.error, self.asked = answer, error, []

    def __call__(self, path, **kw):
        self.asked.append(path)
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

    def fleet(self, doc) -> None:
        with open(os.path.join(self.dir, "policies", "arming.json"), "w") as fh:
            fh.write(doc if isinstance(doc, str) else json.dumps(doc))


class Document(unittest.TestCase):
    def test_the_default_is_the_behaviour_before_the_policy(self):
        d = arm_policy.default()
        self.assertEqual(d["commits"], {"min": 8, "advice_over": 16, "below_min": "owner-word"})
        self.assertEqual((d["mode"], d["method"], d["roles"], d["classes"]), ("auto", "merge", {}, {}))

    def test_a_partial_document_is_completed_from_the_default_and_the_default_is_not_changed(self):
        p = arm_policy.validate({"commits": {"min": 3}})
        self.assertEqual(p["commits"], {"min": 3, "advice_over": 16, "below_min": "owner-word"})
        self.assertEqual(arm_policy.DEFAULT["commits"]["min"], 8)

    def test_an_unknown_key_anywhere_it_is_checked_is_refused_not_ignored(self):
        for bad in ({"colour": 1}, {"commits": {"mn": 3}}, {"queue": {"x": 1}}, {"roles": {"web-dev": {"min": 2, "x": 1}}},
                    {"classes": {"docs": {"paths": "x", "min": 1, "x": 1}}}):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate(bad)

    def test_the_schema_and_description_keys_are_for_the_reader(self):
        self.assertEqual(arm_policy.validate({"$schema": "x", "description": "y"}), arm_policy.default())

    def test_values_of_the_wrong_kind_or_range_are_refused(self):
        for bad in ({"mode": "fast"}, {"method": "ff"}, {"commits": {"min": 0}}, {"commits": {"min": True}}, {"commits": {"min": 2.5}},
                    {"commits": {"min": "8"}}, {"commits": {"min": 9, "advice_over": 8}}, {"commits": {"below_min": "nobody"}},
                    {"roles": {"Web Dev": {"min": 2}}}, {"roles": {"web-dev": {"min": 0}}}, {"roles": {"web-dev": 2}}, {"roles": []},
                    {"required_checks": ["a", "a"]}, {"required_checks": [""]}, {"required_checks": "ci-ok"}, {"required_checks": [3]},
                    {"app": 0}, {"app": True}, {"app": "15368"}, {"signatures": "yes"}, {"delete_branch_on_merge": 1},
                    {"protect": ["deletion", "deletion"]}, {"protect": ["force_push"]}, {"ruleset_name": " "}, {"ruleset_name": 3},
                    {"queue": {**arm_policy.DEFAULT["queue"], "merge_method": "FF"}},
                    {"queue": {**arm_policy.DEFAULT["queue"], "grouping_strategy": "ANY"}},
                    {"queue": {**arm_policy.DEFAULT["queue"], "max_entries_to_build": 0}},
                    {"queue": {**arm_policy.DEFAULT["queue"], "min_entries_to_merge": 9, "max_entries_to_merge": 2}}, 7, [], "x", None):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate(bad)

    def test_the_older_class_form_is_a_class_with_a_minimum_of_one_and_names_may_have_spaces(self):
        p = arm_policy.validate({"classes": {"Single-Check Tooling": r"^tools/", "docs": {"paths": r"\.md$", "min": 3}}})
        self.assertEqual(p["classes"], {"single-check tooling": {"paths": "^tools/", "min": 1}, "docs": {"paths": r"\.md$", "min": 3}})

    def test_a_class_that_is_not_one_is_refused(self):
        for bad in ({"a": {"paths": "("}}, {"a": {"paths": 3}}, {"a": {"min": 2}}, {"a": {"paths": "x", "min": 0}}, {"a": 3},
                    {"A": "x", "a": "y"}, {" a": "x"}, {"": "x"}):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                arm_policy.validate({"classes": bad})


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
        self.fleet({"roles": {"web-dev": {"min": 2}}, "required_checks": ["a", "b"], "commits": {"min": 5}})
        api = Api(contents({"roles": {"rust-dev": {"min": 3}}, "required_checks": ["c"], "commits": {"advice_over": 20}}))
        p = arm_policy.load("o/r", root=self.dir, registry={"settings_repo": "o/settings"}, api=api)
        self.assertEqual(p["roles"], {"web-dev": {"min": 2}, "rust-dev": {"min": 3}})
        self.assertEqual(p["required_checks"], ["c"])
        self.assertEqual(p["commits"], {"min": 5, "advice_over": 20, "below_min": "owner-word"})


class Load(Scratch):
    REG = {"settings_repo": "o/settings"}

    def load(self, api, repo="o/r", registry=None, cache=None):
        return arm_policy.load(repo, root=self.dir, registry=self.REG if registry is None else registry, api=api, cache=cache)

    def test_no_settings_repository_is_the_fleet_policy_and_no_call_is_made(self):
        api = Api(error=ghe(500))
        self.assertEqual(self.load(api, registry={"projects": {}}), arm_policy.default())
        self.assertEqual(api.asked, [])

    def test_no_repository_is_the_fleet_policy(self):
        self.assertEqual(arm_policy.load(None, root=self.dir, registry=self.REG, api=Api(error=ghe(500))), arm_policy.default())

    def test_the_file_is_asked_for_by_path_from_the_default_branch_never_a_ref(self):
        api = Api(contents({"commits": {"min": 2}}))
        p = self.load(api)
        self.assertEqual(api.asked, ["repos/o/settings/contents/repos/o/r.json"])
        self.assertEqual(p["commits"]["min"], 2)

    def test_no_file_for_the_repository_is_the_fleet_policy(self):
        self.assertEqual(self.load(Api(error=ghe(404, "Not Found"))), arm_policy.default())

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
        self.assertIn("o/settings repos/o/r.json", str(cm.exception))

    def test_a_repository_name_that_could_walk_the_path_is_refused_before_any_call(self):
        api = Api(contents({}))
        for bad in ("../x", "o/r/../../x", "o/r?ref=evil", "o", "o/r r", ""):
            if not bad:
                continue
            with self.assertRaises(arm_policy.PolicyUnavailable, msg=bad):
                self.load(api, repo=bad)
        self.assertEqual(api.asked, [])

    def test_a_settings_repository_that_is_not_a_name_is_an_error(self):
        for bad in ("x", "a/b/c", 3, ["a/b"], ""):
            with self.assertRaises(arm_policy.PolicyError, msg=repr(bad)):
                self.load(Api(contents({})), registry={"settings_repo": bad})

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

    def test_the_registry_is_read_when_not_given_and_its_failure_is_unavailable(self):
        import workingcopy
        with mock.patch.object(workingcopy, "load_registry", side_effect=OSError("gone")):
            with self.assertRaises(arm_policy.PolicyUnavailable):
                arm_policy.load("o/r", root=self.dir, api=Api(contents({})))
        with mock.patch.object(workingcopy, "load_registry", return_value=self.REG):
            self.assertEqual(arm_policy.load("o/r", root=self.dir, api=Api(contents({"commits": {"min": 4}})))["commits"]["min"], 4)


class Threshold(unittest.TestCase):
    P = arm_policy.validate({"commits": {"min": 8}, "roles": {"web-dev": {"min": 4}, "rust-dev": {"min": 12}},
                             "classes": {"docs": {"paths": r"\.md$", "min": 2}, "tooling": r"^tools/"}})

    def test_the_repositorys_minimum_when_nothing_more_specific_applies(self):
        self.assertEqual(arm_policy.threshold(self.P, None, "", False), 8)
        self.assertEqual(arm_policy.threshold(self.P, "python-dev", "", False), 8)

    def test_the_role_over_the_repository_and_the_class_over_the_role(self):
        self.assertEqual(arm_policy.threshold(self.P, "web-dev", "", False), 4)
        self.assertEqual(arm_policy.threshold(self.P, "rust-dev", "", False), 12)
        self.assertEqual(arm_policy.threshold(self.P, "rust-dev", "docs", False), 2)
        self.assertEqual(arm_policy.threshold(self.P, "web-dev", "tooling", False), 1, "the older form is a minimum of one")

    def test_a_boundary_not_waived_is_the_repositorys_minimum_whatever_the_role_or_the_class(self):
        for role, cls in ((None, ""), ("web-dev", ""), ("rust-dev", ""), ("web-dev", "docs"), ("rust-dev", "tooling")):
            self.assertEqual(arm_policy.threshold(self.P, role, cls, True), 8, (role, cls))

    def test_a_class_the_policy_does_not_have_is_an_error_not_the_repositorys_minimum(self):
        with self.assertRaises(arm_policy.PolicyError):
            arm_policy.threshold(self.P, None, "nothing", False)

    def test_classes_from_arm_json_are_added_under_the_policys_own(self):
        p = arm_policy.with_classes(self.P, {"tooling": "^other/", "ddl": "^db/"})
        self.assertEqual(p["classes"]["tooling"], {"paths": "^tools/", "min": 1})
        self.assertEqual(p["classes"]["ddl"], {"paths": "^db/", "min": 1})
        self.assertNotIn("ddl", self.P["classes"], "the policy given is not changed")


class Render(unittest.TestCase):
    def test_agent_fabrics_policy_renders_the_ruleset_it_has(self):
        with open(RULESET, encoding="utf-8") as fh:
            want = json.load(fh)
        self.assertEqual(arm_policy.render(arm_policy.validate(FABRIC_POLICY))["ruleset"], want)

    def test_the_repository_fields_follow_the_method(self):
        for method, field in (("merge", "allow_merge_commit"), ("squash", "allow_squash_merge"), ("rebase", "allow_rebase_merge")):
            r = arm_policy.render(arm_policy.validate({"method": method, "delete_branch_on_merge": True}))
            self.assertEqual(r["repository"], {"allow_auto_merge": True, "delete_branch_on_merge": True,
                                               **{f: f == field for f in ("allow_merge_commit", "allow_squash_merge", "allow_rebase_merge")}})
            pull_request = next(x for x in r["ruleset"]["rules"] if x["type"] == "pull_request")
            self.assertEqual(pull_request["parameters"]["allowed_merge_methods"], [method])

    def test_a_queue_adds_the_merge_queue_rule_with_its_parameters_and_auto_does_not(self):
        q = {**arm_policy.DEFAULT["queue"], "merge_method": "SQUASH", "grouping_strategy": "HEADGREEN", "max_entries_to_build": 3,
             "min_entries_to_merge": 2, "min_entries_to_merge_wait_minutes": 10, "check_response_timeout_minutes": 30}
        rules = arm_policy.render(arm_policy.validate({"mode": "queue", "queue": q}))["ruleset"]["rules"]
        self.assertEqual([x["parameters"] for x in rules if x["type"] == "merge_queue"], [q])
        self.assertEqual(arm_policy.render(arm_policy.validate({"mode": "queue"}))["repository"]["allow_auto_merge"], True)
        self.assertNotIn("merge_queue", [x["type"] for x in arm_policy.render(arm_policy.default())["ruleset"]["rules"]])

    def test_checks_app_signatures_and_protection_are_each_a_rule_only_when_asked(self):
        types = lambda doc: [x["type"] for x in arm_policy.render(arm_policy.validate(doc))["ruleset"]["rules"]]  # noqa: E731
        self.assertEqual(types({}), ["deletion", "non_fast_forward", "pull_request"])
        self.assertEqual(types({"protect": []}), ["pull_request"])
        self.assertEqual(types({"protect": ["deletion"], "required_checks": ["a"], "signatures": True}),
                         ["deletion", "pull_request", "required_status_checks", "required_signatures"])
        rule = next(x for x in arm_policy.render(arm_policy.validate({"required_checks": ["a", "b"]}))["ruleset"]["rules"]
                    if x["type"] == "required_status_checks")
        self.assertEqual(rule["parameters"]["required_status_checks"], [{"context": "a"}, {"context": "b"}], "no app: no integration id")
        rule = next(x for x in arm_policy.render(arm_policy.validate({"required_checks": ["a"], "app": 7}))["ruleset"]["rules"]
                    if x["type"] == "required_status_checks")
        self.assertEqual(rule["parameters"]["required_status_checks"], [{"context": "a", "integration_id": 7}])

    def test_the_ruleset_is_named_and_aimed_at_the_default_branch(self):
        rs = arm_policy.render(arm_policy.validate({"ruleset_name": "protect"}))["ruleset"]
        self.assertEqual((rs["name"], rs["conditions"]["ref_name"]["include"], rs["bypass_actors"], rs["enforcement"]),
                         ("protect", ["~DEFAULT_BRANCH"], [], "active"))

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
        text = self.v(9, "o/settings repos/o/r.json could not be read (HTTP 500)")
        self.assertIn("the arming policy cannot be read (o/settings repos/o/r.json could not be read (HTTP 500))", text)
        self.assertNotIn("arm: post", text)


class ArmCountRule(unittest.TestCase):
    """arm.arm() in process, with everything it reads replaced: the count rule's numbers are the policy's."""
    HEAD = "abcdef1234567890abcdef1234567890abcdef12"

    def run_arm_with(self, load, work, **kw):
        return self.run_arm(None, work, load_fn=load, **kw)

    def run_arm(self, policy, work, files=("docs/a.md",), basis="reviewed", body="", boundary_re=r"^policies/", classes=None,
                load_error=None, extra=(), load_fn=None):
        pr = {"number": 7, "state": "OPEN", "isDraft": False, "headRefName": "h/me/feat/x", "headRefOid": self.HEAD, "body": body, "title": "t"}
        gate = [{"commits_known": True, "work_commits": work}]
        review = {"blind": {"rows": [{"commit_sha8": self.HEAD[:8]}]}, "unresolved_threads": 0}

        def reader(head, args, timeout=600):
            return (0, json.dumps(review if "review-status" in " ".join(head) else gate))
        classes = {k: re.compile(v) for k, v in (classes or {}).items()}
        load = load_fn or (mock.Mock(side_effect=load_error) if load_error else mock.Mock(return_value=policy))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(arm.shutil, "which", return_value="/bin/gh"))
            st.enter_context(mock.patch.object(arm.gh, "run", return_value=json.dumps(pr)))
            st.enter_context(mock.patch.object(arm.gh, "this_repo", return_value="o/r"))
            st.enter_context(mock.patch.object(arm.gh, "api", return_value=[{"filename": f} for f in files]))
            st.enter_context(mock.patch.object(arm.pr_gate, "session_prefix", return_value="h/me"))
            st.enter_context(mock.patch.object(arm, "config_path", return_value="x"))
            st.enter_context(mock.patch.object(arm, "load_config", return_value=(re.compile(boundary_re), None, classes, None)))
            st.enter_context(mock.patch.object(arm, "run_reader", side_effect=reader))
            st.enter_context(mock.patch.object(arm.arm_policy, "load", load))
            st.enter_context(contextlib.redirect_stdout(out))
            st.enter_context(contextlib.redirect_stderr(err))
            try:
                rc = arm.arm(["7", "--basis", basis, "--dry-run", *extra])
            except arm.Refused as e:
                rc = f"refused: {e}"
            except arm.Unanswered as e:
                rc = f"unanswered: {e}"
        return rc, out.getvalue()

    def test_the_minimum_is_the_policys(self):
        p = arm_policy.validate({"commits": {"min": 3, "advice_over": 5}})
        rc, out = self.run_arm(p, 3)
        self.assertEqual(rc, 0, out)
        self.assertIn("count rule: 3 work commits — 3 or more, arms at the review gate", out)
        rc, _ = self.run_arm(p, 2)
        self.assertIn("under 3 arms only on the owner's word", str(rc))
        rc, out = self.run_arm(p, 2, basis="the owner's word")
        self.assertEqual(rc, 0, out)
        self.assertIn("under 3, on the owner's word", out)

    def test_the_advice_threshold_is_the_policys(self):
        p = arm_policy.validate({"commits": {"min": 3, "advice_over": 5}})
        _, out = self.run_arm(p, 6)
        self.assertIn("6 work commits — over 5: smaller batches next time", out)
        _, out = self.run_arm(p, 5)
        self.assertNotIn("smaller batches", out)

    def test_a_boundary_is_judged_against_the_repositorys_minimum_and_marked_with_it(self):
        p = arm_policy.validate({"commits": {"min": 3, "advice_over": 5}, "roles": {"web-dev": {"min": 1}}})
        rc, out = self.run_arm(p, 2, files=("policies/x.json",))
        self.assertIn("a security-boundary change under 3 arms only on the owner's word", str(rc))
        rc, out = self.run_arm(p, 3, files=("policies/x.json",))
        self.assertEqual(rc, 0, out)
        self.assertIn("Security boundary, armed on the count rule (3 or more work commits) without the owner's word.", out)

    def test_a_stated_class_arms_at_its_own_minimum_and_below_it_asks_for_the_word(self):
        p = arm_policy.validate({"commits": {"min": 8}, "classes": {"docs": {"paths": r"\.md$", "min": 3}}})
        body = "Class: docs"
        rc, out = self.run_arm(p, 3, body=body, classes={"docs": r"\.md$"})
        self.assertEqual(rc, 0, out)
        rc, _ = self.run_arm(p, 2, body=body, classes={"docs": r"\.md$"})
        self.assertIn("the class docs arms at 3 or more", str(rc))
        rc, out = self.run_arm(p, 2, body=body, classes={"docs": r"\.md$"}, basis="the owner's word")
        self.assertEqual(rc, 0, out)

    def test_an_arm_json_class_arms_at_one_as_before_and_a_boundary_is_not_lowered_by_it(self):
        p = arm_policy.default()
        rc, out = self.run_arm(p, 1, body="Class: docs", classes={"docs": r"\.md$"})
        self.assertEqual(rc, 0, out)
        rc, _ = self.run_arm(p, 1, files=("policies/a.md",), body="Class: docs", classes={"docs": r"\.md$"})
        self.assertIn("a security-boundary change under 8", str(rc))

    def test_a_policy_that_cannot_be_read_stops_the_arming_and_is_never_the_default(self):
        for e in (arm_policy.PolicyUnavailable("o/settings repos/o/r.json could not be read (HTTP 500)"), arm_policy.PolicyError("bad")):
            rc, out = self.run_arm(None, 9, load_error=e)
            self.assertIn("unanswered: the arming policy for o/r cannot be read", str(rc))
            self.assertNotIn("count rule", out)

    def test_the_policy_is_asked_for_the_repository_the_pull_request_is_in_and_the_arm_json_classes_ride_with_it(self):
        loaded = []

        def spy(repo, **kw):
            loaded.append(repo)
            return arm_policy.default()
        self.load_spy = spy
        with mock.patch.object(arm_policy, "load", spy):
            real_with = arm_policy.with_classes
            seen = []
            with mock.patch.object(arm.arm_policy, "with_classes", lambda p, c: (seen.append(c), real_with(p, c))[1]):
                rc, out = self.run_arm_with(spy, 9, classes={"docs": r"\.md$"})
        self.assertEqual((rc, loaded, seen), (0, ["o/r"], [{"docs": r"\.md$"}]), out)


if __name__ == "__main__":
    unittest.main()
