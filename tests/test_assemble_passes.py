#!/usr/bin/env python3
"""A second pass over one drain's bundles leaves the tree byte-identical (j82; the 2026-10-31 drain changed 12 files and
raised SUPERSEDING? on four bundles on its second pass). The same claims in, the same tree out: a claim already applied is a
no-op, and the text a correction took out is not written back by the bundle that still carries it.

Each case runs a drain's bundles in order twice over one tree and compares the tree (every file but the drain report, which
says what each run did). The fixtures are test_assemble.py's own, imported.

Stdlib only; runnable as `python3 test_assemble_passes.py`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_assemble as ta  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

AGENTS = {"h1": "dev-01", "h2": "dev-02", "h3": "dev-02", "h4": "dev-01", "h5": "dev-02", "h6": "dev-01"}


def claim(topic: str, title: str, body: str, evidence: str, target: str | None = None, klass: str = "solution", **extra) -> dict:
    return {"class": klass, "topic": topic, "title": title, "body": body, "evidence": [evidence],
            **({"merge_target": target} if target else {}), **extra}


ORIGINAL = claim("t", "Status v1 of the thing", "Original text of the finding.", "h1")
CORRECTION_A = claim("fix-a", "Status v2 of the thing", "Text A, a longer correction.", "h2", "Status v1 of the thing")
CORRECTION_B = claim("fix-b", "Status v3 of the thing", "Text B, the second correction.", "h3", "Status v2 of the thing")
FLAT_CLASS = claim("lone", "A lone topic", "The only topic of its class, so a flat class file.", "h5", klass="domain")


def two_passes(tmp: str, bundles: list[list[dict]]) -> tuple[str, dict[str, str], dict[str, str], list[int]]:
    """Run the bundles in order, then again; the tree after each pass and the second pass's exit codes."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    ta.with_agents(drain, AGENTS)

    def one_pass() -> list[int]:
        codes = []
        for bundle in bundles:
            ta.set_claims(claims_dir, "alpha", bundle)
            proc = ta.run_assemble(drain, claims_dir, out)
            codes.append(proc.returncode)
            assert proc.returncode == 0, proc.stderr
        return codes

    one_pass()
    first = ta.tree(out)
    codes = one_pass()
    return out, first, ta.tree(out), codes


def assert_converged(first: dict[str, str], second: dict[str, str]) -> None:
    changed = sorted(k for k in set(first) | set(second) if first.get(k) != second.get(k))
    assert not changed, f"the second pass changed {changed}"


def held(tree: dict[str, str]) -> str:
    return "".join(v for k, v in sorted(tree.items()) if "/solution" in k and k.endswith(".md") and "INDEX" not in k)


def test_a_second_pass_over_two_bundles_with_a_chained_correction_and_a_flat_class_file_changes_nothing(tmp: str) -> None:
    """The memory in one bundle, its correction and the correction of that correction in the next, and a class of one topic
    (a flat file) beside them. The control is the first pass: the corrections applied, the replaced texts gone."""
    out, first, second, _codes = two_passes(tmp, [[ORIGINAL, FLAT_CLASS], [CORRECTION_A, CORRECTION_B]])
    text = held(first)
    assert "Text B, the second correction." in text and "Original text" not in text and "Text A," not in text, text
    assert os.path.isfile(ta.dom(out, "alpha", "domain.md")) or os.path.isfile(ta.proj(out, "alpha", "domain.md")), "precondition: the class of one topic is a flat file"
    assert_converged(first, second)


def test_a_chain_in_one_bundle_is_applied_in_one_pass(tmp: str) -> None:
    """B names the heading A gives its section, which the corpus holds only once A is applied: B was written as a topic of its
    own and the next pass replaced A in the other slice, leaving B's text twice. The same bundle carries the memory and both
    corrections in the third case: each correction follows the claim it corrects."""
    for bundles in ([[ORIGINAL], [CORRECTION_A, CORRECTION_B]], [[ORIGINAL, CORRECTION_A, CORRECTION_B]]):
        with tempfile.TemporaryDirectory() as sub:
            _out, first, second, _codes = two_passes(sub, bundles)
            text = held(first)
            assert text.count("Text B, the second correction.") == 1 and "Original text" not in text and "Text A," not in text, text
            assert_converged(first, second)


def test_the_bundle_of_a_chain_run_alone_again_leaves_the_corrected_text_once(tmp: str) -> None:
    """The single-bundle re-run of a chained merge_target re-appended A."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    ta.with_agents(drain, AGENTS)
    for bundle in ([ORIGINAL], [CORRECTION_A], [CORRECTION_B], [CORRECTION_A, CORRECTION_B], [ORIGINAL]):
        ta.set_claims(claims_dir, "alpha", bundle)
        proc = ta.run_assemble(drain, claims_dir, out)
        assert proc.returncode == 0, proc.stderr
    text = held(ta.tree(out))
    assert text.count("## ") == 1 and "Text B, the second correction." in text, text


def test_an_older_text_of_the_same_agent_is_no_collision_on_the_second_pass(tmp: str) -> None:
    """Pass 1's newer text stands in the corpus (the same-agent rule replaced the older one); the older bundle, read again, is
    the text that was replaced, not a claim against the newer one."""
    older = claim("x", "X heading here", "First text of x, in words.", "h1", observed_at="2026-09-01")
    newer = claim("x", "X heading here", "Newer text of x, in words.", "h4", observed_at="2026-09-20")
    _out, first, second, _codes = two_passes(tmp, [[older], [newer]])
    assert "Newer text of x" in held(first) and "First text of x" not in held(first), held(first)
    assert_converged(first, second)


def test_a_revert_is_not_dropped_and_its_original_then_stands(tmp: str) -> None:
    """The control of the drop: a correction whose merge_target stands is a real replacement even when its text was replaced
    once; and after the revert the original text is the corpus's own, so its bundle is a no-op."""
    revert = claim("revert", "Status v1 of the thing", "Original text of the finding.", "h6", "Status v2 of the thing")
    out, first, second, _codes = two_passes(tmp, [[ORIGINAL], [CORRECTION_A], [revert]])
    text = held(first)
    assert "Original text of the finding." in text and "Text A," not in text, text
    assert_converged(first, second)
    # The original is the corpus's own text again, so its bundle is no replay.
    notes = json.loads(ta.read(ta.report_path(out)))["superseded_harvests"]
    assert not any("memory 't'" in n for n in notes), notes


def test_a_replayed_text_is_named_in_the_report_and_not_written(tmp: str) -> None:
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    ta.with_agents(drain, AGENTS)
    for bundle in ([ORIGINAL], [CORRECTION_A]):
        ta.set_claims(claims_dir, "alpha", bundle)
        assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    ta.set_claims(claims_dir, "alpha", [ORIGINAL])
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    listed = json.loads(ta.read(ta.report_path(out)))["superseded_harvests"]
    assert any("memory 't'" in line and "not written" in line for line in listed), listed
    assert "Original text" not in held(ta.tree(out))


def test_a_correction_recorded_before_replaced_sections_existed_drops_the_replayed_original(tmp: str) -> None:
    """The herdr drain of 2026-11-01: the correction was applied by a drain of 2026-10-18, whose report has applied_corrections
    and no replaced_sections, and another agent of the role carried the original memory again. Not a collision: the original."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    ta.with_agents(drain, AGENTS)
    for bundle in ([ORIGINAL], [CORRECTION_A]):
        ta.set_claims(claims_dir, "alpha", bundle)
        assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    before = ta.tree(out)
    report = json.loads(ta.read(ta.report_path(out)))
    assert report["applied_corrections"] and report["replaced_sections"], "precondition: this run's report records both"
    del report["replaced_sections"]
    with open(ta.report_path(out), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    other_agent = claim("t-other", "Status v1 of the thing", "Original text of the finding.", "h6", observed_at="2026-09-01")
    ta.set_claims(claims_dir, "alpha", [other_agent])
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert held(ta.tree(out)) == held(before) and "Original text" not in held(ta.tree(out)), held(ta.tree(out))


def test_a_correction_replayed_after_its_revert_is_written_and_named(tmp: str) -> None:
    """After a revert the corpus holds the original again, so the bundle of the first correction reads as that correction's first
    run: nothing says it is a replay. It is written, and the report names it, so the run is not silent (a review of #445, F3)."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    ta.with_agents(drain, AGENTS)
    revert = claim("revert", "Status v1 of the thing", "Original text of the finding.", "h6", "Status v2 of the thing")
    for bundle in ([ORIGINAL], [CORRECTION_A], [revert]):
        ta.set_claims(claims_dir, "alpha", bundle)
        assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    ta.set_claims(claims_dir, "alpha", [CORRECTION_A])
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    named = json.loads(ta.read(ta.report_path(out)))["reharvested_replaced"]
    assert any("memory 'fix-a'" in n and "re-applies" in n for n in named), named
    assert "REHARVESTED UNDER A REPLACED HEADING" in proc.stderr, proc.stderr


def test_other_text_under_a_replaced_heading_is_named_with_both_keys(tmp: str) -> None:
    """The control of the drop: reworded text is no replay, so it is written (verify_replacements judges it) and the note says
    which keys differ, so a person can tell a reworded memory from a defect in the drop."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    ta.with_agents(drain, AGENTS)
    for bundle in ([ORIGINAL], [CORRECTION_A]):
        ta.set_claims(claims_dir, "alpha", bundle)
        assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    ta.set_claims(claims_dir, "alpha", [claim("t", "Status v1 of the thing", "Reworded original text of the finding.", "h6")])
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1 and "REPLACED SECTION STANDS" in proc.stderr, proc.stderr
    assert "carries other text than the section 'Status v1 of the thing' a correction replaced" in proc.stderr, proc.stderr


def test_a_decision_stated_again_by_a_rerun_keeps_its_place_in_the_report(tmp: str) -> None:
    """The second pass of the 2026-10-31 gzapp drain moved one collision decision to the end of the list: the same entry, the
    report's bytes different. The later run's value stands; the first run's place does."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "fabric"))
    from assembler.slices import merge_reports
    def decision(key: str, text: str) -> dict:
        return {"key": key, "decision": text}
    def run_report(*decisions: dict) -> dict:
        return {"stamp": "s", "files": [], "roles": [], "shared_topics": [], "retitles": [], "telemetry_sources": {},
                "collision_decisions": list(decisions)}
    first = merge_reports(run_report(decision("a", "keep-both")), run_report(decision("a", "keep-both")))
    both = merge_reports(first, run_report(decision("b", "drop")))
    again = merge_reports(both, run_report(decision("a", "keep-both, restated")))
    assert [d["key"] for d in again["collision_decisions"]] == ["a", "b"], again["collision_decisions"]
    assert again["collision_decisions"][0]["decision"] == "keep-both, restated", "the later run's value stands"


def test_a_replayed_original_whose_links_the_run_points_is_still_a_replay(tmp: str) -> None:
    """A correction memory merged into another topic's slice is linked by its new stem, in every claim of the run. The original
    that a correction replaced was recorded with the links it had when it was written, so its replay arrives with other links
    than the recorded text (herdr, 2026-11-01): the key of the body as the memory wrote it decides."""
    original = claim("t", "Status v1 of the thing", "Original text of the finding. See [[fix-x]].", "h1")
    other = claim("t2", "Other section here", "Text of another topic.", "h4")
    fix_x = claim("fix-x", "Other section, corrected", "Corrected text of the other topic, in full.", "h6", "Other section here")
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    ta.with_agents(drain, AGENTS)
    # The correction first, alone: the text it replaces is recorded with its links as written. The memory it links is merged
    # into another slice only afterwards.
    for bundle in ([original, other], [CORRECTION_A], [fix_x]):
        ta.set_claims(claims_dir, "alpha", bundle)
        assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    before = ta.tree(out)
    ta.set_claims(claims_dir, "alpha", [original, fix_x])
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "Original text" not in held(ta.tree(out)), held(ta.tree(out))
    assert held(ta.tree(out)) == held(before)


def test_an_earlier_drains_correction_is_not_judged_as_this_drains(tmp: str) -> None:
    """The report carries every earlier drain's applied corrections forward and restamps itself, so the second run of a new
    stamp read the old drain's corrections as its own and refused over a replaced heading that a later drain's claim holds
    (the 2026-10-31 drain, j84). The entry's own stamp decides. The control: a correction of this stamp that is undone is still
    refused."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    ta.with_agents(drain, AGENTS)

    def run(bundle: list[dict], stamp: str):
        ta.set_claims(claims_dir, "alpha", bundle)
        return ta.run_assemble(drain, claims_dir, out, "--stamp", stamp)

    for bundle in ([ORIGINAL], [CORRECTION_A]):
        assert run(bundle, "2026-10-12").returncode == 0
    # A later drain writes a section under the heading the old correction replaced: its own, new text.
    unrelated = claim("t2", "Other section here", "Text of another topic.", "h4")
    first = run([unrelated], "2026-10-31")
    assert first.returncode == 0, first.stderr
    assert "Text A," in held(ta.tree(out)), "precondition: the old correction is applied"
    # Writing the reused heading by hand stands in for the later drain's claim having been merged in an earlier run.
    with open(ta.proj(out, "alpha", "solution.md"), "a", encoding="utf-8") as fh:
        fh.write("\n## Status v1 of the thing\n\nA different finding that reuses the heading.\n")
    proc = run([unrelated], "2026-10-31")
    assert proc.returncode == 0, proc.stderr
    # Control: the same stamp's correction, undone by reworded text, is refused.
    other = claim("o", "Subject v1 here", "Original subject text.", "h1")
    fix = claim("fix-o", "Subject v2 here", "Corrected subject text, longer.", "h2", "Subject v1 here")
    assert run([other], "2026-10-31").returncode == 0 and run([fix], "2026-10-31").returncode == 0
    proc = run([claim("o", "Subject v1 here", "Reworded subject text.", "h6")], "2026-10-31")
    assert proc.returncode == 1 and "REPLACED SECTION STANDS" in proc.stderr, proc.stderr


def main() -> int:
    cases = [
        test_a_second_pass_over_two_bundles_with_a_chained_correction_and_a_flat_class_file_changes_nothing,
        test_a_chain_in_one_bundle_is_applied_in_one_pass,
        test_the_bundle_of_a_chain_run_alone_again_leaves_the_corrected_text_once,
        test_an_older_text_of_the_same_agent_is_no_collision_on_the_second_pass,
        test_a_revert_is_not_dropped_and_its_original_then_stands,
        test_a_replayed_text_is_named_in_the_report_and_not_written,
        test_a_correction_recorded_before_replaced_sections_existed_drops_the_replayed_original,
        test_a_correction_replayed_after_its_revert_is_written_and_named,
        test_other_text_under_a_replaced_heading_is_named_with_both_keys,
        test_a_decision_stated_again_by_a_rerun_keeps_its_place_in_the_report,
        test_a_replayed_original_whose_links_the_run_points_is_still_a_replay,
        test_an_earlier_drains_correction_is_not_judged_as_this_drains,
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
