#!/usr/bin/env python3
"""runtime/claude-code/hooks/model-switch-guard.sh (Claude Code PreModelSwitch hook) — Wave 9 batch 5.

The oracle is test_model-switch-guard.sh, ported case for case; the cases it missed are marked NEW. The hook is
driven through ONE constant, ENTRY, the command the harness runs (`bash "<path>"`, the payload on stdin), so this file runs unchanged against the bash and against the Python port behind the same path.
$MODEL_SWITCH_GUARD_HOOK aims it at another file (the module that replaces the script): that file is then run as a program,
by its shebang, from its absolute path.

Contract held still: in a broker session (AGENT_FABRIC_LAUNCH_PROFILE set and non-empty) a bare /model to a family
that needs a shim is denied, naming the composite and the profile; a composite, a family with no shim, a bare
preset and a vanilla session pass in silence; a guard that cannot consult routing asks; exit 0 always.
Cases of the bash test: vanilla (2), bare shimmed denied, composite allowed, request spelled as the composite,
no-shim family, bare preset, the denial's three facts (composite, profile, event), routing.py missing asks, jq
missing asks, malformed payloads never exit 2 (4).
NEW: exit status 0 and one JSON line on every decision; an empty profile is vanilla; a request spelled bare is
ignored; a composite passes with routing unreachable; routing that fails or answers nothing (the bash seam: a
routing.py run as a program, a port that calls routing in-process replaces these three with its own fixture).
The shimmed family is read from this checkout's routing/shims.json, as the bash test did.

Mutations each case set fails on: the profile test removed (vanilla cases); `*@preset/*` test removed (composite
cases); `requested` judged when not a composite (a request spelled bare); ask replaced by allow when routing.py
is missing or fails; deny's composite built from `$target` instead of `${target%%@*}$shim`; exit 2 on bad JSON.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

FABRIC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(FABRIC, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
HOOK = os.path.abspath(os.environ.get("MODEL_SWITCH_GUARD_HOOK") or os.path.join(FABRIC, "runtime", "claude-code", "hooks", "model-switch-guard.sh"))
if not os.path.isfile(HOOK):
    sys.exit(f"test: not found: {HOOK}")
# The tracked hook is what the harness runs as `bash <path>`; an override is run as a program (its shebang), the way
# tab-title's oracle runs $TAB_TITLE_HOOK, so it can name the module that replaces the script.
ENTRY = [HOOK] if os.environ.get("MODEL_SWITCH_GUARD_HOOK") else ["bash", HOOK]
SAFE_PATH = "/usr/bin:/bin"
UNSHIMMED = "example/no-shim-model"


def shimmed() -> tuple[str, str]:
    """A shimmed model id and its shim, read from routing/shims.json so the test follows the policy and names no vendor."""
    with open(os.path.join(FABRIC, "routing", "shims.json"), encoding="utf-8") as fh:
        first = json.load(fh)["shims"][0]
    family = first["family"]
    family = family[:-1] + "5.3" if family.endswith("*") else family
    return family.replace("*", "x"), first["shim"]


SHIMMED, SHIM = shimmed()


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="msg-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        r = subprocess.run([sys.executable, os.path.join(FABRIC, "tools", "fabric", "routing.py"), "--fabric", FABRIC, "shim", UNSHIMMED],
                           capture_output=True, text=True, env={"PATH": SAFE_PATH}, timeout=60, check=False)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, ""), f"fixture {UNSHIMMED} unexpectedly has a shim")

    def env(self, profile="broker-test", root=FABRIC, path=SAFE_PATH):
        e = {"PATH": path, "HOME": self.tmp, "TMPDIR": self.tmp, "LANG": "C.UTF-8"}
        if profile is not None:
            e["AGENT_FABRIC_LAUNCH_PROFILE"] = profile
        if root is not None:
            e["AGENT_FABRIC_ROOT"] = root
        return e

    def run_hook(self, payload, **kw):
        data = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run(ENTRY, input=data, capture_output=True, text=True, env=self.env(**kw), cwd=self.tmp, timeout=60, check=False)

    def decision(self, to, requested=None, **kw) -> str:
        payload = {"to_model": to, **({"requested_model": requested} if requested else {})}
        r = self.run_hook(payload, **kw)
        self.assertEqual(r.returncode, 0, f"exit 0 always: {r.stderr!r}")
        if r.stdout == "":
            return "allow"
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 1, "one JSON line")
        return json.loads(lines[0]).get("hookSpecificOutput", {}).get("permissionDecision", "malformed")

    def test_a_vanilla_session_is_never_touched(self):
        self.assertEqual(self.decision(SHIMMED, profile=None), "allow")
        self.assertEqual(self.decision(UNSHIMMED, profile=None), "allow")
        self.assertEqual(self.run_hook({"to_model": SHIMMED}, profile=None).stdout, "")

    def test_an_empty_launch_profile_is_a_vanilla_session(self):                       # NEW
        self.assertEqual(self.decision(SHIMMED, profile=""), "allow")

    def test_in_a_broker_session_a_bare_shimmed_id_is_refused_and_the_rest_passes(self):
        self.assertEqual(self.decision(SHIMMED), "deny")
        self.assertEqual(self.decision(SHIMMED + SHIM), "allow", "the composite of the same model")
        self.assertEqual(self.decision(SHIMMED, SHIMMED + SHIM), "allow", "a request spelled as the composite, to_model bare")
        self.assertEqual(self.decision(UNSHIMMED), "allow", "a family with no shim rides bare")
        self.assertEqual(self.decision("@preset/reviewer"), "allow", "a bare preset already is one")

    def test_only_a_composite_request_is_a_second_witness(self):                          # NEW
        self.assertEqual(self.decision(UNSHIMMED, SHIMMED), "allow", "a bare request is not judged: to_model is")
        self.assertEqual(self.decision(SHIMMED, UNSHIMMED), "deny", "a bare request does not rescue a bare shimmed to_model")

    def test_a_composite_passes_without_consulting_routing(self):                          # NEW
        for root in ("/nonexistent", self.tmp):
            with self.subTest(root=root):
                self.assertEqual(self.decision(SHIMMED + SHIM, root=root), "allow")

    def test_the_denial_names_the_composite_the_profile_and_the_event(self):
        r = self.run_hook({"to_model": SHIMMED}, profile="p1")
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreModelSwitch", "deny"))
        self.assertIn(f"'{SHIMMED}{SHIM}'", out["permissionDecisionReason"])
        self.assertIn("profile p1", out["permissionDecisionReason"])

    def test_the_composite_in_a_denial_is_the_model_without_any_preset_plus_the_shim(self):  # NEW
        r = self.run_hook({"to_model": SHIMMED, "requested_model": "ignored"}, profile="p1")
        self.assertIn(f"Switch to '{SHIMMED}{SHIM}' instead", json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_when_routing_cannot_be_consulted_it_asks_never_allows(self):
        r = self.run_hook({"to_model": SHIMMED}, profile="p1", root="/nonexistent")
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual((r.returncode, out["permissionDecision"], out["hookEventName"]), (0, "ask", "PreModelSwitch"))

    def test_when_jq_is_unavailable_it_asks(self):
        # A PATH with the tools the guard may use and no jq: the harness command is `bash <path>`, so bash must be there.
        tools = os.path.join(self.tmp, "tools")
        os.makedirs(tools)
        for name in ("bash", "env", "python3", "cat", "tr", "sed", "grep", "dirname"):
            found = shutil.which(name, path=SAFE_PATH)
            if found:
                os.symlink(found, os.path.join(tools, name))
        r = self.run_hook({"to_model": SHIMMED}, profile="p1", path=tools)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_malformed_input_never_exits_2(self):
        for payload in ("{}", "not json", "", '{"to_model":""}'):
            with self.subTest(payload=payload):
                r = self.run_hook(payload, profile="p1")
                self.assertNotEqual(r.returncode, 2)

    def seam(self, body: str) -> str:
        """A fabric root whose tools/fabric/routing.py is `body`: the bash seam (routing run as a program)."""
        root = os.path.join(self.tmp, "seam-root")
        os.makedirs(os.path.join(root, "tools", "fabric"), exist_ok=True)
        with open(os.path.join(root, "tools", "fabric", "routing.py"), "w", encoding="utf-8") as fh:
            fh.write(body)
        return root

    def test_routing_that_fails_asks_and_routing_that_answers_nothing_allows(self):          # NEW (bash seam)
        failing = self.seam("import sys\nsys.exit(3)\n")
        r = self.run_hook({"to_model": SHIMMED}, profile="p1", root=failing)
        self.assertEqual((r.returncode, json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]), (0, "ask"))
        silent = self.seam("")
        self.assertEqual(self.run_hook({"to_model": SHIMMED}, profile="p1", root=silent).stdout, "")

    def test_the_shim_routing_names_is_the_shim_the_denial_names(self):                         # NEW (bash seam)
        root = self.seam("print('@preset/fixture-shim')\n")
        r = self.run_hook({"to_model": "acme/model-1"}, profile="p1", root=root)
        reason = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("'acme/model-1@preset/fixture-shim'", reason)
        r = self.run_hook({"to_model": "acme/model-1@v2"}, profile="p1", root=root)
        reason = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("'acme/model-1@preset/fixture-shim'", reason, "a suffix the resolved id carries is replaced, not kept")


if __name__ == "__main__":
    unittest.main()
