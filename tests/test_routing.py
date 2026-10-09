#!/usr/bin/env python3
"""Behavioural tests for tools/fabric/routing.py.

The invariant under test: capability -> model and model -> shim are two
independent dimensions, and the composite `model@preset/slug` is derived —
never read from a canonical file. Cases run against the real routing files
and against throwaway copies with one model changed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import instance_fixtures  # noqa: E402 — tests/, this script's own directory
import routing  # noqa: E402

GLM_SHIM = "@preset/glm2claude-shim"


FIXTURE = os.path.join(HERE, "fixtures", "routing-distinct")


def scratch_root(tmp: str, distinct: bool = True) -> str:
    """A copy of the engine's routing files and aliases, to be edited freely
    — with the column and levels of 2026-09-24, where the five classes differ
    (tests/fixtures/routing-distinct/): the committed column is one model at
    one level, and a mechanic that answered from the wrong class would pass.
    `distinct=False` keeps the committed column and levels, for the cases
    that assert them. The operator half (the profiles overlay, the review
    grade) is the fixture's either way, never the live files: a checkout
    without its instance data (tests/stripped_run.py) must pass too."""
    root = os.path.join(tmp, "fabric")
    shutil.copytree(os.path.join(ROOT, "routing"), os.path.join(root, "routing"),
                    ignore=shutil.ignore_patterns(*instance_fixtures.ROUTING_OPERATOR_IGNORE))
    for name in ("capabilities.json", "effort.json") if distinct else ():
        shutil.copy2(os.path.join(FIXTURE, name), os.path.join(root, "routing", name))
    instance_fixtures.write_routing_overlay(os.path.join(root, "routing"))
    os.makedirs(os.path.join(root, "runtime", "claude-code"))
    shutil.copy2(os.path.join(ROOT, "runtime", "claude-code", "aliases.json"),
                 os.path.join(root, "runtime", "claude-code", "aliases.json"))
    return root


def set_model(root: str, provider: str, klass: str, model: str) -> None:
    path = os.path.join(root, "routing", "capabilities.json")
    d = json.load(open(path, encoding="utf-8"))
    d["providers"][provider]["models"][klass] = model
    json.dump(d, open(path, "w", encoding="utf-8"))


DS_SHIM = "@preset/deepseek2claude-shim"


def test_current_broker_policy(tmp: str) -> None:
    """The broker column as decided: GLM on the cheap tiers, DeepSeek V4
    Pro on the top tier, the session and the review class (the owner,
    2026-09-19) — the reviewer is the strongest admissible model, and its
    independence is the blind brief, not a different family."""
    expected = {
        "code-low": ("z-ai/glm-5.3-flash", GLM_SHIM, "z-ai/glm-5.3-flash@preset/glm2claude-shim"),
        "code-medium": ("z-ai/glm-5.2", GLM_SHIM, "z-ai/glm-5.2@preset/glm2claude-shim"),
        "code-high": ("deepseek/deepseek-v4-pro-0813", DS_SHIM, "deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim"),
        "code-plan": ("deepseek/deepseek-v4-pro-0813", DS_SHIM, "deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim"),
        "code-review": ("deepseek/deepseek-v4-pro-0813", DS_SHIM, "deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim"),
    }
    root = scratch_root(tmp, distinct=False)
    for klass, (model, shim, comp) in expected.items():
        res = routing.resolve(klass, "openrouter", root=root)
        assert (res["model"], res["shim"], res["composite"]) == (model, shim, comp), res


def test_native_path_pins_haiku_and_sonnet_5_5_low_and_opus_5_5_above(tmp: str) -> None:
    """On plain claude code-low is Haiku 5.5 (the owner, 2026-10-07),
    code-medium Sonnet 5.5 (the owner, 2026-09-29), and the upper classes, the review class included, Opus 5.5
    (the owner, 2026-09-25; the top model of each class's own tier from
    2026-09-15 until then); a coding class's pin is the export of the
    alias it rides, the review class's reaches its agent file. No shim.
    A class the column leaves null is the harness's own tier."""
    root = scratch_root(tmp, distinct=False)
    got = {k: routing.resolve(k, "anthropic", root=root) for k in routing.load_capabilities(root)["classes"]}
    assert {k: v["composite"] for k, v in got.items()} == {
        "code-low": "claude-haiku-5-5", "code-medium": "claude-sonnet-5-5", "code-high": "claude-opus-5-5",
        "code-plan": "claude-opus-5-5", "code-review": "claude-opus-5-5"}, got
    assert {k: v["via"] for k, v in got.items()} == {
        "code-low": "export", "code-medium": "export", "code-high": "export", "code-plan": "export", "code-review": "file"}, got
    assert {k: v["alias"] for k, v in got.items()} == {
        "code-low": "haiku", "code-medium": "sonnet", "code-high": "opus", "code-plan": "fable", "code-review": "fable"}
    assert all(v["shim"] is None for v in got.values()), "no shim on the native path"
    # …and every class and the session ask medium (the owner, 2026-09-25):
    # check() judges a level only where it is lost, so nothing else pins them.
    effort = routing.load_effort(root)
    assert effort["classes"] == dict.fromkeys(routing.load_capabilities(root)["classes"], "medium"), effort["classes"]
    assert effort["session"] == "medium", effort["session"]
    assert {k: v["effort"]["level"] for k, v in got.items()} == dict.fromkeys(got, "medium"), got
    assert routing.review_grade_ok("claude-opus-5-5", root), "the native spelling is graded under anthropic/"
    assert routing.review_grade_ok("claude-opus-5[1m]", root), "the reviewer of 2026-09-15 stays admitted"
    assert not routing.review_grade_ok("claude-haiku-4-5", root)
    ex = routing.exports("anthropic", root=root)
    assert {k: v["model"] for k, v in ex.items()} == {
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-5-5", "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5-5",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-5-5", "ANTHROPIC_DEFAULT_FABLE_MODEL": "claude-opus-5-5"}, ex
    assert "code-review" not in {v["class"] for v in ex.values()}, "the review class is never an export"
    s = routing.resolve_session(provider="anthropic", root=root)
    assert (s["model"], s["composite"], s["openrouter_id"], s["source"], s["skipped"]) == \
        ("claude-opus-5-5", "claude-opus-5-5", "anthropic/claude-opus-5-5", "defaults", None), s
    # A broker-only local override (GLM) says nothing about plain claude: the
    # nearest layer naming an Anthropic model wins, and the skip is reported.
    s = routing.resolve_session(local={"session": "z-ai/glm-5.3"}, provider="anthropic", root=root)
    assert (s["model"], s["source"], s["skipped"]) == ("claude-opus-5-5", "defaults", "z-ai/glm-5.3"), s
    s = routing.resolve_session(local={"session": "anthropic/claude-opus-5[1m]"}, provider="anthropic", root=root)
    assert (s["model"], s["source"]) == ("claude-opus-5[1m]", "local"), s
    # An agent layer moves that agent's session and nobody else's (the live
    # layer, architect-cto-01 on Fable 5.1, is the operator's: a layer here).
    prof = os.path.join(root, "routing", "profiles.json")
    doc = json.load(open(prof, encoding="utf-8"))
    doc["agents"] = {"architect-cto-01": {"providers": {"anthropic": {"session": "claude-fable-5-1"}}}}
    json.dump(doc, open(prof, "w", encoding="utf-8"))
    s = routing.resolve_session("architect-cto", "architect-cto-01", provider="anthropic", root=root)
    assert (s["model"], s["source"]) == ("claude-fable-5-1", "agent"), s
    assert routing.resolve_session("architect-cto", "architect-cto-02", provider="anthropic", root=root)["model"] == "claude-opus-5-5"


def test_a_null_in_the_harness_column_is_the_harness_tier(tmp: str) -> None:
    root = scratch_root(tmp)
    set_model(root, "anthropic", "code-high", None)
    r = routing.resolve("code-high", "anthropic", root=root)
    assert (r["model"], r["via"], r["pinned"], r["alias"]) == ("opus", "harness", False, "opus"), r
    assert "ANTHROPIC_DEFAULT_OPUS_MODEL" not in routing.exports("anthropic", root=root), "nothing pinned, nothing exported"
    assert routing.check(root) == [], routing.check(root)
    set_model(root, "anthropic", "code-high", "opus")
    assert any("tier alias is the adapter" in f for f in routing.check(root)), "an alias in the column is refused: the class is the vocabulary"


def test_a_layer_is_per_provider(tmp: str) -> None:
    """One layer names each provider's choices in that provider's
    vocabulary — the class and the provider's model id, never a tier
    alias; the merge is per provider, per key, nearest layer wins. The
    flat session/capabilities are the OpenRouter form (and an anthropic/
    session serves plain claude too), so an old local file reads exactly
    as before. A session may name a class."""
    root = scratch_root(tmp)
    local = {"providers": {"openrouter": {"session": "z-ai/glm-5.3", "capabilities": {"code-low": "z-ai/glm-5.2"}},
                           "anthropic": {"session": "code-plan",
                                         "capabilities": {"code-high": "claude-opus-5[1m]", "code-review": "claude-opus-5"}}}}
    s = routing.resolve_session(local=local, provider="openrouter", root=root)
    assert (s["model"], s["source"], s["capability"]) == ("z-ai/glm-5.3", "local", None), s
    s = routing.resolve_session(local=local, provider="anthropic", root=root)
    assert (s["model"], s["source"], s["skipped"], s["capability"]) == ("claude-fable-5-1", "local", None, "code-plan"), \
        "a class-named session is that class's model on the provider"
    assert routing.resolve("code-low", "openrouter", local=local, root=root)["model"] == "z-ai/glm-5.2"
    assert routing.resolve("code-low", "anthropic", local=local, root=root)["model"] == "claude-haiku-4-5-20251001", "the broker override stays on the broker"
    hi = routing.resolve("code-high", "anthropic", local=local, root=root)
    assert (hi["model"], hi["via"], hi["source"], hi["alias"]) == ("claude-opus-5[1m]", "export", "local", "opus")
    assert routing.resolve("code-high", "openrouter", local=local, root=root)["model"] == "deepseek/deepseek-v4-pro-0813", "the native pin stays on plain claude"
    rv = routing.resolve("code-review", "anthropic", local=local, root=root)
    assert (rv["model"], rv["source"], rv["via"]) == ("claude-opus-5", "local", "file"), rv
    ex = routing.exports("anthropic", local=local, root=root)
    assert ex["ANTHROPIC_DEFAULT_OPUS_MODEL"]["model"] == "claude-opus-5[1m]" and \
        ex["ANTHROPIC_DEFAULT_FABLE_MODEL"]["class"] == "code-plan", ex
    # A class-named session on the broker carries the class's shim.
    s = routing.resolve_session(local={"session": "code-high"}, provider="openrouter", root=root)
    assert (s["composite"], s["capability"]) == ("deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim", "code-high"), s
    s = routing.resolve_session(local={"session": "code-high"}, provider="anthropic", root=root)
    assert (s["model"], s["capability"]) == ("claude-opus-5-5", "code-high"), "a flat class-named session serves both providers"
    # A flat layer over a per-provider one: the nearest layer wins per key.
    both = {"providers": {"anthropic": {"session": "claude-opus-5[1m]"}}, "session": "anthropic/claude-sonnet-5"}
    assert routing.resolve_session(local=both, provider="anthropic", root=root)["model"] == "claude-opus-5[1m]", \
        "providers.anthropic.session outranks what the flat anthropic/ session implies"
    assert routing.resolve_session(local=both, provider="openrouter", root=root)["model"] == "anthropic/claude-sonnet-5"


def test_a_layer_is_validated_in_its_provider_vocabulary() -> None:
    def refused(layer, needle):
        try:
            routing.normalize_layer(layer, "local")
        except ValueError as exc:
            assert needle in str(exc), f"{needle!r} not in {exc}"
            return
        raise AssertionError(f"{layer} was accepted")
    refused({"session": None}, "session is None")
    refused({"providers": {"anthropic": {"session": "z-ai/glm-5.3"}}}, "neither a capability class")
    refused({"providers": {"anthropic": {"session": "opus"}}}, "neither a capability class")
    refused({"providers": {"anthropic": {"capabilities": {"code-high": "opus"}}}}, "not a native Claude id")
    refused({"providers": {"anthropic": {"aliases": {"opus": "claude-opus-5"}}}}, "a tier alias is never named")
    refused({"providers": {"anthropic": {"capabilities": {"turbo": "claude-opus-5"}}}}, "not a capability class")
    refused({"providers": {"openrouter": {"capabilities": {"code-high": "opus"}}}}, "not an OpenRouter model id")
    refused({"providers": {"vertex": {}}}, "unknown provider")
    refused({"capabilities": {"code-low": "z-ai/glm-5.3@preset/glm2claude-shim"}}, "not an OpenRouter model id")
    # A layer carries effort beside capabilities now (the owner, 2026-09-23):
    # effort is layered like a model id, in the fabric's own vocabulary.
    assert routing.normalize_layer({}) == {"openrouter": {"capabilities": {}, "effort": {}},
                                           "anthropic": {"capabilities": {}, "effort": {}}}
    refused({"providers": {"anthropic": {"effort": {"code-high": "enormous"}}}}, "not an effort level")
    refused({"providers": {"anthropic": {"effort": {"turbo": "high"}}}}, "not a capability class")


def test_effort_is_one_vocabulary_resolved_per_class(tmp: str) -> None:
    """Effort is routed beside the model: one vocabulary in
    routing/effort.json, translated per provider by the adapter, and
    every resolution says which of the three things happened to it."""
    root = scratch_root(tmp, distinct=False)
    for provider in ("anthropic", "openrouter"):
        for klass in routing.load_capabilities(root)["classes"]:
            e = routing.resolve(klass, provider, root=root)["effort"]
            assert e["intent"], f"{klass}/{provider} asks for nothing"
            assert e["outcome"] in ("applied", "approximated", "unexpressible"), e
    # Every class asks medium (the owner, 2026-09-25). Plain claude serves it
    # as asked; the one level lost on the broker is acknowledged in the file.
    assert all(routing.resolve(k, "anthropic", root=root)["effort"]["outcome"] == "applied"
               for k in routing.load_capabilities(root)["classes"])
    assert routing.resolve("code-low", "openrouter", root=root)["effort"]["source"].endswith("providers.openrouter")
    assert routing.resolve("code-low", "openrouter", root=root)["effort"]["level"] == "low"


def test_a_vendor_that_remaps_upward_is_not_clamped_down(tmp: str) -> None:
    """GLM-5.2 documents low/medium -> HIGH. A fabric that only ever
    clamped downward would ask for less thinking than sending the level
    untouched — the first cut of this did exactly that."""
    served, outcome = routing.ADAPTERS["openrouter"].effort_for(
        "z-ai/glm-5.2", "medium", list(routing.load_effort()["levels"]))
    assert (served, outcome) == ("high", "approximated"), (served, outcome)


def test_a_downgrade_is_refused_until_it_is_written_down(tmp: str) -> None:
    """The rule the dimension exists for: a level the provider will not
    give is a committed value with a note, or check() refuses."""
    root = scratch_root(tmp)
    path = os.path.join(root, "routing", "effort.json")
    doc = json.load(open(path, encoding="utf-8"))
    doc["providers"] = {}                      # drop both acknowledgements
    json.dump(doc, open(path, "w", encoding="utf-8"))
    findings = routing.check(root)
    assert any("code-plan" in f and "'high'" in f for f in findings), findings
    assert any("code-low" in f and "no effort at all" in f for f in findings), findings

    # An acknowledgement with no note is still refused: "with a note" is
    # the whole point, and a bare value is a downgrade nobody explained.
    doc["providers"] = {"anthropic": {"classes": {"code-low": None}},
                        "openrouter": {"classes": {"code-plan": "high", "code-review": "high"}}}
    json.dump(doc, open(path, "w", encoding="utf-8"))
    bare = [f for f in routing.check(root) if "notes" in f]
    assert len(bare) == 3, routing.check(root)

    for prov, klass in (("anthropic", "code-low"), ("openrouter", "code-plan"), ("openrouter", "code-review")):
        doc["providers"][prov].setdefault("notes", {})[klass] = "why, in one committed sentence"
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert not [f for f in routing.check(root) if "effort.json" in f], routing.check(root)

    # And an acknowledgement written for a model that has since changed is
    # re-judged, not trusted: it is keyed by class and outlives its model.
    doc["providers"]["openrouter"]["classes"]["code-plan"] = "low"
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert any("written for a different model" in f for f in routing.check(root)), routing.check(root)


def test_the_session_level_is_judged_like_a_class(tmp: str) -> None:
    """The session asks for a level on its own model: one the model lowers
    is refused until written down with a note, and an acknowledgement is
    re-judged when the model changes (PE1 of the #40 review)."""
    root = scratch_root(tmp)
    path = os.path.join(root, "routing", "effort.json")
    doc = json.load(open(path, encoding="utf-8"))
    doc["session"] = "xhigh"                  # the broker's session model gives high
    json.dump(doc, open(path, "w", encoding="utf-8"))
    lost = [f for f in routing.check(root) if "the session asks for 'xhigh'" in f]
    assert len(lost) == 1 and "openrouter" in lost[0] and "'high'" in lost[0], routing.check(root)
    doc["providers"].setdefault("openrouter", {})["session"] = "high"
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert any("providers.openrouter.session has no matching entry" in f for f in routing.check(root)), routing.check(root)
    doc["providers"]["openrouter"].setdefault("notes", {})["session"] = "why, in one committed sentence"
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert not [f for f in routing.check(root) if "session" in f], routing.check(root)
    doc["session"] = "max"                     # the acknowledgement now describes another request
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert any("providers.openrouter.session is 'high'" in f for f in routing.check(root)), routing.check(root)

    # Raised to the model's floor is refused too: "none" on Opus 5.5 is given "low".
    del doc["providers"]["openrouter"]["session"]
    doc["session"] = "none"
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert any("the session asks for 'none'" in f and "anthropic" in f and "'low'" in f
               for f in routing.check(root)), routing.check(root)

    # A session naming a class asks what the class asks after its own
    # acknowledgement: nothing is demanded twice (#57 blind review F4).
    # The broker session rides code-low's model, which serves low where the
    # class asks medium; code-low's acknowledgement already says so.
    doc["session"] = "code-low"
    json.dump(doc, open(path, "w", encoding="utf-8"))
    prof = os.path.join(root, "routing", "profiles.json")
    p = json.load(open(prof, encoding="utf-8"))
    p["defaults"]["providers"]["openrouter"]["session"] = "code-low"
    json.dump(p, open(prof, "w", encoding="utf-8"))
    assert routing.session_effort("openrouter", root=root) == "low"
    assert not [f for f in routing.check(root) if "the session asks" in f], routing.check(root)

    # A class acknowledged as `null` (its model takes no effort) settles a
    # session riding that class's model too (#57 re-review N1): on plain
    # claude, code-low on a Haiku model with providers.anthropic.classes
    # code-low null and its note.
    p["defaults"]["providers"]["anthropic"]["session"] = "code-low"
    json.dump(p, open(prof, "w", encoding="utf-8"))
    set_model(root, "anthropic", "code-low", "claude-haiku-4-5-20251001")
    assert routing.resolve_session(root=root, provider="anthropic")["model"] == "claude-haiku-4-5-20251001"
    doc.setdefault("providers", {}).setdefault("anthropic", {}).setdefault("classes", {})["code-low"] = None
    doc["providers"]["anthropic"].setdefault("notes", {})["code-low"] = "a model with no effort"
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert not [f for f in routing.check(root) if "the session asks" in f], routing.check(root)
    # A session acknowledgement beside the class's is read by nothing: said.
    doc["providers"]["anthropic"]["session"] = None
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert any("providers.anthropic.session is redundant" in f for f in routing.check(root)), routing.check(root)
    del doc["providers"]["anthropic"]["session"]
    json.dump(doc, open(path, "w", encoding="utf-8"))
    # And with no acknowledgement at all, the unexpressible session is told
    # to write null (the class is refused too, which is its own finding).
    doc["providers"]["anthropic"]["classes"].pop("code-low")
    doc["providers"]["anthropic"]["notes"].pop("code-low")
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert any("providers.anthropic.session: null" in f for f in routing.check(root)), routing.check(root)


def test_an_agent_layer_outranks_a_committed_acknowledgement(tmp: str) -> None:
    """The acknowledgement is the committed INTENT for a column, so it sits
    UNDER the profile and agent layers exactly as a model id does. It sat
    above them once, and an agent asking for a level its model admits was
    served the acknowledgement's instead (review 2026-09-23, F3)."""
    root = scratch_root(tmp)
    ack = routing.load_effort(root)["providers"]["openrouter"]["classes"]["code-plan"]
    assert routing.resolve("code-plan", "openrouter", root=root)["effort"]["intent"] == ack, \
        "with no layer the acknowledgement decides"
    local = {"providers": {"openrouter": {"effort": {"code-plan": "max"}}}}
    got = routing.resolve("code-plan", "openrouter", None, "someone", local, root=root)["effort"]
    assert got["intent"] == "max" and got["source"] == "local", got
    assert got["level"] == "max", f"the model admits max; the agent asked for it and must get it: {got}"


def test_a_level_below_the_models_floor_is_raised_not_dropped(tmp: str) -> None:
    """Asking for LESS than a model's lowest level once resolved to "this
    model has no effort", so nothing was sent and the vendor's own default
    applied — a silent UPGRADE on a model defaulting high (F5)."""
    root = scratch_root(tmp)
    scale = list(routing.load_effort(root)["levels"])
    adapter = routing.ADAPTERS["openrouter"]
    assert "minimal" not in adapter.effort_levels("z-ai/glm-5.3-flash")
    assert adapter.effort_for("z-ai/glm-5.3-flash", "minimal", scale) == ("low", "raised")
    assert adapter.effort_for("z-ai/glm-5.3-flash", "none", scale) == ("low", "raised")
    # …and check() says so in its own words, not as "expresses none".
    path = os.path.join(root, "routing", "effort.json")
    doc = json.load(open(path, encoding="utf-8"))
    doc["classes"]["code-low"] = "minimal"
    doc["providers"] = {}
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert any("admits nothing that low" in f for f in routing.check(root)), routing.check(root)


def test_no_model_pinned_is_not_a_claim_about_a_model(tmp: str) -> None:
    """`unexpressible` also meant "no model was given", and every printer
    stated it as a fact about the model (F6)."""
    root = scratch_root(tmp)
    scale = list(routing.load_effort(root)["levels"])
    assert routing.ADAPTERS["anthropic"].effort_for(None, "high", scale) == (None, "unknown-model")
    phrase = routing.effort_phrase({"outcome": "unknown-model", "intent": "high"})
    assert "no model pinned" in phrase and "expresses none" not in phrase, phrase
    assert "expresses none" in routing.effort_phrase({"outcome": "unexpressible", "intent": "high"})


def test_effort_names_every_class(tmp: str) -> None:
    root = scratch_root(tmp)
    path = os.path.join(root, "routing", "effort.json")
    doc = json.load(open(path, encoding="utf-8"))
    doc["classes"].pop("code-medium")
    json.dump(doc, open(path, "w", encoding="utf-8"))
    assert any("code-medium" in f and "effort.json" in f for f in routing.check(root)), routing.check(root)


def test_each_provider_validates_a_reference_through_its_adapter(tmp: str) -> None:
    """The rule for what a model reference is lives in one adapter per
    provider; check() and normalize_layer() ask it, so a provider column
    in capabilities.json with no adapter, or a resolution the adapter does
    not have, is a finding rather than an unguarded branch."""
    a = routing.ADAPTERS
    assert set(a) == set(routing.PROVIDERS) == {"openrouter", "anthropic"}
    assert a["openrouter"].is_model("z-ai/glm-5.3") and a["openrouter"].is_model("anthropic/claude-opus-5[1m]")
    assert not a["openrouter"].is_model("claude-opus-5") and not a["openrouter"].is_model("opus")
    assert a["anthropic"].is_model("claude-opus-5[1m]") and not a["anthropic"].is_model("anthropic/claude-opus-5")
    assert a["openrouter"].is_runtime("z-ai/glm-5.3@preset/glm2claude-shim") and not a["anthropic"].is_runtime("claude-opus-5@preset/x")
    assert a["anthropic"].openrouter_id("claude-opus-5") == "anthropic/claude-opus-5"
    assert a["openrouter"].column_findings("code-low", None, "w") == ["w.code-low is null; openrouter resolves by model id"]
    assert a["anthropic"].column_findings("code-low", None, "w") == []
    assert any("carries a preset" in f for f in a["openrouter"].column_findings("code-low", "z-ai/glm-5.3@preset/s", "w"))
    assert any("tier alias is the adapter" in f for f in a["anthropic"].column_findings("code-low", "opus", "w"))
    root = scratch_root(tmp)
    caps = json.load(open(os.path.join(root, "routing", "capabilities.json")))
    caps["providers"]["vertex"] = {"resolution": "model-id", "models": dict.fromkeys(caps["classes"], "google/gemini")}
    caps["providers"]["anthropic"]["resolution"] = "model-id"
    json.dump(caps, open(os.path.join(root, "routing", "capabilities.json"), "w"))
    findings = routing.check(root)
    assert any("providers.vertex has no adapter" in f for f in findings), findings
    assert any("providers.anthropic.resolution is 'model-id'" in f for f in findings), findings


def test_composite_is_derived_not_stored() -> None:
    # profiles.json is the operator's, judged by lint's profiles section: a
    # scan of the frozen fixture copy here could never fail.
    for path in (os.path.join(ROOT, "routing", "capabilities.json"), os.path.join(ROOT, "routing", "shims.json")):
        text = open(path, encoding="utf-8").read()
        assert "@preset/glm2claude-shim" not in text or path.endswith("shims.json"), \
            f"{path} carries a composite; the shim belongs only in shims.json"
    text = open(os.path.join(ROOT, "routing", "capabilities.json"), encoding="utf-8").read()
    assert "glm-5.3@" not in text


def test_a_non_glm_model_gets_no_shim(tmp: str) -> None:
    root = scratch_root(tmp)
    set_model(root, "openrouter", "code-high", "anthropic/claude-sonnet-5")
    res = routing.resolve("code-high", "openrouter", root=root)
    assert res["shim"] is None and res["composite"] == "anthropic/claude-sonnet-5", res
    set_model(root, "openrouter", "code-low", "meta-llama/llama-4-maverick")
    res = routing.resolve("code-low", "openrouter", root=root)
    assert res["shim"] is None and res["composite"] == "meta-llama/llama-4-maverick", res
    # The untouched class still gets its family shim: the two dimensions are independent.
    res = routing.resolve("code-medium", "openrouter", root=root)
    assert res["composite"] == "z-ai/glm-5.2@preset/glm2claude-shim", res
    # And the real files are untouched.
    # The engine's committed column, read from a fresh copy: the edits above were to `root`.
    assert routing.resolve("code-high", "openrouter", root=scratch_root(os.path.join(tmp, "b"), distinct=False))["composite"] == \
        "deepseek/deepseek-v4-pro-0813@preset/deepseek2claude-shim"


def test_shim_follows_the_family_of_the_merged_model(tmp: str) -> None:
    root = scratch_root(tmp)
    local = {"capabilities": {"code-low": "z-ai/glm-5.2", "code-high": "openai/gpt-5"}}
    assert routing.resolve("code-low", "openrouter", local=local, root=root)["composite"] == "z-ai/glm-5.2@preset/glm2claude-shim"
    assert routing.resolve("code-high", "openrouter", local=local, root=root)["composite"] == "openai/gpt-5"


def test_shim_subcommand_answers_for_a_bare_id_and_stays_quiet_otherwise(tmp: str) -> None:
    """A hook asks `routing.py shim <model>` rather than matching families
    itself: a bare id of a shimmed family prints the shim; a composite,
    a foreign family and a bare preset print nothing; every case exits 0."""
    cli = os.path.join(ROOT, "tools", "fabric", "routing.py")

    def ask(model: str) -> str:
        out = subprocess.run([sys.executable, cli, "shim", model], capture_output=True, text=True, check=True)
        return out.stdout.strip()

    assert ask("z-ai/glm-5.3") == GLM_SHIM
    assert ask("z-ai/glm-5.3" + GLM_SHIM) == GLM_SHIM      # composite: same family, same answer
    assert ask("anthropic/claude-opus-5") == ""
    assert ask("@preset/reviewer") == ""
    assert ask("not-a-model") == ""


def test_a_bare_preset_gets_nothing_attached() -> None:
    assert routing.shim_for("@preset/reviewer", routing.load_shims()) is None
    assert routing.composite("@preset/reviewer", None) == "@preset/reviewer"


def test_only_live_tested_families_have_a_shim() -> None:
    shims = routing.load_shims()
    assert [s["family"] for s in shims] == ["z-ai/glm-*", "deepseek/deepseek-v4*"], "no speculative families"
    for s in shims:
        assert s["tested"].startswith("2026-"), f"{s['family']}: a shim is added only with a live check"
    assert routing.shim_for("deepseek/deepseek-v4-pro-0813", shims) == "@preset/deepseek2claude-shim"
    assert routing.shim_for("deepseek/deepseek-v3", shims) is None, "v3 was never checked"


def test_review_grade_gate_is_on_review_only(tmp: str) -> None:
    root = scratch_root(tmp)
    assert routing.review_grade_ok("anthropic/claude-opus-5", root)
    assert routing.review_grade_ok("anthropic/claude-opus-5[1m]", root)
    assert routing.review_grade_ok("z-ai/glm-5.3", root), "admitted by architect-cto 2026-09-13"
    assert not routing.review_grade_ok("z-ai/glm-5.3-flash", root)
    assert not routing.review_grade_ok("z-ai/glm-5.2", root)
    set_model(root, "openrouter", "code-review", "z-ai/glm-5.3-flash")
    findings = routing.check(root)
    assert any("code-review" in f and "review-grade" in f for f in findings), findings
    root2 = scratch_root(tmp + "/b") if os.path.isdir(tmp + "/b") else scratch_root(os.path.join(tmp, "b"))
    set_model(root2, "openrouter", "code-high", "z-ai/glm-5.3-flash")
    assert not [f for f in routing.check(root2) if "review-grade" in f], "a coding class is not review-gated"


def test_check_refuses_a_preset_as_a_model(tmp: str) -> None:
    root = scratch_root(tmp)
    set_model(root, "openrouter", "code-low", "@preset/glm2claude-shim")
    findings = routing.check(root)
    assert any("preset" in f for f in findings), findings


def test_every_shim_has_its_source_under_version_control(tmp: str) -> None:
    """A shim is an OpenRouter preset; its text lives in routing/shims/<slug>/
    so it can be diffed, rebuilt and pushed (tools/fabric/shim.py). An entry
    whose source is missing is a finding, not a silent gap."""
    root = scratch_root(tmp)
    assert not routing.check(root), routing.check(root)
    shutil.rmtree(os.path.join(root, "routing", "shims", "glm2claude-shim"))
    findings = routing.check(root)
    assert any("no source under routing/shims/glm2claude-shim/" in f for f in findings), findings
    path = os.path.join(root, "routing", "shims.json")
    d = json.load(open(path, encoding="utf-8"))
    d["shims"].append({"family": "acme/*", "shim": "@preset/acme2claude-shim", "harness": "claude-code",
                       "tested": "never", "note": "a fixture"})
    json.dump(d, open(path, "w", encoding="utf-8"))
    findings = routing.check(root)
    assert any("acme2claude-shim' has no source" in f for f in findings), findings


def test_every_class_rides_an_alias_and_only_the_review_class_shares(tmp: str) -> None:
    """The Agent tool accepts only tier aliases, so nothing may be `declared`
    by full id; one alias carries one export, so two exporting classes
    cannot share one — the review class may share code-plan's fable only
    because it is file_pinned, and the gated class must be."""
    aliases = json.load(open(os.path.join(ROOT, "runtime", "claude-code", "aliases.json")))
    assert "declared" not in aliases
    assert aliases["aliases"]["code-review"] == "fable" == aliases["aliases"]["code-plan"]
    assert aliases["aliases"]["code-high"] == "opus"
    assert aliases["file_pinned"] == ["code-review"]
    root = scratch_root(tmp)
    path = os.path.join(root, "runtime", "claude-code", "aliases.json")
    d = json.load(open(path))
    d["declared"] = {"code-review": d["aliases"].pop("code-review")}
    json.dump(d, open(path, "w"))
    findings = routing.check(root)
    assert any("declared" in f and "retired" in f for f in findings), findings
    d = json.load(open(os.path.join(ROOT, "runtime", "claude-code", "aliases.json")))
    d["file_pinned"] = []
    json.dump(d, open(path, "w"))
    findings = routing.check(root)
    assert any("share the fable alias" in f for f in findings), findings
    assert any("gated class" in f and "not file_pinned" in f for f in findings), findings
    try:
        routing.exports("anthropic", root=root)  # fable-5-1 for code-plan, opus-5-5 for the reviewer: one export cannot carry both
    except KeyError as exc:
        assert "both ride fable" in str(exc), exc
    else:
        raise AssertionError("two exporting classes on one alias resolved to different models without complaint")


def test_committed_files_are_clean(tmp: str) -> None:
    """The engine's committed column, effort and aliases against the
    fixture overlay and grade. The operator's own overlay is judged where it
    lives: tools/fabric/lint.py's profiles section."""
    root = scratch_root(tmp, distinct=False)
    assert routing.check(root) == []
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fabric", "routing.py"), "check"],
                          capture_output=True, text=True, env={**os.environ, "AGENT_FABRIC_ROOT": root})
    assert proc.returncode == 0, proc.stdout + proc.stderr


def main() -> int:
    cases = [
        test_current_broker_policy,
        test_native_path_pins_haiku_and_sonnet_5_5_low_and_opus_5_5_above,
        test_a_null_in_the_harness_column_is_the_harness_tier,
        test_effort_is_one_vocabulary_resolved_per_class,
        test_a_vendor_that_remaps_upward_is_not_clamped_down,
        test_a_downgrade_is_refused_until_it_is_written_down,
        test_the_session_level_is_judged_like_a_class,
        test_an_agent_layer_outranks_a_committed_acknowledgement,
        test_a_level_below_the_models_floor_is_raised_not_dropped,
        test_no_model_pinned_is_not_a_claim_about_a_model,
        test_effort_names_every_class,
        test_each_provider_validates_a_reference_through_its_adapter,
        test_composite_is_derived_not_stored,
        test_a_non_glm_model_gets_no_shim,
        test_shim_follows_the_family_of_the_merged_model,
        test_a_bare_preset_gets_nothing_attached,
        test_shim_subcommand_answers_for_a_bare_id_and_stays_quiet_otherwise,
        test_only_live_tested_families_have_a_shim,
        test_a_layer_is_per_provider,
        test_a_layer_is_validated_in_its_provider_vocabulary,
        test_review_grade_gate_is_on_review_only,
        test_check_refuses_a_preset_as_a_model,
        test_every_shim_has_its_source_under_version_control,
        test_every_class_rides_an_alias_and_only_the_review_class_shares,
        test_committed_files_are_clean,
    ]
    failures = 0
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                case(tmp) if case.__code__.co_argcount else case()
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
