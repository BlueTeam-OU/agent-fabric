#!/usr/bin/env python3
"""tools/fabric/provisioning/host_platform.py: the detection and the package
lists the platform/*.sh scripts held (their differential check against the
shell, 0 differences over all four platforms and the unknown one, is the
source of the literal lists below). Plain script: prints ok/FAIL, exit 1
on any failure."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from provisioning import host_platform as hp  # noqa: E402

TOOL = os.path.join(HERE, "tools", "fabric", "provisioning", "host_platform.py")
FEDORA = ("bash coreutils curl diffutils gh git-core gnupg2 jq nodejs nodejs-npm openssh-clients openssl paperkey procps-ng "
          "python3 shadow-utils sudo util-linux").split()
DEBIAN = ("bash coreutils curl diffutils gh git gnupg jq libc-bin nodejs npm openssh-client openssl paperkey passwd procps "
          "python3 sudo util-linux").split()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as t:
        none = os.path.join(t, "no-qubes")

        def det(release: str | None, env: dict | None = None, qubes: bool = False) -> str:
            path = os.path.join(t, "os-release")
            if release is None:
                path = os.path.join(t, "absent")
            else:
                with open(path, "w") as fh:
                    fh.write(release)
            marker = t if qubes else none
            return hp.detect(env or {}, os_release=path, qubes_dir=marker, qubes_release=os.path.join(t, "no-release"))

        print("detect")
        check("fedora", det('ID=fedora\n') == "fedora")
        check("debian, ubuntu, and a derivative that says it is like debian",
              det('ID=debian\n') == "debian" and det('ID=ubuntu\nID_LIKE=debian\n') == "debian"
              and det('ID=mint\nID_LIKE="ubuntu debian"\n') == "debian")
        check("a distribution the fabric has no profile for is blank, and so is no file", det('ID=arch\n') == "" and det(None) == "")
        check("a Qubes marker adds -qubes (the directory)", det('ID=fedora\n', qubes=True) == "fedora-qubes"
              and det('ID=debian\n', qubes=True) == "debian-qubes")
        check("…QUBES_ENV_SOURCED set non-empty is one, set empty is not",
              det('ID=fedora\n', {"QUBES_ENV_SOURCED": "1"}) == "fedora-qubes" and det('ID=fedora\n', {"QUBES_ENV_SOURCED": ""}) == "fedora")
        check("AGENT_FABRIC_PLATFORM wins, whatever it says", det('ID=fedora\n', {"AGENT_FABRIC_PLATFORM": "debian"}) == "debian"
              and det('ID=fedora\n', {"AGENT_FABRIC_PLATFORM": "x"}) == "x")
        check("a name with no profile is the unknown profile", hp.profile("x").id == "unknown")

        print("packages")
        for name, want in (("fedora", FEDORA), ("fedora-qubes", FEDORA), ("debian", DEBIAN), ("debian-qubes", DEBIAN)):
            r = subprocess.run([sys.executable, "-I", TOOL, "packages", name], capture_output=True, text=True, timeout=60)
            check(f"{name}: the sorted list, one per line", r.returncode == 0 and r.stdout.split("\n")[:-1] == want, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-I", TOOL, "packages", "nope"], capture_output=True, text=True, timeout=60)
        check("an unknown platform: exit 2, nothing on stdout, the choices on stderr",
              r.returncode == 2 and r.stdout == "" and "unknown platform" in r.stderr and "debian-qubes" in r.stderr, r.stderr)
        r = subprocess.run([sys.executable, "-I", TOOL, "frob"], capture_output=True, text=True, timeout=60)
        check("an unknown command: usage, exit 2", r.returncode == 2 and "usage:" in r.stderr, r.stderr)
        r = subprocess.run([sys.executable, "-I", TOOL, "detect"], capture_output=True, text=True, timeout=60,
                           env={"AGENT_FABRIC_PLATFORM": "fedora-qubes", "PATH": os.environ.get("PATH", "")})
        check("detect on the command line prints the name", r.returncode == 0 and r.stdout == "fedora-qubes\n", r.stdout + r.stderr)

        print("the interpreter floor")
        check("3.13 is the floor: 3.13 and 3.14 pass, 3.12 and 3.11 do not",
              hp.host_python_ok((3, 13)) and hp.host_python_ok((3, 14)) and not hp.host_python_ok((3, 12)) and not hp.host_python_ok((3, 11)))

    print("test_host_platform:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
