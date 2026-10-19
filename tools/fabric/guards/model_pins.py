#!/usr/bin/env python3
"""tools/fabric/guards/model_pins.py — a repository's COMMITTED Claude Code
settings carry no model pin, no effort pin and no provider routing (ADR-040
Wave 9 batch 3; policies/check_repo_settings_carry_no_model_pins.sh is its
forwarder).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      none; extra arguments are ignored, as the bash ignored them
  env       AGENT_FABRIC_SETTINGS_FILE  the file to check, taken as given
            REPO_ROOT                   else <it>/.claude/settings.json
            (both unset or empty: <toplevel of the cwd's repository>/.claude/settings.json,
            and outside a repository <cwd>/.claude/settings.json)
            AGENT_FABRIC_PYTHON         read by the forwarder only, never here
  files     the one settings file above; .mcp.json is NOT read although the
            bash header said so (the bash never did). Not a regular file
            (absent, or a directory) reads as absent.
  stdout    every verdict, pass or fail, one report per run:
              absent  `check_repo_settings_carry_no_model_pins: OK — <file> does not exist.`
              clean   `check_repo_settings_carry_no_model_pins: OK — <file> carries no model pins.`
              pinned  `FAIL: <file> carries model pins (<n>):`, then `      <i>. <reason>`
                      per pin in the order: model, modelOverrides, effortLevel,
                      maxEffortLevel, modelSettings, then env keys sorted, then
                      the two closing lines (`Shape D ...`, `remove these ...`)
              broken  `FAIL: <file> is not readable JSON (<error>); a broken settings file`
                      and `      silently disables every setting it carries.`
  stderr    nothing, but for a settings file whose JSON is not an object: one
            line (the bash crashed with a traceback there; exit 1 either way)
  exit      0 absent or clean; 1 any pin, unreadable JSON, a non-object
            document. The forwarder adds 127 (no pinned Python), checked
            there before the file is looked at, so a missing pin with a missing
            file is 127 through the forwarder and 0 in the bash.

WHY EACH KEY. Model choice lives in two places and nowhere else: a managed
repository pins harness ALIASES in policy text, and the launcher exports the
concrete ANTHROPIC_DEFAULT_*_MODEL pins from routing/. A committed pin would
outrank the launcher's process env (user-scope env beats process env), and
`modelOverrides` is taken as the whole map from the highest scope that sets
it, so it binds both paths. Effort is the second routed dimension
(routing/effort.json): effortLevel pins the session's, modelSettings carries a
per-model one, and maxEffortLevel is a CAP whose LOWEST value across scopes
wins, so a committed cap cannot be raised back by a launch. All of them stay
refused HERE although the launcher's live scan refuses only maxEffortLevel:
a committed scope is read on every clone and nothing should pin anything in
it. A key that is present is pinned whatever its value (null too).

NOT CHECKED: .claude/settings.local.json (gitignored) and the user scopes; the
launcher fences those at launch (tools/fabric/launcher/settings.py). A managed
project's CI may run its own, older copy of the bash, which this port does
not touch."""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import git  # noqa: E402

NAME = "check_repo_settings_carry_no_model_pins"
EFFORT_KEYS = (
    ("effortLevel", "pins the session's thinking for every session on this repo"),
    ("maxEffortLevel", "caps it — the lowest value across all scopes wins, so this one cannot be raised back by a launch"),
    ("modelSettings", "carries per-model settings, effort included"),
)
ENV_NAMES = ("CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL")


def settings_path(env: dict[str, str]) -> str:
    if env.get("AGENT_FABRIC_SETTINGS_FILE"):
        return env["AGENT_FABRIC_SETTINGS_FILE"]
    root = env.get("REPO_ROOT")
    if not root:
        try:
            root = git.toplevel(os.getcwd())
        except git.GitError:  # no such program: the bash fell back to pwd the same way
            root = None
        root = root or os.getcwd()
    return os.path.join(root, ".claude", "settings.json")


def pins_of(d: dict) -> list[str]:
    fails = []
    if "model" in d:
        fails.append('top-level "model" is set — it pins the session model for every session on this repo, both paths.')
    if "modelOverrides" in d:
        fails.append('"modelOverrides" present: taken as the WHOLE MAP from the highest-precedence scope that sets it, '
                     'so it binds the claude path too — model choice belongs to the launcher.')
    for key, why in EFFORT_KEYS:
        if key in d:
            fails.append(f'"{key}" present: it {why}. Effort is routed in routing/effort.json.')
    env = d.get("env") or {}
    for k in sorted(k for k in env if k.startswith("ANTHROPIC_") or k in ENV_NAMES):
        fails.append(f'env.{k} present — provider/routing env in a committed scope would outrank the launcher pins.')
    return fails


def main() -> int:
    sys.stdout.reconfigure(errors="surrogateescape")
    path = settings_path(dict(os.environ))
    if not os.path.isfile(path):
        print(f"{NAME}: OK — {path} does not exist.")
        return 0
    try:
        with open(path) as fh:
            d = json.load(fh)
    except Exception as exc:
        print(f"FAIL: {path} is not readable JSON ({exc}); a broken settings file")
        print("      silently disables every setting it carries.")
        return 1
    if not isinstance(d, dict):
        print(f"{NAME}: {path} is not a JSON object.", file=sys.stderr)
        return 1
    fails = pins_of(d)
    if fails:
        print(f"FAIL: {path} carries model pins ({len(fails)}):")
        for i, f in enumerate(fails, 1):
            print(f"      {i}. {f}")
        print("      Shape D puts model choice in the launcher + routing files;")
        print("      remove these from the committed settings file.")
        return 1
    print(f"{NAME}: OK — {path} carries no model pins.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
