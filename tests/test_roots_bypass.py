#!/usr/bin/env python3
"""tools/fabric/roots_bypass.py: the engine finds a tree and reads instance data only through roots.py (agent-fabric
ADR-045 §5 rule 1, j222). Stdlib only; runnable as `python3 tests/test_roots_bypass.py`. **Each case names the mutation it kills**:

  env_read_is_found          <- the get/pop/getenv, subscript or `in` branch dropped, or a write counted as a read
  fallback_is_found          <- the projects/agent-fabric join pair dropped, or the f-string rule widened to messages
  instance_path_is_found     <- the literal or the module-constant branch dropped, or "memory" alone counted as instance data
  judged_set                 <- roots.py, tests or non-Python bin shims judged; a Python command in bin/ skipped
  entries_admit_or_say       <- an entry not honoured, one that admits nothing, or one for an untracked file left silent
  unreadable_policy          <- a policy that is not JSON read as empty
  the_tree_is_clean          <- a bypass left in the engine without an entry, or an entry the tree no longer needs
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import warnings

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import roots_bypass as rb  # noqa: E402

MOD = "tools/fabric/x.py"


def lines(src: str, rel: str = MOD) -> list[int]:
    return [int(f.split(":")[1]) for f in rb.scan(rel, src)]


class Scan(unittest.TestCase):
    def test_env_read_is_found(self):
        src = ('import os\n'
               'a = os.environ.get("AGENT_FABRIC_ROOT")\n'
               'b = os.getenv("AGENT_FABRIC_OPERATOR")\n'
               'c = os.environ["AGENT_FABRIC_ROOT"]\n'
               'd = "AGENT_FABRIC_ROOT" in os.environ\n'
               'e = env.pop("AGENT_FABRIC_ROOT", None)\n')
        self.assertEqual(lines(src), [2, 3, 4, 5, 6])
        # Positive control's negative: exporting the variable, or naming it, reads nothing.
        clean = ('import os\n'
                 'os.environ["AGENT_FABRIC_ROOT"] = root\n'
                 'child = {**os.environ, "AGENT_FABRIC_ROOT": root}\n'
                 'KEEP = ("PATH", "AGENT_FABRIC_ROOT")\n'
                 'x = os.environ.get("HOME")\n')
        self.assertEqual(lines(clean), [])

    def test_fallback_is_found(self):
        src = ('import os\nfrom pathlib import Path\n'
               'a = os.path.join(home, "projects", "agent-fabric")\n'
               'b = Path(home, "projects", "agent-fabric", "bin")\n'
               'c = f"{home}/projects/agent-fabric"\n')
        self.assertEqual(lines(src), [3, 4, 5])
        clean = ('a = os.path.join(home, "projects", "gzapp")\n'
                 'b = f"as {login}: ~/projects/agent-fabric/bin/fabric-secrets sync"\n'
                 'c = os.path.join(home, "projects")\n')
        self.assertEqual(lines(clean), [])

    def test_instance_path_is_found(self):
        src = ('import os\n'
               'POLICY = "policies/x.json"\n'
               'OTHER = "policies/x.json"\n'
               'a = os.path.join(root, POLICY)\n'
               'b = os.path.join(root, "identities/roles/catalog.json")\n'
               'c = os.path.join(root, "memory/domains")\n')
        self.assertEqual(lines(src), [4, 5, 6])
        clean = ('import os\nPOLICY = "policies/x.json"\n'
                 'a = os.path.join(root, "memory")\n'                 # the harness's own memory directory
                 'b = os.path.join(root, "tools", "fabric")\n'
                 'c = f"{POLICY} is wrong"\n'
                 'd = os.path.join(POLICY)\n')                        # a lone argument names no root
        self.assertEqual(lines(clean), [])

    def test_a_modules_own_invalid_escape_does_not_hide_a_bypass(self):
        src = 'import os\nx = "\\ "\ny = os.environ.get("AGENT_FABRIC_ROOT")\n'
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with self.assertRaises(SyntaxError):
                compile(src, "x", "exec")      # control: this fixture is a SyntaxError under -W error
            self.assertEqual(lines(src), [3])

    def test_judged_set(self):
        bad = 'import os\nx = os.environ.get("AGENT_FABRIC_ROOT")\n'
        for rel in ("tools/fabric/roots.py", "tests/test_x.py", "tools/fabric/tests/t.py", "docs/x.py"):
            self.assertEqual(rb.scan(rel, bad), [], rel)
        for rel in ("tools/fabric/a.py", "runtime/a.py", "bin/fabric-x"):
            self.assertEqual(len(rb.scan(rel, bad)), 1, rel)
        self.assertTrue(rb.is_python_command("bin/fabric-x", b"#!/usr/bin/env python3\n"))
        self.assertTrue(rb.is_python_command("bin/fabric-x", b"#!/usr/local/bin/fabric-python\n"))
        self.assertFalse(rb.is_python_command("bin/fabric-x", b"#!/usr/bin/env bash\n"))
        self.assertEqual(rb.scan(MOD, "def ("), [])


def planted(policy, files: dict[str, str]) -> str:
    root = tempfile.mkdtemp(prefix="roots-bypass-")
    for rel, text in {**files, **({rb.POLICY: policy if isinstance(policy, str) else json.dumps(policy)} if policy is not None else {})}.items():
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
            fh.write(text)
    subprocess.run(["git", "-C", root, "init", "-q"], check=True, stdin=subprocess.DEVNULL)
    subprocess.run(["git", "-C", root, "add", "-A"], check=True, stdin=subprocess.DEVNULL)
    return root


def judged(root: str) -> list[str]:
    return rb.tree_findings(root, rb.tracked_files(root))


BYPASS = 'import os\nx = os.environ.get("AGENT_FABRIC_ROOT")\n'


class Tree(unittest.TestCase):
    def test_a_planted_bypass_is_red_and_an_entry_makes_it_green(self):
        files = {MOD: BYPASS, "tools/fabric/clean.py": "x = 1\n", "bin/fabric-sh": "#!/usr/bin/env bash\nexport AGENT_FABRIC_ROOT=x\n"}
        out = judged(planted(None, files))
        self.assertEqual(len(out), 1, out)
        self.assertIn("tools/fabric/x.py:2: a read of AGENT_FABRIC_ROOT", out[0])
        self.assertEqual(judged(planted({"modules": {MOD: "a stub"}}, files)), [])

    def test_the_script_exits_one_on_a_bypass_and_zero_without(self):
        script = os.path.join(HERE, "tools", "fabric", "roots_bypass.py")
        red = subprocess.run([sys.executable, script, planted(None, {MOD: BYPASS})], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        green = subprocess.run([sys.executable, script, planted(None, {MOD: "x = 1\n"})], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual((red.returncode, green.returncode, green.stdout), (1, 0, ""), (red, green))
        self.assertIn("x.py:2", red.stdout)

    def test_entries_admit_or_say(self):
        files = {MOD: BYPASS, "tools/fabric/clean.py": "x = 1\n", "tools/fabric/roots.py": BYPASS}
        out = judged(planted({"modules": {MOD: "why", "tools/fabric/clean.py": "why", "tools/fabric/roots.py": "why",
                                          "tools/fabric/gone.py": "why", "tools/fabric/blank.py": " "}}, files))
        self.assertEqual(sum("clean.py admits nothing" in f for f in out), 1, out)
        self.assertEqual(sum("roots.py admits nothing" in f for f in out), 1, out)
        self.assertEqual(sum("gone.py is listed but is not a tracked file" in f for f in out), 1, out)
        self.assertFalse(any(f.startswith("tools/fabric/x.py") for f in out), out)
        self.assertFalse(any("blank.py" in f and "admits" in f for f in out), out)   # an empty reason admits nothing and is not an entry

    def test_unreadable_policy(self):
        out = judged(planted("{not json", {MOD: BYPASS}))
        self.assertEqual(len(out), 1, out)
        self.assertIn("cannot be read as JSON", out[0])

    def test_the_tree_is_clean(self):
        self.assertEqual(judged(HERE), [])


if __name__ == "__main__":
    unittest.main()
