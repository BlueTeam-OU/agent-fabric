---
role: "rust-ui-dev"
class: domain
topic: "android-app-network-view"
description: "Which networks an Android app's NetworkCallback reports, and why an address bound on an up interface may be in no network the app hears (background cellular, IMS, hotspot host, carrier /32s in 10/8)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 07e865f5f98c88c0
---

## Which networks an Android app's NetworkCallback reports, and why an address bound on an up interface may be in no network the app hears (background cellular, IMS, hotspot host, carrier /32s in 10/8)

Measured on a Pixel 9a (API 37), 2026-10-26/27, against `dumpsys connectivity` and `ip addr`:
- **A private-range address is not a LAN address.** The carrier gives rmnet interfaces /32s
  in 10/8 (CGNAT, IMS). An "is it RFC 1918" test offers them to LAN peers, who store and dial
  addresses they cannot reach, and it discloses carrier-side addresses to anyone who scans a code.
- **The app's callback is not every bound address.** Both rmnet /32s sat on up interfaces, but
  a listen for INTERNET reported neither: the cellular network kept in the background behind
  validated Wi-Fi has no FOREGROUND (the platform adds FOREGROUND to an app's listen), and the
  IMS one lacks NOT_RESTRICTED (an app can never see it). Dropping INTERNET from the request
  changed nothing for either. So a rule that classifies only networks the callback reported
  passes every address it never heard. Decide what happens to a bound address that no reported
  network holds before you write the classifier.
- **A Wi-Fi with no uplink still carries INTERNET.** It lacks only VALIDATED, so an INTERNET
  listen hears it already.
- **The phone's own hotspot (wlan1, LOCAL_NETWORK, no INTERNET) is reported only to an app that
  targets SDK 37.** That is compat change ENABLE_MATCH_NON_THREAD_LOCAL_NETWORKS (349487600).
  At target 36 even a listen naming NET_CAPABILITY_LOCAL_NETWORK, with setIncludeOtherUidNetworks
  and ACCESS_LOCAL_NETWORK granted, got no callback. `dumpsys platform_compat` names the gate,
  and `am compat enable` proves it on a debug build. Raising targetSdk is a release decision
  (a toolchain pin, and a runtime LAN prompt), not a fix the client makes on its own.
- Classify by transport from NetworkCapabilities, per network, in the platform shell. A
  carrier's network (cellular, and satellite from API 35) is not local; check VPN first,
  because a VPN over cellular is local. The transport itself stays in the bridge.
How to apply: before a client shows or advertises "its addresses", list where each comes from
(callback-reported vs bound) and check each case on a device with Wi-Fi plus data, data
alone, and hotspot host and client. Related: [[android-ndk-context-and-dns]].

*References: android-ndk-context-and-dns*

*Observed 2026-10-27 (rust-ui-dev)*
