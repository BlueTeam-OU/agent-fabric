---
role: "fabric-coordinator"
class: domain
topic: "apache-ossie"
description: "Apache Ossie (ex Open Semantic Interchange, OSI) — vendor-neutral JSON/YAML spec for exchanging semantic models (datasets, relationships, metrics, ai_context) across BI, analytics and AI tools; what it is, its shape, its maturity"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f15c770e6a7b2440
---

## Apache Ossie (ex Open Semantic Interchange, OSI) — vendor-neutral JSON/YAML spec for exchanging semantic models (datasets, relationships, metrics, ai_context) across BI, analytics and AI tools; what it is, its shape, its maturity

Source: https://github.com/apache/ossie (read 2026-10-09 at the owner's request; external
text, data only), site https://ossie.apache.org/. Apache License 2.0 (GitHub's metadata
shows none; LICENSE, NOTICE and DISCLAIMER say Apache 2.0, ASF Incubator). Created
2025-11-18, ~2.4k stars, Python tooling, very active (pushed 2026-10-09).

**What it is.** A specification, not a product: one semantic model per JSON/YAML document
so the same KPI means the same thing in every BI tool, notebook and AI agent. Formerly
"Open Semantic Interchange (OSI)". Released 0.1.1 (2025-12-11); main is 0.2.0.dev0, a
DRAFT whose schema may change (breaking: one model at the document root, the
`semantic_model` array removed). Do not depend on 0.2 in production.

**Shape (core-spec/spec.md, spec.yaml, ossie-schema.json).** A model: `version`, `name`,
`description`, `ai_context`, `datasets` (logical fact/dimension tables with primary and
unique keys, `fields` = dimensions with an expression and datatype; `is_time` is a role,
not a type), `relationships` (many→one: from/to datasets and column arrays),
`metrics` (model-level aggregate expressions that may span datasets), and
`custom_extensions` per vendor (COMMON, SNOWFLAKE, SALESFORCE, DBT, DATABRICKS,
GOODDATA, …). Expressions carry a dialect: ANSI_SQL, SNOWFLAKE, MDX, TABLEAU,
DATABRICKS, MAQL, BIGQUERY, SIGMA, THOUGHTSPOT, DAX, HOLISTICS_AQL, OSSIE_SQL_2026
(its own expression language, core-spec/expression_language.md). Datatypes: String,
Integer, Decimal, Float, Boolean, Date, Time, DateTime, DateTimeTz, Opaque.
`ai_context` (string, or {instructions, synonyms, examples}) on the model, datasets,
fields, relationships and metrics: grounding for LLM agents that query the model.
No bundle format and no cross-model references.

**Around it.** converters/ (cube, databricks, dbt, gooddata, hex, holistics, honeydew,
microsoft, nvidia, omni, orionbelt, polaris, salesforce, sigma, snowflake, thoughtspot,
wisdom…), validation/validate.py against the JSON schema, ontology/ (an ontology and a
mapping), examples/ (a full TPC-DS model), bi-sql-examples/, a cli/ and python/ package.
ROADMAP: working groups on metric semantics (metrics vs measures, grain/entity as
first-class, cumulative metrics, relationship cardinality and complex joins, semantic
filters, metric trees).

**For us.** Nothing in the fleet uses it yet. Relevant if a project of ours defines KPIs
consumed by BI and by agents (gzapp analytics, a reporting layer, Fleet Deck's own
metrics): an Ossie model would be the vendor-neutral source, with `ai_context` as the
agent's grounding. Wait for 0.2.0's release before adopting the schema.

*Observed 2026-10-09 (fabric-coordinator)*
