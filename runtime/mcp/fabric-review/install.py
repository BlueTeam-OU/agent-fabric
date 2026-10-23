#!/usr/bin/env python3
"""runtime/mcp/fabric-review/install.py — the fabric-review MCP entry in a login's Claude Code user configuration
(ADR-065 §2 A): the read-only tools the review class reads through (review_diff, review_log, review_show,
review_blame, review_grep, review_check).

    install.py <claude.json> set [--dry-run]

`set` writes (or leaves, when identical) mcpServers["fabric-review"] as a stdio server running the bare name
`fabric-review-mcp`. The rules for the file, the exit codes (3 = UNUSABLE) and the output line are
runtime/mcp/stdio_entry.py's, shared with fabric-memory/install.py. There is no `remove`: the server is for every
login, since any session may dispatch the review class.
"""
from __future__ import annotations

import os
import sys

# -I (as bootstrap and the tests run this) leaves the script's directory off sys.path, and the shared module sits
# one level up.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stdio_entry  # noqa: E402

NAME = "fabric-review"
COMMAND = "fabric-review-mcp"
ENTRY = {"type": "stdio", "command": COMMAND, "args": [], "env": {}}
UNUSABLE = stdio_entry.UNUSABLE
load = stdio_entry.load
save = stdio_entry.save


def main(argv: list[str]) -> int:
    return stdio_entry.main(argv, NAME, COMMAND, __doc__)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
