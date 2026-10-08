"""Where this runtime's agent-fabric checkout is, and where GZCoord's own
files ship. paths.mjs's counterpart: a module of its own so i18n and gzmsg
can both read it without importing each other (the validator's
diagnostics are dictionary lines)."""
from __future__ import annotations

import os
import sys

# tools/fabric/gzcoord/ -> the checkout. Real paths: the commands are links
# in ~/.local/bin, and a link's directory is not the checkout's.
_HERE = os.path.dirname(os.path.realpath(__file__))
CHECKOUT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
# What ships WITH the tools — the default dictionary, the scripts' paths —
# is found from the code, never from AGENT_FABRIC_ROOT.
GZCOORD_DIR = os.path.join(CHECKOUT, "communication", "gzcoord")

sys.path.insert(0, os.path.dirname(_HERE))
import roots  # noqa: E402


def fabric_root() -> str:
    """AGENT_FABRIC_ROOT when set (a test, a fixture, a session that
    exported it), else the checkout this code is in — the engine's tree.
    The roles, the catalogue and the projects' integrations are read under
    operator_root(). Set but
    empty is set, as `??` read it in paths.mjs: the port keeps what the
    Node did, and an empty root names nothing found."""
    return roots.engine_root(empty_is_set=True)


def operator_root() -> str:
    """Where the roles, the catalogue and the projects' integrations are
    read under: AGENT_FABRIC_OPERATOR when exported, else fabric_root()."""
    return roots.operator_root(empty_is_set=True)


def identity():
    """runtime/identity.py of the checkout this code is in: the one source
    of the agent's state directory, its lock and its atomic write
    (ADR-003), loaded when a caller first writes state."""
    runtime = os.path.join(CHECKOUT, "runtime")
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    import identity as module  # noqa: E402 — runtime/, found by its path
    return module
