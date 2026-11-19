---
role: "fabric-coordinator"
class: workflow
topic: "interweave-pin-bump-procedure"
description: moving runtime/interweave/release.json to a new InterWeave release — what to verify, what to amend, and the rollout order while the dual run is live
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0980305b6aeaf49c
  - c08167ee76ab8a96
---

## moving runtime/interweave/release.json to a new InterWeave release — what to verify, what to amend, and the rollout order while the dual run is live

Done for v0.2.0 on 2026-10-28 (j401, commit 0c3fbc40 on develop-qzapp/user/feat/j401-owner-2026-10-25-v0-1-2):

- Verify four ways before writing: `gh release download` + own sha256sum; the page's asset `digest`; the `.sha256` asset; the release run on the tag (`gh run list --branch vX`, headSha = tag commit, deref the annotated tag via git/tags/<sha>). Asset `url` is `releases/assets/<id>` from `gh api .../releases/tags/vX`.
- Extract and read `bin/transportctl --version`, `bin/transport-daemon --version`, sha256 of each (program_sha256); diff `systemd/*.service` against ~/.config/systemd/user/.
- The installer reads the pin from each account's own checkout (carrier_install.py PIN_REL), so the pin must reach main and `upgrade fabric` before `interweave-install`.
- ADR-064 §6/§8 now name the pin, not a version, so a bump needs no amendment unless the decision moves. DIGEST entry budget is 250 words; an amendment needs an `- A <date>` bullet there, the history note, the table row, index.json `amendments` +1, and `tools/fabric/adr.py index --write`; `tests/test_adr.py` checks all.
- Rollout while the dual run is live: two accounts first with rule 13's `tests/live_interweave_two_accounts.py` on the new programs, then all; the parity window restarts after the fleet runs one version. Since j449 (fe878b52, ADR-064 rule 4 A 2026-10-31) a bump also pins the signature: the release's `minisign` {public_key, key_id, release_keys_commit} read from InterWeave packaging/release-keys.toml [archive] on InterWeave's MAIN (its release job signs from main's tip, not the tag), and each build's `minisig` = lines 2, 3 (after "trusted comment: "), 4 of `<name>.minisig`; verify first with `minisign -Vm <archive> -x <rebuilt .minisig> -P <key>`, plus a flipped-byte control. The installer's check is python-dev-02's (REQUEST 01a18f58); fabric-python has blake2b, no `cryptography`, so it is stdlib Ed25519.

v0.3.0, 2026-11-14 (j817, c44fae2b on PR #595): archive key unchanged but packaging/release-keys.toml moved on InterWeave main (00eb473f rotated the TAG key, ADR-0066) — release_keys_commit is the file's latest commit on main, read with `gh api "repos/.../commits?path=packaging/release-keys.toml&sha=main"`. tests/test_control_carrier_install.py RealPin named "0.2.0" and failed the bump; it now reads `current` (mutation: current=0.1.0 fails 2 tests). Also run the installer's own check: `PYTHONPATH=tools/fabric` + `control.minisign.verify_file(archive, key, minisig, name)` with a wrong-name control. pytest is not in fabric-python: `fabric-python -m unittest tests.<mod>`. Release notes' BREAKING (human-client store schema) does not touch transportctl/daemon; read them anyway.

Rollout 0.3.0 done 2026-11-14 ~03:15Z: #595 merged, upgrade fabric to 30, install on python-dev-02/03, rule 13 by both (REQUESTs 01a1d7c8-d4fa…, -d59a…; J92_RUN 1794621623186, all phases OK, files in a host scratch path), then `fabric-ctl all interweave-install` at load ~7: 30/30 ok, pinned, channel ok, no retry. That install outlives a 600 s foreground call: run it in the background. After the pin reaches main and BEFORE the install, `fabric-ctl all interweave` shows channel "off" on every account: read_channel compares the daemon's version to the pin, so it is a version mismatch, not a dead carrier (gzcoord-carrier status still ok). Control link read-back: `fabric-ctl all status` prints "relay only: user" = the operator, by design; 29 by InterWeave. The python-devs had no command for the control link's own check: that read-back is mine.

Related: [[adr-064-waits-on-interweave-tag]].

*References: adr-064-waits-on-interweave-tag*

*Anchors: `tools/fabric/control/carrier_install.py::PIN_REL`, `runtime/interweave/release.json::program_sha256`*

*Observed 2026-11-14 (fabric-coordinator)*
