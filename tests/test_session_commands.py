#!/usr/bin/env python3
"""Every fabric command a session is told to run runs without an approval.

The harness asks before any command carrying a shell expansion, whatever
the permission mode or rules (the owner, 2026-09-26: no approval for any
fabric script or executable). So a session-facing text names a command
from runtime/claude-code/commands.json, never `$AGENT_FABRIC_ROOT/...`;
every such command is a real executable; and a wrapper that runs another
command is never allowed outright.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = json.load(open(os.path.join(ROOT, "runtime", "claude-code", "commands.json"), encoding="utf-8"))
# An expansion used as a path: `$AGENT_FABRIC_ROOT/...` or `${AGENT_FABRIC_ROOT}/...`.
# A sentence that warns against it names the variable without a path after it.
EXPANDED_PATH = re.compile(r"\$\{?AGENT_FABRIC_ROOT\}?/|(?:\.\./)?agent-fabric/bin/fabric-")
# ...or by a path to the fabric's bin/: no `Bash(<name> *)` rule matches a
# path, so the session is asked anyway (review of #42, 2026-09-26).

# The texts a session reads and runs commands from.
SESSION_FACING = (
    glob.glob(os.path.join(ROOT, "communication", "gzcoord", "skills", "*", "SKILL.md"))
    + [os.path.join(ROOT, "policies", "subagent-dispatch", "SKILL.md")]
    + glob.glob(os.path.join(ROOT, "projects", "*", "integration", "gzcoord", "CLAUDE*.md"))
    + glob.glob(os.path.join(ROOT, "identities", "prompt", "*.md"))
    + [os.path.join(ROOT, "CLAUDE.md")]
    # What the scripts PRINT into a session's context (the replay hint of a
    # delivery over the notification cap, the start drain's lines).
    + glob.glob(os.path.join(ROOT, "communication", "gzcoord", "scripts", "*.mjs"))
    + glob.glob(os.path.join(ROOT, "communication", "gzcoord", "i18n", "*.json"))
)


def test_every_command_is_an_executable_with_a_shebang() -> None:
    for name, rel in DOC["commands"].items():
        path = os.path.join(ROOT, rel)
        assert os.path.isfile(path), (name, rel)
        assert os.access(path, os.X_OK), f"{rel} is not executable; `{name}` on PATH would not run"
        with open(path, "rb") as fh:
            assert fh.read(2) == b"#!", f"{rel} has no shebang; `{name}` on PATH would not run"


def test_every_script_runs_through_its_link() -> None:
    """bootstrap links each command into ~/.local/bin, so it runs with argv[1]
    the LINK. A main-module guard comparing argv[1] with the file's own path
    as a string made every node command a silent no-op that exited 0 (review
    of #42, 2026-09-26)."""
    probes = {"gzmsg": (["new-id"], r"^[0-9a-f]{8}-"), "gzcoord-send": (["--help"], r"usage"),
              "gzcoord-inbox": (["--held"], r"\S")}
    with tempfile.TemporaryDirectory() as d:
        for name, (args, expect) in probes.items():
            link = os.path.join(d, name)
            os.symlink(os.path.join(ROOT, DOC["commands"][name]), link)
            out = subprocess.run([link, *args], capture_output=True, text=True, timeout=60)
            assert re.search(expect, out.stdout + out.stderr), f"{name} {' '.join(args)} through its link printed nothing: {out}"


def test_a_wrapper_that_runs_another_command_is_never_allowed() -> None:
    assert set(DOC.get("not_allowed", {})) <= set(DOC["commands"]), DOC.get("not_allowed")
    assert {"fabric-lease", "fabric-host", "fabric-secret-run"} <= set(DOC.get("not_allowed", {})), \
        "fabric-lease and fabric-secret-run run the command after --, fabric-host runs any command on a host: an allow rule would allow everything"


# In a Markdown text a session reads, a command named by its script or by
# a relative bin/ path matches no allow rule either (review of #42). The
# scripts themselves may name their own files in comments; only prose that
# tells a session what to run is held to this.
BY_SCRIPT = re.compile(r"\bnode\s+\S*(?:inbox|send|gzmsg)\.mjs\b"
                       r"|\b(?:inbox|send)\.mjs`?\s+(?:--?\w|<|[/~.$]|\S+\.\w+\b|msg\b)"
                       r"|\bgzmsg\.mjs`?\s+(?:--?\w|(?:new-id|normalize|validate|hello)\b|<)"
                       r"|scripts/send\.mjs|(?:^|[\s`(\"'\[*])(?:\.{1,2}/)*bin/fabric-[a-z]+\b")


def test_no_session_facing_text_runs_a_command_through_an_expansion() -> None:
    hits = []
    for path in SESSION_FACING:
        with open(path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if EXPANDED_PATH.search(line) or (path.endswith(".md") and BY_SCRIPT.search(line)):
                    hits.append(f"{os.path.relpath(path, ROOT)}:{n}: {line.strip()[:100]}")
    assert not hits, "a session told to run these would be asked every time:\n" + "\n".join(hits)


def test_the_scan_catches_every_spelling_it_replaced() -> None:
    """Every form a session was told before (the review of #43)."""
    for line in ("run `./bin/fabric-status`", "(`bin/fabric-role bind`)", "`node inbox.mjs --replay 5`",
                 "`inbox.mjs --held`", "`send.mjs msg.txt`", "`gzmsg.mjs hello`", "`gzmsg.mjs new-id`",
                 "`communication/gzcoord/scripts/send.mjs`", "`inbox.mjs --follow` under Monitor",
                 "`node inbox.mjs`", "`send.mjs msg`", "`send.mjs /tmp/m.eml`", "`../../bin/fabric-status`",
                 "[bin/fabric-x](x)", "*bin/fabric-status*"):
        assert BY_SCRIPT.search(line), line
    for line in ("`communication/gzcoord/scripts/inbox.mjs` drains the relay", "run `fabric-status`",
                 "`gzcoord-send <file>`", "the fabric's `bin/` wrappers"):
        assert not BY_SCRIPT.search(line), line


def test_the_watch_the_hook_prescribes_is_a_bare_command() -> None:
    sys.path.insert(0, os.path.join(ROOT, "runtime", "claude-code", "hooks"))
    src = open(os.path.join(ROOT, "runtime", "claude-code", "hooks", "session-start.py"), encoding="utf-8").read()
    m = re.search(r"Monitor\(command: '([^']*)'", src)
    assert m and m.group(1).split()[0] in DOC["commands"] and "$" not in m.group(1), m and m.group(1)


def main() -> int:
    cases = [
        test_every_command_is_an_executable_with_a_shebang,
        test_every_script_runs_through_its_link,
        test_a_wrapper_that_runs_another_command_is_never_allowed,
        test_no_session_facing_text_runs_a_command_through_an_expansion,
        test_the_scan_catches_every_spelling_it_replaced,
        test_the_watch_the_hook_prescribes_is_a_bare_command,
    ]
    failed = 0
    for case in cases:
        try:
            case()
            print(f"  ok   {case.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
