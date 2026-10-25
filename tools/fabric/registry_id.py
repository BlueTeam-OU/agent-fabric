"""tools/fabric/registry_id.py — the grammar of a project's id in projects/registry.json, defined once.

The control plane's jobs-add (control/jobs.py), the job list's pool and
project checks (jobsparts/base.py) and the GZCoord intake (gzcoord/intake.py)
each refuse a project that is no registry id; they share this one pattern so
they cannot disagree about which REQUESTs are queued. A registry id is
segments joined by single dots, each segment lowercase letters and digits
with hyphens inside it, the whole at most 63 characters, no leading or
trailing dot or hyphen. The registry holds ids with a dot (a brand or a
locale of a product, written product.part), so a dot is part of the grammar;
tests/test_registry_id.py checks every id in projects/registry.json against it.

Standard library only: the jobs parts load this file by path, never by name.
"""
from __future__ import annotations

import re

REGISTRY_ID_MAX = 63

# Match whole (fullmatch): the lookahead is the length bound, the lookbehind the
# trailing hyphen a segment's own `[a-z0-9-]*` would otherwise allow.
REGISTRY_ID = re.compile(r"(?!.{%d})[a-z0-9][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)*(?<!-)" % (REGISTRY_ID_MAX + 1), re.ASCII)
