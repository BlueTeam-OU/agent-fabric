#!/usr/bin/env bash
# tools/fabric/github-repo-settings.sh — reapply this repository's GitHub-side
# settings (docs/adr/ADR-019-work-arrives-as-pull-requests.md §6) to a
# repository, with `gh`. It covers the repository, Actions and workflow
# permissions; code scanning and secret scanning are set on GitHub by hand.
#
#   tools/fabric/github-repo-settings.sh [owner/repo]     # default: gzapi-org/agent-fabric
#   tools/fabric/github-repo-settings.sh --show [owner/repo]
#
# Idempotent: every call sets the documented value. It never touches
# secrets (there are none), rules (there are none) or collaborators.
set -euo pipefail
show=0; [[ "${1:-}" == "--show" ]] && { show=1; shift; }
REPO="${1:-gzapi-org/agent-fabric}"
if (( show )); then
    gh api "repos/$REPO" --jq '{visibility, default_branch, description, has_issues, has_projects, has_wiki, has_discussions, allow_merge_commit, allow_squash_merge, allow_rebase_merge, allow_auto_merge, delete_branch_on_merge, allow_update_branch, merge_commit_title, merge_commit_message, squash_merge_commit_title, squash_merge_commit_message, web_commit_signoff_required}'
    gh api "repos/$REPO/actions/permissions" --jq '{actions_enabled: .enabled, allowed_actions}'
    gh api "repos/$REPO/actions/permissions/workflow" --jq '{default_workflow_permissions, can_approve_pull_request_reviews}'
    exit 0
fi
gh api -X PATCH "repos/$REPO" \
    -f description='Control plane for the agents working on sibling repositories: identities, roles, memory, model routing, messaging.' \
    -f default_branch=main \
    -F has_issues=true -F has_projects=true -F has_wiki=true -F has_discussions=false \
    -F allow_merge_commit=true -F allow_squash_merge=true -F allow_rebase_merge=true \
    -F allow_auto_merge=false -F delete_branch_on_merge=false -F allow_update_branch=false \
    -f merge_commit_title=MERGE_MESSAGE -f merge_commit_message=PR_TITLE \
    -f squash_merge_commit_title=COMMIT_OR_PR_TITLE -f squash_merge_commit_message=COMMIT_MESSAGES \
    -F web_commit_signoff_required=false >/dev/null
gh api -X PUT "repos/$REPO/actions/permissions" -F enabled=true -f allowed_actions=all >/dev/null
gh api -X PUT "repos/$REPO/actions/permissions/workflow" -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false >/dev/null
echo "github-repo-settings: applied to $REPO (docs/adr/ADR-019-work-arrives-as-pull-requests.md)"
