"""tools/fabric/provisioning/host_platform.py — the platform profile of the
machine provisioning runs on: what runtime/provisioning/platform/{detect,
packages,debian,fedora,fedora-qubes,debian-qubes}.sh held (agent-fabric
ADR-040 Wave 5, off shell). /etc/os-release decides the distribution, a
Qubes marker the deployment; $AGENT_FABRIC_PLATFORM names one explicitly (a
test, or a host the detection misreads).

CONTRACT, frozen from the shell
  detect(environ, os_release, qubes_markers) -> a profile name, or ""
      AGENT_FABRIC_PLATFORM wins, whatever it says; else ID and ID_LIKE of
      /etc/os-release: fedora* is fedora, debian*, *debian* and ubuntu* are
      debian, anything else (or no file) is none; a Qubes marker (a
      /usr/share/qubes directory, QUBES_ENV_SOURCED set non-empty, a
      readable /etc/qubes-release) adds "-qubes". A name with no profile
      (AGENT_FABRIC_PLATFORM=x) is the unknown profile.
  profile(name) -> Profile(id, persists_across_reboot, pkg_install_hint,
      global_bashrc, sudo_group_note, packages)
  pkg_for(profile, tool) -> the package providing a tool of the fabric's
      host contract; a tool with no entry is its own name, and so is every
      tool on an unknown platform
  packages(profile) -> the sorted, de-duplicated package list the contract
      needs: what `packages.sh [platform]` printed, one per line (CI installs
      it before any Python runs it, so CI keeps asking a shell for it; see
      `python3 host_platform.py packages [platform]`)
  host_python_ok(version) -> the host's python3 is no older than
      FABRIC_HOST_PYTHON_MIN

CLI  python3 host_platform.py detect                  print the profile name ("" is a blank line)
     python3 host_platform.py packages [platform]     one package per line; exit 2, with the
                                                 shell's message, on an unknown platform
"""
from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field

# The fabric's host contract: what its hooks, scripts and provisioning call.
FABRIC_HOST_TOOLS = ("bash", "sudo", "ssh", "getent", "pgrep", "timeout", "flock", "stat", "sha256sum", "cmp", "useradd",
                     "usermod", "shred", "install", "curl", "python3", "node", "npm", "git", "gh", "jq", "gpg", "paperkey",
                     "openssl")
# The host's own python3 runs what comes before the pin (the installer, the
# git and Claude Code hooks, bootstrap): no older than CI proves (ADR-040
# rule 1). Ubuntu 24.04's 3.12 and Debian 12's 3.11 are below it.
FABRIC_HOST_PYTHON_MIN = (3, 13)


@dataclass(frozen=True)
class Profile:
    id: str
    persists_across_reboot: bool
    pkg_install_hint: str
    global_bashrc: str
    sudo_group_note: str
    packages: Mapping[str, str] = field(default_factory=dict)

    def pkg_for(self, tool: str) -> str:
        return self.packages.get(tool, tool)


UNKNOWN = Profile("unknown", True, "install with the distribution's package manager", "/etc/bashrc", "sudo: unknown platform")

# Fedora, a plain install.
FEDORA = Profile("fedora", True, "sudo dnf install", "/etc/bashrc", "sudo is the wheel group's", {
    "git": "git-core", "node": "nodejs", "npm": "nodejs-npm", "gpg": "gnupg2", "ssh": "openssh-clients",
    "getent": "shadow-utils", "useradd": "shadow-utils", "usermod": "shadow-utils", "pgrep": "procps-ng",
    "timeout": "coreutils", "stat": "coreutils", "sha256sum": "coreutils", "shred": "coreutils", "install": "coreutils",
    "flock": "util-linux", "cmp": "diffutils"})

# Debian, and a derivative that says so in ID_LIKE.
DEBIAN = Profile("debian", True, "sudo apt-get install --no-install-recommends", "/etc/bash.bashrc",
                 "sudo is the sudo group's", {
    "node": "nodejs", "gpg": "gnupg", "ssh": "openssh-client", "getent": "libc-bin", "useradd": "passwd",
    "usermod": "passwd", "pgrep": "procps", "timeout": "coreutils", "stat": "coreutils", "sha256sum": "coreutils",
    "shred": "coreutils", "install": "coreutils", "flock": "util-linux", "cmp": "diffutils"})

# A TemplateVM's AppVM under Qubes OS: only /home, /rw and /usr/local survive
# a reboot, so a package is installed in the TemplateVM, never here, and sudo
# reaches the operator through the `qubes` group (which role accounts are not
# in). The account records themselves (/etc/passwd and its siblings) and the
# linger flag are on the volatile root: persist-accounts snapshots them under
# /rw/config/agent-fabric/ and platform/qubes/agent-fabric-accounts.rc re-adds
# them at boot from /rw/config/rc.local.d (found 2026-09-17: fifteen accounts
# that had never met a reboot).
_QUBES_NOTE = "sudo is the qubes group's; role accounts are not in it (runtime/provisioning/moveto/README.md)"
PROFILES: dict[str, Profile] = {
    "fedora": FEDORA,
    "debian": DEBIAN,
    "fedora-qubes": Profile("fedora-qubes", False, "in the TemplateVM: sudo dnf install", FEDORA.global_bashrc,
                            _QUBES_NOTE, FEDORA.packages),
    "debian-qubes": Profile("debian-qubes", False, "in the TemplateVM: sudo apt-get install --no-install-recommends",
                            DEBIAN.global_bashrc, _QUBES_NOTE, DEBIAN.packages),
}


def _os_release(path: str) -> tuple[str, str]:
    """ID and ID_LIKE of an os-release file; both empty when it cannot be read."""
    values = {"ID": "", "ID_LIKE": ""}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                key, sep, rest = line.strip().partition("=")
                if sep and key in values:
                    values[key] = rest.strip().strip("\"'")
    except OSError:
        pass
    return values["ID"], values["ID_LIKE"]


def detect(environ: Mapping[str, str] | None = None, *, os_release: str = "/etc/os-release",
           qubes_dir: str = "/usr/share/qubes", qubes_release: str = "/etc/qubes-release") -> str:
    env = os.environ if environ is None else environ
    if env.get("AGENT_FABRIC_PLATFORM"):
        return env["AGENT_FABRIC_PLATFORM"]
    ident, like = _os_release(os_release)
    qubes = "-qubes" if (os.path.isdir(qubes_dir) or env.get("QUBES_ENV_SOURCED") or os.access(qubes_release, os.R_OK)) else ""
    text = f"{ident} {like}"
    if text.startswith("fedora"):
        return "fedora" + qubes
    if text.startswith(("debian", "ubuntu")) or "debian" in text:
        return "debian" + qubes
    return ""


def profile(name: str) -> Profile:
    return PROFILES.get(name, UNKNOWN)


def packages(prof: Profile) -> list[str]:
    return sorted({prof.pkg_for(t) for t in FABRIC_HOST_TOOLS})


def host_python_ok(version: tuple[int, ...] | None = None) -> bool:
    return (tuple(version) if version is not None else tuple(sys.version_info[:2])) >= FABRIC_HOST_PYTHON_MIN


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    env = dict(os.environ if environ is None else environ)
    if argv[:1] == ["detect"]:
        print(detect(env))
        return 0
    if argv[:1] == ["packages"]:
        if len(argv) > 1 and argv[1]:
            env["AGENT_FABRIC_PLATFORM"] = argv[1]
        prof = profile(detect(env))
        if prof.id == "unknown":
            print("packages.sh: unknown platform (AGENT_FABRIC_PLATFORM=fedora|fedora-qubes|debian|debian-qubes)", file=sys.stderr)
            return 2
        print("\n".join(packages(prof)))
        return 0
    print("usage: host_platform.py detect | packages [platform]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
