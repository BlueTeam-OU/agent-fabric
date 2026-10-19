#!/usr/bin/env python3
"""The oracle for runtime/claude-code/install-agent-files.sh: what it installs
into an account's ~/.claude, removes, leaves alone and prints, with its exit
status. It was runtime/claude-code/test_install-agent-files.sh, case for case,
(the bash test is gone, Wave 9 batch 8),
driven through ONE constant, INSTALL (default
runtime/claude-code/install-agent-files.sh; $INSTALL_AGENT_FILES names
another), so the same file runs against the shim and against the port behind
it (ADR-040 §5 rule 5). tests/test_install_agent_files.py is the
module's internals; this file is the command-line contract only.

The script is never run where it lies: it finds the fabric root from its own
location, so it is copied, with the modules it reads, into a fixture fabric in
scratch and run there. HOME, the state directory and TMPDIR are scratch; the
environment is rebuilt from PATH plus what the script reads, never the
session's (no AGENT_FABRIC_*, GITHUB_*, CLAUDE_*).

The bash test's cases, each a test method here:
  worker installed on a language-culture login
    test_worker_dry_run_names_it_and_writes_nothing   (dry run names it)
    test_worker_installed_byte_equal_with_class_files (installed byte-equal; class files ride)
    test_worker_second_run_changes_nothing            (a second run changes nothing)
  the locale search tool
    test_mcp_entry_written_beside_the_logins_own      (entry written beside what was there)
    test_mcp_entry_second_run_leaves_it               (a second run leaves it)
    test_websearch_denied_and_marked                  (WebSearch deny in the user settings)
  another role: the worker is removed by its marker
    test_role_change_dry_run_names_removal_and_touches_nothing
    test_role_change_removes_worker_and_names_the_role
    test_second_removal_is_silent
    test_role_change_removes_mcp_entry_keeps_the_logins_own
    test_role_change_removes_the_websearch_deny
    test_own_websearch_deny_is_left_alone
  fabric-memory (ADR-049)
    test_fabric_memory_entry_by_bare_command_name_every_role
    test_fabric_memory_second_run_leaves_it
  test_locale_without_worker_is_removed_naming_the_locale
  the class files' effort
    test_class_files_carry_the_effort_routing_resolves (+ the sources carry none)
    test_second_run_rewrites_nothing
  the pre-fabric backup
    test_backup_taken_once_not_on_every_run
  routing failure
    test_routing_failure_refuses_the_whole_run
    test_efforts_failure_alone_is_caught_and_named
  test_hand_written_worker_without_marker_survives

Added where a refactor could break the contract and the bash test is silent:
  test_success_exit_status_and_stderr_empty, test_dry_run_exit_status_zero,
  test_unknown_option_is_refused, test_missing_pin_is_exit_127,
  test_fabrics_own_previous_file_is_not_backed_up_when_routing_rewrites_it (the bash
  backup case wrote the "fabric's own file" by hand, without the marker or the record,
  so its second-backup assertion held whatever keep_person_version did).

Mutations (planted one at a time on the source as formatted, 2026-10-19, when the bash test
was retired; each killed by the test named): second run's "=" test in put() ->
test_worker_second_run_changes_nothing; "(would write)" text and the dry run's return ->
test_worker_dry_run_names_it_and_writes_nothing; written bytes -> test_worker_installed_byte_equal_...;
a class file dropped from CLASS_FILES -> test_class_files_carry_the_effort_...; the marker test
before removal -> test_hand_written_worker_without_marker_survives; "role is" text, "(would
remove" text and the dry run's branch in remove() -> the three test_role_change_* cases; the
locale in the reason -> test_locale_without_worker_is_removed_naming_the_locale; the
language-culture test on the worker and on the MCP entry -> test_role_change_* and
test_hand_written_...; the allow/deny-websearch calls and the marker on the deny ->
test_websearch_denied_and_marked, test_role_change_removes_the_websearch_deny,
test_own_websearch_deny_is_left_alone; memory_search() -> test_fabric_memory_*; the effort
write -> test_class_files_carry_the_effort_...; the pin guards (each route() call, the exit
status, the subcommand named) -> the two RoutingFailure cases; unknown option's status ->
test_unknown_option_is_refused; --locale before the record -> test_locale_option_wins_...;
the websearch entry's command, args, env and the memory entry's command ->
test_mcp_entry_written_beside_the_logins_own, test_fabric_memory_entry_by_bare_command_name_...;
the backup (keep_person_version) -> test_backup_taken_once_... and the rewrite case above.
`parts[1] != "-"` (no effort line where none is expressible) is killed by
tests/test_install_agent_files.py, not here: the fixture's routing resolves an effort for every class.

Exit codes: 0 all passed, non-zero on any failure (unittest)."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import ROUTING_OPERATOR_IGNORE, own_instance_tree, write_routing_overlay  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

INSTALL = os.path.abspath(os.environ.get("INSTALL_AGENT_FILES")
                          or os.path.join(HERE, "runtime", "claude-code", "install-agent-files.sh"))
if not os.path.isfile(INSTALL):
    sys.exit(f"test: script under test not found at {INSTALL}")
# A .py entry (the port itself, or its shim) runs on the interpreter that runs
# this file; anything else is run by bash.
IS_PY = INSTALL.endswith(".py")

# The script reads its login from the password database and has no seam for
# it. Its locale is the one the last launch recorded for that login
# (launch-locale.json, tools/fabric/launch_locale.py), never the login's
# suffix (agent-fabric ADR-060 §5 rule 8): the login ends in the fixture's
# locale so that a script reading the suffix again passes no case that has
# no record (test_no_record_is_english_whatever_the_login). Every process
# the run starts sees this login, through a sitecustomize on PYTHONPATH
# (SITECUSTOMIZE) that patches pwd.getpwuid.
LOGIN = "fixture-qq"
SUFFIX = "qq"
assert LOGIN.rsplit("-", 1)[-1] == SUFFIX != LOGIN
SITECUSTOMIZE = """\
import os, pwd
_real = pwd.getpwuid
def getpwuid(uid):
    r = _real(uid)
    if uid != os.getuid() and uid != os.geteuid():
        return r
    return pwd.struct_passwd((%r,) + tuple(r)[1:])
pwd.getpwuid = getpwuid
""" % LOGIN
# The shim runs `$AGENT_FABRIC_PYTHON -I script`; -I ignores PYTHONPATH, so
# the stand-in drops it and runs the interpreter that runs this file.
PIN_STAND_IN = '#!/bin/sh\n[ "$1" = "-I" ] && shift\nexec "%s" "$@"\n'

HOST = socket.gethostname().split(".")[0]
CLASSES = ("code-low", "code-medium", "code-high", "code-plan", "code-review")
WORKER_BODY = ("---\nname: locale-worker\ndescription: The locale worker (agent-fabric) — fixture\n"
               "model: opus\ntools:\n---\n\nფიქსტურა.\n")
# What the bash does with the pin: the fleet's python, or AGENT_FABRIC_PYTHON.
# A host or runner without the pin runs the same cases on the interpreter that
# runs this file, so the suite does not depend on the machine's installation.
PYTHON = sys.executable
TIMEOUT_S = 120


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class Fixture(unittest.TestCase):
    """A fixture fabric root, a state dir with this login's binding, HOME in scratch."""

    def setUp(self) -> None:
        self.sandbox = tempfile.mkdtemp(prefix="iaf.")
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)
        self.login_dir = os.path.join(self.sandbox, "login")
        write(os.path.join(self.login_dir, "sitecustomize.py"), SITECUSTOMIZE)
        self.pin = os.path.join(self.sandbox, "pin", "python")
        write(self.pin, PIN_STAND_IN % PYTHON)
        os.chmod(self.pin, 0o755)
        self.home = os.path.join(self.sandbox, "home")
        self.fabric = os.path.join(self.sandbox, "fabric")
        self.state = os.path.join(self.sandbox, "state")
        for d in (self.home, os.path.join(self.fabric, "runtime", "claude-code"),
                  os.path.join(self.fabric, "tools", "fabric"), os.path.join(self.state, "agents", LOGIN)):
            os.makedirs(d, exist_ok=True)
        cc = os.path.join(HERE, "runtime", "claude-code")
        # The engine half of routing from the checkout, the operator half
        # (profiles, review grade) from the frozen fixture: roles and agents
        # empty, so the cases assert what the defaults and the layers they
        # write resolve to, whoever runs this suite.
        routing = os.path.join(self.fabric, "routing")
        shutil.copytree(os.path.join(HERE, "routing"), routing, ignore=shutil.ignore_patterns(*ROUTING_OPERATOR_IGNORE))
        write_routing_overlay(routing)
        shutil.copy(os.path.join(cc, "aliases.json"), os.path.join(self.fabric, "runtime", "claude-code"))
        # The entry sits in the fixture where it sits in the checkout (a .py
        # entry finds its sibling modules from its own location); a script
        # from outside the checkout takes the shim's place.
        rel = os.path.relpath(INSTALL, HERE)
        if rel.startswith(os.pardir):
            rel = os.path.join("runtime", "claude-code", "install-agent-files.sh")
        self.entry = os.path.join(self.fabric, rel)
        os.makedirs(os.path.dirname(self.entry), exist_ok=True)
        shutil.copy(INSTALL, self.entry)
        shutil.copytree(os.path.join(cc, "agents"), os.path.join(self.fabric, "runtime", "claude-code", "agents"))
        shutil.copy(os.path.join(HERE, "runtime", "identity.py"), os.path.join(self.fabric, "runtime"))
        mem = os.path.join(self.fabric, "runtime", "mcp", "fabric-memory")
        os.makedirs(mem)
        shutil.copy(os.path.join(HERE, "runtime", "mcp", "fabric-memory", "install.py"), mem)
        for m in ("routing", "workingcopy", "layout", "install_agent_files", "fabric_writes", "launch_locale", "roots"):
            shutil.copy(os.path.join(HERE, "tools", "fabric", m + ".py"), os.path.join(self.fabric, "tools", "fabric"))
        # Present from the start: the installer runs it on every role, to
        # install or to remove, and a run without it exits 2 on a bare Python error.
        ws = os.path.join(self.fabric, "runtime", "mcp", "websearch-locale")
        os.makedirs(ws)
        shutil.copy(os.path.join(HERE, "runtime", "mcp", "websearch-locale", "install.py"), ws)
        self.worker = os.path.join(self.fabric, "identities", "roles", "language-culture", "locale", SUFFIX, "worker.md")
        write(self.worker, WORKER_BODY)
        self.dest = os.path.join(self.home, ".claude", "agents", "locale-worker.md")
        self.agents = os.path.join(self.home, ".claude", "agents")
        self.claude_json = os.path.join(self.home, ".claude.json")
        self.settings = os.path.join(self.home, ".claude", "settings.json")
        self.bind("language-culture")
        self.record_locale(SUFFIX)

    def record_locale(self, tag: str | None) -> None:
        """The launch record a launch leaves (launch_locale.py); None removes it."""
        path = os.path.join(self.state, "agents", LOGIN, "launch-locale.json")
        if tag is None:
            if os.path.exists(path):
                os.unlink(path)
        else:
            write(path, json.dumps({"locale": tag}) + "\n")

    def bind(self, role: str) -> None:
        write(os.path.join(self.state, "agents", LOGIN, "binding.json"),
              json.dumps({"agent": LOGIN, "host": HOST, "role": role, "updated_at": "x"}) + "\n")

    def env(self) -> dict[str, str]:
        # An exported operator would outrank the fixture fabric (ADR-045 §5
        # rule 3) and send the reads to data this suite did not build.
        return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": self.home, "LANG": "C.UTF-8",
                "TMPDIR": self.sandbox, "AGENT_FABRIC_ROOT": self.fabric, "AGENT_FABRIC_STATE_DIR": self.state,
                "AGENT_FABRIC_PYTHON": self.pin, "PYTHONPATH": self.login_dir, "PYTHONDONTWRITEBYTECODE": "1"}

    def run_raw(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([PYTHON if IS_PY else "bash", self.entry, *args],
                              capture_output=True, text=True, env=env or self.env(), cwd=self.sandbox,
                              timeout=TIMEOUT_S, check=False)

    def run_install(self, *args: str) -> str:
        """stdout and stderr in one string, as the bash test reads them."""
        p = self.run_raw(*args)
        return p.stdout + p.stderr

    def add_websearch_locale(self) -> None:
        write(os.path.join(os.path.dirname(self.worker), "locale.json"), json.dumps(
            {"timezone": "Asia/Tbilisi", "serpapi": {"gl": "ge", "hl": "ka", "tool_description": "ვებ-ძიება"}}))
        os.makedirs(os.path.join(self.fabric, "bin"), exist_ok=True)
        write(os.path.join(self.fabric, "bin", "fabric-websearch-locale"), "")
        write(self.claude_json, json.dumps({"theme": "dark", "mcpServers": {"mine": {"command": "x"}}}))


class WorkerInstall(Fixture):
    def test_worker_dry_run_names_it_and_writes_nothing(self) -> None:
        out = self.run_install("--dry-run")
        self.assertIn("locale-worker.md (would write)", out)
        self.assertFalse(os.path.exists(self.dest), out)

    def test_worker_installed_byte_equal_with_class_files(self) -> None:
        out = self.run_install()
        self.assertTrue(os.path.isfile(self.dest), out)
        self.assertEqual(open(self.dest, "rb").read(), open(self.worker, "rb").read())
        for k in ("code-low", "code-review"):
            self.assertTrue(os.path.isfile(os.path.join(self.agents, k + ".md")), out)

    def test_worker_second_run_changes_nothing(self) -> None:
        self.run_install()
        out = self.run_install()
        self.assertIn("locale-worker.md", out)
        self.assertIn(f"=  {self.dest}", out)

    def test_success_exit_status_and_stderr_empty(self) -> None:
        self.add_websearch_locale()
        p = self.run_raw()
        self.assertEqual((p.returncode, p.stderr), (0, ""), p.stdout)
        self.assertIn(self.dest, p.stdout)

    def test_dry_run_exit_status_zero(self) -> None:
        self.add_websearch_locale()
        p = self.run_raw("--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_unknown_option_is_refused(self) -> None:
        p = self.run_raw("--bogus")
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(os.path.exists(self.dest), p.stdout)
        self.assertNotIn("Traceback", p.stderr)

    @unittest.skipIf(IS_PY, "the pin check is the bash shim's")
    def test_missing_pin_is_exit_127(self) -> None:
        # The shim's own words, the bash's: absent pin, one line, 127. A port
        # that keeps the shim keeps this; a port that drops the pin edits it.
        env = {**self.env(), "AGENT_FABRIC_PYTHON": os.path.join(self.sandbox, "absent")}
        p = self.run_raw(env=env)
        self.assertEqual(p.returncode, 127, p.stdout + p.stderr)
        self.assertIn("the fleet's pinned Python is not installed", p.stderr)


class McpEntries(Fixture):
    def test_mcp_entry_written_beside_the_logins_own(self) -> None:
        self.add_websearch_locale()
        out = self.run_install()
        self.assertIn("mcpServers.websearch-locale", out)
        d = load(self.claude_json)
        e = d["mcpServers"]["websearch-locale"]
        self.assertTrue(e["command"].endswith("/bin/fabric-websearch-locale"), d)
        self.assertEqual(e["args"], [])
        self.assertTrue(e["env"]["WEBSEARCH_LOCALE_FILE"].endswith("/locale.json"), d)
        self.assertEqual(d["theme"], "dark")
        self.assertIn("mine", d["mcpServers"])

    def test_mcp_entry_second_run_leaves_it(self) -> None:
        self.add_websearch_locale()
        self.run_install()
        out = self.run_install()
        self.assertIn(f"=  {self.claude_json} mcpServers.websearch-locale", out)

    def test_websearch_denied_and_marked(self) -> None:
        self.add_websearch_locale()
        self.run_install()
        self.assertEqual(load(self.settings)["permissions"]["deny"], ["WebSearch", "WebSearch(agent-fabric)"])

    def test_fabric_memory_entry_by_bare_command_name_every_role(self) -> None:
        self.add_websearch_locale()
        self.run_install()
        self.bind("backend-dev")
        self.run_install()
        d = load(self.claude_json)
        self.assertEqual(d["mcpServers"]["fabric-memory"],
                         {"type": "stdio", "command": "fabric-memory-mcp", "args": [], "env": {}})
        self.assertIn("mine", d["mcpServers"])

    def test_fabric_memory_second_run_leaves_it(self) -> None:
        self.bind("backend-dev")
        self.run_install()
        out = self.run_install()
        self.assertIn(f"=  {self.claude_json} mcpServers.fabric-memory", out)


class RoleChange(Fixture):
    def installed_as_worker(self) -> None:
        self.add_websearch_locale()
        self.run_install()
        self.assertTrue(os.path.isfile(self.dest))
        self.bind("backend-dev")

    def test_role_change_dry_run_names_removal_and_touches_nothing(self) -> None:
        self.installed_as_worker()
        out = self.run_install("--dry-run")
        self.assertIn("would remove: role is backend-dev", out)
        self.assertTrue(os.path.isfile(self.dest))

    def test_role_change_removes_worker_and_names_the_role(self) -> None:
        self.installed_as_worker()
        out = self.run_install()
        self.assertFalse(os.path.exists(self.dest), out)
        self.assertIn("removed: role is backend-dev", out)

    def test_second_removal_is_silent(self) -> None:
        self.installed_as_worker()
        self.run_install()
        self.assertNotIn("locale-worker", self.run_install())

    def test_role_change_removes_mcp_entry_keeps_the_logins_own(self) -> None:
        self.installed_as_worker()
        self.run_install()
        d = load(self.claude_json)
        self.assertNotIn("websearch-locale", d["mcpServers"], d)
        self.assertIn("mine", d["mcpServers"])

    def test_role_change_removes_the_websearch_deny(self) -> None:
        self.installed_as_worker()
        self.run_install()
        self.assertEqual(load(self.settings)["permissions"]["deny"], [])

    def test_own_websearch_deny_is_left_alone(self) -> None:
        self.installed_as_worker()
        self.run_install()
        write(self.settings, json.dumps({"permissions": {"deny": ["WebSearch"]}, "theme": "dark"}))
        self.run_install()
        d = load(self.settings)
        self.assertEqual(d["permissions"]["deny"], ["WebSearch"])
        self.assertEqual(d["theme"], "dark")

    def test_locale_without_worker_is_removed_naming_the_locale(self) -> None:
        self.run_install()
        self.assertTrue(os.path.isfile(self.dest))
        shutil.rmtree(os.path.dirname(self.worker))
        other = os.path.join(self.fabric, "identities", "roles", "language-culture", "locale", f"{SUFFIX}-other")
        write(os.path.join(other, "worker.md"), WORKER_BODY)
        out = self.run_install()
        self.assertFalse(os.path.exists(self.dest), out)
        self.assertIn(f"no worker authored for locale {SUFFIX}", out)

    def test_no_record_is_english_whatever_the_login(self) -> None:
        # Bootstrap passes no --locale: with no launch record the locale is en, even for a login named for qq.
        # Kills: choosing the locale from the login's suffix.
        self.record_locale(None)
        out = self.run_install()
        self.assertFalse(os.path.exists(self.dest), out)

    def test_locale_option_wins_over_the_record(self) -> None:
        # The launcher's --locale is this launch's answer; the record is the last one's. Kills: reading the record first.
        self.record_locale("en")
        out = self.run_install(f"--locale={SUFFIX}")
        self.assertTrue(os.path.isfile(self.dest), out)

    def test_hand_written_worker_without_marker_survives(self) -> None:
        self.bind("backend-dev")
        write(self.dest, "---\nname: locale-worker\ndescription: my own\n---\nmine\n")
        self.run_install()
        self.assertIn("my own", read(self.dest))


class ClassFiles(Fixture):
    def efforts(self) -> dict[str, str]:
        p = subprocess.run([PYTHON, os.path.join(self.fabric, "tools", "fabric", "routing.py"), "efforts", "--me",
                            "--provider", "anthropic"], capture_output=True, text=True, env=self.env(), timeout=TIMEOUT_S,
                           check=True)
        return dict(line.split()[:2] for line in p.stdout.splitlines() if line.strip())

    def test_class_files_carry_the_effort_routing_resolves(self) -> None:
        self.bind("backend-dev")
        self.run_install()
        want = self.efforts()
        self.assertEqual(sorted(want), sorted(CLASSES))
        for k in CLASSES:
            m = re.search(r"^effort: (.*)$", read(os.path.join(self.agents, k + ".md")), re.M)
            if want[k] == "-":
                self.assertIsNone(m, f"{k}: effort where none is expressible")
            else:
                self.assertEqual(m and m.group(1), want[k], k)
        # Positive control: at least one class expresses an effort, or the
        # loop above proved only the "-" branch.
        self.assertTrue(any(v != "-" for v in want.values()), want)

    def test_committed_sources_carry_no_effort(self) -> None:
        src = read(os.path.join(HERE, "runtime", "claude-code", "agents", "code-high.md"))
        self.assertIsNone(re.search(r"^effort:", src, re.M), "the installer is the only writer")

    def test_second_run_rewrites_nothing(self) -> None:
        self.bind("backend-dev")
        self.run_install()
        self.assertIn("0 written, 6 already current", self.run_install())

    def test_backup_taken_once_not_on_every_run(self) -> None:
        self.bind("backend-dev")
        a = self.agents
        write(os.path.join(a, "code-high.md"), "---\nname: code-high\nmodel: sonnet\n---\n\nthe user own file.\n")
        self.run_install()
        backup = os.path.join(a, "code-high.md.before-agent-fabric")
        self.assertIn("the user own file", read(backup))
        write(os.path.join(a, "code-high.md"), "---\nname: code-high\nmodel: opus\neffort: max\n---\n\nfabric.\n")
        self.run_install()
        self.assertIn("the user own file", read(backup), "the backup was clobbered by a second run")

    def test_fabrics_own_previous_file_is_not_backed_up_when_routing_rewrites_it(self) -> None:
        # The hand-written "fabric." file above is not the fabric's record, so it is rightly kept
        # too; this is the real case: the file the installer itself wrote, rewritten after the
        # routed effort changes, must not become a second backup. Kills: dropping the marker and
        # record test from fabric_writes.keep_person_version.
        self.bind("backend-dev")
        dest = os.path.join(self.agents, "code-high.md")
        write(dest, "---\nname: code-high\nmodel: sonnet\n---\n\nthe user own file.\n")
        self.run_install()
        before = read(dest)
        level = "low" if "effort: low" not in before else "medium"
        write(os.path.join(self.state, "agents", LOGIN, "model-profile.local.json"),
              json.dumps({"providers": {"anthropic": {"effort": {"code-high": level}}}}) + "\n")
        out = self.run_install()
        self.assertIn(f"effort: {level}", read(dest), out)       # positive control: it was rewritten
        self.assertEqual(sorted(n for n in os.listdir(self.agents) if n.startswith("code-high.md.before-agent-fabric")),
                         ["code-high.md.before-agent-fabric"], out)


class RoutingFailure(Fixture):
    def test_routing_failure_refuses_the_whole_run(self) -> None:
        self.bind("backend-dev")
        write(os.path.join(self.state, "agents", LOGIN, "model-profile.local.json"),
              '{"providers":{"anthropic":{"effort":{"code-high":"not-a-level"}}}}\n')
        p = self.run_raw()
        out = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, out)
        self.assertIn("refusing to write agent files with no routing", out)
        self.assertFalse(os.path.exists(os.path.join(self.agents, "code-high.md")), "wrote with an empty routing map")

    def test_efforts_failure_alone_is_caught_and_named(self) -> None:
        # EACH routing call is guarded, not just the first. Every data-shaped
        # break fails `pins` before `efforts` is reached, so the second guard
        # is proved by failing that ONE subcommand: a stub in front of the
        # fixture's routing.py (it opens with `from __future__`, so nothing can
        # be injected at its top) exits non-zero for `efforts` alone.
        self.bind("backend-dev")
        tools = os.path.join(self.fabric, "tools", "fabric")
        os.rename(os.path.join(tools, "routing.py"), os.path.join(tools, "routing.real.py"))
        write(os.path.join(tools, "routing.py"),
              "import os, runpy, sys\n"
              "if 'efforts' in sys.argv:\n    sys.exit(3)\n"
              "runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'routing.real.py'), run_name='__main__')\n")
        p = self.run_raw()
        out = p.stdout + p.stderr
        self.assertNotEqual(p.returncode, 0, out)
        self.assertIn("routing.py efforts failed", out)
        # Positive control: with the stub passing efforts through, the same run succeeds.
        write(os.path.join(tools, "routing.py"), read(os.path.join(tools, "routing.real.py")))
        self.assertEqual(self.run_raw().returncode, 0)


if __name__ == "__main__":
    unittest.main()
