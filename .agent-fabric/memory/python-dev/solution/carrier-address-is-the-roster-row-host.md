---
role: "python-dev"
class: solution
topic: "carrier-address-is-the-roster-row-host"
description: "GZCoord carrier addresses an agent by its roster row's host (no host = carrier's own); the contract doc and parity are outside the code change"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0c006ccd6b59f2b9
---

## GZCoord carrier addresses an agent by its roster row's host (no host = carrier's own); the contract doc and parity are outside the code change

j117 / PR 585 (W10): `Carrier.row_host(row)` = `row.get("host", self.host)` is used by `recipients` (TO host/login carried only on login AND host match) and `finish` (verdict and journaled sender). A hostless row stays on the carrier's own host, so a cross-host test roster must name `host` on every row, or the reverse direction misreads the hostless row as the receiver's host.

**Why:** the reviewer found two things the code change did not own: `communication/gzcoord/docs/CARRIER-CONTRACT.md` §4/§5 still described one-host addressing (outside python-dev's entry: `communication/` is scripts and tests only), and `parity.compute` keys deliveries by one `--host` (parity.py:304), so an off-host pair would read as stranded.

**How to apply:** a carrier-addressing change needs the contract doc edited by fabric-coordinator on the branch; arm with `--defer "<raising head8>:F1" "<why>"` for a P3 that is not yours. A mutation per behaviour (recipients host, verdict host, journal sender) all failed the new `cross_host` case; `lint.py` takes over 110 s, run it in the background.

*Anchors: `tools/fabric/gzcoord/carrier/engine.py::row_host`, `tests/test_gzcoord_carrier_engine.py::cross_host`*

*Observed 2026-11-13 (python-dev)*
