"""tools/fabric/control/local.py — each account's per-clone harness settings,
<working copy>/.claude/settings.local.json, on the control plane
(ADR-029; ADR-038 rule 9). The port of runtime/control/local.mjs. The work
is tools/fabric/local_settings.py, run as this login by argv — no field of
a request reaches it; this is the daemon's door to it, as jobs.py is to
tools/fabric/jobs.py.

  `local`        a read op: per working copy, the env key NAMES, which of
                 them are synced secrets, permission rules by count,
                 other top-level keys. Never a value.
  `local-prune`  an ACTION (sign ACTION_OPS): removes the env entries
                 that duplicate a synced secret, nothing else. It takes
                 no arguments.

A failure of `local` raises, for collect() to say as the section's; a
failure of `local-prune` is its reply.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Callable

from control.ops import util
from gzcoord import gzmsg

LOCAL_TIMEOUT_S = 15


def _tool(root: str) -> str:
    return os.path.join(root, "tools", "fabric", "local_settings.py")


def _default_root(home: str) -> str:
    env = os.environ.get("AGENT_FABRIC_ROOT")
    return os.path.join(home, "projects", "agent-fabric") if env is None else env


def _run(sub: str, home: str | None = None, root: str | None = None, run: Callable[..., Any] = subprocess.run) -> Any:
    home = os.path.expanduser("~") if home is None else home
    root = _default_root(home) if root is None else root
    r = run([sys.executable, _tool(root), sub, "--home", home], capture_output=True, text=True, errors="replace",
            timeout=LOCAL_TIMEOUT_S, check=True, stdin=subprocess.DEVNULL)
    return json.loads(r.stdout)


def local(**opts: Any) -> Any:
    return _run("report", **opts)


def takes_no_arguments(request: Any) -> bool:
    """`args` absent, or an empty object — nothing else, null included."""
    if not isinstance(request, dict) or "args" not in request:
        return True
    a = request["args"]
    return isinstance(a, dict) and not a


def local_prune(request: Any, **opts: Any) -> dict:
    if not takes_no_arguments(request):
        return {"status": "refused", "reason": "local-prune takes no arguments"}
    try:
        return _run("prune", **opts)
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        said = getattr(e, "stderr", None) or ""
        why = said if said else (util.node_error(e, ["python3", "local_settings.py", "prune"]) if isinstance(e, (subprocess.SubprocessError, OSError)) else str(e))
        return {"status": "failed", "reason": gzmsg.js_trim(why).split("\n")[-1][:200]}
