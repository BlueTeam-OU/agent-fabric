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
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_assemble as ta  # noqa: E402

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


def main() -> int:
    cases = [
        test_an_owner_named_only_in_shared_with_gets_its_index,
        test_a_project_collision_is_reported_relative_to_the_working_copy,
        test_a_retire_beside_a_flat_file_clips_the_siblings_new_cue,
        test_a_carried_copy_dropped_clips_the_carried_files_new_cue,
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
