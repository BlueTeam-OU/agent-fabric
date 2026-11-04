#!/usr/bin/env python3
"""tools/fabric/review_card.py — a project's review card: where it is and how large it may be (agent-fabric ADR-020).

One definition for the three that judge it: review_brief.py, which renders it into every brief and refuses one over the
cap; the pre-commit hook (tools/fabric/guards/commit_hooks.py), which refuses a commit that stages it over the cap (one
already committed over it does not stop a commit that leaves it untouched); and lint (tools/fabric/lint_rules/card.py),
which every project CI that lints its .agent-fabric/ runs. Without the last two
the renderer was the only judge, and it judged only at review time: a managed project's card reached 2396 bytes over
two commits nothing refused (j475), and every review of that project then failed until it was cut.

Standard library only, and no sibling import: the hook copies this file into scratch fabrics by name."""
from __future__ import annotations

# The reviewer runs without the project's instruction files (omitClaudeMd), so this card is all of the project it
# gets, and it is re-sent every turn: a cap, refused over, never truncated (a cut rule reads as a whole one).
CARD_PATH = ".agent-fabric/review-card.md"
CARD_CAP = 2048


def over_cap(size: int) -> bool:
    return size > CARD_CAP


def refusal(where: str, size: int) -> str:
    """The one wording, so a reader who met it in a hook, a lint run or a brief knows it is the same rule."""
    return f"{where}: the project review card is {size} bytes, over the {CARD_CAP}-byte cap; shorten it"
