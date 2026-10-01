#!/usr/bin/env python3
"""tools/fabric/fabric_settings.py — agent-fabric's own .claude/settings.json,
rendered from the workspace template.

    fabric_settings.py --write     render it into .claude/settings.json
    fabric_settings.py --check     exit 1 when the committed file differs

Claude Code reads a project's settings from the folder a session starts
in, not from its parents. Every managed project commits a
.claude/settings.json carrying the fabric's hooks and status line, reaching
the fabric as $CLAUDE_PROJECT_DIR/../agent-fabric; agent-fabric had none,
because until python-dev-01 (2026-10-01) only the coordinator worked here,
started from the workspace, whose settings bootstrap.sh writes from
runtime/claude-code/workspace/settings.json. A session started inside this
clone ran with no SessionStart context, no dispatch guard, no status line.
This renders the same template with the fabric at $CLAUDE_PROJECT_DIR, so
the hooks a session gets here are the workspace's, never a second list.
"""
from __future__ import annotations

import json
import os
import sys

FABRIC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join("runtime", "claude-code", "workspace", "settings.json")
TARGET = os.path.join(".claude", "settings.json")
ROOT_REF = "$CLAUDE_PROJECT_DIR"


def render(root: str = FABRIC) -> str:
    with open(os.path.join(root, TEMPLATE), encoding="utf-8") as f:
        tpl = json.load(f)
    tpl.pop("_comment", None)

    def sub(v):
        if isinstance(v, str):
            return v.replace("$AGENT_FABRIC_ROOT", ROOT_REF)
        if isinstance(v, list):
            return [sub(x) for x in v]
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        return v
    return json.dumps(sub(tpl), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    if argv not in (["--write"], ["--check"]):
        print("usage: fabric_settings.py --write|--check", file=sys.stderr)
        return 2
    path = os.path.join(FABRIC, TARGET)
    want = render()
    if argv == ["--write"]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(want)
        print(f"wrote {TARGET} from {TEMPLATE}")
        return 0
    try:
        have = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        have = None
    if have != want:
        print(f"{TARGET} is not {TEMPLATE} rendered with {ROOT_REF}: python3 tools/fabric/fabric_settings.py --write",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
