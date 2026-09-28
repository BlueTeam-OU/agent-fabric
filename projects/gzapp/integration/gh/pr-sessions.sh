#!/usr/bin/env bash
# Compatibility forwarder: the GitHub tooling is agent-fabric's, at
# runtime/github/pr-sessions.sh, general to every managed project (the project
# supplies its repository through the working copy). gzapp's tools/gh/pr-sessions.sh still
# names this path; it is repointed in gzapp's next change, then this goes.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)/runtime/github/pr-sessions.sh" "$@"
