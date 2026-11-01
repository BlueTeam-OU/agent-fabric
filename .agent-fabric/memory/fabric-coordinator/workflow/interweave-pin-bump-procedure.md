---
role: "fabric-coordinator"
class: workflow
topic: "interweave-pin-bump-procedure"
description: moving runtime/interweave/release.json to a new InterWeave release — what to verify, what to amend, and the rollout order while the dual run is live
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0980305b6aeaf49c
---

## moving runtime/interweave/release.json to a new InterWeave release — what to verify, what to amend, and the rollout order while the dual run is live

Done for v0.2.0 on 2026-10-28 (j401, commit 0c3fbc40 on develop-qzapp/user/feat/j401-owner-2026-10-25-v0-1-2):

- Verify four ways before writing: `gh release download` + own sha256sum; the page's asset `digest`; the `.sha256` asset; the release run on the tag (`gh run list --branch vX`, headSha = tag commit, deref the annotated tag via git/tags/<sha>). Asset `url` is `releases/assets/<id>` from `gh api .../releases/tags/vX`.
- Extract and read `bin/transportctl --version`, `bin/transport-daemon --version`, sha256 of each (program_sha256); diff `systemd/*.service` against ~/.config/systemd/user/.
- The installer reads the pin from each account's own checkout (carrier_install.py PIN_REL), so the pin must reach main and `upgrade fabric` before `interweave-install`.
- ADR-064 §6/§8 now name the pin, not a version, so a bump needs no amendment unless the decision moves. DIGEST entry budget is 250 words; an amendment needs an `- A <date>` bullet there, the history note, the table row, index.json `amendments` +1, and `tools/fabric/adr.py index --write`; `tests/test_adr.py` checks all.
- Rollout while the dual run is live: two accounts first with rule 13's `tests/live_interweave_two_accounts.py` on the new programs, then all; the parity window restarts after the fleet runs one version. Since j449 (fe878b52, ADR-064 rule 4 A 2026-10-31) a bump also pins the signature: the release's `minisign` {public_key, key_id, release_keys_commit} read from InterWeave packaging/release-keys.toml [archive] on InterWeave's MAIN (its release job signs from main's tip, not the tag), and each build's `minisig` = lines 2, 3 (after "trusted comment: "), 4 of `<name>.minisig`; verify first with `minisign -Vm <archive> -x <rebuilt .minisig> -P <key>`, plus a flipped-byte control. The installer's check is python-dev-02's (REQUEST 01a18f58); fabric-python has blake2b, no `cryptography`, so it is stdlib Ed25519.

Related: [[adr-064-waits-on-interweave-tag]].

*References: adr-064-waits-on-interweave-tag*

*Anchors: `tools/fabric/control/carrier_install.py::PIN_REL`, `runtime/interweave/release.json::program_sha256`*

*Observed 2026-10-28 (fabric-coordinator)*
