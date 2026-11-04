---
role: "python-dev"
class: solution
topic: "live-run-finds-what-fakes-miss-j132"
description: "pin kinds that run programs (rustup-init, cargo install): a proof naming an absent toolchain makes rustup download it and the proof bound kills it; CI containers have a non-reaping pid 1"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ab3b22072fe552c8
---

## pin kinds that run programs (rustup-init, cargo install): a proof naming an absent toolchain makes rustup download it and the proof bound kills it; CI containers have a non-reaping pid 1

#303 (j132) added `installer` and `cargo` pin kinds to tools/fabric/tools_install.py. Two defects only a real run or a CI container showed:

- `cargo +1.98.1 ndk --version` as a proof on an account without that toolchain makes rustup download it; the 15 s proof bound kills it halfway and leaves `toolchains/<tc>` with "missing manifest", after which `cargo install` exits 101. Fixed by `RUSTUP_AUTO_INSTALL=0` inside `tools_check.prove` (every proof), never in the install run itself, which has to download. Verified: fresh home, rustup-init 1.29.1 `--default-toolchain none`, the proof fails in 0.01 s and creates no toolchains dir.
- A test that checks a killed grandchild with `kill -0` passes locally and fails in the CI containers (pid 1 is `tail -f /dev/null`, nothing reaps, the dead child stays a zombie). Read `/proc/<pid>/stat` state and treat Z as dead. Reproduced with `podman run -d fedora tail -f /dev/null` + `podman exec -u <non-root>`; root also fails unrelated chmod tests.

**Why:** the fakes passed 7 review rounds; the first live run against the real assets and the first CI run found these.
**How to apply:** for a pin that runs a program, run the real asset in a scratch HOME before the first review, and run the new tests in a non-reaping container as a non-root user.

Other facts: `cargo install --version 4.1.2` is a caret range, pass `=4.1.2`; rustup-init must be named `rustup-init` (any other name is a proxy); a frozen oracle fixture (tests/fixtures/node-oracle-ctl-upgrade-sessions-queue.json) held tools-install's 330 s timeout and ttl: re-frozen to 1230/600 (ACTION_TTL_MAX_S caps ttl).

*Anchors: `tools/fabric/tools_check.py::RUSTUP_AUTO_INSTALL`, `tools/fabric/tools_install.py::install_cargo`*

*Observed 2026-10-18 (python-dev)*
