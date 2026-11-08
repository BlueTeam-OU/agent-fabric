---
role: "fabric-coordinator"
class: threads
topic: "adr-043-managed-settings-option-1"
description: "owner 2026-10-31: harness upgrade goes the ADR-043 way — the owner installs managed settings as root; job j509; nothing of it is built yet"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 66a766ef742a4e24
  - 99dcae89459fb175
---

## owner 2026-10-31: harness upgrade goes the ADR-043 way — the owner installs managed settings as root; job j509; nothing of it is built yet

2026-10-31: the owner was asked whether to upgrade Claude Code. The pin is 2.1.286 (harness.json), and the newest build is 2.1.316. ADR-043 rule 6 holds the pin until `fabric-ctl all` reports rules 1 and 2 in force on every host. The owner chose option 1: the owner installs the managed settings as root on each host. The alternative was amending rule 6.

State found that day: no template, installer or check exists in the tree. `/etc/claude-code/` is absent on develop-qzapp, the only host in runtime/hosts/registry.json. The guards are 13 hook entries in runtime/claude-code/workspace/settings.json, and all of them run from `$AGENT_FABRIC_ROOT`, a login's own checkout.

Design facts that shape it:
- develop-qzapp is a Qubes AppVM, so /etc is lost at reboot ([[appvm-persists-only-rw]]). The managed file has to be re-created from /rw/config/rc.local.d.
- Root-owned guard copies mean every guard change after this needs an operator reinstall.

Tracked as job j509. A live read-back of the target build's managed keys comes first.

The plan, given to the owner 2026-10-31 ~15:40Z. They answered "do it" after it was explained, so it goes with a template and a renderer, not a static file copied as is.
1. Live read-back of the target build (2.1.316 or newer): the managed keys, the managed hooks, and that sideload is refused. Goes in docs/live-checks/.
2. The template goes in runtime/claude-code/managed/. A renderer fills each host's values, such as GUARD_DIR=/usr/local/lib/agent-fabric/hooks. The 13 workspace guard entries leave workspace/settings.json in the same change.
3. A root installer, `fabric-managed install`. It copies the guards plus the rendered file from a named commit on main. It also writes /rw/config/rc.local.d/agent-fabric-managed.rc so the file is re-created at boot.
4. The owner runs `! sudo fabric-managed install` on each host.
5. `fabric-ctl all status` reports in-force, missing or drifted, by comparing a fresh render of main with /etc.
6. The pin moves in harness.json, then a trial on one account, then `fabric-ctl all upgrade claude`.
It lands as one PR with an ADR-043 amendment (AppVM persistence, guard update path). The builder code is contracted to python-dev; runtime/claude-code/ and the guards stay mine.
Owner answers 2026-10-31 ~16:10Z: a reinstall for every guard change is accepted ("Yes, reinstall per change"), so step 2 may land. Running the read-back as root in a private `sudo unshare -m` namespace (an /etc overlay, then claude as uid 1000) was approved.
Step 1 is done: docs/live-checks/2026-10-31-managed-settings-2-1-316.md, commit c1f6fb80. Facts that change the build: CLAUDE_CODE_MANAGED_SETTINGS_PATH is ignored, so the check reads /etc only. disableSideloadFlags makes `--plugin-dir` and `--agents` exit 1 at start. `--mcp-config` is silently dropped. Probe scripts: scratchpad rb/ns.sh, all.sh, inner.sh. They are worth keeping as fabric-managed check's live probe.
Branch develop-qzapp/user/feat/j509-adr-043-rules-1-2-in, worktree ~/projects/agent-fabric-j509-adr-043-rules-1-2-in.

Progress 2026-10-31 ~17:00Z. Live check 150bd0ca: a managed hook inherits the session's PATH and env. A shell-form hook runs the absolute /bin/sh. Exec form (`command` = an absolute path, `args`) runs with no shell. Design: guards in exec form through a root-owned `runtime/claude-code/managed/hook_entry.py` (fabric-python -I -S, execve with an allowlisted env; ADR-040 r1: never bash, owner caught my bash contract). It runs a snapshot of one named sha, extracted by git plumbing (archive filters would run as root). The ADR-043 amendment is 4th commit on the branch (rule 2 rewritten, rule 9 added). The builder (code-high subagent) does managed_settings.py, bin/fabric-managed, the template, review-fence.py and the tests. Workspace guard entries become no-ops where /etc/claude-code/managed-settings.json exists. Next: the fabric-ctl status `managed` piece as a REQUEST to an idle python-dev holder (01, 03 or 04 idle that day) on `check --json`, after the builder lands. Follow-up job: split the session-start seal (ADR-038 r9) into its own managed hook.
- python-dev-01 j197 (REQUEST 01a1930d, 2026-10-31): status section + rule 6 upgrade gate; for/user/j509-managed-status on b67e0dff, fold then PR.
2026-10-31 ~18:10Z: pushed b67e0dff. Suite: FAILED_SUITES=0, and only the corpus lint is red, from 130 sibling INDEX/review-card findings, none of them agent-fabric's. j509 does NOT ride #437: it was at 24 work commits and blocked on review ([[over-16-work-commits-my-call]]). j509 gets its own PR after #437 merges, folding the for/ branch from python-dev-01 j197. The owner's install command needs the full path: `sudo ~/projects/agent-fabric/bin/fabric-managed install --sha <main sha>` (secure_path does not include the login's bin). Read-back N11b: a missing interpreter fails open, so the workspace gate also requires `-x /usr/local/bin/fabric-python` (commit b67e0dff).

*References: appvm-persists-only-rw, over-16-work-commits-my-call*

*Observed 2026-10-31 (fabric-coordinator)*
