#!/usr/bin/env python3
"""The correction shapes tools/fabric/assemble.py refuses (j81; #437 round 5, F10-F13 of the 2026-10-31 drain).

One case per rule, each with its control: the same run without the defect passes. A refusal names the claim key and the
rule, exits 1 and leaves the tree as it was (except the post-write check, which says its files are written). The fixtures
are test_assemble.py's own, imported.

Stdlib only; runnable as `python3 test_assemble_shapes.py`.
"""
from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_assemble as ta  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "fabric"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

LONG_HEADING = "Always verify a grep based guard with the system grep before trusting a local green run of the static suite"
BODY = "The finding, written out in full with its reason and what to do about it."


def seeded(tmp: str, shared: bool = False) -> tuple[str, str, str, dict]:
    """A corpus of two topics of one agent, each one section; `shared` files them as shared slices."""
    sw = {"shared_with": ["beta"]} if shared else {}
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "one", "title": LONG_HEADING, "body": "Old text of one.", "evidence": ["h1"], **sw},
        {"class": "workflow", "topic": "two", "title": "Second section", "body": "Old text of two.", "evidence": ["h2"], **sw},
    ])})
    ta.with_agents(drain, {"h1": "dev-01", "h2": "dev-01", "h3": "dev-01", "h4": "dev-01", "h5": "dev-01"})
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    return drain, claims_dir, out, sw


def correction(topic: str, title: str, target: str, body: str, evidence: str, sw: dict) -> dict:
    return {"class": "workflow", "topic": topic, "title": title, "merge_target": target, "body": body,
            "evidence": [evidence], **sw}


def refused(proc, out: str, before: dict, key: str, rule: str) -> None:
    assert proc.returncode == 1, proc.stderr
    assert key in proc.stderr and rule in proc.stderr, proc.stderr
    assert ta.tree(out) == before, "a refused drain must not touch the tree"


def test_a_one_word_correction_body_is_refused_and_a_full_text_passes(tmp: str) -> None:
    """F10: five corrections with the body "project" replaced five sections. The shared slice is judged like a role's."""
    for shared in (False, True):
        with tempfile.TemporaryDirectory() as sub:
            drain, claims_dir, out, sw = seeded(sub, shared)
            before = ta.tree(out)
            label = "shared" if shared else "alpha"
            ta.set_claims(claims_dir, "alpha", [correction("fix", "Corrected heading", "Second section", "project", "h3", sw)])
            refused(ta.run_assemble(drain, claims_dir, out), out, before,
                    f"{label}/workflow:two#Corrected heading@h3", "correction body is one word")
            # The control: the same correction with its text.
            ta.set_claims(claims_dir, "alpha", [correction("fix", "Corrected heading", "Second section", BODY, "h3", sw)])
            proc = ta.run_assemble(drain, claims_dir, out)
            assert proc.returncode == 0, proc.stderr
            assert BODY in "".join(ta.tree(out).values()) and "Old text of two." not in "".join(ta.tree(out).values())


def test_a_retire_is_no_one_word_body(tmp: str) -> None:
    """The empty body of a retire (ADR-050 rule 7) has no word; it is the rule's own control."""
    drain, claims_dir, out, sw = seeded(tmp)
    ta.set_claims(claims_dir, "alpha", [{"class": "workflow", "topic": "retire-two", "title": "Retire", "body": "",
                                         "merge_target": "Second section", "evidence": ["h3"]}])
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "Old text of two." not in "".join(ta.tree(out).values())


def test_two_corrections_of_different_sections_with_one_body_are_refused(tmp: str) -> None:
    """F10: the body of one correction written over several sections. The same body over ONE section is a repeat."""
    drain, claims_dir, out, sw = seeded(tmp)
    before = ta.tree(out)
    ta.set_claims(claims_dir, "alpha", [
        correction("fix-one", "Corrected one", LONG_HEADING, BODY, "h3", sw),
        correction("fix-two", "Corrected two", "Second section", BODY, "h4", sw),
    ])
    proc = ta.run_assemble(drain, claims_dir, out)
    refused(proc, out, before, "alpha/workflow:one#Corrected one@h3", "correction body equals another correction's")
    assert "alpha/workflow:two#Corrected two@h4" in proc.stderr, proc.stderr
    # The control: each its own text.
    ta.set_claims(claims_dir, "alpha", [
        correction("fix-one", "Corrected one", LONG_HEADING, BODY, "h3", sw),
        correction("fix-two", "Corrected two", "Second section", BODY + " Different words.", "h4", sw),
    ])
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr


def test_a_correction_title_that_is_a_prefix_of_its_target_is_refused(tmp: str) -> None:
    """F12: seven titles cut at 100 characters became the headings."""
    for shared in (False, True):
        with tempfile.TemporaryDirectory() as sub:
            drain, claims_dir, out, sw = seeded(sub, shared)
            before = ta.tree(out)
            label = "shared" if shared else "alpha"
            cut = LONG_HEADING[:60]
            ta.set_claims(claims_dir, "alpha", [correction("fix", cut, LONG_HEADING, BODY, "h3", sw)])
            refused(ta.run_assemble(drain, claims_dir, out), out, before,
                    f"{label}/workflow:one#{cut}@h3", "correction title is a prefix of the heading it replaces")
            # Controls: a title that merely shares the start, and the heading itself.
            for title in (LONG_HEADING[:60] + " — corrected", LONG_HEADING):
                ta.set_claims(claims_dir, "alpha", [correction("fix", title, LONG_HEADING, BODY, "h3", sw)])
                proc = ta.run_assemble(drain, claims_dir, out)
                assert proc.returncode == 0, proc.stderr


def test_a_replaced_heading_standing_after_the_write_fails_the_run(tmp: str) -> None:
    """F11: the replaced section was in the shared slice again. A later run of the drain brought the old memory's text under
    the replaced heading (a bundle cut before the correction), and nothing said that it undid the correction."""
    for shared in (False, True):
        with tempfile.TemporaryDirectory() as sub:
            drain, claims_dir, out, sw = seeded(sub, shared)
            ta.set_claims(claims_dir, "alpha", [correction("fix", "Corrected heading", "Second section", BODY, "h3", sw)])
            proc = ta.run_assemble(drain, claims_dir, out)
            assert proc.returncode == 0, proc.stderr
            assert "Second section" not in "".join(ta.tree(out).values()), "the correction replaced it, shared or not"
            # The control: a later run bringing something else.
            ta.set_claims(claims_dir, "alpha", [{"class": "workflow", "topic": "two", "title": "Unrelated news", "body": "Other.",
                                                 "evidence": ["h4"], **sw}])
            proc = ta.run_assemble(drain, claims_dir, out)
            assert proc.returncode == 0, proc.stderr
            # The same text harvested again is the correction's own predecessor (j82): a no-op, named, not an undo.
            ta.set_claims(claims_dir, "alpha", [{"class": "workflow", "topic": "two", "title": "Second section",
                                                 "body": "Old text of two.", "evidence": ["h5"], **sw}])
            proc = ta.run_assemble(drain, claims_dir, out)
            assert proc.returncode == 0 and "Second section" not in "".join(ta.tree(out).values()), proc.stderr
            # The defect: other text under the replaced heading, which nothing says is the old one.
            ta.set_claims(claims_dir, "alpha", [{"class": "workflow", "topic": "two", "title": "Second section",
                                                 "body": "Reworded old text of two.", "evidence": ["h5"], **sw}])
            proc = ta.run_assemble(drain, claims_dir, out)
            assert proc.returncode == 1, proc.stderr
            assert "replaced heading stands after the write" in proc.stderr and "Second section" in proc.stderr \
                and "WRITTEN" in proc.stderr, proc.stderr


def test_a_later_drain_reusing_a_replaced_heading_undoes_nothing(tmp: str) -> None:
    """The control of the check above: another stamp is another drain, whose section under the old title is its own."""
    drain, claims_dir, out, sw = seeded(tmp)
    ta.set_claims(claims_dir, "alpha", [correction("fix", "Corrected heading", "Second section", BODY, "h3", sw)])
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    # A later drain (another stamp) reusing the heading writes a section of its own: no earlier correction is undone.
    ta.set_claims(claims_dir, "alpha", [{"class": "workflow", "topic": "three", "title": "Second section",
                                         "body": "A new lesson under the old title.", "evidence": ["h4"], **sw}])
    assert ta.run_assemble(drain, claims_dir, out, "--stamp", "2026-01-02").returncode == 0
    ta.set_claims(claims_dir, "alpha", [{"class": "workflow", "topic": "three", "title": "Second section",
                                         "body": "A new lesson under the old title, again.", "evidence": ["h4"], **sw}])
    assert ta.run_assemble(drain, claims_dir, out, "--stamp", "2026-01-02").returncode == 0


def test_verify_replacements_names_the_claim_key_and_passes_a_removed_heading(tmp: str) -> None:
    """The writer's own record, read against the files: the heading standing is named by the claim's key; its absence passes."""
    from assembler import shapes
    path = os.path.join(tmp, "workflow-one.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("---\nrole: shared\nclass: workflow\ntopic: one\n---\n\n## Replaced heading\n\nText.\n")
    stub_layout = SimpleNamespace(project_report_path=lambda _p: os.path.join(tmp, "no-report.json"),
                                  working_copy_for=lambda _p: None, FABRIC_ROOT=None)
    saved = shapes.layout, shapes.in_report
    shapes.layout, shapes.in_report = stub_layout, lambda _run, p: os.path.basename(p)
    try:
        run = SimpleNamespace(project="demo", args=SimpleNamespace(stamp="2026-01-01"), reharvested_replaced=[], replacements=[("shared/workflow:one#New@h9", path, "Replaced heading")])
        assert shapes.verify_replacements(run) == 1
        run.replacements = [("shared/workflow:one#New@h9", path, "Another heading")]
        assert shapes.verify_replacements(run) is None
    finally:
        shapes.layout, shapes.in_report = saved


def flat_state(out: str) -> tuple[bool, list[str]]:
    base = ta.dom(out, "alpha")
    return os.path.exists(os.path.join(base, "domain.md")), sorted(os.listdir(os.path.join(base, "domain"))) \
        if os.path.isdir(os.path.join(base, "domain")) else []


def test_a_flat_file_recording_no_topic_does_not_take_another_topic(tmp: str) -> None:
    """F13: per-bundle runs each see one topic, so unrelated topics piled into brand-comms' domain.md. A flat file with no
    topic recorded is not known to be the drain's topic's: it moves into the directory and the topic gets a file of its own.
    The control is the same file recording its topic: the same topic stays flat and receives its claim."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "domain", "topic": "first", "title": "First fact", "body": "First.", "evidence": ["h1"]}])})
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    flat = ta.dom(out, "alpha", "domain.md")
    recorded = ta.read(flat)
    assert "\ntopic: first\n" in recorded, recorded

    # The control: a second claim of the recorded topic is written into the flat file.
    ta.set_claims(claims_dir, "alpha", [{"class": "domain", "topic": "first", "title": "More of first", "body": "More.", "evidence": ["h2"]}])
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    assert flat_state(out)[0] and "More of first" in ta.read(flat) and not flat_state(out)[1], flat_state(out)

    # The defect: the same file written before topics were recorded, and an unrelated topic arriving alone.
    legacy = "".join(line for line in ta.read(flat).splitlines(keepends=True) if not line.startswith("topic:"))
    with open(flat, "w", encoding="utf-8") as fh:
        fh.write(legacy)
    ta.set_claims(claims_dir, "alpha", [{"class": "domain", "topic": "unrelated", "title": "Unrelated fact", "body": "U.", "evidence": ["h3"]}])
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    has_flat, files = flat_state(out)
    assert not has_flat and files == ["domain-carried-2026-01-01.md", "unrelated.md"], (has_flat, files)
    carried = [f for f in files if f != "unrelated.md"]   # the carried file: the crossref's one topic is not a label to put on a file that may hold more
    assert "Unrelated fact" not in ta.read(ta.dom(out, "alpha", "domain", carried[0])), "the stranger piled into the old file"
    assert "First fact" in ta.read(ta.dom(out, "alpha", "domain", carried[0])), files
    assert "Unrelated fact" in ta.read(ta.dom(out, "alpha", "domain", "unrelated.md")), files


def test_a_one_word_body_is_refused_whatever_the_claim_carries_around_it(tmp: str) -> None:
    """The body alone is counted: citations and anchors are rendered after it, and a body of one word with
    any of them was applied (a review of #445, F2). The equal-body rule reads the same words."""
    for extra in ({"citations": {"memories": ["other-memory"]}}, {"anchors": ["tools/a.py::run"]}):
        with tempfile.TemporaryDirectory() as sub:
            drain, claims_dir, out, sw = seeded(sub)
            before = ta.tree(out)
            ta.set_claims(claims_dir, "alpha", [{**correction("fix", "Corrected heading", "Second section", "project", "h3", sw), **extra}])
            refused(ta.run_assemble(drain, claims_dir, out), out, before,
                    "alpha/workflow:two#Corrected heading@h3", "correction body is one word")
    with tempfile.TemporaryDirectory() as sub:
        drain, claims_dir, out, sw = seeded(sub)
        before = ta.tree(out)
        ta.set_claims(claims_dir, "alpha", [
            {**correction("fix-one", "Corrected one", LONG_HEADING, BODY, "h3", sw), "citations": {"memories": ["a-memory"]}},
            {**correction("fix-two", "Corrected two", "Second section", BODY, "h4", sw), "citations": {"memories": ["b-memory"]}}])
        refused(ta.run_assemble(drain, claims_dir, out), out, before, "alpha/workflow:one#Corrected one@h3",
                "correction body equals another correction's")


def test_a_correction_in_a_topic_named_for_a_date_is_not_undone_by_its_sibling_topic(tmp: str) -> None:
    """`deploy-2026-09-18` is a topic of its own beside `deploy-2026-09-17`, not a budget part of it: its section under the
    same heading is its own, and a correction of the first topic's is no write-back (a review of #445, F5)."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "deploy-2026-09-17", "title": "Daily status", "body": "Status of the 17th.", "evidence": ["h1"]},
        {"class": "workflow", "topic": "deploy-2026-09-18", "title": "Daily status", "body": "Status of the 18th.", "evidence": ["h2"]},
    ])})
    ta.with_agents(drain, {"h1": "dev-01", "h2": "dev-01", "h3": "dev-01"})
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    ta.set_claims(claims_dir, "alpha", [{"class": "workflow", "topic": "deploy-2026-09-17", "title": "Daily status, corrected",
                                         "merge_target": "Daily status", "body": "Status of the 17th, in full with its reason.",
                                         "evidence": ["h3"]}])
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    text = "".join(ta.tree(out).values())
    assert "Status of the 17th, in full" in text and "Status of the 18th." in text and "Status of the 17th." not in text, text


def main() -> int:
    cases = [
        test_a_one_word_correction_body_is_refused_and_a_full_text_passes,
        test_a_retire_is_no_one_word_body,
        test_two_corrections_of_different_sections_with_one_body_are_refused,
        test_a_correction_title_that_is_a_prefix_of_its_target_is_refused,
        test_a_replaced_heading_standing_after_the_write_fails_the_run,
        test_a_later_drain_reusing_a_replaced_heading_undoes_nothing,
        test_verify_replacements_names_the_claim_key_and_passes_a_removed_heading,
        test_a_flat_file_recording_no_topic_does_not_take_another_topic,
        test_a_one_word_body_is_refused_whatever_the_claim_carries_around_it,
        test_a_correction_in_a_topic_named_for_a_date_is_not_undone_by_its_sibling_topic,
    ]
    # A case written and not listed passes silently and forever (test_assemble_seams.py's registry guard).
    declared = {name for name, obj in sorted(globals().items()) if name.startswith("test_") and callable(obj)}
    missing = sorted(declared - {case.__name__ for case in cases})
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
