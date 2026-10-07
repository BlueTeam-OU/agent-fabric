#!/usr/bin/env python3
"""tools/fabric/routing.py — capability -> model + effort -> family shim.

Three independent dimensions, one derived artifact:

    CAPABILITY CLASS -> CONCRETE MODEL       routing/capabilities.json (+ profile layers)
    CAPABILITY CLASS -> REASONING EFFORT     routing/effort.json (+ profile layers)
    MODEL FAMILY     -> COMPATIBILITY SHIM   routing/shims.json
    model @ shim                             derived here, at runtime, never committed

The effort a class ASKS for is one vocabulary; what a given model will
actually be given is (intent, model) resolved through that provider's
adapter, and is computed here every time, never stored.

    routing.py resolve code-high                      # openrouter by default
    routing.py resolve code-high --provider anthropic
    routing.py table [--provider P]
    routing.py check                                  # validate the canonical files
    routing.py shim <model>                           # the family shim a bare model id needs, if any

    routing.py pins [--provider P] [--me]             # the file-pinned classes (the review class): <class> <alias> <model>
    routing.py efforts [--provider P] [--me]          # every class's level: <class> <level|-> <outcome>
    routing.py session-effort [--provider P] [--me]   # the session's level, or nothing

Profile layers (routing/profiles.json and the agent's local override) may
override a class's model and name the session's; the shim is looked up on
the MERGED model, so an override to another family gets that family's
shim, or none.

A LAYER IS PER PROVIDER. The two launch paths speak different vocabularies
(an OpenRouter id on the broker; a tier alias or a native `claude-…` id on
plain claude), so a layer names each provider's choices under
`providers.<provider>.{session, capabilities}`. The flat `session` and
`capabilities` a layer may also carry are the OpenRouter form — and a flat
`session` of `anthropic/<id>` serves plain claude too, as `<id>`. The
merge is per provider, per key, nearest layer wins:
defaults <- roles.<role> <- agents.<login> <- the agent's local override
($STATE_DIR/model-profile.local.json, written by bin/fabric-model).
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import sys
from typing import Any

FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

MODEL_ID = re.compile(r"^~?[a-z0-9-]+/[a-z0-9.-]+(:[a-z]+)?(\[1m\])?$")
# A harness model reference: a tier alias (`opus`, `fable`) — the only form
# the Agent tool's `model` field accepts.
HARNESS_REF = re.compile(r"^(haiku|sonnet|opus|fable)$")
# A native Anthropic model id, as `claude` itself names it: what the harness
# provider's column holds when the fabric decides a tier's model on the
# vanilla path rather than leaving it to the harness's own default.
NATIVE_ID = re.compile(r"^claude-[a-z0-9.-]+(\[1m\])?$")
PRESET = re.compile(r"^@preset/[a-z0-9-]+$")
COMPOSITE = re.compile(r"^~?[a-z0-9-]+/[a-z0-9.-]+(:[a-z]+)?(\[1m\])?(@preset/[a-z0-9-]+)?$")


class ProviderAdapter:
    """What a model reference looks like on one provider, in one place
    (review, 2026-09-16: before this the regexes were applied inline, per
    call site, and a provider's rule lived in whichever branch named it).
    normalize_layer, check and the launch's composite test all ask the
    adapter; a new provider is a new adapter, never a new branch."""
    name: str
    resolution: str            # "model-id": the column names a model; "harness": null means the harness's tier
    pattern: re.Pattern        # a capability model reference
    runtime: re.Pattern        # what the launcher may hand to --model (a composite on the broker)
    describe: str

    def is_model(self, value: Any) -> bool:
        return isinstance(value, str) and bool(self.pattern.fullmatch(value))

    def model(self, value: Any, where: str) -> str:
        if not self.is_model(value):
            raise ValueError(f"{where} is {value!r}, not {self.describe}")
        return value

    def session(self, value: Any, where: str, classes: set[str]) -> str:
        """A session names a class (that class's model here) or a model."""
        if isinstance(value, str) and value in classes:
            return value
        if not self.is_model(value):
            raise ValueError(f"{where} is {value!r}, neither a capability class ({', '.join(sorted(classes))}) "
                             f"nor {self.describe}")
        return value

    def is_runtime(self, value: str) -> bool:
        return bool(self.runtime.fullmatch(value))

    def column_findings(self, klass: str, model: Any, where: str) -> list[str]:
        """capabilities.json's column for this provider: one finding per
        malformed cell, in the provider's own words."""
        if model is None:
            return [] if self.resolution == "harness" else [f"{where}.{klass} is null; {self.name} resolves by model id"]
        if "@preset/" in str(model):
            return [f"{where}.{klass} {model!r} carries a preset; a preset is a shim (routing/shims.json), not a model"]
        if not self.is_model(model):
            return [f"{where}.{klass} {model!r} is not {self.describe}"]
        return []

    def openrouter_id(self, model: str) -> str:
        """The model as the broker names it, for policies written in
        OpenRouter ids (review-grade)."""
        return model

    # ── effort ──────────────────────────────────────────────────────
    # The level set is a property of the (provider, MODEL) pair, never of
    # the provider: OpenAI's own set moved three times across one model
    # family, and Haiku 4.5 rejects the parameter the rest of the Claude
    # line accepts. So an adapter answers "which levels?" only when told
    # which model. A table here goes stale the way a model id does — it is
    # declared, and a live read-back proves it (docs/live-checks/).
    effort_channel: str = "none"          # "agent-file" | "session" | "none"
    # (glob, levels the model DISTINGUISHES, the vendor's own remap of the
    # rest). First match wins. The remap matters as much as the set: a
    # vendor may map a level UP — GLM-5.2 documents low/medium -> high —
    # so a fabric that only ever clamps downward would ask for LESS
    # thinking than sending the level untouched. Found by running it.
    effort_by_model: tuple[tuple[str, tuple[str, ...], dict[str, str]], ...] = ()

    def effort_levels(self, model: str | None) -> tuple[str, ...] | None:
        """The levels `model` distinguishes, or None — effort cannot be
        expressed for it at all, which is a thing to say, not to ignore."""
        row = self._effort_row(model)
        return row[1] or None if row else None

    def _effort_row(self, model: str | None):
        if self.effort_channel == "none" or not model:
            return None
        bare = model.split("@preset/")[0]
        for row in self.effort_by_model:
            if fnmatch.fnmatchcase(bare, row[0]):
                return row
        return None

    def effort_for(self, model: str | None, asked: str, scale: list[str]) -> tuple[str | None, str]:
        """(served, outcome) for a class asking `asked` on `model`.

        Resolution order: the model distinguishes the level (applied); the
        vendor documents what it becomes (approximated, the vendor's own
        mapping, in either direction); otherwise the fabric clamps down to
        the nearest level below.

        The clamp is the FABRIC's and happens before the request leaves,
        because the vendors disagree about what an unsupported level
        means: OpenAI answers 400, xAI and Claude Code quietly drop a
        level, GLM-5.3-Flash errors, DeepSeek remaps. One routing decision
        must not mean two things depending on who serves it."""
        row = self._effort_row(model)
        if row is None:
            # No row means no model was given (a class the harness's tier
            # decides). Nothing is known about what it admits, which is
            # not the same as knowing it admits nothing.
            return None, "unknown-model"
        if not row[1]:
            return None, "unexpressible"
        _, levels, remap = row
        if asked in levels:
            return asked, "applied"
        if asked in remap:
            return remap[asked], "approximated"
        below = [l for l in scale[:scale.index(asked)] if l in levels] if asked in scale else []
        if below:
            return below[-1], "approximated"
        # Asked for LESS than the model's own floor. Sending nothing would
        # hand the vendor its default, which on a model defaulting to
        # `high` is a silent UPGRADE — the mirror image of the drop this
        # dimension exists to prevent. Clamp UP to the floor and say so
        # (review of 2026-09-23, F5).
        # From the SCALE's order, not the row's: its sibling `below` above
        # already derives from the scale, and a row written out of order
        # would otherwise return the wrong floor silently (re-review).
        floor = next((l for l in scale if l in levels), None)
        return (floor, "raised") if floor else (None, "unexpressible")


class OpenRouterAdapter(ProviderAdapter):
    name, resolution = "openrouter", "model-id"
    pattern, runtime = MODEL_ID, COMPOSITE
    describe = f"an OpenRouter model id (vendor/model, {MODEL_ID.pattern})"
    # The harness is still Claude Code here — ori proxies, it does not
    # replace — so the channel is the same agent file. OpenRouter's
    # Anthropic-shaped endpoint takes output_config.effort and re-emits it
    # in the upstream's own form. What differs is the models: each admits
    # its own set, and the levels a vendor ACCEPTS are not the levels it
    # DISTINGUISHES (GLM-5.2 takes seven and collapses them to three).
    # Listed here are the distinct outcomes, so a clamp means something.
    effort_channel = "agent-file"
    effort_by_model = (
        # DeepSeek V4: low/high/max + none, and it remaps the rest itself.
        ("deepseek/deepseek-v4*", ("none", "low", "high", "max"),
         {"minimal": "low", "medium": "high", "xhigh": "high"}),
        # GLM-5.3-Flash: "any other input will result in an error" — no
        # vendor remap, so the fabric clamps rather than let it 400.
        ("z-ai/glm-5.3*", ("low", "high", "max"), {}),
        # GLM-5.2 accepts seven and collapses them UPWARD to three.
        # xhigh -> high, not -> max as Z.ai documents: measured through the
        # broker, four of four xhigh runs sat in the same reasoning-token
        # band as medium and high and none approached max
        # (docs/live-checks/2026-09-23-effort-registry.md).
        ("z-ai/glm-5.2*", ("none", "minimal", "high", "max"),
         {"low": "high", "medium": "high", "xhigh": "high"}),
    )


class AnthropicAdapter(ProviderAdapter):
    name, resolution = "anthropic", "harness"
    pattern, runtime = NATIVE_ID, NATIVE_ID
    describe = "a native Claude id (claude-…); a tier alias is the adapter's, never named here"
    # Claude Code carries effort per class in the agent file's frontmatter
    # and per session on --effort; the Agent tool has no per-dispatch
    # effort, exactly as it takes no full model id (2.1.280, read back).
    effort_channel = "agent-file"
    # Every row read out of 2.1.280's own bundled model registry, not from
    # documentation: each entry carries a `capabilities` list, and a model
    # without "effort" in it is gated out before any request is built, so
    # no level is ever sent for it. "max_effort"/"xhigh_effort" are
    # separate capabilities, which is why 4.6 stops at max and 4.7 does
    # not (docs/live-checks/2026-09-23-effort-registry.md).
    effort_by_model = (
        # Haiku 4.x has no "effort" capability: none is sent. Haiku 5.5 is not
        # in 2.1.285's registry; the harness takes it with its defaults and
        # reports per_turn_effort_active true, where Haiku 4.5 reports false
        # (docs/live-checks/2026-10-07-haiku-5-5.md), so the catch-all holds it.
        ("claude-haiku-4*", (), {}),
        ("claude-opus-4-6*", ("low", "medium", "high", "max"), {}),   # no xhigh before 4.7
        ("claude-sonnet-4-6*", ("low", "medium", "high", "max"), {}),
        ("claude-*", ("low", "medium", "high", "xhigh", "max"), {}),
    )

    def column_findings(self, klass: str, model: Any, where: str) -> list[str]:
        if model is not None and not self.is_model(model):
            return [f"{where}.{klass} {model!r} is neither null (the harness's tier) nor a native Claude id; "
                    "a tier alias is the adapter's, never named here"]
        return super().column_findings(klass, model, where)

    def openrouter_id(self, model: str) -> str:
        return "anthropic/" + model


ADAPTERS: dict[str, ProviderAdapter] = {a.name: a for a in (OpenRouterAdapter(), AnthropicAdapter())}


def adapter(provider: str) -> ProviderAdapter:
    if provider not in ADAPTERS:
        raise KeyError(f"unknown provider {provider!r}; known: {', '.join(ADAPTERS)}")
    return ADAPTERS[provider]


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def routing_dir(root: str | None = None) -> str:
    return os.path.join(root or FABRIC_ROOT, "routing")


def load_capabilities(root: str | None = None) -> dict[str, Any]:
    return _load(os.path.join(routing_dir(root), "capabilities.json"))


def load_shims(root: str | None = None) -> list[dict[str, Any]]:
    return _load(os.path.join(routing_dir(root), "shims.json")).get("shims") or []


def load_review_grade(root: str | None = None) -> dict[str, Any]:
    path = os.path.join(routing_dir(root), "policies", "review-grade.json")
    return _load(path) if os.path.exists(path) else {"capability": "code-review", "models": []}


def load_effort(root: str | None = None) -> dict[str, Any]:
    path = os.path.join(routing_dir(root), "effort.json")
    return _load(path) if os.path.exists(path) else {"levels": [], "classes": {}, "providers": {}}


def effort_for(capability: str, provider: str, model: str | None, role: str | None = None,
               agent: str | None = None, local: dict[str, Any] | None = None,
               root: str | None = None) -> dict[str, Any]:
    """What this class asks for, what the model will actually be given,
    and which of the two it is. `intent` is the fabric's one vocabulary;
    `level` is what leaves. They differ only where a provider's model
    admits less, and then `outcome` says so — the downgrade is on the
    record rather than discovered later in a bill or a worse answer."""
    doc = load_effort(root)
    scale = list(doc.get("levels") or [])
    intent = (doc.get("classes") or {}).get(capability)
    source = "effort.json"
    # Order matters, and it is the order a MODEL id already follows:
    # committed file first, then the profile and agent layers over it. A
    # provider acknowledgement is the committed INTENT for that column,
    # not the last word — placing it after the layers let a file in the
    # repository outrank the agent's own choice, so an agent asking for
    # `max` on a model that admits `max` was served `high` and told its
    # intent WAS `high` (review of 2026-09-23, F3).
    committed = ((doc.get("providers") or {}).get(provider, {}).get("classes") or {}).get(capability)
    if committed:
        intent, source = committed, f"effort.json:providers.{provider}"
    over = merged_provider(provider, role, agent, local, root).get("effort", {}).get(capability)
    if over:
        intent, source = over["level"], over["source"]
    if not intent:
        return {"level": None, "intent": None, "outcome": "unset", "how": "none", "source": source}
    served, outcome = adapter(provider).effort_for(model, intent, scale)
    return {"level": served, "intent": intent, "outcome": outcome,
            "how": adapter(provider).effort_channel if served else "none", "source": source}


def load_profiles(root: str | None = None) -> dict[str, Any]:
    path = os.path.join(routing_dir(root), "profiles.json")
    return _load(path) if os.path.exists(path) else {"version": 2, "defaults": {}}


def shim_for(model: str, shims: list[dict[str, Any]], harness: str = "claude-code") -> str | None:
    """The shim a model's family needs for `harness`, or None. A bare
    `@preset/...` is already a preset and gets nothing attached."""
    if not model or PRESET.match(model):
        return None
    for entry in shims:
        if entry.get("harness", "claude-code") != harness:
            continue
        if fnmatch.fnmatchcase(model, entry["family"]):
            return entry["shim"]
    return None


def composite(model: str, shim: str | None) -> str:
    """The runtime string: `model@preset/slug`, or the model alone."""
    return f"{model}{shim}" if shim else model


def effort_phrase(effort: dict[str, Any] | None) -> str:
    """How a resolved effort reads beside its model, for every printer that
    shows one. Kept here so `launch --print` and `fabric-status` cannot
    describe the same downgrade in two different words — the point of the
    dimension is that `asked -> served` is legible wherever it appears."""
    e = effort or {}
    outcome = e.get("outcome")
    if outcome == "applied":
        return "effort %s" % e["level"]
    if outcome in ("approximated", "raised"):
        return "effort %s (asked %s)" % (e["level"], e["intent"])
    if outcome == "unexpressible":
        return "effort - (asked %s; this model expresses none)" % e.get("intent")
    if outcome == "unknown-model":
        # No model is pinned, so nothing is known about what it admits.
        # Saying "expresses none" here would assert a fact about a model
        # nobody has chosen (review of 2026-09-23, F6).
        return "effort - (asked %s; no model pinned, the harness's tier decides)" % e.get("intent")
    return ""


PROVIDERS = tuple(ADAPTERS)
LAYERS = ("defaults", "role", "agent", "local")
LOCAL_OVERRIDE = "model-profile.local.json"


def load_aliases(root: str | None = None) -> dict[str, Any]:
    return _load(os.path.join(root or FABRIC_ROOT, "runtime", "claude-code", "aliases.json"))


def file_pinned(root: str | None = None) -> list[str]:
    """Classes whose model reaches their agent file instead of a tier
    export (runtime/claude-code/aliases.json `file_pinned`): the review
    class, so that it never follows the class sharing its alias."""
    return list(load_aliases(root).get("file_pinned") or [])


def _object(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{where} is {value!r}, not an object")
    return value


def normalize_layer(layer: Any, where: str = "", root: str | None = None) -> dict[str, dict[str, Any]]:
    """One layer, as one object per provider, every value validated in that
    provider's vocabulary; a malformed value is a ValueError naming the
    field (the committed file is schema-checked, the local override is
    not, and a null there once reached `--model` as the string "None").

      openrouter: {session: <model id | class>, capabilities: {<class>: <model id>}}
      anthropic:  {session: <native id | class>, capabilities: {<class>: <native id>}}

    The vocabulary is the capability class and the provider's own model
    id; a harness tier alias is never named here — which alias a class
    rides is the Claude Code adapter's (runtime/claude-code/aliases.json).
    A session may name a class, meaning that class's model on the
    provider. The flat `session` and `capabilities` are the OpenRouter
    form; a flat `session` of `anthropic/<id>` also names `<id>` for
    plain claude unless `providers.anthropic.session` says otherwise."""
    prefix = where + "." if where else ""
    layer = _object(layer, where or "the profile layer")
    classes = set(load_capabilities(root)["classes"])

    def session(provider: str, value: Any, field: str) -> str:
        return ADAPTERS[provider].session(value, field, classes)

    def klass(name: str, field: str) -> str:
        if name not in classes:
            raise ValueError(f"{field}: {name!r} is not a capability class ({', '.join(sorted(classes))})")
        return name

    scale = list(load_effort(root).get("levels") or [])

    def level(value: Any, field: str) -> str:
        if value not in scale:
            raise ValueError(f"{field}: {value!r} is not an effort level ({', '.join(scale)})")
        return value

    out: dict[str, dict[str, Any]] = {p: {"capabilities": {}, "effort": {}} for p in PROVIDERS}
    if "session" in layer:
        value = session("openrouter", layer["session"], prefix + "session")
        out["openrouter"]["session"] = value
        if value.startswith("anthropic/"):
            out["anthropic"]["session"] = value[len("anthropic/"):]
        elif value in classes:
            out["anthropic"]["session"] = value
    for name, model in _object(layer.get("capabilities"), prefix + "capabilities").items():
        out["openrouter"]["capabilities"][klass(name, prefix + "capabilities")] = \
            ADAPTERS["openrouter"].model(model, f"{prefix}capabilities.{name}")
    for provider, body in _object(layer.get("providers"), prefix + "providers").items():
        p = f"{prefix}providers.{provider}"
        if provider not in ADAPTERS:
            raise ValueError(f"{p}: unknown provider; known: {', '.join(ADAPTERS)}")
        body = _object(body, p)
        for key in body:
            if key not in ("session", "capabilities", "effort"):
                raise ValueError(f"{p}.{key}: not a field of a provider layer (session, capabilities, effort); "
                                 "a class is set under capabilities, a tier alias is never named")
        if "session" in body:
            out[provider]["session"] = session(provider, body["session"], p + ".session")
        for name, model in _object(body.get("capabilities"), p + ".capabilities").items():
            out[provider]["capabilities"][klass(name, p + ".capabilities")] = \
                ADAPTERS[provider].model(model, f"{p}.capabilities.{name}")
        # Effort is layered like a model (the owner, 2026-09-23), but its
        # vocabulary is the fabric's — a level, never a provider spelling.
        for name, lvl in _object(body.get("effort"), p + ".effort").items():
            out[provider]["effort"][klass(name, p + ".effort")] = level(lvl, f"{p}.effort.{name}")
    return out


def layers(role: str | None, agent: str | None, local: dict[str, Any] | None = None,
           root: str | None = None) -> list[tuple[str, dict[str, Any]]]:
    """The four layers, bottom first, raw."""
    profiles = load_profiles(root)
    return [("defaults", profiles.get("defaults") or {}),
            ("role", ((profiles.get("roles") or {}).get(role) or {}) if role else {}),
            ("agent", ((profiles.get("agents") or {}).get(agent) or {}) if agent else {}),
            ("local", local or {})]


def merged_provider(provider: str, role: str | None = None, agent: str | None = None,
                    local: dict[str, Any] | None = None, root: str | None = None) -> dict[str, Any]:
    """One provider's merged choices with their provenance, each value as
    {"model", "source"}: {"session": … | None, "capabilities": {class: …}}.
    Per key, the nearest layer naming it wins. A malformed layer raises
    ValueError (normalize_layer)."""
    adapter(provider)
    out: dict[str, Any] = {"session": None, "capabilities": {}, "effort": {}}
    for name, body in layers(role, agent, local, root):
        norm = normalize_layer(body, name, root)[provider]
        if "session" in norm:
            out["session"] = {"model": norm["session"], "source": name}
        for klass, model in norm["capabilities"].items():
            out["capabilities"][klass] = {"model": model, "source": name}
        for klass, lvl in norm.get("effort", {}).items():
            out["effort"][klass] = {"level": lvl, "source": name}
    return out


def local_override_path(agent: str | None = None) -> str:
    """$STATE_DIR/model-profile.local.json for the agent — the login's own
    layer, gitignored, written by bin/fabric-model. Identity comes from
    runtime/identity.py, the one resolver."""
    spec = importlib.util.spec_from_file_location(
        "fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))
    identity = importlib.util.module_from_spec(spec); spec.loader.exec_module(identity)
    return os.path.join(identity.agent_state_dir(agent), LOCAL_OVERRIDE)


def load_local(agent: str | None = None, path: str | None = None) -> dict[str, Any]:
    """The agent's local layer, {} when absent. Validated where it is
    merged (normalize_layer names the field), not here."""
    path = path or local_override_path(agent)
    if not os.path.exists(path):
        return {}
    local = _load(path)
    if not isinstance(local, dict):
        raise ValueError(f"{path} is {type(local).__name__}, not an object")
    return local


def resolve(capability: str, provider: str = "openrouter", role: str | None = None,
            agent: str | None = None, local: dict[str, Any] | None = None,
            root: str | None = None, harness: str = "claude-code") -> dict[str, Any]:
    """One class on one provider: {model, shim, composite, source, alias,
    pinned, via}. `alias` is the tier the class rides (the adapter's);
    `via` says how the model reaches the class — "export" (the alias's
    ANTHROPIC_DEFAULT_*_MODEL), "file" (its agent file), or "harness"
    (nothing pinned: the harness's own model of that tier)."""
    caps = load_capabilities(root)
    if capability not in caps["classes"]:
        raise KeyError(f"unknown capability class {capability!r}; known: {sorted(caps['classes'])}")
    prov = caps["providers"].get(provider)
    if prov is None:
        raise KeyError(f"unknown provider {provider!r}; known: {sorted(caps['providers'])}")
    model = prov["models"].get(capability)
    source = f"capabilities.providers.{provider}"
    override = merged_provider(provider, role, agent, local, root)["capabilities"].get(capability)
    if override:
        model, source = override["model"], override["source"]
    alias = (load_aliases(root).get("aliases") or {}).get(capability)
    in_file = capability in file_pinned(root)
    if prov["resolution"] == "harness":
        if not model:
            # Nothing pinned: the harness's own model of the tier — spelled
            # as the alias, which is what plain claude takes.
            if not alias:
                raise KeyError(f"provider {provider!r} pins no model to {capability!r} and it rides no alias")
            # Nothing pinned, so nothing is known about the model that
            # will serve it — effort cannot be judged against a tier.
            return {"capability": capability, "provider": provider, "model": alias, "shim": None,
                    "composite": alias, "resolution": "harness", "source": "harness",
                    "alias": alias, "pinned": False, "via": "harness",
                    "effort": effort_for(capability, provider, None, role, agent, local, root)}
        return {"capability": capability, "provider": provider, "model": model, "shim": None,
                "composite": model, "resolution": "harness", "source": source,
                "alias": alias, "pinned": True, "via": "file" if in_file else "export",
                "effort": effort_for(capability, provider, model, role, agent, local, root)}
    if not model:
        raise KeyError(f"provider {provider!r} binds no model to {capability!r}")
    shim = shim_for(model, load_shims(root), harness)
    return {"capability": capability, "provider": provider, "model": model, "shim": shim,
            "composite": composite(model, shim), "resolution": "model-id", "source": source,
            "alias": alias, "pinned": True, "via": "file" if in_file else "export",
            "effort": effort_for(capability, provider, model, role, agent, local, root)}


def exports(provider: str = "openrouter", role: str | None = None, agent: str | None = None,
            local: dict[str, Any] | None = None, root: str | None = None) -> dict[str, dict[str, Any]]:
    """What the launcher exports, {ALIAS_ENV_VAR: {"model", "class", "source"}}:
    every class whose model reaches it through its alias's export — on the
    broker every non-file class; on plain claude the pinned ones. Two
    classes riding one alias cannot both export: only a file-pinned class
    may share (check() enforces it), so this raises if it ever happens."""
    aliases = load_aliases(root)
    out: dict[str, dict[str, Any]] = {}
    for klass, alias in (aliases.get("aliases") or {}).items():
        res = resolve(klass, provider, role, agent, local, root)
        if res["via"] != "export":
            continue
        var = aliases["env"][alias]
        if var in out and out[var]["model"] != res["composite"]:
            raise KeyError(f"{klass} and {out[var]['class']} both ride {alias} and would export different models")
        out[var] = {"model": res["composite"], "class": klass, "source": res["source"], "alias": alias}
    return out


def resolve_session(role: str | None = None, agent: str | None = None,
                    local: dict[str, Any] | None = None, root: str | None = None,
                    harness: str = "claude-code", provider: str = "openrouter") -> dict[str, Any]:
    """The main agent's model, with its family shim on the broker path.
    Separate from capability resolution: the session is not a class, but
    a layer may name one, meaning that class's model on the provider.
    Each provider's session comes from the nearest layer naming one for
    it — on plain claude that is `providers.anthropic.session` or a flat
    `session` of `anthropic/<id>` (or a class); a broker-only layer (GLM)
    says nothing about plain claude and is skipped, and the skip is
    reported. A model of another vendor cannot run there, so none at all
    is refused rather than mistranslated."""
    merged = merged_provider(provider, role, agent, local, root)
    entry = merged["session"]
    broker = merged_provider("openrouter", role, agent, local, root)["session"] if provider == "anthropic" else None
    if not entry:
        if broker:
            raise KeyError(f"session model {broker['model']!r} is not an Anthropic model and no profile layer "
                           "names one; plain claude cannot run it (set providers.anthropic.session: a class "
                           "or a native id)")
        raise KeyError("no session model: routing/profiles.json defaults must carry one for every provider")
    model, klass = entry["model"], None
    if model in load_capabilities(root)["classes"]:
        model, klass = resolve(model, provider, role, agent, local, root)["composite"], model
    if provider == "anthropic":
        skipped = broker["model"] if broker and LAYERS.index(broker["source"]) > LAYERS.index(entry["source"]) else None
        return {"model": model, "shim": None, "composite": model, "capability": klass,
                "openrouter_id": ADAPTERS["anthropic"].openrouter_id(model) if ADAPTERS["anthropic"].is_model(model) else None,
                "source": entry["source"], "skipped": skipped}
    if klass:
        return {"model": model.split("@", 1)[0], "shim": shim_for(model.split("@", 1)[0], load_shims(root), harness),
                "composite": model, "capability": klass, "source": entry["source"]}
    shim = shim_for(model, load_shims(root), harness)
    return {"model": model, "shim": shim, "composite": composite(model, shim), "capability": None,
            "source": entry["source"]}


def session_effort(provider: str = "anthropic", role: str | None = None, agent: str | None = None,
                   local: dict[str, Any] | None = None, root: str | None = None) -> str | None:
    """The level the SESSION runs at, already clamped to what its model
    admits, or None when that model expresses no effort at all.

    `session` in routing/effort.json names a level or a capability class
    whose level to take, as routing/profiles.json's own `session` may name
    a class. Naming the class keeps the session's thinking with the
    session's model, so one edit moves both."""
    doc = load_effort(root)
    want = doc.get("session")
    if not want:
        return None
    if want in (doc.get("classes") or {}):
        want = (resolve(want, provider, role, agent, local, root) or {}).get("effort", {}).get("intent")
    if not want:
        return None
    model = resolve_session(role, agent, local, root, provider=provider)["model"]
    served, _ = adapter(provider).effort_for(model, want, list(doc.get("levels") or []))
    return served


def review_grade_ok(model: str, root: str | None = None) -> bool:
    """Admitted by routing/policies/review-grade.json, whose entries are
    OpenRouter ids; a native id (claude-…) is the same model spelled as
    plain claude names it, so it is compared under `anthropic/`."""
    if ADAPTERS["anthropic"].is_model(model):
        model = ADAPTERS["anthropic"].openrouter_id(model)
    return model in (load_review_grade(root).get("models") or [])


def check(root: str | None = None) -> list[str]:
    """Consistency findings across the canonical files; empty means clean."""
    findings: list[str] = []
    caps = load_capabilities(root)
    classes = set(caps.get("classes") or {})
    for name, prov in (caps.get("providers") or {}).items():
        if name not in ADAPTERS:
            findings.append(f"capabilities.json: providers.{name} has no adapter (tools/fabric/routing.py ADAPTERS: "
                            f"{', '.join(ADAPTERS)})")
            continue
        ad = ADAPTERS[name]
        if prov.get("resolution") != ad.resolution:
            findings.append(f"capabilities.json: providers.{name}.resolution is {prov.get('resolution')!r}; "
                            f"the {name} adapter resolves by {ad.resolution!r}")
        for klass, model in (prov.get("models") or {}).items():
            if klass not in classes:
                findings.append(f"capabilities.json: providers.{name} binds unknown class {klass!r}")
            findings += ad.column_findings(klass, model, f"capabilities.json: providers.{name}")
        for klass in classes:
            if klass not in (prov.get("models") or {}):
                findings.append(f"capabilities.json: providers.{name} binds no model to {klass!r}")
    for entry in load_shims(root):
        if not PRESET.match(entry.get("shim") or ""):
            findings.append(f"shims.json: {entry.get('family')!r} -> {entry.get('shim')!r} is not a preset reference")
        else:
            # A shim's text is under version control (routing/shims/<slug>/,
            # tools/fabric/shim.py pull/push); an entry with no source is a
            # preset nobody can rebuild or diff (2026-09-16).
            slug = entry["shim"].split("@preset/", 1)[1]
            src = os.path.join(root or FABRIC_ROOT, "routing", "shims", slug, "system_prompt.md")
            if not os.path.isfile(src):
                findings.append(f"shims.json: {entry.get('shim')!r} has no source under routing/shims/{slug}/ "
                                "(tools/fabric/shim.py pull <slug>)")
    grade = load_review_grade(root)
    if grade.get("capability") not in classes:
        findings.append(f"review-grade.json: gates unknown capability {grade.get('capability')!r}")
    for model in grade.get("models") or []:
        if not MODEL_ID.match(model):
            findings.append(f"review-grade.json: {model!r} is not a model id")
    # The review class must be review-grade wherever the fabric names its
    # model: on every model-id provider, and on the harness provider when
    # the column pins a native id (an alias is the harness's choice, ungated).
    for name, prov in (caps.get("providers") or {}).items():
        model = (prov.get("models") or {}).get(grade.get("capability"))
        if model and name in ADAPTERS and ADAPTERS[name].is_model(model):
            if not review_grade_ok(model, root):
                findings.append(f"capabilities.json: providers.{name}.{grade.get('capability')} {model!r} "
                                "is not in routing/policies/review-grade.json")
    # The Claude Code binding: every class rides a harness tier alias (the
    # Agent tool's `model` field accepts nothing else), aliases are unique
    # (one export per alias), and the harness provider in capabilities.json
    # says the same thing.
    aliases_path = os.path.join(root or FABRIC_ROOT, "runtime", "claude-code", "aliases.json")
    if os.path.exists(aliases_path):
        doc = _load(aliases_path)
        aliases = doc.get("aliases") or {}
        if "declared" in doc:
            findings.append("runtime/claude-code/aliases.json: `declared` is retired; the Agent tool cannot "
                            "name a full model id, so every class must ride an alias")
        if set(aliases) != classes:
            findings.append(f"runtime/claude-code/aliases.json: bound classes {sorted(aliases)} != {sorted(classes)}")
        pinned = set(doc.get("file_pinned") or [])
        for klass in pinned:
            if klass not in classes:
                findings.append(f"runtime/claude-code/aliases.json: file_pinned names unknown class {klass!r}")
        for alias in set(aliases.values()):
            exporters = [k for k, a in aliases.items() if a == alias and k not in pinned]
            if len(exporters) > 1:
                findings.append(f"runtime/claude-code/aliases.json: {' and '.join(exporters)} share the {alias} alias "
                                "and both export; one alias carries one export — the class that must not follow "
                                "the other goes through its agent file (file_pinned)")
        for klass, alias in aliases.items():
            if alias not in (doc.get("env") or {}):
                findings.append(f"runtime/claude-code/aliases.json: alias {alias!r} has no export variable")
        if grade.get("capability") in classes and grade.get("capability") not in pinned:
            findings.append(f"runtime/claude-code/aliases.json: the gated class {grade.get('capability')!r} is not "
                            "file_pinned; through an export it would follow whatever shares its alias")

    # ── effort ──────────────────────────────────────────────────────
    # The rule this file exists for: a level the fabric asks for and the
    # provider will not give is WRITTEN DOWN, or check refuses. A
    # computed downgrade is the silent re-tuning the whole dimension was
    # added to stop (docs/live-checks/2026-09-23-opus-5-5.md).
    effort = load_effort(root)
    scale = list(effort.get("levels") or [])
    if not scale:
        findings.append("routing/effort.json: no levels; the vocabulary is this file's, not an adapter's")
    if sorted(dict.fromkeys(scale)) != sorted(set(scale)):
        findings.append("routing/effort.json: levels repeat; the scale is ordered and distinct")
    declared = set(effort.get("classes") or {})
    if declared != set(classes):
        missing, extra = sorted(set(classes) - declared), sorted(declared - set(classes))
        findings.append(f"routing/effort.json: classes {sorted(declared)} but capabilities.json defines "
                        f"{sorted(classes)}" + (f"; missing {missing}" if missing else "")
                        + (f"; unknown {extra}" if extra else ""))
    for klass, lvl in (effort.get("classes") or {}).items():
        if lvl not in scale:
            findings.append(f"routing/effort.json: classes.{klass} is {lvl!r}, not one of {', '.join(scale)}")
    sess = effort.get("session")
    if sess is not None and sess not in scale and sess not in classes:
        findings.append(f"routing/effort.json: session {sess!r} is neither a level nor a capability class")
    for provider in (effort.get("providers") or {}):
        if provider not in ADAPTERS:
            findings.append(f"routing/effort.json: providers.{provider} has no adapter; known: {', '.join(ADAPTERS)}")
    for provider in ADAPTERS:
        if provider not in caps.get("providers", {}):
            continue
        ack = ((effort.get("providers") or {}).get(provider, {}).get("classes") or {})
        notes = ((effort.get("providers") or {}).get(provider, {}).get("notes") or {})
        base = (effort.get("classes") or {})
        for klass in classes:
            try:
                res = resolve(klass, provider, root=root)
            except KeyError:
                continue
            if klass in ack:
                # An acknowledgement is a committed statement about a
                # (provider, MODEL) pair, but it is keyed only by class —
                # so it outlives the model it was written for. Re-judge it
                # rather than skipping: an ack that no longer matches what
                # the adapter yields was written for a model that has since
                # been replaced, and is as wrong as a missing one (review
                # of 2026-09-23, F3).
                if klass not in notes:
                    findings.append(
                        f"routing/effort.json: providers.{provider}.classes.{klass} has no matching entry in "
                        f"providers.{provider}.notes — an acknowledged downgrade without its reason is the "
                        "commit this file exists to require, with the reason left out.")
                if res["via"] == "harness" or not res.get("model"):
                    continue
                want = base.get(klass)
                if want:
                    now, _ = adapter(provider).effort_for(res["model"], want, scale)
                    if now != ack[klass]:
                        findings.append(
                            f"routing/effort.json: providers.{provider}.classes.{klass} is {ack[klass]!r}, but "
                            f"{klass} asks for {want!r} and {res['model']} now yields {now!r}. The "
                            "acknowledgement was written for a different model; re-decide it or delete it.")
                continue
            if res["via"] == "harness":
                # Nothing is pinned, so which model serves this class is
                # the harness's choice of its tier — there is no model to
                # ask about a level, and inventing a finding here would
                # demand an acknowledgement of something nobody decided.
                continue
            e = res.get("effort") or {}
            if e.get("outcome") == "raised" and e.get("intent"):
                findings.append(
                    f"routing/effort.json: {klass} asks for {e['intent']!r}; {res['model']} on {provider} "
                    f"admits nothing that low and is given {e['level']!r} instead. Write "
                    f"providers.{provider}.classes.{klass}: {e['level']!r} with a note, or raise the class — "
                    "a class given MORE thinking than anyone asked for is the same defect upside down.")
            elif e.get("outcome") == "unexpressible" and e.get("intent"):
                findings.append(
                    f"routing/effort.json: {klass} asks for {e['intent']!r}; {res['model']} on {provider} "
                    f"expresses no effort at all. Write providers.{provider}.classes.{klass}: null with a "
                    "note, or change the model — a class whose thinking nobody chose is the defect this file "
                    "was added for.")
            elif e.get("outcome") == "approximated" and e.get("level") and e.get("intent") \
                    and scale.index(e["level"]) < scale.index(e["intent"]):
                findings.append(
                    f"routing/effort.json: {klass} asks for {e['intent']!r}; {res['model']} on {provider} "
                    f"gives {e['level']!r}. Write providers.{provider}.classes.{klass}: {e['level']!r} with a "
                    "note, or lower the class — a level lost with no commit and nothing to review is exactly "
                    "what this dimension exists to stop.")
        # The session is judged like a class: the level it asks for (its
        # own, or the class it names), on the model the session resolves
        # to for this provider. Its acknowledgement is
        # providers.<provider>.session, with notes.session beside it. A
        # session naming a class asks what that class asks on this provider
        # — its intent after the class's own acknowledgement, as
        # session_effort() reads it — so a downgrade already written for
        # the class is not demanded a second time. A `null` acknowledgement
        # (a model with no effort at all) leaves the intent at the class's
        # base level, so it is honoured here directly: when the session
        # rides that class's own model, the class's decision is the
        # session's too (#57 re-review N1).
        sess_want = sess
        if sess in base:
            try:
                res_cls = resolve(sess, provider, root=root) or {}
                sess_want = (res_cls.get("effort") or {}).get("intent")
                if sess in ack and res_cls.get("model") and \
                        res_cls.get("model") == resolve_session(root=root, provider=provider).get("model"):
                    sess_want = None
                    # A session acknowledgement written beside the class's
                    # is then read by nothing: said, not passed in silence
                    # (#58 review F5).
                    if "session" in ((effort.get("providers") or {}).get(provider, {}) or {}):
                        findings.append(
                            f"routing/effort.json: providers.{provider}.session is redundant: the session rides "
                            f"{sess}'s model on {provider}, and providers.{provider}.classes.{sess} decides; "
                            "delete it (and its note).")
            except (KeyError, ValueError):
                sess_want = None
        if sess_want in scale:
            try:
                model = resolve_session(root=root, provider=provider).get("model")
            except (KeyError, ValueError):
                model = None
            if model:
                served, outcome = adapter(provider).effort_for(model, sess_want, scale)
                acked = ((effort.get("providers") or {}).get(provider, {}) or {})
                # Raised is the same defect upside down, as for a class.
                lost = outcome in ("unexpressible", "raised") or (outcome == "approximated" and served and
                                                                  scale.index(served) < scale.index(sess_want))
                if "session" in acked:
                    if "session" not in notes:
                        findings.append(
                            f"routing/effort.json: providers.{provider}.session has no matching entry in "
                            f"providers.{provider}.notes — an acknowledged downgrade without its reason.")
                    elif acked["session"] != served:
                        findings.append(
                            f"routing/effort.json: providers.{provider}.session is {acked['session']!r}, but the "
                            f"session asks for {sess_want!r} and {model} now yields {served!r}; re-decide it or "
                            "delete it.")
                elif lost:
                    findings.append(
                        f"routing/effort.json: the session asks for {sess_want!r}; {model} on {provider} gives "
                        f"{served!r}. Write providers.{provider}.session: {'null' if served is None else repr(served)} with a note in "
                        f"providers.{provider}.notes, or change the session's level or model.")
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--fabric", default=None, help="agent-fabric root (default: this checkout)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="resolve one capability class")
    r.add_argument("capability")
    r.add_argument("--provider", default="openrouter")
    r.add_argument("--role", default=None)
    r.add_argument("--agent", default=None)
    r.add_argument("--json", action="store_true")
    t = sub.add_parser("table", help="every class, resolved")
    t.add_argument("--provider", default="openrouter")
    t.add_argument("--role", default=None)
    t.add_argument("--agent", default=None)
    sub.add_parser("check", help="validate the canonical routing files")
    s = sub.add_parser("pins", help="the file-pinned classes' models on a provider (the review class): `<class> <alias> <model>`")
    s.add_argument("--provider", default="anthropic")
    s.add_argument("--role", default=None)
    s.add_argument("--agent", default=None)
    s.add_argument("--local", default=None, help="a model-profile.local.json to merge as the local layer")
    s.add_argument("--me", action="store_true",
                   help="this login's role binding and local override (runtime/identity.py)")
    s = sub.add_parser("session-effort", help="the session's resolved effort level on a provider, or nothing")
    s.add_argument("--provider", default="anthropic")
    s.add_argument("--role", default=None)
    s.add_argument("--agent", default=None)
    s.add_argument("--local", default=None, help="a model-profile.local.json to merge as the local layer")
    s.add_argument("--me", action="store_true",
                   help="this login's role binding and local override (runtime/identity.py)")
    s = sub.add_parser("efforts", help="every class's resolved effort on a provider: `<class> <level|-> <outcome>`")
    s.add_argument("--provider", default="anthropic")
    s.add_argument("--role", default=None)
    s.add_argument("--agent", default=None)
    s.add_argument("--local", default=None, help="a model-profile.local.json to merge as the local layer")
    s.add_argument("--me", action="store_true",
                   help="this login's role binding and local override (runtime/identity.py)")
    s = sub.add_parser("shim", help="the family shim a model id needs, or nothing")
    s.add_argument("model")
    s.add_argument("--harness", default="claude-code")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.fabric) if args.fabric else None

    def _whose(args):
        """(role, agent, local) for a subcommand that may say --me: this
        login's binding and its local layer, or whatever the flags name."""
        role, agent, local = args.role, args.agent, None
        if args.me:
            spec = importlib.util.spec_from_file_location(
                "fabric_identity", os.path.join(root or FABRIC_ROOT, "runtime", "identity.py"))
            identity = importlib.util.module_from_spec(spec); spec.loader.exec_module(identity)
            agent = agent or identity.current_agent()
            role = role or identity.read_binding(agent).get("role")
        if args.local or args.me:
            local = load_local(agent, args.local)
        return role, agent, local

    if args.cmd == "session-effort":
        # One line for the launcher's --effort, or nothing at all when the
        # session's model expresses none. Never a default: a level this
        # model cannot take is not a decision worth stamping.
        role, agent, local = _whose(args)
        level = session_effort(args.provider, role, agent, local, root)
        if level:
            print(level)
        return 0
    if args.cmd == "efforts":
        # For the agent-file installer and the launcher: every class and the
        # effort level that actually leaves for it, already clamped by the
        # adapter. `<class> <level|-> <outcome>`; `-` means the model
        # expresses no effort and NO `effort:` line should be written, which
        # is different from writing a default. The caller decides what an
        # outcome costs — the launcher refuses an unexpressible review class,
        # a coding class only warns (the owner, 2026-09-23).
        role, agent, local = _whose(args)
        for klass in load_capabilities(root)["classes"]:
            e = resolve(klass, args.provider, role, agent, local, root=root).get("effort") or {}
            print(f"{klass} {e.get('level') or '-'} {e.get('outcome') or 'unset'}")
        return 0
    if args.cmd == "pins":
        # For the dispatch guard and the agent-file installer: the classes
        # whose model goes through their agent file (file_pinned — the
        # review class, which must never follow the class sharing its
        # alias), resolved on the given provider, with the alias each
        # rides. Nothing when the merged model is the harness's; exit 0
        # either way. Every other class is an alias export (`exports`).
        role, agent, local = _whose(args)
        for klass in file_pinned(root):
            res = resolve(klass, args.provider, role, agent, local, root=root)
            if res["via"] == "file":
                print(f"{klass} {res.get('alias') or ''} {res['composite']}")
        return 0
    if args.cmd == "shim":
        # One line, the shim or nothing; exit 0 either way. A hook asks this
        # so that "which families need a shim" has one implementation. A
        # composite already names its shim and gets nothing more.
        shim = shim_for(args.model.split("@", 1)[0], load_shims(root), args.harness)
        if shim:
            print(shim)
        return 0

    if args.cmd == "check":
        findings = check(root)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        print("routing: clean" if not findings else f"routing: {len(findings)} finding(s)")
        return 1 if findings else 0
    if args.cmd == "resolve":
        res = resolve(args.capability, args.provider, args.role, args.agent, root=root)
        if args.json:
            print(json.dumps(res, indent=2, sort_keys=True))
        else:
            print(res["composite"])
        return 0
    caps = load_capabilities(root)
    for klass in caps["classes"]:
        res = resolve(klass, args.provider, args.role, args.agent, root=root)
        print(f"{klass:12} -> {res['model']:32} shim: {res['shim'] or '-':28} => {res['composite']}")
    s = resolve_session(args.role, args.agent, root=root, provider=args.provider)
    print(f"{'session':12} -> {s['model']:32} shim: {s['shim'] or '-':28} => {s['composite']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
