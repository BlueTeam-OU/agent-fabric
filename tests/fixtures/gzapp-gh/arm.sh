#!/usr/bin/env bash
# gzapp's forwarder to the fabric's runtime/github/arm.sh — the one place
# this project's own names for the tool are allowed to live (the lint
# refuses them in runtime/, which is what keeps the tool every project's).
# gzapp's tools/gh/arm.sh forwards here, argv and stdin untouched.
#
# The rules are this directory's arm.json, named here rather than found
# from the clone's remote. The review reader arm calls counts gzapp's
# legacy review marker as pr-gate's forwarder does, and the GZAPP_*
# environment names gzapp's test_arm.sh and skills use are mapped to the
# fabric's, the fabric's winning when both are set.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AGENT_FABRIC_ARM_CONFIG="${AGENT_FABRIC_ARM_CONFIG:-$here/arm.json}"
export AGENT_FABRIC_LEGACY_REVIEW_MARKERS="${AGENT_FABRIC_LEGACY_REVIEW_MARKERS:-<!-- gzapp-substitute-review v1 -->}"
[[ -n "${GZAPP_PR_GATE:-}" ]]          && export AGENT_FABRIC_PR_GATE="${AGENT_FABRIC_PR_GATE:-$GZAPP_PR_GATE}"
[[ -n "${GZAPP_PR_REVIEW_STATUS:-}" ]] && export AGENT_FABRIC_PR_REVIEW_STATUS="${AGENT_FABRIC_PR_REVIEW_STATUS:-$GZAPP_PR_REVIEW_STATUS}"
[[ -n "${GZAPP_PR_SESSION:-}" ]]       && export AGENT_FABRIC_PR_SESSION="${AGENT_FABRIC_PR_SESSION:-$GZAPP_PR_SESSION}"
exec bash "$here/../../../runtime/github/arm.sh" "$@"
