#!/usr/bin/env bash
# runtime/provisioning/platform/packages.sh [--operator] [platform] — the
# packages that provide the fabric's host contract on a platform (default:
# the one this runs on), one per line, sorted. What a person installs, and
# what the CI smoke containers install before running the suites — so the
# map is proven by being used.
#
# --operator prints instead the ONE line the owner pastes in the template VM
# at first run: the install command, the host packages, then the operator's
# (FABRIC_OPERATOR_TOOLS). In a Qubes AppVM it is headed by the TemplateVM to
# paste it in. Same output as `host_platform.py packages --operator`.
set -uo pipefail
operator=0
if [[ "${1:-}" == --operator ]]; then operator=1; shift; fi
[[ -n "${1:-}" ]] && export AGENT_FABRIC_PLATFORM="$1"
# shellcheck source=runtime/provisioning/platform/detect.sh
. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/detect.sh"
[[ "$PLATFORM_ID" != unknown ]] || { echo "packages.sh: unknown platform (AGENT_FABRIC_PLATFORM=fedora|fedora-qubes|debian|debian-qubes)" >&2; exit 2; }
host_list() { for tool in "${FABRIC_HOST_TOOLS[@]}"; do pkg_for "$tool"; done | sort -u; }
if ((! operator)); then host_list; exit; fi
case "$PLATFORM_ID" in
    fedora*) install_cmd="sudo dnf install -y" ;;
    *) install_cmd="sudo apt-get install -y" ;;
esac
line="$install_cmd $( { host_list; for tool in "${FABRIC_OPERATOR_TOOLS[@]}"; do pkg_for "$tool"; done | sort -u; } | tr '\n' ' ')"
line="${line% }"
template=""
if [[ "$PLATFORM_ID" == *-qubes && "$(timeout 10 qubesdb-read /type 2>/dev/null </dev/null)" == AppVM ]]; then
    template="$(timeout 10 qubesdb-read /qubes-base-template 2>/dev/null </dev/null)"
fi
if [[ -n "$template" ]]; then
    echo "In the TemplateVM $template (Qubes menu: $template > Terminal), paste once, then shut it down and restart this qube:"
    echo "  $line"
else
    [[ "$PLATFORM_ID" == *-qubes ]] && echo "packages.sh: no TemplateVM name from qubesdb (not an AppVM here, or qubesdb-read failed): the line alone" >&2
    echo "$line"
fi
