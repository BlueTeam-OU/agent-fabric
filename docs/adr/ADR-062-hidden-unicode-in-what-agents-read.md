# ADR-062 — Hidden Unicode is refused in what agents read

**Date:** 2026-10-20
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** `tools/fabric/hidden_unicode.py`, the corpus lint, the pre-commit hook, every file of the control plane an agent reads (skills, charters, briefs, remits, instruction files, memory slices), and every other boundary that admits text into an agent's context
**Pillar:** P3

## 1. Context and Problem

An agent's prompt is assembled from files: a charter and brief, a project's
remit, CLAUDE.md and AGENTS.md, the skills, the memory slices a lookup
returns. A model reads every code point of them, while a person reviewing
the same diff sees only the ones that render. Three classes of character
open that gap: bidi overrides and isolates, which change the order a
reviewer reads text in; zero-width and other format (Cf) characters,
Unicode tag characters among them, which can carry a whole instruction in
invisible ASCII; and control characters, which can rewrite what a terminal
shows. A skill or a slice carrying any of them can say one thing to the
reviewer and another to every agent that loads it.

Until 2026-10-20 three boundaries each refused some of this their own way
(holder addenda, GZCoord bodies, the i18n dictionaries), and the corpus
itself, the larger surface, was checked by nothing. PR #338 made one scanner
of the three. On the day this record was written every tracked Markdown file
of the fabric scanned clean, and a managed project's own design record
carried three zero-width spaces, unnoticed.

## 2. Decision

`tools/fabric/hidden_unicode.py` is the one definition of hidden Unicode,
and it is enforced on every file of the control plane an agent reads: the
pre-commit hook refuses a staged file that carries one, and the corpus lint
(run by the suite and by CI) refuses a committed one. The approach follows
microsoft/apm's install-time scan of agent packages (MIT), adapted.

## 3. Alternatives Considered

- **A check per file kind** (skills, slices, charters each with their
  own): the state before #338, and why addenda admitted U+206A while the
  i18n check refused a different set. One definition, one set of
  allowances.
- **Normalising instead of refusing** (strip the characters on read):
  silent, and it moves the defect from the commit, where its author can be
  asked, to every reader. Refusal names the line and column.
- **Only the lint, no hook**: the lint judges a commit after it exists, on
  a branch other sessions may already have pulled; the hook keeps the
  character out of history. Both, as for every guard (ADR-018).
- **Judging a project's own documents too**: they are the project's truth,
  and a character in a project's record would fail the fabric's lint on
  every machine that holds the project beside it. The fabric judges
  `.agent-fabric/`, which it writes; the project may run the same scanner
  in its own CI.

## 4. Rationale

The allowances are the scanner's and each answers a real file (a leading
BOM, ZWJ inside an emoji, VS16 after an emoji or in a keycap). Everything
else of the refused classes has no legitimate use in the corpus, which is
written in English, Russian and Georgian, none of which needs ZWNJ. The cost
is nil today, since the corpus is clean, and the scan is linear in the text.

## 5. Binding Rules

1. `tools/fabric/hidden_unicode.py` is the only definition of hidden
   Unicode in the fabric. A boundary that admits text into an agent's
   context calls `scan` (or `is_format`) and keeps no table of its own; an
   allowance is added there, with the scripts or sequence it serves and a
   test, never as a caller's exemption.
2. In agent-fabric, every tracked Markdown file and every Markdown or
   JSON file under `identities/` and `.agent-fabric/` is judged; in a
   managed project, its `.agent-fabric/`. Vendored or third-party text in
   those places is not exempt: a skill taken from elsewhere is the case
   this guards.
3. The pre-commit hook judges the staged content of those files for every
   committer, carve-outs included, and refuses the commit with each
   finding's path, line, column, code point and class. The corpus lint
   judges the committed tree in the suite and in CI. Each has a test that
   fails when its check is removed.
4. A project's own documents and instruction files are the project's and
   are not judged by the fabric; a character found there is reported to
   the project's owning role as an observation.
5. The rule is about what text may hide, never what it may say: a visible
   character of any script passes.

## 6. Consequences

A hidden character is caught before it reaches history, with its position,
whichever role commits it. A file that genuinely needs a new sequence (a
new locale's script) costs an allowance in the scanner and a test, which
is deliberate. A judged file that is not UTF-8 is refused too, as
unreadable.

## 7. Future Evolution

Reopened if a locale needs ZWNJ or another joiner, or if text reaches an
agent through a boundary that does not call the scanner (a tool's output,
a web page read through moli): such text is data, never instructions, but
a renderer that shows the reader its hidden characters may follow.

## 8. Decision Status

Proposed; waits on the owner's acceptance. The scanner landed in #338; the
lint, the hook and the i18n move land with this record.

## References

- `tools/fabric/hidden_unicode.py`, `tests/test_hidden_unicode.py` (#338).
- `tools/fabric/agent_text.py`, `tools/fabric/lint_rules/hidden.py`, `tools/fabric/guards/commit_hooks.py`.
- ADR-018 (authority and its guards), ADR-060 (holder addenda).
- microsoft/apm, install-time hidden-Unicode scan (MIT), the approach adapted.
