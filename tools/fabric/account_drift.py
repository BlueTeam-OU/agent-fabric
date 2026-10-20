#!/usr/bin/env python3
"""tools/fabric/account_drift.py — what in an account differs from what the
fabric wrote there. Read-only: it fixes and rewrites nothing.

The idea is `apm audit --ci` of microsoft/apm (MIT): rebuild what the tool
installs, then diff that against the tree. The fabric already keeps half of
it: fabric_writes.py records the sha256 of every file bootstrap.py and
install_agent_files.py write, and bootstrap.py --dry-run says what a run
would change. This module puts the two side by side.

CONTRACT (j138; the request is develop-qzapp/user's, 2026-10-20):

  argv         [--json], [-h|--help]. Anything else: "fabric-drift: unknown
               argument X" on stderr, nothing on stdout, exit 2.
  environment  what fabric_writes.state_dir() reads (AGENT_FABRIC_STATE_DIR,
               XDG_STATE_HOME, HOME) to find the record, and what the
               bootstrap child reads (HOME, CLAUDE_CONFIG_DIR,
               XDG_CONFIG_HOME, AGENT_FABRIC_LOCAL_BIN) to know the same
               account's files. Passed to the child as it is.
  reads        <state>/agents/<login>/fabric-written.json — {absolute path:
               sha256 of what the fabric last wrote there}; every path it
               names; and the stdout of this checkout's
               `tools/fabric/bootstrap.py --dry-run`, which writes nothing.
  findings     one per path that is not as the fabric left it:
                 edited      exists and its sha256 is not the recorded one
                 missing     the record names it and nothing is there
                 unreadable  it is there and cannot be read (the error)
                 stale       a "+  <what> (would write)" or "(would link)"
                             line of the dry run that no edited or missing
                             path above explains: the fabric would change it
                             although the account holds what the fabric last
                             wrote (it moved upstream), or never recorded it
               A path whose hash matches is `ok`: counted, never listed.
  stdout       one line per finding, "<kind>  <what>[: <detail>]", sorted by
               kind then path with the stale lines in the dry run's order,
               then the counts last: "ok N, edited N, missing N, unreadable
               N, stale N". --json: one object, {"status": "ok"|"drift",
               "counts": {...}, "findings": [{"kind", "path"[, "detail"]}]},
               the same data.
  stderr       a refusal, one line, "fabric-drift: <why>".
  exit         0 no finding; 1 drift found; 2 usage, or the check could not
               be made: no record, an unreadable or malformed record, the
               bootstrap child failing, timing out or not found. Unknown
               is never "ok": a record that cannot be read does not read as
               an account that has written nothing (fabric_writes.py reads
               it so, to cost one extra backup; here that would be silence).

What is deliberately not here: a fix, ~/.claude.json (bootstrap edits it in
place and records no hash), and the dry run's lines that are not a file or a
link ("episodic journal: would import …" has no "(would write)").
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from typing import Any

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import fabric_writes  # noqa: E402

# bootstrap --dry-run measured at about 3 s on a warm host; the children it
# runs (the langid and settings dry runs) are what make it that long.
BOOTSTRAP_TIMEOUT_S = 60
KINDS = ("ok", "edited", "missing", "unreadable", "stale")
_WOULD = re.compile(r"^  \+  (?P<what>.+) \((?:would write|would link)\)$")

HELP = """bin/fabric-drift — what in this account differs from what the fabric wrote.

usage: fabric-drift [--json]

Read-only. Compares fabric-written.json (the sha256 of every file bootstrap
and install-agent-files wrote) with the files now, then asks this checkout's
`bootstrap.py --dry-run` what it would change and reports each line the
record does not already explain as stale. One line per finding, the counts
last; --json is the same as data.
exit: 0 clean, 1 drift found, 2 usage or the check could not be made.
"""


class DriftError(Exception):
    """The check could not be made; the message is the one line to say."""


def load_record(path: str) -> dict[str, str]:
    """The record as written, or DriftError: unlike fabric_writes._load,
    which reads an unreadable record as empty, absent and unreadable are
    different answers here."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        raise DriftError(f"no record at {path}: bootstrap has not run as this account") from None
    except (OSError, ValueError) as e:
        raise DriftError(f"cannot read the record {path}: {e}") from None
    ok = isinstance(doc, dict) and all(isinstance(k, str) and os.path.isabs(k) and isinstance(v, str) for k, v in doc.items())
    if not ok:
        raise DriftError(f"the record {path} is not a map of absolute paths to hashes")
    return doc


def judge(path: str, recorded: str) -> tuple[str, str | None]:
    """(kind, detail) of one recorded path."""
    try:
        with open(path, "rb") as f:
            got = hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        if e.errno in (errno.ENOENT, errno.ENOTDIR):
            return "missing", None
        return "unreadable", e.strerror or str(e)
    return ("ok", None) if got == recorded else ("edited", None)


def _reap(proc: subprocess.Popen) -> None:
    """The child and what it started, gone: bootstrap's own children (the
    settings and langid dry runs) share its group, and subprocess.run kills
    only the direct child. The wait is bounded; a grandchild that left the
    group and holds the pipes open is left to finish."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def would_change(root: str, env: dict[str, str], timeout: float) -> list[str]:
    """What the dry run says it would write or link, one subject per line,
    in its order."""
    script = os.path.join(root, "tools", "fabric", "bootstrap.py")
    try:
        proc = subprocess.Popen([sys.executable, script, "--dry-run"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, errors="replace", env=env, start_new_session=True)
    except OSError as e:
        raise DriftError(f"cannot run bootstrap --dry-run: {e.strerror or e}") from None
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _reap(proc)
        raise DriftError(f"bootstrap --dry-run did not finish in {timeout:g} s") from None
    except BaseException:   # an interrupt must not strand a child in its own session
        _reap(proc)
        raise
    if proc.returncode != 0:
        said = [ln for ln in err.splitlines() if ln.strip()]
        raise DriftError(f"bootstrap --dry-run exited {proc.returncode}" + (f": {said[-1].strip()[:200]}" if said else ""))
    return [m["what"] for m in map(_WOULD.match, out.splitlines()) if m]


def explained(what: str, paths: set[str]) -> bool:
    """A dry-run subject is a path, or a path and words after it
    ("<settings> fabric user settings", "<link> -> <target>")."""
    return any(what == p or what.startswith(p + " ") for p in paths)


def check(state: str | None = None, root: str | None = None, home: str | None = None,
          timeout: float = BOOTSTRAP_TIMEOUT_S) -> dict[str, Any]:
    """The report; DriftError when it cannot be made."""
    state = fabric_writes.state_dir() if state is None else state
    root = os.path.dirname(os.path.dirname(HERE)) if root is None else root
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = home
    record = load_record(os.path.join(state, fabric_writes.RECORD))
    counts = dict.fromkeys(KINDS, 0)
    findings: list[dict[str, str]] = []
    off: set[str] = set()
    for path in sorted(record):
        kind, detail = judge(path, record[path])
        counts[kind] += 1
        if kind != "ok":
            findings.append({"kind": kind, "path": path, **({"detail": detail} if detail else {})})
        if kind in ("edited", "missing", "unreadable"):
            off.add(path)
    findings.sort(key=lambda f: KINDS.index(f["kind"]))
    for what in would_change(root, env, timeout):
        if not explained(what, off):
            counts["stale"] += 1
            findings.append({"kind": "stale", "path": what})
    return {"status": "drift" if findings else "ok", "counts": counts, "findings": findings}


def render(report: dict[str, Any]) -> str:
    lines = [f"{f['kind']:<10} {f['path']}" + (f": {f['detail']}" if "detail" in f else "") for f in report["findings"]]
    lines.append(", ".join(f"{k} {report['counts'][k]}" for k in KINDS))
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    as_json = False
    for a in argv:
        if a in ("-h", "--help"):
            sys.stdout.write(HELP)
            return 0
        if a == "--json":
            as_json = True
        else:
            print(f"fabric-drift: unknown argument {a}", file=sys.stderr)
            return 2
    try:
        report = check()
    except DriftError as e:
        print(f"fabric-drift: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(report, indent=1) + "\n" if as_json else render(report))
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
