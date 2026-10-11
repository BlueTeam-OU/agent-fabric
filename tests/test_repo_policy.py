#!/usr/bin/env python3
"""tools/fabric/github/repo_policy.py, fabric-repo-policy plan|verify (arming step C): the differences between a
repository's arming policy and the settings and ruleset GitHub holds, what is only advisory, what an unreadable
side means (never "no difference"), the exit codes and the --json shape. GitHub is a function answering by path;
the policy is the real arm_policy.render of a real policy, so what is compared is what apply (step E) would write."""
from __future__ import annotations

import copy
import io
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
from github import arm_policy, repo_policy  # noqa: E402

REPO = "O/R"
POLICY = arm_policy.validate({"required_checks": [{"context": "ci-ok", "app": "github-actions"}], "github": {"ruleset": "main protection"}})
QUEUE = arm_policy.validate({"mode": "queue", "method": "squash", "required_checks": [{"context": "ci-ok", "app": "github-actions"}],
                             "queue": {"build": 3}, "github": {"ruleset": "main protection"}})


class Github:
    """What GitHub holds for REPO: the repository's fields and one ruleset, as `policy` would write them; each can be
    spoiled by a test. Answers the three reads and the App lookup; records the paths asked."""

    def __init__(self, policy: dict, apps: dict | None = None):
        want = arm_policy.render(policy, apps)
        self.repository = dict(want["repository"])
        self.ruleset = copy.deepcopy(want["ruleset"])
        self.name = policy["github"]["ruleset"]
        self.asked, self.fail, self.others = [], None, []
        self.apps = {}

    def __call__(self, path, **kw):
        self.asked.append(path)
        if kw.get("method", "GET") != "GET":
            raise AssertionError(f"a write: {path}")
        if self.fail and self.fail in path:
            raise gh.GhError("gh api GET x", "HTTP 403", status=403)
        if path.startswith("apps/"):
            if path[5:] not in self.apps:
                raise gh.GhError("gh api GET x", "Not Found", status=404)
            return {"id": self.apps[path[5:]]}
        if path == f"repos/{REPO}":
            return dict(self.repository)
        if path == f"repos/{REPO}/rulesets?includes_parents=false":
            listed = [{"id": o, "name": f"other {o}"} for o in self.others]
            return listed + ([{"id": 7, "name": self.name}] if self.ruleset is not None else [])
        if path == f"repos/{REPO}/rulesets/7":
            return copy.deepcopy(self.ruleset)
        raise AssertionError(f"unexpected read: {path}")


def rule(gh_state: Github, kind: str) -> dict:
    return next(r for r in gh_state.ruleset["rules"] if r["type"] == kind)


class Differences(unittest.TestCase):
    def check(self, g: Github, policy: dict = POLICY) -> list[str]:
        return repo_policy.check(REPO, policy, g)

    def test_a_repository_as_the_policy_writes_it_has_no_difference(self):
        for policy in (POLICY, QUEUE):
            self.assertEqual(self.check(Github(policy), policy), [])

    def test_github_adds_fields_of_its_own_to_a_rule_and_that_is_not_a_difference(self):
        g = Github(POLICY)
        rule(g, "pull_request")["parameters"]["automatic_copilot_code_review_enabled"] = False
        g.ruleset["id"], g.ruleset["source"], g.ruleset["created_at"] = 7, "O/R", "x"
        self.assertEqual(self.check(g), [])

    def test_rule_order_is_not_a_difference(self):
        g = Github(POLICY)
        g.ruleset["rules"].reverse()
        self.assertEqual(self.check(g), [])

    def test_the_repository_fields_are_compared_and_the_merge_method_ones_are_advisory(self):
        g = Github(POLICY)
        g.repository.update(allow_squash_merge=True, allow_rebase_merge=True, delete_branch_on_merge=True, allow_auto_merge=False)
        found = self.check(g)
        self.assertEqual(found, ["repository allow_auto_merge is False, the policy wants True",
                                 "repository allow_squash_merge is True, the policy wants False (advisory)",
                                 "repository allow_rebase_merge is True, the policy wants False (advisory)",
                                 "repository delete_branch_on_merge is True, the policy wants False (advisory)"])
        self.assertEqual(repo_policy.blocking(found), ["repository allow_auto_merge is False, the policy wants True"])

    def test_a_missing_ruleset_is_a_difference_and_so_is_one_that_should_not_be_there(self):
        g = Github(POLICY)
        g.ruleset = None
        self.assertEqual(self.check(g), ["ruleset 'main protection' is missing"])
        g = Github(arm_policy.validate({"mode": "direct", "github": {"ruleset": "main protection"}}))
        g.ruleset = {"name": "main protection", "rules": []}
        found = repo_policy.check(REPO, arm_policy.validate({"mode": "direct", "github": {"ruleset": "main protection"}}), g)
        self.assertEqual(found, ["ruleset 'main protection' exists, and the policy's mode has no server-side rule"])

    def test_only_the_ruleset_the_policy_names_is_looked_at(self):
        g = Github(POLICY)
        g.others = [1, 2, 3]
        self.assertEqual(self.check(g), [])
        self.assertIn(f"repos/{REPO}/rulesets?includes_parents=false", g.asked)

    def test_a_rule_missing_extra_or_with_other_parameters_is_a_difference(self):
        g = Github(POLICY)
        g.ruleset["rules"] = [r for r in g.ruleset["rules"] if r["type"] != "required_signatures"]
        g.ruleset["rules"].append({"type": "creation"})
        rule(g, "pull_request")["parameters"]["allowed_merge_methods"] = ["merge", "squash"]
        found = self.check(g)
        self.assertEqual(sorted(found), sorted([
            "rule required_signatures is missing",
            "rule creation is on the ruleset, and the policy does not want it",
            "rule pull_request: allowed_merge_methods is ['merge', 'squash'], the policy wants ['merge']"]))

    def test_the_required_checks_are_compared_by_context_and_integration_id(self):
        g = Github(POLICY)
        rule(g, "required_status_checks")["parameters"]["required_status_checks"] = [{"context": "ci-ok"}]
        self.assertEqual(len(self.check(g)), 1)
        self.assertIn("required checks are [('ci-ok', None)], the policy wants [('ci-ok', 15368)]", self.check(g)[0])
        rule(g, "required_status_checks")["parameters"]["required_status_checks"] = [{"context": "ci-ok", "integration_id": 15368}]
        self.assertEqual(self.check(g), [])

    def test_the_ruleset_target_enforcement_conditions_and_bypass_actors_are_compared(self):
        g = Github(POLICY)
        g.ruleset.update(enforcement="evaluate", target="tag", bypass_actors=[{"actor_id": 5, "actor_type": "Team", "bypass_mode": "always"}])
        g.ruleset["conditions"] = {"ref_name": {"include": ["refs/heads/other"], "exclude": []}}
        found = self.check(g)
        self.assertEqual(len(found), 4)
        self.assertTrue(all(line.startswith("ruleset ") for line in found), found)

    def test_a_queue_rules_parameters_are_compared_with_the_schemas_names_mapped(self):
        g = Github(QUEUE)
        rule(g, "merge_queue")["parameters"]["max_entries_to_build"] = 9
        self.assertEqual(self.check(g, QUEUE), ["rule merge_queue: max_entries_to_build is 9, the policy wants 3"])

    def test_an_app_arm_policy_does_not_know_is_asked_of_github_and_its_id_compared(self):
        policy = arm_policy.validate({"required_checks": [{"context": "x", "app": "circleci"}], "github": {"ruleset": "main protection"}})
        g = Github(policy, {"circleci": 18001})
        g.apps = {"circleci": 18001}
        self.assertEqual(self.check(g, policy), [])
        self.assertIn("apps/circleci", g.asked)
        g.apps = {"circleci": 1}
        self.assertEqual(len(self.check(g, policy)), 1)
        g.apps = {}
        with self.assertRaises(repo_policy.Unreadable):
            self.check(g, policy)

    def test_a_read_that_fails_or_answers_in_another_shape_is_unreadable_never_no_difference(self):
        for path in (f"repos/{REPO}", "rulesets?", "rulesets/7"):
            g = Github(POLICY)
            g.fail = path
            with self.assertRaises(repo_policy.Unreadable, msg=path):
                self.check(g)
        g = Github(POLICY)
        del g.repository["allow_squash_merge"]
        with self.assertRaises(repo_policy.Unreadable):
            self.check(g)
        g = Github(POLICY)
        g.repository["allow_auto_merge"] = "yes"
        with self.assertRaises(repo_policy.Unreadable):
            self.check(g)

    def test_a_policy_that_cannot_be_mapped_is_unreadable(self):
        policy = arm_policy.validate({"required_checks": [{"context": "x", "app": "nobody-knows"}]})
        g = Github(POLICY)
        with self.assertRaises(repo_policy.Unreadable):
            repo_policy.check(REPO, policy, g)

    def test_only_reads_are_made(self):
        g = Github(POLICY)
        g.repository["allow_auto_merge"] = False
        self.check(g)          # Github raises AssertionError on any call that is not a GET


class Cli(unittest.TestCase):
    def run_cli(self, argv, g: Github | None = None, policy: dict = POLICY, load_error=None):
        out, err = io.StringIO(), io.StringIO()
        load = mock.Mock(side_effect=load_error) if load_error else mock.Mock(return_value=policy)
        with mock.patch.object(arm_policy, "load", load), mock.patch.object(gh, "this_repo", return_value=REPO):
            rc = repo_policy.run(argv, g or Github(policy), out, err)
        self.load = load
        return rc, out.getvalue(), err.getvalue()

    def test_no_difference_is_said_and_both_verbs_exit_zero(self):
        for verb in ("plan", "verify"):
            rc, out, _ = self.run_cli([verb, REPO])
            self.assertEqual((rc, out), (0, f"{REPO}: GitHub matches the arming policy\n"), verb)

    def test_plan_lists_the_differences_and_exits_zero_verify_exits_one(self):
        g = Github(POLICY)
        g.ruleset = None
        rc, out, _ = self.run_cli(["plan", REPO], g)
        self.assertEqual(rc, 0)
        self.assertIn("differs from the arming policy in 1 place(s)", out)
        self.assertIn("  ruleset 'main protection' is missing", out)
        rc, out2, _ = self.run_cli(["verify", REPO], g)
        self.assertEqual((rc, out2), (1, out))

    def test_verify_fails_on_an_advisory_difference_too(self):
        g = Github(POLICY)
        g.repository["allow_squash_merge"] = True
        rc, out, _ = self.run_cli(["verify", REPO], g)
        self.assertEqual(rc, 1)
        self.assertIn("(advisory)", out)

    def test_json_says_drift_blocking_and_every_difference(self):
        g = Github(POLICY)
        g.repository.update(allow_squash_merge=True, allow_auto_merge=False)
        rc, out, _ = self.run_cli(["verify", REPO, "--json"], g)
        d = json.loads(out)
        self.assertEqual((rc, d["drift"], d["repository"], d["verb"]), (1, True, REPO, "verify"))
        self.assertEqual(d["blocking"], ["repository allow_auto_merge is False, the policy wants True"])
        self.assertEqual(len(d["differences"]), 2)
        rc, out, _ = self.run_cli(["plan", "--json", REPO])
        self.assertEqual((rc, json.loads(out)["drift"]), (0, False))

    def test_the_repository_defaults_to_the_current_one_and_the_policy_is_loaded_for_it(self):
        rc, _, _ = self.run_cli(["verify"])
        self.assertEqual(rc, 0)
        self.load.assert_called_once()
        self.assertEqual(self.load.call_args.args[0], REPO)

    def test_usage_errors_exit_two_and_say_the_usage(self):
        for argv in ([], ["apply", REPO], ["plan", REPO, "x/y"], ["plan", "--force"], ["verify", "-x"]):
            rc, out, err = self.run_cli(argv)
            self.assertEqual((rc, out), (2, ""), argv)
            self.assertIn("usage: fabric-repo-policy plan|verify", err)

    def test_a_repository_name_that_is_not_one_exits_two(self):
        for bad in ("../x", "o", "o/r r"):
            rc, _, err = self.run_cli(["plan", bad])
            self.assertEqual(rc, 2, bad)
            self.assertIn("is not an <owner>/<name>", err)

    def test_what_cannot_be_read_exits_two_for_both_verbs_and_says_why(self):
        g = Github(POLICY)
        g.fail = f"repos/{REPO}/rulesets/7"
        for verb in ("plan", "verify"):
            rc, out, err = self.run_cli([verb, REPO], g)
            self.assertEqual((rc, out), (2, ""), verb)
            self.assertIn("cannot be read", err)
        for e in (arm_policy.PolicyUnavailable("settings gone"), arm_policy.PolicyError("bad file")):
            rc, _, err = self.run_cli(["verify", REPO], load_error=e)
            self.assertEqual(rc, 2)
            self.assertIn(str(e), err)

    def test_the_shim_runs_the_module(self):
        import subprocess
        r = subprocess.run([os.path.join(HERE, "bin", "fabric-repo-policy")], capture_output=True, text=True, timeout=60,
                           env={"PATH": os.environ["PATH"], "AGENT_FABRIC_PYTHON": sys.executable})
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage: fabric-repo-policy plan|verify", r.stderr)


if __name__ == "__main__":
    unittest.main()
