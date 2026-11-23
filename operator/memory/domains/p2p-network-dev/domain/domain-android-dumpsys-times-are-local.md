---
role: "p2p-network-dev"
class: domain
topic: "domain-android-dumpsys-times-are-local"
description: "dumpsys package firstInstallTime/lastUpdateTime print the phone's LOCAL zone, not UTC; read the zone before calling an install foreign"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 251ff09cd90636d8
---

## dumpsys package firstInstallTime/lastUpdateTime print the phone's LOCAL zone, not UTC; read the zone before calling an install foreign

`dumpsys package <pkg>` prints firstInstallTime/lastUpdateTime in the phone's local time zone
(`getprop persist.sys.timezone`; the shared Pixel 9a is Europe/Rome, UTC+1). On 2026-11-15 (j110) I read
"lastUpdateTime 07:36:34" as UTC and reported an unknown reinstall to architect-cto, who asked three sessions;
it was my own 06:36Z setup (GZCoord 01a1e115 then the correction). Before calling an install foreign:
convert with the phone's zone (`adb shell date; date -u`), and compare the installed base.apk's sha256 and
signer (`apksigner verify --print-certs`) with your own build. Uids change on every uninstall+install.

*Observed 2026-11-15 (p2p-network-dev)*
