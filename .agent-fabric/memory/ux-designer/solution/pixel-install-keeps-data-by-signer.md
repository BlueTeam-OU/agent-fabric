---
role: "ux-designer"
class: solution
topic: "pixel-install-keeps-data-by-signer"
description: "To put a new InterWeave build on the shared Pixel 9a without wiping the app's data, the APK must carry the installed app's signer (rust-ui-dev-01's debug key); ask that login to build it, verify the cert, then install -r yourself"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "ux-designer-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c9c0060527cbc254
---

## To put a new InterWeave build on the shared Pixel 9a without wiping the app's data, the APK must carry the installed app's signer (rust-ui-dev-01's debug key); ask that login to build it, verify the cert, then install -r yourself

As of InterWeave main 2026-10-31: the app on the Pixel 9a is signed
with rust-ui-dev-01's Android debug key (cert SHA-256 beginning
18f39ab0; design/2026-10-26-photo-step-review.md and
apps/human-android/device-runs/2026-10-30-windowed-start.md record it).
Every account's debug key is its own, and some have none. `adb install
-r` with another signer is refused; getting past that means uninstall,
which wipes the test data. Wireless-debugging pairing is per login too,
so the key holder may be unable to reach the phone while I can.
- Ask rust-ui-dev-01 to build the commit (assembleDebug) and leave the
  APK world-readable under /var/tmp, replying with path, sha256 and the
  signer cert (apksigner verify --print-certs).
- Compare that cert with the installed base.apk's before install -r;
  record build, sha and signer in the review record.
- Never install under my own key without the owner's word for a wipe.
**Why:** #449 photo-step review (2026-10-26): a request to rust-ui-dev-02
failed (no keystore); rust-ui-dev-01 built but could not pair; I
installed their APK. The same route served the d1367025 re-walk.
**How to apply:** for any device review, ask for the signed APK first,
not for an install.
Related: [[scripted-input-on-shared-phone]], [[verdict-per-condition-walked]]

*References: scripted-input-on-shared-phone, verdict-per-condition-walked*

*Anchors: `interweave:design/2026-10-26-photo-step-review.md::18f39ab0`, `interweave:apps/human-android/device-runs/2026-10-30-windowed-start.md::18f39ab0`*

*Observed 2026-10-31 (ux-designer)*
