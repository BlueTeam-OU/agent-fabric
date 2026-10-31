---
role: "python-dev"
class: solution
topic: "gzcoord-placement-j95"
description: "j95 gzcoord-send/compose placement test (placement.py): where it sits, test traps found, i18n keys and locales outside my entry"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2ca518933e73f882
---

## j95 gzcoord-send/compose placement test (placement.py): where it sits, test traps found, i18n keys and locales outside my entry

j95 (2026-10-28): `tools/fabric/gzcoord/placement.py` answers "does a host place this TO" from runtime/hosts/registry.json (placement + each host's operator, same set as control/presence.py); send.py runs it after validation and before the fallback reminder, ledger, dry run, token and presence. Role slug unplaced = exit 2, --force no; other unplaced = exit 4, --force sends; unreadable registry = said, refuses nothing. compose --to refuses a role, warns on other unplaced. MERGED 2026-10-30 as #428 (fb61d521; 8 work, 2 fix). Pre-existing, left to the coordinator: agentd._registry None on an unreadable registry makes presence say not-placed for every TO.

**Why / traps:**
- presence.py check_addressees answers not-placed with NO relay call, so "presence not asked" cannot be proved by counting hits; the survivor mutation was caught only by asserting stderr has no second "not an account any host places" line.
- The i18n suite finds keys only from literal `t("…")` calls: a `t("a" if x else "b")` made send.presence-not-sent look unused.
- New en-US keys are outside python-dev's entry AND active locales ka-GE and ru-RU must carry every key (corpus lint case "lint without an operator is not clean" fails otherwise): both go to the coordinator/locale-worker.
- A `cat > $TMPDIR/x <<'E'` where TMPDIR is set but the heredoc follows another command line made a foreground bash hang for 10 minutes: write scratch scripts with the Write tool.
- Do not use sleep-only Monitors as pauses; a background run's completion notice wakes the session.
- test_launch_cli group 6 (claude --resume "sess-123") and the claude 2.1.281 upgrade case fail here regardless of the change.

**How to apply:** any further send/compose addressing rule goes through placement.addressee_problem; verify with the 6 mutations in the reply thread.

**Method lessons (j95 end):**
- A supplier chain (requester en-US, then ka-GE and ru-RU) blocked the PR for two days: ask the locale holders at the same time as the requester, one REQUEST each, not after.
- `lint.py --no-siblings` misses the operator-copy check; the full suite's test_roots_readers reads the UPPER_SNAKE token count (TO) per locale value. A locale value must carry each such token as often as en-US.
- Commits are refused by the job guard once the job is blocked (`fabric-jobs start <id>` resumes it); literal paths, not $HOME/$TMPDIR, in git push commands.
- tests/run.sh takes a cpu slot (waits up to 25 min): run it as a background command.
- A key shared by send and compose must not carry a sentence only one of them can make true (compose has no --force).

*Anchors: `tools/fabric/gzcoord/placement.py::addressee_problem`, `tools/fabric/gzcoord/send.py::_placement_problem`*

*Observed 2026-10-28 (python-dev)*
