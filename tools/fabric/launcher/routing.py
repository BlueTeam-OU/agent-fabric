"""tools/fabric/launcher/routing.py — the class routed to a model, the broker's environment and authentication, the effort.
A part of tools/fabric/launch.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
import subprocess
import traceback
from urllib.parse import urlsplit
from fabric_launcher.base import _load, ORI_AUTH_TIMEOUT_S, BROKER_ENV, die, say


# ── resolve ─────────────────────────────────────────────────────────
class ResolveError(Exception):
    """What the bash's resolver heredoc said with sys.exit(<message>)."""


def load_routing(routing_path: str, fabric_root: str):
    """routing.py from the fabric being launched, imported as the bash's
    heredoc did with AGENT_FABRIC_ROOT set to it — routing reads its root
    once, at import — and without leaving that variable in the session's
    environment when the caller did not set it."""
    saved = os.environ.get("AGENT_FABRIC_ROOT")
    os.environ["AGENT_FABRIC_ROOT"] = fabric_root
    try:
        return _load("fabric_routing", routing_path)
    finally:
        if saved is None:
            os.environ.pop("AGENT_FABRIC_ROOT", None)
        else:
            os.environ["AGENT_FABRIC_ROOT"] = saved


def resolve(routing, aliases_path: str, local_path: str, role: str, agent: str, provider: str) -> dict:
    local = {}
    if os.path.exists(local_path):
        with open(local_path) as fh:
            local = json.load(fh)
        if not isinstance(local, dict):
            raise ResolveError("model-profile.local.json is %s, not an object" % type(local).__name__)
    with open(aliases_path) as fh:
        aliases = json.load(fh)
    # Every merged value must be a model reference in its provider's
    # vocabulary: the committed files are linted, the local layer is not, and
    # a null/number/""/prose there once passed the emptiness checks as the
    # string "None" and reached `--model`. normalize_layer names the field.
    try:
        routing.normalize_layer(local, "local")
        out = {"role": role, "agent": agent, "provider": provider, "exports": {}, "classes": {}, "files": {}}
        for klass in aliases["aliases"]:
            res = routing.resolve(klass, provider, role, agent, local)
            # via "harness" is the tier's alias, the harness's own choice; anything
            # pinned must be a model reference the provider's adapter accepts.
            if res["via"] != "harness" and not routing.ADAPTERS[provider].is_runtime(res["composite"]):
                raise ResolveError("resolved %s is %r, not a model reference the %s adapter accepts"
                                   % (klass, res["composite"], provider))
            out["classes"][klass] = res
            # A file-pinned class (the review class) is never exported: its
            # alias is also code-plan's, and through the export the reviewer
            # would follow code-plan (as it once followed code-high on opus).
            # Its model reaches its agent file — install-agent-files.sh, run
            # by launch() for this provider — and the dispatch guard drops the
            # dispatch's alias under a fabric launch so the file decides.
            if res["via"] == "file":
                out["files"][klass] = res["composite"]
        # Every other class rides its alias's ANTHROPIC_DEFAULT_*_MODEL: on
        # the broker the composite, on plain claude the native pin (a class
        # the column leaves null is the harness's and exports nothing).
        for var, entry in routing.exports(provider, role, agent, local).items():
            out["exports"][var] = entry["model"]
        session = routing.resolve_session(role, agent, local, provider=provider)
    except (KeyError, ValueError) as exc:
        raise ResolveError("merged profile: %s" % exc) from None
    out["session"] = session
    grade = routing.load_review_grade()
    review = out["classes"].get(grade.get("capability", "code-review"))
    if review and not routing.review_grade_ok(review["model"]):
        out["review_violation"] = review["model"]
    # Through JSON and back, as the bash's resolution reached every later
    # step: what the report prints is the serialised value, never a tuple.
    return json.loads(json.dumps(out))


def resolve_or_die(*a) -> dict:
    try:
        return resolve(*a)
    except ResolveError as exc:
        say(str(exc))
    except Exception:
        traceback.print_exc()
    die("could not resolve the profile (see the message above).")


def is_broker_url(url: str) -> bool:
    try:
        h = urlsplit(url).hostname or ""
    except ValueError:
        h = ""
    return h == "openrouter.ai" or h.endswith(".openrouter.ai")


# PLAIN CLAUDE MEANS ANTHROPIC DIRECT, and it carries nothing the broker
# set for its own model. `ori claude` builds its child's environment in one
# function (read out of the ori binary, `rIa`), and a launch started from
# inside such a session inherits all of it:
#   pointing and credentials, forced: ANTHROPIC_BASE_URL=https://openrouter.ai/api,
#     ANTHROPIC_AUTH_TOKEN="" (present, EMPTY), ANTHROPIC_API_KEY=<the account's
#     OpenRouter key>, OPENROUTER_API_KEY=<the same key>, ANTHROPIC_MODEL=<its
#     model>, and sometimes ANTHROPIC_CUSTOM_HEADERS;
#   tuning for the BROKER'S model: CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT=1,
#     CLAUDE_CODE_MAX_CONTEXT_TOKENS, CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY,
#     CLAUDE_CODE_SKIP_FAST_MODE_ORG_CHECK, ENABLE_TOOL_SEARCH;
#   privacy opt-outs: DISABLE_TELEMETRY=1, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1,
#     DISABLE_GROWTHBOOK, CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF;
#   and more this was NOT enumerated for: a helper (`tIa`) and two computed
#     names. Nothing below claims to clear "everything ori set".
#
# History, because the next change here must not repeat it (review of #31,
# three rounds). Nothing cleared: the child ran and billed on the broker
# while stamped "anthropic". Then the URL alone: the key stayed, and the
# child would have sent the account's OpenRouter SECRET to
# api.anthropic.com. Then the credentials: the broker's system-prompt and
# context-cap tuning still followed onto an Anthropic session.
#
# So, when the base URL names OpenRouter (the host test model-audit.sh
# classifies a session by), the pointing, the credentials and the model
# tuning go. The privacy opt-outs STAY: clearing them could switch
# telemetry back on against a person's own choice, and leaving them costs
# nothing. OPENROUTER_API_KEY is not this function's: settle_secrets
# keeps it on the broker path, from the file, and drops it on this one. A base URL naming anything else is someone's
# deliberate choice, unreviewed, and is left exactly as it was. What is
# dropped is said once on stderr — names, never values.
def drop_broker_env() -> None:
    env = os.environ
    dropped = []
    if env.get("ANTHROPIC_BASE_URL") and is_broker_url(env["ANTHROPIC_BASE_URL"]):
        for v in BROKER_ENV:
            if v in env:
                dropped.append(v)
                del env[v]
    # And the SECRET, independently of the base URL: an ANTHROPIC_API_KEY that
    # is the OpenRouter key — equal to OPENROUTER_API_KEY, or shaped like one
    # (sk-or-) — is never an Anthropic credential, whatever else the
    # environment says, so it never reaches a plain-claude child. Precise on
    # purpose: a real Anthropic key (sk-ant-) is not touched.
    key = env.get("ANTHROPIC_API_KEY", "")
    if key and (key.startswith("sk-or-") or (env.get("OPENROUTER_API_KEY") and key == env["OPENROUTER_API_KEY"])):
        dropped.append("ANTHROPIC_API_KEY")
        del env["ANTHROPIC_API_KEY"]
    if dropped:
        say("launch: plain claude goes to Anthropic direct — dropped what a broker session left in this "
            "environment: " + " ".join(dropped))


# ── the pins ─────────────────────────────────────────────────────────
# Every alias variable starts EMPTY, then only the resolved ones are set.
# A class whose column is null rides the harness's own tier, which means
# NO export — and a launch started from inside another fabric session
# arrived carrying that session's export for the alias, silently pinning
# the tier to the parent's model (review of #31). The four names are the
# adapter's (runtime/claude-code/aliases.json), read, never repeated here.
def set_pins(aliases_path: str, exports: dict) -> None:
    with open(aliases_path) as fh:
        for name in json.load(fh)["env"].values():
            if name:
                os.environ.pop(name, None)
    for name, value in sorted(exports.items()):
        if name:
            os.environ[name] = value


# Auth: ori must be working from the environment BEFORE we exec, because a
# prompt at this point would come after we already exported the pins.
# The check is a CONJUNCTION on the documented shape — {"ok":true,"data":
# {"authenticated":true,"source":{"kind":"environment",...}}} — and keeps
# ori's exit status. Plain claude carries its own login; nothing to check.
def ori_auth_ok(text: str) -> bool:
    try:
        d = json.loads(text or "{}")
    except Exception:
        return False
    if not isinstance(d, dict):
        return False
    data = d.get("data") if isinstance(d.get("data"), dict) else d
    src = data.get("source") if isinstance(data.get("source"), dict) else {}
    return data.get("authenticated") is True and src.get("kind") == "environment"


def check_ori_auth() -> None:
    try:
        r = subprocess.run(["ori", "auth", "--json"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True, errors="surrogateescape",
                           timeout=ORI_AUTH_TIMEOUT_S)
        rc, text = r.returncode, r.stdout
    except subprocess.TimeoutExpired:
        rc, text = 124, ""
    except OSError:
        rc, text = 127, ""
    if rc != 0 or not ori_auth_ok(text):
        die(f"ori is not authenticated from the environment (ori auth exit {rc}). This account needs "
            "OPENROUTER_API_KEY in ~/.config/agent-fabric/secrets.env (fabric-secrets sync), which the launcher "
            "hands to ori "
            "— a stored `ori login` credential is deliberately not accepted, because per-agent spend follows "
            "the key (ori auth --json to inspect).")


def caller_value(args: list[str], flag: str) -> tuple[str | None, bool, bool]:
    """What the caller passed for `flag` (spaced or `=`), whether they
    passed it at all, and whether the last argument is the bare flag."""
    value, given, prev = None, False, ""
    for arg in args:
        if prev == flag:
            value, given = arg, True
        if arg.startswith(flag + "="):
            value, given = arg[len(flag) + 1:], True
        prev = arg
    trailing = prev == flag
    return value, given or trailing, trailing


def effort_for(args: list[str], routed: str) -> tuple[str, bool]:
    """The session's effort and whether the caller decided it: the caller's
    own --effort wins over the routed level."""
    value, given, trailing = caller_value(args, "--effort")
    if trailing:
        # A TRAILING `--effort` with no value never entered the scan as a value,
        # so the launcher appended its own and the child saw
        # `--effort --effort <level>` — claude would read "--effort" as the level.
        # The caller meant to pass one; let their (malformed) flag stand and let
        # claude report it, rather than adding a second — and stamp nothing.
        return "", True
    return (value if value is not None else routed), given
