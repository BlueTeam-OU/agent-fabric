"""tools/fabric/lint_rules/card.py — a project's review card within its cap (j475, agent-fabric ADR-020).
tools/fabric/review_card.py is the definition; the pre-commit hook judges the commit that changes the card, and this judges
the tree, so a project CI that lints its .agent-fabric/ (a managed project's ban checks do) refuses what a --no-verify commit or
a web edit let through. A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import importlib.util
import os

from .base import layout

_FABRIC = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# By path, as lint loads every module it trusts: a directory on sys.path would let a fixture fabric answer for it.
_spec = importlib.util.spec_from_file_location("fabric_review_card", os.path.join(_FABRIC, "review_card.py"))
review_card = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review_card)


def _card_finding(root: str, label: str) -> list[str]:
    path = os.path.join(root, review_card.CARD_PATH)
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return []   # a project need not keep a card
    except OSError as exc:
        return [f"{label}{review_card.CARD_PATH}: cannot be read ({exc.__class__.__name__}); its size is not judged"]
    return [review_card.refusal(f"{label}{review_card.CARD_PATH}", size)] if review_card.over_cap(size) else []


def review_card_findings(root: str) -> list[str]:
    """The fabric's own card, then each linted working copy's, labelled `<pid>:`."""
    out = _card_finding(root, "")
    for pid, path in sorted(layout.explicit_working_copies().items()):
        if pid != layout.FABRIC_PROJECT_ID and os.path.realpath(path) != os.path.realpath(root):
            out += _card_finding(path, f"{pid}:")
    return out
