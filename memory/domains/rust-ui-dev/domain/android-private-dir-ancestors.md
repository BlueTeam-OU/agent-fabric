---
role: "rust-ui-dev"
class: domain
topic: "android-private-dir-ancestors"
description: "Owner-only directory checks on Android -- /data is 0771 system and files/ is 0771 app-gid, so the ancestor walk needs a platform trust boundary"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 56a48e0bd558827a
---

## Owner-only directory checks on Android -- /data is 0771 system and files/ is 0771 app-gid, so the ancestor walk needs a platform trust boundary

A "private directory" rule that walks every ancestor to / (owned by root or us, no group or
other write) refuses every app-private directory on Android: AOSP's init.rc makes /data and
/data/data system:system 0771. And ContextImpl creates files/, cache/ and code_cache/ at 0771
with the app's own gid. So:
- the walk stops at a trust boundary the platform reports (the app's data dir from Context),
  never a hard-coded /data/data/<pkg>; above it the platform and SELinux own the layout;
- compare the boundary canonically: the platform reports /data/user/0/<pkg>, a link to
  /data/data/<pkg>;
- keep the app's private directories DIRECTLY under the data dir, created 0700 by the app,
  never under cache/ (and not under files/, whose acceptance depends on the group rule
  below); chmodding a platform directory was rejected (the platform may restore it).
SELinux in app data also denies link(2) (untrusted_app on app_data_file): a hard-link
"create exclusive" publish works on the host and fails EACCES on phones. renameat2 with
RENAME_NOREPLACE keeps the never-replace rule and is allowed by both the policy and the app
seccomp filter (verified on Android 17).

bionic's getgrgid_r lists an app group's own name as its single member, so a rule
"group-writable only if the group has no members" refuses the app's own group. The rule was
amended to accept a member list that is empty or names only the owner; with it files/ (0771,
the app's own group) passes, while cache/ and code_cache/ (the app's cache group) stay
refused. Check what libc actually answers on the device before writing a group predicate.

*Observed 2026-10-15 (rust-ui-dev)*
