#!/usr/bin/env python3
"""tools/fabric/local_settings.py — this account's per-clone harness
settings, <working copy>/.claude/settings.local.json, as the control
plane reads and prunes them (ADR-029; ADR-038 rule 9). Run as the
account, by its control agent (tools/fabric/control/local.py), by argv.

    local_settings.py report [--home H]   names and counts, JSON on stdout
    local_settings.py prune  [--home H]   remove the synced-secret env entries, JSON on stdout

The file is the account's own and gitignored, so nothing in a repository
shows what it holds, and no account may read another's home. Its `env`
block reaches the harness and every Bash call, and a token pasted there
(the relay's, before the launcher handed it over) is a second copy of a
secret that goes stale at the next rotation.

report: per working copy under ~/projects (and the projects root), the env
key NAMES, which of them are synced secrets, the permission rules by
count, the file's other top-level keys. Never a value.

prune: removes from each file the env entries that are synced secrets, and
nothing else. A synced secret is a name sync wrote into secrets.env that
is not one of env.sh's plain values, or one of the harness credentials the
fabric hands over itself. The file keeps its mode; it is rewritten through
a temporary file and a rename, only if nobody wrote it in between (the
harness writes it itself, for an "always allow" answer), and a symlink is
never followed.

Exit: 0 with a JSON object on stdout, whatever each file's state (the
object says it); 2 a usage error. Nothing here prints a value.
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys

HARNESS_CREDENTIALS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                       "OPENROUTER_API_KEY", "GH_TOKEN", "CLAUDE_BRIDGE_AUTH_TOKEN")
EXPORT_NAME = re.compile(r"^export ([A-Za-z_][A-Za-z0-9_]*)=")
SETTINGS = os.path.join(".claude", "settings.local.json")
ROOT_LABEL = "(projects root)"
USAGE = "usage: local_settings.py report|prune [--home H]"


def exported_names(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return [m.group(1) for m in map(EXPORT_NAME.match, fh) if m]
    except OSError:
        return []


def secret_names(home: str) -> set[str]:
    cfg = os.path.join(home, ".config", "agent-fabric")
    plain = set(exported_names(os.path.join(cfg, "env.sh")))
    return {n for n in (*HARNESS_CREDENTIALS, *exported_names(os.path.join(cfg, "secrets.env"))) if n not in plain}


def settings_files(home: str) -> list[tuple[str, str]]:
    """(working copy, path) for every settings.local.json one level under
    ~/projects, and the projects root's own; a symlink is listed, never
    followed."""
    root = os.path.join(home, "projects")
    try:
        names = sorted(e.name for e in os.scandir(root) if e.is_dir(follow_symlinks=False) and not e.name.startswith("."))
    except OSError:
        return []
    found = []
    for label, path in [(ROOT_LABEL, os.path.join(root, SETTINGS)), *[(n, os.path.join(root, n, SETTINGS)) for n in names]]:
        if os.path.lexists(path) or os.path.islink(os.path.dirname(path)):
            found.append((label, path))
    return found


def read_settings(path: str):
    """(status, doc, stat). Neither the file nor its .claude directory may
    be a symlink: O_NOFOLLOW guards only the last component, and a linked
    .claude would take every read and write into the link's target."""
    if os.path.islink(os.path.dirname(path)):
        st = os.lstat(os.path.dirname(path))
        return "symlink", None, st
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return "symlink", None, st
    if not stat.S_ISREG(st.st_mode):
        return "not a file", None, st
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except OSError:
        return "unreadable", None, st
    except ValueError:
        return "not json", None, st
    if not isinstance(doc, dict):
        return "not an object", None, st
    return "ok", doc, st


def env_of(doc: dict) -> dict:
    env = doc.get("env")
    return env if isinstance(env, dict) else {}


def report(home: str) -> dict:
    secrets = secret_names(home)
    files = []
    for label, path in settings_files(home):
        status, doc, _ = read_settings(path)
        if status != "ok":
            files.append({"working_copy": label, "status": status})
            continue
        env = sorted(env_of(doc))
        perms = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
        count = {k: len(perms[k]) if isinstance(perms.get(k), list) else 0 for k in ("allow", "deny", "ask")}
        files.append({"working_copy": label, "status": "ok", "env": env, "secrets": [n for n in env if n in secrets],
                      "permissions": count, "keys": sorted(k for k in doc if k not in ("env", "permissions"))})
    return {"status": "ok", "files": files}


def prune_file(path: str, secrets: set[str], before_rename=lambda: None) -> dict:
    status, doc, st = read_settings(path)
    if status != "ok":
        return {"status": "skipped" if status == "symlink" else "failed", "reason": status}
    env = env_of(doc)
    drop = sorted(n for n in env if n in secrets)
    if not drop:
        return {"status": "clean", "removed": []}
    for n in drop:
        del env[n]
    if not env:
        doc.pop("env", None)
    mode = stat.S_IMODE(st.st_mode)
    tmp = f"{path}.prune-{os.getpid()}"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, indent=2) + "\n")
        os.chmod(tmp, mode)
        before_rename()
        now = os.lstat(path)
        if (now.st_mtime_ns, now.st_size, now.st_ino) != (st.st_mtime_ns, st.st_size, st.st_ino):
            os.unlink(tmp)
            return {"status": "busy", "reason": "the file changed while it was being pruned; nothing was written"}
        os.replace(tmp, path)
    except OSError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return {"status": "failed", "reason": (e.strerror or type(e).__name__)[:120]}
    return {"status": "pruned", "removed": drop}


def prune(home: str, before_rename=lambda: None) -> dict:
    secrets = secret_names(home)
    files = [{"working_copy": label, **prune_file(path, secrets, before_rename)} for label, path in settings_files(home)]
    if any(f["status"] in ("failed", "busy") for f in files):
        status = "failed"
    else:
        status = "pruned" if any(f["status"] == "pruned" for f in files) else "clean"
    return {"status": status, "files": files}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("report", "prune"):
        print(USAGE, file=sys.stderr)
        return 2
    home = os.path.expanduser("~")
    rest = argv[1:]
    if rest[:1] == ["--home"] and len(rest) == 2:
        home = rest[1]
    elif rest:
        print(USAGE, file=sys.stderr)
        return 2
    print(json.dumps(report(home) if argv[0] == "report" else prune(home)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
