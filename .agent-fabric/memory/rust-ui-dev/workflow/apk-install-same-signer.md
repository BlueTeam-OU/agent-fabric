---
role: "rust-ui-dev"
class: workflow
topic: "apk-install-same-signer"
description: "Updating the shared test phone's app without wiping its data, or the phone does not answer adb -- install -r keeps data only under the same signing cert; prove data kept by firstInstallTime; triage an unreachable phone by ping, then port…"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a29617f0eeb3d39b
  - b9020eba6982c45b
---

## Updating the shared test phone's app without wiping its data, or the phone does not answer adb -- install -r keeps data only under the same signing cert; prove data kept by firstInstallTime; triage an unreachable phone by ping, then port, then pairing

- `adb install -r` keeps the app's data only when the APK is signed with the cert already
  installed. Under another key the install fails with a signature mismatch, and the only way
  past that (uninstall) wipes the data. Each login's debug keystore is its own, and a login
  can have none. So the login whose key signed the installed app builds every update.
- Who installs does not matter, only who signed. When the phone refuses my login's adb (lost
  pairing), build the APK anyway and hand it over: a world-readable path (dir 0755, file 0644
  under /var/tmp/<job>-<commit>/, with a copy in home because /var/tmp gets wiped), the
  commit, the sha256, and the signer cert SHA-256 from `apksigner verify --print-certs`. The
  installer compares that cert with the installed one, from `adb shell pm path <pkg>`, then a
  pulled base.apk, then `apksigner verify --print-certs`, before running install -r.
- A pairing control: when my connect fails at an address, another login's connect at the
  same address tells "this login's pairing is lost" apart from "the address or port moved".
  The phone's DHCP address moved on each reboot, and the Wireless debugging port changes
  per pairing.
- Before replacing a build someone else installed, tell them which commit replaces it, and
  whether it carries theirs.
- Unreachable phone, triage before asking the owner (seen four times, 2026-10-27..31):
  no ping answer = the phone is asleep or off the Wi-Fi; ping answers but the port refuses
  (a full TCP scan finds nothing) = Wireless debugging is off, or toggled to a new port;
  port accepts but `adb connect` says "failed to connect" = this login's key is not paired.
  mDNS does not reach this host, so an empty `adb mdns services` proves nothing. Each case
  is the owner's step: ask fabric-coordinator for the address:port the phone's screen shows,
  name the check that failed, and have the pairing done in the asker's own session.
- Proof for the run record, every install: the commit built (the host side of a device case
  is built at the same commit as the APK), each APK's sha256, the signer digest from
  `dumpsys package <pkg>` beside the APK's cert, and firstInstallTime unchanged -- that,
  not "Success", shows the data was kept.
Related: [[release-phone-after-testing]] (project slice: phone-run, how a lost pairing looks).

*References: release-phone-after-testing*

*Observed 2026-10-31 (rust-ui-dev)*
