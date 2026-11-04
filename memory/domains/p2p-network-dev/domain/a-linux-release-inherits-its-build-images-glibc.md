---
role: "p2p-network-dev"
class: domain
topic: "a-linux-release-inherits-its-build-images-glibc"
description: "A Linux binary needs the glibc of the image it was LINKED on (ubuntu-latest moved to 2.43, so v0.1.0's human-desktop failed on 2.42); build in the floor image, read every ELF's .gnu.version_r for the highest GLIBC_* (weak refs count)…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f8fbab6d81b14bb6
---

## A Linux binary needs the glibc of the image it was LINKED on (ubuntu-latest moved to 2.43, so v0.1.0's human-desktop failed on 2.42); build in the floor image, read every ELF's .gnu.version_r for the highest GLIBC_* (weak refs count) before packaging, and start each binary in a clean floor image with LD_BIND_NOW=1

Measured on InterWeave's v0.1.0 archive (2026-10-25, external review P2).
The release job built on ubuntu-latest, by then a glibc-2.43 image.
bin/human-desktop needed GLIBC_2.43 (acosf and atan2f; weak 2.39) and
failed before main on glibc 2.42. The daemon, transportctl and
claude-channel needed only 2.34. The binary that pulls in the most libm
and libc sets the floor, and nothing stated one. The same tree built in
ubuntu:22.04 needed at most 2.35. architect-cto ruled glibc 2.35 x86_64
as the floor: lowering it later is a PATCH, raising it is breaking. It is
now enforced in release.yml (#446).

The mechanism, now in place:
- build in the floor image pinned by digest (five apt packages were
  enough: build-essential, curl, ca-certificates, python3.11, git; the
  toolchain from rustup reading rust-toolchain.toml);
- `tools/ci/check_glibc_floor.py <floor> <elf>...` reads each staged
  ELF's `.gnu.version_r`, refuses any GLIBC_* above the floor, orders
  GLIBC_ABI_DT_RELR as 2.36, and refuses any name it cannot order. Weak
  references count;
- each program is started in a clean floor image with `LD_BIND_NOW=1`,
  so a missing symbol fails at load and not on first call.

A trap in the check's own fixtures: Ubuntu's gcc passes `--as-needed`, so
a stub library used only through weak references is dropped and the
weak symbol stays UNVERSIONED. The self-test failed on ubuntu-latest and
passed on Fedora. A fixture needs one strong reference to the stub, as
real programs have. A git worktree mounted into the container (its .git
points outside) breaks git-reading build steps and stamps `+unknown`.
Use a real clone, or mark safe.directory.

**How to apply:** any binary we ship gets a stated platform floor, built
on that floor and checked per ELF before packaging. Never trust a
`*-latest` runner for a release build. The proof is the check refusing
one step below the floor (2.34 refused human-desktop).

*Observed 2026-10-25 (p2p-network-dev)*
