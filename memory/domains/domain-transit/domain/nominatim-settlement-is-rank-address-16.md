---
role: "domain-transit"
class: domain
topic: "nominatim-settlement-is-rank-address-16"
description: in a Nominatim gazetteer the settlement ancestor is rank_address 16, never admin_level, and isaddress must order rather than filter
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "domain-transit"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 31342f4fe0a41e09
  - 735f400f7ea32773
---

## in a Nominatim gazetteer the settlement ancestor is rank_address 16, never admin_level, and isaddress must order rather than filter

Reading a place's settlement out of Nominatim's `place_addressline`:

**`admin_level` does not name the settlement.** It is assigned per
country and is not even consistent inside one: in this deployment's
country the SAME level is the *city* for a self-governing city and the
*municipality* for an ordinary one, so a rule keyed on it labels a village
street with its municipality. **`rank_address` does name it**:
16 = the settlement whatever carries it (`place|city`, `place|village`, a
level-6 boundary or a level-8 one), 12 = municipality, 20 = district,
24 = neighbourhood, 26 = street.

**A settlement is commonly in `placex` twice and UNLINKED** — a `place`
row and an admin boundary, `linked_place_id` null on both, so following
the link cannot unify them. Nominatim marks exactly one of the pair
`isaddress`, and **which one flips from street to street**.

**So `isaddress` must ORDER, never filter.** Requiring it hid the
deployment's city from 321 of its own streets. Ignoring it moved 207 rows
onto a *different* locality, 130 onto a village flagged
`isaddress=false` — because outside
the duplicate-representation case the several rank-16 lines of one street
are several **different villages**, and the flag is the only thing saying
which one the street is in. Order by `rank_address DESC, isaddress DESC,
(class='place') DESC`: the flagged ancestor wins when there is one, the
unflagged one is taken only when nothing else is on offer.

**A settlement with no rank-16 ancestor is its own locality.** Otherwise
it becomes a suburb of nothing. Promote only `place|city/town/village/
hamlet/locality` — never a neighbourhood or quarter.

Measured on the seed gazetteer 2026-09-17 (`export-places.sql`,
commits `9601135f`, `412b7ae9`, `c424c9b1`).

Related: [[a-street-is-many-exported-rows]], [[parent-keys-always-point-at-an-area]].

*References: a-street-is-many-exported-rows, parent-keys-always-point-at-an-area*

*Observed 2026-09-18 (domain-transit)*
