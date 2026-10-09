#!/usr/bin/env python3
"""runtime/provisioning/platform/qubes/ssh-operator.sh --dry-run (agent-fabric
ADR-048 §5 rules 1-3, 6): what it would write, without root and without
writing. The registry and the host are a fixture's; the staging directory
and rc.local are scratch paths, so a dry run that wrote anything shows.
Plain script: ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "runtime", "provisioning", "platform", "qubes", "ssh-operator.sh")
ME = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
HOME = os.path.expanduser("~")
OPKEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGb1y2fxD0RkCq3dHn2iN8f3mR1vD0n1QvJx2v0r2X7a"
SETTINGS = ["ListenAddress 127.0.0.1", "PasswordAuthentication no", "KbdInteractiveAuthentication no",
            "PermitRootLogin no", "AllowTcpForwarding no", "AllowStreamLocalForwarding no",
            "AllowAgentForwarding no", "X11Forwarding no", "PermitTunnel no", "GatewayPorts no",
            "AuthorizedKeysFile /etc/ssh/authorized_keys/%u"]


def dry(tmp: str, key_text: str, platform: str = "fedora-qubes") -> subprocess.CompletedProcess[str]:
    reg = os.path.join(tmp, "registry.json")
    with open(reg, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "hosts": {}, "placement": {ME: "here", "ghost-login-x": "here", "far-login": "there"}}, fh)
    pub = os.path.join(tmp, "op.pub")
    with open(pub, "w", encoding="utf-8") as fh:
        fh.write(key_text)
    env = {**os.environ, "AGENT_FABRIC_HOSTS_REGISTRY": reg, "AGENT_FABRIC_SSH_HOST": "here",
           "AGENT_FABRIC_SSH_STAGE": os.path.join(tmp, "stage"), "AGENT_FABRIC_RC_LOCAL": os.path.join(tmp, "rc.local"),
           "AGENT_FABRIC_PLATFORM": platform}
    return subprocess.run(["bash", SCRIPT, "--dry-run", pub], env=env, capture_output=True, text=True, timeout=60)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good:
            print(f"      {detail[-1500:]}")
            fails += 1

    with tempfile.TemporaryDirectory() as tmp:
        r = dry(tmp, OPKEY + " owner@deck\n")
        out = r.stdout
        check("a dry run exits 0", r.returncode == 0, r.stderr)
        for s in SETTINGS:
            check(f"the drop-in says {s}", f"    {s}\n" in out, out)
        check("AllowUsers names exactly the logins placed on this host", f"    AllowUsers ghost-login-x {ME}\n" in out, out)
        want = f'command="{HOME}/projects/agent-fabric/runtime/provisioning/moveto/enter-ssh",restrict {OPKEY}'
        check("the login's keys file forces its own checkout's enter-ssh, restricted, the comment dropped",
              f"authorized_keys/{ME} (0644):\n    {want}\n" in out, out)
        check("a placed login with no account gets no keys file, said", "ghost-login-x is placed here but has no account" in r.stderr
              and "authorized_keys/ghost-login-x" not in out, r.stderr)
        check("a login placed elsewhere is not named", "far-login" not in out)
        check("host keys are generated into the staging directory, all three types",
              all(f"-t {t} -f {tmp}/stage/host_keys/ssh_host_{t}_key" in out for t in ("ed25519", "ecdsa", "rsa")), out)
        check("the boot block is written into rc.local, marked",
              "# BEGIN agent-fabric-ssh (ADR-048)" in out and f"{tmp}/stage/restore.sh" in out, out)
        check("the operator-side keygen is printed", "ssh-keygen -t ed25519 -f ~/.ssh/fabric_deck" in out, out)
        check("a dry run writes nothing", sorted(os.listdir(tmp)) == ["op.pub", "registry.json"], str(os.listdir(tmp)))
        r = dry(tmp, OPKEY + "\n", platform="fedora")
        check("off Qubes there is no boot block", r.returncode in (0, 1) and "rc.local" not in r.stdout, r.stdout)
        for label, text in (("two keys", OPKEY + "\n" + OPKEY + "\n"), ("an options prefix", 'command="x" ' + OPKEY + "\n"),
                            ("a private key", "-----BEGIN OPENSSH PRIVATE KEY-----\n"), ("empty", "")):
            r = dry(tmp, text)
            check(f"refuses {label} as the operator key", r.returncode == 1 and "is not one ed25519 or ecdsa" in r.stderr,
                  r.stdout + r.stderr)
    print(f"\n{'all passed' if not fails else f'{fails} failed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
