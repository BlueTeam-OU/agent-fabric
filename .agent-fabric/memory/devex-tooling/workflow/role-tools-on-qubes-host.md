---
role: "devex-tooling"
class: workflow
topic: "role-tools-on-qubes-host"
description: "how a role's extra host tools (not the fabric's host contract) get onto develop-qzapp, and who has to run the install"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
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
  checking its sha256 first. The script belongs somewhere root can read: a role home is 0700,
  which root can still read, but never put it in world-writable /tmp.
- Third-party Python modules go into the system python3, never fabric-python, which stays
  stdlib-only.
- `dnf repoquery` as a role account needs `--disablerepo='qubes*'`, because the Qubes repo's
  GPG key import prompts and fails.
- FABRIC_HOST_TOOLS in runtime/provisioning/platform/detect.sh is the fabric's own contract,
  and CI installs the whole list, so a role's tools never go in it. fabric-coordinator decided
  (REPLY 01a1402b, 2026-10-15) that the per-role list is identities/roles/<role>/host-tools.json
  (schema identities/schemas/host-tools.schema.json, both fabric-coordinator's), read by
  python-dev's `packages.sh --role <slug>` plus a script for the root install of the binaries.
  A role's entry is supplied as message text, never a commit (fenced path); brand-comms'
  went as REPLY 01a1402c (seq 222760). Check origin/main for whether it has landed.

**Why:** a role account cannot run dnf or write to /usr/local, so these installs need the owner.

**How to apply:** verify everything as your own login in the scratchpad (download, checksum,
smoke run, a mutation with a wrong sha), then give the owner the one dnf line plus one
`sudo bash` line.

*Anchors: `runtime/provisioning/platform/fedora-qubes.sh::PERSISTS_ACROSS_REBOOT=0`, `runtime/provisioning/platform/detect.sh::FABRIC_HOST_TOOLS`*

*Observed 2026-10-15 (devex-tooling)*
