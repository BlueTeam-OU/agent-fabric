#!/usr/bin/env python3
"""tools/fabric/workspace_trust.py — the folders the fabric itself set up
for an account are trusted in Claude Code before its first session.

    workspace_trust.py [--dry-run] <dir>...

Run AS THE ACCOUNT, by bootstrap.sh: the workspace (~/projects), the
fabric's checkout and each registered project's working copy — clones the
fabric made from the remotes projects/registry.json names, and nothing
else. Claude Code asks, once per folder, whether it is trusted, and keeps
the answer as `projects.<dir>.hasTrustDialogAccepted` in the account's
.claude.json; a new account met that question at its first launch, in a
terminal, for folders the coordinator had just cloned (the owner,
2026-10-01: a new agent's setup asks no such question).

Every other key of the file is kept as read; the file is replaced
atomically with its own mode, and only when something changes, since a
running session writes the same file. A folder that does not exist is
skipped, never recorded.

exit 0 done; 1 the file is unreadable or not an object (nothing written);
2 usage.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

KEY = "hasTrustDialogAccepted"


def config_path(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    base = env.get("CLAUDE_CONFIG_DIR")
    return os.path.join(base, ".claude.json") if base else os.path.join(env.get("HOME") or os.path.expanduser("~"), ".claude.json")


def trust(dirs: list[str], path: str, dry_run: bool = False) -> list[tuple[str, str]]:
    """(dir, "+" newly trusted | "=" already | "-" skipped: not a directory)."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        doc = {}
    if not isinstance(doc, dict):
        raise ValueError(f"{path} is not a JSON object")
    projects = doc.setdefault("projects", {})
    if not isinstance(projects, dict):
        raise ValueError(f"{path}: `projects` is not an object")
    rows, changed = [], False
    for d in dirs:
        d = os.path.realpath(d)
        if not os.path.isdir(d):
            rows.append((d, "-"))
            continue
        entry = projects.setdefault(d, {})
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: projects[{d!r}] is not an object")
        if entry.get(KEY) is True:
            rows.append((d, "="))
        else:
            entry[KEY] = True
            rows.append((d, "+"))
            changed = True
    if changed and not dry_run:
        mode = os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o600
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".claude.json.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2)
                f.write("\n")
            os.chmod(tmp, mode)
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise
    return rows


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    dirs = [a for a in argv if a != "--dry-run"]
    if not dirs or any(a.startswith("-") for a in dirs):
        print("usage: workspace_trust.py [--dry-run] <dir>...", file=sys.stderr)
        return 2
    try:
        rows = trust(dirs, config_path(), dry)
    except (OSError, ValueError) as e:
        print(f"workspace_trust: {e}; nothing written", file=sys.stderr)
        return 1
    for d, mark in rows:
        print({"+": f"  +  {d}: trusted in Claude Code" + (" (would write)" if dry else ""),
               "=": f"  =  {d}: trusted in Claude Code",
               "-": f"  -  {d}: not a directory; not recorded"}[mark])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
