---
role: "devex-tooling"
class: threads
topic: "j146-pr-repo-flag-design"
description: "j146 fabric-pr --repo design survey: where each verb reads repo and project from the cwd, what to reuse, the worktree/branch already set up"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - cbf688b2e5051aad
---

## j146 fabric-pr --repo design survey: where each verb reads repo and project from the cwd, what to reuse, the worktree/branch already set up

j146 (REQUEST 01a14f2c, from the owner via fabric-coordinator): `--repo <owner>/<name> | <project id>` on arm, gate, wait-merged, post-review and review-status. The design was promised in REPLY 01a14f2e (seq 311580).

- **Worktree:** ~/projects/agent-fabric-j146-fabric-pr-arm-take-repo-so, on branch develop-qzapp/devex-tooling/for/user/j146-pr-repo-flag. The branch was renamed from the job's feat/ name, because the fence requires for/.
- **Repository:** every verb takes it from `gh.this_repo()` (arm.py:638, pr_gate.py:576, wait_merged.py:611, post_review.py:409, pr_review_status.py:203). GH_REPO already overrides it.
- **Project rules:** these come from the cwd. `common.project_config_path` uses `workingcopy.resolve(local.toplevel())` for arm.json (arm_rules.py:38) and pr-tools.json (`apply_project_env`). A --repo naming a repository that no project registers must get NO project, never the cwd's.
- **Plan:** parse --repo once, in fabric_pr.py's dispatcher, for those five verbs only. Strip it from argv, set GH_REPO, and set a project variable (e.g. AGENT_FABRIC_PR_PROJECT, possibly empty) that project_config_path honours before toplevel. Resolve names with pr_counts.registry_projects, resolve_name and project_of_repo.
- **Already safe:** landed.head_in_base answers None when the clone's origin is another repository. post_review's toplevel is only the lane check.
- **Landed b0c9062d (2026-10-18):** dispatcher fabric_pr.take_repo + common.resolve_repository; AGENT_FABRIC_PR_PROJECT set (even "") overrides the cwd in common.project_config_path, and is popped when no --repo. arm reads this_repo before pr view and names it. Mutation-checked: drop GH_REPO → 9 FAILs, drop project → 2.
- **Test trap:** test_arm_cli's gh mock serves only gzapi-org/gzapp, so the acceptance arms `--repo gzapp` from the InterWeave clone with GH_REPO unset (cli(unset=…)); the shim logs each call's GH_REPO to state/gh_repos.
- **Tests:** the test_arm_cli and test_fabric_pr pattern, with gh mocked on PATH. Acceptance: dry-run-arm a PR of repo A from a checkout of repo B.

*Observed 2026-10-18 (devex-tooling)*
