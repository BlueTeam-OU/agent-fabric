---
role: "python-dev"
class: domain
topic: "j228-pidfile-race-merged-566"
description: "j228 pidfile race in test_review_mcp merged in #566; shell creates the file empty before echo fills it; forced-race test needs a partial-write stage"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4e752209dd068be8
---

## j228 pidfile race in test_review_mcp merged in #566; shell creates the file empty before echo fills it; forced-race test needs a partial-write stage

A shell's `echo $! > f` truncates (file exists, empty) before it writes, so a reader gets "" (ValueError) or no file. #566 (2026-11-12): `read_pid` waits for a newline-terminated line, bounded, fails by name.

**Why:** the first forced test (empty then "4242\n") let the mutant "accept any non-empty text" survive; a `printf 42` stage between killed it. Create the empty file from Python rather than polling for it (review F1: an unbounded poll hangs the suite), and unlink after the case (F2: a stale fixed pid passes the next case vacuously).

**How to apply:** any test reading a pidfile or a file a child fills later; plant mutants "if text:" and "wait=0". Armed at 1 work commit on the owner's word ("arm 566 when review end"). A `kill -0` wait loop on a pid of this session's own tree is refused by the hook: poll `[ -d /proc/PID ]`.

*Observed 2026-11-12 (python-dev)*
