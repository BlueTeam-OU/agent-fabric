# shellcheck shell=bash
# runtime/provisioning/platform/fedora-qubes.sh — a Fedora TemplateVM's
# AppVM under Qubes OS: only /home, /rw and /usr/local survive a reboot, so
# a package is installed in the TemplateVM, never here, and sudo reaches
# the operator through the `qubes` group (which role accounts are not in).
# The account records themselves (/etc/passwd and its siblings) and the
# linger flag are on the volatile root: runtime/provisioning/
# persist_accounts.py snapshots them under /rw/config/agent-fabric/ and
# platform/qubes/agent-fabric-accounts.rc re-adds them at boot from
# /rw/config/rc.local.d (found 2026-09-17: fifteen accounts that had never
# met a reboot).
# shellcheck source=runtime/provisioning/platform/fedora.sh
. "$(dirname "${BASH_SOURCE[0]}")/fedora.sh"
PLATFORM_ID=fedora-qubes
PERSISTS_ACROSS_REBOOT=0
PKG_INSTALL_HINT="in the TemplateVM: sudo dnf install"
SUDO_GROUP_NOTE="sudo is the qubes group's; role accounts are not in it (runtime/provisioning/moveto/README.md)"
