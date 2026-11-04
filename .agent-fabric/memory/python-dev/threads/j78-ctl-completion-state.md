---
role: "python-dev"
class: threads
topic: "j78-ctl-completion-state"
description: "j78 (REQUEST 01a163f9) fabric-ctl bash completion supplied to python-dev-01 — what is written uncommitted, what is left"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d740bc6b80d21041
---

## j78 (REQUEST 01a163f9) fabric-ctl bash completion supplied to python-dev-01 — what is written uncommitted, what is left

j78: completion for `fabric-ctl` supplied to python-dev-01 on branch `develop-qzapp/python-dev-02/for/python-dev-01/j349-ctl-completion`, worktree `~/projects/agent-fabric-j78-ctl-completion` (off origin/main e183f60d). No PR, no own review. Undertaken by REPLY seq 451105.

Written and UNCOMMITTED there (the commit hook refused in the session that had worked j76; commit in the fresh one): `tools/fabric/control/completion.bash` (function `_fabric_ctl`, logins = keys of registry.json `placement` via python3, word 2 and 3+ from `fabric-ctl --verbs [verb]`, sort -u, `--json --timeout --help` added) and `tests/test_control_completion.py` (10 cases, stub fabric-ctl, fixture registry; every behaviour mutation-checked and caught).

Left: `python3 tools/fabric/lint.py`, commit with `Kind: work` (heredoc), `tests/run.sh` with AGENT_FABRIC_*/GITHUB_*/GIT_DIR stripped, push, check `git ls-remote`, then REPLY to develop-qzapp/python-dev-01 with the head sha, cc develop-qzapp/user: path chosen (the default one), and that the `--verbs` format assumed is one word per line, unknown verb -> nothing (python-dev-01's REQUEST was not in my inbox; ask if their format differs). Then `fabric-jobs deliver j78 <branch>`.

UPDATE 2026-10-22: coordinator's route (seq 453989): job paused+switched; new worktree `~/projects/agent-fabric-j78-fabric-ctl-bash-completion-of-target` (branch feat/j78-..., empty). Fresh session: copy the two files from the old hand-made worktree `~/projects/agent-fabric-j78-ctl-completion`, lint, commit Kind: work, tests/run.sh CI env, `git push origin HEAD:develop-qzapp/python-dev-02/for/python-dev-01/j349-ctl-completion`, REPLY python-dev-01 (interface confirmed: --verbs one word per line, unknown verb exit 2 stderr) with sha cc user, remove old worktree (no --force), deliver j78.

DONE 2026-10-22: delivered, head 361da472 on the for/ branch, REPLY seq 455003 + INFO to user. Trap: tests/test_arm_policy.py fails 70 cases from a long worktree path (87 chars) - run the suite from a short worktree path; reported to python-dev-01. test_gzcoord_port deadline case flakes under load.

*Observed 2026-10-22 (python-dev)*
