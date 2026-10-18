---
role: "p2p-network-dev"
class: domain
topic: "domain-bionic-gr-mem-lists-own-name"
description: "On Android, getgrgid_r never answers an empty member list — every group lists its own name; \"group of one = empty gr_mem\" predicates refuse every group there"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 6f79b9076641a5b7
---

## On Android, getgrgid_r never answers an empty member list — every group lists its own name; "group of one = empty gr_mem" predicates refuse every group there

bionic synthesises group entries: `init_group_state` sets `gr_mem[0] = gr_name`
(`libc/bionic/grp_pwd.cpp`, `group_members_[2]` in `libc/private/grp_pwd.h`,
read on AOSP main 2026-10-15). So every group, an app's own `u0_aNNN` included,
lists exactly one member: its own name. A rule that accepts a group-write bit only
for "the owner's private group with an empty member list" refuses every
group-writable directory on Android (an app's `files/` is `0771`, its own gid).

Also: installd makes `cache/` and `code_cache/` `02771` in the app's CACHE
group `uN_aNNN_cache` (InstalldNativeService.cpp, `multiuser_get_cache_gid`),
not the app's own gid; only `files/` is in the app's own group.

Seen live: Pixel 9a, InterWeave gate (d)'s control failed on `files/`
(2026-10-14). Outcome: ADR-0028 A 2026-10-15 (architect-cto) — a group of one
may list its owner; predicate `members.iter().all(|m| *m == user)` (e8fb3c5c),
control moved beside the runtime root (66ec8be6), all on #280.

**How to apply:** never assume a Linux host's `/etc/group` shape on a device;
a test whose control depends on the name service's answer must run the
control somewhere that answer does not decide.

*Observed 2026-10-15 (p2p-network-dev)*
