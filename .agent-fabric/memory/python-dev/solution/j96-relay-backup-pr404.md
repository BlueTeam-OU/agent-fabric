---
role: "python-dev"
class: solution
topic: "j96-relay-backup-pr404"
description: "j96 relay-db backup to Proton Drive: PR #404 state, what is carried, traps met"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6a7d0540cd53a20c
---

## j96 relay-db backup to Proton Drive: PR #404 state, what is carried, traps met

`fabric-secrets relay backup|backup --verify|restore DIR` (tools/fabric/secretstore/relaycopy.py, tools/fabric/secret_relay.py), PR #404, branch develop-qzapp/python-dev-02/feat/j96-adr-034-sec-7-step-1. Head c793aa11 reviewed (3 rounds, no P1/P2); 3 work + 3 fix; security-boundary so it arms only on the owner's word (asked by REPLY 01a17d4c to develop-qzapp/user). Open P3s carried: test label F8 (empty keyring does not reach the unverifiable-signature path), stale "-shm empty" test comment at test_secret_relay.py ~223, `_fetch` decrypt message also fires on gpg exit 2. Replay of an older signed revision is not detected (contract says so).

**Why:** the encryption key is public, so restore must require a VALIDSIG by the store key (review F2); a host with only the recovery key decrypts by hand.
**How to apply:** after the owner's word, `fabric-pr arm 404 --basis "the owner's word ..."`; then tell fabric-coordinator it merged; the owner installs the timer (proposed 6-hourly agent-fabric-relay-backup).

Traps: my mutation script ran `git checkout -- file` and wiped uncommitted fixes — commit before mutating. A hook blocked `git commit` in a command containing $HOME. sqlite `mode=ro` URI with an unquoted `?`/`#` path silently opens an empty db, so a control must read rows back. `fabric-review brief` refuses previous_findings on a PR re-review and requirements that name what was fixed.

*Anchors: `tools/fabric/secretstore/relaycopy.py::_require_signed_by_store`, `tools/fabric/secret_relay.py::main`*

*Observed 2026-10-27 (python-dev)*
