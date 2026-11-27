#!/usr/bin/env python3
"""tools/fabric/git_rules.py, bin/fabric-git-rules and the two hooks that deliver it (agent-fabric ADR-019 §5 rule 9).

The numbers a session reads are checked against the policy the account holds, not against a copy of them written
here: each layer is rendered from the real identities/prompt/git.md and its numbers compared with arming.json's merged
policy. The environment is the test's own (state dir, operator and engine trees in a scratch directory)."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
from git_env import git_env, scrub_process_env  # noqa: E402

scrub_process_env()
import git_rules  # noqa: E402
from github import arm_policy  # noqa: E402

REPO = "fix-org/fix-repo"
ENGINE_TEXT = open(os.path.join(ROOT, "identities", "prompt", "git.md"), encoding="utf-8").read()
HOOKS = os.path.join(ROOT, "runtime", "claude-code", "hooks")
BIN = os.path.join(ROOT, "bin", "fabric-git-rules")


def load_hook(name: str):
    spec = importlib.util.spec_from_file_location("hook_" + name.replace("-", "_"), os.path.join(HOOKS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class Tree(unittest.TestCase):
    """An operator tree with one registered project, an engine tree holding the real default text, and a state dir the
    account's copy is written into."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="git-rules-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.op, self.eng, self.state = (os.path.join(self.tmp, n) for n in ("op", "eng", "state"))
        write(os.path.join(self.eng, "identities", "prompt", "git.md"), ENGINE_TEXT)
        write(os.path.join(self.op, "projects", "registry.json"), json.dumps({"projects": {"fix": {
            "client": "c", "remotes": [f"git@github.com:{REPO}.git"], "default_branch": "trunk"}}}))
        write(os.path.join(self.op, "policies", "arming.json"), json.dumps({"commits": {"min": 3, "advice_over": 5, "refuse_over": 9}}))
        write(os.path.join(self.op, "policies", "signing.json"), json.dumps({
            "default": {"format": "ssh", "since": None}, "repositories": {REPO: {"since": "abc123"}}}))
        write(os.path.join(self.op, "projects", "fix", "integration", "gh", "arm.json"), json.dumps({"boundary": {"paths": "^x/"}}))
        env = mock.patch.dict(os.environ, {"AGENT_FABRIC_STATE_DIR": self.state, "AGENT_FABRIC_OPERATOR": self.op,
                                           "AGENT_FABRIC_ROOT": self.eng})
        env.start()
        self.addCleanup(env.stop)

    def clone(self, name: str, remote: str) -> str:
        path = os.path.join(self.tmp, name)
        os.makedirs(path)
        subprocess.run(["git", "init", "-q", "."], cwd=path, check=True, env=git_env(), timeout=60)
        if remote:
            subprocess.run(["git", "remote", "add", "origin", remote], cwd=path, check=True, env=git_env(), timeout=60)
        return path

    def fleet(self) -> dict:
        return arm_policy.fleet_policy(self.op)

    def copy(self, git_md: dict, commits: dict | None = None) -> dict:
        policy = self.fleet()
        if commits:
            policy = arm_policy.validate(arm_policy.merge(policy, {"commits": commits}))
        arm_policy.write_threshold_cache(REPO, policy, git_md)
        return policy

    def render(self, **kw) -> git_rules.Rendered:
        return git_rules.render(repo=REPO, operator=self.op, engine=self.eng, **kw)

    def assert_numbers(self, out: git_rules.Rendered, policy: dict) -> None:
        c = policy["commits"]
        self.assertIn(f"**A branch lands at {c['advice_over']} work commits**", out.body)
        self.assertIn(f"Past {c['refuse_over']} a commit", out.body)
        self.assertIn(f"prints ({c['min']} unless", out.body)
        self.assertIn(f"merged with GitHub's `{policy['method']}` method", out.body)
        self.assertIn(f"{', '.join(policy['reviews'])} on the head", out.body)
        self.assertIsNone(git_rules.PLACEHOLDER.search(out.body), out.body)


class Layers(Tree):
    def test_the_engine_text_on_the_fleet_value_when_there_is_no_copy_and_says_so(self):
        out = self.render()
        self.assert_numbers(out, self.fleet())
        self.assertIn("the engine's git.md", out.header)
        self.assertIn("the fleet's value", out.header)
        self.assertTrue(any("no copy of fix-org/fix-repo's policy" in n for n in out.notes), out.notes)
        # Control: the numbers are the fleet file's (3/5/9), not the built-in 8/16/32 a blank would fall to.
        self.assertIn("lands at 5 work commits", out.body)

    def test_the_operator_text_wins_over_the_engine_text_whole(self):
        write(os.path.join(self.op, "prompt", "git.md"), "OPERATOR {commits.advice_over}\n")
        out = self.render()
        self.assertEqual(out.body.strip(), "OPERATOR 5")
        self.assertIn("the operator's git.md", out.header)

    def test_the_repository_copy_with_an_override_wins_over_the_operator_and_renders_its_numbers(self):
        write(os.path.join(self.op, "prompt", "git.md"), "OPERATOR\n")
        policy = self.copy({"state": "present", "text": ENGINE_TEXT}, {"advice_over": 20, "refuse_over": 40})
        out = self.render()
        self.assertEqual(policy["commits"]["advice_over"], 20)
        self.assert_numbers(out, policy)
        self.assertIn("the repository's git.md", out.header)
        self.assertRegex(out.header, r"policy: the account's copy as read \d{4}-\d\d-\d\dT")
        self.assertEqual(out.notes, ())

    def test_the_repository_text_replaces_the_others_it_does_not_merge(self):
        self.copy({"state": "present", "text": "REPO RULE {commits.advice_over} on {repo.default_branch}\n"})
        self.assertEqual(self.render().body.strip(), "REPO RULE 5 on trunk")

    def test_an_absent_repository_text_gives_the_operator_text_on_the_copy_without_a_line(self):
        write(os.path.join(self.op, "prompt", "git.md"), "OPERATOR {commits.advice_over}\n")
        self.copy({"state": "absent"}, {"advice_over": 20, "refuse_over": 40})
        out = self.render()
        self.assertEqual(out.body.strip(), "OPERATOR 20")
        self.assertEqual(out.notes, ())

    def test_an_unreadable_repository_text_gives_the_operator_text_and_the_reason(self):
        write(os.path.join(self.op, "prompt", "git.md"), "OPERATOR\n")
        self.copy({"state": "unreadable", "why": "o/s repos/fix-repo.git.md could not be read (HTTP 502)"})
        out = self.render()
        self.assertEqual(out.body.strip(), "OPERATOR")
        self.assertTrue(any("could not be read (o/s repos/fix-repo.git.md could not be read (HTTP 502))" in n for n in out.notes), out.notes)

    def test_a_copy_not_in_the_current_shape_is_no_copy(self):
        path = git_rules.branch_size.cache_path(REPO)
        for doc in ({"repository": REPO, "read_at": "x", "advice_over": 20, "refuse_over": 40},   # written before the whole policy was kept
                    {"repository": "other/repo", "policy": self.fleet(), "git_md": {"state": "absent"}},
                    {"repository": REPO, "policy": self.fleet(), "git_md": {"state": "present"}},
                    {"repository": REPO, "policy": self.fleet(), "git_md": {"state": "nonsense"}},
                    {"repository": REPO, "policy": {"method": "merge"}, "git_md": {"state": "absent"}}):   # no commits block
            write(path, json.dumps(doc))
            out = self.render()
            self.assertIn("the fleet's value", out.header, doc)
            self.assertTrue(out.notes and "policy" in out.notes[0], (doc, out.notes))
        write(path, "{torn")
        self.assertIn("cannot be read", self.render().notes[0])

    def test_a_hand_written_copy_over_the_bound_is_no_copy_and_says_why(self):
        self.copy({"state": "present", "text": "x" * (git_rules.TEXT_LIMIT + 1)})
        out = self.render()
        self.assertIn("the fleet's value", out.header)
        self.assertIn(f"git.md is over {git_rules.TEXT_LIMIT} bytes", out.notes[0])

    def test_a_repository_no_project_has_gets_the_operator_text_on_the_fleet_value(self):
        write(os.path.join(self.op, "prompt", "git.md"), "OPERATOR {commits.refuse_over}\n")
        out = git_rules.render(repo="x/unregistered", operator=self.op, engine=self.eng)
        self.assertEqual(out.body.strip(), "OPERATOR 9")
        self.assertIn("no registered repository here", out.header)
        self.assertEqual(out.notes, ())

    def test_a_layer_that_is_there_and_unreadable_is_an_error_not_the_next_layer(self):
        write(os.path.join(self.op, "prompt", "git.md"), "   \n")
        with self.assertRaisesRegex(git_rules.GitRulesError, "is empty"):
            self.render()
        with open(os.path.join(self.op, "prompt", "git.md"), "wb") as fh:
            fh.write(b"\xff\xfe")
        with self.assertRaisesRegex(git_rules.GitRulesError, "not UTF-8"):
            self.render()

    def test_no_layer_at_all_is_an_error(self):
        os.unlink(os.path.join(self.eng, "identities", "prompt", "git.md"))
        with self.assertRaisesRegex(git_rules.GitRulesError, "no git.md found"):
            self.render()


class Placeholders(Tree):
    def body(self, text: str) -> str:
        write(os.path.join(self.op, "prompt", "git.md"), text)
        return self.render().body.strip()

    def test_each_scope_is_filled_from_its_own_document(self):
        self.assertEqual(self.body("{repo.id} {repo.default_branch} {signing.format} {signing.since} {integration.boundary.paths}"),
                         "fix trunk ssh abc123 ^x/")

    def test_a_list_renders_joined_and_a_scalar_as_itself(self):
        self.assertEqual(self.body("{reviews}|{method}|{commits.min}|{signatures}"), "claude|merge|3|true")
        write(os.path.join(self.op, "policies", "arming.json"), json.dumps({"reviews": ["claude", "codex"]}))
        self.assertEqual(self.body("{reviews}"), "claude, codex")

    def test_a_name_with_no_value_is_an_error_that_names_it(self):
        for text, name in (("{repo.nonsense}", "repo.nonsense"), ("{commits.nothing}", "commits.nothing"),
                           ("{signing.since}x{signing.missing}", "signing.missing"), ("{commits.roles}", "commits.roles"),
                           ("{additional_reviews_none}", "additional_reviews_none"), ("{integration.nope}", "integration.nope")):
            write(os.path.join(self.op, "prompt", "git.md"), text)
            with self.assertRaises(git_rules.GitRulesError, msg=text) as cm:
                self.render()
            self.assertIn("{" + name + "}", str(cm.exception))
        # Controls: null, an empty list and an empty string are no value either, never a blank.
        write(os.path.join(self.op, "policies", "signing.json"), json.dumps({"default": {"since": None, "x": [], "y": ""}}))
        for name in ("signing.since", "signing.x", "signing.y"):
            write(os.path.join(self.op, "prompt", "git.md"), "{" + name + "}")
            with self.assertRaises(git_rules.GitRulesError, msg=name):
                self.render()

    def test_signing_takes_the_repository_entry_over_the_default(self):
        write(os.path.join(self.op, "policies", "signing.json"), json.dumps({
            "default": {"format": "ssh", "since": "d"}, "repositories": {REPO: {"format": "gpg"}}}))
        self.assertEqual(self.body("{signing.format} {signing.since}"), "gpg d")

    def test_braces_that_are_no_placeholder_pass_through(self):
        self.assertEqual(self.body("`{}` {Upper} {a b} {1x} <<'EOF' {x.}"), "`{}` {Upper} {a b} {1x} <<'EOF' {x.}")

    def test_repo_scope_is_absent_outside_a_registered_project(self):
        write(os.path.join(self.op, "prompt", "git.md"), "{repo.default_branch}")
        with self.assertRaisesRegex(git_rules.GitRulesError, r"\{repo.default_branch\}"):
            git_rules.render(repo="x/unregistered", operator=self.op, engine=self.eng)


class WorkingCopy(Tree):
    def test_a_working_copy_resolves_to_its_origin_and_project(self):
        wc = self.clone("wc", f"https://github.com/{REPO}")
        policy = self.copy({"state": "present", "text": ENGINE_TEXT}, {"advice_over": 20, "refuse_over": 40})
        out = git_rules.render(wc, operator=self.op, engine=self.eng)
        self.assert_numbers(out, policy)
        self.assertIn(f"git rules for {REPO}", out.header)

    def test_outside_any_registered_project_it_is_the_operator_text_on_the_fleet_value(self):
        write(os.path.join(self.op, "prompt", "git.md"), "OPERATOR {commits.advice_over}\n")
        for path in (self.clone("other", "https://github.com/else/where"), self.clone("none", ""), self.tmp):
            out = git_rules.render(path, operator=self.op, engine=self.eng)
            self.assertEqual(out.body.strip(), "OPERATOR 5", path)
            self.assertIn("no registered repository here", out.header)

    def test_the_command_prints_the_header_and_the_text_and_fails_with_one_line(self):
        env = {**os.environ, "AGENT_FABRIC_PYTHON": sys.executable}
        run = lambda *a, **k: subprocess.run([BIN, *a], capture_output=True, text=True, env=env, timeout=60, **k)
        write(os.path.join(self.op, "prompt", "git.md"), "OPERATOR {commits.advice_over}\n")
        ok = run("--repo", REPO)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(ok.stdout.splitlines()[0].split(" — ")[0], f"agent-fabric: git rules for {REPO}")
        self.assertTrue(ok.stdout.rstrip().endswith("OPERATOR 5"), ok.stdout)
        write(os.path.join(self.op, "prompt", "git.md"), "{repo.nothing}\n")
        bad = run("--repo", REPO)
        self.assertEqual((bad.returncode, bad.stdout), (1, ""))
        self.assertEqual(bad.stderr.strip(), "fabric-git-rules: the placeholder {repo.nothing} has no value here")
        self.assertEqual(run("--repo", "not-a-repo").returncode, 2)
        self.assertEqual(run("--repo", REPO, self.tmp).returncode, 2)
        self.assertEqual(run(os.path.join(self.tmp, "absent")).returncode, 1)

    def test_an_arming_file_the_validator_refuses_is_one_line_not_a_traceback(self):
        write(os.path.join(self.op, "policies", "arming.json"), json.dumps({"commits": {"min": "many"}}))
        env = {**os.environ, "AGENT_FABRIC_PYTHON": sys.executable}
        bad = subprocess.run([BIN, "--repo", "else/where"], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual((bad.returncode, bad.stdout), (1, ""))
        self.assertEqual(len(bad.stderr.strip().splitlines()), 1, bad.stderr)
        self.assertTrue(bad.stderr.startswith("fabric-git-rules: "), bad.stderr)
        self.assertNotIn("Traceback", bad.stderr)

    def test_the_real_default_text_renders_in_this_checkout_without_an_unfilled_placeholder(self):
        env = {k: v for k, v in os.environ.items() if k not in ("AGENT_FABRIC_OPERATOR", "AGENT_FABRIC_ROOT")}
        env.update(AGENT_FABRIC_PYTHON=sys.executable, AGENT_FABRIC_STATE_DIR=self.state)
        done = subprocess.run([BIN, "--repo", "BlueTeam-OU/agent-fabric"], capture_output=True, text=True, env=env, timeout=60, cwd=ROOT)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIsNone(git_rules.PLACEHOLDER.search(done.stdout), done.stdout)
        self.assertIn("lands at", done.stdout)


class Malformed(Tree):
    def test_a_malformed_policy_document_is_one_line_not_a_traceback(self):
        env = {**os.environ, "AGENT_FABRIC_PYTHON": sys.executable}
        good = {"projects/registry.json": {"projects": {"fix": {
                    "client": "c", "remotes": [f"git@github.com:{REPO}.git"], "default_branch": "trunk"}}},
                "policies/signing.json": {"default": {"format": "ssh"}},
                "projects/fix/integration/gh/arm.json": {"boundary": {"paths": "^x/"}}}
        cases = (("policies/signing.json", {"default": {"format": "ssh"}, "repositories": ["x"]}),
                 ("policies/signing.json", {"default": {"format": "ssh"}, "repositories": {REPO: ["x"]}}),
                 ("projects/fix/integration/gh/arm.json", ["x"]),
                 ("projects/registry.json", {"projects": {"fix": {"remotes": 3}}}),
                 ("projects/registry.json", {"projects": {"fix": ["x"]}}))
        for rel, doc in cases:
            for name, ok in good.items():
                write(os.path.join(self.op, name), json.dumps(ok))
            write(os.path.join(self.op, rel), json.dumps(doc))
            bad = subprocess.run([BIN, "--repo", REPO], capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual((bad.returncode, bad.stdout), (1, ""), (rel, doc, bad.stderr))
            self.assertEqual(len(bad.stderr.strip().splitlines()), 1, bad.stderr)
            self.assertNotIn("Traceback", bad.stderr)
            self.assertTrue(bad.stderr.startswith("fabric-git-rules: "), bad.stderr)
        # A remote that is no string, through the working-copy route that resolves an origin (review 6065071013 F19).
        wc = self.clone("wc", f"https://github.com/{REPO}")
        write(os.path.join(self.op, "projects/registry.json"), json.dumps({"projects": {"fix": {"remotes": [3]}}}))
        bad = subprocess.run([BIN, wc], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual((bad.returncode, bad.stdout, len(bad.stderr.strip().splitlines())), (1, "", 1), bad.stderr)
        self.assertNotIn("Traceback", bad.stderr)
        # null remotes is no remotes, as the other registry readers take it: no refusal.
        write(os.path.join(self.op, "projects/registry.json"), json.dumps({"projects": {"fix": {"remotes": None}}}))
        self.assertEqual(subprocess.run([BIN, wc], capture_output=True, text=True, env=env, timeout=60).returncode, 0)

    def test_the_engine_text_alone_renders_with_no_operator_layer_and_no_registered_project(self):
        self.assertFalse(os.path.exists(os.path.join(self.op, "prompt", "git.md")))
        for out in (git_rules.render(self.tmp, operator=self.op, engine=self.eng),
                    git_rules.render(repo="x/unregistered", operator=self.op, engine=self.eng)):
            self.assertIn("the engine's git.md", out.header)
            self.assertIsNone(git_rules.PLACEHOLDER.search(out.body), out.body)
            self.assertIn("lands at", out.body)


class Hooks(Tree):
    def test_an_absent_operator_registry_is_empty_and_a_present_null_one_is_an_error(self):
        registry = os.path.join(self.op, "projects", "registry.json")
        os.remove(registry)
        out = git_rules.render(repo=REPO, operator=self.op, engine=self.eng)
        self.assertIn("no registered repository here", out.header)
        self.assertIsNone(git_rules.PLACEHOLDER.search(out.body), out.body)
        for text in ("null", "[]", "{}"):
            write(registry, text)
            with self.assertRaises(git_rules.GitRulesError, msg=text):
                git_rules.render(repo=REPO, operator=self.op, engine=self.eng)

    def setUp(self):
        super().setUp()
        self.wc = self.clone("wc", f"https://github.com/{REPO}")
        self.elsewhere = self.clone("elsewhere", "https://github.com/else/where")
        self.copy({"state": "present", "text": "REPO-RULES {commits.advice_over}\n"}, {"advice_over": 20, "refuse_over": 40})
        write(os.path.join(self.op, "prompt", "git.md"), "OPERATOR-RULES {commits.advice_over}\n")

    def test_session_start_gives_the_rendered_text_and_notes_the_working_copy(self):
        env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT}
        done = subprocess.run(["bash", os.path.join(HOOKS, "session-start.sh")], input=json.dumps({"cwd": self.wc, "session_id": "sg1"}),
                              capture_output=True, text=True, env=env, timeout=120)
        ctx = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(f"agent-fabric: git rules for {REPO} — text: the repository's git.md", ctx)
        self.assertIn("REPO-RULES 20", ctx)
        self.assertNotIn("OPERATOR-RULES", ctx)
        self.assertEqual(git_rules.given("sg1"), os.path.realpath(self.wc))
        # Control: a subagent's start (the parent's session id, a scratch worktree) gives the text and moves no note.
        sub = subprocess.run(["bash", os.path.join(HOOKS, "session-start.sh")],
                             input=json.dumps({"cwd": self.elsewhere, "session_id": "sg1", "agent_id": "a1"}),
                             capture_output=True, text=True, env=env, timeout=120)
        self.assertIn("OPERATOR-RULES 5", sub.stdout)
        self.assertEqual(git_rules.given("sg1"), os.path.realpath(self.wc))

    def test_a_render_failure_is_a_line_and_the_start_goes_on(self):
        write(os.path.join(self.op, "prompt", "git.md"), "{repo.nothing}")
        env = {**os.environ, "AGENT_FABRIC_ROOT": ROOT}
        done = subprocess.run(["bash", os.path.join(HOOKS, "session-start.sh")], input=json.dumps({"cwd": self.elsewhere, "session_id": "sg2"}),
                              capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        ctx = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("the git rules could not be rendered (the placeholder {repo.nothing} has no value here)", ctx)
        self.assertIn("agent-fabric: agent=", ctx)
        self.assertIsNone(git_rules.given("sg2"), "a failure line is not the rules: not noted as given")

    def test_the_prompt_gives_the_rules_again_only_when_the_working_copy_changes(self):
        fresh = load_hook("freshness")
        p = lambda cwd, sid="sf1": {"cwd": cwd, "session_id": sid}
        git_rules.record_given("sf1", self.wc)                      # what session-start does
        self.assertIsNone(fresh.git_rules_note(p(self.wc)), "the working copy session-start gave: nothing")
        self.assertIsNone(fresh.git_rules_note(p(os.path.join(self.wc, "."))), "the same copy by another spelling")
        sub = os.path.join(self.wc, "sub")
        os.makedirs(sub)
        self.assertIsNone(fresh.git_rules_note(p(sub)), "a subdirectory is the same working copy")
        moved = fresh.git_rules_note(p(self.elsewhere))
        self.assertIn("OPERATOR-RULES 5", moved)
        self.assertIsNone(fresh.git_rules_note(p(self.elsewhere)), "once per change")
        back = fresh.git_rules_note(p(self.wc))
        self.assertIn("REPO-RULES 20", back)
        self.assertIsNone(fresh.git_rules_note(p(self.wc)))
        # Outside any git working copy: the operator layer once, never a crash.
        outside = fresh.git_rules_note(p(self.tmp))
        self.assertIn("no registered repository here", outside)
        self.assertIsNone(fresh.git_rules_note(p(self.tmp)))
        # Another session has its own note: it is given the rules on its first prompt.
        self.assertIn("REPO-RULES 20", fresh.git_rules_note(p(self.wc, "sf2")))
        # No usable session id or cwd: nothing, never a guess.
        self.assertIsNone(fresh.git_rules_note({"cwd": self.wc, "session_id": "../x"}))
        self.assertIsNone(fresh.git_rules_note({"cwd": os.path.join(self.tmp, "absent"), "session_id": "sf3"}))

    def test_main_prints_one_context_and_survives_a_failure_of_either_part(self):
        fresh = load_hook("freshness")
        import io
        with mock.patch.object(fresh, "note", side_effect=RuntimeError("x")), \
                mock.patch("sys.stdin", io.StringIO(json.dumps({"cwd": self.wc, "session_id": "sm1"}))), \
                mock.patch("sys.stdout", io.StringIO()) as out:
            self.assertEqual(fresh.main(), 0)
        ctx = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(ctx["hookEventName"], "UserPromptSubmit")
        self.assertIn("REPO-RULES 20", ctx["additionalContext"])
        # The reverse: the rules fail, the freshness line survives and the failure is said, not swallowed.
        with mock.patch.object(fresh, "note", return_value="FRESH-LINE"), \
                mock.patch.object(fresh, "git_rules_note", side_effect=RuntimeError("boom")), \
                mock.patch("sys.stdin", io.StringIO(json.dumps({"cwd": self.wc, "session_id": "sm2"}))), \
                mock.patch("sys.stdout", io.StringIO()) as out:
            self.assertEqual(fresh.main(), 0)
        said = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("FRESH-LINE", said)
        self.assertIn("agent-fabric: the git rules could not be given (RuntimeError: boom); run fabric-git-rules", said)
        # Out of budget with rules due: they are not rendered, it is said, and nothing is noted as given.
        with mock.patch.object(fresh, "note", return_value=None), \
                mock.patch.object(git_rules, "for_hook", side_effect=AssertionError("must not run")), \
                mock.patch.object(fresh, "git_rules", return_value=git_rules), \
                mock.patch.object(fresh, "HOOK_BUDGET_S", 0.0), \
                mock.patch("sys.stdin", io.StringIO(json.dumps({"cwd": self.wc, "session_id": "sm3"}))), \
                mock.patch("sys.stdout", io.StringIO()) as out:
            self.assertEqual(fresh.main(), 0)
        self.assertIn("were not given on this prompt", out.getvalue())
        self.assertIn("on a later prompt", out.getvalue())
        self.assertIsNone(git_rules.given("sm3"))
        # Out of budget with nothing owed: not a word about the rules.
        git_rules.record_given("sm4", self.wc)
        with mock.patch.object(fresh, "note", return_value=None), mock.patch.object(fresh, "HOOK_BUDGET_S", 0.0), \
                mock.patch("sys.stdin", io.StringIO(json.dumps({"cwd": self.wc, "session_id": "sm4"}))), \
                mock.patch("sys.stdout", io.StringIO()) as out:
            self.assertEqual(fresh.main(), 0)
        self.assertEqual(out.getvalue(), "")
        with mock.patch("sys.stdin", io.StringIO("not json")), mock.patch("sys.stdout", io.StringIO()) as out:
            self.assertEqual(fresh.main(), 0)
        self.assertEqual(out.getvalue(), "")

    def test_a_call_that_times_out_is_a_failure_line_and_is_not_noted_as_given(self):
        with self.assertRaisesRegex(git_rules.GitRulesError, r"did not answer within"):
            git_rules.render(self.wc, operator=self.op, engine=self.eng, timeout=1e-6)
        line = git_rules.for_hook(self.wc, timeout=1e-6)
        self.assertTrue(line.startswith(git_rules.FAILURE_PREFIX), line)
        self.assertNotIn("OPERATOR-RULES", line)
        fresh = load_hook("freshness")
        real = git_rules.for_hook
        with mock.patch.object(fresh, "git_rules", return_value=git_rules), \
                mock.patch.object(git_rules, "for_hook", lambda wc, timeout=None: real(wc, timeout=1e-6)):
            said = fresh.git_rules_note({"cwd": self.wc, "session_id": "st1"})
        self.assertTrue(said.startswith(git_rules.FAILURE_PREFIX), said)
        self.assertIsNone(git_rules.given("st1"))
        # Control: an unbounded render works.
        self.assertIn("REPO-RULES 20", git_rules.render(self.wc, operator=self.op, engine=self.eng).body)


if __name__ == "__main__":
    unittest.main(verbosity=1)
