"""tools/fabric/control/tools.py — the tools report: what `fabric-tools --all
--json` says this account has of the tools every project declares
(projects/registry.json `tools`), kept in <state>/tools.json and read
back by the `tools` op. The port of runtime/control/tools.mjs; tools.json
is frozen with the wire (ADR-040 Wave 8).

WHY A FILE. The proofs are 15 s each and a session start must not wait
on a dozen of them, so the control agent runs them in the background
and the session-start hook (runtime/claude-code/hooks/session-start.py
tools_line) reads the result. The file IS fabric-tools' --json document,
byte for byte in meaning: the hook reads `tools` rows and takes the age
from the file's mtime, so no field is added to it.

A run that fails (the Python pin absent, a registry that does not parse,
the bound exceeded) leaves the previous report in place: an old answer
that says how old it is beats none, and a missing tool must not look
present because a later run could not look. The failure is logged once
per distinct cause, not every hour.

`tools` is an operator read like `jobs`: not public.

The timers (at start, every hour, on a change of the binding file) are
the daemon's: ToolsKeeper gives it refresh() and refresh_again().
"""
from __future__ import annotations

import errno
import json
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Callable

from control.ops import util

TOOLS_REPORT = "tools.json"
TOOLS_INTERVAL_MS = 3600 * 1000
BINDING_POLL_MS = 30 * 1000
# The proofs run one after another at 15 s each at worst, so this holds sixty
# of them; the registry declares sixteen. A registry past that would time every
# run out and keep the first report for ever, with one log line.
TOOLS_RUN_TIMEOUT_MS = 15 * 60 * 1000
MAX_BUFFER = 4 * 1024 * 1024

# tools/fabric/control/ -> the checkout this code is in.
_CODE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))


def report_file(directory: str | None = None) -> str:
    return os.path.join(util.state_dir() if directory is None else directory, TOOLS_REPORT)


def parse_run(code: int, stdout: str) -> dict:
    """fabric-tools exits 1 when a required tool is missing, with the complete
    document on stdout: that is an answer, not a failure. Exit 2 (a bad
    registry), 127 (no pinned Python) and a timeout are failures. A document
    whose `ok` disagrees with the exit status is not trusted either way."""
    if code not in (0, 1):
        return {"error": f"fabric-tools exited {code}"}
    try:
        doc = json.loads(stdout)
    except ValueError:
        return {"error": "fabric-tools --json printed no JSON document"}
    if (not isinstance(doc, dict) or not isinstance(doc.get("projects"), list) or not isinstance(doc.get("tools"), list)
            or not isinstance(doc.get("ok"), bool)):
        return {"error": "fabric-tools --json printed a document without projects, tools and ok"}
    if doc["ok"] != (code == 0):
        return {"error": f"fabric-tools exited {code} but the document says ok: {'true' if doc['ok'] else 'false'}"}
    return {"doc": doc}


def run_tools(root: str | None = None, run: Callable[..., Any] = util.run_bounded, home: str | None = None,
              timeout_ms: int = TOOLS_RUN_TIMEOUT_MS) -> dict:
    root = _CODE_ROOT if root is None else root
    home = os.path.expanduser("~") if home is None else home
    try:
        r = run([os.path.join(root, "bin", "fabric-tools"), "--all", "--json"], cwd=home,
                timeout=timeout_ms / 1000, max_bytes=MAX_BUFFER)
        return parse_run(0, util.decode(r.stdout))
    except subprocess.TimeoutExpired:
        return {"error": f"fabric-tools did not finish within {util.whole(timeout_ms / 1000)} s"}
    except util.OutputOverflow:
        return {"error": f"fabric-tools printed more than {MAX_BUFFER // 1048576} MiB"}
    except subprocess.CalledProcessError as e:
        # A signal (the OOM killer's SIGKILL) is not the bound being too small.
        if e.returncode < 0:
            return {"error": f"fabric-tools was killed by {signal.Signals(-e.returncode).name}"}
        return parse_run(e.returncode, util.decode(e.output))
    except OSError as e:
        return {"error": f"fabric-tools could not run ({errno.errorcode.get(e.errno or 0) or e})"}


def write_report(file: str, doc: Any) -> None:
    """tmp beside the target and a rename, so the hook and the op read either
    the old report or the new one, never half of one."""
    os.makedirs(os.path.dirname(file), exist_ok=True)
    tmp = f"{file}.{os.getpid()}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(util.js_json(doc, indent=2) + "\n")
        os.rename(tmp, file)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass   # nothing was written
        raise


def _stderr(m: str) -> None:
    print(m, file=sys.stderr, flush=True)


class ToolsKeeper:
    """One run at a time; a failure is said once per distinct cause until a
    run succeeds. A caller that asks while a run is in flight joins it and
    gets its answer, as the Node's single-flight promise did."""

    def __init__(self, run: Callable[[], dict] | None = None, file: str | None = None,
                 log: Callable[[str], None] = _stderr) -> None:
        self._run = run or (lambda: run_tools())
        self.file = report_file() if file is None else file
        self.log = log
        self._said: set[str] = set()
        self._cv = threading.Condition()
        self._running = False
        self._done = 0          # how many runs have ended: a joiner waits for the next
        self._last: dict = {}

    def _once(self) -> dict:
        try:
            r = self._run()
        except Exception as e:  # noqa: BLE001 — a run that raised is a run that failed, said once
            r = {"error": str(e)}
        if r.get("doc") is not None:
            try:
                write_report(self.file, r["doc"])
                self._said.clear()
                return {"status": "written"}
            except OSError as e:
                r = {"error": f"the report could not be written ({errno.errorcode.get(e.errno or 0) or e})"}
        if r["error"] not in self._said:
            self._said.add(r["error"])
            self.log(f"agentd: tools report not refreshed, the previous one stays: {r['error']}")
        return {"status": "kept", "error": r["error"]}

    def _join(self) -> dict:
        ended = self._done
        while self._done == ended:
            self._cv.wait()
        return self._last

    def refresh(self) -> dict:
        with self._cv:
            if self._running:
                return self._join()
            self._running = True
        r: dict = {"status": "kept", "error": "the run was interrupted"}
        try:
            r = self._once()
        finally:
            with self._cv:
                self._running = False
                self._done += 1
                self._last = r
                self._cv.notify_all()
        return r

    def refresh_again(self) -> dict:
        """A run already in flight began under the binding that has since
        changed, so its answer is stale on arrival: wait for it, then run once
        more (the callers waiting meanwhile join that one more run)."""
        with self._cv:
            if self._running:
                self._join()
        return self.refresh()


def tools(directory: str | None = None, now: Callable[[], float] = lambda: time.time() * 1000) -> dict:
    """The `tools` op: the report as the last good run left it, and its age."""
    file = report_file(directory)
    try:
        with open(file, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        at = os.stat(file).st_mtime * 1000
    except FileNotFoundError:
        return {"status": "none"}
    except OSError as e:
        return {"status": "failed", "error": f"{TOOLS_REPORT}: {errno.errorcode.get(e.errno or 0) or e}"}
    try:
        doc = json.loads(text)
    except ValueError:
        return {"status": "failed", "error": f"{TOOLS_REPORT} is not JSON"}
    if not util.truthy(doc) or not isinstance(doc.get("tools") if isinstance(doc, dict) else None, list):
        return {"status": "failed", "error": f"{TOOLS_REPORT} holds no tools list"}
    return {"status": "ok", "age_s": max(0, util.js_round((now() - at) / 1000)), "ok": doc.get("ok") is True, "tools": doc["tools"]}
