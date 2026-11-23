---
role: "rust-ui-dev"
class: domain
topic: "android-local-network-target37"
description: "An Android app sees its own hotspot (a LOCAL_NETWORK network) in NetworkCallback only when it targets SDK 37; a background cellular network and IMS are never reported; measured 2026-10-27"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: interweave
    working_copy: interweave
derived_from:
  - db4e024a9bf1f850
---

## An Android app sees its own hotspot (a LOCAL_NETWORK network) in NetworkCallback only when it targets SDK 37; a background cellular network and IMS are never reported; measured 2026-10-27

Measured on the Pixel 9a (API 37) on 2026-10-27, InterWeave app at targetSdk 36:
- `registerNetworkCallback` adds FOREGROUND to an app's listen implicitly, so a background cellular network (kept up behind validated Wi-Fi) is never reported. The restricted IMS network (rmnet, 10.x/32) is never reported either.
- The phone's own Wi-Fi hotspot is network wlan1 with capability LOCAL_NETWORK. It reaches no listen of an app targeting 36, not even one that names NET_CAPABILITY_LOCAL_NETWORK with setIncludeOtherUidNetworks(true) and holds ACCESS_LOCAL_NETWORK.
- The gate is the compat change ENABLE_MATCH_NON_THREAD_LOCAL_NETWORKS (349487600), enableSinceTargetSdk=37. ENABLE_MATCH_LOCAL_NETWORK (319212206) is on from 35.
- `adb shell am compat enable ENABLE_MATCH_NON_THREAD_LOCAL_NETWORKS <pkg>` works on a debuggable app below the threshold, and then the plain widened listen reports the hotspot. `am compat reset` undoes it.
- `dumpsys platform_compat | grep LOCAL_NETWORK` lists the gates.
- Raising targetSdk to 37 also makes ACCESS_LOCAL_NETWORK a runtime permission for LAN traffic.
Related: [[j166-rule10-bridge-supply]] [[android-network-change-contract]]

2026-10-27: the owner's word (via architect-cto-01, INFO 01a17e74): stay on targetSdk 36 for now. The hotspot host's own address stays a recorded limit (ADR-0052 rule 10 amendment (iv)); revisit only when a release targets Android 17 for its own reasons or a user hits the case.

*References: android-network-change-contract, j166-rule10-bridge-supply*

*Observed 2026-10-27 (rust-ui-dev)*
