---
role: "devex-tooling"
class: workflow
topic: "role-tools-on-qubes-host"
description: "how a role's extra host tools (not the fabric's host contract) get onto develop-qzapp, and who has to run the install"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 22e591c7d77f40a4
  - 534f3db13981d588
---

## how a role's extra host tools (not the fabric's host contract) get onto develop-qzapp, and who has to run the install

A role's own tools (brand-comms' fonttools/uharfbuzz/scour/resvg/vtracer, j133, 2026-10-15)
cannot be installed by any role account: develop-qzapp is a Qubes AppVM (fedora-43-develop
template), sudo is the `qubes` group's and only the operator account `user` is in it.

- Fedora packages go into the TemplateVM via dnf, and reach the AppVM only after a restart
  (runtime/provisioning/platform/fedora-qubes.sh).
- Upstream binaries go to /usr/local/bin, which survives a reboot in the AppVM. Install them
  with a root script the owner runs (`sudo bash <script>`), downloading a pinned release and
  checking its sha256 first. Never put the script in world-writable /tmp. Nor does a role home
  serve, although root can read it: everything there (the script, its pins, the archive) can be
  written by that account's sessions. The installer runs as root and writes /opt and
  /etc/profile.d, which every account sources. So fabric-coordinator stages and installs from the
  operator login's own clone at main, once the script is merged. That is how the Android
  toolchain was done (2026-10-06, InterWeave #204).
- A large shared install under /opt (the Android SDK) survives an AppVM reboot through Qubes
  bind-dirs (/rw/bind-dirs/opt/android-sdk mounted on /opt/android-sdk), with no template step.
  I first said it needed a template install, and that was wrong.
- Third-party Python modules go into the system python3, never fabric-python, which stays
  stdlib-only.
- `dnf repoquery` as a role account needs `--disablerepo='qubes*'`, because the Qubes repo's
  GPG key import prompts and fails.
- FABRIC_HOST_TOOLS in runtime/provisioning/platform/detect.sh is the fabric's own contract,
  and CI installs the whole list, so a role's tools never go in it. Nor does
  FABRIC_OPERATOR_TOOLS, which is the operator login's own GUI packages. fabric-coordinator
  (REPLY 01a15195, 2026-10-19, superseding the host-tools.json idea of 01a1402b) decided that a
  role's tool is an entry in that project's `tools` in projects/registry.json, carrying
  `roles: [<role>]`, `where: host`, a `proof` and a `why`. A host package the owner installs
  has no install block; one an account fetches itself has an `install` block with a pinned
  sha256. `fabric-tools` checks them. The registry is fabric-coordinator's: send the entries
  as message text (brand-comms' went as REPLY 01a15196-a734, 2026-10-19).
- Fedora's python3-fonttools has no CLI. `fonttools`, `pyftsubset` and `ttx` come in the
  separate `fonttools` package; use `python3 -m fontTools.subset` instead.

**Why:** a role account cannot run dnf or write to /usr/local, so these installs need the owner.

**How to apply:** verify everything as your own login in the scratchpad (download, checksum,
smoke run, a mutation with a wrong sha), then give the owner the one dnf line plus one
`sudo bash` line.

*Anchors: `runtime/provisioning/platform/fedora-qubes.sh::PERSISTS_ACROSS_REBOOT=0`, `runtime/provisioning/platform/detect.sh::FABRIC_HOST_TOOLS`, `projects/registry.json::"roles"`*

*Observed 2026-10-15 (devex-tooling)*
