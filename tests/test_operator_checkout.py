#!/usr/bin/env python3
"""The operator's checkout beside the engine, and the engine pin it carries (agent-fabric ADR-045 §6,
tools/fabric/operator_checkout.py), on each surface that learned it: the module itself (absent clone, present
clone, unreachable remote, an empty remote), the pin's reader, bootstrap's step, `upgrade fabric`, the
launcher's verdict and pull, moveto's entry refresh and new-agent's worker step.

Every repository is a local bare origin under one mkdtemp; git runs with no global or system configuration and
no terminal prompt, and the clone URL is injected (AGENT_FABRIC_OPERATOR_CLONE_URL), so nothing reaches the
network or this account's checkouts."""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(HERE, "tools", "fabric")
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(HERE, "runtime", "provisioning", "moveto"))
import operator_checkout as oc  # noqa: E402
import bootstrap  # noqa: E402
import launch  # noqa: E402
import moveto  # noqa: E402
from control import upgrade as U  # noqa: E402
from provisioning import worker, worker_args as wa  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_TERMINAL_PROMPT": "0"}
NOWHERE = "file:///nonexistent/operator.git"


def git(cwd: str, *a: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, env={**os.environ, **GIT_ENV}, timeout=60)
    if check and r.returncode != 0:
        raise AssertionError(f"git {a}: {r.stderr}")
    return r.stdout.strip()


class Fx:
    """projects/ holding an engine clone (agent-fabric) and, on request, an operator clone (blueteam-fabric)."""

    def __init__(self, tc: unittest.TestCase, operator: bool = True, operator_commits: bool = True) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="operator-checkout-")
        tc.addCleanup(tmp.cleanup)
        self.base = tmp.name
        self.projects = os.path.join(self.base, "projects")
        os.makedirs(self.projects)
        self.engine_origin = os.path.join(self.base, "engine.git")
        self.engine_seed = os.path.join(self.base, "engine-seed")
        self.engine = os.path.join(self.projects, "agent-fabric")
        git(self.base, "init", "-q", "--bare", "-b", "main", self.engine_origin)
        git(self.base, "init", "-q", "-b", "main", self.engine_seed)
        # moveto and the upgrade run the module and git.py of the checkout under them.
        os.makedirs(os.path.join(self.engine_seed, "tools", "fabric"))
        for name in ("operator_checkout.py", "git.py"):
            with open(os.path.join(TOOLS, name), "rb") as src, open(os.path.join(self.engine_seed, "tools", "fabric", name), "wb") as dst:
                dst.write(src.read())
        git(self.engine_seed, "remote", "add", "origin", self.engine_origin)
        self.first = self.engine_advance("one")
        git(self.projects, "clone", "-q", self.engine_origin, self.engine)
        self.op_origin = os.path.join(self.base, "operator.git")
        self.op_seed = os.path.join(self.base, "operator-seed")
        self.op = oc.path(self.projects)
        git(self.base, "init", "-q", "--bare", "-b", "main", self.op_origin)
        git(self.base, "init", "-q", "-b", "main", self.op_seed)
        git(self.op_seed, "remote", "add", "origin", self.op_origin)
        if operator_commits:
            self.operator_commit("readme", "x")
        if operator:
            git(self.projects, "clone", "-q", self.op_origin, self.op)

    def engine_advance(self, name: str) -> str:
        with open(os.path.join(self.engine_seed, f"{name}.txt"), "w") as fh:
            fh.write(name)
        git(self.engine_seed, "add", "-A")
        git(self.engine_seed, "commit", "-q", "-m", name)
        git(self.engine_seed, "push", "-q", "origin", "main")
        return git(self.engine_seed, "rev-parse", "HEAD")

    def operator_commit(self, rel: str, content: str) -> str:
        full = os.path.join(self.op_seed, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write(content)
        git(self.op_seed, "add", "-A")
        git(self.op_seed, "commit", "-q", "-m", rel)
        git(self.op_seed, "push", "-q", "origin", "main")
        return git(self.op_seed, "rev-parse", "HEAD")

    def pin(self, sha: str, raw: str | None = None) -> None:
        """The operator publishes a pin; the account has not pulled it yet."""
        self.operator_commit(oc.PIN_PATH, (sha + "\n") if raw is None else raw)

    def pull_operator(self) -> None:
        git(self.op, "pull", "-q", "--ff-only")

    def head(self) -> str:
        return git(self.engine, "rev-parse", "HEAD")


def env(**extra: str) -> dict:
    return mock.patch.dict(os.environ, {**GIT_ENV, **extra})


class Module(unittest.TestCase):
    def test_absent_clone_is_cloned_beside_the_engine(self):
        f = Fx(self, operator=False)
        with env():
            s = oc.clone(f.projects, f.op_origin)
        self.assertEqual(s.state, "cloned")
        self.assertTrue(oc.is_checkout(f.op))
        self.assertEqual(os.path.dirname(f.op), f.projects)
        self.assertEqual(os.path.basename(f.op), "blueteam-fabric")

    def test_an_unreachable_remote_is_said_nothing_is_left_and_it_does_not_raise(self):
        f = Fx(self, operator=False)
        with env():
            s = oc.clone(f.projects, NOWHERE)
        self.assertEqual(s.state, "offline")
        self.assertIn("not cloned", s.line)
        self.assertIn(NOWHERE, s.line)
        self.assertFalse(os.path.lexists(f.op), "a failed clone must leave no half-made directory")

    def test_a_present_clone_is_synced_never_cloned_over(self):
        f = Fx(self)
        marker = os.path.join(f.op, "mine.txt")
        with open(marker, "w") as fh:
            fh.write("local")
        with env():
            self.assertEqual(oc.clone(f.projects, NOWHERE).state, "current", "a present clone does not touch the URL at all")
            f.operator_commit("two", "2")
            self.assertEqual(oc.clone(f.projects, NOWHERE).state, "updated")
        self.assertTrue(os.path.exists(marker))
        self.assertEqual(git(f.op, "rev-parse", "HEAD"), git(f.op_seed, "rev-parse", "HEAD"))

    def test_a_dry_run_clone_makes_nothing(self):
        f = Fx(self, operator=False)
        with env():
            s = oc.clone(f.projects, f.op_origin, dry_run=True)
        self.assertEqual(s.state, "would-clone")
        self.assertFalse(os.path.lexists(f.op))

    def test_an_empty_remote_is_cloned_and_is_not_unreachable(self):
        f = Fx(self, operator=False, operator_commits=False)
        with env():
            self.assertEqual(oc.clone(f.projects, f.op_origin).state, "cloned")
            s = oc.sync(f.op)
        self.assertEqual(s.state, "empty")
        self.assertIn("no main branch yet", s.line)

    def test_sync_with_the_remote_gone_says_offline_and_leaves_the_checkout(self):
        f = Fx(self)
        before = git(f.op, "rev-parse", "HEAD")
        os.rename(f.op_origin, f.op_origin + ".away")
        with env():
            s = oc.sync(f.op)
        self.assertEqual(s.state, "offline")
        self.assertIn("not refreshed", s.line)
        self.assertEqual(git(f.op, "rev-parse", "HEAD"), before)

    def test_sync_leaves_a_branch_or_a_diverged_checkout_and_says_so(self):
        f = Fx(self)
        f.operator_commit("two", "2")
        git(f.op, "switch", "-q", "-c", "work")
        with env():
            s = oc.sync(f.op)
        self.assertEqual(s.state, "left")
        self.assertIn("on work, not main", s.line)
        git(f.op, "switch", "-q", "main")
        with open(os.path.join(f.op, "local.txt"), "w") as fh:
            fh.write("l")
        git(f.op, "add", "-A")
        git(f.op, "commit", "-q", "-m", "local")
        with env():
            s = oc.sync(f.op)
        self.assertEqual(s.state, "left")
        self.assertIn("cannot fast-forward", s.line)

    def test_a_directory_that_is_not_a_checkout_is_reported_and_not_replaced(self):
        f = Fx(self, operator=False)
        os.mkdir(f.op)
        with env():
            self.assertEqual(oc.sync(f.op).state, "not-a-checkout")
            self.assertEqual(oc.clone(f.projects, f.op_origin).state, "not-a-checkout")
        self.assertEqual(os.listdir(f.op), [])

    def test_a_missing_checkout_is_never_replaced_by_the_engine_tree(self):
        f = Fx(self, operator=False)
        s = oc.sync(f.op)
        self.assertEqual((s.state, f.op in s.line), ("absent", True))
        self.assertEqual(oc.read_pin(f.op).kind, "absent")
        self.assertFalse(os.path.lexists(f.op))

    def test_git_is_never_allowed_to_ask_a_person(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GIT_SSH_COMMAND", None)
            e = oc._noninteractive()
        self.assertEqual((e["GIT_TERMINAL_PROMPT"], e["GIT_SSH_COMMAND"]), ("0", "ssh -o BatchMode=yes"))
        with mock.patch.dict(os.environ, {"GIT_SSH_COMMAND": "ssh -i k"}):
            self.assertEqual(oc._noninteractive()["GIT_SSH_COMMAND"], "ssh -i k", "an account's own ssh command stands")

    def test_the_clone_url_comes_from_the_environment_else_ssh(self):
        self.assertEqual(oc.clone_url({}), "git@github.com:BlueTeam-OU/blueteam-fabric.git")
        self.assertEqual(oc.clone_url({oc.CLONE_URL_ENV: "x"}), "x")
        self.assertEqual(oc.clone_url({oc.CLONE_URL_ENV: ""}), "git@github.com:BlueTeam-OU/blueteam-fabric.git")


class Pin(unittest.TestCase):
    def pin(self, f: Fx, raw: str) -> oc.Pin:
        f.pin("", raw=raw)
        f.pull_operator()
        return oc.read_pin(f.op)

    def test_absent_in_each_of_its_four_shapes_is_not_an_error(self):
        f = Fx(self, operator=False)
        self.assertEqual(oc.read_pin(f.op).kind, "absent")                      # no directory
        os.mkdir(f.op)
        self.assertEqual(oc.read_pin(f.op).kind, "absent")                      # not a checkout
        os.rmdir(f.op)
        g = Fx(self, operator_commits=False)
        self.assertIn("no commits", oc.read_pin(g.op).why)                      # an empty repository
        h = Fx(self)
        self.assertIn(f"no {oc.PIN_PATH}", oc.read_pin(h.op).why)               # no file

    def test_a_full_lowercase_sha_is_the_pin_with_or_without_the_newline(self):
        f = Fx(self)
        self.assertEqual(self.pin(f, f.first + "\n"), oc.Pin("pinned", f.first))
        self.assertEqual(self.pin(f, f.first), oc.Pin("pinned", f.first))

    def test_anything_else_in_the_file_is_malformed_never_absent(self):
        f = Fx(self)
        good = f.first
        for raw in (good.upper() + "\n", good[:39] + "\n", good + "a\n", good + " \n", good + " v1\n", good + "\n" + good + "\n",
                    "", "\n", good + "\r\n", " " + good + "\n", "HEAD\n", "x" * 500):
            p = self.pin(f, raw)
            self.assertEqual(p.kind, "malformed", repr(raw))
            self.assertIn(oc.PIN_PATH, p.why)

    def test_a_symlink_is_not_a_pin(self):
        f = Fx(self)
        f.operator_commit("target", f.first + "\n")
        os.makedirs(os.path.join(f.op_seed, ".agent-fabric"), exist_ok=True)
        os.symlink("../target", os.path.join(f.op_seed, oc.PIN_PATH))
        git(f.op_seed, "add", "-A")
        git(f.op_seed, "commit", "-q", "-m", "link")
        git(f.op_seed, "push", "-q", "origin", "main")
        f.pull_operator()
        p = oc.read_pin(f.op)
        self.assertEqual(p.kind, "malformed")
        self.assertIn("not a regular file", p.why)

    def test_the_pin_is_the_committed_one_an_edit_in_the_working_tree_is_not(self):
        f = Fx(self)
        self.assertEqual(self.pin(f, f.first + "\n").sha, f.first)
        with open(os.path.join(f.op, oc.PIN_PATH), "w") as fh:
            fh.write("garbage")
        self.assertEqual(oc.read_pin(f.op), oc.Pin("pinned", f.first))


class Plan(unittest.TestCase):
    def test_no_pin_goes_where_the_engine_always_went(self):
        f = Fx(self, operator=False)
        p = oc.engine_plan(f.engine, oc.read_pin(f.op))
        self.assertEqual(p.target, "origin/main")
        self.assertIn("no engine pin is in force", p.notes[0])
        self.assertEqual(p.refusal, "")

    def test_a_pin_ahead_of_head_is_the_target_even_when_main_is_further(self):
        f = Fx(self)
        pin = f.engine_advance("two")
        f.engine_advance("three")
        git(f.engine, "fetch", "-q", "origin", "main")
        p = oc.engine_plan(f.engine, oc.Pin("pinned", pin))
        self.assertEqual((p.target, p.notes), (pin, []))

    def test_a_pin_at_head_is_the_target(self):
        f = Fx(self)
        self.assertEqual(oc.engine_plan(f.engine, oc.Pin("pinned", f.head())).target, f.head())

    def test_a_pin_behind_head_leaves_the_engine_and_says_it_is_ahead(self):
        f = Fx(self)
        f.engine_advance("two")
        git(f.engine, "pull", "-q", "--ff-only")
        p = oc.engine_plan(f.engine, oc.Pin("pinned", f.first))
        self.assertEqual(p.target, "")
        self.assertIn("ahead of the operator's pin", p.notes[0])

    def test_a_pin_the_engine_does_not_have_leaves_the_engine_and_says_so(self):
        f = Fx(self)
        p = oc.engine_plan(f.engine, oc.Pin("pinned", "a" * 40))
        self.assertEqual(p.target, "")
        self.assertIn("does not have", p.notes[0])

    def test_a_diverged_pin_leaves_the_engine(self):
        f = Fx(self)
        git(f.engine, "switch", "-q", "-c", "side")
        with open(os.path.join(f.engine, "side.txt"), "w") as fh:
            fh.write("s")
        git(f.engine, "add", "-A")
        git(f.engine, "commit", "-q", "-m", "side")
        side = git(f.engine, "rev-parse", "HEAD")
        git(f.engine, "switch", "-q", "main")
        f.engine_advance("two")
        git(f.engine, "pull", "-q", "--ff-only")
        p = oc.engine_plan(f.engine, oc.Pin("pinned", side))
        self.assertEqual(p.target, "")
        self.assertIn("diverged", p.notes[0])

    def test_a_malformed_pin_is_a_refusal_not_a_plan(self):
        f = Fx(self)
        p = oc.engine_plan(f.engine, oc.Pin("malformed", why="bad"))
        self.assertEqual((p.refusal, p.target), ("bad", ""))


class Refresh(unittest.TestCase):
    """The shared refresh moveto runs: the operator is synced, then the engine goes to the pin."""

    def refresh(self, f: Fx) -> tuple[int, list[str]]:
        with env():
            return oc.refresh(f.engine, f.projects)

    def test_with_a_pin_the_engine_stops_at_it(self):
        f = Fx(self)
        pin = f.engine_advance("two")
        f.engine_advance("three")
        f.pin(pin)
        rc, lines = self.refresh(f)
        self.assertEqual((rc, f.head()), (0, pin))
        self.assertEqual(lines, ["operator checkout %s fast-forwarded 1 commit(s)" % f.op])

    def test_without_an_operator_checkout_the_engine_tracks_main_and_one_line_says_so(self):
        f = Fx(self, operator=False)
        top = f.engine_advance("two")
        rc, lines = self.refresh(f)
        self.assertEqual((rc, f.head(), len(lines)), (0, top, 1))
        self.assertIn("is absent; no engine pin is in force", lines[0])

    def test_a_malformed_pin_refuses_and_the_engine_stays(self):
        f = Fx(self)
        before = f.head()
        f.engine_advance("two")
        f.pin("", raw="not a sha\n")
        rc, lines = self.refresh(f)
        self.assertEqual((rc, f.head()), (1, before))
        self.assertIn("not one full 40-hex commit id", lines[-1])

    def test_an_unreachable_operator_is_said_and_the_engine_half_still_runs(self):
        f = Fx(self)
        top = f.engine_advance("two")
        os.rename(f.op_origin, f.op_origin + ".away")
        rc, lines = self.refresh(f)
        self.assertEqual((rc, f.head()), (0, top))
        self.assertTrue(any("not refreshed" in l for l in lines), lines)

    def hang_operator_fetch(self, f: Fx, seconds: int) -> None:
        """The operator's remote answers the fetch with a server that never does (a stalled ssh, a dead route)."""
        hang = os.path.join(f.base, "hang-upload-pack")
        with open(hang, "w") as fh:
            fh.write(f"#!/bin/sh\nexec sleep {seconds}\n")
        os.chmod(hang, 0o755)
        git(f.op, "config", "remote.origin.uploadpack", hang)

    def test_a_hanging_operator_fetch_is_bounded_by_the_budget_and_the_engine_half_still_runs(self):
        f = Fx(self)
        top = f.engine_advance("two")
        self.hang_operator_fetch(f, 12)
        with env():
            rc, lines = oc.refresh(f.engine, f.projects, budget=10)
        self.assertEqual((rc, f.head()), (0, top))
        self.assertTrue(any(l.startswith("operator checkout") and "no answer within 3 s" in l for l in lines), lines)

    def test_a_budget_leaves_the_engine_its_own_larger_share(self):
        self.assertGreater(oc.ENGINE_SHARE, oc.OPERATOR_SHARE)
        self.assertLess(oc.ENGINE_SHARE + oc.OPERATOR_SHARE, 1)

    def test_an_unreachable_operator_keeps_the_pin_the_checkout_last_held(self):
        f = Fx(self)
        pin = f.engine_advance("two")
        f.engine_advance("three")
        f.pin(pin)
        f.pull_operator()
        os.rename(f.op_origin, f.op_origin + ".away")
        rc, _ = self.refresh(f)
        self.assertEqual((rc, f.head()), (0, pin))

    def test_the_command_line_speaks_on_stderr_only_and_exits_by_the_plan(self):
        f = Fx(self)
        pin = f.engine_advance("two")
        f.engine_advance("three")
        f.pin(pin)
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "operator_checkout.py"), "refresh", "--engine", f.engine, "--projects", f.projects],
                           capture_output=True, text=True, env={**os.environ, **GIT_ENV}, timeout=120)
        self.assertEqual((r.returncode, r.stdout, f.head()), (0, "", pin))
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "operator_checkout.py"), "ensure", "--projects", f.projects, "--dry-run"],
                           capture_output=True, text=True, env={**os.environ, **GIT_ENV}, timeout=120)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_bad_arguments_exit_2_with_nothing_on_stdout(self):
        f = Fx(self)
        for argv in ([], ["nope"], ["ensure"], ["ensure", "--projects", "/nonexistent"], ["ensure", "--engine", f.engine],
                     ["refresh", "--projects", f.projects], ["ensure", "--projects"], ["ensure", "--projects", f.projects, "--bogus"]):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = oc.main(argv)
            self.assertEqual((rc, out.getvalue()), (2, ""), argv)
            self.assertTrue(err.getvalue().startswith("operator_checkout: "), argv)


class BootstrapStep(unittest.TestCase):
    def step(self, f: Fx, dry: bool = False, url: str | None = None) -> tuple[bootstrap.Bootstrap, str]:
        b = bootstrap.Bootstrap(f.projects, dry, root=f.engine)
        out = io.StringIO()
        with env(**({oc.CLONE_URL_ENV: url} if url else {})), redirect_stdout(out):
            b.operator_checkout()
        return b, out.getvalue()

    def test_absent_is_cloned_and_counted_written(self):
        f = Fx(self, operator=False)
        b, out = self.step(f, url=f.op_origin)
        self.assertEqual(out, f"  +  {f.op}\n")
        self.assertEqual((b.changed, b.same, b.failed), (1, 0, 0))
        self.assertTrue(oc.is_checkout(f.op))

    def test_present_is_current_and_a_second_run_writes_nothing(self):
        f = Fx(self)
        b, out = self.step(f, url=NOWHERE)
        self.assertEqual((out, b.changed), (f"  =  {f.op}\n", 0))

    def test_present_and_behind_is_fast_forwarded_and_counted(self):
        f = Fx(self)
        f.operator_commit("two", "2")
        b, out = self.step(f)
        self.assertEqual((out, b.changed), (f"  +  {f.op} (fast-forwarded)\n", 1))

    def test_unreachable_is_one_uncounted_bang_line_on_stdout_and_the_run_goes_on(self):
        f = Fx(self, operator=False)
        b, out = self.step(f, url=NOWHERE)
        self.assertTrue(out.startswith("  !  operator checkout "), out)
        self.assertEqual(out.count("\n"), 1)
        self.assertEqual((b.changed, b.same, b.failed), (0, 0, 0))
        self.assertFalse(os.path.lexists(f.op))

    def test_a_dry_run_says_it_would_clone_and_clones_nothing(self):
        f = Fx(self, operator=False)
        b, out = self.step(f, dry=True, url=f.op_origin)
        self.assertEqual(out, f"  +  {f.op} (would clone)\n")
        self.assertFalse(os.path.lexists(f.op))


class UpgradeFabricPin(unittest.TestCase):
    def upgrade(self, f: Fx, target: str) -> dict:
        record = os.path.join(f.base, "bootstrap.log")
        os.makedirs(os.path.join(f.engine, "runtime", "claude-code"), exist_ok=True)
        with open(os.path.join(f.engine, "runtime", "claude-code", "bootstrap.sh"), "w") as fh:
            fh.write(f"echo ran >> {record}\n")
        git(f.engine, "update-index", "--assume-unchanged", "--", ".") if False else None
        req = {"id": "r", "from": "h/user", "op": "upgrade", "args": {"piece": "fabric", "commit": target}}
        with env():
            return U.upgrade_fabric(req, root=f.engine, sessions=[], env={"PATH": os.environ["PATH"], "HOME": f.base, **GIT_ENV})

    def test_the_move_is_to_the_pin_not_to_the_commit_the_coordinator_sent(self):
        f = Fx(self)
        pin = f.engine_advance("two")
        top = f.engine_advance("three")
        f.pin(pin)
        r = self.upgrade(f, top)
        self.assertEqual((r["status"], f.head()), ("upgraded", pin))
        self.assertIn("fast-forwarded", r["operator"])

    def test_a_commit_behind_the_pin_is_the_limit_when_it_is_the_nearer(self):
        f = Fx(self)
        mid = f.engine_advance("two")
        pin = f.engine_advance("three")
        f.pin(pin)
        r = self.upgrade(f, mid)
        self.assertEqual((r["status"], f.head()), ("upgraded", mid))

    def test_a_pin_the_engine_is_ahead_of_holds_it_and_says_so(self):
        f = Fx(self)
        f.pin(f.first)
        top = f.engine_advance("two")
        git(f.engine, "pull", "-q", "--ff-only")
        r = self.upgrade(f, top)
        self.assertEqual((r["status"], f.head()), ("current", top))
        self.assertIn("ahead of the operator's pin", r["operator"])

    def test_a_malformed_pin_refuses_before_anything_moves_or_bootstraps(self):
        f = Fx(self)
        top = f.engine_advance("two")
        before = f.head()
        f.pin("", raw="oops\n")
        r = self.upgrade(f, top)
        self.assertEqual(r["status"], "refused")
        self.assertIn("not one full 40-hex commit id", r["reason"])
        self.assertEqual(f.head(), before)
        self.assertFalse(os.path.exists(os.path.join(f.base, "bootstrap.log")))

    def test_an_unreachable_operator_is_said_in_the_reply_and_the_engine_half_runs(self):
        f = Fx(self)
        top = f.engine_advance("two")
        os.rename(f.op_origin, f.op_origin + ".away")
        r = self.upgrade(f, top)
        self.assertEqual((r["status"], f.head()), ("upgraded", top))
        self.assertIn("not refreshed", r["operator"])

    def test_no_operator_checkout_leaves_the_reply_as_it_was(self):
        f = Fx(self, operator=False)
        top = f.engine_advance("two")
        r = self.upgrade(f, top)
        self.assertEqual((r["status"], f.head(), "operator" in r), ("upgraded", top, False))


class LauncherPin(unittest.TestCase):
    def verdict(self, f: Fx):
        with env():
            return launch.fabric_verdict(f.engine)

    def test_without_an_operator_the_verdict_is_behind_origin_main_with_the_absent_note(self):
        f = Fx(self, operator=False)
        f.engine_advance("two")
        v = self.verdict(f)
        self.assertEqual((v.kind, v.behind, v.target), ("behind", 1, "origin/main"))
        self.assertIn("is absent; no engine pin is in force", v.notes[0])

    def test_a_pin_makes_the_target_the_pin_and_the_count_stops_at_it(self):
        f = Fx(self)
        pin = f.engine_advance("two")
        f.engine_advance("three")
        f.pin(pin)
        v = self.verdict(f)
        self.assertEqual((v.kind, v.behind, v.target), ("behind", 1, pin))
        self.assertEqual(launch.pull_ff(f.engine, v.target), ("ok", ""))
        self.assertEqual(f.head(), pin)
        self.assertEqual(self.verdict(f).kind, "current", "at the pin the launcher has nothing to pull though main is further")

    def test_a_malformed_pin_is_refused_with_its_reason(self):
        f = Fx(self)
        f.engine_advance("two")
        f.pin("", raw="x\n")
        v = self.verdict(f)
        self.assertEqual(v.kind, "pin-refused")
        self.assertIn("not one full 40-hex commit id", v.reason)

    def test_an_unreachable_operator_is_a_note_and_the_verdict_is_still_the_engines(self):
        f = Fx(self)
        f.engine_advance("two")
        os.rename(f.op_origin, f.op_origin + ".away")
        v = self.verdict(f)
        self.assertEqual((v.kind, v.behind), ("behind", 1))
        self.assertTrue(any("not refreshed" in n for n in v.notes), v.notes)

    def test_a_pin_the_engine_is_ahead_of_is_current_with_the_note(self):
        f = Fx(self)
        f.pin(f.first)
        f.engine_advance("two")
        git(f.engine, "pull", "-q", "--ff-only")
        f.engine_advance("three")
        v = self.verdict(f)
        self.assertEqual(v.kind, "current")
        self.assertIn("ahead of the operator's pin", v.notes[-1])


class LauncherKeepsFabricCurrent(unittest.TestCase):
    """launch.keep_fabric_current acts on the verdict: the pull goes to the pin, a malformed pin ends the launch."""

    class Reexec(Exception):
        pass

    def run_it(self, f: Fx) -> tuple[str, BaseException | None]:
        err, raised = io.StringIO(), None
        with env(), redirect_stderr(err), redirect_stdout(err), mock.patch.object(launch, "reexec", side_effect=self.Reexec):
            try:
                launch.keep_fabric_current(f.engine, [])
            except (self.Reexec, launch.Refused) as e:
                raised = e
        return err.getvalue(), raised

    def test_the_pull_goes_to_the_pin_and_the_launcher_relaunches_on_it(self):
        f = Fx(self)
        pin = f.engine_advance("two")
        f.engine_advance("three")
        f.pin(pin)
        said, raised = self.run_it(f)
        self.assertIsInstance(raised, self.Reexec)
        self.assertEqual(f.head(), pin)
        self.assertIn("the operator's pin", said)

    def test_a_malformed_pin_ends_the_launch_and_moves_nothing(self):
        f = Fx(self)
        before = f.head()
        f.engine_advance("two")
        f.pin("", raw="junk\n")
        said, raised = self.run_it(f)
        self.assertIsInstance(raised, launch.Refused)
        self.assertEqual(f.head(), before)
        self.assertIn("40-hex", str(raised))

    def test_with_no_operator_it_pulls_main_and_says_no_pin_is_in_force(self):
        f = Fx(self, operator=False)
        top = f.engine_advance("two")
        said, raised = self.run_it(f)
        self.assertIsInstance(raised, self.Reexec)
        self.assertEqual(f.head(), top)
        self.assertIn("no engine pin is in force", said)


class MovetoEntry(unittest.TestCase):
    def refresh(self, f: Fx) -> str:
        err = io.StringIO()
        with env(), redirect_stderr(err):
            moveto.refresh_fabric(f.engine)
        return err.getvalue()

    def test_the_entry_pull_stops_at_the_pin(self):
        f = Fx(self)
        pin = f.engine_advance("two")
        f.engine_advance("three")
        f.pin(pin)
        self.refresh(f)
        self.assertEqual(f.head(), pin)

    def test_without_an_operator_it_pulls_main_and_says_no_pin_is_in_force(self):
        f = Fx(self, operator=False)
        top = f.engine_advance("two")
        err = self.refresh(f)
        self.assertEqual(f.head(), top)
        self.assertIn("moveto: operator checkout", err)
        self.assertIn("no engine pin is in force", err)

    def test_a_malformed_pin_is_said_as_not_fast_forwarded_and_the_engine_stays(self):
        f = Fx(self)
        before = f.head()
        f.engine_advance("two")
        f.pin("", raw="junk\n")
        err = self.refresh(f)
        self.assertEqual(f.head(), before)
        self.assertIn("agent-fabric not fast-forwarded", err)
        self.assertIn("40-hex", err)

    def test_a_hanging_operator_fetch_does_not_cost_the_engine_its_refresh_and_the_note_names_the_operator(self):
        f = Fx(self)
        top = f.engine_advance("two")
        Refresh.hang_operator_fetch(self, f, 45)
        err = self.refresh(f)
        self.assertEqual(f.head(), top)
        self.assertIn("moveto: operator checkout", err)
        self.assertNotIn("timed out", err)

    def test_a_refresh_that_runs_out_names_the_refresher_not_git_pull(self):
        self.assertEqual(moveto.pull_reason("", 124, "operator_checkout refresh"), "operator_checkout refresh timed out after 30 s")

    def test_an_engine_that_predates_the_module_is_still_pulled_to_main(self):
        f = Fx(self, operator=False)
        os.unlink(os.path.join(f.engine, "tools", "fabric", "operator_checkout.py"))
        git(f.engine, "update-index", "--assume-unchanged", "tools/fabric/operator_checkout.py")
        top = f.engine_advance("two")
        self.refresh(f)
        self.assertEqual(f.head(), top)


class WorkerStep(unittest.TestCase):
    def make(self, *argv: str, home: str) -> worker.Worker:
        w = worker.Worker(wa.parse_args(["finish", "zz-unit-login", "backend-dev", *argv]), root=HERE, env={})
        w.home = home
        return w

    def test_the_account_runs_its_own_module_as_the_login_and_a_failure_is_not_fatal(self):
        with tempfile.TemporaryDirectory(prefix="operator-worker-") as home:
            module = os.path.join(home, "projects", "agent-fabric", "tools", "fabric", "operator_checkout.py")
            os.makedirs(os.path.dirname(module))
            open(module, "w").close()
            w = self.make(home=home)
            calls = []

            def as_login(argv, **kw):
                calls.append(list(argv))
                return subprocess.CompletedProcess(argv, 1, "operator checkout x not cloned from y: no route\n", None)
            err = io.StringIO()
            with mock.patch.object(w, "sudo_test", lambda flag, p: os.path.exists(p)), mock.patch.object(w, "as_login", as_login), redirect_stderr(err):
                worker.operator_checkout_step(w)
            self.assertEqual(calls, [[worker.PY, "-I", module, "ensure", "--projects", os.path.join(home, "projects")]])
            self.assertIn("6c. operator checkout x not cloned from y", err.getvalue())

    def test_a_fabric_clone_without_the_module_is_said_not_failed(self):
        with tempfile.TemporaryDirectory(prefix="operator-worker-") as home:
            w = self.make(home=home)
            err = io.StringIO()
            with mock.patch.object(w, "sudo_test", lambda flag, p: False), mock.patch.object(
                    w, "as_login", side_effect=AssertionError("must not run")), redirect_stderr(err):
                worker.operator_checkout_step(w)
            self.assertIn("6c. the operator checkout is not provisioned", err.getvalue())

    def test_a_dry_run_asks_the_module_for_a_dry_run(self):
        with tempfile.TemporaryDirectory(prefix="operator-worker-") as home:
            module = os.path.join(home, "projects", "agent-fabric", "tools", "fabric", "operator_checkout.py")
            os.makedirs(os.path.dirname(module))
            open(module, "w").close()
            w = self.make("--dry-run", home=home)
            calls = []
            with mock.patch.object(w, "sudo_test", lambda flag, p: True), mock.patch.object(
                    w, "as_login", lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", None)), redirect_stderr(io.StringIO()):
                worker.operator_checkout_step(w)
            self.assertEqual(calls[0][-1], "--dry-run")


if __name__ == "__main__":
    unittest.main()
