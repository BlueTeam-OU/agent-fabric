#!/usr/bin/env python3
"""The control agent's `clone` action (tools/fabric/control/clone.py), the judgements it shares with provisioning's step 6
(tools/fabric/project_clone.py) and fabric-ctl's side of the verb. Real git against a local bare remote; a scratch fabric
root whose bootstrap.sh records when it ran and what stood on disk then; a scratch home. The step-6 side of the shared code
is tests/test_provisioning_worker.py's and tests/test_new_agent.py's, run unchanged."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402

own_instance_tree()
from control import agentd, ctl, ops  # noqa: E402
from control import clone as cl  # noqa: E402
from control.ops import util  # noqa: E402
import project_clone as pc  # noqa: E402

GIT = shutil.which("git") or "/usr/bin/git"
HTTPS = "https://example.invalid/o/gzapp"


def git(*argv: str, cwd: str | None = None) -> str:
    env = {"PATH": os.environ["PATH"], "HOME": "/nonexistent", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run([GIT, *argv], cwd=cwd, env=env, check=True, capture_output=True, text=True, timeout=60).stdout.strip()


class Scratch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="control-clone-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.home = os.path.join(self.dir, "home")
        self.root = os.path.join(self.dir, "fabric")
        self.remote = os.path.join(self.dir, "remote.git")
        os.makedirs(self.home)
        seed = os.path.join(self.dir, "seed")
        git("init", "-q", "-b", "main", seed)
        with open(os.path.join(seed, "f"), "w") as fh:
            fh.write("x\n")
        git("add", "f", cwd=seed)
        git("commit", "-qm", "seed", cwd=seed)
        git("clone", "-q", "--bare", seed, self.remote)
        self.registry({"gzapp": {"remotes": [self.remote, HTTPS]}})
        # What bootstrap sees when it runs: the marker says whether the working copy was already there, and with which
        # environment, so "after the clone" and "as it is called" are read from the script's own witness.
        os.makedirs(os.path.join(self.root, "runtime", "claude-code"))
        self.marker = os.path.join(self.dir, "bootstrap.log")
        self.script("0")

    def script(self, code: str) -> None:
        path = os.path.join(self.root, "runtime", "claude-code", "bootstrap.sh")
        with open(path, "w") as fh:
            fh.write(f'#!/bin/bash\necho "$PWD|$HOME|${{AGENT_FABRIC_DEFER_AGENTD_RESTART-unset}}|$(ls -d "$HOME"/projects/*/.git 2>&1 | tr "\\n" " ")" >> {self.marker}\n'
                     f'[ {code} = 0 ] || {{ echo "bootstrap said no" >&2; exit {code}; }}\n')
        os.chmod(path, 0o755)

    def registry(self, projects: dict) -> None:
        os.makedirs(os.path.join(self.root, "projects"), exist_ok=True)
        with open(os.path.join(self.root, "projects", "registry.json"), "w") as fh:
            json.dump({"projects": projects}, fh)

    def go(self, project: str = "gzapp", run=None, **kw) -> dict:
        return cl.clone({"op": "clone", "args": {"project": project}}, root=self.root, home=self.home,
                        **({"run": run} if run else {}), **kw)

    def bootstraps(self) -> list[str]:
        try:
            with open(self.marker) as fh:
                return fh.read().splitlines()
        except FileNotFoundError:
            return []

    @property
    def dest(self) -> str:
        return os.path.join(self.home, "projects", "gzapp")


class Clone(Scratch):
    def test_a_fresh_clone_is_made_from_the_registrys_ssh_remote_and_bootstrap_runs_after_it(self):
        doc = self.go()
        self.assertEqual((doc["status"], doc["project"], doc["remote"]), ("cloned", "gzapp", self.remote))
        self.assertEqual(git("config", "--get", "remote.origin.url", cwd=self.dest), self.remote)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "f")))
        (line,) = self.bootstraps()
        cwd, home, defer, seen = line.split("|")
        self.assertEqual((cwd, home, defer), (os.path.realpath(self.root), self.home, "1"))
        self.assertIn("gzapp/.git", seen, "bootstrap ran after the clone: the working copy was on disk then")

    def test_the_remote_is_the_first_git_at_one_and_the_first_remote_otherwise(self):
        self.assertEqual(pc.ssh_remote({"remotes": [HTTPS, "git@h:o/r.git", "git@h:o/s.git"]}), "git@h:o/r.git")
        self.assertEqual(pc.ssh_remote({"remotes": [HTTPS, "https://b"]}), HTTPS)
        for bad in (None, {}, {"remotes": []}, {"remotes": "git@h:o/r"}, {"remotes": [1]}, {"remotes": [""]}, []):
            self.assertIsNone(pc.ssh_remote(bad), bad)

    def test_a_clone_already_there_is_present_and_only_its_origin_is_pointed_at_the_registrys_remote(self):
        git("clone", "-q", self.remote, self.dest)
        git("remote", "set-url", "origin", HTTPS, cwd=self.dest)
        with open(os.path.join(self.dest, "mine"), "w") as fh:
            fh.write("uncommitted\n")
        calls: list[list[str]] = []

        def run(argv, **kw):
            calls.append(list(argv))
            return util.run_bounded(argv, **kw)
        doc = self.go(run=run)
        self.assertEqual((doc["status"], doc["origin"]), ("present", "set"))
        self.assertEqual(git("config", "--get", "remote.origin.url", cwd=self.dest), self.remote)
        self.assertEqual([c for c in calls if c[:2] == ["git", "clone"]], [], "no second clone")
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "mine")), "the working copy is left as it was")
        self.assertEqual(len(self.bootstraps()), 1, "bootstrap re-runs on a present copy: a failed one must converge on a retry")

    def test_a_present_copy_with_the_registrys_origin_is_not_rewritten(self):
        git("clone", "-q", self.remote, self.dest)
        calls: list[list[str]] = []

        def run(argv, **kw):
            calls.append(list(argv))
            return util.run_bounded(argv, **kw)
        doc = self.go(run=run)
        self.assertEqual((doc["status"], doc["origin"]), ("present", "keep"))
        self.assertEqual([c for c in calls if "set-url" in c], [])

    def test_a_push_url_of_its_own_is_said_not_rewritten(self):
        git("clone", "-q", self.remote, self.dest)
        git("config", "remote.origin.pushurl", HTTPS, cwd=self.dest)
        doc = self.go()
        self.assertIn(HTTPS, doc["warning"])
        self.assertEqual(git("config", "--get", "remote.origin.pushurl", cwd=self.dest), HTTPS)

    def test_an_origin_that_cannot_be_read_is_left_as_it_is_and_the_copy_is_still_present(self):
        git("clone", "-q", self.remote, self.dest)
        git("remote", "remove", "origin", cwd=self.dest)
        doc = self.go()
        self.assertEqual((doc["status"], doc["origin"]), ("present", "unreadable"))
        self.assertEqual(subprocess.run([GIT, "-C", self.dest, "remote"], capture_output=True, text=True).stdout, "")

    def test_an_id_the_registry_does_not_know_is_refused_before_anything_runs(self):
        def boom(*a, **k):
            raise AssertionError("something ran")
        for pid in ("nope", "gzapp-x"):
            doc = self.go(pid, run=boom)
            self.assertEqual(doc["status"], "refused", pid)
            self.assertIn(pid, doc["reason"])
        self.assertFalse(os.path.exists(os.path.join(self.home, "projects")), "not even ~/projects was made")
        self.assertEqual(self.bootstraps(), [])

    def test_an_entry_with_no_remote_is_refused_not_guessed(self):
        self.registry({"gzapp": {"remotes": []}, "bare": {}})
        for pid in ("gzapp", "bare"):
            self.assertEqual(self.go(pid, run=lambda *a, **k: self.fail("ran"))["status"], "refused", pid)

    def test_what_is_not_a_registry_id_or_one_argument_is_refused_before_the_registry_is_read(self):
        for args in ({"project": "../x"}, {"project": "a/b"}, {"project": ""}, {"project": 3}, {"project": "gzapp", "x": 1}, {}, None, [], "gzapp",
                     {"project": "-oProxyCommand=x"}, {"project": "GZAPP"}):
            doc = cl.clone({"op": "clone", "args": args}, root="/nonexistent", home=self.home, run=lambda *a, **k: self.fail("ran"))
            self.assertEqual((doc["status"], doc["reason"]), ("refused", "clone takes one argument, a project id"), args)
        self.assertEqual(cl.clone("x", root="/nonexistent", home=self.home)["status"], "refused")
        self.assertFalse(os.path.exists(os.path.join(self.home, "projects")))

    def test_a_clone_that_fails_is_not_ok_names_why_and_runs_no_bootstrap(self):
        self.registry({"gzapp": {"remotes": [os.path.join(self.dir, "missing.git")]}})
        doc = self.go()
        self.assertEqual(doc["status"], "failed")
        self.assertIn("git clone exited 128", doc["reason"])
        self.assertFalse(os.path.exists(self.dest), "a failed clone leaves no half working copy")
        self.assertEqual(self.bootstraps(), [])
        self.assertNotIn(doc["status"], ctl.ACTION_OK["clone"])

    def test_a_clone_that_hangs_is_a_failure_with_its_bound(self):
        def hang(argv, **kw):
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        doc = self.go(run=hang, clone_timeout_ms=1500)
        self.assertEqual(doc, {"status": "failed", "reason": "git clone did not finish within 1.5 s", "project": "gzapp"})

    def test_a_missing_git_a_killed_child_and_a_flood_are_each_their_own_failure(self):
        for exc, words in ((FileNotFoundError(2, "No such file or directory", "git"), "could not run"),
                           (subprocess.CalledProcessError(-9, ["git"]), "killed by SIGKILL"),
                           (util.OutputOverflow(["git"], 5, b"", b""), "printed more than")):
            def run(argv, e=exc, **kw):
                raise e
            doc = self.go(run=run)
            self.assertEqual(doc["status"], "failed")
            self.assertIn(words, doc["reason"])

    def test_a_failed_bootstrap_after_a_clone_is_failed_and_the_retry_finds_it_present_and_bootstraps_again(self):
        self.script("3")
        doc = self.go()
        self.assertEqual(doc["status"], "failed")
        self.assertIn("cloned, but bootstrap.sh exited 3: bootstrap said no", doc["reason"])
        self.assertTrue(os.path.isdir(os.path.join(self.dest, ".git")))
        self.script("0")
        doc = self.go()
        self.assertEqual(doc["status"], "present")
        self.assertEqual(len(self.bootstraps()), 2)

    def test_a_bootstrap_that_hangs_is_a_failure(self):
        def run(argv, **kw):
            if argv[0] == "bash":
                raise subprocess.TimeoutExpired(argv, kw["timeout"])
            return util.run_bounded(argv, **kw)
        doc = self.go(run=run)
        self.assertEqual(doc["status"], "failed")
        self.assertIn("cloned, but bootstrap.sh did not finish within 300 s", doc["reason"])

    def test_a_path_that_is_not_a_working_copy_is_left_alone_and_reported(self):
        os.makedirs(self.dest)
        with open(os.path.join(self.dest, "keep"), "w") as fh:
            fh.write("x")
        doc = self.go()
        self.assertEqual(doc["status"], "failed")
        self.assertIn("not a working copy", doc["reason"])
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "keep")))
        self.assertEqual(self.bootstraps(), [])

    def test_a_symlink_at_the_destination_is_never_followed(self):
        elsewhere = os.path.join(self.dir, "elsewhere")
        git("clone", "-q", self.remote, elsewhere)
        os.makedirs(os.path.dirname(self.dest))
        os.symlink(elsewhere, self.dest)
        git("remote", "set-url", "origin", HTTPS, cwd=elsewhere)
        doc = self.go()
        self.assertEqual(doc["status"], "failed")
        self.assertEqual(git("config", "--get", "remote.origin.url", cwd=elsewhere), HTTPS, "the link's target was not touched")

    def test_an_unreadable_registry_is_a_failure_not_an_unknown_project(self):
        os.remove(os.path.join(self.root, "projects", "registry.json"))
        doc = self.go()
        self.assertEqual(doc["status"], "failed")
        self.assertIn("registry could not be read", doc["reason"])

    def test_a_registry_that_is_not_json_names_no_project(self):
        with open(os.path.join(self.root, "projects", "registry.json"), "w") as fh:
            fh.write("{ not json")
        self.assertEqual(self.go()["status"], "refused")

    def test_the_callers_git_variables_do_not_reach_the_clone_and_a_prompt_is_never_waited_on(self):
        decoy = os.path.join(self.dir, "decoy")
        os.makedirs(decoy)
        seen: list[dict] = []

        def run(argv, **kw):
            seen.append(kw["env"])
            return util.run_bounded(argv, **kw)
        with mock.patch.dict(os.environ, {"GIT_DIR": decoy, "GIT_WORK_TREE": decoy, "HOME": "/nonexistent"}):
            doc = self.go(run=run)
        self.assertEqual(doc["status"], "cloned", doc)
        self.assertEqual(os.listdir(decoy), [], "the decoy repository was not written")
        for env in seen:
            self.assertEqual((env["HOME"], env["GIT_TERMINAL_PROMPT"]), (self.home, "0"))
            self.assertFalse([k for k in env if k.startswith("GIT_") and k != "GIT_TERMINAL_PROMPT"])

    def test_an_existing_projects_directory_and_other_working_copies_are_left_as_they_are(self):
        other = os.path.join(self.home, "projects", "other")
        git("init", "-q", other)
        self.assertEqual(self.go()["status"], "cloned")
        self.assertTrue(os.path.isdir(os.path.join(other, ".git")))


class Shared(unittest.TestCase):
    def test_the_registrys_remote_reads_from_text_and_unknown_stays_unknown(self):
        text = json.dumps({"projects": {"a": {"remotes": ["git@h:o/a.git"]}}})
        self.assertEqual(pc.registry_remote(text, "a"), "git@h:o/a.git")
        for t, pid in ((text, "b"), ("{", "a"), ("[]", "a"), ('{"projects": []}', "a"), ('{"projects": {"a": 1}}', "a"), ("", "a")):
            self.assertIsNone(pc.registry_remote(t, pid), (t, pid))

    def test_each_origin_case_has_its_plan(self):
        r = "git@h:o/a.git"
        self.assertEqual(pc.plan_origin("", "x", ""), pc.OriginPlan("none"))
        self.assertEqual(pc.plan_origin(r, "", "p"), pc.OriginPlan("unreadable"))
        self.assertEqual(pc.plan_origin(r, r, ""), pc.OriginPlan("keep"))
        self.assertEqual(pc.plan_origin(r, HTTPS, ""), pc.OriginPlan("set"))
        self.assertEqual(pc.plan_origin(r, r, r), pc.OriginPlan("keep"), "a push URL equal to the remote is no warning")
        plan = pc.plan_origin(r, HTTPS, "git@other:o/a.git")
        self.assertEqual(plan.action, "set")
        self.assertIn("git@other:o/a.git", plan.warning)


class Ctl(unittest.TestCase):
    def test_the_verb_is_a_signed_action_with_a_budget_past_the_accounts_own_bounds(self):
        self.assertIn("clone", ctl.ACTION_OPS)
        self.assertIn("clone", ops.OPS)
        self.assertNotIn("clone", ops.PUBLIC_OPS)
        a = ctl.parse_args(["ux-designer-01", "clone", "gzapp"])
        self.assertEqual((a["op"], a["tool"], a["targets"], a["timeout"]), ("clone", "gzapp", ["ux-designer-01"], cl.CLONE_BUDGET_S))
        self.assertEqual(cl.CLONE_BUDGET_S, (cl.CLONE_TIMEOUT_MS + 3 * cl.GIT_TIMEOUT_MS + 300_000) // 1000 + 30)
        self.assertEqual(ctl.VERB["clone"].signed, "always")
        self.assertIn("clone", ctl.USAGE)
        self.assertIn("clone <project-id>", ctl.render_help("clone"))

    def test_it_takes_one_registry_id_and_named_logins_never_all(self):
        for argv in (["a", "clone"], ["a", "clone", "../x"], ["a", "clone", "GZAPP"], ["all", "clone", "gzapp"], ["a", "all", "clone", "gzapp"]):
            with self.assertRaises(ctl.CtlError, msg=argv):
                ctl.parse_args(argv)
        self.assertEqual(ctl.parse_args(["a", "b", "clone", "gzapp"])["targets"], ["a", "b"])
        self.assertEqual(ctl.parse_args(["a", "clone", "gzapp.web"])["tool"], "gzapp.web")

    def rows(self, doc: dict) -> list:
        return ctl.rows([{"login": "a", "host": "h", "address": "h/a"}],
                        [{"kind": "reply", "from": "h/a", "op": "clone", "latency_ms": 1, "data": {"clone": doc}}])

    def test_the_table_says_per_account_what_became_of_the_clone_and_escapes_what_it_was_sent(self):
        ok = ctl.table("clone", self.rows({"status": "cloned", "project": "gzapp"})).splitlines()[0]
        self.assertTrue(ok.startswith("a") and "cloned" in ok and "gzapp" in ok, ok)
        pres = ctl.table("clone", self.rows({"status": "present", "project": "gzapp", "origin": "set"})).splitlines()[0]
        self.assertIn("(origin set)", pres)
        bad = ctl.table("clone", self.rows({"status": "failed", "project": "gzapp", "reason": "git clone exited 128\x1b]0;x\x07"})).splitlines()[0]
        self.assertIn("failed", bad)
        self.assertNotIn("\x1b", bad)
        self.assertIn("refused", ctl.table("clone", self.rows({"status": "refused", "reason": "the registry holds no project x with a remote"})))

    def run_main(self, answer: dict, extra=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        reg = os.path.join(tmp.name, "registry.json")
        with open(reg, "w", encoding="utf-8") as fh:
            json.dump({"hosts": {"h1": {"operator": "op"}}, "placement": {"a": "h1"}}, fh)
        sent: list[dict] = []

        def call(path, method="GET", body=None, **_kw):
            if path.startswith("/api/send"):
                sent.append(json.loads(json.loads(body)["content"]))
                return {"id": "m1"}
            reply = {"v": 1, "kind": "reply", "id": "r1", "in_reply_to": sent[-1]["id"], "from": "h1/a", "op": "clone", "ok": True, "data": {"clone": answer}}
            return {"messages": [{"id": "x1", "content": json.dumps(reply)}]}
        keep = (ctl.signing_key, ctl.sign_request)
        ctl.signing_key, ctl.sign_request = (lambda *a, **k: {"key": "k"}), (lambda r, k: r)
        self.addCleanup(lambda: setattr(ctl, "signing_key", keep[0]) or setattr(ctl, "sign_request", keep[1]))
        out, err = [], []
        rc = ctl.main(["a", "clone", "gzapp", "--timeout", "5", *extra], registry=reg, call=call, out=out.append, err=err.append,
                      sleep=lambda s: None, who={"host": "h1", "agent": "op", "project": None}, token="tok")
        return rc, sent, "\n".join(out), "\n".join(err)

    def test_the_run_exits_0_on_cloned_and_present_and_1_on_every_other_row(self):
        for status, want in (("cloned", 0), ("present", 0), ("failed", 1), ("refused", 1), ("surprise", 1)):
            rc, sent, out, err = self.run_main({"status": status, "project": "gzapp", "reason": "why"})
            self.assertEqual(rc, want, (status, out, err))
            self.assertEqual((sent[0]["op"], sent[0]["args"]), ("clone", {"project": "gzapp"}))


class Daemon(Scratch):
    def test_the_daemon_answers_the_action_with_its_own_home_and_root(self):
        ctx = {"me": {"address": "h/a"}, "started": "2026-10-28T00:00:00.000Z", "home": self.home, "root": self.root}
        reply = agentd.answer({"op": "clone", "id": "r1", "args": {"project": "gzapp"}}, ctx)
        self.assertEqual(reply["data"]["clone"]["status"], "cloned", reply)
        self.assertTrue(os.path.isdir(os.path.join(self.dest, ".git")))
        refused = agentd.answer({"op": "clone", "id": "r2", "args": {"project": "nope"}}, ctx)
        self.assertEqual(refused["data"]["clone"]["status"], "refused")
        self.assertEqual(agentd.answer({"op": "clone", "id": "r3"}, ctx)["data"]["clone"]["status"], "refused")


if __name__ == "__main__":
    unittest.main()
