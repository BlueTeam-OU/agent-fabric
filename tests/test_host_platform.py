#!/usr/bin/env python3
"""tools/fabric/provisioning/host_platform.py: the detection and the package
lists the platform/*.sh scripts held (their differential check against the
shell, 0 differences over all four platforms and the unknown one, is the
source of the literal lists below; while the shell stays for CI's bare
container and ssh-operator.sh, the last case here keeps the two together). Plain script: prints ok/FAIL, exit 1
on any failure."""
from __future__ import annotations

import os
import shutil
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
        for name in ("fedora", "fedora-qubes", "debian", "debian-qubes"):
            sh = subprocess.run(["bash", os.path.join(HERE, "runtime", "provisioning", "platform", "packages.sh"), name],
                                capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")})
            py = subprocess.run([sys.executable, "-I", TOOL, "packages", name], capture_output=True, text=True, timeout=60)
            check(f"{name}: the shell CI still asks (packages.sh, before any Python exists there) prints the same list",
                  sh.returncode == 0 and sh.stdout == py.stdout, sh.stdout + sh.stderr)
        print("packages --operator")
        sh_tool = os.path.join(HERE, "runtime", "provisioning", "platform", "packages.sh")
        stub = os.path.join(t, "bin")
        os.makedirs(stub)
        for tag, key_type, template in (("ok", "AppVM", "fedora-43-develop"), ("tmpl", "TemplateVM", "x")):
            os.makedirs(os.path.join(stub, tag))
            qdb = os.path.join(stub, tag, "qubesdb-read")
            with open(qdb, "w") as fh:
                fh.write(f'#!/bin/sh\ncase "$1" in /type) echo {key_type};; /qubes-base-template) echo {template};; *) exit 1;; esac\n')
            os.chmod(qdb, 0o755)
        empty = os.path.join(t, "empty")
        os.makedirs(empty)
        # Only what packages.sh calls, so a real qubesdb-read on the machine running the suite is not found.
        for tool in ("bash", "timeout", "sort", "awk", "tr", "dirname", "readlink", "env", "cat"):
            os.symlink(shutil.which(tool), os.path.join(empty, tool))

        def both(args: list[str], path: str) -> tuple[subprocess.CompletedProcess, subprocess.CompletedProcess]:
            env = {"PATH": f"{path}:{empty}"}
            return (subprocess.run(["bash", sh_tool, "--operator", *args], capture_output=True, text=True, timeout=60, env=env),
                    subprocess.run([sys.executable, "-I", TOOL, "packages", "--operator", *args], capture_output=True, text=True,
                                   timeout=60, env=env))
        for name, want, cmd in (("fedora", FEDORA, "sudo dnf install -y"), ("debian", DEBIAN, "sudo apt-get install -y")):
            sh, py = both([name], empty)
            line = f"{cmd} {' '.join(want)} kitty\n"
            check(f"{name}: one line, the install command, the host list, then the operator's (shell and Python agree)",
                  sh.stdout == line and py.stdout == line and sh.returncode == py.returncode == 0 and sh.stderr == py.stderr == "",
                  sh.stdout + sh.stderr + py.stdout + py.stderr)
        sh, py = both(["fedora-qubes"], os.path.join(stub, "ok"))
        want = ("In the TemplateVM fedora-43-develop (Qubes menu: fedora-43-develop > Terminal), paste once, then shut it down "
                f"and restart this qube:\n  sudo dnf install -y {' '.join(FEDORA)} kitty\n")
        check("an AppVM: the TemplateVM named, the line under it", sh.stdout == want and py.stdout == want, sh.stdout + py.stdout + sh.stderr)
        sh, py = both(["debian-qubes"], os.path.join(stub, "tmpl"))
        line = f"sudo apt-get install -y {' '.join(DEBIAN)} kitty\n"
        check("a Qubes platform that is not an AppVM, or whose template cannot be read: the line alone, said on stderr",
              sh.stdout == line == py.stdout and "no TemplateVM name" in sh.stderr and "no TemplateVM name" in py.stderr,
              sh.stdout + sh.stderr + py.stderr)
        sh, py = both(["fedora-qubes"], empty)
        check("…the same with qubesdb-read absent",
              sh.stdout.endswith(" kitty\n") and sh.stdout.count("\n") == 1 and sh.stdout == py.stdout and sh.returncode == py.returncode == 0,
              sh.stdout + sh.stderr)
        sh, py = both(["nope"], empty)
        check("an unknown platform under --operator: exit 2, nothing on stdout",
              sh.returncode == py.returncode == 2 and sh.stdout == py.stdout == "")
        default = subprocess.run([sys.executable, "-I", TOOL, "packages", "fedora"], capture_output=True, text=True, timeout=60)
        check("without --operator the output is unchanged: no kitty, one package per line",
              "kitty" not in default.stdout and default.stdout.split("\n")[:-1] == FEDORA)
        check("the operator list is not the host contract (CI installs the host list whole)",
              "kitty" not in hp.FABRIC_HOST_TOOLS and hp.FABRIC_OPERATOR_TOOLS == ("kitty",)
              and hp.operator_packages(hp.profile("fedora")) == ["kitty"] and hp.operator_packages(hp.profile("debian-qubes")) == ["kitty"])
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
