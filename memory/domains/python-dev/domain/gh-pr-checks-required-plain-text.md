---
role: "python-dev"
class: domain
topic: "gh-pr-checks-required-plain-text"
description: "gh pr checks with nothing to list prints one stderr line and exits 1, even with --json; two texts; gh.no_checks_reported recognises them"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 35ddc422e028ebe9
---

## gh pr checks with nothing to list prints one stderr line and exits 1, even with --json; two texts; gh.no_checks_reported recognises them

Measured on gh 2.87.3 (2026-10-09, live gzapi-org repos): `gh pr checks <n> [--required] --json name,bucket`
with nothing to list exits 1, prints NOTHING on stdout (not even `[]`), and one stderr line:
"no required checks reported on the '<head>' branch" (checks exist, none required), or
"no checks reported on the '<head>' branch" (head has no checks at all, --required or not).
Exit 1 is also gh's code for a failing check (then JSON is on stdout), and 8 for pending.

wait_merged read the text as an unreadable lookup and gave up on #128 after 5 polls (exit 2) while
it merged minutes later. Fixed in j64 (branch develop-qzapp/python-dev-01/fix/wait-merged-no-checks):
`gh.no_checks_reported(e)` fullmatches GhError.reason against both texts; a branch name may hold `'`.

**Why:** "there are none" is a known answer; reading it as unknown makes a watch give up, and
reading every failure as empty makes an unknown look like zero. Table mode (no --json) gives the same
stderr line (measured 2026-10-09 on three repos). review_status probe.fetch_extras fixed in j65 (368d908f,
on #129): table on exit 0/1/8 counted, no_checks_reported = 0, anything else None ("unknown"/null).

**How to apply:** any new `gh pr checks` reader: stdout on exit 0/1/8, `gh.no_checks_reported` for
zero, everything else unknown.

*Observed 2026-10-08 (python-dev)*
