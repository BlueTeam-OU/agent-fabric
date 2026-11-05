---
role: "devex-tooling"
class: workflow
topic: "one-format-one-parser"
description: "two readers of one format (a trailer, a fence, a marker, a header key) drift apart and disagree on the same input; keep one parser that every reader imports, and drive the reader's test from the real producer"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1fd25e3ee05decbc
  - 291d9ea62b1b2c50
---

## two readers of one format (a trailer, a fence, a marker, a header key) drift apart and disagree on the same input; keep one parser that every reader imports, and drive the reader's test from the real producer

Four cases in a week where readers of one format disagreed, each found by a review:

- `Kind:` trailers (#120, 2026-10-08): commit_class.kind_of matched `^Kind:` anywhere in the body,
  while pr_gate read git's trailer block. The same commit counted as work in one and as a fix in
  the other. kind_of now reads only the final all-trailer paragraph.
- The dispatch fence (#259): post_review's DISPATCH_FENCE allowed no space before the info string.
  ledger.FENCE allowed `[ \t]*`. review_rounds kept the unspaced one and claimed "as post-review
  reads it". So a spaced working-tree header posted as header-less.
- The codex unavailable marker: python-dev-03's review_codex.parse_marker and my
  verdicts.unavailable_of parsed the same grammar. We settled on one reader, the arm's, which
  review_codex imports. The writer (format_marker) stays separate.
- The ledger hook read the header key `evidence`, but the producer wrote `evidence_mode`, and it
  rejected `canonical_remote`'s host/owner/name. Every real row would have carried nulls. That
  case is [[contract-test-renders-real-producer]].

**How to apply:** before writing a reader for a format another module already reads or writes,
grep for its other readers and import the existing parser. If you are the first reader, export
yours where the next one will look. When two copies must exist (a writer and a reader), test the
reader with the writer's real output, and test the writer by reading back through the reader. A
review finding on one reader means checking every other reader of that format in the same fix.

When the one reader lives in another language and has no entry the other side can call, pin
the two copies to each other (gzapp #1182, 2026-10-26). architect-cto's ask: "never read from a
second copy of the rule that can drift". release.sh's bash check of
GZAPP_MIGRATE_COMMAND_TIMEOUT_SECONDS mirrors MigrateCommandTimeout.Resolve in C#.
test_release.sh reads every InlineData of the C# Theories and runs it through release.sh. It
fails if it reads fewer than a minimum of each kind, so a rename turns it red rather than
passing on zero cases. Tell the other side's owner that their test names are now an input.

*References: contract-test-renders-real-producer*

*Anchors: `tools/fabric/github/commit_class.py::def kind_of`, `tools/fabric/github/review_status/verdicts.py::def unavailable_of`*

*Observed 2026-10-22 (devex-tooling)*
