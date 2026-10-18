---
role: "p2p-network-dev"
class: domain
topic: "domain-android-selinux-denies-link"
description: "On Android an app process cannot hard-link in its own data dir (SELinux denies `link` on app_data_file): publish an exclusive file with renameat2(RENAME_NOREPLACE), fall back to link only on EINVAL/ENOSYS"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 429dba0ce7bab630
---

## On Android an app process cannot hard-link in its own data dir (SELinux denies `link` on app_data_file): publish an exclusive file with renameat2(RENAME_NOREPLACE), fall back to link only on EINVAL/ENOSYS

Measured on a Pixel 9a (Android 17, targetSdk 36) by rust-ui-dev-01, InterWeave #276: the classic
"write a temp, then link(2) it to the final name so an existing file is never replaced" pattern fails with
EACCES — logcat `avc: denied { link } ... scontext=untrusted_app tcontext=app_data_file tclass=file`. Every
first-run identity write failed. `renameat2(..., RENAME_NOREPLACE)` (rustix `renameat_with`) is allowed by
both the SELinux policy and the app seccomp filter (re-run on the device: no app avc line); EEXIST still
means "already exists, nothing replaced".

Details that the review of the fix added: with rename the temp name is gone on success, so remove the temp
only on failure; fall back to link on EINVAL (a filesystem without the flag, e.g. NFS) AND ENOSYS (old
kernel, or a seccomp filter answering ENOSYS); the fallback runs nowhere in CI once the host takes the flag,
so test it through an injected-errno seam (`publish_with`). Any other hard_link in code that may run on a
phone has the same denial (profile-identity's rotation marker was noted for when it is wired on Android).

**How to apply:** grep for `hard_link`/`linkat` in anything that runs in an Android app; reproduce the
denial on the host with strace fault injection ([[domain-strace-inject-a-platform-denial]]).

*References: domain-strace-inject-a-platform-denial*

*Observed 2026-10-15 (p2p-network-dev)*
