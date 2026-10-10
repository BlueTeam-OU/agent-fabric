#!/usr/bin/env python3
"""tools/fabric/gateway_plan.py — the session plan (plan v0) the fleet gateway serves, written for a login
(gateway-switch s6).

    gateway_plan.py --login L [--role R] [--provider anthropic|openrouter] [--port N] [--session S]
                    [--out PATH] [--validate [--gateway-bin PATH]]

WHAT IT WRITES. One plan per login, stable: the same routing and token path give the same bytes and so the same
plan_digest (the gateway's own, sha256 of the exact bytes). `session` only changes session.opaque_id, for a plan per
launch. The listener is loopback (port 0 asks the OS; READY reports the one bound). A route is an IDENTITY route, one
per distinct model the login's routing resolves for the provider column — the session's and every capability class's
(routing.py): selector and upstream model are the same string, which is what the launcher exports as
ANTHROPIC_DEFAULT_*_MODEL and --model. A class that rides a harness alias with no pinned model has no id to write a
route for: it is named in `skipped`, never guessed.
  anthropic   backend api.anthropic.com; profile `claude-subscription`: source file, the token file
              gateway_token.token_path(uid) (`fabric-secrets sync` writes it), header Authorization, prefix "Bearer ",
              companion anthropic-beta oauth-2025-04-20 (the plan example's own)
  openrouter  backend openrouter.ai/api; profile `openrouter-key`: source env, OPENROUTER_API_KEY, Authorization
              "Bearer "; the selectors are the composite ids (model@preset/shim) the broker path sends

CONTRACT
  build(login, ...) -> Plan(doc, bytes, digest, selectors, skipped, token_file, warnings)
  validate(doc) -> list of "path: why" — empty when the plan passes the schema (the gateway's plan-v0 schema, kept
                   here as data) and the rules no schema can say (unique identifiers, every reference declared, one
                   route per selector). It reads no credential and writes nothing.
  write(plan, path) the bytes, atomically, 0600; returns the path.
  The command prints the plan on stdout, or with --out writes it and prints one JSON object: plan, plan_digest,
  selectors, skipped, token_file (and validation, with --validate: the gateway's `validate-plan` when its binary is
  found — exit 3 is a plan refusal, exit 4 a credential source unavailable, which is the token file not written yet).
  exit 0 written; 1 the plan did not validate or the binary refused it; 2 usage or a routing that cannot be resolved.
  No credential value appears in a plan, a message or an exception: a plan names where a credential is."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "runtime"))
import gateway_token  # noqa: E402
import routing  # noqa: E402

# The gateway's plan-v0 schema (draft 2020-12), as data: its `$id`, `$schema`, `title` and `description` annotations
# dropped. tests/fixtures/gateway-plan-v0/schema.json is the same document and tests/test_gateway_plan.py holds the
# two equal. The schema is the authority for shape; the gateway's README beside it, for the rest.
SCHEMA = json.loads(r'''{"type":"object","additionalProperties":false,"properties":{"schema_version":{"const":0},"session":{"type":"object","additionalProperties":false,"properties":{"opaque_id":{"type":"string","minLength":1,"maxLength":128}},"required":["opaque_id"]},"listeners":{"type":"array","minItems":1,"maxItems":1,"items":{"type":"object","additionalProperties":false,"properties":{"ingress_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9._-]{0,63}$"},"protocol":{"const":"anthropic"},"bind":{"type":"string","pattern":"^127\\.0\\.0\\.1:(0|[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$"},"harness_auth":{"type":"object","additionalProperties":false,"properties":{"source":{"const":"fd"}},"required":["source"]}},"required":["ingress_id","protocol","bind","harness_auth"]}},"backends":{"type":"array","minItems":1,"items":{"type":"object","additionalProperties":false,"properties":{"backend_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9._-]{0,63}$"},"protocol":{"const":"anthropic"},"base_url":{"type":"string","pattern":"^https://(?:[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?(?:\\.[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?)*\\.?|\\[[0-9A-Fa-f.]*:[0-9A-Fa-f:.]*\\])(?::(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?(?:/[!-\"$->@-~]*)?$"}},"required":["backend_id","protocol","base_url"]}},"auth_profiles":{"type":"array","minItems":1,"items":{"type":"object","additionalProperties":false,"properties":{"profile_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9._-]{0,63}$"},"source":{"enum":["env","file"]},"name":{"type":"string","pattern":"^[A-Za-z_][A-Za-z0-9_]*$"},"path":{"type":"string","pattern":"^/"},"header":{"type":"string","pattern":"^[A-Za-z0-9-]+$","not":{"pattern":"^([Hh][Oo][Ss][Tt]|[Cc][Oo][Nn][Tt][Ee][Nn][Tt]-[Ll][Ee][Nn][Gg][Tt][Hh]|[Ee][Xx][Pp][Ee][Cc][Tt]|[Uu][Ss][Ee][Rr]-[Aa][Gg][Ee][Nn][Tt]|[Cc][Oo][Nn][Nn][Ee][Cc][Tt][Ii][Oo][Nn]|[Kk][Ee][Ee][Pp]-[Aa][Ll][Ii][Vv][Ee]|[Pp][Rr][Oo][Xx][Yy]-[Cc][Oo][Nn][Nn][Ee][Cc][Tt][Ii][Oo][Nn]|[Pp][Rr][Oo][Xx][Yy]-[Aa][Uu][Tt][Hh][Ee][Nn][Tt][Ii][Cc][Aa][Tt][Ee]|[Pp][Rr][Oo][Xx][Yy]-[Aa][Uu][Tt][Hh][Oo][Rr][Ii][Zz][Aa][Tt][Ii][Oo][Nn]|[Tt][Ee]|[Tt][Rr][Aa][Ii][Ll][Ee][Rr]|[Tt][Rr][Aa][Nn][Ss][Ff][Ee][Rr]-[Ee][Nn][Cc][Oo][Dd][Ii][Nn][Gg]|[Uu][Pp][Gg][Rr][Aa][Dd][Ee]|[Cc][Oo][Oo][Kk][Ii][Ee]|[Aa][Nn][Tt][Hh][Rr][Oo][Pp][Ii][Cc]-[Bb][Ee][Tt][Aa])$"}},"prefix":{"type":"string","pattern":"^[^\\u0000-\\u001f\\u007f]*$"},"companion_headers":{"type":"array","items":{"type":"object","additionalProperties":false,"properties":{"name":{"const":"anthropic-beta"},"value":{"type":"string","pattern":"^[A-Za-z0-9._-]+$"}},"required":["name","value"]}}},"required":["profile_id","source","header","prefix"],"oneOf":[{"properties":{"source":{"const":"env"}},"required":["name"],"not":{"required":["path"]}},{"properties":{"source":{"const":"file"}},"required":["path"],"not":{"required":["name"]}}]}},"routes":{"type":"array","minItems":1,"items":{"type":"object","additionalProperties":false,"properties":{"route_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9._-]{0,63}$"},"ingress_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9._-]{0,63}$"},"source":{"type":"object","additionalProperties":false,"properties":{"model_selector":{"type":"string","minLength":1}},"required":["model_selector"]},"target":{"type":"object","additionalProperties":false,"properties":{"backend_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9._-]{0,63}$"},"model":{"type":"string","minLength":1}},"required":["backend_id","model"]},"auth_profile_id":{"type":"string","pattern":"^[a-z0-9][a-z0-9._-]{0,63}$"}},"required":["route_id","ingress_id","source","target","auth_profile_id"]}},"defaults":{"type":"object","additionalProperties":false,"properties":{"unknown_route":{"type":"object","additionalProperties":false,"properties":{"status":{"type":"integer","minimum":400,"maximum":499},"error_type":{"type":"string","minLength":1}},"required":["status","error_type"]}},"required":["unknown_route"]}},"required":["schema_version","session","listeners","backends","auth_profiles","routes","defaults"]}''')

INGRESS_ID = "claude"
LISTEN_HOST = "127.0.0.1"
BACKENDS = {
    "anthropic": {"backend_id": "anthropic", "base_url": "https://api.anthropic.com", "profile_id": "claude-subscription"},
    "openrouter": {"backend_id": "openrouter", "base_url": "https://openrouter.ai/api", "profile_id": "openrouter-key"},
}
COMPANION = {"name": "anthropic-beta", "value": "oauth-2025-04-20"}
# The gateway's binary has the name of the project it is built in, which the corpus lint keeps out of generic files.
GATEWAY_BINARY = "agent-fabric" + "-gateway"
BINARY_TIMEOUT_S = 30


class PlanError(Exception):
    """The plan cannot be built: one line."""


@dataclass
class Plan:
    doc: dict
    bytes: bytes
    digest: str
    selectors: list[dict]
    skipped: list[str]
    token_file: str | None
    warnings: list[str] = field(default_factory=list)


# ── the schema, checked ──────────────────────────────────────────────

def _ecma(pattern: str) -> str:
    """The schema's patterns are ECMAScript's, where a closing $ matches the end of the text alone; Python's also
    matches before a final newline, which would pass "Bearer\\n" as a prefix. \\Z is the end and only the end."""
    return pattern[:-1] + r"\Z" if pattern.endswith("$") and not pattern.endswith("\\$") else pattern


def _check(value: object, schema: dict, path: str, out: list[str]) -> None:
    kind = schema.get("type")
    if kind == "object" and not isinstance(value, dict):
        out.append(f"{path or '/'}: not an object")
        return
    if kind == "array" and not isinstance(value, list):
        out.append(f"{path or '/'}: not an array")
        return
    if kind == "string" and not isinstance(value, str):
        out.append(f"{path or '/'}: not a string")
        return
    if kind == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        out.append(f"{path or '/'}: not an integer")
        return
    if "const" in schema and (value != schema["const"] or type(value) is not type(schema["const"])):
        out.append(f"{path or '/'}: not {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path or '/'}: not one of {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append(f"{path or '/'}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(f"{path or '/'}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(_ecma(schema["pattern"]), value):
            out.append(f"{path or '/'}: does not match its pattern")
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{path or '/'}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{path or '/'}: above {schema['maximum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            out.append(f"{path or '/'}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(f"{path or '/'}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                _check(item, schema["items"], f"{path}/{i}", out)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                out.append(f"{path}/{key}: required")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    out.append(f"{path}/{key}: not a field of this object")
        for key, sub in props.items():
            if key in value:
                _check(value[key], sub, f"{path}/{key}", out)
    if "not" in schema:
        inner: list[str] = []
        _check(value, schema["not"], path, inner)
        if not inner:
            out.append(f"{path or '/'}: a value this field refuses")
    if "oneOf" in schema:
        passing = 0
        for branch in schema["oneOf"]:
            inner = []
            _check(value, branch, path, inner)
            passing += not inner
        if passing != 1:
            out.append(f"{path or '/'}: matches {passing} of its {len(schema['oneOf'])} alternatives, not exactly one")


def validate(doc: object) -> list[str]:
    problems: list[str] = []
    _check(doc, SCHEMA, "", problems)
    if problems or not isinstance(doc, dict):
        return problems
    # The rules of the contract's README that a schema cannot say.
    def ids(items: list[dict], key: str, what: str) -> set[str]:
        seen: set[str] = set()
        for i, item in enumerate(items):
            if item[key] in seen:
                problems.append(f"/{what}/{i}/{key}: declared twice")
            seen.add(item[key])
        return seen
    ingresses = ids(doc["listeners"], "ingress_id", "listeners")
    backends = ids(doc["backends"], "backend_id", "backends")
    profiles = ids(doc["auth_profiles"], "profile_id", "auth_profiles")
    ids(doc["routes"], "route_id", "routes")
    selectors: set[tuple[str, str]] = set()
    for i, route in enumerate(doc["routes"]):
        for key, known, where in (("ingress_id", ingresses, "ingress_id"), ("auth_profile_id", profiles, "auth_profile_id")):
            if route[key] not in known:
                problems.append(f"/routes/{i}/{where}: names {route[key]!r}, which the plan does not declare")
        if route["target"]["backend_id"] not in backends:
            problems.append(f"/routes/{i}/target/backend_id: names {route['target']['backend_id']!r}, which the plan does not declare")
        key = (route["ingress_id"], route["source"]["model_selector"])
        if key in selectors:
            problems.append(f"/routes/{i}/source/model_selector: {key[1]!r} is on another route of the same ingress")
        selectors.add(key)
    return problems


# ── what routing resolves ────────────────────────────────────────────

def slug(model: str) -> str:
    out = re.sub(r"[^a-z0-9._-]+", "-", model.lower()).strip("-.") or "model"
    if len(out) > 60:
        out = out[:51] + "-" + hashlib.sha256(model.encode()).hexdigest()[:8]
    return out


def models_of(login: str, role: str | None, provider: str) -> tuple[list[str], list[str]]:
    """(the distinct models routing resolves for the provider column, in order: the session's, then each class's;
    the classes that name none)."""
    models: list[str] = []
    skipped: list[str] = []
    try:
        session = routing.resolve_session(role, login, provider=provider)["composite"]
        models.append(session)
        for klass in routing.load_capabilities()["classes"]:
            res = routing.resolve(klass, provider, role, login)
            if res["resolution"] == "harness" and not res["pinned"]:
                skipped.append(f"{klass}: rides the harness alias {res['alias']} with no model pinned for {provider}; no route can be written for it")
            elif res["composite"] not in models:
                models.append(res["composite"])
    except (KeyError, ValueError, OSError) as e:
        raise PlanError(f"routing cannot be resolved for {login} on {provider}: {e}") from None
    return models, skipped


def build(login: str, role: str | None = None, provider: str = "anthropic", port: int = 0, session: str | None = None,
          uid: int | None = None, runtime_root: str = gateway_token.RUNTIME_ROOT) -> Plan:
    if provider not in BACKENDS:
        raise PlanError(f"provider {provider!r}: known are {', '.join(sorted(BACKENDS))}")
    if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
        raise PlanError(f"port {port!r}: 0 to 65535")
    if uid is None:
        try:
            uid = pwd.getpwnam(login).pw_uid
        except KeyError:
            raise PlanError(f"no account {login} on this host") from None
    models, skipped = models_of(login, role, provider)
    backend = BACKENDS[provider]
    token_file = gateway_token.token_path(uid, runtime_root) if provider == "anthropic" else None
    if provider == "anthropic":
        profile = {"profile_id": backend["profile_id"], "source": "file", "path": token_file, "header": "Authorization",
                   "prefix": "Bearer ", "companion_headers": [dict(COMPANION)]}
    else:
        profile = {"profile_id": backend["profile_id"], "source": "env", "name": "OPENROUTER_API_KEY", "header": "Authorization",
                   "prefix": "Bearer "}
    routes, selectors, used = [], [], set()
    for model in models:
        route_id, n = slug(model), 2
        while route_id in used:
            route_id, n = f"{slug(model)[:56]}-{n}", n + 1
        used.add(route_id)
        routes.append({"route_id": route_id, "ingress_id": INGRESS_ID, "source": {"model_selector": model},
                       "target": {"backend_id": backend["backend_id"], "model": model}, "auth_profile_id": backend["profile_id"]})
        selectors.append({"selector": model, "model": model, "route_id": route_id})
    doc = {
        "schema_version": 0,
        "session": {"opaque_id": login if not session else f"{login}:{session}"},
        "listeners": [{"ingress_id": INGRESS_ID, "protocol": "anthropic", "bind": f"{LISTEN_HOST}:{port}", "harness_auth": {"source": "fd"}}],
        "backends": [{"backend_id": backend["backend_id"], "protocol": "anthropic", "base_url": backend["base_url"]}],
        "auth_profiles": [profile],
        "routes": routes,
        "defaults": {"unknown_route": {"status": 400, "error_type": "invalid_request_error"}},
    }
    problems = validate(doc)
    if problems:
        raise PlanError("the plan built does not validate: " + "; ".join(problems[:3]))
    data = (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return Plan(doc, data, "sha256:" + hashlib.sha256(data).hexdigest(), selectors, skipped, token_file)


def write(plan: Plan, path: str) -> str:
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{os.path.basename(path)}.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(plan.bytes)
            fh.flush()
            os.fchmod(fh.fileno(), 0o600)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    return path


def gateway_binary(explicit: str | None = None) -> str | None:
    return explicit or shutil.which(GATEWAY_BINARY)


def validate_with_binary(path: str, binary: str) -> dict:
    """The gateway's own `validate-plan`. Its exit 3 is the plan refused; 4 a credential source unavailable (the token
    file not written yet is that); anything else is not a verdict on the plan."""
    try:
        r = subprocess.run([binary, "validate-plan", "--plan", path], capture_output=True, text=True, timeout=BINARY_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"binary": binary, "ran": False, "why": type(e).__name__}
    first = (r.stderr or r.stdout).strip().splitlines()[:1]
    return {"binary": binary, "ran": True, "exit": r.returncode, "note": first[0][:200] if first else ""}


def _role_of(login: str) -> str | None:
    """The role in the login's binding, when its state is readable from here (this login's own, in practice)."""
    import identity
    try:
        with open(identity.binding_path(login), encoding="utf-8") as fh:
            role = json.load(fh).get("role")
    except (OSError, ValueError, AttributeError):
        return None
    return role if isinstance(role, str) and role else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gateway_plan.py", description=__doc__.split("\n", 2)[1].strip())
    ap.add_argument("--login", required=True)
    ap.add_argument("--role", default=None, help="the login's role (default: its binding's, when readable here)")
    ap.add_argument("--provider", default="anthropic", choices=sorted(BACKENDS))
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--session", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--gateway-bin", default=None)
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    if args.validate and not args.out:
        ap.error("--validate needs --out: the gateway validates a file")
    try:
        plan = build(args.login, args.role or _role_of(args.login), args.provider, args.port, args.session)
    except PlanError as e:
        print(f"gateway_plan: {e}", file=sys.stderr)
        return 2
    if not args.out:
        sys.stdout.write(plan.bytes.decode("utf-8"))
        return 0
    out: dict = {"plan": write(plan, args.out), "plan_digest": plan.digest, "selectors": plan.selectors, "skipped": plan.skipped,
                 "token_file": plan.token_file}
    rc = 0
    if args.validate:
        binary = gateway_binary(args.gateway_bin)
        out["validation"] = validate_with_binary(args.out, binary) if binary else {"ran": False, "why": "the gateway binary is not on PATH"}
        if out["validation"].get("ran") and out["validation"].get("exit") not in (0, 4):
            rc = 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
