#!/usr/bin/env python3
"""runtime/claude-code/hooks/session-seal.py — the shell seal, a SessionStart hook (agent-fabric ADR-038 rule 9).

CONTRACT:
  argv    none; the managed file runs it through hook_entry.py (`session-seal`), the workspace settings as
          python3 <this file>
  stdin   ignored (the hook payload is never read)
  stdout  nothing
  exit    0, whatever happens: it must never block or fail a session start

Appends one line to $CLAUDE_ENV_FILE, the file the harness sources into every later Bash call:
`unset <the harness's credentials and every name sync wrote into secrets.env>  # agent-fabric: no secret in the
session shell`. Names only, never a value.

A hook of its own, not a step of session-start.py: that one is a workspace hook a login drops by editing its
settings, and the seal is a guard, so it runs from the managed file too (ADR-043 rule 2). Stdlib only and no
import from the tree: hook_entry runs it as `fabric-python -I -S`, where only the standard library is on the path.
"""
from __future__ import annotations

import os
import re
import sys

# No secret in the session's shell (ADR-038 rule 9). The harness holds its
# own credential in its environment, and every Bash call and subagent
# inherited it, with whatever else the launch's shell carried; a reviewer
# printed its environment and a key was rotated (#95). The file the
# harness sources into every Bash call unsets the harness's credentials
# and every name sync wrote into secrets.env, but the plain values in
# env.sh. Names only, never a value; the harness keeps what it signs in
# with. Once per file: the hook runs again on resume and compaction, and the
# managed and the workspace copy may both run on the same file.
SHELL_SEAL = "# agent-fabric: no secret in the session shell"
HARNESS_CREDENTIALS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                       "OPENROUTER_API_KEY", "GH_TOKEN", "CLAUDE_BRIDGE_AUTH_TOKEN")
EXPORT_NAME = re.compile(r"^export ([A-Za-z_][A-Za-z0-9_]*)=")


def synced_names(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return [m.group(1) for m in map(EXPORT_NAME.match, fh) if m]
    except OSError:
        return []


def seal_session_shell(env_file: str | None, home: str) -> None:
    if not env_file:
        return
    try:
        with open(env_file, "rb") as fh:   # bytes: a file that is not UTF-8 is still searched
            if any(line.rstrip(b"\n").endswith(SHELL_SEAL.encode()) for line in fh):
                return
    except FileNotFoundError:
        pass
    except OSError:
        return
    cfg = os.path.join(home, ".config", "agent-fabric")
    plain = set(synced_names(os.path.join(cfg, "env.sh")))
    names = list(HARNESS_CREDENTIALS)
    names += [n for n in synced_names(os.path.join(cfg, "secrets.env")) if n not in names and n not in plain]
    try:
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.write(f"unset {' '.join(names)}  {SHELL_SEAL}\n")
    except OSError:
        pass


def main() -> int:
    try:
        seal_session_shell(os.environ.get("CLAUDE_ENV_FILE"), os.path.expanduser("~"))
    except Exception:  # noqa: BLE001 — a seal that cannot be written must not cost the session its start
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
