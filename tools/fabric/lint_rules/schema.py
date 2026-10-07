"""tools/fabric/lint_rules/schema.py — the JSON rules: the schema validator, the pins, settings and model profile checks, and the schema and JSON loaders.
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import importlib.util
import json
import os
import re
from typing import Any

from .base import _tracked


def validate_json(schema: dict[str, Any], doc: Any, where: str) -> list[str]:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return _structural_check(schema, doc, where)
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{where}: {'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
        for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    ]


def _json_equal(a: Any, b: Any) -> bool:
    """JSON Schema's equality: a boolean is never a number (Python's
    True == 1 is not JSON's), and 1 equals 1.0; containers compare by it
    recursively."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def _json_type(doc: Any, t: str) -> bool:
    """Is `doc` of JSON Schema type `t`: a boolean is not an integer or a
    number, and 1.0 is an integer."""
    if t == "boolean":
        return isinstance(doc, bool)
    if t == "integer":
        return not isinstance(doc, bool) and (isinstance(doc, int) or (isinstance(doc, float) and doc.is_integer()))
    if t == "number":
        return not isinstance(doc, bool) and isinstance(doc, (int, float))
    return isinstance(doc, {"object": dict, "array": list, "string": str, "null": type(None)}.get(t, object))


def _structural_check(schema: dict[str, Any], doc: Any, where: str, path: str = "",
                      root: dict[str, Any] | None = None) -> list[str]:
    """The no-dependency validator, and on the fleet's pinned interpreter
    (standard library only, ADR-040) the only one: type, required,
    properties, patternProperties, additionalProperties, propertyNames,
    minProperties, items, minItems, maxItems, uniqueItems, enum, const,
    pattern, minLength, maxLength, minimum, maximum, and the composition
    the schemas here use — local `$ref` (#/$defs/…), `allOf`, `oneOf` and
    `if`/`then`/`else`. SCHEMA_KEYWORDS lists them, and schema_keyword_findings
    refuses a schema that uses any other: a keyword this cannot check
    would pass unchecked wherever jsonschema is absent (two lint cases did,
    on the pinned 3.13, 2026-10-01)."""
    root = root if root is not None else schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/"):
            target: Any = root
            for part in ref[2:].split("/"):
                target = target.get(part, {}) if isinstance(target, dict) else {}
            merged = {k: v for k, v in schema.items() if k != "$ref"}
            problems = _structural_check(target, doc, where, path, root)
            return problems + (_structural_check(merged, doc, where, path, root) if merged else [])
    if "allOf" in schema:
        problems: list[str] = []
        for sub in schema["allOf"]:
            problems += _structural_check(sub, doc, where, path, root)
        rest = {k: v for k, v in schema.items() if k != "allOf"}
        return problems + (_structural_check(rest, doc, where, path, root) if rest else [])
    if "if" in schema:
        # Draft 2020-12: `then` applies when `if` validates, `else` when not.
        branch = schema.get("then") if not _structural_check(schema["if"], doc, where, path, root) else schema.get("else")
        problems = _structural_check(branch, doc, where, path, root) if isinstance(branch, dict) else []
        rest = {k: v for k, v in schema.items() if k not in ("if", "then", "else")}
        return problems + (_structural_check(rest, doc, where, path, root) if rest else [])
    if "oneOf" in schema:
        matched = sum(1 for sub in schema["oneOf"] if not _structural_check(sub, doc, where, path, root))
        problems = [] if matched == 1 else [f"{where}{path}: matches {matched} of its oneOf schemas, not exactly one"]
        rest = {k: v for k, v in schema.items() if k != "oneOf"}
        return problems + (_structural_check(rest, doc, where, path, root) if rest else [])
    """Enough of JSON Schema to be useful without the dependency."""
    problems: list[str] = []
    expected = schema.get("type")
    if expected:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_json_type(doc, t) for t in types):
            return [f"{where}{path}: expected {expected}"]
    if isinstance(doc, dict):
        for key in schema.get("required", []):
            if key not in doc:
                problems.append(f"{where}{path}: missing required '{key}'")
        props = schema.get("properties", {})
        pattern_props = schema.get("patternProperties", {})
        if "minProperties" in schema and len(doc) < schema["minProperties"]:
            problems.append(f"{where}{path}: fewer than {schema['minProperties']} properties")
        names = schema.get("propertyNames")
        if isinstance(names, dict):
            for key in doc:
                problems += _structural_check(names, key, where, f"{path}/<{key}>", root)
        # Draft 2020-12 applies every matching pattern's schema, to a key
        # `properties` also names as much as to any other.
        for pat, sub in pattern_props.items():
            for key, value in doc.items():
                if re.search(pat, key):
                    problems += _structural_check(sub, value, where, f"{path}/{key}", root)
        if schema.get("additionalProperties") is False:
            for key in doc:
                if key in props:
                    continue
                if any(re.search(p, key) for p in pattern_props):
                    continue
                problems.append(f"{where}{path}: unexpected property '{key}'")
        for key, sub in props.items():
            if key in doc:
                problems += _structural_check(sub, doc[key], where, f"{path}/{key}", root)
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            for key, value in doc.items():
                if key not in props and not any(re.search(p, key) for p in pattern_props):
                    problems += _structural_check(extra, value, where, f"{path}/{key}", root)
    if isinstance(doc, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, value in enumerate(doc):
                problems += _structural_check(items, value, where, f"{path}[{i}]", root)
        if "minItems" in schema and len(doc) < schema["minItems"]:
            problems.append(f"{where}{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(doc) > schema["maxItems"]:
            problems.append(f"{where}{path}: more than {schema['maxItems']} items")
        if schema.get("uniqueItems") and any(_json_equal(doc[i], doc[j])
                                             for i in range(len(doc)) for j in range(i + 1, len(doc))):
            problems.append(f"{where}{path}: duplicate items")
    if isinstance(doc, str):
        if "minLength" in schema and len(doc) < schema["minLength"]:
            problems.append(f"{where}{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(doc) > schema["maxLength"]:
            problems.append(f"{where}{path}: longer than {schema['maxLength']} characters")
    # bool is an int in Python and never a number in JSON Schema.
    if isinstance(doc, (int, float)) and not isinstance(doc, bool):
        if "minimum" in schema and doc < schema["minimum"]:
            problems.append(f"{where}{path}: {doc} is below the minimum {schema['minimum']}")
        if "maximum" in schema and doc > schema["maximum"]:
            problems.append(f"{where}{path}: {doc} is above the maximum {schema['maximum']}")
    if "const" in schema and not _json_equal(doc, schema["const"]):
        problems.append(f"{where}{path}: {doc!r} is not {schema['const']!r}")
    if "enum" in schema and not any(_json_equal(doc, v) for v in schema["enum"]):
        problems.append(f"{where}{path}: {doc!r} not in {schema['enum']}")
    if "pattern" in schema and isinstance(doc, str) and not re.search(schema["pattern"], doc):
        problems.append(f"{where}{path}: {doc!r} does not match {schema['pattern']}")
    return problems


SCHEMA_KEYWORDS = {
    "$schema", "$id", "$ref", "$defs", "$comment", "title", "description", "examples", "default",
    "type", "required", "properties", "patternProperties", "additionalProperties", "propertyNames",
    "minProperties", "items", "minItems", "maxItems", "uniqueItems", "enum", "const", "pattern",
    "minLength", "maxLength", "minimum", "maximum", "allOf", "oneOf", "if", "then", "else",
}


# Keywords whose value maps NAMES to schemas: the names are not keywords.
_SCHEMA_MAPS = ("properties", "patternProperties", "$defs")


def python_pin_findings(root: str) -> list[str]:
    """runtime/python.json (ADR-040): a version, a release, and per machine
    an https URL and a 64-hex sha256 — the installer downloads nothing it
    cannot check. CI's matrix carries the pinned minor version, so what the
    hosts run is what CI runs the Python suites on."""
    path = os.path.join(root, "runtime", "python.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        # python_pin.py and fabric-status read it: without it there is no pin.
        return (["runtime/python.json: missing, and tools/fabric/python_pin.py installs from it"]
                if os.path.exists(os.path.join(root, "tools", "fabric", "python_pin.py")) else [])
    except ValueError as e:
        return [f"runtime/python.json: not JSON ({e})"]
    findings = []
    version = doc.get("python")
    if not (isinstance(version, str) and re.fullmatch(r"3\.\d+\.\d+", version)):
        findings.append(f"runtime/python.json: python {version!r} is not a 3.x.y version")
    if not (isinstance(doc.get("release"), str) and doc["release"]):
        findings.append("runtime/python.json: no release")
    builds = doc.get("builds")
    if not (isinstance(builds, dict) and builds):
        findings.append("runtime/python.json: no builds")
        builds = {}
    for arch, b in builds.items():
        if not (isinstance(b, dict) and isinstance(b.get("url"), str) and b["url"].startswith("https://")):
            findings.append(f"runtime/python.json: {arch}: the url must be https")
        if not (isinstance(b, dict) and isinstance(b.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", b["sha256"])):
            findings.append(f"runtime/python.json: {arch}: the sha256 must be 64 hex digits")
        elif isinstance(version, str) and isinstance(b.get("url"), str) \
                and not any(f"cpython-{version}{sep}" in b["url"] for sep in ("+", "%2B")):
            findings.append(f"runtime/python.json: {arch}: the url does not name Python {version}")
    if isinstance(version, str) and re.fullmatch(r"3\.\d+\.\d+", version):
        minor = ".".join(version.split(".")[:2])
        try:
            with open(os.path.join(root, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
                ci = fh.read()
        except OSError:
            ci = None
        if ci is not None and f"python: '{minor}'" not in ci:
            findings.append(f".github/workflows/ci.yml: no matrix leg on Python {minor}, the pinned version "
                            "(runtime/python.json)")
    return findings


def fabric_settings_findings(root: str) -> list[str]:
    """agent-fabric's own .claude/settings.json is the workspace template
    rendered with the fabric at $CLAUDE_PROJECT_DIR (fabric_settings.py):
    a session started inside this clone gets the workspace's hooks and
    status line, never a second list that drifts."""
    if not os.path.isfile(os.path.join(root, "runtime", "claude-code", "workspace", "settings.json")):
        return []
    spec = importlib.util.spec_from_file_location(
        "fabric_settings_under_lint", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fabric_settings.py"))
    fs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fs)
    try:
        have = open(os.path.join(root, ".claude", "settings.json"), encoding="utf-8").read()
    except OSError:
        have = None
    if have != fs.render(root):
        return [".claude/settings.json: not runtime/claude-code/workspace/settings.json rendered with $CLAUDE_PROJECT_DIR "
                "— python3 tools/fabric/fabric_settings.py --write"]
    return []


def schema_keyword_findings(root: str) -> list[str]:
    """Every tracked *.schema.json uses only keywords _structural_check
    checks: on the pinned interpreter there is no jsonschema to fall back
    on, and an unknown keyword would pass silently there."""
    findings = []

    def walk(node: Any, rel: str, at: str) -> None:
        if isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, rel, f"{at}[{i}]")
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key not in SCHEMA_KEYWORDS:
                findings.append(f"{rel}: {at or '<root>'}: keyword {key!r} is not checked without jsonschema "
                                "(lint.py SCHEMA_KEYWORDS); add it to _structural_check or do without it")
            if key in _SCHEMA_MAPS and isinstance(value, dict):
                for name, sub in value.items():
                    walk(sub, rel, f"{at}/{key}/{name}")
            elif key in ("items", "additionalProperties", "propertyNames", "if", "then", "else"):
                walk(value, rel, f"{at}/{key}")
            elif key in ("allOf", "oneOf"):
                walk(value, rel, f"{at}/{key}")

    for rel in _tracked(root):
        if rel.endswith(".schema.json"):
            try:
                with open(os.path.join(root, rel), encoding="utf-8") as fh:
                    walk(json.load(fh), rel, "")
            except (OSError, ValueError) as e:
                findings.append(f"{rel}: unreadable ({e})")
    return findings


def model_profile_findings(root: str, doc: dict[str, Any], known_roles: set[str]) -> list[str]:
    """Invariants the schema cannot express for routing/profiles.json.

    The file is layered — defaults <- roles.<role> <- agents.<login> — over
    routing/capabilities.json, and the launcher resolves each capability
    by merging the layers. So the review gate is on the MERGED review
    model of every row, not on each layer's own value: a row that sets no
    review model inherits the provider's and is fine; one that sets a
    cheaper model is the defect this exists to catch, because a review's
    failure mode is a green PR that merges. Role rows must name roles the
    catalogue knows; agent rows are keyed by login, never by a directory.
    The rest of the routing consistency — classes, providers, shims,
    aliases, the declared review id — is tools/fabric/routing.py's check().
    """
    findings: list[str] = []
    where = "routing/profiles.json"
    routing_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "routing.py")
    spec = importlib.util.spec_from_file_location("fabric_routing", routing_path)
    routing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routing)
    findings += [f"routing: {f}" for f in routing.check(root)]
    grade = routing.load_review_grade(root)
    gated = grade.get("capability", "code-review")
    try:
        routing.load_capabilities(root)
    except (OSError, KeyError, ValueError):
        return findings
    rows = [("defaults", None, None)]
    rows += [("roles", name, None) for name in (doc.get("roles") or {})]
    rows += [("agents", None, name) for name in (doc.get("agents") or {})]
    for layer, role, agent in rows:
        label = layer if layer == "defaults" else f"{layer}.{role or agent}"
        for provider in routing.PROVIDERS:
            try:
                model = routing.resolve(gated, provider, role, agent, None, root)["model"]
            except (KeyError, ValueError) as exc:
                findings.append(f"{where}: {label} on {provider}: {exc}")
                continue
            if not routing.ADAPTERS[provider].is_model(model):
                continue  # an alias is the harness's choice, ungated
            if not routing.review_grade_ok(model, root):
                findings.append(f"{where}: {label} resolves {gated} on {provider} to {model!r}, which is not in "
                                "routing/policies/review-grade.json; the review class would run on it")
    # The bottom layer must give every provider a session: the launcher
    # refuses a path with none rather than guess one.
    for provider in routing.PROVIDERS:
        try:
            routing.resolve_session(root=root, provider=provider)
        except (KeyError, ValueError) as exc:
            findings.append(f"{where}: defaults name no session for {provider}: {exc}")
    if known_roles:
        for name in (doc.get("roles") or {}):
            if name not in known_roles:
                findings.append(f"{where}: roles.{name} is not a role in identities/roles/catalog.json")
    for name in (doc.get("agents") or {}):
        if "/" in name or name.startswith("clone-"):
            findings.append(f"{where}: agents.{name} is not a Linux login")
    return findings


def load_schema(root: str, subdir: str, name: str) -> dict[str, Any] | None:
    path = os.path.join(root, subdir, f"{name}.schema.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_json(path: str, where: str, findings: list[str]) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as exc:
        findings.append(f"{where}: not valid JSON ({exc})")
        return None
