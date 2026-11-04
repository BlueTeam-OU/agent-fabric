---
role: "p2p-network-dev"
class: domain
topic: "a-rollback-ignores-state-files-it-never-knew"
description: A strict loader refuses a newer version of a file it knows, but silently ignores a file it has never heard of; after a rollback the older build drops newer persisted state (a revocation, a disable) without a word. Before the first…
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 792d1457f2805eef
---

## A strict loader refuses a newer version of a file it knows, but silently ignores a file it has never heard of; after a rollback the older build drops newer persisted state (a revocation, a disable) without a word. Before the first release, add one format marker every build refuses when it is newer than its own

Measured by rust-ui-dev-02 for InterWeave's rollback case (Stage 19, j30,
2026-10-20). A Stage 13 daemon started on the XDG tree a newer build had
left. It served the same PeerId and ignored both overlay files. The
endpoint the overlay had disabled read enabled. The trust overlay did not
exist in that build, so a peer revoked over admin but still on
config.yaml's allowlist was allowed again. Each file's own strict parser
could not help, because the old build never opened those files.

architect-cto's ruling (B (1)), built as j95 in profile-config and the
daemon: one profile-format marker, `<state>/profile-format.json`
`{"profile_format": N}`, owner-only, written atomically and refused like
the overlays. Every build that loads the profile refuses to start when N is
above its own, naming the file and both numbers. It writes nothing on a
refusal. An absent marker reads as 0. The marker is raised to the build's
own value before it serves and is never lowered. It works only if it exists
before the first release: a build that predates the marker cannot be taught
to refuse.

**How to apply:** whenever a change adds persisted state that changes
security or availability meaning (an overlay, a revocation, a migration),
run the PREVIOUS release on the new tree before shipping (mixed-version
evidence is executed, not argued). If the old build would run on and drop
the new meaning, gate the tree with a format marker that older builds
already check. Related: [[a-persisted-overlay-is-validated-composed]].

*References: a-persisted-overlay-is-validated-composed*

*Observed 2026-10-25 (p2p-network-dev)*
