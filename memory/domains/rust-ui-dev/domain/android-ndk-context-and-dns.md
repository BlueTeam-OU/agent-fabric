---
role: "rust-ui-dev"
class: domain
topic: "android-ndk-context-and-dns"
description: "Rust networking crates on Android -- system resolver config needs ndk_context (panics outside an Activity process); feed DNS from the platform's per-network view instead"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f3bd969d77e396df
---

## Rust networking crates on Android -- system resolver config needs ndk_context (panics outside an Activity process); feed DNS from the platform's per-network view instead

hickory_resolver::system_conf::read_system_conf() on Android calls
ndk_context::android_context(), which PANICS (not Err) when nothing initialised the
context. android-activity initialises it only on the Activity's first android_main, so an
instrumentation process or a service-only process panics on the first runtime start.
Do not wrap it in catch_unwind (the hook still fires, and a later init races it): never
call the system read on Android. DNS configuration comes from the platform per network --
LinkProperties.getDnsServers() and, in strict Private DNS mode, getPrivateDnsServerName() --
sent with the network snapshot the service reports on every change (Wi-Fi to cellular, VPN),
not once at launch; an empty server list means unknown, never "no DNS". A search-domain
list may be deliberately not applied when the product resolves only fully qualified names.

*Observed 2026-10-15 (rust-ui-dev)*
