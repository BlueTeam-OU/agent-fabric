"""tools/fabric/agent_text.py — which tracked paths are text an agent reads (j305).

One predicate for the corpus lint (lint_rules/hidden.py) and the pre-commit refusal (guards/commit_hooks.py), so the two
cannot disagree on what hidden_unicode.py is held against. Imported by path or from tools/fabric/ by both; it imports nothing.

In agent-fabric itself: every Markdown file, and every Markdown or JSON file under identities/ and .agent-fabric/. In a
managed project's working copy: only .agent-fabric/. The project's own docs and its root CLAUDE.md or AGENTS.md are project
truth under its own review and are not judged here. No exemption for ruff.toml's exclude list or a vendored skill: a vendored
skill is text from outside, which is exactly what this guards.
"""
from __future__ import annotations

AGENT_FABRIC_DIR = ".agent-fabric/"
TEXT_SUFFIXES = (".md", ".json")


def is_agent_text(rel: str, *, itself: bool) -> bool:
    """`rel` is repo-relative with forward slashes; `itself` says the repository is agent-fabric, not a managed project."""
    if not rel.endswith(TEXT_SUFFIXES):
        return False
    if rel.startswith(AGENT_FABRIC_DIR):
        return True
    return itself and (rel.endswith(".md") or rel.startswith("identities/"))
