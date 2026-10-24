---
role: "rust-ui-dev"
class: domain
topic: "android-device-credential-prompt"
description: Android BiometricPrompt with DEVICE_CREDENTIAL on API 30 has no Cancel button; leaving for Recents arrives as onError 10; FLAG_SECURE blocks screencap
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - 67e84daade0fc07f
---

## Android BiometricPrompt with DEVICE_CREDENTIAL on API 30 has no Cancel button; leaving for Recents arrives as onError 10; FLAG_SECURE blocks screencap

Measured on a Samsung A40 (API 30), 2026-10-20, on InterWeave #313's unlock prompt:
- With the `DEVICE_CREDENTIAL` authenticator the prompt shows no Cancel button; Back cancels it.
- Leaving for Recents while it shows arrives as `onAuthenticationError` code 10 (user canceled); handle it as a cancel.
- A window with `FLAG_SECURE` set makes `adb shell screencap` capture black, so device evidence of a secured screen is read by a person at the phone.
- Android 12's behaviour-changes page (read 2026-10-19) says `allowBackup=false` does not stop device-to-device transfer on some manufacturers' devices; only `dataExtractionRules` excluding everything does.

Related: [[a40-own-adb-server]] [[device-review-run-method]]

*References: a40-own-adb-server, device-review-run-method*

*Observed 2026-10-24 (rust-ui-dev)*
