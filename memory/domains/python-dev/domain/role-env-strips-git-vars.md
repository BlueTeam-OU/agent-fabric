---
role: "python-dev"
class: domain
topic: "role-env-strips-git-vars"
description: "a test's role env built from os.environ must drop inherited GIT_*; prove with GIT_DIR at a decoy repo and a hostile GIT_CONFIG_GLOBAL"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2a8097b5d7585819
---

## a test's role env built from os.environ must drop inherited GIT_*; prove with GIT_DIR at a decoy repo and a hostile GIT_CONFIG_GLOBAL

A test env built as {**os.environ, HOME: scratch, GIT_CONFIG_GLOBAL: scratch}
still passes GIT_DIR/GIT_WORK_TREE/GIT_CONFIG_PARAMETERS through: run from a
hook, the fixture's `git init`+commit lands in the hook's repo. Drop every
inherited GIT_* and add back your own. Counterfactuals that bite
(tests/test_secret_store.py, branch develop-qzapp/python-dev-01/test/
secret-store-git-env, 2026-10-07): GIT_DIR=<decoy>/.git (decoy gains a
commit without the strip); GIT_CONFIG_GLOBAL with init.templateDir holding a
failing pre-commit hook (crashes un-env'd fixture setup); a malformed
GIT_CONFIG_GLOBAL ("[broken") fails any git call that reads it. Also: a
check capping stdout length fails under a long TMPDIR — use a short one.
See [[env-isolation-in-process-environ]], [[git-config-get-reads-beyond-the-repo]].

Fleet-wide (#112, 2026-10-08): tests/git_env.py — scrub_process_env() in each
suite's __main__ (drops GIT_*, GIT_CONFIG_NOSYSTEM=1; NOT GIT_CONFIG_GLOBAL:
secrets_sync's test reads a global config the tool wrote into a scratch HOME)
and git_env() for a test's own git calls (devnull global/XDG, fixed identity).
Three suites already scrubbed themselves (secrets_sync, fabric_fresh_git,
store_enroll): their base passed every counterfactual, so no change there.
Run the base side from a scratch `git worktree add --detach <dir> origin/main`,
never by swapping files in the tree, so lanes can run in parallel.

*References: env-isolation-in-process-environ, git-config-get-reads-beyond-the-repo*

*Observed 2026-10-08 (python-dev)*
