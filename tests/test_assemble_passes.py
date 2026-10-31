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


def main() -> int:
    cases = [
        test_a_second_pass_over_two_bundles_with_a_chained_correction_and_a_flat_class_file_changes_nothing,
        test_a_chain_in_one_bundle_is_applied_in_one_pass,
        test_the_bundle_of_a_chain_run_alone_again_leaves_the_corrected_text_once,
        test_an_older_text_of_the_same_agent_is_no_collision_on_the_second_pass,
        test_a_revert_is_not_dropped_and_its_original_then_stands,
        test_a_replayed_text_is_named_in_the_report_and_not_written,
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
