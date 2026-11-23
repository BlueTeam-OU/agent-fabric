---
role: "fabric-coordinator"
class: domain
topic: "tool-rustgis"
description: "opengeos/RustGIS (Apache-2.0 pure-Rust desktop+web GIS, built mostly by Claude Opus 5.5 under human review): reviewed 2026-11-12 at the owner's ask; a GIS/MCP tool for domain-transit maps, and an agent-built repo whose AGENTS.md and…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c18487e1fe0a6710
---

## opengeos/RustGIS (Apache-2.0 pure-Rust desktop+web GIS, built mostly by Claude Opus 5.5 under human review): reviewed 2026-11-12 at the owner's ask; a GIS/MCP tool for domain-transit maps, and an agent-built repo whose AGENTS.md and review conventions are worth borrowing

Reviewed 2026-11-12 at the owner's request, from github.com/<owner>/RustGIS at main ce27286f, release v0.6.0 (2026-11-09). It was created 2026-10-10 and already has 1,281 commits, 2.6k stars, 394 forks and an active community of contributors (giswqs leads). Apache-2.0, `cargo deny` licence gate, Rust 1.90+. Read from the README, AGENTS.md and skills/rustgis/SKILL.md through the GitHub API; nothing was cloned or run.

- **What it is:** a QGIS/ArcGIS-style GIS in one native egui binary. It also builds to WASM at web.rustgis.app, and ships `rustgis-cli` and a `rustgis` Python package (PyO3). The crates are layered from L0 `geom` up to L6 `ui-egui`, and `cargo xtask layers` enforces the layering. It reads GeoJSON, Shapefile, GeoPackage, GeoParquet, FlatGeobuf, COG, Zarr, PMTiles and MVT, talks to OGC services and STAC, offers over 1,000 GeoLibre/Whitebox tools, and runs sandboxed `wasmi` plugins. It has an AI assistant for Anthropic, OpenAI, Gemini and OpenRouter.
- **Everything is a command with an id.** `rustgis-cli run --cmd 'gp.run={…}'`, and `rustgis-cli mcp --sample|--project|--data` is a stdio MCP server for agents. `--attach` instead drives the open desktop app through a loopback relay on 127.0.0.1:8767, which is off until the user starts it. Command ingress carries policy scopes (assistant, MCP, plugin), and a scope can only inherit or narrow.
- **Network:** the README says it is local-first and touches the network only when asked (basemaps, plugins, GeoLibre, the AI model). That was not verified by a trace.
- **Worth borrowing for the fabric:**
  - AGENTS.md is written as "Never crash / Never silent / Never hold the window" rules, each one held by a named test, for example `hostile_params_never_panic` and `long_commands_stop_when_cancelled_while_they_run`. That is our "a guard is a hook + CI + a suite case" applied to product invariants.
  - "Never silent": every lossy reader or writer reports what was lost, how much and where, and is tested both ways.
  - Review comments: a bug is fixed in the PR. A quality point is deferred to a "release quality pass", and the reply ends with `<!-- quality-sweep -->`, a machine-readable deferral marker. Compare [[owner-defers-findings-to-bugfix-pr]].
  - A shipped agent skill plus MCP. When it is attached to a live app it refuses to fall back silently to a private project.
- **Fit:** not adopted, and nothing was sent. A possible map/GTFS-shape viewer and geoprocessing CLI for domain-transit (gzapp), beside [[tool-graphhopper]]; that decision is theirs, with architect-cto. If anyone adopts it, pin a release tag: the project is a month old and moves daily.

**Why:** the owner asked for an analysis. It is the clearest public example so far of a large product built mostly by a Claude model with written agent rules.
**How to apply:** cite this note when an AGENTS.md rule set, a deferral marker for review comments, or a GIS tool comes up. Related: [[external-tools-evaluated]].

*References: external-tools-evaluated, owner-defers-findings-to-bugfix-pr, tool-graphhopper*

*Observed 2026-11-12 (fabric-coordinator)*
