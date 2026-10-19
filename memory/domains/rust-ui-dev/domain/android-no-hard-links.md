---
role: "rust-ui-dev"
class: domain
topic: "android-no-hard-links"
description: "Android app processes cannot link(2) in their data dir (SELinux untrusted_app), so any create-via-hard-link persistence fails with EACCES on a phone and passes on the host"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 7b2e88bbac76b614
---

## Android app processes cannot link(2) in their data dir (SELinux untrusted_app), so any create-via-hard-link persistence fails with EACCES on a phone and passes on the host

On Android (measured on a Pixel 9a, Android 17, targetSdk 36, 2026-10-14) SELinux denies `link` on app_data_file to untrusted_app. link(2) returns EACCES (os error 13), and logcat shows `avc: denied { link } ... tclass=file permissive=0`. Host tests on ext4/tmpfs cannot see this. Any no-replace publish built on hard_link (InterWeave profile-config persist.rs create_private_exclusive*) breaks first-run provisioning on a phone. Check a new persistence primitive on the device, or with an avc grep, before treating host tests as evidence for Android.

Related: [[j66-android-e2e-seam]] [[android-shell-build]]

*References: android-shell-build, j66-android-e2e-seam*

*Observed 2026-10-14 (rust-ui-dev)*
