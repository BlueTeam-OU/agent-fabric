---
role: "fabric-coordinator"
class: threads
topic: "j544-readback-2-1-286"
description: "2026-11-01 read-back on develop-qzapp, Claude Code 2.1.286: the managed exec-form hook runs with its args and its deny holds; still to record under docs/live-checks/ in j544's session"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9fac51883829b56b
---

## 2026-11-01 read-back on develop-qzapp, Claude Code 2.1.286: the managed exec-form hook runs with its args and its deny holds; still to record under docs/live-checks/ in j544's session

The owner installed ADR-043 rules 1-2 on develop-qzapp at 2026-11-01 ~14:30Z, from main afd25d75. That host carries all 30 logins. The owner ran my scratchpad script, which named `bin/fabric-managed` by its full path: a bare `sudo fabric-managed` is not on sudo's secure_path. That is a doc bug, queued with j545.

Measured afterwards on 2.1.286, the pinned build:
- `fabric-managed check` reported "in force (fabric-afd25d75…)".
- `probe` reported ok: hook_entry agent-dispatch-guard denies a class dispatch with no model, and `claude --plugin-dir` exits 1 under disableSideloadFlags (N2/N3 on 2.1.286).
- **N9 on 2.1.286.** I ran a headless `claude -p --model haiku --allowedTools Bash` in a throwaway git repo that has no project settings. `~/.claude/settings.json` has 12 user-scope hooks and no pipe-status hook, so the managed file was the only source of that guard. The control command `git log --oneline | wc -l` ran and printed 1. The test command `false | tail -1 && git commit --allow-empty -m probe` was denied with the pipe-status reason, and the repo still had 1 commit. So 2.1.286 honours exec-form `command`+`args`. Without the args, fabric-python would have read the payload as a script and failed open.
- **How the session got its account.** A bare `claude -p` from Bash fails with "weekly limit", because Bash does not hold the session's CLAUDE_CODE_OAUTH_TOKEN and falls back to the console login. The wrapper (scratchpad rb286.py) loads only CLAUDE_CODE_OAUTH_TOKEN from ~/.config/agent-fabric/secrets.env into the child's environment and never prints it. The owner's choice was "use the API key", but the API key was not needed: fabric-secret-run refuses CLAUDE_ names.
- **Not measured on 2.1.286.** N11a/N11b, a managed hook that cannot spawn. It needs the interpreter or the snapshot removed as root.

**How to apply:** in j544's session, add a live-check record (docs/live-checks/2026-11-01-managed-settings-2-1-286.md) with these lines, and say that other hosts may be installed. Rollback is `sudo rm /etc/claude-code/managed-settings.json`. Related: [[owner-bug-list-after-j509]].

*References: owner-bug-list-after-j509*

*Observed 2026-11-01 (fabric-coordinator)*
