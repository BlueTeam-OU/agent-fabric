# shellcheck shell=bash
# runtime/provisioning/platform/almalinux.sh — AlmaLinux 10, a plain install
# (measured on almalinux:10.2, 2026-11-11). The Fedora package names hold, but
# gh (and the operator's kitty) are in EPEL, so EPEL is enabled first; paperkey
# is in no repository of the release, so the contract lists it and the platform
# has no package for it. python3 is 3.12 here; the pin is the Python, not it.
PLATFORM_ID=almalinux
PERSISTS_ACROSS_REBOOT=1
PKG_INSTALL_HINT="sudo dnf install -y epel-release && sudo dnf install"
GLOBAL_BASHRC=/etc/bashrc
SUDO_GROUP_NOTE="sudo is the wheel group's"
PLATFORM_NO_PACKAGE=(paperkey)
PLATFORM_INSTALL_CMD="sudo dnf install -y epel-release && sudo dnf install -y"
# shellcheck source=runtime/provisioning/platform/fedora.sh
pkg_for() { ( . "$(dirname "${BASH_SOURCE[0]}")/fedora.sh"; pkg_for "$1" ); }
