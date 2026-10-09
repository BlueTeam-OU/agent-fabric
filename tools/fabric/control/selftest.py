"""tools/fabric/control/selftest.py — the `secrets-selftest` ACTION (sign
ACTION_OPS): proves, on each account, that an agent can add, use and
delete a secret of its own. The port of runtime/control/selftest.mjs. The
work is tools/fabric/secret_selftest.py, run as this login through
`fabric-secrets selftest --json` — no field of a request reaches it; this
is the daemon's door to it, as local.py is to local_settings.py.

An action, signed, because it writes: two signed commits to the login's
store (set, then rm, of AF_SELFTEST_CANARY), pushed to its remote. It
takes no arguments. The reply is the tool's verdict and its steps —
{status: pass|fail, name, steps: [{step, ok, reason}]} — never the
canary or its digest, which never leave the tool. `failed` is a test
that could not be run or answered no report; `busy`, one already
running on this account.
"""
from __future__ import annotations

import os
import subprocess
import threading
from typing import Any, Callable

from control.local import takes_no_arguments
from control.ops import util
from gzcoord import gzmsg

# Above the tool's own worst case (seven commands, each bounded at 60 s):
# a test killed half-way may leave its canary, which the next one then
# refuses to overwrite and names.
SELFTEST_TIMEOUT_MS = 450000
# How long fabric-ctl waits for the replies: the run, and the relay's way back.
SELFTEST_BUDGET_S = SELFTEST_TIMEOUT_MS // 1000 + 30
SELFTEST_MAX_BYTES = 4 * 1024 * 1024
MAX_STEPS = 16


def _default_root(home: str) -> str:
    env = os.environ.get("AGENT_FABRIC_ROOT")
    return os.path.join(home, "projects", "agent-fabric") if env is None else env


def _last_line(s: Any) -> str:
    return gzmsg.js_trim("" if s is None else util.decode(s)).split("\n")[-1][:200]


def _str(v: Any, limit: int) -> str:
    """What the tool reports is relayed only as strings and booleans of bounded
    size: a field of another type is no field, so no report can make the
    reply fail to build (and agentd post nothing) or grow without bound."""
    return v[:limit] if isinstance(v, str) else ""


# One self-test at a time per daemon: both would write the same name.
_RUNNING = threading.Lock()


def secrets_selftest(request: Any, **opts: Any) -> dict:
    if not _RUNNING.acquire(blocking=False):
        return {"status": "busy", "note": "a secrets-selftest is already running on this account"}
    try:
        return secrets_selftest_once(request, **opts)
    finally:
        _RUNNING.release()


def secrets_selftest_once(request: Any, home: str | None = None, root: str | None = None,
                          run: Callable[..., Any] = util.run_bounded) -> dict:
    home = os.path.expanduser("~") if home is None else home
    root = _default_root(home) if root is None else root
    if not takes_no_arguments(request):
        return {"status": "refused", "reason": "secrets-selftest takes no arguments"}
    cmd = [os.path.join(root, "bin", "fabric-secrets"), "selftest", "--json"]
    code, out, err = 0, "", ""
    try:
        out = util.decode(run(cmd, timeout=SELFTEST_TIMEOUT_MS / 1000, max_bytes=SELFTEST_MAX_BYTES).stdout)
    except subprocess.CalledProcessError as e:
        if e.returncode < 0:   # a signal: no exit code, as the Node's e.code was not a number
            return {"status": "failed", "reason": f"fabric-secrets selftest: {_last_line(util.node_error(e, cmd))}"}
        code, out, err = e.returncode, util.decode(e.output), util.decode(e.stderr)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": f"fabric-secrets selftest: timed out after {SELFTEST_TIMEOUT_MS // 1000} s"}
    except (subprocess.SubprocessError, OSError) as e:
        return {"status": "failed", "reason": f"fabric-secrets selftest: {_last_line(util.node_error(e, cmd))}"}
    try:
        report = util.loads(out)
    except ValueError:
        report = None   # said below
    # 0 is pass, 1 fail; anything else, or no report, is a test not run.
    steps_in = report.get("steps") if isinstance(report, dict) else None
    if code not in (0, 1) or not util.truthy(report) or not isinstance(steps_in, list):
        return {"status": "failed", "reason": _last_line(err) or f"fabric-secrets selftest exited {code} with no report"}
    if len(steps_in) > MAX_STEPS:
        return {"status": "failed", "reason": f"fabric-secrets selftest reported {len(steps_in)} steps, more than {MAX_STEPS}"}
    steps = [{"step": _str(s.get("step") if isinstance(s, dict) else None, 40) or "?",
              "ok": (s.get("ok") if isinstance(s, dict) else None) is True,
              "reason": _str(s.get("reason") if isinstance(s, dict) else None, 200)} for s in steps_in]
    passed = code == 0 and report.get("status") == "pass" and len(steps) > 0 and all(s["ok"] for s in steps)
    return {"status": "pass" if passed else "fail", "name": _str(report.get("name"), 64), "steps": steps}
