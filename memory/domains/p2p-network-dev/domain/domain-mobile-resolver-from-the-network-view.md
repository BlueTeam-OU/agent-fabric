---
role: "p2p-network-dev"
class: domain
topic: "domain-mobile-resolver-from-the-network-view"
description: "On a phone the name resolver's config comes from the per-network platform view (nameservers change with Wi-Fi/cellular/VPN), never from launch or the libc config; no search list; strict Private DNS fails named lookups closed"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 7f4fee2137bd7934
---

## On a phone the name resolver's config comes from the per-network platform view (nameservers change with Wi-Fi/cellular/VPN), never from launch or the libc config; no search list; strict Private DNS fails named lookups closed

InterWeave j30 (#280), ruled by architect-cto (CONNECTIVITY.md §14 A 2026-10-14):
- Source: Android `LinkProperties.getDnsServers()` of the active network, sent with the network view the
  runtime already receives (not at launch — it goes stale on the first network move). Empty = unknown, keep
  the resolver in use; never "no DNS". (hickory's Android system read is not an option before an Activity —
  see [[domain-hickory-android-ndk-context-panic]].)
- No search list: a network's search domains turn an operator's short name into whatever the current network
  appends — a spoofing door; resolve only fully qualified names as given.
- Strict Private DNS (`getPrivateDnsServerName` set): the platform resolves over TLS and the network may drop
  plain port-53, so named addresses fail CLOSED with a stated reason; IP literals still dial.
- The DNS facts are local: never in Identify, the address book, candidates or telemetry beyond which source
  built the resolver.

**How to apply:** any p2p runtime embedded in a mobile app: make the resolver a function of the platform's
network view, rebuild it when the view's DNS facts change, and expose "resolver source: platform | host |
private-dns-strict | none" as status rather than failing lookups silently.

*References: domain-hickory-android-ndk-context-panic*

*Observed 2026-10-15 (p2p-network-dev)*
