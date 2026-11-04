#!/usr/bin/env python3
"""Tab completion of fabric-ctl's target and verb (tools/fabric/control/completion.bash), driven the way bash drives
it: COMP_WORDS and COMP_CWORD set, the function called, COMPREPLY read back. The registry is a fixture and
`fabric-ctl` a stub that prints the `--verbs` output (one word per line) and records its argv, so a tab is shown to
reach nothing else.

Each case fails when its guard is removed: a login placed on any host is proposed; `all`, `keygen` and `help` are;
the second word is the verbs; the third is that verb's own words plus --json/--timeout/--help; keygen and help take no
verb; a registry that is absent, unreadable or not JSON still completes `all` and the verbs and prints nothing on
stderr; a tab calls the tool for `--verbs` only."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

COMPLETION = os.path.join(HERE, "tools", "fabric", "control", "completion.bash")
STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_LOG"
[ "$1" = --verbs ] || exit 64
[ -z "$STUB_FAIL" ] || { echo "fabric-ctl: stub failure" >&2; exit 1; }
case "$2" in
  "") printf 'status\\nkeys\\nupgrade\\n' ;;
  keys) printf -- '--json\\n--refresh\\nhealth\\n' ;;
  *) exit 1 ;;
esac
"""


class Completion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ctlcomp-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = os.path.join(self.tmp, "fabric")
        self.log = os.path.join(self.tmp, "calls")
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        with open(os.path.join(bindir, "fabric-ctl"), "w", encoding="utf-8") as fh:
            fh.write(STUB)
        os.chmod(os.path.join(bindir, "fabric-ctl"), 0o755)
        self.env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": self.tmp, "AGENT_FABRIC_ROOT": self.root,
                    "STUB_LOG": self.log, "LC_ALL": "C"}
        self.registry('{"placement": {"alpha-01": "host-a", "beta-01": "host-a", "gamma-01": "host-b"}}')

    def registry(self, text: str | None) -> None:
        path = os.path.join(self.root, "runtime", "hosts", "registry.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if text is not None:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

    def complete(self, *words: str) -> tuple[list[str], str]:
        """COMPREPLY and stderr; the cursor is on the last word, as bash puts it."""
        script = ('source "$1"; shift; COMP_WORDS=("$@"); COMP_CWORD=$(( $# - 1 )); _fabric_ctl; '
                  'printf "%s\\n" "${COMPREPLY[@]}"')
        r = subprocess.run(["bash", "-c", script, "_", COMPLETION, *words], env=self.env, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.split(), r.stderr

    def calls(self) -> list[str]:
        try:
            with open(self.log, encoding="utf-8") as fh:
                return fh.read().splitlines()
        except FileNotFoundError:
            return []

    def test_the_first_word_is_all_keygen_help_and_every_login_on_any_host(self):
        words, err = self.complete("fabric-ctl", "")
        self.assertEqual(sorted(words), ["all", "alpha-01", "beta-01", "gamma-01", "help", "keygen"])
        self.assertEqual(err, "")

    def test_the_first_word_narrows_on_the_prefix(self):
        self.assertEqual(self.complete("fabric-ctl", "be")[0], ["beta-01"])
        self.assertEqual(self.complete("fabric-ctl", "k")[0], ["keygen"])

    def test_the_second_word_after_a_login_or_all_is_the_verbs(self):
        for target in ("alpha-01", "all"):
            self.assertEqual(self.complete("fabric-ctl", target, "")[0], ["status", "keys", "upgrade"], target)
        self.assertEqual(self.complete("fabric-ctl", "all", "s")[0], ["status"])

    def test_keygen_and_help_take_no_verb(self):
        for first in ("keygen", "help"):
            self.assertEqual(self.complete("fabric-ctl", first, "")[0], [], first)
        self.assertEqual(self.calls(), [])

    def test_the_third_word_is_the_verbs_own_words_and_the_common_options(self):
        words, _ = self.complete("fabric-ctl", "all", "keys", "")
        self.assertEqual(sorted(words), ["--help", "--json", "--refresh", "--timeout", "health"], "each word once")
        self.assertEqual(self.complete("fabric-ctl", "all", "keys", "--t")[0], ["--timeout"])
        self.assertEqual(self.complete("fabric-ctl", "all", "keys", "he")[0], ["health"])

    def test_a_verb_the_tool_does_not_know_still_offers_the_common_options(self):
        words, err = self.complete("fabric-ctl", "all", "nonesuch", "--")
        self.assertEqual(sorted(words), ["--help", "--json", "--timeout"])
        self.assertEqual(err, "")

    def test_a_tool_that_fails_prints_nothing_on_the_terminal_and_the_options_remain(self):
        self.env["STUB_FAIL"] = "1"
        words, err = self.complete("fabric-ctl", "all", "")
        self.assertEqual((words, err), ([], ""))
        words, err = self.complete("fabric-ctl", "all", "keys", "")
        self.assertEqual((sorted(words), err), (["--help", "--json", "--timeout"], ""))

    def test_a_registry_that_cannot_be_read_leaves_all_keygen_help_and_the_verbs(self):
        for text in (None, "{not json", '{"placement": []}', '{"nothing": 1}'):
            with self.subTest(registry=text):
                self.registry(None)
                if text is not None:
                    self.registry(text)
                else:
                    shutil.rmtree(self.root)
                words, err = self.complete("fabric-ctl", "")
                self.assertEqual(sorted(words), ["all", "help", "keygen"])
                self.assertEqual(err, "")
                self.assertEqual(self.complete("fabric-ctl", "all", "")[0], ["status", "keys", "upgrade"])

    def test_a_registry_without_read_permission_does_not_print_an_error(self):
        if os.geteuid() == 0:
            self.skipTest("root reads any file")
        path = os.path.join(self.root, "runtime", "hosts", "registry.json")
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o600)
        words, err = self.complete("fabric-ctl", "")
        self.assertEqual(sorted(words), ["all", "help", "keygen"])
        self.assertEqual(err, "")

    def test_a_tab_calls_the_tool_for_verbs_only(self):
        self.complete("fabric-ctl", "")
        self.complete("fabric-ctl", "all", "")
        self.complete("fabric-ctl", "all", "keys", "")
        self.assertEqual(self.calls(), ["--verbs", "--verbs keys"])


if __name__ == "__main__":
    unittest.main()
