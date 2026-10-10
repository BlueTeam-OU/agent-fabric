# shellcheck shell=bash
# runtime/provisioning/platform/debian-qubes.sh — a Debian TemplateVM's
# AppVM under Qubes OS: the same volatile root as fedora-qubes.sh (only
# /home, /rw and /usr/local survive), so packages belong to the template
# and the account records go through persist_accounts.py. Not yet read
# back on a live host: detect.sh names it when the Qubes marker is found
# on a Debian-like /etc/os-release (review, 2026-09-17).
# shellcheck source=runtime/provisioning/platform/debian.sh
. "$(dirname "${BASH_SOURCE[0]}")/debian.sh"
PLATFORM_ID=debian-qubes
PERSISTS_ACROSS_REBOOT=0
PKG_INSTALL_HINT="in the TemplateVM: sudo apt-get install --no-install-recommends"
SUDO_GROUP_NOTE="sudo is the qubes group's; role accounts are not in it (runtime/provisioning/moveto/README.md)"
