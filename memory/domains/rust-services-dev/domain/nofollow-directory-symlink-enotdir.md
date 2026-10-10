---
role: "rust-services-dev"
class: domain
topic: "nofollow-directory-symlink-enotdir"
description: "openat(O_DIRECTORY|O_NOFOLLOW) on a symlink fails ENOTDIR on Linux, not ELOOP; classify with fstatat"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-services-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric-gateway"
    working_copy: "agent-fabric-gateway"
derived_from:
  - 3975cae7b7c7462e
---

## openat(O_DIRECTORY|O_NOFOLLOW) on a symlink fails ENOTDIR on Linux, not ELOOP; classify with fstatat

On Linux, `openat(dir, name, O_RDONLY|O_DIRECTORY|O_NOFOLLOW)` where `name` is a symlink to a directory
fails with ENOTDIR (the O_DIRECTORY check wins), not ELOOP; without O_DIRECTORY it is ELOOP. Both refuse,
so security holds, but an error that names "symlink" must look again: `statat(dir, name,
AT_SYMLINK_NOFOLLOW)` only to classify. Seen building ADR-005 rule 19's token-file walk
(agent-fabric-gateway a0bb550, `token_file.rs` `open_error`). Also: an O_PATH descriptor cannot
`fgetxattr`, so a walk that checks ACLs on descriptors opens directories O_RDONLY (needs read on each).
Tests can set POSIX ACLs without setfacl by writing `system.posix_acl_access`/`_default` xattrs
(version u32 LE = 2, then tag u16, perm u16, id u32 entries) with `fsetxattr`.

*Observed 2026-10-08 (rust-services-dev)*
