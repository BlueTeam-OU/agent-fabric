#!/usr/bin/env bash
# Run as root IN THE TEMPLATEVM, once, before ssh-operator.sh in the AppVM
# (agent-fabric ADR-048 §5 rule 6). An AppVM's /usr resets from its
# template at every boot, so the package can only come from here.
#
#     sudo runtime/provisioning/platform/qubes/ssh-template.sh [--dry-run]
#
# The package and nothing else: no configuration, no host key, and sshd
# left DISABLED, because every AppVM on this template boots from it and
# only ours restores a configuration (ssh-operator.sh). dnf applies the
# distribution's preset on install, which may enable sshd — with password
# login on every address — so it is disabled explicitly, every run.
set -euo pipefail
dry=0
case "${1:-}" in
    --dry-run) dry=1 ;;
    '') ;;
    *) echo "usage: ssh-template.sh [--dry-run]" >&2; exit 2 ;;
esac
run() { if (( dry )); then printf 'would run:'; printf ' %q' "$@"; echo; else "$@"; fi; }
if (( !dry )) && [[ $EUID -ne 0 ]]; then
    echo "ssh-template.sh: run as root in the TemplateVM (sudo)" >&2; exit 1
fi
if rpm -q openssh-server >/dev/null 2>&1; then
    echo "openssh-server is installed"
else
    run dnf install -y openssh-server
fi
run systemctl disable sshd.service
echo "Now shut the template down and restart the AppVM; then run ssh-operator.sh there (or let its boot block apply what it staged)."
