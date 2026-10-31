"""tools/fabric/assembler/shapes.py — corrections of a shape no author meant are refused, before the write and after it.
A part of tools/fabric/assemble.py, whose docstring is the contract.

The 2026-10-31 drain wrote three corrections that nothing refused (#437 round 5, F10-F12). A correction replaces a section
and puts its own text and title in the section's place, so a body or a title that is a truncation of what it stands for
loses the section's knowledge with no collision to ask about:

  one-word body       five corrections with the body "project" replaced five sections; the report held one applied_key.
  equal bodies        the same body written over sections that were different.
  title is a prefix   seven titles cut at 100 characters became the headings, and the full headings were gone.
  replaced heading stands after the write
                      a section a correction had replaced was in its slice again.

The first three are judged before anything is written and stop the drain like a collision does; none of them is a question
the owner can answer with a decision, because the fix is the memory's text. The last is read from the files written, since
only the writer knows what it left; it names the files already written, and the drain is discarded, as for a hygiene
failure."""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any
from assembler.core import layout, Run, in_report
from assembler.slices import read_existing_slice, claim_heading, claim_block, undated, is_retire
from assembler.targets import existing_sections, slice_candidates


def _groups(run: Run) -> list[tuple[str | None, str, str, str, list[dict[str, Any]]]]:
    """(role or None for shared, label, class, topic, claims) for every group of the drain, in the order the collision pre-pass reads them."""
    found = [(role, role, klass, topic, group) for role, topics in run.per_role.items() for (klass, topic), group in topics.items()]
    found += [(None, "shared", klass, topic, group) for (klass, topic), group in run.shared.items()]
    return found


def claim_key(label: str, klass: str, topic: str, claim: dict[str, Any]) -> str:
    """The claim's key as the collision pre-pass prints it, so one claim has one name in every refusal."""
    return f"{label}/{klass}:{topic}#{claim_heading(claim)}@{(claim.get('evidence') or ['?'])[0][:12]}"


def _words(claim: dict[str, Any]) -> list[str]:
    return undated(claim_block(claim).split("\n", 1)[1]).split()


def check_correction_shapes(run: Run) -> int | None:
    """Refuse a correction whose body is one word, whose body another correction of the run, writing a different section, also
    has, or whose title is a strict prefix of the heading it replaces. Nothing is written."""
    refused: list[str] = []
    corrections: list[tuple[str, str, tuple[str | None, str, str], list[str]]] = []   # key, target, (scope, class, target), words
    for role, label, klass, topic, group in _groups(run):
        present: dict[str, str] | None = None
        for claim in group:
            target = (claim.get("merge_target") or "").strip()
            if not target or is_retire(claim):
                continue
            key = claim_key(label, klass, topic, claim)
            words = _words(claim)
            if len(words) == 1:
                refused.append(f"{key}   (rule: correction body is one word)\n"
                               f"    it replaces {target!r} with the body {words[0]!r}; a correction is the section's new text, "
                               "not a label — write the whole text, or retire the section with an empty body")
            if present is None:
                present = existing_sections(slice_candidates(run, role, klass, topic))
            heading = claim_heading(claim)
            if target in present and heading != target and target.startswith(heading):
                refused.append(f"{key}   (rule: correction title is a prefix of the heading it replaces)\n"
                               f"    title {heading!r} is the first {len(heading)} of the {len(target)} characters of {target!r}; "
                               "a title cut short would become the section's heading and lose the rest")
            corrections.append((key, target, (role, klass, target), words))
    by_body: dict[tuple[str, ...], list[tuple[str, tuple[str | None, str, str]]]] = defaultdict(list)
    for key, _target, where, words in corrections:
        by_body[tuple(words)].append((key, where))
    for words, claimants in by_body.items():
        # The same body over one section twice is a correction repeated, not two sections overwritten with one text.
        if len(words) > 1 and len({where for _key, where in claimants}) > 1:
            for key, where in claimants:
                refused.append(f"{key}   (rule: correction body equals another correction's in this run)\n"
                               f"    it replaces {where[2]!r}; {len(claimants)} corrections of sections that differ carry the body "
                               f"{' '.join(words)[:80]!r}")
    # A one-word body is also "equal to another" when several share it; the single-word rule above names those already.
    if not refused:
        return None
    print("CORRECTION REFUSED — a correction has a shape that loses the section it replaces. "
          "This run wrote NOTHING and exits 1.", file=sys.stderr)
    for note in refused:
        print(f"  {note}", file=sys.stderr)
    print("\nThe memory's author fixes the memory (its body or its title); there is no decision to give.", file=sys.stderr)
    return 1


def _sections_around(path: str) -> dict[str, str]:
    """The sections of the slice file and of its budget parts `<stem>-<n>.md`, which a replacement may have left a copy in."""
    directory, name = os.path.split(path)
    stem = re.sub(r"-\d+$", "", name[:-3])
    files = sorted({path, *glob.glob(os.path.join(glob.escape(directory), glob.escape(stem) + "*.md"))})
    found: dict[str, str] = {}
    for file in files:
        if file == path or re.fullmatch(re.escape(stem) + r"-\d+\.md", os.path.basename(file)):
            found.update(read_existing_slice(file)[1])
    return found


def verify_replacements(run: Run) -> int | None:
    """After the write: a section a correction replaced is not in its slice. The writer replaces by heading, so what stands
    is a section some other claim of the drain wrote again (or an earlier run of the same drain's correction, undone by this
    run's claim), and the knowledge the correction removed is back beside its replacement."""
    standing: list[str] = []
    for key, path, target in run.replacements:
        if os.path.isfile(path) and target in _sections_around(path):
            standing.append(f"{key}   (rule: replaced heading stands after the write)\n"
                            f"    {target!r} is still a section of {in_report(run, path)}")
    # Corrections an earlier run of this drain applied, which this run may have undone: the report keeps them while they hold.
    # Only the report of this drain's own stamp: a heading reused by a later drain's claim is that drain's section, not
    # an undone correction (whether an old text is harvested back across drains is the harvest's, corrections.py).
    try:
        with open(layout.project_report_path(run.project), encoding="utf-8") as fh:
            previous = json.load(fh)
        earlier = (previous.get("applied_corrections") or []) if previous.get("stamp") == run.args.stamp else []
    except (OSError, ValueError, AttributeError):
        earlier = []
    seen = {(path, target) for _key, path, target in run.replacements}
    for entry in earlier:
        if not isinstance(entry, dict) or not isinstance(entry.get("slice"), str) or not isinstance(entry.get("replaced"), str):
            continue
        if entry["replaced"] == entry.get("heading"):
            continue
        for base in [layout.working_copy_for(run.project), layout.FABRIC_ROOT]:
            path = os.path.join(base, entry["slice"]) if base else ""
            if path and os.path.isfile(path):
                if (path, entry["replaced"]) not in seen and entry["replaced"] in _sections_around(path):
                    standing.append(f"{entry['slice']}#{entry['replaced']}@{entry.get('memory', '?')}   "
                                    "(rule: replaced heading stands after the write)\n"
                                    f"    an earlier run of this drain replaced it ({entry.get('memory')!r}); it is a section again")
                break
    if not standing:
        return None
    print("REPLACED SECTION STANDS — a correction replaced a section and the section is in its slice again. "
          "The files of this run are WRITTEN: discard the working tree, fix the claim that wrote it back, and re-run. "
          "Exits 1.", file=sys.stderr)
    for note in standing:
        print(f"  {note}", file=sys.stderr)
    return 1
