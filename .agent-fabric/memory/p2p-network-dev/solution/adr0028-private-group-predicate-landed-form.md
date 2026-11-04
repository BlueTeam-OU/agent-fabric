---
role: "p2p-network-dev"
class: solution
topic: "adr0028-private-group-predicate-landed-form"
description: "ADR-0028's private-group predicate as it landed (#228, #236, #239): name equality through NSS with the process's euid, no access ACL, reads bounded at 5 s with a waiting one-outstanding gate; ADR-0028 is the authority, this is where the…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "p2p-network-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1c1c508f33ba3a28
---

## ADR-0028's private-group predicate as it landed (#228, #236, #239): name equality through NSS with the process's euid, no access ACL, reads bounded at 5 s with a waiting one-outstanding gate; ADR-0028 is the authority, this is where the code is

The rule's text is ADR-0028 (amendments "A group of one is the owner's own",
#231, and "The name-service read is bounded", #239); read it there. This
section corrects the earlier one, which recorded the 2026-10-08 draft:
"the owner" as the directory's owner and a thread that "may leak, at most
one per start". Both are wrong now.

As landed in profile-config (persist.rs `owners_private_group`, #228 and
#236):
- A group-write bit on an ancestor, a traversed link's directory, or
  config.yaml passes only when the group's name equals the user name of
  THE OWNER, defined as the account the process runs as (euid), never the
  directory's owner, and gr_mem is empty, and no
  `system.posix_acl_access` xattr is present (with an access ACL, the
  group bits are the mask). Other-write is always refused unless sticky.
  A failed or missing read refuses.
- The two NSS reads run on a helper thread under `NSS_READ_DEADLINE`
  (5 s, a constant, not a knob). At most one read is outstanding per
  process (`NSS_READ_OUTSTANDING`, a `ReadGate` behind
  `NameService::outstanding()`). A caller that finds it taken waits, on one
  budget counted from its own request, then refuses naming the earlier
  read. The deadline bounds each READ, not the operation: a walk reads
  once per group-writable component.
- Known gaps the ADR states: primary-group members and a lying name
  service are root's acts; NFSv4 ACLs are not inspected.

Not true on Android: bionic's gr_mem is never empty there, see
[[domain-bionic-gr-mem-lists-own-name]]. The general lesson is
[[a-blocking-lookup-in-a-fail-closed-check-is-fail-stuck]].

*References: a-blocking-lookup-in-a-fail-closed-check-is-fail-stuck, domain-bionic-gr-mem-lists-own-name*

*Anchors: `interweave:crates/config/profile-config/src/persist.rs::NSS_READ_OUTSTANDING`, `interweave:crates/config/profile-config/src/persist.rs::owners_private_group`*

*Observed 2026-10-25 (p2p-network-dev)*
