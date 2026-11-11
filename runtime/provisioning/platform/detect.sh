# shellcheck shell=bash
# runtime/provisioning/platform/detect.sh — source this to load the
# platform profile for the machine it runs on: /etc/os-release decides
# the distribution, a Qubes marker the deployment. $AGENT_FABRIC_PLATFORM
# names one explicitly (a test, or a host the detection misreads).
_platform_dir="$(dirname "${BASH_SOURCE[0]}")"
platform_detect() {
    if [[ -n "${AGENT_FABRIC_PLATFORM:-}" ]]; then echo "$AGENT_FABRIC_PLATFORM"; return; fi
    local id="" like=""
    local osr="${AGENT_FABRIC_OS_RELEASE:-/etc/os-release}"
    if [[ -r "$osr" ]]; then
        id="$(. "$osr"; echo "${ID:-}")"; like="$(. "$osr"; echo "${ID_LIKE:-}")"
    fi
    local qubes=""
    if [[ -d /usr/share/qubes || -n "${QUBES_ENV_SOURCED:-}" || -r /etc/qubes-release ]]; then qubes="-qubes"; fi
    case "$id $like" in
        fedora*) echo "fedora$qubes" ;;
        almalinux*) [[ -n "$qubes" ]] && echo "" || echo almalinux ;;
        debian*|*debian*|ubuntu*) echo "debian$qubes" ;;
        *) echo "" ;;
    esac
}
PLATFORM_NO_PACKAGE=()
PLATFORM="$(platform_detect)"
if [[ -n "$PLATFORM" && -r "$_platform_dir/$PLATFORM.sh" ]]; then
    # shellcheck source=/dev/null
    . "$_platform_dir/$PLATFORM.sh"
else
    PLATFORM_ID=unknown; PERSISTS_ACROSS_REBOOT=1; PKG_INSTALL_HINT="install with the distribution's package manager"
    GLOBAL_BASHRC=/etc/bashrc; SUDO_GROUP_NOTE="sudo: unknown platform"
    pkg_for() { echo "$1"; }
fi
# The fabric's host contract: what its hooks, scripts and provisioning call.
FABRIC_HOST_TOOLS=(bash sudo ssh getent pgrep timeout flock stat sha256sum cmp useradd usermod shred install curl python3 node npm git gh jq gpg paperkey openssl)
# What the operator's desktop needs on the host the deck is attached from:
# kitty, for the graphics protocol the deck shows the agents' avatars with. Not
# in FABRIC_HOST_TOOLS on purpose: no account calls it, and CI installs that
# whole list in its containers (packages.sh --operator adds it).
FABRIC_OPERATOR_TOOLS=(kitty)
# CI's container check of the platform's python3 (ci.yml). Provisioning no
# longer reads it: it checks the pin, not the host's python3 (the owner's word,
# 2026-11-11).
FABRIC_HOST_PYTHON_MIN=3.13
host_python_ok() { python3 -c 'import sys; m = tuple(int(x) for x in sys.argv[1].split(".")); sys.exit(sys.version_info[:2] < m)' "$FABRIC_HOST_PYTHON_MIN" 2>/dev/null; }
