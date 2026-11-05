---
role: "devex-tooling"
class: workflow
topic: "dependabot-pr-review-posters"
description: "a blind review posted on a Dependabot PR counts only once the push account is a poster: by default from j271 (review_posters.for_pr), by AGENT_FABRIC_REVIEW_POSTERS by hand before it lands"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 93d4358a058d9204
  - db5801709eb4aa05
---

## a blind review posted on a Dependabot PR counts only once the push account is a poster: by default from j271 (review_posters.for_pr), by AGENT_FABRIC_REVIEW_POSTERS by hand before it lands

On a Dependabot PR the PR author is the bot, so the push account's blind review read "marked, other login" (not coverage) and arm's gate 4c did not read its findings. j271 (branch develop-qzapp/devex-tooling/for/user/j271-bot-pr-posters, commit 10fd6489, 2026-11-02) adds `tools/fabric/github/review_posters.py`: on an app's PR (gh pr view `app/…`+is_bot, REST `…[bot]`/type Bot, GraphQL `__typename: Bot`) the login `gh api user` names is a poster, in pr-review-status, the review checkpoint, gate 4c and pr-counts. Before it is on main (check by ancestry), set `export AGENT_FABRIC_REVIEW_POSTERS='["<gh api user login>"]'` by hand. Arm still needs `--any-owner` (the branch names no session). Seen #266 (2026-10-24), #408/#409 (2026-11-01). Related: [[review-post-no-repo-flag]].

*References: review-post-no-repo-flag*

*Anchors: `tools/fabric/github/review_posters.py::def for_pr`, `tools/fabric/github/review_status/verdicts.py::cfg.review_posters`*

*Observed 2026-11-02 (devex-tooling)*
