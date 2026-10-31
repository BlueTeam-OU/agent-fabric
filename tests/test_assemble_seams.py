#!/usr/bin/env python3
"""Behaviours of tools/fabric/assemble.py that tests/test_assemble.py left
unpinned: a mutation of each passed that suite on the code as it stood
before main() was cut into phases (j30), so the cut could not be shown to
keep them. Each case here passed on that code and fails when its seam is
broken. The fixtures are test_assemble.py's own, imported.

Stdlib only; runnable as `python3 test_assemble_seams.py`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_assemble as ta  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "fabric"))
from assembler.slices import read_existing_slice  # noqa: E402
from corrections import section_key  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

LONG = "A heading that runs on " + "and on " * 40 + "past every cue an index can show"


def description_of(path: str) -> str:
    for line in ta.read(path).split("\n"):
        if line.startswith("description: "):
            return json.loads(line[len("description: "):]) if line[len("description: ")] == '"' \
                else line[len("description: "):]
    raise AssertionError(f"{path} has no description line")


def test_an_owner_named_only_in_shared_with_gets_its_index(tmp: str) -> None:
    """A role can own knowledge only through another role's shared_with,
    with no claims file of its own in the drain. It is an owning role all
    the same: its INDEX.md is written and points at the shared slice."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "domain", "topic": "observability", "title": "Dashboards are shared",
         "body": "One metrics stack serves both.", "evidence": ["h1"], "shared_with": ["beta"]},
    ])})
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    index = ta.proj(out, "beta", "INDEX.md")
    assert os.path.exists(index), "beta owns the shared slice and must get an index"
    assert "shared/domain-observability.md" in ta.read(index), ta.read(index)
    assert "beta" in json.loads(ta.read(ta.report_path(out)))["roles"]


def test_a_project_collision_is_reported_relative_to_the_working_copy(tmp: str) -> None:
    """title_collisions names a project slice the way every other report
    list does: relative to the project's working copy, not to the fabric
    root the working copy happens to sit under."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "solution", "topic": "one", "title": "Same title", "body": "First.", "evidence": ["h1"]},
        {"class": "solution", "topic": "one", "title": "Same title", "body": "Second.", "evidence": ["h2"]},
    ])})
    proc = ta.run_assemble(drain, claims_dir, out, *ta.keep_both(tmp, "alpha/solution:one#Same title"))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(ta.read(ta.report_path(out)))["title_collisions"] == [
        ".agent-fabric/memory/alpha/solution.md: 'Same title' appears twice — set merge_target to resolve"
    ]


def test_a_retire_beside_a_flat_file_clips_the_siblings_new_cue(tmp: str) -> None:
    """A supersede written into the flat `<class>.md` retires its target
    from a numbered sibling beside it. The sibling's description follows
    its first remaining heading, clipped as every description is, and the
    clip is reported."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "solution", "topic": "t", "title": "Fixed", "body": "The corrected text.",
         "evidence": ["h1"], "merge_target": "Target"},
    ])})
    base = ta.proj(out, "alpha")
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, "solution.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: solution\ndescription: Other\ntier: 2\n---\n\n## Other\n\nStays.\n")
    sibling = os.path.join(base, "solution-2.md")
    with open(sibling, "w", encoding="utf-8") as fh:
        fh.write("---\nrole: alpha\nclass: solution\ndescription: Target\ntier: 2\n---\n\n"
                 f"## Target\n\nThe stale text.\n\n## {LONG}\n\nKept.\n")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "## Target" not in ta.read(sibling), ta.read(sibling)
    cue = description_of(sibling)
    assert cue.endswith("…") and len(cue) <= 240, cue
    assert "solution-2.md: description clipped" in proc.stderr, proc.stderr


def test_a_carried_copy_dropped_clips_the_carried_files_new_cue(tmp: str) -> None:
    """A section standing word for word in a topic's own file and in a
    carried file is dropped from the carried one. The carried file's
    description follows its first remaining heading, clipped as every
    description is, and the clip is reported."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "dup", "title": "Dup", "body": "Written twice.", "evidence": ["h1"]},
        {"class": "workflow", "topic": "other", "title": "Other", "body": "b", "evidence": ["h2"]},
    ])})
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    directory = ta.proj(out, "alpha", "workflow")
    carried = os.path.join(directory, "workflow-carried-2025-12-01.md")
    shutil.copyfile(os.path.join(directory, "dup.md"), carried)
    with open(carried, "a", encoding="utf-8") as fh:
        fh.write(f"\n## {LONG}\n\nKept.\n")
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    assert "## Dup" not in ta.read(carried), ta.read(carried)
    cue = description_of(carried)
    assert cue.endswith("…") and len(cue) <= 240, cue
    assert "workflow-carried-2025-12-01.md: description clipped" in proc.stderr, proc.stderr


def test_the_command_runs_in_isolated_mode(tmp: str) -> None:
    """`python -I` leaves the script's directory off sys.path. The command
    still finds what it reads beside it, and assembles a drain."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "domain", "topic": "ble", "title": "Advertisements are one-way",
         "body": "A passive beacon emits and never listens.", "evidence": ["h1"]},
    ])})
    os.makedirs(os.path.join(ta.working_copy(out), ".agent-fabric"), exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-I", ta.ASSEMBLE, "--claims", claims_dir, "--drain", drain,
         "--fabric", out, "--project", ta.PROJECT, "--working-copy", ta.working_copy(out),
         "--stamp", "2026-01-01"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "Advertisements are one-way" in ta.read(ta.dom(out, "alpha", "domain.md"))


def tree_of(out: str) -> dict[str, str]:
    """The corpus; the project's hygiene list is the fixture's, written by the first run of any case."""
    return {k: v for k, v in ta.tree(out).items() if not k.endswith("hygiene.json")}


def same_run_pair(tmp: str) -> tuple[str, str, str]:
    """A corpus holding 'Issue 851' (dev-01's text); then a drain in which dev-01 harvests a newer 'Issue 851' (claim A,
    memory `tracker`) and dev-02's memory `fix-note` names the heading in merge_target (claim B)."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue 851", "body": "Old text.", "evidence": ["a1"],
         "observed_at": "2026-09-20"}])})
    ta.with_agents(drain, {"a1": "dev-01", "a2": "dev-01", "b1": "dev-02"})
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    ta.set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue 851", "body": "A new lesson.", "evidence": ["a2"],
         "observed_at": "2026-09-24"},
        {"class": "domain", "topic": "fix-note", "title": "Issue 851 fixed", "body": "B correction.", "evidence": ["b1"],
         "observed_at": "2026-09-25", "merge_target": "Issue 851"}])
    return drain, claims_dir, out


def test_d1_two_claims_writing_one_heading_stop_the_drain_and_the_owner_decides(tmp: str) -> None:
    """j481 D1 (InterWeave #516, review 5716071440 F1): claim A under heading H (which the same-agent rule makes a
    replacement of the corpus's H) and claim B naming H in merge_target were applied one over the other, and A's text
    left the run with no report line. They are a contested heading: nothing written, both claim keys printed; a
    supersede on B's key keeps B and names A's memory in collision_decisions."""
    drain, claims_dir, out = same_run_pair(tmp)
    before = tree_of(out)
    standing = read_existing_slice(ta.dom(out, "alpha", "domain.md"))[1]["Issue 851"]
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 1, (proc.returncode, proc.stderr)
    assert "alpha/domain:tracker#Issue 851@b1" in proc.stderr and "alpha/domain:tracker#Issue 851@a2" in proc.stderr, proc.stderr
    assert tree_of(out) == before, "a refused drain writes nothing"
    key = "alpha/domain:tracker#Issue 851@b1"
    proc = ta.run_assemble(drain, claims_dir, out, "--collision-decisions", ta.decisions_file(tmp, {key: "supersede"}))
    assert proc.returncode == 0, proc.stderr
    text = ta.read(ta.dom(out, "alpha", "domain", "tracker.md"))
    assert "B correction." in text and "A new lesson." not in text, text
    assert description_of(ta.dom(out, "alpha", "domain", "tracker.md")) == "Issue 851 fixed"
    rows = {d["key"]: d for d in json.loads(ta.read(ta.report_path(out)))["collision_decisions"]}
    assert rows[key]["decision"] == "supersede" and rows[key]["memory"] == "fix-note", rows
    # B replaced the section the corpus held, not A's text, which never stood there (the row the lost claim left).
    (applied,) = json.loads(ta.read(ta.report_path(out)))["applied_corrections"]
    assert applied["replaced_key"] == section_key(standing), applied
    (lost,) = [d for d in rows.values() if d["decision"] == "superseded"]
    assert lost["memory"] == "tracker" and lost["by"] == key, rows
    # The positive control of the refusal: a pair of one text is no question (the same drain without B's difference).
    ta.set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "tracker", "title": "Issue 851", "body": "B correction.", "evidence": ["a2"]},
        {"class": "domain", "topic": "fix-note", "title": "Issue 851 fixed", "body": "B correction.", "evidence": ["b1"],
         "merge_target": "Issue 851"}])
    assert ta.run_assemble(drain, claims_dir, out, "--stamp", "2026-01-03").returncode == 0


def test_d1_keep_both_and_drop_leave_no_claim_unreported(tmp: str) -> None:
    drain, claims_dir, out = same_run_pair(tmp)
    key = "alpha/domain:tracker#Issue 851@b1"
    proc = ta.run_assemble(drain, claims_dir, out, "--collision-decisions", ta.decisions_file(tmp, {key: "keep-both"}))
    assert proc.returncode == 0, proc.stderr
    text = ta.read(ta.dom(out, "alpha", "domain", "tracker.md"))
    assert "A new lesson." in text and "B correction." in text, text
    drain, claims_dir, out = same_run_pair(os.path.join(tmp, "drop"))
    proc = ta.run_assemble(drain, claims_dir, out, "--collision-decisions", ta.decisions_file(tmp, {key: "drop"}))
    assert proc.returncode == 0, proc.stderr
    text = ta.read(ta.dom(out, "alpha", "domain", "tracker.md"))
    assert "A new lesson." in text and "B correction." not in text, text
    assert [d["memory"] for d in json.loads(ta.read(ta.report_path(out)))["collision_decisions"]
            if d["key"] == key] == ["fix-note"]


def test_d2_a_description_follows_a_heading_the_file_holds(tmp: str) -> None:
    """j481 D2 (F1): the description was the first claim's title whether or not that heading stood. A retire claim
    filed first in a part that does not hold its section gave the part the cue 'Retire B'. A heading that stands
    keeps the description it had; a slice no claim touches is not rewritten."""
    big = "x " * 800
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "solution", "topic": "big", "title": "A", "body": big, "evidence": ["h1"]},
        {"class": "solution", "topic": "big", "title": "B", "body": big, "evidence": ["h2"]},
        {"class": "solution", "topic": "calm", "title": "First", "body": "One.", "evidence": ["h1"]},
        {"class": "solution", "topic": "calm", "title": "Second", "body": "Two.", "evidence": ["h1"]}])})
    assert ta.run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    calm = ta.proj(out, "alpha", "solution", "calm.md")
    calm_before = ta.read(calm)
    ta.set_claims(claims_dir, "alpha", [ta.retire("B", topic="big"),
                                        {"class": "solution", "topic": "big", "title": "N", "body": "new", "evidence": ["h1"]}])
    proc = ta.run_assemble(drain, claims_dir, out, "--budget", "500", "--stamp", "2026-01-02")
    assert proc.returncode == 0, proc.stderr
    first = ta.proj(out, "alpha", "solution", "big.md")
    assert "## Retire B" not in ta.read(first) and description_of(first) == "A", description_of(first)
    assert ta.read(calm) == calm_before, "an untouched multi-section slice is byte for byte what it was"
    ta.set_claims(claims_dir, "alpha", [{"class": "solution", "topic": "calm", "title": "Third", "body": "Three.", "evidence": ["h1"]}])
    assert ta.run_assemble(drain, claims_dir, out, "--budget", "500", "--stamp", "2026-01-03").returncode == 0
    assert description_of(calm) == "Third", "a heading that stands is the description, as before"


def test_d3_the_predecessor_of_a_same_run_correction_is_reported_not_written_back(tmp: str) -> None:
    """j481 D3 (F2): memory `grow` still carries the text of 'Heading H'; memory `fix` corrects that section in this
    drain. The pre-pass read the old text as standing, the writer put it in part 1 and the correction in part 2, and
    the corrected text was back in the corpus. It is not written and the report names both memories."""
    old = "h " * 850
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    directory = ta.dom(out, "alpha", "domain")
    os.makedirs(directory)
    for name, sections in (("grow.md", [("Big", "y " * 20)]), ("grow-2.md", [("Heading H", old.strip())])):
        with open(os.path.join(directory, name), "w", encoding="utf-8") as fh:
            fh.write("---\nrole: alpha\nclass: domain\ndescription: x\ntier: 2\nknowledge_scope: full\ntopic: grow\n"
                     "origin:\n  - agent: unresolved\n    host: unknown\nderived_from:\n  - h1\n---\n\n"
                     + "\n\n".join(f"## {h}\n\n{t}" for h, t in sections) + "\n")
    ta.set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "grow", "title": "Heading H", "body": old, "evidence": ["h1"]},
        {"class": "domain", "topic": "fix", "title": "Heading H, corrected", "body": "Corrected. " * 150,
         "evidence": ["h2"], "merge_target": "Heading H"}])
    proc = ta.run_assemble(drain, claims_dir, out, "--budget", "500")
    assert proc.returncode == 0, proc.stderr
    everything = "".join(ta.read(os.path.join(directory, n)) for n in os.listdir(directory))
    assert "## Heading H\n" not in everything and "Heading H (2)" not in everything and "collisions:" not in everything, everything
    assert "## Heading H, corrected" in everything
    (note,) = json.loads(ta.read(ta.report_path(out)))["superseded_harvests"]
    assert "'grow'" in note and "'fix'" in note, note


def write_part(directory: str, name: str, sections: list[tuple[str, str]], topic: str = "grow") -> None:
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, name), "w", encoding="utf-8") as fh:
        fh.write(f"---\nrole: alpha\nclass: domain\ndescription: x\ntier: 2\nknowledge_scope: full\ntopic: {topic}\n"
                 "origin:\n  - agent: unresolved\n    host: unknown\nderived_from:\n  - h1\n---\n\n"
                 + "\n\n".join(f"## {h}\n\n{t}" for h, t in sections) + "\n")


def test_d3_a_correction_replaces_the_kept_both_siblings_so_their_text_is_a_predecessor_too(tmp: str) -> None:
    """The consolidation a merge_target does retires 'X (2)' with 'X': a memory whose text is the sibling's is the
    correction's predecessor as much as the one whose text is 'X'."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    write_part(ta.dom(out, "alpha", "domain"), "grow.md", [("Heading H", "One."), ("Heading H (2)", "Two.")])
    ta.set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "grow", "title": "Heading H", "body": "Two.", "evidence": ["h1"]},
        {"class": "domain", "topic": "fix", "title": "Heading H, corrected", "body": "Corrected.", "evidence": ["h2"],
         "merge_target": "Heading H"}])
    proc = ta.run_assemble(drain, claims_dir, out)
    assert proc.returncode == 0, proc.stderr
    text = ta.read(ta.dom(out, "alpha", "domain", "grow.md"))
    assert "Two." not in text and "Corrected." in text, text
    assert len(json.loads(ta.read(ta.report_path(out)))["superseded_harvests"]) == 1


def test_d4_a_merge_target_two_parts_of_one_topic_hold_is_ambiguous(tmp: str) -> None:
    """j481 D4 (F2): the part a correction is written into is split_by_budget's grouping, not the target's; with the
    heading in two parts it replaced one copy and the other stood. Refused like a heading two topics hold, nothing
    written. Chosen over retiring the other copy with the correction: which copy is the true predecessor is the
    author's to say, and a silent retire of the part the claim did not land in is the loss the run is refused for."""
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [])})
    directory = ta.dom(out, "alpha", "domain")
    os.makedirs(directory)
    for name, text in (("grow.md", "First text."), ("grow-2.md", "Second text.")):
        with open(os.path.join(directory, name), "w", encoding="utf-8") as fh:
            fh.write("---\nrole: alpha\nclass: domain\ndescription: x\ntier: 2\nknowledge_scope: full\ntopic: grow\n"
                     "origin:\n  - agent: unresolved\n    host: unknown\nderived_from:\n  - h1\n---\n\n"
                     f"## Heading H\n\n{text}\n")
    ta.set_claims(claims_dir, "alpha", [
        {"class": "domain", "topic": "fix", "title": "Heading H, corrected", "body": "Corrected.", "evidence": ["h2"],
         "merge_target": "Heading H"}])
    before = tree_of(out)
    proc = ta.run_assemble(drain, claims_dir, out, "--budget", "500")
    assert proc.returncode == 1 and "MERGE TARGET AMBIGUOUS" in proc.stderr and "grow-2.md" in proc.stderr, (proc.returncode, proc.stderr)
    assert tree_of(out) == before, "a refused drain writes nothing"
    # The positive control: with one copy the same correction is applied.
    os.remove(os.path.join(directory, "grow-2.md"))
    assert ta.run_assemble(drain, claims_dir, out, "--budget", "500").returncode == 0
    assert "Corrected." in ta.read(os.path.join(directory, "grow.md"))
    # The claim of the topic itself (its parts are one topic's, whichever part it lands in).
    write_part(directory, "grow.md", [("Heading H", "First text.")])
    write_part(directory, "grow-2.md", [("Heading H", "Second text.")])
    ta.set_claims(claims_dir, "alpha", [{"class": "domain", "topic": "grow", "title": "Heading H, corrected",
                                         "body": "Corrected.", "evidence": ["h2"], "merge_target": "Heading H"}])
    proc = ta.run_assemble(drain, claims_dir, out, "--budget", "500")
    assert proc.returncode == 1 and "MERGE TARGET AMBIGUOUS" in proc.stderr, (proc.returncode, proc.stderr)


FOOTER = "*Observed 2026-10-20 (architect-cto)*"


def test_j485_a_body_that_carries_its_own_observed_footer_gets_one_footer(tmp: str) -> None:
    """j485: claim_block appended the claim's footer without looking at the body's, so a memory copied from a slice
    (or a correction memory) ended in two identical lines. The claim's footer is the only one when it has observed_at,
    and its date wins; two footers in the body make one; without observed_at the body's last footer stays, once;
    only a footer at the very end is touched."""
    from assembler.slices import claim_block
    base = {"topic": "t", "title": "T", "evidence": ["h1"], "_role": "architect-cto"}
    block = lambda body, **extra: claim_block({**base, "body": body, **extra})  # noqa: E731 — the rendering under test
    assert block("Text.", observed_at="2026-10-25") == "## T\n\nText.\n\n*Observed 2026-10-25 (architect-cto)*\n", "the control: no footer in the body"
    assert block(f"Text.\n\n{FOOTER}", observed_at="2026-10-25") == "## T\n\nText.\n\n*Observed 2026-10-25 (architect-cto)*\n"
    assert block(f"Text.\n\n{FOOTER}\n\n*Observed 2026-10-21 (architect-cto)*", observed_at="2026-10-20") \
        == "## T\n\nText.\n\n*Observed 2026-10-20 (architect-cto)*\n"
    assert block(f"Text.\n\n{FOOTER}") == f"## T\n\nText.\n\n{FOOTER}\n", "no observed_at: the body's footer, once"
    assert block(f"Text.\n\n*Observed 2026-10-19 (architect-cto)*\n\n{FOOTER}") == f"## T\n\nText.\n\n{FOOTER}\n", "the last of the body's"
    assert block("Text.") == "## T\n\nText.\n", "no footer anywhere: nothing added"
    prose = f"On 2026-10-20 it was Observed 2026-10-20 (x) in the logs.\n\n{FOOTER}\n\nMore prose, Observed 2026-10-19."
    assert block(prose, observed_at="2026-10-25") == f"## T\n\n{prose}\n\n*Observed 2026-10-25 (architect-cto)*\n", "prose stays"


def test_j485_a_slice_re_rendered_from_a_body_with_its_footer_carries_one(tmp: str) -> None:
    """The section a drain wrote twice-footed is re-rendered from its claim with one footer (a fixture of the
    correction memories' shape), and the same drain again is a no-op."""
    body = f"The correction authorizes the send.\n\n{FOOTER}"
    drain, claims_dir, out = ta.build(tmp, {"alpha": ta.claims("alpha", [
        {"class": "workflow", "topic": "correction-x", "title": "Correction X", "body": body, "evidence": ["h1"],
         "observed_at": "2026-10-20"}])})
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0
    text = ta.read(ta.proj(out, "alpha", "workflow.md"))
    assert text.count("*Observed 2026-10-20") == 1, text
    first = tree_of(out)
    assert ta.run_assemble(drain, claims_dir, out).returncode == 0 and tree_of(out) == first


def main() -> int:
    cases = [
        test_an_owner_named_only_in_shared_with_gets_its_index,
        test_a_project_collision_is_reported_relative_to_the_working_copy,
        test_a_retire_beside_a_flat_file_clips_the_siblings_new_cue,
        test_a_carried_copy_dropped_clips_the_carried_files_new_cue,
        test_the_command_runs_in_isolated_mode,
        test_d1_two_claims_writing_one_heading_stop_the_drain_and_the_owner_decides,
        test_d1_keep_both_and_drop_leave_no_claim_unreported,
        test_d2_a_description_follows_a_heading_the_file_holds,
        test_d3_the_predecessor_of_a_same_run_correction_is_reported_not_written_back,
        test_d3_a_correction_replaces_the_kept_both_siblings_so_their_text_is_a_predecessor_too,
        test_d4_a_merge_target_two_parts_of_one_topic_hold_is_ambiguous,
        test_j485_a_body_that_carries_its_own_observed_footer_gets_one_footer,
        test_j485_a_slice_re_rendered_from_a_body_with_its_footer_carries_one,
    ]
    # Cases run because they are listed, so one written and not listed
    # would pass forever unrun (test_assemble.py's registry rule).
    declared = {name for name, obj in globals().items() if name.startswith("test_") and callable(obj)}
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
