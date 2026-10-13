#!/usr/bin/env python3
"""policies/check_agent_fabric_dir_authority.sh as CI and tests/run.sh invoke it: the tripwire that refuses a branch whose commits
change `.agent-fabric/` (or, in agent-fabric itself, anything) without the owning role's Fabric-Role trailer (Wave 9 batch 3;
ADR-040 rule 5). The entry point is ONE constant, ENTRY (override with DIR_AUTHORITY_ENTRY), run as a command from the scratch
repository, so this file runs unchanged against the bash forwarder today and against its Python port later.

policies/test_check_agent_fabric_dir_authority.sh, case for case (the number is its assertion order; each is a method here):
  01 a code change passes, trailer or not                         02 no trailer: refused              03 the refusal names the missing trailer
  04 ... and lists the commit with what it declared               05 ... and says the login is not the question
  06 ... and gives the slice correction (merge_target), not a raise
  07 a trailer naming another role: refused                       08 Fabric-Role: fabric-coordinator: allowed
  09 the role value is exact (case matters)                       10 an undeclared commit in the middle is caught
  11 exactly the offending commit is listed
  12 agent-fabric itself: a code change with no trailer is refused   13 ... and the refusal says the whole repository is guarded
  14 a code change declaring the owning role passes (the role name is read from authority.json)
  15 fabric-coordinator is refused where the owning role is corpus-keeper
  16 locale carve-out: a locale commit declaring the role it translates is admitted, and said     17 declaring another role: refused
  18 a locale file beside a code change: refused                  19 the English charter is not the locale: refused
  20 Dependabot, workflows only: admitted, and said               21 Dependabot beyond .github/workflows/: refused
  22 a workflow-only commit by anyone else without the trailer: refused
  23 an unresolvable base: not enforced, not a failure (exit 0)
The twin tests/test_agent_fabric_dir_authority.py runs the module in-process: it pins the "[Fabric-Role: none]" listing, the two carve-out
lines, the owner role read from the base's authority.json and the exit-2 line, but not the refusal's other wording (03, 05, 06, 13), the case
exactness of the role value (09) or the run through the entry (the forwarder, its Python and its argv); those are here.

Streams: the refusal and the carve-out notes are asserted where they are written - the FAIL block on stderr with stdout empty, the carve-out
sentences on stdout (cases 02-06, 16, 20). Cases the bash test does not carry: in agent-fabric itself an undeclared commit below a declared tip is still refused (the bash
test's "middle commit" case runs in a managed project only); the entry run outside a git repository is exit 2 with one line; a missing pinned Python is
exit 127 naming the path on stderr.

Mutations each case fails on (one per behaviour, on the module or the forwarder): comparing the trailer role case-insensitively (09);
reading the owner role from a constant instead of authority.json (14, 15); admitting any author's workflow-only commit (22);
dropping the "irrelevant" sentence from the refusal (05); examining only the tip commit (10; and, for agent-fabric itself, the extra case); exiting 1 on an unresolvable base (23).

The environment is built from scratch: PATH, HOME, LANG, git's identity, AGENT_FABRIC_ROOT=/nonexistent (the bash test's own: no
sibling fabric's authority.json is read), AGENT_FABRIC_CHARTER_BASE=base-ref and the documented test hook AGENT_FABRIC_PYTHON; no
GITHUB_*, CLAUDE_* or inherited git variable."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()      # the entry is handed a tree (AGENT_FABRIC_ROOT): the runner's operator must not be the one it finds
ENTRY = os.environ.get("DIR_AUTHORITY_ENTRY") or os.path.join(ROOT, "policies", "check_agent_fabric_dir_authority.sh")
DECLARED = "drain\n\nFabric-Role: fabric-coordinator"
DEPENDABOT = ("-c", "user.name=dependabot[bot]", "-c", "user.email=49699333+dependabot[bot]@users.noreply.github.com")
# PYTHONDONTWRITEBYTECODE: the guard imports the real tools/fabric modules, and Python would write __pycache__ into the checkout
GIT_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def authority_json(role: str) -> str:
    return '{"role_definitions":{"role":"%s","holders":[]}}\n' % role


class Entry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dir-authority-entry-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = ""
        self.n = 0

    def git(self, *args, env=None):
        return subprocess.run(["git", "-C", self.repo, *args], check=True, capture_output=True, text=True, timeout=60,
                              env={**GIT_ENV, **(env or {})}).stdout

    def new_repo(self, files=None, authority=None):
        """A managed-project repo with .agent-fabric/memory/<role>/ and a slice, base-ref at its first commit."""
        self.n += 1
        self.repo = os.path.join(self.tmp, f"r{self.n}")
        for rel, text in {".agent-fabric/memory/backend-dev/workflow.md": "slice\n", "src/a.txt": "code\n", **(files or {})}.items():
            self.write(rel, text)
        if authority:
            self.write("policies/authority.json", authority_json(authority))
        self.git("init", "-q")
        self.git("config", "user.email", "t@e")
        self.git("config", "user.name", "t")
        self.git("config", "commit.gpgsign", "false")      # the account's signing is not what this suite tests
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.git("branch", "-q", "base-ref")
        self.git("branch", "-q", "-M", "sandbox-head")

    def write(self, rel, text, append=False):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a" if append else "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit_change(self, path, message=None, *git_c):
        self.n += 1
        self.write(path, f"changed {self.n}\n", append=True)
        self.git("add", "-A")
        subprocess.run(["git", "-C", self.repo, *git_c, "commit", "-q", "-m", message or f"touch {path}"], check=True, capture_output=True,
                       timeout=60, env=GIT_ENV)

    def guard(self, **env_over):
        env = {**GIT_ENV, "HOME": self.tmp, "AGENT_FABRIC_ROOT": "/nonexistent", "AGENT_FABRIC_CHARTER_BASE": "base-ref",
               "AGENT_FABRIC_PYTHON": sys.executable, "GITHUB_BASE_REF": "", "GITHUB_HEAD_REF": ""}
        env.update(env_over)
        return subprocess.run([ENTRY], cwd=self.repo, capture_output=True, text=True, timeout=120, env=env)

    def rc(self):
        return self.guard().returncode

    def out(self):
        r = self.guard()
        return r.stdout + r.stderr


class Declaration(Entry):
    def test_01_a_code_change_passes_trailer_or_not(self):
        self.new_repo()
        self.commit_change("src/a.txt")
        self.assertEqual(self.rc(), 0)

    def test_02_to_06_an_undeclared_change_is_refused_and_the_refusal_says_what_to_do(self):
        self.new_repo()
        self.commit_change(".agent-fabric/memory/backend-dev/workflow.md")
        r = self.guard()
        self.assertEqual(r.returncode, 1)                                                          # 02
        self.assertEqual(r.stdout, "", "the refusal is on stderr alone")
        out = r.stderr
        self.assertIn("do not declare Fabric-Role: fabric-coordinator", out)                       # 03
        self.assertIn("[Fabric-Role: none]", out)                                                  # 04
        self.assertIn("irrelevant", out)                                                           # 05
        self.assertIn("merge_target", out)                                                         # 06
        self.assertNotIn("raise it", out.lower())

    def test_07_a_trailer_naming_another_role_is_refused(self):
        self.new_repo()
        self.commit_change(".agent-fabric/memory/backend-dev/workflow.md", "drain\n\nFabric-Role: backend-dev")
        self.assertEqual(self.rc(), 1)

    def test_08_fabric_role_fabric_coordinator_is_allowed(self):
        self.new_repo()
        self.commit_change(".agent-fabric/memory/backend-dev/workflow.md", DECLARED)
        r = self.guard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_09_the_role_value_is_exact_case_matters_in_a_role_id(self):
        self.new_repo()
        self.commit_change(".agent-fabric/memory/backend-dev/workflow.md", "drain\n\nfabric-role: Fabric-Coordinator")
        self.assertEqual(self.rc(), 1)

    def test_10_and_11_every_commit_is_examined_and_exactly_the_offender_is_listed(self):
        self.new_repo()
        self.commit_change(".agent-fabric/memory/backend-dev/workflow.md", DECLARED)
        self.commit_change(".agent-fabric/memory/backend-dev/workflow.md")
        self.commit_change("src/a.txt", DECLARED)
        r = self.guard()
        self.assertEqual(r.returncode, 1)                                                          # 10
        self.assertEqual((r.stdout + r.stderr).count("[Fabric-Role: none]"), 1)                    # 11


class InAgentFabricItself(Entry):
    def test_12_and_13_every_commit_must_declare_the_role_and_the_refusal_says_the_whole_repository_is_guarded(self):
        self.new_repo(authority="corpus-keeper")
        self.commit_change("src/a.txt")
        r = self.guard()
        self.assertEqual(r.returncode, 1)                                                          # 12
        self.assertIn("agent-fabric itself changed", r.stderr)                                     # 13
        self.assertEqual(r.stdout, "")

    def test_14_a_code_change_declaring_the_owning_role_passes_the_role_name_is_read_from_authority_json(self):
        self.new_repo(authority="corpus-keeper")
        self.commit_change("src/a.txt", "code\n\nFabric-Role: corpus-keeper")
        r = self.guard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_15_fabric_coordinator_is_refused_where_the_owning_role_is_corpus_keeper(self):
        self.new_repo(authority="corpus-keeper")
        self.commit_change("src/a.txt", "code\n\nFabric-Role: corpus-keeper")
        self.commit_change(".agent-fabric/memory/backend-dev/workflow.md", DECLARED)
        self.assertEqual(self.rc(), 1)


    def test_extra_in_agent_fabric_itself_an_undeclared_commit_below_a_declared_tip_is_still_refused(self):
        self.new_repo(authority="corpus-keeper")
        self.commit_change("src/a.txt")
        self.commit_change("src/a.txt", "code\n\nFabric-Role: corpus-keeper")
        r = self.guard()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual((r.stdout + r.stderr).count("[Fabric-Role: none]"), 1)


class LocaleCarveOut(Entry):
    def test_16_and_17_a_locale_commit_declaring_the_role_it_translates_is_admitted_and_said_another_role_is_refused(self):
        self.new_repo(authority="fabric-coordinator")
        self.commit_change("identities/roles/language-culture/locale/ge/harness.md", "ge harness\n\nFabric-Role: language-culture")
        r = self.guard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)                                     # 16
        self.assertIn("the locale carve-out", r.stdout)                                            # said on stdout
        self.assertEqual(r.stderr, "")
        self.commit_change("identities/roles/language-culture/locale/ge/team.md", "ge team\n\nFabric-Role: backend-dev")
        self.assertEqual(self.rc(), 1)                                                             # 17

    def test_18_a_locale_file_beside_a_code_change_is_refused(self):
        self.new_repo(authority="fabric-coordinator")
        self.write("identities/roles/language-culture/locale/ge/team.md", "x\n")
        self.write("src/a.txt", "y\n", append=True)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "locale and code\n\nFabric-Role: language-culture")
        self.assertEqual(self.rc(), 1)

    def test_19_the_english_charter_is_not_the_locale(self):
        self.new_repo(authority="fabric-coordinator")
        self.commit_change("identities/roles/language-culture/locale/ge/harness.md", "ge harness\n\nFabric-Role: language-culture")
        self.assertEqual(self.rc(), 0, "precondition: the locale commit alone is admitted")
        self.commit_change("identities/roles/language-culture/charter.md", "charter\n\nFabric-Role: language-culture")
        self.assertEqual(self.rc(), 1)


class Dependabot(Entry):
    def workflow_repo(self):
        self.new_repo(files={".github/workflows/ci.yml": "on: push\n"}, authority="fabric-coordinator")

    def test_20_dependabot_bumping_a_workflow_pin_is_admitted_and_said(self):
        self.workflow_repo()
        self.write(".github/workflows/ci.yml", "# bump\n", append=True)
        self.git("add", "-A")
        subprocess.run(["git", "-C", self.repo, *DEPENDABOT, "commit", "-qm", "Bump actions/checkout"], check=True, capture_output=True, env=GIT_ENV,
                       timeout=60)
        r = self.guard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("the action-pin carve-out", r.stdout)                                        # said on stdout
        self.assertEqual(r.stderr, "")

    def test_21_dependabot_touching_anything_beyond_the_workflows_is_refused(self):
        self.workflow_repo()
        self.write("src/a.txt", "y\n", append=True)
        self.write(".github/workflows/ci.yml", "# more\n", append=True)
        self.git("add", "-A")
        subprocess.run(["git", "-C", self.repo, *DEPENDABOT, "commit", "-qm", "Bump and more"], check=True, capture_output=True, env=GIT_ENV,
                       timeout=60)
        self.assertEqual(self.rc(), 1)

    def test_22_a_workflow_only_commit_by_anyone_else_without_the_trailer_is_refused(self):
        self.workflow_repo()
        self.write(".github/workflows/ci.yml", "# edit\n", append=True)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "a workflow edit, no trailer")
        self.assertEqual(self.rc(), 1)


class BaseAndEnvironment(Entry):
    def test_23_an_unresolvable_base_is_not_enforced_and_not_a_failure(self):
        self.new_repo()
        self.commit_change(".agent-fabric/memory/backend-dev/workflow.md")
        self.assertEqual(self.guard().returncode, 1, "precondition: with a base the same change is refused")
        r = self.guard(AGENT_FABRIC_CHARTER_BASE="no-such-ref")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_outside_a_git_repository_it_is_exit_2_and_one_line(self):
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain)
        r = subprocess.run([ENTRY], cwd=plain, capture_output=True, text=True, timeout=60,
                           env={**GIT_ENV, "HOME": self.tmp, "AGENT_FABRIC_PYTHON": sys.executable, "GIT_CEILING_DIRECTORIES": self.tmp})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stderr.strip(), "check_agent_fabric_dir_authority: not inside a git repository")

    def test_a_missing_pinned_python_is_exit_127_naming_the_path(self):
        self.new_repo()
        r = self.guard(AGENT_FABRIC_PYTHON="/nonexistent/fabric-python")
        self.assertEqual(r.returncode, 127, r.stdout + r.stderr)
        self.assertIn("the fleet's pinned Python is not installed at /nonexistent/fabric-python", r.stderr)


if __name__ == "__main__":
    unittest.main()
