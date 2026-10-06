#!/bin/sh
# A gh for the secrets-sync tests (AGENT_FABRIC_GH): it keeps one token in
# the sandbox HOME and never reaches the network or a keyring. A real gh in
# a test once read the runner's keyring and tried a login with a fixture
# token (2026-10-06).
f="${GH_CONFIG_DIR:-$HOME/.config/gh}/fake-token"
case "$1 $2" in
  "auth token") [ -s "$f" ] && cat "$f" && exit 0; exit 1 ;;
  "auth login") mkdir -p "$(dirname "$f")" && cat > "$f"; exit "${FAKE_GH_LOGIN_EXIT:-0}" ;;
esac
echo "fake gh: unsupported: $*" >&2
exit 2
