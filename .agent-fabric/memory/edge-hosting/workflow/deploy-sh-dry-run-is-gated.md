---
role: "edge-hosting"
class: workflow
topic: "deploy-sh-dry-run-is-gated"
description: "Running blueteam.ee deploy/deploy.sh, even a credential-less dry run, can be refused by auto mode as a production deploy; verify a deploy-tool change by its parts"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "edge-hosting"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 57d6aa49291625e9
---

## Running blueteam.ee deploy/deploy.sh, even a credential-less dry run, can be refused by auto mode as a production deploy; verify a deploy-tool change by its parts

On 2026-10-19 (blueteam.ee PR #15, the check-dist port) a second run of
`deploy/deploy.sh` with no `BLUETEAM_DEPLOY_*` in the environment was refused
by the auto-mode classifier as "[Production Deploy]"; the first run had gone
through. Without host and user set, `site_upload.py` does a dry run that never
contacts the host (`site_upload.py` "dry run without the host" line), but the
classifier does not know that.

**Why:** the refusal covers the outcome, not the command; retrying another
way counts as working around it.

**How to apply:** verify a change to the deploy chain by its parts —
`npm ci && npm run build`, `npm run check`, `bash -n deploy/deploy.sh`, the
`deploy/tests/` suite — and run `deploy.sh` itself at most once, saying why.
A live deploy still needs the owner's word in session
([[publish-needs-owner-word-in-session]]).

*References: publish-needs-owner-word-in-session*

*Anchors: `deploy/site_upload.py::dry run without the host`, `deploy/deploy.sh::check_dist.py`*

*Observed 2026-10-19 (edge-hosting)*
