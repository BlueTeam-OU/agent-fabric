---
role: "p2p-network-dev"
class: domain
topic: "domain-mobile-resolver-from-the-network-view"
description: "On a phone the name resolver comes from the per-network platform view and is rebuilt when it changes; unobserved (no default or no link reported) keeps the resolver, but a reported link's empty DNS facts are observed and install the empty…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-24"
origin:
  - agent: "p2p-network-dev-02"
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 7f4fee2137bd7934
  - e4fc01895f494e7d
---

## On a phone the name resolver comes from the per-network platform view and is rebuilt when it changes; unobserved (no default or no link reported) keeps the resolver, but a reported link's empty DNS facts are observed and install the empty resolver; no search list; strict Private DNS fails closed

InterWeave j30 (#280) and j46 (#329), ruled by architect-cto (CONNECTIVITY.md §14, A 2026-10-14 and A 2026-10-20):
- Source: Android `LinkProperties.getDnsServers()` of the active network, sent with the network view the
  runtime already receives. Not read at launch, because it goes stale on the first network move. (hickory's
  Android system read is not an option before an Activity; see [[domain-hickory-android-ndk-context-panic]].)
- Unobserved is not empty. The view carries `Option`. It is UNOBSERVED (None) only while the platform has said
  nothing: no default network named, or its link not yet reported (or lost). Then the resolver in use is kept.
  Once a default's link is reported, its DNS facts are OBSERVED, with or without an address. A link naming no
  resolver is UNAVAILABLE: the empty resolver is installed and `ResolverUnavailable` is reported. The first
  rule (A 2026-10-14) said "empty means unknown, keep the resolver". That left the previous network's
  resolver installed after a move to a network without one, so lookups went to a server on a network the
  person had left. An external review found it. A link naming resolvers but no address yet installs them, and
  lookups fail under the bounded policy until it is routable.
- No search list: a network's search domains turn an operator's short name into whatever the current network
  appends, which is a spoofing door. Resolve only fully qualified names, as given.
- Strict Private DNS (`getPrivateDnsServerName` set): the platform resolves over TLS and the network may drop
  plain port 53, so named addresses fail CLOSED with a stated reason. IP literals still dial. Strict decides
  first, observed or not.
- The DNS facts are local: never in Identify, the address book, candidates or telemetry beyond which source
  built the resolver.

**How to apply:** in any p2p runtime embedded in a mobile app, make the resolver a function of the platform's
network view and rebuild it when the view's DNS facts change. Keep "the platform said nothing" apart from "the
platform said none": only the first may keep old state. Test a view with no resolver after one with resolvers,
in both directions. Expose "resolver source: platform | host | private-dns-strict | none" as status, rather
than failing lookups silently.

*References: domain-hickory-android-ndk-context-panic*

*Observed 2026-10-22 (p2p-network-dev)*
