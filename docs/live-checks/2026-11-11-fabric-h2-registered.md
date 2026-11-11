# 2026-11-11: fabric-h2, the second host, answers through hostexec's ssh backend

**Why.** ADR-010 rule 5 registers a host by three things: an entry, a check, and one live read-back. ADR-010 §7 says the ssh backend of hostexec had never been read back on a real second host. The owner made one in job j706 (REQUEST 01a1c063 from architect-cto-01, plan `docs/proposals/j422-control-plane-on-interweave-cli.md` §3.2). It is VM 101 `fabric-h2` on the Proxmox node s13337. devex-tooling created it through the PVE API (its job j320), and the owner installed AlmaLinux 10.2 (x86_64_v2) on its console. s13337 itself is not a fabric host, and nobody has ssh to it.

**What the owner decided for it (2026-11-11, in the coordinator's session).**
- No overlay. develop-qzapp reaches fabric-h2 directly over the LAN and its VPN. This replaces the plan's WireGuard (§3.1).
- The platform id is `almalinux`, os-release's ID.
- For P2 only, two gates are waived: ADR-034 §7 step 3's held bound and P1's control parity report.
- The coordinator's key went on `op` by `ssh-copy-id`, typed by the owner with `op`'s password. devex-tooling could not do it: the guest's qemu-ga ships with guest-exec and guest-file-* disabled (EL's default blocklist), and that stays as shipped.

**Measured from develop-qzapp, 2026-11-11.**

| what | how | result |
|---|---|---|
| reachability | `ssh-keyscan 192.168.200.79` | OpenSSH 9.9; three host keys |
| host-key pin | the scan, devex-tooling's own scan (j320), and `/etc/ssh/ssh_host_*_key.pub` read as `op` over the session that key authenticated | all three agree; ED25519 `SHA256:xtZRtO2afGSaZqid5t1gqNjktOr914j9OHcgdx3aZ64`, ECDSA `SHA256:s+IAqOTIwkTlz4cIxpe2olbsAaoQCDzsnflCDYRc5Xc`, RSA `SHA256:yMmap7y07ARgNAtfeHjLxJDzPVorekEq3h6inTb7kYU` |
| the pin, on the host | `fabric-ssh-hosts check fabric-h2`, run on fabric-h2 against this branch's registry | `match` |
| the operator | `id` as `op` | uid 1000, groups `op`, `wheel`. sudo first asked for a password. On the owner's word `/etc/sudoers.d/agent-fabric-op` (`op ALL=(ALL) NOPASSWD: ALL`, `root:root 0440`, `visudo -c` passed) was installed by the owner, and `sudo -n true` over `fabric-host fabric-h2 run` then succeeded |
| the address | `ip -4 addr` | `192.168.200.79/24` on ens18, DHCP; the owner reserved it in OPNsense for MAC `BC:24:11:BA:13:FA` (2026-11-11, not read back from OPNsense) |
| the source H2 sees | `$SSH_CONNECTION` | `10.10.10.3`, develop-qzapp's VPN address as the LAN sees it |
| the way back | a TCP connect from fabric-h2 to `10.10.10.3:22` and `10.137.0.30:22` | both closed: H2 cannot open a connection to develop-qzapp |
| clock | `timedatectl show -p NTPSynchronized` | `yes` |
| the check | `fabric-host fabric-h2 check`, `AGENT_FABRIC_HOSTS_REGISTRY` at this branch's registry | `host fabric-h2: answers as fabric-h2`, exit 0 |
| a command as the operator | `fabric-host fabric-h2 run -- …` | `op`; `Python 3.14.9` (the pin, installed by `python_pin.py install`); the checkout at `e124a0f2` |

The control for the check is the same call before the entry existed: `hostexec: unknown host 'fabric-h2'`, exit 1.

**What it decides.**
- The `fabric-h2` entry lands with `ssh: op@192.168.200.79` and `sshd` pinning the three keys.
- ADR-010 §7's "the ssh backend never read back" is answered.

**What it does not decide.**
- The way back is closed. Anything that needs H2 to open a connection to develop-qzapp is not possible as the network stands; an InterWeave dial from H2 is the case in point.
- No account is placed on fabric-h2.
- sshd there is AlmaLinux's own, with no agent-fabric drop-in, and it still accepts passwords.
- The provisioning profile for almalinux is python-dev-02's #554. AlmaLinux's python3 is 3.12, below the 3.13 floor, so no account goes there until the hooks that still run on the host's python3 run on the pin (ADR-040 rule 1, A 2026-11-11).
