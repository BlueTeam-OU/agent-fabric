#!/usr/bin/env python3
"""tools/fabric/assemble.py

>>> help
Turn distiller claims into the knowledge corpus, filed by scope.

    tools/fabric/assemble.py --claims DIR --drain DIR --project <project> --stamp DATE
    tools/fabric/assemble.py --bundle FILE|- --project <project> --stamp DATE

A BUNDLE is the drain as one tar with a manifest (harvest_memory.py
--bundle; bin/fabric-host <host> drain <login> streams one from the
account's own host). It is verified before anything is read from it:
every file the manifest names present with the digest it records, the
agent and host the same in manifest and report, nothing in the tar the
manifest does not name. A bundle that was cut short or changed on the
way is refused with the file named.

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
  * Runs the hygiene checks that must never reach a commit.

Merge mode is the default: existing slices are read, and a claim whose
`merge_target` names an existing section updates it instead of appending
beside it. Regenerating from scratch would discard accumulated curation,
so it is never done implicitly.
<<< help
"""

from __future__ import annotations

import os
import sys

# A script's own directory is on sys.path only by default: `python -I`, `-P`
# and PYTHONSAFEPATH leave it out, and so does a load by spec. The parts beside
# this file are put there explicitly, as layout.py was found by its path when
# this was one file (tests/test_assemble_seams.py runs it under -I).
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from assembler.core import Run  # noqa: E402
from assembler.intake import parse_args, open_layout, read_claims, screen_hygiene, bucket_claims, hold_back, load_decisions  # noqa: E402
from assembler.targets import plan_classes, held_files, resolve_all_targets  # noqa: E402
from assembler.collisions import check_collisions  # noqa: E402
from assembler.writer import write_shared, write_role  # noqa: E402
from assembler.index import index_role  # noqa: E402
from assembler.report import report  # noqa: E402


def main() -> int:
    args = parse_args()
    run = Run(args=args, project=open_layout(args))
    if read_claims(run):
        return 1
    screen_hygiene(run)
    bucket_claims(run)
    hold_back(run)
    load_decisions(run)
    plan_classes(run)
    held_files(run)
    if resolve_all_targets(run):
        return 1
    if check_collisions(run):
        return 1
    write_shared(run)
    # Every role that owns anything gets a project directory and an index —
    # including one whose claims all live in shared slices, which would
    # otherwise end up with knowledge and no way to find it.
    run.owning_roles = sorted(set(run.per_role) | set(run.shared_index) | set(run.all_claims))
    for role in run.owning_roles:
        write_role(run, role)
        index_role(run, role)
    return report(run)


if __name__ == "__main__":
    sys.exit(main())
