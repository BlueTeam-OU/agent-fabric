---
role: "edge-hosting"
class: index
description: "What edge-hosting knows and where it lives."
tier: 1
distilled_at: "2026-10-10"
---

# edge-hosting — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/edge-hosting/charter.md`](identities/roles/edge-hosting/charter.md) — The layer between the public internet and the system: names, routes, certificates, and the platform serving what the local stack does not.

## domain

- [`memory/domains/edge-hosting/domain/cloudflare-origin-errors.md`](memory/domains/edge-hosting/domain/cloudflare-origin-errors.md) — Cloudflare 521 vs 522/523 — what each error class actually means
- [`memory/domains/edge-hosting/domain/cloudflare-pages-custom-domain.md`](memory/domains/edge-hosting/domain/cloudflare-pages-custom-domain.md) — Cloudflare Pages custom-domain cutover: attach via API, then swap the DNS record
- [`memory/domains/edge-hosting/domain/tileserver-public-url-flag.md`](memory/domains/edge-hosting/domain/tileserver-public-url-flag.md) — TileServer-GL's --public_url flag rewrites embedded URLs so a fronting proxy needs no body-rewriting logic
- [`memory/domains/edge-hosting/domain/wrangler-miniflare-cve-pinning.md`](memory/domains/edge-hosting/domain/wrangler-miniflare-cve-pinning.md) — sharp CVEs in a Workers project are fixed by bumping wrangler, and range updates can lag the fix by a day
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## recall

- [`identities/roles/edge-hosting/recall.md`](identities/roles/edge-hosting/recall.md) — Where edge-hosting's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
