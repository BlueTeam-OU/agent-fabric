#!/usr/bin/env python3
"""tools/fabric/assemble.py

>>> help
Turn distiller claims into the knowledge corpus, filed by scope.

    tools/fabric/assemble.py --claims DIR --drain DIR --project <project> --stamp DATE
    tools/fabric/assemble.py --bundle FILE|- --project <project> --stamp DATE
    tools/fabric/assemble.py … --flags [--send]      # then the flag phase (memory_flagrun.py): dry run, or --send
    tools/fabric/assemble.py … --commit-message FILE  # the commit body for the drain, built from its report (commit with -F)

A BUNDLE is the drain as one tar with a manifest (harvest_memory.py
--bundle; bin/fabric-host <host> drain <login> streams one from the
account's own host). It is verified before anything is read from it:
every file the manifest names present with the digest it records, the
agent and host the same in manifest and report, nothing in the tar the
manifest does not name. A bundle that was cut short or changed on the
way is refused with the file named.

THE TREE A RUN WRITES is --fabric when given, else the checkout this file is in. Without --fabric, an exported
AGENT_FABRIC_ROOT or AGENT_FABRIC_OPERATOR naming another tree is refused before anything is written (exit 1): it
would take the domain and shared slices there while the project slices follow --working-copy.

Where a slice lands is decided by tools/fabric/layout.py from its class:
domain knowledge under memory/domains/<role>/, everything learned about
the project under <working copy>/.agent-fabric/memory/<role>/ (the
project's own repository; fabric-coordinator's to write), multi-owner
slices under the matching shared/. The generated INDEX.md for each
(project, role) lists all of it with paths relative to the working copy
(fabric-side slices through ../agent-fabric/), plus the role's authored
charter and recall from identities/roles/<role>/.

Distillers judge; this assembles. A distiller emits claims and nothing
else — no files, no frontmatter, no index — because everything mechanical
belongs here where it is deterministic: same claims in, byte-identical
tree out. That property is what makes a drain reviewable as a content
diff rather than a diff of formatting noise.

What it does:

  * Places each claim in its class/topic slice, splitting a slice when it
    outgrows its token budget so no single file can quietly become
    enormous.
  * Writes provenance frontmatter: which observations a slice came from,
    and which clone and host produced them, so a claim stays auditable
    after the observation store has been archived and emptied.
  * Regenerates every role INDEX.md from slice frontmatter. The index is
    the only thing a session reads before deciding to load a slice, so it
    is generated rather than maintained — a hand-written index drifts.
  * Routes a claim owned by two or more roles to `memory/shared/` (or the
    project's own `shared/`), so
    knowledge two roles need lives once instead of in two copies that
    will disagree later.
  * Merges the citation graph into each role's crossref.json.
  * Runs the hygiene checks that must never reach a commit. A registered project whose working copy (so whose
    .agent-fabric/hygiene.json) the run cannot find refuses the run, naming it and where it looked;
    --allow-missing-hygiene lets it through and the report names each project assembled without its list.

A project-scoped claim (solution, intersection, rationale, workflow, threads) whose role the project's taxonomy does not bind is
not admitted to that project's corpus (the owner, 2026-11-11; drain of 2026-11-08). fabric-coordinator's goes to agent-fabric's
own .agent-fabric/memory/fabric-coordinator/ instead, that role's remit covering the control plane wherever it learned the
lesson, and the report's `rehomed` names each (its stderr section and the commit body count them). That pass records
its decisions in agent-fabric's own last-drain-report.json, in the keys section_writers, applied_corrections,
replaced_sections, collision_decisions and retitles only; any other key of that report stays as it is, and a report that
cannot be read is not replaced: the run refuses (exit 1) before the pass writes anything. Any other role refuses the
run before anything is written (exit 1), naming the claim, its role and the project: no fallback. A claim some bound role
co-owns (shared_with) stays; a project with no taxonomy, the fabric's own project and domain claims are not judged.

Merge mode is the default: existing slices are read, and a claim whose
`merge_target` names an existing section updates it instead of appending
beside it. Regenerating from scratch would discard accumulated curation,
so it is never done implicitly.

A merge_target is judged against the claims of the same run as well as the
corpus: two claims that both write one heading (one under it, one naming it
in merge_target) are a contested heading the owner decides; a memory whose
text is the section another memory corrects in the same run is not written
and is listed under `superseded_harvests`; a merge_target that two parts of
one topic hold is ambiguous, like one two topics hold.

A correction of a shape that loses what it replaces is refused before anything is written (assembler/shapes.py): a body
of one word, a body another correction of the run writes over a different section, a title that is a strict prefix of
the heading it replaces. After the write, a section a correction replaced that stands in its slice again fails the run
(its files are written: discard them). A flat class file that records no topic is not taken for the topic a drain brings:
it moves into the directory as the carried file.
<<< help
"""

from __future__ import annotations

import copy
import os
import sys

# A script's own directory is on sys.path only by default: `python -I`, `-P`
# and PYTHONSAFEPATH leave it out, and so does a load by spec. The parts beside
# this file are put there explicitly, as layout.py was found by its path when
# this was one file (tests/test_assemble_seams.py runs it under -I).
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from assembler.core import Run, layout, in_report  # noqa: E402
from assembler.intake import parse_args, open_layout, read_claims, screen_hygiene, bucket_claims, hold_back, rehome_unbound, note_unbound_owners, rehomed_row, load_hygiene, load_decisions  # noqa: E402
from assembler.targets import plan_classes, held_files, resolve_all_targets, point_disk  # noqa: E402
from assembler.anchorkeep import keep_resolving_anchors  # noqa: E402
from assembler.collisions import check_collisions  # noqa: E402
from assembler.shapes import check_correction_shapes, drop_replayed, verify_replacements  # noqa: E402
from assembler.writer import write_shared, write_role  # noqa: E402
from assembler.index import bound_roles_with_domain_slices, index_role, read_crossref_index, roles_with_project_directory  # noqa: E402
from assembler.report import report, record_rehomed, read_rehome_report  # noqa: E402


def main() -> int:
    args = parse_args()
    run = Run(args=args, project=open_layout(args))
    if read_claims(run):
        return 1
    # Before anything is written: the passes read this report for the corrections they already applied (shapes._earlier,
    # targets), and take an unreadable one for none; only the refusal here keeps all of them, and the report's write, honest.
    _, why = read_rehome_report(run.project)
    if why:
        print(f"{run.project}'s own drain report is not replaced: {why}. Nothing is written.", file=sys.stderr)
        return 1
    rehomed = rehome_unbound(run)
    if rehomed:
        # Before the project's own pass, which reports them: a claim the control plane's pass refuses stops the run with
        # nothing of the project's written. The two passes are not one transaction (the second can still fail after the
        # first wrote); the rerun is a replay, as any rerun of a drain is.
        rc = rehome(run, rehomed)
        if rc:
            return rc
    rc = assemble_project(run)
    if rc is not None:
        return rc
    rc = report(run)
    if rc == 0 and args.flags:
        # After the report, which it reads for who wrote each section; a failed drain routes nothing.
        import memory_flagrun
        return memory_flagrun.phase(run.project, send=args.send, record_in_report=True, where=layout)
    return rc


def rehome(run: Run, claims: list) -> int:
    """The claims rehome_unbound took out of `run`, assembled into the control plane's own project corpus as that project's drain
    would: its taxonomy, hygiene view and working copy. Its report is agent-fabric's own last-drain-report.json (record_rehomed),
    and what the project's report says of it is the re-homed rows, the files, and the notes the pass made; a rejection, redaction
    or problem it found is carried into the project's report so the run exits as it would."""
    _, why = read_rehome_report()
    if why:
        print(f"agent-fabric's own drain report is not replaced: {why}. Nothing is written.", file=sys.stderr)
        return 1
    other = Run(args=copy.copy(run.args), project=layout.FABRIC_PROJECT_ID)
    other.args.working_copy = None
    # Only --hold names the project's own slices (read here it would be refused as naming no slice). --collision-decisions is
    # keyed by claim and a key naming no claim of a pass is not refused, so the one file serves both passes: a collision the
    # control plane's pass stops on is decided by the owner and the re-run carries it, as in any drain.
    other.args.hold = None
    other.references, other.origins, other.evidence_epoch, other.telemetry = run.references, run.origins, run.evidence_epoch, run.telemetry
    for claim in claims:
        other.all_claims.setdefault(claim["_role"], []).append(claim)
    load_hygiene(other.args, other.project)
    try:
        rc = assemble_project(other)
    finally:
        load_hygiene(run.args, run.project)
    # From the claims the pass screened (a rejected one is gone from them), not those read: see rehomed_row.
    run.rehomed = [rehomed_row(run, c) for role in sorted(other.all_claims) for c in other.all_claims[role]]
    run.rehomed_files = [in_report(other, p) for p in other.written]
    for name in ("rejected_hygiene", "redactions", "problems", "oversized", "oversized_details", "clipped_descriptions", "migrated",
                 "unresolved_targets", "superseded_harvests", "reharvested_replaced", "titles_one_lined", "anchors_kept",
                 "anchors_lost", "retired_in", "empty_crossrefs", "applied_decisions", "retitles"):
        getattr(run, name).extend(getattr(other, name))
    if not rc:
        # A pass that stopped wrote no report, as the project's does not: its rerun is the replay.
        rc = record_rehomed(other)
    return rc or 0


def assemble_project(run: Run) -> int | None:
    """Everything a run does between reading its claims and reporting; 1 when it stops, None to go on to the report."""
    screen_hygiene(run)
    bucket_claims(run)
    hold_back(run)
    note_unbound_owners(run)
    load_decisions(run)
    plan_classes(run)
    held_files(run)
    run.bound_roles = bound_roles_with_domain_slices(run)
    if resolve_all_targets(run):
        return 1
    keep_resolving_anchors(run)
    drop_replayed(run)
    if check_correction_shapes(run):
        return 1
    if check_collisions(run):
        return 1
    # Refused before anything is written, as a broken taxonomy is.
    held_roles = roles_with_project_directory(run)
    for role in held_roles:
        read_crossref_index(os.path.join(layout.project_dir(run.project, role), "crossref.json"))
    point_disk(run)
    write_shared(run)
    # Every role that owns anything gets a project directory and an index —
    # including one whose claims all live in shared slices, which would
    # otherwise end up with knowledge and no way to find it — and so does
    # every role the project binds whose domain holds slices.
    # An unbound author of a shared slice a bound role co-owns (note_unbound_owners) with nothing else here owns nothing to write:
    # indexing it would give the project a corpus of a role it does not bind (a role with a domain claim, a shared slice
    # or a bound role still has its index).
    emptied = {r for r in run.unbound_held_roles if not run.per_role.get(r) and r not in run.shared_index} - run.bound_roles
    run.owning_roles = sorted((set(run.per_role) | set(run.shared_index) | set(run.all_claims)
                               | run.bound_roles) - emptied)
    for role in run.owning_roles:
        write_role(run, role)
        index_role(run, role)
    # A role that already has a directory here is re-indexed too, though
    # this run brought it nothing: another project's run may have written
    # its domain slices since. Not in owning_roles, which the report
    # records as the roles the drain touched.
    for role in sorted(held_roles - set(run.owning_roles)):
        index_role(run, role)
    if verify_replacements(run):
        return 1
    return None


if __name__ == "__main__":
    sys.exit(main())
