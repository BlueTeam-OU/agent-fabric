#!/usr/bin/env bash
# policies/check_adr_amendment.sh — every commit a branch adds that edits
# the body of an existing decision record records it: an Amendments row in
# the same commit, or an `ADR-Editorial: <why>` trailer (agent-fabric
# ADR-001 §5 rule 4). The commit hook cannot see this — it judges one
# staged tree, and the question is about each commit's diff — so it runs
# over the branch's range, in CI and in tests/run.sh, like the attribution
# guard whose range logic it follows.
#
# Range: the event payload's base..head in CI; else AGENT_FABRIC_ADR_BASE,
# origin/<GITHUB_BASE_REF>, origin/main or main, ..HEAD. No range, or no
# docs/adr/ at all, is a pass that says so — never a guess.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2
[[ -d docs/adr ]] || { echo "check_adr_amendment: no docs/adr/ — nothing to check"; exit 0; }

base=""; head="HEAD"
if [[ -n "${GITHUB_EVENT_PATH:-}" && -r "${GITHUB_EVENT_PATH:-}" ]] && command -v jq >/dev/null 2>&1; then
    b="$(jq -r '.pull_request.base.sha // .merge_group.base_sha // empty' "$GITHUB_EVENT_PATH" 2>/dev/null)"
    h="$(jq -r '.pull_request.head.sha // .merge_group.head_sha // empty' "$GITHUB_EVENT_PATH" 2>/dev/null)"
    if [[ -n "$b" && -n "$h" ]] && git cat-file -e "$b^{commit}" 2>/dev/null && git cat-file -e "$h^{commit}" 2>/dev/null; then
        base="$b"; head="$h"
    fi
fi
if [[ -z "$base" ]]; then
    for c in "${AGENT_FABRIC_ADR_BASE:-}" "origin/${GITHUB_BASE_REF:-}" origin/main main; do
        [[ -n "$c" && "$c" != "origin/" ]] || continue
        if git rev-parse --verify -q "$c^{commit}" >/dev/null 2>&1; then base="$c"; break; fi
    done
fi
[[ -n "$base" ]] || { echo "check_adr_amendment: no base to compare with — not enforced"; exit 0; }
# The fleet's pinned Python (runtime/python.json, ADR-040), one per host;
# AGENT_FABRIC_PYTHON points elsewhere for a test or a host without it.
py="${AGENT_FABRIC_PYTHON:-/usr/local/bin/fabric-python}"
[[ -x "$py" ]] || { echo "check_adr_amendment.sh: the fleet's pinned Python is not installed at $py; as root: /usr/bin/python3 <agent-fabric>/tools/fabric/python_pin.py install" >&2; exit 127; }
exec "$py" tools/fabric/adr.py range-check "$base" "$head"
