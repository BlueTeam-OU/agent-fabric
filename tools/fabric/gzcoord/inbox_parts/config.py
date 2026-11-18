"""tools/fabric/gzcoord/inbox_parts/config.py — the project's integration: the relay, the channel, the inbox's root.
A part of tools/fabric/gzcoord/inbox.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any
from .. import i18n
from .. import paths
import roots  # noqa: E402
from ..gzmsg import en
from ..carrier import CARRIER_NAME


# ── the project's integration ────────────────────────────────────────

def workspace() -> str:
    """The projects/ directory the fabric checkout sits in: where the relay's
    database, token and venv live — host state, never inside a repository."""
    return os.path.dirname(paths.fabric_root())


def relay_runtime_dir(cfg: dict, ws: str | None = None) -> str:
    v = cfg.get("relay_runtime_dir")
    return os.path.abspath(os.path.join(workspace() if ws is None else ws, ".gzcoord" if v is None else v))


def integration_config(project: str | None, env: dict | None = None, t: i18n.Printer | None = None) -> dict:
    """Which relay, which channel, where the token and the hosted relay's
    runtime live: from the PROJECT (projects/<id>/integration/gzcoord/
    config.json) or from the environment (CLAUDE_BRIDGE_URL and
    GZCOORD_CHANNEL together). Nothing else: until 2026-09-16 the defaults
    were one project's, and a working copy of any other silently joined
    that project's channel with its token file."""
    env = os.environ if env is None else env
    t = t or en()
    file = roots.project_integration(project, "gzcoord", "config.json", root=paths.operator_root()) if project else None
    if file:
        try:
            with open(file, encoding="utf-8") as fh:
                own = json.load(fh)
            if isinstance(own, dict) and own.get("relay_url") and own.get("channel"):
                return {"configured": True, "source": file, "relay_runtime_dir": ".gzcoord", **own,
                        "relay_url": env.get("CLAUDE_BRIDGE_URL", own["relay_url"]),
                        "channel": env.get("GZCOORD_CHANNEL", own["channel"])}
        except (OSError, ValueError):
            pass   # no file, or not JSON: the environment may still configure it
    if env.get("CLAUDE_BRIDGE_URL") and env.get("GZCOORD_CHANNEL"):
        return {"configured": True, "source": "environment", "relay_url": env["CLAUDE_BRIDGE_URL"],
                "channel": env["GZCOORD_CHANNEL"], "relay_runtime_dir": ".gzcoord"}
    where = f"projects/{project}/integration/gzcoord/config.json" if project else t("config.where-registered")
    what = t("config.for-project", {"project": project}) if project else t("config.for-working-copy")
    return {"configured": False, "source": None, "reason": t("config.not-configured", {"what": what, "where": where})}


# What a carrier-only command shows where the relay's channel was shown: the account has no channel there, and the relay's
# is not asked for (cutover W15, first part).
CARRIER_ONLY_CHANNEL = CARRIER_NAME


def carrier_only_config() -> dict:
    """The integration of an account in carrier-only: configured, with no relay URL, no channel of the relay's and no token
    file. It reads neither the project's config.json nor CLAUDE_BRIDGE_URL, GZCOORD_CHANNEL: a project with no relay section
    works here, and a relay setting that is present is not this mode's to honour. Nothing in a carrier-only path reaches for
    `relay_url` (open_transport builds no relay), so None there is a fault a test finds, not a default."""
    return {"configured": True, "source": None, "relay_url": None, "channel": CARRIER_ONLY_CHANNEL, "relay_runtime_dir": ".gzcoord"}


def resolve_integration(project: str | None, env: dict | None = None, t: i18n.Printer | None = None,
                        state_dir: str | None = None) -> tuple[dict, dict | None]:
    """(the integration this command runs on, the Mode it resolved or None). In carrier-only the carrier's; in the other two
    modes integration_config's, so a project with no relay section is refused there in its one line. A mode that cannot be
    resolved is None and the relay's integration: the failure is the transport's to say, where it always was, in its own line
    and exit code (open_transport reads the mode again and raises the same error). The one-command override is said here
    once, and the caller hands the Mode on so nothing reads or says it twice."""
    from ..transport import mode as transport_mode
    try:
        resolved = transport_mode.effective(state_dir, env, say=transport_mode.say_stderr)
    except transport_mode.ModeError:
        if (os.environ if env is None else env).get(transport_mode.ENV):
            raise      # the override is the command's own word and it is wrong: said first, not behind the config line
        return integration_config(project, env, t), None
    if resolved["mode"] == transport_mode.CARRIER_ONLY:
        return carrier_only_config(), resolved
    return integration_config(project, env, t), resolved


def default_relay() -> str:
    """Where a caller that names no relay posts (the Node read it once at
    import; a process reads it once either way)."""
    return os.environ.get("CLAUDE_BRIDGE_URL", "http://127.0.0.1:8765")


class ControlChannel(ValueError):
    pass


def assert_not_control_channel(channel: Any, t: i18n.Printer | None = None) -> None:
    """A channel ending in ":control" carries the fabric's machine records
    (runtime/control/), and no session may drain or send on it — a control
    record printed into a session's context is what the control plane
    exists to avoid, and GZCOORD_CHANNEL could otherwise name one
    (2026-09-17)."""
    t = t or en()
    if isinstance(channel, str) and channel.endswith(":control"):
        raise ControlChannel(t("config.control-channel", {"channel": channel}))


def git_toplevel() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def inbox_root(who: dict) -> str:
    """The working copy the token and integration are read from: the
    checkout this runs in; outside one (a session in the workspace), the
    binding's working copy — found live on architect-cto-01, 2026-09-14,
    when a workspace launch drained nothing; the cwd is the last resort."""
    top = git_toplevel()
    if top:
        return top
    if who.get("working_copy"):
        return who["working_copy"]
    if who.get("bound_working_copy") and os.path.exists(who["bound_working_copy"]):
        return who["bound_working_copy"]
    return os.getcwd()
