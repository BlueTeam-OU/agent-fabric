#!/usr/bin/env python3
"""Behavioural tests for tools/fabric/assemble.py and tools/fabric/lint.py.

Stdlib only; runnable as `python3 test_assemble.py` or under pytest.

The assembler's value is that it is boring: distillers judge, and this puts
the results in the same place every time. So the cases here are about the
properties that make a drain reviewable — identical claims producing an
identical tree, an index that cannot drift from the files beside it, a
slice that splits before it grows past what a session can afford to load —
plus the two refusals that must never be silent: content that should not be
committed, and knowledge quietly duplicated into two roles that will
disagree later.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSEMBLE = os.path.join(ROOT, "tools", "fabric", "assemble.py")
LINT = os.path.join(ROOT, "tools", "fabric", "lint.py")
SCHEMA_DIR = os.path.join(ROOT, "identities", "schemas")
PROMPT_DIR = os.path.join(ROOT, "identities", "prompt")


def lint_inputs(out: str) -> None:
    """The committed inputs lint wants beyond what the assembler writes:
    the real schemas, and the launch-prompt sections (identities/prompt/,
    checked by name)."""
    import shutil
    if os.path.isdir(SCHEMA_DIR):
        shutil.copytree(SCHEMA_DIR, os.path.join(out, "identities", "schemas"), dirs_exist_ok=True)
    if os.path.isdir(PROMPT_DIR):
        shutil.copytree(PROMPT_DIR, os.path.join(out, "identities", "prompt"), dirs_exist_ok=True)

OBSERVATIONS = [
    {"content_hash": "h1", "clone_id": "clone-aaa", "host": "hostA"},
    {"content_hash": "h2", "clone_id": "clone-bbb", "host": "hostB"},
    {"content_hash": "h3", "clone_id": None, "host": "hostA"},
]
REFERENCES = {
    "h1": {"adrs": ["ADR-054"], "prs": ["#428"]},
    "h2": {"migrations": ["migration-007"]},
}


def claims(role: str, items: list[dict]) -> dict:
    return {"role": role, "telemetry": {"observations_in": 10, "admitted": len(items),
                                        "rejected": 3}, "claims": items}


def build(tmp: str, claim_files: dict[str, dict]) -> tuple[str, str, str]:
    drain = os.path.join(tmp, "drain")
    claims_dir = os.path.join(tmp, "claims")
    out = os.path.join(tmp, "roles")
    os.makedirs(drain, exist_ok=True)
    os.makedirs(claims_dir, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(drain, "references.json"), "w", encoding="utf-8") as fh:
        json.dump(REFERENCES, fh)
    with open(os.path.join(drain, "observations.jsonl"), "w", encoding="utf-8") as fh:
        for row in OBSERVATIONS:
            fh.write(json.dumps(row) + "\n")
    for role, payload in claim_files.items():
        with open(os.path.join(claims_dir, f"{role}.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    return drain, claims_dir, out


PROJECT = "demo"


def working_copy(out: str) -> str:
    """The demo project's checkout: project memory lives IN the project, under
    <working copy>/.agent-fabric/memory/. Kept beside the throwaway fabric root."""
    return os.path.join(out, "wc-" + PROJECT)


HYGIENE = {"patterns": [{"pattern": "\\bspringfield\\b", "flags": "i", "label": "city name"}]}


def run_assemble(drain: str, claims_dir: str, out: str, *extra: str) -> subprocess.CompletedProcess:
    """`out` is a throwaway agent-fabric root; domain slices land under its
    memory/domains/<role>/, project slices under the demo working copy's
    .agent-fabric/memory/<role>/. The working copy carries the project's
    hygiene list (a city name), as a real one does."""
    os.makedirs(os.path.join(working_copy(out), ".agent-fabric"), exist_ok=True)
    hyg = os.path.join(working_copy(out), ".agent-fabric", "hygiene.json")
    if not os.path.exists(hyg):
        with open(hyg, "w", encoding="utf-8") as fh:
            json.dump(HYGIENE, fh)
    return subprocess.run(
        [sys.executable, ASSEMBLE, "--claims", claims_dir, "--drain", drain,
         "--fabric", out, "--project", PROJECT, "--working-copy", working_copy(out),
         "--stamp", "2026-01-01", *extra],
        capture_output=True, text=True,
    )


def dom(out: str, role: str, *rest: str) -> str:
    return os.path.join(out, "memory", "domains", role, *rest)


def proj(out: str, role: str, *rest: str) -> str:
    return os.path.join(working_copy(out), ".agent-fabric", "memory", role, *rest)


def ident(out: str, role: str, *rest: str) -> str:
    # Authored identity is never created by the assembler; the fixture
    # makes room for a hand-written charter.
    os.makedirs(os.path.join(out, "identities", "roles", role), exist_ok=True)
    return os.path.join(out, "identities", "roles", role, *rest)


def shared_path(out: str, filename: str) -> str:
    return os.path.join(out, "memory", "shared", filename)


def report_path(out: str) -> str:
    """The drain report lives with the project memory it describes."""
    return os.path.join(working_copy(out), ".agent-fabric", "memory", "last-drain-report.json")


def walk_role(out: str, role: str):
    """Every file a role's knowledge is spread over: its domain and project directories."""
    for base in (dom(out, role), proj(out, role)):
        yield from os.walk(base)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_places_claims_and_writes_provenance(tmp: str) -> None:
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "ble", "title": "Advertisements are one-way",
         "body": "A passive beacon emits and never listens.", "evidence": ["h1", "h2"],
         "citations": {"adrs": ["ADR-054"]}},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    slice_path = dom(out, "alpha", "domain.md")
    text = read(slice_path)
    assert "role: alpha" in text and "class: domain" in text
    assert "derived_from:" in text and "- h1" in text
    # Provenance must name the clones, so a claim stays traceable after the
    # source store is gone.
    assert "clone-aaa" in text and "clone-bbb" in text
    assert "ADR-054" in text


def test_unresolved_origin_is_stated_not_invented(tmp: str) -> None:
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "x", "body": "b", "evidence": ["h3"]},
    ])})
    run_assemble(drain, claims_dir, out)
    assert "unresolved" in read(dom(out, "alpha", "domain.md"))


def test_index_lists_every_slice(tmp: str) -> None:
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "First", "body": "b", "evidence": ["h1"]},
        {"class": "domain", "topic": "two", "title": "Second", "body": "b", "evidence": ["h1"]},
        {"class": "workflow", "topic": "how", "title": "Third", "body": "b", "evidence": ["h2"]},
    ])})
    run_assemble(drain, claims_dir, out)
    index = read(proj(out, "alpha", "INDEX.md"))
    assert "domain/one.md" in index and "domain/two.md" in index
    assert "workflow.md" in index
    # The description is the retrieval cue: without it the index is a file
    # listing, and a session has no basis for choosing what to open.
    assert "First" in index and "Third" in index


def test_index_banner_names_which_sections_load_when(tmp: str) -> None:
    # The banner says what a session is given — the charter and brief, the
    # remit and this index's pointer — and that a workflow slice is read
    # before the work it governs. It once claimed the hook gave every
    # workflow slice, which no hook did.
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "workflow", "topic": "how", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    run_assemble(drain, claims_dir, out)
    index = read(proj(out, "alpha", "INDEX.md"))
    assert "is given" in index and "launch prompt" in index and "session-start hook" in index, index
    assert "Everything below loads on demand" not in index, index
    # And it never again claims the hook gives the workflow slices, which
    # no hook does (ADR-013 §7): they are cued, read before the work.
    assert "every `workflow` slice (from the session-start hook)" not in index, index
    assert "nothing below" in index and "before that work" in index, index


def test_committed_indexes_carry_the_banner_the_assembler_emits(tmp: str) -> None:
    """The committed tree must match what a drain would write.

    INDEX.md is generated, so the banner exists in two places: this
    assembler, and ten committed files. Nothing else compares them — and a
    generator that disagrees with the tree beside it is exactly the defect
    that stranded the tier-1 workflow slices, one level up.
    """
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "workflow", "topic": "how", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    run_assemble(drain, claims_dir, out)
    generated = read(proj(out, "alpha", "INDEX.md"))

    # The banner is the block between the H1 and the first section heading.
    body = generated.split("# alpha — knowledge index\n", 1)[1]
    banner = body.split("\n## ", 1)[0].strip()
    assert banner, generated

    # The committed project indexes this repository holds: its own, under
    # .agent-fabric/memory/<role>/INDEX.md (a managed project's live in that
    # project's repository and are checked there by lint).
    roles_dir = os.path.join(ROOT, ".agent-fabric", "memory")
    committed = sorted(
        os.path.join(roles_dir, d, "INDEX.md") for d in os.listdir(roles_dir)
        if os.path.isfile(os.path.join(roles_dir, d, "INDEX.md")))
    assert committed, "no committed role indexes found"
    for path in committed:
        assert banner in read(path), (
            f"{os.path.relpath(path, roles_dir)} does not carry the assembler's "
            f"current banner — regenerate it or revert the generator:\n{banner}")


def test_fabric_links_use_the_sibling_prefix_even_when_the_checkout_is_nested(tmp: str) -> None:
    """CI checks agent-fabric out INSIDE the working copy. A fabric slice is
    still linked as ../agent-fabric/<path>: the prefix names the layout the
    adapters assume, never where this run put the checkout. Caught live:
    an index linted clean beside a sibling checkout and drifted in CI."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    import importlib
    layout = importlib.import_module("layout")
    wc = os.path.join(tmp, "wc")
    nested_fabric = os.path.join(wc, "_agent-fabric")
    os.makedirs(os.path.join(nested_fabric, "memory", "domains", "web-dev"))
    os.makedirs(os.path.join(wc, ".agent-fabric", "memory", "web-dev"))
    saved = layout.FABRIC_ROOT
    try:
        layout.FABRIC_ROOT = nested_fabric
        layout.set_working_copy("demo", wc)
        slice_ = os.path.join(nested_fabric, "memory", "domains", "web-dev", "x.md")
        assert layout.link_rel(slice_, "demo") == "../agent-fabric/memory/domains/web-dev/x.md"
        own = os.path.join(wc, ".agent-fabric", "memory", "web-dev", "y.md")
        assert layout.link_rel(own, "demo") == ".agent-fabric/memory/web-dev/y.md"
        assert layout.resolve_link("../agent-fabric/memory/domains/web-dev/x.md", "demo") == slice_
    finally:
        layout.FABRIC_ROOT = saved
        layout.set_working_copy("demo", None)


def test_drain_report_carries_the_watermark_forward(tmp: str) -> None:
    """The committed record must answer "since when" for the next drain.

    The watermark was written only into the drain directory's
    harvest-report.json, which is temporary. Losing it meant the next cycle
    had nothing but the stamp date to work back from, by hand, per store.
    """
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    with open(os.path.join(drain, "harvest-report.json"), "w", encoding="utf-8") as fh:
        json.dump({"host": "boxA", "database": "/home/someone/.claude-mem/claude-mem.db",
                   "since_watermark": 1000, "next_watermark": 2500,
                   "counts": {"provisional_agent": 0, "in_scope": 7}}, fh)
    run_assemble(drain, claims_dir, out)
    report = json.loads(read(report_path(out)))

    # .get throughout: a missing key must fail this test with a readable
    # message, not raise KeyError and abort the whole suite behind it.
    # Keyed agent@host: every account on a host has its own store.
    assert list((report.get("watermarks") or {}).values()) == [2500] and \
        all(k.endswith("@boxA") for k in report["watermarks"]), report.get("watermarks")
    harvest = report.get("harvest") or {}
    assert harvest.get("next_watermark") == 2500, harvest
    assert harvest.get("since_watermark") == 1000, harvest
    assert harvest.get("host") == "boxA", harvest
    # An absolute path into somebody's home must not be committed.
    assert "database" not in harvest, harvest
    assert "/home/someone" not in read(report_path(out))


def test_drain_report_records_unattributable_rows(tmp: str) -> None:
    # A row that resolves to no clone is reported provisional and never
    # guessed — but nothing downstream read the tally, so a drain in which
    # every row was unattributable landed looking exactly like a clean one.
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    with open(os.path.join(drain, "harvest-report.json"), "w", encoding="utf-8") as fh:
        json.dump({"host": "boxA", "since_watermark": 0, "next_watermark": 9,
                   "counts": {"provisional_agent": 41, "in_scope": 41}}, fh)
    run_assemble(drain, claims_dir, out)
    report = json.loads(read(report_path(out)))
    harvest = report.get("harvest") or {}
    assert harvest.get("provisional_agent") == 41, harvest
    assert harvest.get("in_scope") == 41, harvest


def test_drain_report_tolerates_a_drain_with_no_harvest_report(tmp: str) -> None:
    # A hand-built drain directory is legitimate — the assembler must not
    # require the harvester to have run, only benefit from it when it did.
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(read(report_path(out)))
    assert report.get("harvest", "MISSING") is None, report.get("harvest", "MISSING")
    assert report.get("watermarks", "MISSING") == {}, report.get("watermarks", "MISSING")


def test_unattributable_rows_warn_loudly_but_do_not_fail_the_drain(tmp: str) -> None:
    """Provisional bindings are reported, never guessed — and never a gate.

    Gating would refuse valid knowledge over a registry gap the assembler
    cannot fix: a clone mints its own id, so it cannot be minted from here.
    """
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    with open(os.path.join(drain, "harvest-report.json"), "w", encoding="utf-8") as fh:
        json.dump({"host": "boxA", "since_watermark": 0, "next_watermark": 9,
                   "counts": {"provisional_agent": 41, "in_scope": 60}}, fh)
    proc = run_assemble(drain, claims_dir, out)

    assert proc.returncode == 0, "an unattributable row is knowledge, not a failure"
    assert "PROVISIONAL BINDINGS" in proc.stderr, proc.stderr
    assert "41 of 60" in proc.stderr, proc.stderr
    # The remedy has to be in the message: it is not doable from here.
    assert "harvest_memory.py" in proc.stderr, proc.stderr


def test_a_fully_attributed_drain_says_nothing_about_bindings(tmp: str) -> None:
    # A warning that fires on a clean drain is noise, and noise is how a real
    # one gets ignored.
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    with open(os.path.join(drain, "harvest-report.json"), "w", encoding="utf-8") as fh:
        json.dump({"host": "boxA", "since_watermark": 0, "next_watermark": 9,
                   "counts": {"provisional_agent": 0, "in_scope": 60}}, fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "PROVISIONAL" not in proc.stderr, proc.stderr


def test_output_is_byte_stable(tmp: str) -> None:
    """The same drain assembled twice is the same tree — every file, and no
    new one. The bodies are sized so the slice sits past HALF its budget:
    with tiny bodies this case passed while a re-run of a real drain split
    the slice into `-2` (2026-09-17), because the carried sections and the
    same claims re-rendered were both counted toward the budget."""
    body = ("A durable fact about the field, stated once. " * 60).strip()
    payload = {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": f"Fact {i}", "body": body, "evidence": ["h1"]}
        for i in range(2)
    ] + [
        {"class": "solution", "topic": "two", "title": "U", "body": body, "evidence": ["h2"]},
    ])}
    drain, claims_dir, out = build(tmp, payload)
    run_assemble(drain, claims_dir, out)
    def snapshot() -> dict[str, str]:
        return {os.path.join(d, n): read(os.path.join(d, n)) for d, _ds, fs in os.walk(out) for n in fs}
    first = snapshot()
    assert not [p for p in first if p.endswith("-2.md")], "the fixture must fit one part on the first run"
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    second = snapshot()
    assert set(second) == set(first), f"files appeared or vanished: {sorted(set(second) ^ set(first))}"
    for path, before in first.items():
        assert second[path] == before, f"{path} differs between identical runs"


def test_slice_splits_when_it_exceeds_budget(tmp: str) -> None:
    big = "x " * 3000  # comfortably past a small budget
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "big", "title": "A", "body": big, "evidence": ["h1"]},
        {"class": "domain", "topic": "big", "title": "B", "body": big, "evidence": ["h2"]},
    ])})
    run_assemble(drain, claims_dir, out, "--budget", "500")
    files = sorted(os.listdir(dom(out, "alpha", "domain")))
    assert len(files) >= 2, f"expected a split, got {files}"


def test_budget_accounts_for_what_merge_mode_carries(tmp: str) -> None:
    """Each drain split its OWN claims correctly, then merge mode added every
    earlier section back underneath.

    So a slice crept past the budget across cycles while no single run ever
    looked wrong — until the mandatory lint budget check failed on a tree
    nobody had touched. The split has to size the combined old-and-new body.
    """
    big = "y " * 900
    first = {"alpha": claims("alpha", [
        {"class": "domain", "topic": "grow", "title": "First", "body": big,
         "evidence": ["h1"]},
    ])}
    drain, claims_dir, out = build(tmp, first)
    run_assemble(drain, claims_dir, out, "--budget", "500")

    # A second, separately-small drain into the SAME topic.
    second = claims("alpha", [
        {"class": "domain", "topic": "grow", "title": "Second", "body": big,
         "evidence": ["h2"]},
    ])
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(second, fh)
    proc = run_assemble(drain, claims_dir, out, "--budget", "500")
    assert proc.returncode == 0, proc.stderr

    # Whichever layout it chose, no single slice may exceed the budget.
    limit = 500 * 4
    oversized = []
    for dirpath, _dirs, files in walk_role(out, "alpha"):
        for name in files:
            if not name.endswith(".md") or name == "INDEX.md":
                continue
            full = os.path.join(dirpath, name)
            size = len(read(full))
            if size > limit * 1.5:      # generous: frontmatter is not free
                oversized.append((os.path.relpath(full, out), size))
    assert not oversized, f"a slice grew past its budget across drains: {oversized}"

    # And both drains' content still exists somewhere.
    everything = ""
    for dirpath, _dirs, files in walk_role(out, "alpha"):
        for name in files:
            everything += read(os.path.join(dirpath, name))
    assert "First" in everything and "Second" in everything, \
        "carrying must not be traded away for staying inside budget"


def test_claim_owned_by_two_roles_is_stored_once(tmp: str) -> None:
    shared_claim = {"class": "domain", "topic": "observability",
                    "title": "Dashboards are shared", "body": "One metrics stack serves both.",
                    "evidence": ["h1"], "shared_with": ["beta"]}
    drain, claims_dir, out = build(tmp, {
        "alpha": claims("alpha", [shared_claim]),
        "beta": claims("beta", [
            {"class": "workflow", "topic": "own", "title": "Own", "body": "b", "evidence": ["h2"]},
        ]),
    })
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    shared_file = shared_path(out, "domain-observability.md")
    assert os.path.exists(shared_file), "a multi-owner claim belongs in shared/"
    assert not os.path.exists(dom(out, "alpha", "domain.md")), \
        "it must not also be copied into the owning role"
    for role in ("alpha", "beta"):
        index = read(proj(out, role, "INDEX.md"))
        assert "shared/domain-observability.md" in index, f"{role} must point at the shared slice"


def test_shared_claims_reach_every_owner_crossref(tmp: str) -> None:
    """A multi-owner claim is routed OUT of per_role and into shared, and the
    citation graph iterated per_role alone.

    So every observation, ADR, PR and migration edge behind shared knowledge
    was missing from both owners' crossref.json. INDEX.md pointed at the
    shared slice correctly, which is what made it invisible: only a
    citation-graph query could see it, and it silently under-reported.
    """
    shared_claim = {"class": "domain", "topic": "observability",
                    "title": "Dashboards are shared", "body": "One metrics stack serves both.",
                    "evidence": ["h1"], "shared_with": ["beta"]}
    drain, claims_dir, out = build(tmp, {
        "alpha": claims("alpha", [shared_claim]),
        "beta": claims("beta", [
            {"class": "workflow", "topic": "own", "title": "Own", "body": "b", "evidence": ["h2"]},
        ]),
    })
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr

    # h1 carries ADR-054 and PR #428 per the fixture, so BOTH owners must be
    # able to answer "what backs my knowledge of ADR-054".
    for role in ("alpha", "beta"):
        with open(proj(out, role, "crossref.json"), encoding="utf-8") as fh:
            index = json.load(fh)["index"]
        assert "ADR-054" in index.get("adrs", {}), \
            f"{role} crossref lost the shared claim's ADR edge: {index}"
        node = index["adrs"]["ADR-054"]
        assert "h1" in node["observations"], node
        assert any("observability" in sl for sl in node["slices"]), node


def test_crossref_maps_artifacts_to_slices(tmp: str) -> None:
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    run_assemble(drain, claims_dir, out)
    with open(proj(out, "alpha", "crossref.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    entry = doc["index"]["adrs"]["ADR-054"]
    assert entry["observations"] == ["h1"]
    assert entry["slices"] == ["domain:one"]


def test_an_empty_crossref_is_said_not_just_written(tmp: str) -> None:
    """A memory drain carries an empty references.json, so the graph it
    writes is empty; the file exists all the same and read as one that
    answers. The run says which index came out empty, and stays clean."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    with open(os.path.join(drain, "references.json"), "w", encoding="utf-8") as fh:
        json.dump({}, fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    with open(proj(out, "alpha", "crossref.json"), encoding="utf-8") as fh:
        assert json.load(fh)["index"] == {}
    assert "CROSSREF EMPTY" in proc.stderr, proc.stderr
    assert ".agent-fabric/memory/alpha/crossref.json" in proc.stderr, proc.stderr


def test_a_crossref_with_entries_says_nothing(tmp: str) -> None:
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "CROSSREF EMPTY" not in proc.stderr, proc.stderr


def test_merge_mode_preserves_earlier_drains(tmp: str) -> None:
    """The second drain renders only what it admitted. Writing that alone
    would delete what the first drain learned, so prior sections are carried
    forward and their provenance unions."""
    first = {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Learned in cycle one",
         "body": "The original finding.", "evidence": ["h1"]},
    ])}
    drain, claims_dir, out = build(tmp, first)
    run_assemble(drain, claims_dir, out)

    second = claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Learned in cycle two",
         "body": "A later, unrelated finding.", "evidence": ["h2"]},
    ])
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(second, fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr

    text = read(dom(out, "alpha", "domain.md"))
    assert "Learned in cycle one" in text, "the earlier drain's claim was destroyed"
    assert "Learned in cycle two" in text, "the new claim is missing"
    assert "- h1" in text and "- h2" in text, "provenance must union across drains"


def test_index_keeps_slices_this_drain_did_not_touch(tmp: str) -> None:
    """Merge mode rewrites only the slices a claim touched. The index is the
    ONLY thing a session reads before deciding what to load, so an index built
    from just this run's writes silently retires every untouched slice. On the
    first drain everything is written and this cannot be seen; the second drain
    dropped 101 entries across ten roles before it was caught."""
    first = {"alpha": claims("alpha", [
        {"class": "domain", "topic": "kept", "title": "Learned in cycle one",
         "body": "b", "evidence": ["h1"]},
    ])}
    drain, claims_dir, out = build(tmp, first)
    run_assemble(drain, claims_dir, out)
    assert "domain.md" in read(proj(out, "alpha", "INDEX.md"))

    second = claims("alpha", [
        {"class": "workflow", "topic": "fresh", "title": "Learned in cycle two",
         "body": "b", "evidence": ["h2"]},
    ])
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(second, fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr

    index = read(proj(out, "alpha", "INDEX.md"))
    assert "workflow.md" in index, "the new slice is missing from the index"
    assert "domain.md" in index, "an untouched slice vanished from the index"


def test_a_title_containing_a_newline_is_not_truncated(tmp: str) -> None:
    """`text.strip() != text` catches only leading and trailing whitespace, so
    an interior newline is written raw. parse_frontmatter then keeps the first
    line and silently drops the rest — and the index entry for that slice would
    differ depending on whether a drain touched it, since the write path has the
    full title and the on-disk scan reads only the truncated one."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "first line\nsecond line",
         "body": "b", "evidence": ["h1", "h2"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr

    text = read(dom(out, "alpha", "domain.md"))
    meta = text.split("---")[1]
    desc = [l for l in meta.splitlines() if l.startswith("description:")]
    assert len(desc) == 1, f"description spilled across lines: {meta}"
    assert "second line" in desc[0], "the tail of the title was dropped from frontmatter"
    assert "second line" in read(proj(out, "alpha", "INDEX.md"))


def test_a_class_never_gets_both_a_flat_file_and_a_directory(tmp: str) -> None:
    """switch.py takes the directory branch and skips the flat file, so a class
    holding both has an unreachable half — at tier 1 that silently retires
    knowledge the index promises loads at activation. The layout must follow the
    TREE, not this drain's topic count, or a class that has already split gains a
    flat file the moment a later drain touches exactly one topic in it."""
    first = {"alpha": claims("alpha", [
        {"class": "workflow", "topic": "aaa", "title": "A", "body": "b", "evidence": ["h1"]},
        {"class": "workflow", "topic": "bbb", "title": "B", "body": "b", "evidence": ["h2"]},
    ])}
    drain, claims_dir, out = build(tmp, first)
    run_assemble(drain, claims_dir, out)
    assert os.path.isdir(proj(out, "alpha", "workflow")), "expected a split class"

    second = claims("alpha", [
        {"class": "workflow", "topic": "aaa", "title": "A again", "body": "b", "evidence": ["h3"]},
    ])
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(second, fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr

    flat = proj(out, "alpha", "workflow.md")
    assert not os.path.exists(flat), "a split class gained an unreachable flat file"
    assert "A again" in read(proj(out, "alpha", "workflow", "aaa.md"))


def test_a_hash_shaped_like_a_number_survives_the_frontmatter(tmp: str) -> None:
    """Content hashes are hex, so some are digits plus an `e` —
    `23258632804400e6` is a valid hash and a valid YAML float. Emitted bare it
    reads back as 2.3e+19 and the hash is gone. One reached a committed slice
    and lint caught it only as a type error on derived_from."""
    tricky = "23258632804400e6"
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b",
         "evidence": [tricky, "1234567890123456", "1.5", "true"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr

    text = read(dom(out, "alpha", "domain.md"))
    assert f'"{tricky}"' in text, "a number-shaped hash was emitted unquoted"

    # Only the derived_from list: `origin:` renders nested mappings, not scalars.
    meta = text.split("---")[1].splitlines()
    start = next(i for i, l in enumerate(meta) if l.strip() == "derived_from:")
    for line in meta[start + 1:]:
        item = line.strip()
        if not item.startswith("- "):
            break
        assert item[2:].startswith('"'), f"unquoted ambiguous scalar: {item}"


def test_carried_full_scope_survives_a_domain_only_drain(tmp: str) -> None:
    """`knowledge_scope` was computed from the CURRENT drain's claims alone.

    A cycle contributing only domain-only claims to a slice that already
    held a full-scope section relabelled the whole file `domain-only` while
    the system-specific text was still in it — defeating the cross-project
    boundary the field draws. `full` has to win over anything carried.
    """
    first = {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "System specific finding",
         "body": "How this deployment wires it.", "evidence": ["h1"],
         "knowledge_scope": "full"},
    ])}
    drain, claims_dir, out = build(tmp, first)
    run_assemble(drain, claims_dir, out)
    path = dom(out, "alpha", "domain.md")
    assert "knowledge_scope: full" in read(path), read(path)

    second = claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Transferable finding",
         "body": "True of the field generally.", "evidence": ["h2"],
         "knowledge_scope": "domain-only"},
    ])
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(second, fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr

    text = read(path)
    assert "System specific finding" in text, "the full-scope section is still carried"
    assert "knowledge_scope: full" in text, \
        "a carried full-scope section must keep the file full-scope:\n" + text


def test_merge_target_strengthens_instead_of_appending(tmp: str) -> None:
    """Naming an existing heading replaces that section rather than adding a
    near-duplicate beside it — what keeps a long-lived file dense."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "The finding",
         "body": "First statement of it.", "evidence": ["h1"]},
    ])})
    run_assemble(drain, claims_dir, out)
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "domain", "topic": "one", "title": "The finding",
             "merge_target": "The finding",
             "body": "Sharper statement, with the extra evidence.",
             "evidence": ["h2"]},
        ]), fh)
    run_assemble(drain, claims_dir, out)
    text = read(dom(out, "alpha", "domain.md"))
    assert text.count("## The finding") == 1, "merge_target must not duplicate the section"
    assert "Sharper statement" in text
    assert "First statement" not in text, "the strengthened claim replaces the old text"


def decisions_file(tmp: str, decisions: dict[str, str]) -> str:
    path = os.path.join(tmp, "decisions.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh)
    return path


def keep_both(tmp: str, *keys: str) -> tuple[str, str]:
    """The owner's decision the collision fixtures need: both stand."""
    return ("--collision-decisions", decisions_file(tmp, {k: "keep-both" for k in keys}))


def test_a_collision_stops_the_drain_until_the_owner_decides(tmp: str) -> None:
    """Two claims under one heading with different text is a potential
    supersession — a workflow that changed, or a memory that is wrong —
    and the assembler cannot tell which (the owner, 2026-09-20). It writes
    nothing, exits 1 and names the pair with both texts and dates; the
    re-run carries the owner's decision. keep-both is the old shape:
    both stand, dated, and the collision is reported."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Same title",
         "body": "The first claim.", "evidence": ["h1"], "observed_at": "2026-08-30"},
        {"class": "domain", "topic": "one", "title": "Same title",
         "body": "A genuinely different second claim.", "evidence": ["h2"], "observed_at": "2026-09-18"},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1, proc.stderr
    assert "SUPERSEDING?" in proc.stderr and "alpha/domain:one#Same title" in proc.stderr, proc.stderr
    assert "observed 2026-08-30" in proc.stderr and "observed 2026-09-18" in proc.stderr, proc.stderr
    assert "The first claim." in proc.stderr and "A genuinely different second claim." in proc.stderr, proc.stderr
    assert not os.path.exists(dom(out, "alpha", "domain.md")), "a refused drain must write nothing"
    assert not os.path.exists(report_path(out)), "a refused drain leaves no report"

    proc = run_assemble(drain, claims_dir, out, "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:one#Same title": "keep-both"}))
    assert proc.returncode == 0, proc.stderr
    text = read(dom(out, "alpha", "domain.md"))
    assert "The first claim." in text, "the earlier claim was silently discarded"
    assert "A genuinely different second claim." in text
    assert "*Observed 2026-08-30 (alpha)*" in text and "*Observed 2026-09-18 (alpha)*" in text, text
    assert "TITLE COLLISIONS" in proc.stderr, "the collision must be reported, not hidden"
    report = json.loads(read(report_path(out)))
    assert report["collision_decisions"] == [{"key": "alpha/domain:one#Same title", "decision": "keep-both",
                                              "agent": "unresolved", "observed_at": "2026-09-18"}], report["collision_decisions"]


def test_the_owner_supersedes_or_drops_a_colliding_claim(tmp: str) -> None:
    """Against a section already in the corpus: supersede makes the incoming
    text replace it (merge_target applied on the owner's word, siblings
    retired); drop leaves the corpus as it was. An invalid decision word is
    refused before anything runs."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "workflow", "topic": "deploy", "title": "How we deploy",
         "body": "By hand, from the operator's laptop.", "evidence": ["h1"], "observed_at": "2026-08-30"},
    ])})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    incoming = claims("alpha", [
        {"class": "workflow", "topic": "deploy", "title": "How we deploy",
         "body": "Through the pipeline, never by hand.", "evidence": ["h2"], "observed_at": "2026-09-18"},
    ])
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(incoming, fh)
    path = proj(out, "alpha", "workflow.md")
    before = read(path)

    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "in the corpus (observed 2026-08-30)" in proc.stderr, proc.stderr
    assert read(path) == before, "a refused drain must not touch the slice"

    proc = run_assemble(drain, claims_dir, out, "--collision-decisions",
                        decisions_file(tmp, {"alpha/workflow:deploy#How we deploy": "bogus"}))
    assert proc.returncode != 0 and "supersede, keep-both or drop" in proc.stderr, proc.stderr

    proc = run_assemble(drain, claims_dir, out, "--collision-decisions",
                        decisions_file(tmp, {"alpha/workflow:deploy#How we deploy": "drop"}))
    assert proc.returncode == 0, proc.stderr
    assert read(path) == before, "drop must leave the slice byte-identical — description and stamp included"
    assert "How we deploy" in read(proj(out, "alpha", "INDEX.md")), "the index keeps the slice's cue"

    proc = run_assemble(drain, claims_dir, out, "--collision-decisions",
                        decisions_file(tmp, {"alpha/workflow:deploy#How we deploy": "supersede"}))
    assert proc.returncode == 0, proc.stderr
    after = read(path)
    assert "Through the pipeline, never by hand." in after and "By hand, from the operator" not in after, after
    assert after.count("## How we deploy") == 1 and "(2)" not in after, after
    assert "*Observed 2026-09-18 (alpha)*" in after, after
    report = json.loads(read(report_path(out)))
    assert report["collision_decisions"][0]["decision"] == "supersede"


def test_carried_sections_keep_their_citation_edges(tmp: str) -> None:
    """A preserved section still cites its ADRs and PRs, so rebuilding the
    graph from this drain alone would break every lookup into it."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Cycle one",
         "body": "b", "evidence": ["h1"]},
    ])})
    run_assemble(drain, claims_dir, out)
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "solution", "topic": "two", "title": "Cycle two",
             "body": "b", "evidence": ["h2"]},
        ]), fh)
    run_assemble(drain, claims_dir, out)
    with open(proj(out, "alpha", "crossref.json"), encoding="utf-8") as fh:
        index = json.load(fh)["index"]
    assert "ADR-054" in index.get("adrs", {}), "the first drain's edge was lost"
    assert "migration-007" in index.get("migrations", {}), "the second drain's edge is missing"


def test_carried_evidence_keeps_its_origin(tmp: str) -> None:
    """A hash in derived_from with no matching origin is an audit trail that
    breaks exactly when the observation store has been cleared."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Cycle one",
         "body": "b", "evidence": ["h1"]},
    ])})
    run_assemble(drain, claims_dir, out)
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "domain", "topic": "one", "title": "Cycle two",
             "body": "b", "evidence": ["h2"]},
        ]), fh)
    run_assemble(drain, claims_dir, out)
    text = read(dom(out, "alpha", "domain.md"))
    assert "- h1" in text and "- h2" in text
    assert "clone-aaa" in text, "the carried hash lost the clone that produced it"
    assert "clone-bbb" in text, "the new hash lost its origin"


def test_collision_is_reported_on_every_run(tmp: str) -> None:
    """An unresolved collision must keep appearing. Reporting it only the
    first time made the drain report differ between identical runs and hid a
    still-unresolved collision from every later drain."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Same title",
         "body": "First.", "evidence": ["h1"]},
        {"class": "domain", "topic": "one", "title": "Same title",
         "body": "Second.", "evidence": ["h2"]},
    ])})
    run_assemble(drain, claims_dir, out, *keep_both(tmp, "alpha/domain:one#Same title"))
    first = read(report_path(out))
    run_assemble(drain, claims_dir, out, *keep_both(tmp, "alpha/domain:one#Same title"))
    second = read(report_path(out))
    # The first run applied keep-both; the second found the pair already
    # present and asked nothing. Both are the same drain (one stamp), so
    # the report the second leaves still carries the first's decision.
    assert first == second, "the drain report must be identical for identical input"
    assert json.loads(second)["collision_decisions"], "the drain's decision survives its re-run"
    assert json.loads(second)["title_collisions"], \
        "an unresolved collision must still be reported on later drains"


def test_collision_survives_a_drain_with_an_empty_delta(tmp: str) -> None:
    """An empty delta for a slice is a valid outcome, and both colliding
    sections stay on disk through it. Deriving the warning from the current
    batch let it go quiet exactly then — an unresolved collision that stops
    being reported reads as one that was resolved."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Same title",
         "body": "First.", "evidence": ["h1"]},
        {"class": "domain", "topic": "one", "title": "Same title",
         "body": "Second.", "evidence": ["h2"]},
    ])})
    run_assemble(drain, claims_dir, out, *keep_both(tmp, "alpha/domain:one#Same title"))
    assert json.loads(read(report_path(out)))["title_collisions"]

    # A later drain that admits nothing for this slice — and touches a
    # different one entirely.
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "workflow", "topic": "elsewhere", "title": "Unrelated",
             "body": "b", "evidence": ["h2"]},
        ]), fh)
    run_assemble(drain, claims_dir, out)

    text = read(dom(out, "alpha", "domain.md"))
    assert "## Same title" in text and "## Same title (2)" in text, \
        "both sections must still be on disk"
    still = json.loads(read(report_path(out)))["title_collisions"]
    assert still, "the unresolved collision must still be reported"


def test_merge_target_clears_the_collision_it_resolves(tmp: str) -> None:
    """A collision leaves "X" and "X (2)" and records "X" so the drain
    report can ask for a merge_target.

    Naming it rewrote "X" alone: "X (2)" stayed in the body forever and
    the recorded collision was unioned forward on every later drain — so
    the remedy the report prescribes could never clear the report.
    """
    first = {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Shared title",
         "body": "The first finding.", "evidence": ["h1"]},
        {"class": "domain", "topic": "one", "title": "Shared title",
         "body": "A DIFFERENT second finding.", "evidence": ["h2"]},
    ])}
    drain, claims_dir, out = build(tmp, first)
    run_assemble(drain, claims_dir, out, *keep_both(tmp, "alpha/domain:one#Shared title"))
    path = dom(out, "alpha", "domain.md")
    text = read(path)
    assert "Shared title (2)" in text, "precondition: the collision happened"
    assert "collisions:" in text, "precondition: it was recorded"

    # The prescribed remedy.
    second = claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Shared title",
         "merge_target": "Shared title",
         "body": "Both findings, consolidated.", "evidence": ["h1", "h2"]},
    ])
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(second, fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr

    text = read(path)
    assert "Both findings, consolidated." in text, text
    assert "Shared title (2)" not in text, \
        "the suffixed section survived its own consolidation:\n" + text
    assert "collisions:" not in text, \
        "the collision is still reported after being resolved:\n" + text


def test_collision_scan_ignores_authored_documents(tmp: str) -> None:
    """An authored document may use `X` and `X (2)` as ordinary headings.
    Reporting those as an assembler collision would be wrong, and the
    merge_target it suggests could not fix them — nothing generated them."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Fine", "body": "b", "evidence": ["h1"]},
    ])})
    run_assemble(drain, claims_dir, out)          # creates the role directory
    # A charter (authored, class not generated) and a plain readme.
    with open(ident(out, "alpha", "charter.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: charter\ndescription: d\n"
                 "tier: 1\ndistilled_at: 2026-01-01\n---\n\n"
                 "## Scope\n\ntext\n\n## Scope (2)\n\nmore text\n")
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# Roles\n\n## Layout\n\ntext\n\n## Layout (2)\n\nmore\n")

    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(read(report_path(out)))
    assert report["title_collisions"] == [], \
        f"authored headings must not be reported: {report['title_collisions']}"


def test_authored_headings_are_not_mistaken_for_collisions(tmp: str) -> None:
    """An authored document may legitimately carry "X" and "X (2)". Inferring
    a collision from heading shape reported one where nothing collided, and
    told the reader to set merge_target on a file that has no claims."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Ordinary", "body": "b",
         "evidence": ["h1"]},
    ])})
    run_assemble(drain, claims_dir, out)
    with open(ident(out, "alpha", "charter.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: charter\ndescription: authored\n"
                 "tier: 1\ndistilled_at: 2026-01-01\n---\n\n"
                 "## Phase one\n\ntext\n\n## Phase one (2)\n\nmore text\n")
    run_assemble(drain, claims_dir, out)
    report = json.loads(read(report_path(out)))
    assert report["title_collisions"] == [], \
        f"authored headings were reported as a collision: {report['title_collisions']}"


def test_a_collision_slice_passes_lint(tmp: str) -> None:
    """Whatever the assembler writes, the schema must permit. `collisions` was
    added to the frontmatter without being added to the template schema, so
    the first real collision would have failed CI lint — turning a warning
    that is deliberately advisory into a merge blocker."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Same title",
         "body": "First.", "evidence": ["h1"]},
        {"class": "domain", "topic": "one", "title": "Same title",
         "body": "Second.", "evidence": ["h2"]},
    ])})
    run_assemble(drain, claims_dir, out, *keep_both(tmp, "alpha/domain:one#Same title"))
    assert "collisions:" in read(dom(out, "alpha", "domain.md")), \
        "the collision should have been recorded in the slice"
    lint_inputs(out)
    # Lint also wants the role catalogued; the assembler does not author that.
    os.makedirs(os.path.join(out, "identities", "roles"), exist_ok=True)
    with open(os.path.join(out, "identities", "roles", "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "roles": [{"id": "alpha", "title": "Alpha"}]}, fh)
    with open(ident(out, "alpha", "charter.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: charter\ndescription: d\ntier: 1\ndistilled_at: 2026-01-01\n---\n\n# alpha\n")
    run_assemble(drain, claims_dir, out, *keep_both(tmp, "alpha/domain:one#Same title"))          # re-index with the charter present
    proc = subprocess.run([sys.executable, LINT, "--fabric", out, "--working-copy", f"{PROJECT}={working_copy(out)}"], capture_output=True, text=True)
    assert proc.returncode == 0, \
        f"lint rejected what the assembler wrote:\n{proc.stderr}"


def test_quoted_titles_survive_repeated_drains(tmp: str) -> None:
    """Frontmatter must round-trip. A value with punctuation is written
    JSON-quoted; reading it back by stripping the outer quotes left the
    escapes behind, so a unioned field returned slightly more escaped each
    cycle and grew a fresh entry every drain, without bound."""
    quoted = 'The "quoted" finding'
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": quoted,
         "body": "First.", "evidence": ["h1"]},
        {"class": "domain", "topic": "one", "title": quoted,
         "body": "Second — a different claim under the same title.",
         "evidence": ["h2"]},
    ])})
    run_assemble(drain, claims_dir, out, *keep_both(tmp, 'alpha/domain:one#The "quoted" finding'))
    first = read(dom(out, "alpha", "domain.md"))
    assert first.count("collisions:") == 1
    entries_first = first.count(quoted.replace('"', '\\"'))

    run_assemble(drain, claims_dir, out, *keep_both(tmp, 'alpha/domain:one#The "quoted" finding'))
    second = read(dom(out, "alpha", "domain.md"))
    assert second == first, "a repeated drain must not rewrite the slice"
    assert second.count(quoted.replace('"', '\\"')) == entries_first, \
        "the collision entry multiplied across drains"
    assert "\\\\" not in second, "escaping accumulated in the frontmatter"


def test_domain_only_evidence_may_only_support_a_domain_claim(tmp: str) -> None:
    """Sibling-project evidence is transferable knowledge about a FIELD.

    Filed as `solution` it becomes an as-of-dated assertion about what THIS
    system implements; as `workflow` or `rationale`, about how this team
    works. The schema accepted the combination and the assembler wrote it in
    with only an in-body disclaimer — prose a reader may skim, not a
    boundary. And nothing loaded the schema at all, so it enforced nothing.
    """
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "solution", "topic": "wiring", "title": "Borrowed",
         "body": "How the other project wires it.", "evidence": ["h1"],
         "knowledge_scope": "domain-only"},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "domain-only" in proc.stderr, proc.stderr
    # It must refuse BEFORE writing, so a rerun is enough to recover.
    assert not os.path.exists(proj(out, "alpha", "solution.md")), \
        "a rejected drain must not leave a tree behind"


def test_domain_only_evidence_is_accepted_on_a_domain_claim(tmp: str) -> None:
    """The gate must narrow the case, not delete it."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "wiring", "title": "Borrowed",
         "body": "True of the field generally.", "evidence": ["h1"],
         "knowledge_scope": "domain-only"},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert os.path.exists(dom(out, "alpha", "domain.md"))


def test_hygiene_violation_is_redacted_in_place(tmp: str) -> None:
    """A banned term is replaced where it stands — "[redacted]" — and the
    knowledge around it lands; the run says what it replaced and stays
    clean (decided 2026-09-16: substitute, never refuse)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "leak", "title": "T",
         "body": "This mentions Springfield, which must never reach a committed role file. Set password=hunter2hunter2 too.",
         "evidence": ["h1"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    text = read(dom(out, "alpha", "domain.md"))
    assert "Springfield" not in text and "hunter2" not in text, text
    assert "This mentions [redacted], which must never" in text and "Set [redacted] too." in text, text
    assert "REDACTED (hygiene" in proc.stderr and "city name" in proc.stderr and "credential" in proc.stderr, proc.stderr
    report = json.loads(read(report_path(out)))
    assert any("city name" in r and "[redacted]" in r and "alpha/domain:leak" in r for r in report["redactions"]), report["redactions"]
    assert report["rejected_hygiene"] == [] and "rejected_hygiene" not in report["telemetry"]["alpha"]
    # The report is committed and stderr is read: neither carries what was withheld (B3).
    for said in (read(report_path(out)), proc.stderr):
        assert "Springfield" not in said and "hunter2" not in said, said


def test_carried_text_is_redacted_the_same_way_a_claim_is(tmp: str) -> None:
    """A slice written before a pattern existed carries the banned term into
    the next drain; it is substituted there exactly as a new claim's text
    is, and named. Once the two paths disagreed — a claim refused, the same
    word in carried text written with a warning — and lint failed the
    assembled tree (2026-09-16)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "carry", "title": "Older", "body": "Written before the rule.", "evidence": ["h1"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    path = dom(out, "alpha", "domain.md")
    text = read(path).replace("Written before the rule.", "Written before the rule, in Springfield.")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    # A later drain touches the same slice with a clean claim.
    _drain, claims_dir2, _out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "carry", "title": "Newer", "body": "A clean addition.", "evidence": ["h2"]},
    ])})
    proc = run_assemble(drain, claims_dir2, out)
    assert proc.returncode == 0, proc.stderr
    after = read(path)
    assert "Springfield" not in after and "in [redacted]." in after, after
    assert "A clean addition." in after, after
    assert "REDACTED (hygiene" in proc.stderr and "city name" in proc.stderr, proc.stderr
    assert "HYGIENE PROBLEMS" not in proc.stderr, proc.stderr


def test_the_same_claim_again_is_never_a_collision_whatever_its_date(tmp: str) -> None:
    """An undated corpus (every slice written before sections carried a
    date) re-drained with --all, or a memory whose mtime moved without a
    text change: the same claim again, not a disagreement. The section
    takes the date; nothing is refused (review of 2026-09-20, F1)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "Same body.", "evidence": ["h1"]},
    ])})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    path = dom(out, "alpha", "domain.md")
    assert "*Observed" not in read(path), "precondition: an undated section"
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "domain", "topic": "one", "title": "T", "body": "Same body.", "evidence": ["h1"], "observed_at": "2026-09-18"},
        ]), fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    text = read(path)
    assert text.count("## T") == 1 and "*Observed 2026-09-18 (alpha)*" in text, text
    # ...and a moved date on the same text is a date refresh, not a rival.
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "domain", "topic": "one", "title": "T", "body": "Same body.", "evidence": ["h1"], "observed_at": "2026-09-19"},
        ]), fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert read(path).count("## T") == 1 and "*Observed 2026-09-19 (alpha)*" in read(path)
    # ...and the same text arriving WITHOUT a date keeps the recorded one.
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [{"class": "domain", "topic": "one", "title": "T", "body": "Same body.", "evidence": ["h1"]}]), fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert read(path).count("## T") == 1 and "*Observed 2026-09-19 (alpha)*" in read(path), read(path)


def test_keep_both_is_remembered_on_the_next_drain(tmp: str) -> None:
    """Once the owner kept both, the same pair re-emitted (--all, a
    watermark at zero) is present as "X" and "X (2)" and is not asked
    about again: the same drain twice is the same tree (F3)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "S", "body": "First.", "evidence": ["h1"]},
        {"class": "domain", "topic": "one", "title": "S", "body": "Second.", "evidence": ["h2"]},
    ])})
    assert run_assemble(drain, claims_dir, out, *keep_both(tmp, "alpha/domain:one#S")).returncode == 0
    before = read(dom(out, "alpha", "domain.md"))
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert read(dom(out, "alpha", "domain.md")) == before


def test_another_topic_in_the_flat_class_file_is_not_this_topic_s_rival(tmp: str) -> None:
    """A flat <class>.md holds topic X; a drain brings topic Y whose heading
    equals one of X's with other text. The write phase migrates the flat
    file and writes Y to its own file — no collision exists — so the
    pre-pass must not read X's sections as Y's (F4)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "x", "title": "Shared heading", "body": "About x.", "evidence": ["h1"]},
    ])})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    assert os.path.exists(dom(out, "alpha", "domain.md")), "precondition: the flat file"
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "domain", "topic": "x", "title": "Shared heading", "body": "About x.", "evidence": ["h1"]},
            {"class": "domain", "topic": "y", "title": "Shared heading", "body": "About y.", "evidence": ["h2"]},
        ]), fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "About y." in read(dom(out, "alpha", "domain", "y.md"))
    assert "About x." in read(dom(out, "alpha", "domain", "x.md"))


def test_a_collision_inside_a_two_topic_flat_file_is_still_stopped(tmp: str) -> None:
    """Drain one brings topic x alone (a flat class file), drain two topic y
    alone (merged into the same flat file), drain three x with changed text
    under its heading. The pre-pass reads the flat file exactly when the
    write phase writes into it, so this genuine collision is refused —
    excluded whenever the crossref named two topics, it slipped through as
    an "X (2)" (re-review of 2026-09-20, N1)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "x", "title": "Hx", "body": "About x.", "evidence": ["h1"]},
    ])})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [{"class": "domain", "topic": "y", "title": "Hy", "body": "About y.", "evidence": ["h2"]}]), fh)
    assert run_assemble(drain, claims_dir, out).returncode == 0
    flat = dom(out, "alpha", "domain.md")
    assert os.path.exists(flat) and "## Hx" in read(flat) and "## Hy" in read(flat), "precondition: one flat file, two topics"
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [{"class": "domain", "topic": "x", "title": "Hx", "body": "About x, changed.", "evidence": ["h3"]}]), fh)
    before = read(flat)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "alpha/domain:x#Hx" in proc.stderr, proc.stderr
    assert read(flat) == before


def test_drop_on_a_shared_topic_keeps_it_in_every_owner_s_index(tmp: str) -> None:
    """A shared slice's only incoming claim dropped by the owner: the slice
    stays, and so does its line in every owner's index — a shared slice on
    disk is swept into its owners' indexes as the role's own are (N2)."""
    shared_claim = {"class": "domain", "topic": "one", "title": "H", "body": "First.", "evidence": ["h1"], "shared_with": ["beta"]}
    drain, claims_dir, out = build(tmp, {
        "alpha": claims("alpha", [shared_claim]),
        "beta": claims("beta", [{"class": "workflow", "topic": "own", "title": "Own", "body": "b", "evidence": ["h2"]}]),
    })
    assert run_assemble(drain, claims_dir, out).returncode == 0
    for role in ("alpha", "beta"):
        assert "shared/domain-one.md" in read(proj(out, role, "INDEX.md")), role
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [{**shared_claim, "body": "Second, different.", "evidence": ["h3"]}]), fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "shared/domain:one#H" in proc.stderr, proc.stderr
    proc = run_assemble(drain, claims_dir, out, "--collision-decisions", decisions_file(tmp, {"shared/domain:one#H": "drop"}))
    assert proc.returncode == 0, proc.stderr
    assert "First." in read(shared_path(out, "domain-one.md")) and "Second" not in read(shared_path(out, "domain-one.md"))
    for role in ("alpha", "beta"):
        assert "shared/domain-one.md" in read(proj(out, role, "INDEX.md")), f"{role} lost the shared slice from its index"
    assert set(json.loads(read(report_path(out)))["roles"]) >= {"alpha", "beta"}


def test_supersede_retires_the_section_in_the_part_that_holds_it(tmp: str) -> None:
    """A topic split by budget: the rival heading sits in part two, the
    superseding claim is grouped into part one. The owner's supersede must
    retire the section where it lives and land the new text once — not
    exit 0 with both standing in two files (connected reviewer, 2026-09-20)."""
    big = "y " * 900
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "grow", "title": "First", "body": big, "evidence": ["h1"]},
        {"class": "domain", "topic": "grow", "title": "Second", "body": big, "evidence": ["h2"]},
    ])})
    assert run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    parts = sorted(n for n in os.listdir(dom(out, "alpha", "domain")) if n.startswith("grow"))
    assert len(parts) >= 2, parts
    where = {n: "## Second" in read(dom(out, "alpha", "domain", n)) for n in parts}
    assert any(where.values()), where
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [{"class": "domain", "topic": "grow", "title": "Second", "body": "Second, revised.", "evidence": ["h3"]}]), fh)
    proc = run_assemble(drain, claims_dir, out, "--budget", "500")
    assert proc.returncode == 1 and "alpha/domain:grow#Second" in proc.stderr, proc.stderr
    proc = run_assemble(drain, claims_dir, out, "--budget", "500", "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:grow#Second": "supersede"}))
    assert proc.returncode == 0, proc.stderr
    texts = {n: read(dom(out, "alpha", "domain", n)) for n in os.listdir(dom(out, "alpha", "domain")) if n.startswith("grow")}
    assert sum(t.count("## Second") for t in texts.values()) == 1, texts
    assert any("Second, revised." in t for t in texts.values()) and not any(big.strip() in t and "## Second" in t and "Second, revised." not in t for t in texts.values())
    assert not any("collisions:" in t for t in texts.values()), "the retired section's collision record goes with it"
    # The part that held only the retired section is gone — not left as an
    # empty file the index still points at under the moved section's cue.
    assert not any("grow-2" in n for n in texts), texts.keys()
    assert "grow-2" not in read(proj(out, "alpha", "INDEX.md"))
    assert "RETIRED in another part" in proc.stderr and "grow-2.md: 'Second' removed" in proc.stderr, proc.stderr
    assert json.loads(read(report_path(out)))["retired_in_siblings"], "the report names the sibling touched"
    # A part rewritten with a section left keeps a schema-valid frontmatter
    # (a round trip once wrote tier: "2") and a cue naming what remains.
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "domain", "topic": "grow", "title": "Third", "body": "z " * 400, "evidence": ["h4"]},
            {"class": "domain", "topic": "grow", "title": "Fourth", "body": "z " * 400, "evidence": ["h5"]},
        ]), fh)
    assert run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    parts = {n: read(dom(out, "alpha", "domain", n)) for n in os.listdir(dom(out, "alpha", "domain")) if n.startswith("grow")}
    holder = next(n for n, t in parts.items() if "## Third" in t)
    assert "## Fourth" in parts[holder] and holder != "grow.md", "precondition: Third and Fourth share a later part"
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [{"class": "domain", "topic": "grow", "title": "Third", "body": "Third, revised.", "evidence": ["h6"]}]), fh)
    proc = run_assemble(drain, claims_dir, out, "--budget", "500", "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:grow#Third": "supersede"}))
    assert proc.returncode == 0, proc.stderr
    after = {n: read(dom(out, "alpha", "domain", n)) for n in os.listdir(dom(out, "alpha", "domain")) if n.startswith("grow")}
    assert sum(t.count("## Third") for t in after.values()) == 1 and any("Third, revised." in t for t in after.values()), after
    assert holder in after and "## Third" not in after[holder] and "## Fourth" in after[holder], after
    assert "tier: 2" in after[holder] and 'tier: "2"' not in after[holder], after[holder]
    assert "description: Fourth" in after[holder], after[holder]
    assert "grow-2.md: 'Third' rewritten" in proc.stderr, proc.stderr
    lint_inputs(out)
    os.makedirs(os.path.join(out, "identities", "roles"), exist_ok=True)
    with open(os.path.join(out, "identities", "roles", "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "roles": [{"id": "alpha", "title": "Alpha"}]}, fh)
    with open(ident(out, "alpha", "charter.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: charter\ndescription: d\ntier: 1\ndistilled_at: 2026-01-01\n---\n\n# alpha\n")
    assert run_assemble(drain, claims_dir, out, "--budget", "500", "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:grow#Third": "supersede"})).returncode == 0
    lint = subprocess.run([sys.executable, LINT, "--fabric", out, "--working-copy", f"{PROJECT}={working_copy(out)}"], capture_output=True, text=True)
    assert lint.returncode == 0, f"lint rejected the tree a supersede across parts left:\n{lint.stderr}"


def _lintable(out: str) -> None:
    lint_inputs(out)
    os.makedirs(os.path.join(out, "identities", "roles"), exist_ok=True)
    with open(os.path.join(out, "identities", "roles", "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "roles": [{"id": "alpha", "title": "Alpha"}]}, fh)
    with open(ident(out, "alpha", "charter.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: charter\ndescription: d\ntier: 1\ndistilled_at: 2026-01-01\n---\n\n# alpha\n")


def _lint(out: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, LINT, "--fabric", out, "--working-copy", f"{PROJECT}={working_copy(out)}"], capture_output=True, text=True)


def test_a_retired_sibling_already_indexed_this_run_is_re_listed_by_what_remains(tmp: str) -> None:
    """The other ordering: the target lives in part ONE, which is full of
    carried text, so the superseding claim is grouped into part two — and
    part one was written and indexed before the retire touched it. Its
    index line must follow: re-described when a section remains; lint
    accepts the tree; a part counts once in files_written (re-review of
    2026-09-20, finding 1). Each superseding run is a drain of its own,
    stamped so: a report of the same stamp is merged into, and the count
    would then be the whole drain's."""
    big = "y " * 900
    # Part one holds First alone: its replacement goes to part one.
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "grow", "title": "First", "body": big, "evidence": ["h1"]},
        {"class": "domain", "topic": "grow", "title": "Second", "body": big, "evidence": ["h2"]},
    ])})
    assert run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    assert "## First" in read(dom(out, "alpha", "domain", "grow.md")), "precondition: First in part one"
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [{"class": "domain", "topic": "grow", "title": "First", "body": "w " * 200, "evidence": ["h3"]}]), fh)
    _lintable(out)
    proc = run_assemble(drain, claims_dir, out, "--budget", "500", "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:grow#First": "supersede"}), "--stamp", "2026-01-02")
    assert proc.returncode == 0, proc.stderr
    parts = {n: read(dom(out, "alpha", "domain", n)) for n in os.listdir(dom(out, "alpha", "domain")) if n.startswith("grow")}
    assert sum(t.count("## First") for t in parts.values()) == 1 and any("w w w" in t for t in parts.values()), parts
    index = read(proj(out, "alpha", "INDEX.md"))
    listed = [ln for ln in index.splitlines() if "grow" in ln]
    assert all(any(n in ln for n in parts) for ln in listed), f"the index lists a part that is not on disk: {listed}"
    lint = _lint(out)
    assert lint.returncode == 0, lint.stderr
    report = json.loads(read(report_path(out)))
    # grow.md and INDEX.md. The section being replaced is not carried text,
    # so the superseding claim lands in part one beside nothing and
    # grow-2.md is untouched; part one used to be written, emptied by the
    # retire and removed, taking the topic's name with it (2026-09-25).
    assert report["files_written"] == 2, report["files_written"]
    assert os.path.exists(dom(out, "alpha", "domain", "grow.md"))

    # Rewritten shape: part one keeps Second after First is retired from it.
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "domain", "topic": "keep", "title": "Alpha one", "body": "z " * 400, "evidence": ["h4"]},
            {"class": "domain", "topic": "keep", "title": "Beta two", "body": "z " * 400, "evidence": ["h5"]},
            {"class": "domain", "topic": "keep", "title": "Gamma three", "body": big, "evidence": ["h6"]},
        ]), fh)
    assert run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    first_part = read(dom(out, "alpha", "domain", "keep.md"))
    assert "## Alpha one" in first_part and "## Beta two" in first_part, "precondition: two sections share part one"
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [{"class": "domain", "topic": "keep", "title": "Alpha one", "body": big, "evidence": ["h7"]}]), fh)
    proc = run_assemble(drain, claims_dir, out, "--budget", "500", "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:keep#Alpha one": "supersede"}), "--stamp", "2026-01-03")
    assert proc.returncode == 0, proc.stderr
    first_part = read(dom(out, "alpha", "domain", "keep.md"))
    assert "## Alpha one" not in first_part and "## Beta two" in first_part and "description: Beta two" in first_part, first_part
    index = read(proj(out, "alpha", "INDEX.md"))
    assert "keep.md" in index and "Beta two" in index and "keep (domain)" not in index, index
    lint = _lint(out)
    assert lint.returncode == 0, lint.stderr
    assert json.loads(read(report_path(out)))["files_written"] == 3, "keep.md, keep-2.md, INDEX.md — the rewritten part once"

    # The opposite ordering: the superseding claim lands in part one while
    # part two, which holds the target, also receives a new claim — the
    # part is rewritten by the retire and then written by the loop; once.
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "domain", "topic": "twice", "title": "One", "body": big, "evidence": ["h8"]},
            {"class": "domain", "topic": "twice", "title": "Two", "body": "z " * 300, "evidence": ["h9"]},
            {"class": "domain", "topic": "twice", "title": "Three", "body": "z " * 300, "evidence": ["h10"]},
        ]), fh)
    assert run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    assert "## Two" in read(dom(out, "alpha", "domain", "twice-2.md")), "precondition: Two in part two"
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "domain", "topic": "twice", "title": "Two", "body": "Two, revised.", "evidence": ["h11"]},
            {"class": "domain", "topic": "twice", "title": "Four", "body": big, "evidence": ["h12"]},
        ]), fh)
    proc = run_assemble(drain, claims_dir, out, "--budget", "500", "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:twice#Two": "supersede"}), "--stamp", "2026-01-04")
    assert proc.returncode == 0, proc.stderr
    n_parts = len([n for n in os.listdir(dom(out, "alpha", "domain")) if n.startswith("twice")])
    assert json.loads(read(report_path(out)))["files_written"] == n_parts + 1, (n_parts, proc.stderr)
    assert _lint(out).returncode == 0


def test_a_retired_sibling_loses_its_collision_record_and_clips_its_cue(tmp: str) -> None:
    """The rewritten part's frontmatter is edited as text: a `collisions:`
    list whose only entry was the retired title disappears whole (with
    (?s) the item pattern ran to the frontmatter's end and left a bare
    key), and the refreshed description is clipped as every description
    the assembler writes is (findings 2 and 3)."""
    long_title = "A heading long enough to overrun the schema's description limit " * 5
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "grow", "title": "First", "body": "y " * 900, "evidence": ["h1"]},
        {"class": "domain", "topic": "grow", "title": "Third", "body": "z " * 300, "evidence": ["h2"]},
        {"class": "domain", "topic": "grow", "title": long_title.strip(), "body": "z " * 300, "evidence": ["h3"]},
    ])})
    assert run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    sibling = dom(out, "alpha", "domain", "grow-2.md")
    text = read(sibling)
    assert "## Third" in text and "## A heading long" in text, "precondition: Third and the long heading share part two"
    # Seed a collision record naming Third where the assembler writes it —
    # BEFORE origin: and derived_from:, so a pattern that runs to the end
    # of the frontmatter would swallow those keys' lines too.
    assert "\norigin:\n" in text, text
    text = text.replace("\norigin:\n", '\ncollisions:\n  - "Third"\norigin:\n', 1)
    with open(sibling, "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [{"class": "domain", "topic": "grow", "title": "Third", "body": "Third, revised.", "evidence": ["h4"]}]), fh)
    _lintable(out)
    proc = run_assemble(drain, claims_dir, out, "--budget", "500", "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:grow#Third": "supersede"}))
    assert proc.returncode == 0, proc.stderr
    after = read(sibling)
    front = after.split("\n---\n")[0]
    assert "collisions" not in front, front
    desc = next(ln for ln in front.splitlines() if ln.startswith("description: "))
    assert len(desc) - len("description: ") <= 242 and desc.rstrip('"').endswith("…"), desc
    assert "grow-2.md: description clipped" in proc.stderr and "grow.md: description clipped" not in proc.stderr.replace("grow-2.md", ""), proc.stderr
    assert "origin:" in front and "derived_from:" in front, front
    lint = _lint(out)
    assert lint.returncode == 0, lint.stderr


def test_each_colliding_claim_has_its_own_decision_key(tmp: str) -> None:
    """Two incoming claims under one heading against a corpus section: the
    owner supersedes with one and drops the other. A key per claim (its
    first evidence hash) makes that sayable; the heading's key stays the
    default for every pair under it."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "H", "body": "Original.", "evidence": ["h1"]},
    ])})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    with open(os.path.join(claims_dir, "alpha.json"), "w", encoding="utf-8") as fh:
        json.dump(claims("alpha", [
            {"class": "domain", "topic": "one", "title": "H", "body": "Newest, the truth.", "evidence": ["h2"]},
            {"class": "domain", "topic": "one", "title": "H", "body": "Intermediate, wrong.", "evidence": ["h3"]},
        ]), fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "alpha/domain:one#H@h2" in proc.stderr and "alpha/domain:one#H@h3" in proc.stderr, proc.stderr
    proc = run_assemble(drain, claims_dir, out, "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:one#H@h2": "supersede", "alpha/domain:one#H@h3": "drop"}))
    assert proc.returncode == 0, proc.stderr
    text = read(dom(out, "alpha", "domain.md"))
    assert "Newest, the truth." in text and "Intermediate" not in text and "Original." not in text and text.count("## H") == 1, text
    keys = sorted(d["key"] for d in json.loads(read(report_path(out)))["collision_decisions"])
    assert keys == ["alpha/domain:one#H@h2", "alpha/domain:one#H@h3"], keys


def test_non_english_slice_is_rejected_by_the_assembler(tmp: str) -> None:
    """Non-English prose fails the same hygiene check a city name does: the
    claim is rejected and named, never written for lint to find later."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "it", "title": "T",
         "body": "Questo perche' la configurazione della nella cache dovrebbe essere anche molto lenta.",
         "evidence": ["h1"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1, "non-English prose must be reported"
    assert "non-English" in proc.stderr, proc.stderr
    assert not os.path.exists(dom(out, "alpha", "domain.md")), "the rejected claim was written"


def test_lint_detects_index_drift(tmp: str) -> None:
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    run_assemble(drain, claims_dir, out)
    lint_inputs(out)
    with open(proj(out, "alpha", "solution.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: solution\ndescription: added by hand\n"
                 "tier: 2\ndistilled_at: 2026-01-01\nderived_from:\n  - h1\n---\n\nbody\n")
    proc = subprocess.run([sys.executable, LINT, "--fabric", out, "--working-copy", f"{PROJECT}={working_copy(out)}"], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "drifted" in proc.stderr, proc.stderr


def test_scratchpad_references_are_normalized(tmp: str) -> None:
    """A session scratchpad path must not become a crossref key.

    The index is worth keeping because its keys still resolve once the
    observation buffer is gone. A path under one session's scratchpad
    resolves nowhere — and three such keys reached the repo from other
    sessions before this existed.
    """
    scratch = ("/tmp/claude-1000/-home-user-projects-legacy-clone-9/"
               "cbbf4344-dead-beef-0000-000000000000/scratchpad/probe.test.ts")
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b",
         "evidence": ["hx"]},
    ])})
    # An observation whose only cited artifact is a scratchpad file.
    with open(os.path.join(drain, "references.json"), "w", encoding="utf-8") as fh:
        json.dump({"hx": {"files": [scratch]}}, fh)
    run_assemble(drain, claims_dir, out)

    with open(proj(out, "alpha", "crossref.json"), encoding="utf-8") as fh:
        files = json.load(fh)["index"].get("files", {})
    assert scratch not in files, f"raw session path survived: {sorted(files)}"
    # The digest distinguishes same-named artifacts from different
    # sessions; the readable tail is what the entry is FOR, so both halves
    # are asserted rather than the whole key.
    key = next((k for k in files if k.startswith("scratch:probe.test.ts#")), None)
    assert key is not None, sorted(files)
    assert re.fullmatch(r"scratch:probe\.test\.ts#[0-9a-f]{8}", key), key
    # The edge itself is preserved — normalizing must not drop provenance.
    assert files[key]["observations"] == ["hx"], files


def test_a_tracked_scratchpad_path_is_left_alone(tmp: str) -> None:
    """A `scratchpad/` segment means ephemeral only UNDER a session-temp
    root. `docs/scratchpad/decision.md` is a tracked file someone can
    open, and collapsing it would delete a valid repository path from the
    citation graph — the opposite of what the normalization is for."""
    tracked = "docs/scratchpad/decision.md"
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b",
         "evidence": ["hx"]},
    ])})
    with open(os.path.join(drain, "references.json"), "w", encoding="utf-8") as fh:
        json.dump({"hx": {"files": [tracked]}}, fh)
    run_assemble(drain, claims_dir, out)

    with open(proj(out, "alpha", "crossref.json"), encoding="utf-8") as fh:
        files = json.load(fh)["index"].get("files", {})
    assert tracked in files, sorted(files)
    assert not any(k.startswith("scratch:") for k in files), sorted(files)


def test_same_named_temp_artifacts_stay_distinct(tmp: str) -> None:
    """Two dead paths sharing a basename are not the same artifact.
    Without a distinguishing digest both reduced to `scratch:probe.cs`
    and the assembler merged their observation lists, conflating
    unrelated provenance."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b",
         "evidence": ["ha", "hb"]},
    ])})
    with open(os.path.join(drain, "references.json"), "w", encoding="utf-8") as fh:
        json.dump({"ha": {"files": ["/tmp/run-a/probe.cs"]},
                   "hb": {"files": ["/tmp/run-b/probe.cs"]}}, fh)
    run_assemble(drain, claims_dir, out)

    with open(proj(out, "alpha", "crossref.json"), encoding="utf-8") as fh:
        files = json.load(fh)["index"].get("files", {})
    keys = sorted(k for k in files if k.startswith("scratch:probe.cs#"))
    assert len(keys) == 2, keys
    # And each keeps only its OWN observation.
    assert sorted(files[keys[0]]["observations"] + files[keys[1]]["observations"]) \
        == ["ha", "hb"], files
    assert files[keys[0]]["observations"] != files[keys[1]]["observations"], files


def test_lint_rejects_a_session_temp_crossref_key(tmp: str) -> None:
    """The generator normalizes; lint is the backstop for any key that
    arrives another way (a hand edit, an older generator)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b",
         "evidence": ["h1"]},
    ])})
    run_assemble(drain, claims_dir, out)
    lint_inputs(out)

    crossref_path = proj(out, "alpha", "crossref.json")
    with open(crossref_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["index"].setdefault("files", {})[
        "/tmp/claude-1000/-home-user-projects-legacy-clone-9/x/scratchpad/p.ts"
    ] = {"observations": [], "slices": []}
    with open(crossref_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2, sort_keys=True)

    proc = subprocess.run(
        [sys.executable, LINT, "--fabric", out, "--working-copy", f"{PROJECT}={working_copy(out)}"], capture_output=True, text=True)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "session-local temp path" in proc.stderr, proc.stderr


def lintable(out: str) -> None:
    """Schemas, a catalogue naming alpha, and alpha's charter — what lint
    wants beyond what the assembler writes."""
    lint_inputs(out)
    os.makedirs(os.path.join(out, "identities", "roles"), exist_ok=True)
    with open(os.path.join(out, "identities", "roles", "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "roles": [{"id": "alpha", "title": "Alpha"}]}, fh)
    with open(ident(out, "alpha", "charter.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: charter\ndescription: d\ntier: 1\ndistilled_at: 2026-01-01\n---\n\n# alpha\n")


def run_lint_wc(out: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, LINT, "--fabric", out, "--working-copy", f"{PROJECT}={working_copy(out)}"],
                          capture_output=True, text=True)


def test_a_banned_term_in_title_or_topic_is_redacted_too_and_a_person_becomes_the_role(tmp: str) -> None:
    """The first drain that met this: the city sat in the TITLE, the body
    check passed, the written slice failed lint. Every text field is
    substituted, the topic that names the file included; a person's name
    (the fabric's own list, policies/hygiene.json) becomes the role it
    names, and lint accepts what the assembler wrote."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "workflow", "topic": "clean", "title": "Clean", "body": "fine", "evidence": ["h1"]},
        {"class": "workflow", "topic": "springfield-seed", "title": "The Springfield seed drops names",
         "body": "Andrea Benetton asked twice; Andrea caught it in the Springfield seed.", "evidence": ["h2"]},
    ])})
    os.makedirs(os.path.join(out, "policies"), exist_ok=True)
    shutil.copy(os.path.join(ROOT, "policies", "hygiene.json"), os.path.join(out, "policies", "hygiene.json"))
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    files = sorted(os.listdir(proj(out, "alpha", "workflow")))
    assert files == ["clean.md", "redacted-seed.md"], files
    text = read(proj(out, "alpha", "workflow", "redacted-seed.md"))
    assert "Springfield" not in text and "Andrea" not in text, text
    assert "The [redacted] seed drops names" in text, text
    assert "The CEO asked twice; the CEO caught it in the [redacted] seed." in text, text
    report = json.loads(read(report_path(out)))
    assert any("person's name" in r and "'the CEO'" in r for r in report["redactions"]), report["redactions"]
    assert any("topic" in r for r in report["redactions"]), report["redactions"]
    lint_inputs(out)
    os.makedirs(os.path.join(out, "identities", "roles"), exist_ok=True)
    with open(os.path.join(out, "identities", "roles", "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "roles": [{"id": "alpha", "title": "Alpha"}]}, fh)
    with open(ident(out, "alpha", "charter.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: charter\ndescription: d\ntier: 1\ndistilled_at: 2026-01-01\n---\n\n# alpha\n")
    run_assemble(drain, claims_dir, out)          # re-index with the charter present
    lint = subprocess.run([sys.executable, LINT, "--fabric", out, "--working-copy", f"{PROJECT}={working_copy(out)}"], capture_output=True, text=True)
    assert lint.returncode == 0, f"lint refused what the assembler wrote:\n{lint.stdout}{lint.stderr}"


def test_an_overlong_description_is_clipped_everywhere_it_appears(tmp: str) -> None:
    """The schema caps a description at 240; a longer title is clipped at a
    word boundary in the slice AND in the index entry (an index that kept
    the long form read as drift), and the clip is reported."""
    long = "word " * 70
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "workflow", "topic": "long", "title": long.strip(), "body": "b", "evidence": ["h1"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    text = read(proj(out, "alpha", "workflow.md"))
    desc = [l for l in text.splitlines() if l.startswith("description:")][0]
    assert len(desc) <= 240 + len("description: ") + 2 and desc.rstrip('"').endswith("…"), desc
    index = read(proj(out, "alpha", "INDEX.md"))
    assert "…" in index and long.strip() not in index
    assert "DESCRIPTIONS CLIPPED" in proc.stderr
    lintable(out); run_assemble(drain, claims_dir, out)   # re-index with the charter present
    lint = run_lint_wc(out)
    assert lint.returncode == 0, lint.stderr


def test_a_flat_class_file_moves_into_the_directory_when_the_class_splits(tmp: str) -> None:
    """Drain one: a single workflow topic -> flat workflow.md. Drain two
    brings two topics at once: the class becomes a directory and the flat
    file MOVES in (named for its one prior topic), instead of staying
    unreachable beside it and being counted as carried text for the new
    topics."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "workflow", "topic": "first", "title": "First", "body": "one", "evidence": ["h1"]},
    ])})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    assert os.path.exists(proj(out, "alpha", "workflow.md"))
    drain, claims_dir, _ = build(os.path.join(tmp, "two"), {"alpha": claims("alpha", [
        {"class": "workflow", "topic": "second", "title": "Second", "body": "two", "evidence": ["h2"]},
        {"class": "workflow", "topic": "third", "title": "Third", "body": "three", "evidence": ["h3"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert not os.path.exists(proj(out, "alpha", "workflow.md")), "flat file left beside the directory"
    assert os.path.exists(proj(out, "alpha", "workflow", "first.md")), os.listdir(proj(out, "alpha", "workflow"))
    assert os.path.exists(proj(out, "alpha", "workflow", "second.md"))
    assert "First" in read(proj(out, "alpha", "workflow", "first.md"))
    assert "LAYOUT: flat class file moved" in proc.stderr
    for name in ("first.md", "second.md", "third.md"):
        text = read(proj(out, "alpha", "workflow", name))
        assert "derived_from:" in text, f"{name} lost its provenance"
    lintable(out); run_assemble(drain, claims_dir, out)   # re-index with the charter present
    lint = run_lint_wc(out)
    assert lint.returncode == 0, lint.stderr


def test_an_oversized_single_claim_is_written_whole_and_reported(tmp: str) -> None:
    """A claim larger than the budget cannot be split; it lands as one slice
    and the report says which memory to split — never an empty part one
    with no provenance followed by the whole text in part two."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "threads", "topic": "big", "title": "Big", "body": "x" * 9000, "evidence": ["h1"]},
    ])})
    proc = run_assemble(drain, claims_dir, out, "--budget", "1000")
    assert proc.returncode == 0, proc.stderr
    files = sorted(os.listdir(proj(out, "alpha")))
    assert "threads.md" in files and not any(f.startswith("threads-") for f in files), files
    assert "derived_from:" in read(proj(out, "alpha", "threads.md"))
    assert "OVER BUDGET" in proc.stderr and "split the memory" in proc.stderr, proc.stderr


def set_claims(claims_dir: str, role: str, items: list[dict]) -> None:
    with open(os.path.join(claims_dir, f"{role}.json"), "w", encoding="utf-8") as fh:
        json.dump(claims(role, items), fh)


def tree(out: str) -> dict[str, str]:
    """Every file under the fabric root and the working copy, by path —
    the corpus, not the drain report, which says what each run did."""
    found: dict[str, str] = {}
    for dirpath, _dirs, files in os.walk(out):
        for name in files:
            if name == "last-drain-report.json":
                continue
            path = os.path.join(dirpath, name)
            found[os.path.relpath(path, out)] = read(path)
    return found


def test_a_correction_naming_another_topic_s_section_replaces_it_there(tmp: str) -> None:
    """memory/README.md tells an agent to correct a wrong slice with a
    memory naming the slice's section in merge_target. That memory has
    its own topic (its file name), and the target was looked for in that
    topic alone: the correction landed as a new slice beside the stale
    one, silently (a drain's blind review, 2026-09-25). The target is
    resolved across the role's class; the section is replaced where it
    lives, and a second run of the same drain changes nothing."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "deploy", "title": "How we deploy",
         "body": "By hand, from the operator's laptop.", "evidence": ["h1"]},
        {"class": "domain", "topic": "other", "title": "Something else",
         "body": "Unrelated.", "evidence": ["h2"]},
    ])})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "deploy-correction", "title": "Deploys go through the pipeline",
         "merge_target": "How we deploy", "body": "Through the pipeline, never by hand.", "evidence": ["h3"]},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    names = sorted(os.listdir(dom(out, "alpha", "domain")))
    assert names == ["deploy.md", "other.md"], f"the correction was written beside the stale slice: {names}"
    text = read(dom(out, "alpha", "domain", "deploy.md"))
    assert "Through the pipeline, never by hand." in text and "operator's laptop" not in text, text
    assert text.count("## ") == 1, text
    assert "MERGE TARGET" not in proc.stderr, proc.stderr
    before = tree(out)
    assert run_assemble(drain, claims_dir, out).returncode == 0
    assert tree(out) == before, "the same correction harvested again changed the tree"

    # A target that names no section anywhere is written as its own topic
    # and said aloud — in stderr and in the report.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "orphan", "title": "An orphan correction",
         "merge_target": "No such heading", "body": "Text.", "evidence": ["h4"]},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "MERGE TARGET UNRESOLVED" in proc.stderr and "No such heading" in proc.stderr, proc.stderr
    assert os.path.exists(dom(out, "alpha", "domain", "orphan.md"))
    unresolved = json.loads(read(report_path(out))).get("merge_target_unresolved") or []
    assert any("No such heading" in u for u in unresolved), unresolved

    # A heading two topics hold is refused before anything is written.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "twin-a", "title": "Twin", "body": "A.", "evidence": ["h1"]},
        {"class": "domain", "topic": "twin-b", "title": "Twin", "body": "B.", "evidence": ["h2"]},
    ])
    assert run_assemble(drain, claims_dir, out).returncode == 0
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "fix", "title": "Fixed twin", "merge_target": "Twin",
         "body": "C.", "evidence": ["h3"]},
    ])
    before = tree(out)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1, proc.stderr
    assert "MERGE TARGET AMBIGUOUS" in proc.stderr and "domain:twin-a" in proc.stderr \
        and "domain:twin-b" in proc.stderr, proc.stderr
    assert tree(out) == before, "an ambiguous target must leave the tree untouched"

    # The same holds for a shared slice: the owners' correction replaces
    # the section in the shared topic that holds it.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "joint", "title": "Joint finding", "shared_with": ["beta"],
         "body": "Old joint text.", "evidence": ["h1"]},
    ])
    assert run_assemble(drain, claims_dir, out).returncode == 0
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "joint-fix", "title": "Joint finding, corrected", "shared_with": ["beta"],
         "merge_target": "Joint finding", "body": "New joint text.", "evidence": ["h2"]},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert not os.path.exists(shared_path(out, "domain-joint-fix.md")), os.listdir(shared_path(out, ""))
    joint = read(shared_path(out, "domain-joint.md"))
    assert "New joint text." in joint and "Old joint text." not in joint, joint


def with_agents(drain: str, rows: dict[str, str]) -> None:
    """Observations that name the agent, as harvest_memory.py writes them."""
    with open(os.path.join(drain, "observations.jsonl"), "w", encoding="utf-8") as fh:
        for h, agent in sorted(rows.items()):
            fh.write(json.dumps({"content_hash": h, "agent": agent, "host": "hostA"}) + "\n")


def test_a_retitled_memory_replaces_its_own_old_section(tmp: str) -> None:
    """A memory's topic is its file name and its heading its description.
    An agent that rewrites a tracker with a new description brings a new
    heading into a topic whose every section it wrote; appending it left
    the stale "open" section standing beside the "merged" one (a drain's
    blind review, 2026-09-25). The agent's newer text supersedes its own
    older text without a question, recorded as the same-agent rule (the
    owner, 2026-09-26); an owner's decision still wins; a topic several
    agents wrote keeps appending, and a collision between two agents'
    texts still stops the drain."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue 851 is open",
         "body": "Waiting on review.", "evidence": ["a1"], "observed_at": "2026-09-20"},
        {"class": "domain", "topic": "joint", "title": "First view", "body": "One.", "evidence": ["a2"]},
        {"class": "domain", "topic": "joint", "title": "Second view", "body": "Two.", "evidence": ["b1"]},
    ])})
    with_agents(drain, {"a1": "dev-01", "a2": "dev-01", "a3": "dev-01", "a4": "dev-01", "b1": "dev-02", "b2": "dev-02"})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    retitle = {"class": "domain", "topic": "tracker", "title": "Issue 851 is merged",
               "body": "Merged on 2026-09-24.", "evidence": ["a3"], "observed_at": "2026-09-24"}
    set_claims(claims_dir, "alpha", [retitle])
    tracker = dom(out, "alpha", "domain", "tracker.md")
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "SUPERSEDED, same agent" in proc.stderr and "alpha/domain:tracker#Issue 851 is merged  (dev-01)" in proc.stderr, proc.stderr
    report = json.loads(read(report_path(out)))
    assert any(d.get("rule") == "same-agent" and d["decision"] == "supersede"
               and d["key"].endswith("tracker#Issue 851 is merged") for d in report["collision_decisions"]), report["collision_decisions"]
    text = read(tracker)
    assert "## Issue 851 is merged" in text and "Issue 851 is open" not in text and "Waiting" not in text, text
    assert "description: Issue 851 is merged" in text, text
    index = read(proj(out, "alpha", "INDEX.md"))
    assert "Issue 851 is open" not in index and "Issue 851 is merged" in index, index

    # The author's own merge_target naming the old section is no question.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue 851 is released",
         "merge_target": "Issue 851 is merged", "body": "Released.", "evidence": ["a4"]},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "Released." in read(tracker) and read(tracker).count("## ") == 1, read(tracker)
    assert "## Issue 851 is released" in read(tracker) and "is merged" not in read(tracker), \
        "the corrected section kept its stale heading:\n" + read(tracker)

    # A topic two agents wrote is two memories: a new heading appends.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "joint", "title": "Third view", "body": "Three.", "evidence": ["a4"]},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    joint = read(dom(out, "alpha", "domain", "joint.md"))
    assert all(h in joint for h in ("## First view", "## Second view", "## Third view")), joint

    # Another agent's text under a heading this agent wrote is still asked.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue 851 is released",
         "body": "Not released yet.", "evidence": ["b2"]},
    ])
    before = read(tracker)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "SUPERSEDING?" in proc.stderr, proc.stderr
    assert read(tracker) == before, "a refused drain must not touch the slice"


def test_a_claim_in_the_carried_file_is_not_written_twice(tmp: str) -> None:
    """A flat class file holding several topics moves whole into
    `<class>/<class>-carried-<stamp>.md` when the class splits. That file
    was no topic's candidate, so the same memory harvested again was
    written a second time as `<class>/<topic>.md` beside its carried copy
    (a drain's blind review, 2026-09-25). A claim whose heading sits in
    the carried file lands there — same text a no-op, other text a
    collision the owner decides there — and a copy an earlier drain left
    in both places is dropped from the carried file, which goes when
    empty, reported."""
    one = {"class": "workflow", "topic": "alpha-one", "title": "One", "body": "First way.", "evidence": ["h1"]}
    two = {"class": "workflow", "topic": "alpha-two", "title": "Two", "body": "Second way.", "evidence": ["h2"]}
    three = {"class": "workflow", "topic": "three", "title": "Three", "body": "Third way.", "evidence": ["h3"]}
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [one])})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    set_claims(claims_dir, "alpha", [two])
    assert run_assemble(drain, claims_dir, out).returncode == 0
    assert "## One" in read(proj(out, "alpha", "workflow.md")) and "## Two" in read(proj(out, "alpha", "workflow.md"))

    set_claims(claims_dir, "alpha", [one, three])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    wf = proj(out, "alpha", "workflow")
    carried = os.path.join(wf, "workflow-carried-2026-01-01.md")
    assert sorted(os.listdir(wf)) == ["three.md", "workflow-carried-2026-01-01.md"], \
        f"the carried claim was written again: {sorted(os.listdir(wf))}"
    assert sum(read(os.path.join(wf, n)).count("## One") for n in os.listdir(wf)) == 1
    before = tree(out)
    assert run_assemble(drain, claims_dir, out).returncode == 0
    assert tree(out) == before, "the same drain again changed the tree"

    # A different text under the carried heading is asked about, and the
    # owner's supersede replaces it in the carried file.
    set_claims(claims_dir, "alpha", [dict(one, body="First way, revised.", evidence=["h3"])])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "alpha/workflow:workflow-carried-2026-01-01#One" in proc.stderr, proc.stderr
    proc = run_assemble(drain, claims_dir, out, "--collision-decisions", decisions_file(
        tmp, {"alpha/workflow:workflow-carried-2026-01-01#One": "supersede"}))
    assert proc.returncode == 0, proc.stderr
    assert "First way, revised." in read(carried) and "First way.\n" not in read(carried), read(carried)
    assert sorted(os.listdir(wf)) == ["three.md", "workflow-carried-2026-01-01.md"], sorted(os.listdir(wf))

    # A tree an earlier drain left with each claim in both places: the
    # carried copies go, and the emptied carried file with them.
    front, _, _ = read(carried).partition("\n## ")
    sections = {h: t for h, t in re.findall(r"^## (.+?)\n\n(.*?)(?=\n## |\Z)", read(carried), re.S | re.M)}
    for topic, heading in (("alpha-one", "One"), ("alpha-two", "Two")):
        with open(os.path.join(wf, f"{topic}.md"), "w", encoding="utf-8") as fh:
            fh.write(f"{front}\n## {heading}\n\n{sections[heading].strip()}\n")
    set_claims(claims_dir, "alpha", [dict(one, body="First way, revised.", evidence=["h3"]), two])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert not os.path.exists(carried), read(carried)
    assert sorted(os.listdir(wf)) == ["alpha-one.md", "alpha-two.md", "three.md"], sorted(os.listdir(wf))
    migrated = json.loads(read(report_path(out)))["migrated"]
    assert any("workflow-carried-2026-01-01.md removed" in m for m in migrated), migrated
    assert "carried" not in read(proj(out, "alpha", "INDEX.md"))


def test_part_one_of_a_split_topic_is_always_the_topic_file(tmp: str) -> None:
    """A topic near its budget whose one section is superseded: the old
    section was counted as carried text, the new one pushed to part two,
    and the supersede then retired part one's only section and removed
    the file — `grow.md` became `grow-2.md` and every `[[grow]]` link
    dangled (a drain of 2026-09-25). The text being replaced is not
    carried, and part one is `<topic>.md` whenever the topic has any
    section; the index lists every part."""
    big = "y " * 850
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "grow", "title": "Big", "body": big, "evidence": ["h1"]},
        {"class": "domain", "topic": "other", "title": "Other", "body": "o", "evidence": ["h2"]},
    ])})
    assert run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    d = dom(out, "alpha", "domain")
    assert sorted(n for n in os.listdir(d) if n.startswith("grow")) == ["grow.md"]
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "grow", "title": "Big", "merge_target": "Big",
         "body": "z " * 850, "evidence": ["h3"]},
    ])
    proc = run_assemble(drain, claims_dir, out, "--budget", "500")
    assert proc.returncode == 0, proc.stderr
    parts = sorted(n for n in os.listdir(d) if n.startswith("grow"))
    assert parts == ["grow.md"], f"part one lost its name: {parts}"
    assert ("z " * 850).strip() in read(os.path.join(d, "grow.md"))

    # Carried text plus a new claim over the budget: two parts, the first
    # still grow.md, and the index lists both.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "grow", "title": "More", "body": "m " * 850, "evidence": ["h1"]},
    ])
    proc = run_assemble(drain, claims_dir, out, "--budget", "500")
    assert proc.returncode == 0, proc.stderr
    parts = sorted(n for n in os.listdir(d) if n.startswith("grow"))
    assert parts == ["grow-2.md", "grow.md"], parts
    index = read(proj(out, "alpha", "INDEX.md"))
    assert all(f"domain/{p}" in index for p in parts), index

    # A part one gone from an earlier drain's tree is restored from the
    # lowest part when the topic is next written.
    os.replace(os.path.join(d, "grow.md"), os.path.join(d, "grow-3.md"))
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "grow", "title": "More", "body": "m " * 850, "evidence": ["h1"]},
    ])
    proc = run_assemble(drain, claims_dir, out, "--budget", "500")
    assert proc.returncode == 0, proc.stderr
    parts = sorted(n for n in os.listdir(d) if n.startswith("grow"))
    assert "grow.md" in parts, parts
    texts = "".join(read(os.path.join(d, p)) for p in parts)
    assert texts.count("## More") == 1 and texts.count("## Big") == 1, parts
    assert any("part one restored" in m for m in json.loads(read(report_path(out)))["migrated"])
    index = read(proj(out, "alpha", "INDEX.md"))
    assert all(f"domain/{p}" in index for p in parts), index


def harvest_report(drain: str, agent: str, host: str, next_watermark: int | None) -> None:
    with open(os.path.join(drain, "harvest-report.json"), "w", encoding="utf-8") as fh:
        json.dump({"agent": agent, "host": host, "since_watermark": 0, "next_watermark": next_watermark,
                   "counts": {"provisional_agent": 0, "in_scope": 1}}, fh)


def test_the_drain_report_gathers_every_bundle_of_one_drain(tmp: str) -> None:
    """A drain across accounts is one run per bundle into one working copy,
    and each run rewrote the report whole: the committed report described
    the last bundle alone, and an index-only run wrote empty watermarks
    (a drain's blind review, 2026-09-25). Runs of one stamp merge; a new
    stamp replaces all but the watermarks, which never move back; and no
    path in the report is absolute."""
    drain_a, claims_a, out = build(os.path.join(tmp, "a"), {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "Same title", "body": "First.", "evidence": ["h1"]},
        {"class": "domain", "topic": "one", "title": "Same title", "body": "Second.", "evidence": ["h2"]},
        {"class": "solution", "topic": "long", "title": "A cue that runs on " * 20,
         "body": "Seen in Springfield.", "evidence": ["h3"]},
    ])})
    harvest_report(drain_a, "dev-01", "hostA", 2000)
    proc = run_assemble(drain_a, claims_a, out, *keep_both(tmp, "alpha/domain:one#Same title"))
    assert proc.returncode == 0, proc.stderr
    drain_b, claims_b, _ = build(os.path.join(tmp, "b"), {"beta": claims("beta", [
        {"class": "solution", "topic": "two", "title": "Beta fact", "body": "b", "evidence": ["h2"]},
    ])})
    harvest_report(drain_b, "dev-02", "hostB", 3000)
    proc = run_assemble(drain_b, claims_b, out)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(read(report_path(out)))
    assert report["roles"] == ["alpha", "beta"], f"the first bundle's roles were lost: {report['roles']}"
    assert [d["key"] for d in report["collision_decisions"]] == ["alpha/domain:one#Same title"], \
        report["collision_decisions"]
    assert report["watermarks"] == {"dev-01@hostA": 2000, "dev-02@hostB": 3000}, report["watermarks"]
    assert set(report["telemetry"]) == {"alpha", "beta"}, report["telemetry"]
    assert any("alpha/" in f for f in report["files"]) and any("beta/" in f for f in report["files"]), report["files"]
    assert report["files_written"] == len(report["files"])

    # Every path is relative: to the working copy, or to the fabric root.
    text = read(report_path(out))
    assert tmp not in text and os.path.realpath(tmp) not in text, "an absolute path reached the report"
    paths = report["files"] + [e.split(":")[0] for e in report["redactions"] + report["clipped_descriptions"]]
    assert report["redactions"] and report["clipped_descriptions"], report
    assert all(not p.startswith(("/", "..")) for p in paths), paths
    assert ".agent-fabric/memory/beta/solution.md" in report["files"], report["files"]
    assert "memory/domains/alpha/domain.md" in report["files"], report["files"]

    # Re-running a bundle does not count it twice.
    admitted = report["telemetry"]["beta"]["admitted"]
    assert run_assemble(drain_b, claims_b, out).returncode == 0
    assert json.loads(read(report_path(out)))["telemetry"]["beta"]["admitted"] == admitted

    # An index-only run (no claims, a harvest that read nothing) keeps
    # every watermark and every earlier bundle's record.
    drain_c, claims_c, _ = build(os.path.join(tmp, "c"), {"beta": claims("beta", [])})
    harvest_report(drain_c, "dev-02", "hostB", None)
    assert run_assemble(drain_c, claims_c, out).returncode == 0
    report = json.loads(read(report_path(out)))
    assert report["watermarks"] == {"dev-01@hostA": 2000, "dev-02@hostB": 3000}, report["watermarks"]
    assert report["roles"] == ["alpha", "beta"] and report["collision_decisions"], report

    # The next drain replaces the record. A harvest sets its own store's
    # mark, lower too — the harvester holds it below a memory it could not
    # render, so that memory is read again — and leaves every other store's.
    harvest_report(drain_b, "dev-02", "hostB", 2500)
    assert run_assemble(drain_b, claims_b, out, "--stamp", "2026-01-02").returncode == 0
    report = json.loads(read(report_path(out)))
    assert report["stamp"] == "2026-01-02" and report["roles"] == ["beta"], report["roles"]
    assert report["collision_decisions"] == [], report["collision_decisions"]
    assert report["watermarks"] == {"dev-01@hostA": 2000, "dev-02@hostB": 2500}, report["watermarks"]


def test_a_claim_body_s_own_headings_never_open_a_section(tmp: str) -> None:
    """A claim renders as one `## <heading>` section, but a memory may
    carry `## ` headings of its own; the reader split the section at
    them, the first part lost its dated footer, and re-running the same
    bundle was refused as a collision with itself. Body headings are
    demoted one level, the same claims twice give a byte-identical tree,
    and a slice already written the old way is repaired on its next
    write rather than refused."""
    body = "Intro line.\n\n## Inner heading\n\nInner text.\n\n### Deeper\n\nDeep text."
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "doc", "title": "A structured memory", "body": body,
         "evidence": ["h1"], "observed_at": "2026-09-20"},
        {"class": "domain", "topic": "other", "title": "Other", "body": "o", "evidence": ["h2"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    path = dom(out, "alpha", "domain", "doc.md")
    before = tree(out)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, f"the same bundle again was refused:\n{proc.stderr}"
    assert tree(out) == before, "the same claims twice changed the tree"
    text = read(path)
    assert text.count("\n## ") == 1 and "### Inner heading" in text and "#### Deeper" in text, text
    assert "*Observed 2026-09-20 (alpha)*" in text, text

    # A slice written before the demotion: its body headings split it.
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace("### Inner heading", "## Inner heading").replace("#### Deeper", "### Deeper"))
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, f"a slice written the old way was refused against itself:\n{proc.stderr}"
    assert read(path) == text, read(path)
    assert tree(out) == before


def test_one_agent_s_memories_in_a_flat_class_file_are_not_one_retitled_memory(tmp: str) -> None:
    """A flat class file holds every memory of its class until the class
    splits. Read as the one topic of the drain, sections one agent wrote
    for other memories made that agent's next memory a "retitle", and
    the same-agent rule deleted every earlier memory (a drain's blind
    review, 2026-09-26). A new memory is a new fact: A, B and C all
    stand. In the topic's own file a retitle still supersedes, and so
    does the agent's new text under its own heading."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "topic-a", "title": "Fact A", "body": "A.", "evidence": ["a1"]},
    ])})
    with_agents(drain, {"a1": "dev-01", "a2": "dev-01", "a3": "dev-01", "a4": "dev-01", "a5": "dev-01"})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    for topic, title, h in (("topic-b", "Fact B", "a2"), ("topic-c", "Fact C", "a3")):
        set_claims(claims_dir, "alpha", [
            {"class": "domain", "topic": topic, "title": title, "body": title[-1] + ".", "evidence": [h]},
        ])
        proc = run_assemble(drain, claims_dir, out)
        assert proc.returncode == 0, proc.stderr
        assert "SUPERSEDED" not in proc.stderr, proc.stderr
    flat = read(dom(out, "alpha", "domain.md"))
    assert all(f"## Fact {x}" in flat for x in "ABC"), f"an earlier memory was deleted:\n{flat}"

    # The directory shape: the topic's own file is one memory.
    drain2, claims2, out2 = build(os.path.join(tmp, "dir"), {"alpha": claims("alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue open", "body": "Open.", "evidence": ["a1"]},
        {"class": "domain", "topic": "other", "title": "Other", "body": "O.", "evidence": ["a2"]},
    ])})
    with_agents(drain2, {"a1": "dev-01", "a2": "dev-01", "a3": "dev-01", "a4": "dev-01"})
    assert run_assemble(drain2, claims2, out2).returncode == 0
    set_claims(claims2, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue merged", "body": "Merged.", "evidence": ["a3"]},
    ])
    proc = run_assemble(drain2, claims2, out2)
    assert proc.returncode == 0 and "SUPERSEDED, same agent" in proc.stderr, proc.stderr
    tracker = dom(out2, "alpha", "domain", "tracker.md")
    assert "## Issue merged" in read(tracker) and "Issue open" not in read(tracker), read(tracker)
    set_claims(claims2, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue merged", "body": "Merged and released.", "evidence": ["a4"]},
    ])
    proc = run_assemble(drain2, claims2, out2)
    assert proc.returncode == 0 and "SUPERSEDED, same agent" in proc.stderr, proc.stderr
    assert "Merged and released." in read(tracker) and read(tracker).count("## ") == 1, read(tracker)
    assert "## Other" in read(dom(out2, "alpha", "domain", "other.md"))


def test_two_claims_of_one_drain_under_a_heading_the_corpus_holds_still_stop_it(tmp: str) -> None:
    """The corpus holds "Status" (dev-01); one drain brings two claims of
    the topic, both "Status", with different texts, both dev-01. Looked
    for only where the corpus lacked the heading, the pair was never
    seen: each was superseded by the same-agent rule and the later one
    won silently (a drain's blind review, 2026-09-26). Which of the two
    is newer is not the corpus's to say: the run stops, writing nothing."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Open.", "evidence": ["a1"]},
        {"class": "domain", "topic": "other", "title": "Other", "body": "O.", "evidence": ["a2"]},
    ])})
    with_agents(drain, {"a1": "dev-01", "a2": "dev-01", "a3": "dev-01", "a4": "dev-01"})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Merged.", "evidence": ["a3"]},
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Reverted.", "evidence": ["a4"]},
    ])
    before = tree(out)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "SUPERSEDING?" in proc.stderr, proc.stderr
    assert "alpha/domain:tracker#Status@a4" in proc.stderr and "in this drain" in proc.stderr, proc.stderr
    assert tree(out) == before, "a refused drain must not touch the tree"

    # The first of the pair equal to the corpus is still the pair's first.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Open.", "evidence": ["a1"]},
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Reverted.", "evidence": ["a4"]},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "in this drain" in proc.stderr, proc.stderr
    assert tree(out) == before
    # …and in the other order: the claim equal to the corpus coming second
    # passed as a no-op after the first had superseded it, and the old text
    # came back as "Status (2)" (the re-review of #41, 2026-09-26).
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Reverted.", "evidence": ["a4"]},
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Open.", "evidence": ["a1"]},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "SUPERSEDING?" in proc.stderr and "SUPERSEDED, same agent" not in proc.stderr, proc.stderr
    assert tree(out) == before


def test_an_agents_new_text_under_its_own_heading_in_a_flat_file_supersedes(tmp: str) -> None:
    """The class is still one flat file holding one agent's memories. A new
    text under a heading that agent wrote replaces that one section: the
    same-HEADING rule touches no other memory, so it holds in a shared file
    where the retitle inference must not (the re-review of #41, 2026-09-26)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "topic-a", "title": "Fact A", "body": "A.", "evidence": ["a1"]},
    ])})
    with_agents(drain, {"a1": "dev-01", "a2": "dev-01"})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    flat = dom(out, "alpha", "domain.md")
    assert os.path.isfile(flat), "the class is one flat file"
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "topic-a", "title": "Fact A", "body": "A, updated.", "evidence": ["a2"],
         "observed_at": "2026-09-20"},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0 and "SUPERSEDED, same agent" in proc.stderr, proc.stderr
    assert "A, updated." in read(flat) and read(flat).count("## ") == 1, read(flat)
    # An OLDER text of the same agent (a replayed bundle) is asked about,
    # never applied over the newer section (the review of #41, 2026-09-26).
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "topic-a", "title": "Fact A", "body": "A, stale.", "evidence": ["a2"],
         "observed_at": "2000-01-01"},
    ])
    before = read(flat)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "SUPERSEDING?" in proc.stderr, proc.stderr
    assert read(flat) == before


def test_the_same_agent_rule_never_replaces_newer_text(tmp: str) -> None:
    """The rule replaces an agent's OLDER text with its newer one. A
    supersede retires the heading's kept-both siblings "X (n)" too, and a
    retitle every section of the topic: a claim dated before ANY of those is
    asked about, never applied (the re-review of #41, 2026-09-26). And a
    claim repeating the first claim of a contested heading adds nothing to
    decide."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Open.", "evidence": ["a1"],
         "observed_at": "2026-01-01"},
        {"class": "domain", "topic": "other", "title": "Other", "body": "O.", "evidence": ["a9"]},
    ])})
    with_agents(drain, {"a1": "dev-01", "a2": "dev-01", "a3": "dev-01", "a4": "dev-01", "a5": "dev-01", "a9": "dev-01"})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    # The owner keeps a newer text beside it as "Status (2)".
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Merged.", "evidence": ["a2"],
         "observed_at": "2026-09-20"},
    ])
    assert run_assemble(drain, claims_dir, out, *keep_both(tmp, "alpha/domain:tracker#Status")).returncode == 0
    tracker = dom(out, "alpha", "domain", "tracker.md")
    if not os.path.exists(tracker):
        tracker = dom(out, "alpha", "domain.md")
    assert "## Status (2)" in read(tracker), read(tracker)
    before = read(tracker)
    # Older than the kept sibling: asked, not applied.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Reverted.", "evidence": ["a3"],
         "observed_at": "2026-05-01"},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "SUPERSEDING?" in proc.stderr, proc.stderr
    assert read(tracker) == before
    # An older RETITLE: asked, not applied.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Status, retitled", "body": "Old.", "evidence": ["a4"],
         "observed_at": "2000-01-01"},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert "SUPERSEDED, same agent" not in proc.stderr, proc.stderr
    assert proc.returncode == 1 and read(tracker) == before, proc.stderr
    # A contested heading whose third claim repeats the first: only the
    # differing text is a question.
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Merged again.", "evidence": ["a4"]},
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Reverted.", "evidence": ["a5"]},
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Merged again.", "evidence": ["a3"]},
    ])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "tracker#Status@a5" in proc.stderr and "tracker#Status@a3" not in proc.stderr, proc.stderr
    # …and the owner's heading-wide supersede leaves ONE section: the repeat
    # does not slip past the decision as "Status (2)".
    proc = run_assemble(drain, claims_dir, out, "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:tracker#Status": "supersede"}))
    assert proc.returncode == 0, proc.stderr
    heads = [line for line in read(tracker).splitlines() if line.startswith("## Status")]
    assert heads == ["## Status"], read(tracker)
    # The repeat's evidence and agent stay in the provenance: a second agent
    # asserting the same text keeps the topic two agents' (re-review of #41).
    with_agents(drain, {"a1": "dev-01", "a2": "dev-01", "a3": "dev-01", "a4": "dev-01", "a5": "dev-01",
                        "a9": "dev-01", "b7": "dev-02"})
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Held.", "evidence": ["a1"]},
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Closed.", "evidence": ["a2"]},
        {"class": "domain", "topic": "tracker", "title": "Status", "body": "Held.", "evidence": ["b7"]},
    ])
    proc = run_assemble(drain, claims_dir, out, "--collision-decisions",
                        decisions_file(tmp, {"alpha/domain:tracker#Status": "supersede"}))
    assert proc.returncode == 0, proc.stderr
    text = read(tracker)
    assert "b7" in text and '"dev-02"' in text, "the repeat's evidence or agent left the provenance:\n" + text


def test_a_correction_of_a_section_in_another_part_takes_its_own_heading(tmp: str) -> None:
    """Topic `grow` split by budget: `grow.md` holds "Big", `grow-2.md`
    "More". A claim "More, corrected" with merge_target "More" is written
    into part one, the target retired from part two — and the section
    was written as "## More", the stale cue the correction replaced (a
    drain's blind review, 2026-09-26). It carries its own heading."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "grow", "title": "Big", "body": "y " * 850, "evidence": ["h1"]},
        {"class": "domain", "topic": "other", "title": "Other", "body": "o", "evidence": ["h2"]},
    ])})
    assert run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "grow", "title": "More", "body": "m " * 850, "evidence": ["h1"]},
    ])
    assert run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    d = dom(out, "alpha", "domain")
    assert "## More" in read(os.path.join(d, "grow-2.md")) and "## Big" in read(os.path.join(d, "grow.md")), \
        "precondition: Big in part one, More in part two"
    set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "grow", "title": "More, corrected", "merge_target": "More",
         "body": "Less than thought.", "evidence": ["h3"]},
    ])
    proc = run_assemble(drain, claims_dir, out, "--budget", "500")
    assert proc.returncode == 0, proc.stderr
    texts = "".join(read(os.path.join(d, n)) for n in sorted(os.listdir(d)) if n.startswith("grow"))
    headings = re.findall(r"(?m)^## .*$", texts)
    assert "## More, corrected\n\nLess than thought." in texts, headings
    assert "## More" not in headings, f"the corrected section kept the stale heading: {headings}"
    assert "m m m" not in texts and texts.count("## Big") == 1, texts


def test_an_unresolved_merge_target_is_reported_on_every_drain(tmp: str) -> None:
    """A correction whose merge_target names no section is written as its
    own topic and reported. The next drain bringing it found its heading
    in its own topic and said nothing, while the section it meant to
    replace still stood (a drain's blind review, 2026-09-26). Every drain
    that brings it reports it, the tree unchanged."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "orphan", "title": "An orphan correction",
         "merge_target": "No such heading", "body": "Text.", "evidence": ["h1"]},
        {"class": "domain", "topic": "other", "title": "Other", "body": "o", "evidence": ["h2"]},
    ])})
    for stamp in ("2026-01-01", "2026-01-02"):
        proc = run_assemble(drain, claims_dir, out, "--stamp", stamp)
        assert proc.returncode == 0, proc.stderr
        assert "MERGE TARGET UNRESOLVED" in proc.stderr and "No such heading" in proc.stderr, \
            f"drain of {stamp} said nothing:\n{proc.stderr}"
        unresolved = json.loads(read(report_path(out))).get("merge_target_unresolved") or []
        assert any("No such heading" in u for u in unresolved), (stamp, unresolved)
    names = sorted(os.listdir(dom(out, "alpha", "domain")))
    assert names == ["orphan.md", "other.md"], names
    assert read(dom(out, "alpha", "domain", "orphan.md")).count("## ") == 1


def test_a_merged_drain_report_keeps_every_harvest_and_only_files_that_exist(tmp: str) -> None:
    """Runs of one stamp merge into one report. It kept only the last
    bundle's harvest record, and every file any run wrote — a part a
    later run of the stamp retired stayed listed and counted in
    files_written (a drain's blind review, 2026-09-26). The harvest is
    kept per source; the files are those the tree holds."""
    drain_a, claims_a, out = build(os.path.join(tmp, "a"), {"alpha": claims("alpha", [
        {"class": "domain", "topic": "grow", "title": "Big", "body": "y " * 850, "evidence": ["h1"]},
        {"class": "domain", "topic": "other", "title": "Other", "body": "o", "evidence": ["h2"]},
    ])})
    harvest_report(drain_a, "dev-01", "hostA", 2000)
    assert run_assemble(drain_a, claims_a, out, "--budget", "500").returncode == 0
    drain_b, claims_b, _ = build(os.path.join(tmp, "b"), {"beta": claims("beta", [
        {"class": "domain", "topic": "two", "title": "Beta fact", "body": "b", "evidence": ["h2"]},
    ])})
    harvest_report(drain_b, "dev-02", "hostB", 3000)
    assert run_assemble(drain_b, claims_b, out).returncode == 0
    report = json.loads(read(report_path(out)))
    sources = report.get("harvest_sources") or {}
    assert set(sources) == {"dev-01@hostA", "dev-02@hostB"}, f"a bundle's harvest record was lost: {sources}"
    assert sources["dev-01@hostA"]["next_watermark"] == 2000 and sources["dev-02@hostB"]["next_watermark"] == 3000, sources

    # A part written by one run of the stamp and removed by the next.
    set_claims(claims_a, "alpha", [
        {"class": "domain", "topic": "grow", "title": "More", "body": "m " * 850, "evidence": ["h1"]},
    ])
    assert run_assemble(drain_a, claims_a, out, "--budget", "500").returncode == 0
    grow2 = dom(out, "alpha", "domain", "grow-2.md")
    assert os.path.exists(grow2), "precondition: the topic split into two parts"
    set_claims(claims_a, "alpha", [
        {"class": "domain", "topic": "grow", "title": "More, corrected", "merge_target": "More",
         "body": "Less.", "evidence": ["h3"]},
    ])
    assert run_assemble(drain_a, claims_a, out, "--budget", "500").returncode == 0
    assert not os.path.exists(grow2), "precondition: the correction removed part two"
    report = json.loads(read(report_path(out)))
    gone = [f for f in report["files"]
            if not any(os.path.exists(os.path.join(root, f)) for root in (working_copy(out), out))]
    assert not gone, f"the report lists files the tree no longer holds: {gone}"
    assert report["files_written"] == len(report["files"]), report["files_written"]
    assert set(report["harvest_sources"]) == {"dev-01@hostA", "dev-02@hostB"}, report["harvest_sources"]


def test_a_topic_named_like_a_budget_part_is_its_own_memory(tmp: str) -> None:
    """Memories `release` and `release-2` are two topics, and
    `release-2.md` is also the name part two of `release` would get.
    Taken for a part by its name, `release-2`'s section was `release`'s:
    the same-agent retitle of `release` retired it and removed the file
    (a drain's blind review, 2026-09-26). The slice names its topic in
    its frontmatter; an older slice without one is a part unless the
    drain or the crossref names it as a topic."""
    release = {"class": "domain", "topic": "release", "title": "Release process", "body": "Tag, then build.",
               "evidence": ["a1"]}
    second = {"class": "domain", "topic": "release-2", "title": "Second release notes", "body": "Shipped twice.",
              "evidence": ["a2"]}
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [release, second])})
    with_agents(drain, {"a1": "dev-01", "a2": "dev-01", "a3": "dev-01", "a4": "dev-01"})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    d = dom(out, "alpha", "domain")
    set_claims(claims_dir, "alpha", [dict(release, title="Release process, revised", evidence=["a3"])])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert os.path.exists(os.path.join(d, "release-2.md")), f"another memory was retired as a part: {sorted(os.listdir(d))}"
    assert "## Second release notes" in read(os.path.join(d, "release-2.md"))
    assert "## Release process, revised" in read(os.path.join(d, "release.md"))
    assert 'topic: "release-2"\n' in read(os.path.join(d, "release-2.md")), read(os.path.join(d, "release-2.md"))

    # Slices written before the topic was recorded: the drain naming
    # `release-2` is the evidence, and another agent's claim of `release`
    # under `release-2`'s heading is no rival of it.
    for name in ("release.md", "release-2.md"):
        path = os.path.join(d, name)
        legacy = re.sub(r"(?m)^topic: .*\n", "", read(path))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(legacy)
    set_claims(claims_dir, "alpha", [dict(release, title="Second release notes", body="Different.", evidence=["b1"]),
                                     second])
    with_agents(drain, {"a1": "dev-01", "a2": "dev-01", "a3": "dev-01", "b1": "dev-02"})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, f"another topic's section was read as this topic's rival:\n{proc.stderr}"
    assert "Shipped twice." in read(os.path.join(d, "release-2.md")), sorted(os.listdir(d))
    released = read(os.path.join(d, "release.md"))
    assert "Different." in released and "## Release process, revised" in released, released


def test_a_bundle_that_cannot_be_read_is_refused_in_one_line(tmp: str) -> None:
    """Every way a --bundle can be unreadable or malformed is one
    `assemble: bundle: ...` line and exit 1, as the verified refusals are:
    a missing file, a directory, not a tar, a tar cut short, a manifest or
    harvest report that is not the JSON object it names, a manifest naming
    no agent. Each was a traceback, which a person on a drain cannot read
    (review of the assembler's split, 2026-10-05)."""
    import hashlib
    import io
    import tarfile

    def bundle(name: str, members: list[tuple[str, bytes]] | None = None, raw: bytes | None = None) -> str:
        path = os.path.join(tmp, name)
        if raw is not None:
            with open(path, "wb") as fh:
                fh.write(raw)
            return path
        with tarfile.open(path, "w") as t:
            for n, data in members or []:
                info = tarfile.TarInfo(n)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        return path

    def manifest(**extra) -> bytes:
        return json.dumps({"format": "agent-fabric-drain/1", **extra}).encode()

    bad_report = b"{not json"
    forged = json.dumps({"agent": "dev-01", "host": "hostA", "role": "alpha", "project": None,
                         "store": "victim@hostA#x"}).encode()
    named = {"harvest-report.json": hashlib.sha256(bad_report).hexdigest()}
    good = bundle("whole.tar", [("manifest.json", manifest(files=named)), ("harvest-report.json", bad_report)])
    os.makedirs(os.path.join(tmp, "a-directory"))
    cases = {
        os.path.join(tmp, "absent.tar"): "absent.tar cannot be read",
        os.path.join(tmp, "a-directory"): "a-directory cannot be read",
        bundle("empty.tar", raw=b""): "not a readable tar",
        bundle("text.tar", raw=b"plain text, not a tar\n"): "not a readable tar",
        bundle("cut.tar", raw=open(good, "rb").read()[:700]): "not a readable tar",
        bundle("list.tar", [("manifest.json", b"[1, 2]")]): "manifest.json is not an object",
        bundle("files.tar", [("manifest.json", manifest(files=["x"]))]): "manifest.json's files is not an object",
        good: "harvest-report.json does not parse",
        bundle("report-list.tar", [("manifest.json", manifest(files={"harvest-report.json": hashlib.sha256(b"[1]").hexdigest()})),
                                   ("harvest-report.json", b"[1]")]): "harvest-report.json is not an object",
        bundle("forged-store.tar", [("manifest.json", manifest(agent="dev-01", host="hostA", role="alpha", project=None,
                                                              files={"harvest-report.json": hashlib.sha256(forged).hexdigest()})),
                                    ("harvest-report.json", forged)]): "names the store 'victim@hostA#x'",
        bundle("no-agent.tar", [("manifest.json", manifest(files={"harvest-report.json": hashlib.sha256(b"{}").hexdigest()})),
                                ("harvest-report.json", b"{}")]): "manifest.json names no agent",
    }
    os.makedirs(os.path.join(working_copy(tmp), ".agent-fabric"), exist_ok=True)
    # A good bundle from an unregistered working copy: project null, as the
    # harvest writes it. Read as before, never refused for it.
    files = {"claims/alpha.json": json.dumps(claims("alpha", [
                 {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]}])).encode(),
             "observations.jsonl": (json.dumps(OBSERVATIONS[0]) + "\n").encode(),
             "references.json": json.dumps(REFERENCES).encode(),
             "harvest-report.json": json.dumps({"agent": "dev-01", "host": "hostA", "role": "alpha",
                                                "project": None}).encode()}
    nullp = bundle("null-project.tar", [("manifest.json", manifest(agent="dev-01", host="hostA", role="alpha", project=None,
                                                                    files={n: hashlib.sha256(d).hexdigest() for n, d in files.items()})),
                                        *files.items()])
    proc = subprocess.run([sys.executable, ASSEMBLE, "--bundle", nullp, "--fabric", tmp, "--project", PROJECT,
                           "--working-copy", working_copy(tmp), "--stamp", "2026-01-01"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0 and "file(s) verified" in proc.stdout, proc.stdout + proc.stderr
    for path, said in cases.items():
        proc = subprocess.run(
            [sys.executable, ASSEMBLE, "--bundle", path, "--fabric", tmp, "--project", PROJECT,
             "--working-copy", working_copy(tmp), "--stamp", "2026-01-01"],
            capture_output=True, text=True, timeout=60)
        lines = proc.stderr.strip().split("\n")
        assert proc.returncode == 1, f"{os.path.basename(path)}: exit {proc.returncode}\n{proc.stderr}"
        assert len(lines) == 1 and lines[0].startswith("assemble: bundle: ") and said in lines[0], \
            f"{os.path.basename(path)}: not one refusal line naming it:\n{proc.stderr}"


def test_a_malformed_hygiene_list_stops_the_drain_in_one_line(tmp: str) -> None:
    """A project's hygiene.json that does not parse, holds a key nothing
    reads, a pattern that does not compile, or a scope that is not
    "others" withholds nothing: skipped, it let every name it lists into
    the corpus without a word. The drain stops, one line naming the file,
    nothing written (the 2026-10-05 drain's review, B6)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    hyg = os.path.join(working_copy(out), ".agent-fabric", "hygiene.json")
    os.makedirs(os.path.dirname(hyg), exist_ok=True)
    for broken, said in (
        ("{not json", "does not parse"),
        (json.dumps({"patterns": [{"pattern": "x", "scop": "others"}]}), "keys this does not read: scop"),
        (json.dumps({"patterns": [{"pattern": "(unclosed"}]}), "does not compile"),
        (json.dumps({"patterns": [{"pattern": "x", "scope": "mine"}]}), "the one scope is"),
        (json.dumps({"patterns": [{"label": "no pattern"}]}), "has no pattern"),
        (json.dumps({"patterns": [{"pattern": "x", "flags": "I"}]}), "the one flag is"),
        (json.dumps(["not", "an", "object"]), "\"patterns\" list"),
    ):
        with open(hyg, "w", encoding="utf-8") as fh:
            fh.write(broken)
        proc = run_assemble(drain, claims_dir, out)
        lines = proc.stderr.strip().split("\n")
        assert proc.returncode == 1 and len(lines) == 1 and lines[0].startswith("assemble: ") \
            and "hygiene.json" in lines[0] and said in lines[0], f"{broken!r}:\n{proc.stderr}"
        assert not os.path.exists(dom(out, "alpha")), "a slice was written past a broken list"


def test_a_name_scoped_others_stays_in_its_own_projects_slices_only(tmp: str) -> None:
    """"scope": "others" marks a name as its project's own (the owner,
    2026-10-05: gzapp's slices may name the city): the project's own slice
    keeps it, a domain slice of the same drain still has it withheld, and
    another project's slices withhold it too (B9)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "solution", "topic": "where", "title": "Where it runs", "body": "The pilot runs in Springfield.",
         "evidence": ["h1"]},
        {"class": "domain", "topic": "cities", "title": "Cities", "body": "Springfield has a grid plan.",
         "evidence": ["h2"]},
    ])})
    hyg = os.path.join(working_copy(out), ".agent-fabric", "hygiene.json")
    os.makedirs(os.path.dirname(hyg), exist_ok=True)
    with open(hyg, "w", encoding="utf-8") as fh:
        json.dump({"patterns": [{"pattern": "\\bspringfield\\b", "flags": "i", "label": "city name",
                                 "scope": "others"}]}, fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "The pilot runs in Springfield." in read(proj(out, "alpha", "solution.md")), "the project's own slice lost its name"
    domain = read(dom(out, "alpha", "domain.md"))
    assert "Springfield" not in domain and "[redacted] has a grid plan." in domain, domain
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    import importlib
    layout = importlib.import_module("layout")
    saved = (layout.FABRIC_ROOT, dict(layout._WORKING_COPIES))
    try:
        layout.FABRIC_ROOT = out
        layout.set_working_copy(PROJECT, working_copy(out))
        labels = lambda **kw: [label for _p, label, _r in layout.load_hygiene_patterns([PROJECT], **kw)]
        assert "city name" in labels(), "with no project named, every pattern applies"
        assert "city name" in labels(for_project="another"), "another project's slices must withhold it"
        assert "city name" not in labels(for_project=PROJECT), "its own project's slices may name it"
    finally:
        layout.FABRIC_ROOT = saved[0]
        layout._WORKING_COPIES.clear()
        layout._WORKING_COPIES.update(saved[1])


def test_the_memories_skipped_for_no_roles_class_are_named_in_the_committed_report(tmp: str) -> None:
    """The harvest names the memories it left out for want of a roles_class;
    the drain directory that held that list is temporary, so the committed
    report carries it, per source, under the same hygiene as any committed
    text (the 2026-10-05 drain's review, B7)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    with open(os.path.join(drain, "harvest-report.json"), "w", encoding="utf-8") as fh:
        json.dump({"agent": "dev-01", "host": "hostA", "next_watermark": 5, "counts": {"in_scope": 3},
                   "skipped_no_roles_class": ["private-notes", "springfield-trip"]}, fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(read(report_path(out)))
    assert report["harvest"]["skipped_no_roles_class"] == ["[redacted]-trip", "private-notes"], report["harvest"]
    assert report["harvest_sources"]["dev-01@hostA"]["skipped_no_roles_class"] == ["[redacted]-trip", "private-notes"]
    assert "springfield" not in read(report_path(out)).lower()


def test_a_held_back_slice_is_neither_written_nor_reported_as_the_drains(tmp: str) -> None:
    """--hold: the coordinator holds a slice back from a drain. A hand
    revert after a first run left the report naming it in files,
    files_written, collision_decisions and clipped_descriptions; the
    re-run of the stamp with --hold writes nothing of it and drops what
    the first run said of it, and lists it as held_back (B2). A key that
    names no slice of the drain is refused, not held by nobody."""
    long_title = "Held " + "and long " * 40
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "kept", "title": "Kept", "body": "Stays.", "evidence": ["h1"]},
        {"class": "domain", "topic": "held", "title": long_title, "body": "First, in Springfield.", "evidence": ["h1"]},
        {"class": "domain", "topic": "held", "title": long_title, "body": "Second.", "evidence": ["h2"]},
        {"class": "domain", "topic": "sh", "title": "Shared", "body": "Both know it.", "evidence": ["h1"],
         "shared_with": ["beta"]},
    ])})
    heading = long_title.strip()
    proc = run_assemble(drain, claims_dir, out, *keep_both(tmp, f"alpha/domain:held#{heading}"))
    assert proc.returncode == 0, proc.stderr
    held_file = dom(out, "alpha", "domain", "held.md")
    first = json.loads(read(report_path(out)))
    held_rel = [f for f in first["files"] if f.endswith("domain/held.md")]
    assert held_rel and any(c.startswith(held_rel[0]) for c in first["clipped_descriptions"]), first
    assert any(d["key"].startswith("alpha/domain:held#") for d in first["collision_decisions"]), first
    os.remove(held_file)   # the hand revert of slices that were new
    os.remove(shared_path(out, "domain-sh.md"))
    hold = os.path.join(tmp, "hold.json")
    with open(hold, "w", encoding="utf-8") as fh:
        json.dump(["alpha/domain:held", "shared/domain:sh"], fh)
    proc = run_assemble(drain, claims_dir, out, "--hold", hold, *keep_both(tmp, f"alpha/domain:held#{heading}"))
    assert proc.returncode == 0, proc.stderr
    assert not os.path.exists(held_file), "a held slice was written"
    report = json.loads(read(report_path(out)))
    assert report["held_back"] == ["alpha/domain:held", "shared/domain:sh"], report["held_back"]
    said = json.dumps({k: report[k] for k in ("files", "clipped_descriptions", "collision_decisions", "redactions",
                                               "shared_topics")})
    assert "held.md" not in said and "domain:held" not in said and "domain:sh" not in said, said
    assert report["shared_slices"] == 0, report
    assert report["files_written"] == len(report["files"]) and any(f.endswith("domain/kept.md") for f in report["files"]), report
    # The same stamp again without --hold writes the slices: no longer held.
    proc = run_assemble(drain, claims_dir, out, *keep_both(tmp, f"alpha/domain:held#{heading}"))
    assert proc.returncode == 0, proc.stderr
    third = json.loads(read(report_path(out)))
    assert third["held_back"] == [] and os.path.exists(held_file), third["held_back"]
    with open(hold, "w", encoding="utf-8") as fh:
        json.dump(["alpha/domain:nothing-by-that-name"], fh)
    proc = run_assemble(drain, claims_dir, out, "--hold", hold)
    lines = proc.stderr.strip().split("\n")
    assert proc.returncode == 1 and len(lines) == 1 and "names no slice of this drain: alpha/domain:nothing-by-that-name" in lines[0], proc.stderr


def read_slice_meta(path: str):
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    import importlib
    return importlib.import_module("assembler.slices").read_existing_slice(path)


def test_a_flat_file_moved_in_is_deduplicated_by_text_and_restamped(tmp: str) -> None:
    """A flat class file moved into its directory under one topic's name
    can still hold another topic's section, written there by an earlier
    collision as "Two (2)": the drain writing that topic's own file left
    the copy beside it. The moved file is deduplicated against the drain's
    topics by text, not heading, and it carries this drain's stamp and the
    topic it is now named for (the 2026-10-05 drain's review, B4)."""
    one = {"class": "workflow", "topic": "alpha-one", "title": "One", "body": "First way.", "evidence": ["h1"]}
    two = {"class": "workflow", "topic": "alpha-two", "title": "Two", "body": "Second way.", "evidence": ["h2"]}
    three = {"class": "workflow", "topic": "three", "title": "Three", "body": "Third way.", "evidence": ["h3"]}
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [one])})
    assert run_assemble(drain, claims_dir, out).returncode == 0
    flat = proj(out, "alpha", "workflow.md")
    text = read(flat).replace("distilled_at: 2026-01-01", "distilled_at: 2025-12-01")
    with open(flat, "w", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n\n## Two (2)\n\nSecond way.\n")
    # One's topic brings no claim this time: only the move touches its file.
    set_claims(claims_dir, "alpha", [two, three])
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    wf = proj(out, "alpha", "workflow")
    assert sorted(os.listdir(wf)) == ["alpha-one.md", "alpha-two.md", "three.md"], sorted(os.listdir(wf))
    moved = read(os.path.join(wf, "alpha-one.md"))
    assert "Second way." not in moved and "## One" in moved, moved
    assert "Second way." in read(os.path.join(wf, "alpha-two.md"))
    assert any(f.endswith("workflow/alpha-one.md") for f in json.loads(read(report_path(out)))["files"]), \
        "a moved and restamped file is this drain's too"
    meta, _sections = read_slice_meta(os.path.join(wf, "alpha-one.md"))
    assert meta.get("distilled_at") == "2026-01-01" and meta.get("topic") == "alpha-one", meta
    migrated = json.loads(read(report_path(out)))["migrated"]
    assert any("'Two (2)' dropped from workflow/alpha-one.md" in m for m in migrated), migrated

    # Moved and restamped with nothing to drop: still this drain's file.
    plain = os.path.join(tmp, "plain")
    drain2, claims2, out2 = build(plain, {"alpha": claims("alpha", [one])})
    assert run_assemble(drain2, claims2, out2).returncode == 0
    set_claims(claims2, "alpha", [two, three])
    proc = run_assemble(drain2, claims2, out2)
    assert proc.returncode == 0, proc.stderr
    files = json.loads(read(report_path(out2)))["files"]
    assert any(f.endswith("workflow/alpha-one.md") for f in files), files


def test_every_role_the_project_binds_with_domain_slices_gets_an_index(tmp: str) -> None:
    """A role the project's taxonomy binds, whose domain holds slices, must
    be indexed by the project (lint holds every visible project to it), even
    when the drain brought that role nothing: InterWeave's lint was red for
    two such roles (the 2026-10-05 drain's review, B5)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    os.makedirs(os.path.join(working_copy(out), ".agent-fabric"), exist_ok=True)
    with open(os.path.join(working_copy(out), ".agent-fabric", "taxonomy.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "project": PROJECT, "roles": [{"id": "alpha"}, {"id": "beta"}, {"id": "gamma"}]}, fh)
    os.makedirs(dom(out, "beta"), exist_ok=True)
    with open(dom(out, "beta", "domain.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: beta\nclass: domain\ndescription: What beta knows of the field\ntier: 2\n---\n\n## X\n\nY.\n")
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    index = read(proj(out, "beta", "INDEX.md"))
    assert "memory/domains/beta/domain.md" in index and "What beta knows of the field" in index, index
    assert not os.path.exists(proj(out, "gamma")), "a bound role with no domain slice needs no index"
    with open(os.path.join(working_copy(out), ".agent-fabric", "taxonomy.json"), "w", encoding="utf-8") as fh:
        fh.write("{broken")
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "taxonomy cannot be read" in proc.stderr, proc.stderr
    # Refused before anything is written: a fresh fabric with a shared claim
    # and a broken taxonomy gets no file at all.
    fresh = os.path.join(tmp, "fresh")
    drain2, claims2, out2 = build(fresh, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "sh", "title": "S", "body": "b", "evidence": ["h1"], "shared_with": ["beta"]},
    ])})
    os.makedirs(os.path.join(working_copy(out2), ".agent-fabric"), exist_ok=True)
    with open(os.path.join(working_copy(out2), ".agent-fabric", "taxonomy.json"), "w", encoding="utf-8") as fh:
        fh.write("{broken")
    proc = run_assemble(drain2, claims2, out2)
    assert proc.returncode == 1 and not os.path.exists(os.path.join(out2, "memory")), \
        f"a slice was written before the taxonomy refused: {proc.stderr}"


def test_a_correction_retitling_a_carried_files_only_section_renames_its_cue(tmp: str) -> None:
    """A carried file keeps the cue it moved with, since it names several
    topics. When a correction's merge_target retitles its only section, that
    cue named the stale section: the file's description, and the index line,
    take the correction's heading (the 2026-10-05 drain's review, B8)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "workflow", "topic": "fix", "title": "New cue", "body": "Corrected.", "merge_target": "Old cue",
         "evidence": ["h1"]},
    ])})
    wf = proj(out, "alpha", "workflow")
    os.makedirs(wf, exist_ok=True)
    head = "---\nrole: alpha\nclass: workflow\ndescription: {cue}\ntier: 1\n---\n\n"
    with open(os.path.join(wf, "workflow-carried-2025-12-01.md"), "w", encoding="utf-8") as fh:
        fh.write(head.format(cue="Old cue") + "## Old cue\n\nStale.\n")
    with open(os.path.join(wf, "other.md"), "w", encoding="utf-8") as fh:
        fh.write(head.format(cue="Other") + "## Other\n\nO.\n")
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    carried = read(os.path.join(wf, "workflow-carried-2025-12-01.md"))
    assert "## New cue" in carried and "Stale." not in carried, carried
    assert "description: New cue" in carried or 'description: "New cue"' in carried, carried
    index = read(proj(out, "alpha", "INDEX.md"))
    assert "workflow-carried-2025-12-01.md) — New cue" in index and "Old cue" not in index, index


def test_a_withheld_name_in_a_topic_reaches_no_note(tmp: str) -> None:
    """Every redaction note names its claim by topic: built from the topic
    before it was substituted, the notes carried the very name they said
    was withheld, into stderr and the committed report (B3's review, F4)."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "springfield-grid", "title": "Springfield grid", "body": "Springfield is gridded.",
         "evidence": ["h1"]},
    ])})
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    report = read(report_path(out))
    assert json.loads(report)["redactions"], report
    for said in (report, proc.stderr):
        assert "springfield" not in said.lower(), said


def test_two_stores_of_one_account_keep_two_watermarks(tmp: str) -> None:
    """The projects root's own memory files under the fabric checkout beside
    the checkout's own: one key for both let the later drain's mark skip
    the other store's unread memories (B1's review, F2). A harvest that
    names its store (--store) is kept under agent@host#<store>, and reads
    its own mark back."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    report_file = os.path.join(drain, "harvest-report.json")
    for store, mark in ((None, 200), ("dev-01@hostA#projects-root", 99)):
        with open(report_file, "w", encoding="utf-8") as fh:
            json.dump({"agent": "dev-01", "host": "hostA", "next_watermark": mark, "counts": {},
                       **({"store": store} if store else {})}, fh)
        proc = run_assemble(drain, claims_dir, out)
        assert proc.returncode == 0, proc.stderr
    report = json.loads(read(report_path(out)))
    assert report["watermarks"] == {"dev-01@hostA": 200, "dev-01@hostA#projects-root": 99}, report["watermarks"]
    assert set(report["harvest_sources"]) == {"dev-01@hostA", "dev-01@hostA#projects-root"}, report["harvest_sources"]
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    import importlib
    harvest = importlib.import_module("harvest_memory")
    key = harvest.store_key("dev-01", "hostA", "projects-root")
    assert harvest.previous_watermark(working_copy(out), "hostA", "dev-01", key)[0] == 99
    assert harvest.previous_watermark(working_copy(out), "hostA", "dev-01")[0] == 200


def test_a_harvest_naming_another_accounts_store_is_refused_before_any_write(tmp: str) -> None:
    """A harvest report's store becomes a committed watermark: one naming
    another account's store would move that account's mark and skip its
    unread memories, unsaid (B's re-review, finding 1). Refused before
    anything is written; the account's own second store is accepted."""
    drain, claims_dir, out = build(tmp, {"alpha": claims("alpha", [
        {"class": "domain", "topic": "one", "title": "T", "body": "b", "evidence": ["h1"]},
    ])})
    report_file = os.path.join(drain, "harvest-report.json")
    with open(report_file, "w", encoding="utf-8") as fh:
        json.dump({"agent": "dev-01", "host": "hostA", "next_watermark": 9, "store": "victim@hostA"}, fh)
    proc = run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "names the store 'victim@hostA'" in proc.stderr, proc.stderr
    assert not os.path.exists(os.path.join(out, "memory")), "written before the refusal"
    with open(report_file, "w", encoding="utf-8") as fh:
        json.dump({"agent": "dev-01", "host": "hostA", "next_watermark": 9, "store": "dev-01@hostA#projects-root"}, fh)
    assert run_assemble(drain, claims_dir, out).returncode == 0


def test_holding_a_shared_slice_keeps_the_notes_of_a_role_slice_under_the_same_key(tmp: str) -> None:
    """A note names the slice its claim lands in: holding shared/domain:sh
    drops the shared slice's notes and keeps those of gamma's own
    domain:sh, which this run wrote (B's re-review, finding 2)."""
    drain, claims_dir, out = build(tmp, {
        "alpha": claims("alpha", [{"class": "domain", "topic": "sh", "title": "Shared", "body": "In Springfield.",
                                   "evidence": ["h1"], "shared_with": ["beta"]}]),
        "gamma": claims("gamma", [{"class": "domain", "topic": "sh", "title": "Own", "body": "Also Springfield.",
                                   "evidence": ["h2"]}]),
    })
    hold = os.path.join(tmp, "hold.json")
    with open(hold, "w", encoding="utf-8") as fh:
        json.dump(["shared/domain:sh"], fh)
    proc = run_assemble(drain, claims_dir, out, "--hold", hold)
    assert proc.returncode == 0, proc.stderr
    redactions = json.loads(read(report_path(out)))["redactions"]
    assert [r for r in redactions if " body:" in r] == ["gamma/domain:sh body: city name -> '[redacted]'"], redactions
    assert os.path.exists(dom(out, "gamma", "domain.md"))


def main() -> int:
    cases = [
        test_a_topic_named_like_a_budget_part_is_its_own_memory,
        test_a_merged_drain_report_keeps_every_harvest_and_only_files_that_exist,
        test_an_unresolved_merge_target_is_reported_on_every_drain,
        test_a_correction_of_a_section_in_another_part_takes_its_own_heading,
        test_two_claims_of_one_drain_under_a_heading_the_corpus_holds_still_stop_it,
        test_an_agents_new_text_under_its_own_heading_in_a_flat_file_supersedes,
        test_the_same_agent_rule_never_replaces_newer_text,
        test_one_agent_s_memories_in_a_flat_class_file_are_not_one_retitled_memory,
        test_a_claim_body_s_own_headings_never_open_a_section,
        test_the_drain_report_gathers_every_bundle_of_one_drain,
        test_part_one_of_a_split_topic_is_always_the_topic_file,
        test_a_claim_in_the_carried_file_is_not_written_twice,
        test_a_retitled_memory_replaces_its_own_old_section,
        test_a_correction_naming_another_topic_s_section_replaces_it_there,
        test_places_claims_and_writes_provenance,
        test_unresolved_origin_is_stated_not_invented,
        test_index_lists_every_slice,
        test_index_banner_names_which_sections_load_when,
        test_committed_indexes_carry_the_banner_the_assembler_emits,
        test_fabric_links_use_the_sibling_prefix_even_when_the_checkout_is_nested,
        test_a_banned_term_in_title_or_topic_is_redacted_too_and_a_person_becomes_the_role,
        test_an_overlong_description_is_clipped_everywhere_it_appears,
        test_a_flat_class_file_moves_into_the_directory_when_the_class_splits,
        test_an_oversized_single_claim_is_written_whole_and_reported,
        test_drain_report_carries_the_watermark_forward,
        test_drain_report_records_unattributable_rows,
        test_drain_report_tolerates_a_drain_with_no_harvest_report,
        test_unattributable_rows_warn_loudly_but_do_not_fail_the_drain,
        test_a_fully_attributed_drain_says_nothing_about_bindings,
        test_output_is_byte_stable,
        test_slice_splits_when_it_exceeds_budget,
        test_budget_accounts_for_what_merge_mode_carries,
        test_claim_owned_by_two_roles_is_stored_once,
        test_shared_claims_reach_every_owner_crossref,
        test_crossref_maps_artifacts_to_slices,
    test_an_empty_crossref_is_said_not_just_written,
    test_a_crossref_with_entries_says_nothing,
        test_merge_mode_preserves_earlier_drains,
        test_index_keeps_slices_this_drain_did_not_touch,
        test_a_title_containing_a_newline_is_not_truncated,
        test_a_class_never_gets_both_a_flat_file_and_a_directory,
        test_a_hash_shaped_like_a_number_survives_the_frontmatter,
        test_carried_full_scope_survives_a_domain_only_drain,
        test_merge_target_strengthens_instead_of_appending,
        test_a_collision_stops_the_drain_until_the_owner_decides,
        test_the_owner_supersedes_or_drops_a_colliding_claim,
        test_collision_is_reported_on_every_run,
        test_collision_survives_a_drain_with_an_empty_delta,
        test_authored_headings_are_not_mistaken_for_collisions,
        test_a_collision_slice_passes_lint,
        test_quoted_titles_survive_repeated_drains,
        test_merge_target_clears_the_collision_it_resolves,
        test_collision_scan_ignores_authored_documents,
        test_carried_sections_keep_their_citation_edges,
        test_carried_evidence_keeps_its_origin,
        test_domain_only_evidence_may_only_support_a_domain_claim,
        test_domain_only_evidence_is_accepted_on_a_domain_claim,
        test_hygiene_violation_is_redacted_in_place,
        test_carried_text_is_redacted_the_same_way_a_claim_is,
        test_the_same_claim_again_is_never_a_collision_whatever_its_date,
        test_keep_both_is_remembered_on_the_next_drain,
        test_another_topic_in_the_flat_class_file_is_not_this_topic_s_rival,
        test_a_collision_inside_a_two_topic_flat_file_is_still_stopped,
        test_drop_on_a_shared_topic_keeps_it_in_every_owner_s_index,
        test_supersede_retires_the_section_in_the_part_that_holds_it,
        test_a_retired_sibling_already_indexed_this_run_is_re_listed_by_what_remains,
        test_a_retired_sibling_loses_its_collision_record_and_clips_its_cue,
        test_each_colliding_claim_has_its_own_decision_key,
        test_non_english_slice_is_rejected_by_the_assembler,
        test_lint_detects_index_drift,
        test_scratchpad_references_are_normalized,
        test_a_tracked_scratchpad_path_is_left_alone,
        test_same_named_temp_artifacts_stay_distinct,
        test_lint_rejects_a_session_temp_crossref_key,
        test_a_bundle_that_cannot_be_read_is_refused_in_one_line,
        test_a_malformed_hygiene_list_stops_the_drain_in_one_line,
        test_a_name_scoped_others_stays_in_its_own_projects_slices_only,
        test_the_memories_skipped_for_no_roles_class_are_named_in_the_committed_report,
        test_a_held_back_slice_is_neither_written_nor_reported_as_the_drains,
        test_a_flat_file_moved_in_is_deduplicated_by_text_and_restamped,
        test_every_role_the_project_binds_with_domain_slices_gets_an_index,
        test_a_correction_retitling_a_carried_files_only_section_renames_its_cue,
        test_a_withheld_name_in_a_topic_reaches_no_note,
        test_two_stores_of_one_account_keep_two_watermarks,
        test_a_harvest_naming_another_accounts_store_is_refused_before_any_write,
        test_holding_a_shared_slice_keeps_the_notes_of_a_role_slice_under_the_same_key,
    ]
    # THE REGISTRY IS THE TRAP THIS GUARDS. Cases run because they are
    # listed here, not because they are named test_*, so a case that is
    # written and not listed passes silently and forever — it never
    # runs. Two were added that way and only a mutation that should have
    # failed, and did not, revealed it.
    declared = {
        name for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    }
    listed = {case.__name__ for case in cases}
    missing = sorted(declared - listed)
    if missing:
        print(f"  FAIL registry: defined but never run: {missing}")
        return 1

    failures = 0
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                case(tmp)
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
