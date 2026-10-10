---
role: "domain-transit"
class: index
description: "What domain-transit knows and where it lives."
tier: 1
distilled_at: "2026-10-10"
---

# domain-transit — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/domain-transit/charter.md`](identities/roles/domain-transit/charter.md) — The transport domain: how the network is modelled, planned and drawn.

## brief

- [`identities/roles/domain-transit/brief.md`](identities/roles/domain-transit/brief.md) — How domain-transit works day to day, in any project: the transport network as data — what a line, a stop and 'served' mean, checked against the real map before any textbook answer.

## domain

- [`memory/domains/domain-transit/domain/a-route-number-is-not-a-service.md`](memory/domains/domain-transit/domain/a-route-number-is-not-a-service.md) — in a scraped route catalogue a number shared by a minibus and a trolleybus is two different services, and no trolleybus route has a published schedule at all
- [`memory/domains/domain-transit/domain/country-graph-fits-in-the-otp-cap.md`](memory/domains/domain-transit/domain/country-graph-fits-in-the-otp-cap.md) — measured OTP 2.10 memory for a [redacted]-wide graph vs the [redacted] city graph — the country graph fits the 2 GB container cap
- [`memory/domains/domain-transit/domain/domain-carried-2026-08-10.md`](memory/domains/domain-transit/domain/domain-carried-2026-08-10.md) — Overpass API vs. Geofabrik extracts: different freshness and metadata tradeoffs
- [`memory/domains/domain-transit/domain/georgian-osm-ways-carry-name-en.md`](memory/domains/domain-transit/domain/georgian-osm-ways-carry-name-en.md) — street-name locale variants in [redacted]'s OSM — name:en ~93% / name:ru ~84% of named [redacted] ways, mapper-authored
- [`memory/domains/domain-transit/domain/monotonicity-by-moving-floor-cascades.md`](memory/domains/domain-transit/domain/monotonicity-by-moving-floor-cascades.md) — enforce ordering along a line with an anchor from the construction, never by carrying the previous result forward as the next search's floor
- [`memory/domains/domain-transit/domain/nominatim-settlement-is-rank-address-16.md`](memory/domains/domain-transit/domain/nominatim-settlement-is-rank-address-16.md) — in a Nominatim gazetteer the settlement ancestor is rank_address 16, never admin_level, and isaddress must order rather than filter
- [`memory/domains/domain-transit/domain/otp-pickup-type-3-is-boardable.md`](memory/domains/domain-transit/domain/otp-pickup-type-3-is-boardable.md) — OTP 2.10 non-flex boards a pickup_type 3 stop exactly as 0; type 1 removes it and silently walks the rider to a neighbour
- [`memory/domains/domain-transit/domain/otp-street-name-language-follows-the-request.md`](memory/domains/domain-transit/domain/otp-street-name-language-follows-the-request.md) — OTP 2.10 walk-step streetName language — planConnection without locale gives OSM `name`, legacy `plan` gives name:en, a locale picks name:<lang>; underpass is a bogus name
- [`memory/domains/domain-transit/domain/the-timetable-does-not-bound-operations.md`](memory/domains/domain-transit/domain/the-timetable-does-not-bound-operations.md) — the schedule answers what the service PLANS, never what a vehicle or a shift actually does — those are bounded by driver behaviour, not by a published window
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## recall

- [`identities/roles/domain-transit/recall.md`](identities/roles/domain-transit/recall.md) — Where domain-transit's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
