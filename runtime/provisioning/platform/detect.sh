# shellcheck shell=bash
# runtime/provisioning/platform/detect.sh — source this to load the
# platform profile for the machine it runs on: /etc/os-release decides
# the distribution, a Qubes marker the deployment. $AGENT_FABRIC_PLATFORM
# names one explicitly (a test, or a host the detection misreads).
_platform_dir="$(dirname "${BASH_SOURCE[0]}")"
platform_detect() {
    if [[ -n "${AGENT_FABRIC_PLATFORM:-}" ]]; then echo "$AGENT_FABRIC_PLATFORM"; return; fi
    local id="" like=""
    if [[ -r /etc/os-release ]]; then
        id="$(. /etc/os-release; echo "${ID:-}")"; like="$(. /etc/os-release; echo "${ID_LIKE:-}")"
    fi
    local qubes=""
    if [[ -d /usr/share/qubes || -n "${QUBES_ENV_SOURCED:-}" || -r /etc/qubes-release ]]; then qubes="-qubes"; fi
    case "$id $like" in
        fedora*) echo "fedora$qubes" ;;
        debian*|*debian*|ubuntu*) echo "debian$qubes" ;;
        *) echo "" ;;
    esac
}
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
# The host's own python3 runs what comes before the pin (the installer, the
# git and Claude Code hooks, bootstrap): no older than CI proves (ADR-040
# rule 1). Ubuntu 24.04's 3.12 and Debian 12's 3.11 are below it.
FABRIC_HOST_PYTHON_MIN=3.13
host_python_ok() { python3 -c 'import sys; m = tuple(int(x) for x in sys.argv[1].split(".")); sys.exit(sys.version_info[:2] < m)' "$FABRIC_HOST_PYTHON_MIN" 2>/dev/null; }
