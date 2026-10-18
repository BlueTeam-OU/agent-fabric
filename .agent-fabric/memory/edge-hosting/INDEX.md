---
role: "edge-hosting"
class: index
description: "What edge-hosting knows and where it lives."
tier: 1
distilled_at: "2026-10-18"
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

## brief

- [`identities/roles/edge-hosting/brief.md`](identities/roles/edge-hosting/brief.md) — How edge-hosting works day to day, in any project: the whole path from a public name to its response, every change with its rollback, public behaviour verified from outside, and failure domains kept apart.

## domain

- [`memory/domains/edge-hosting/domain/cloudflare-origin-errors.md`](memory/domains/edge-hosting/domain/cloudflare-origin-errors.md) — Cloudflare 521 vs 522/523 — what each error class actually means
- [`memory/domains/edge-hosting/domain/cloudflare-pages-custom-domain.md`](memory/domains/edge-hosting/domain/cloudflare-pages-custom-domain.md) — Cloudflare Pages custom-domain cutover: attach via API, then swap the DNS record
- [`memory/domains/edge-hosting/domain/tileserver-public-url-flag.md`](memory/domains/edge-hosting/domain/tileserver-public-url-flag.md) — TileServer-GL's --public_url flag rewrites embedded URLs so a fronting proxy needs no body-rewriting logic
- [`memory/domains/edge-hosting/domain/wrangler-miniflare-cve-pinning.md`](memory/domains/edge-hosting/domain/wrangler-miniflare-cve-pinning.md) — sharp CVEs in a Workers project are fixed by bumping wrangler, and range updates can lag the fix by a day
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## solution

- [`.agent-fabric/memory/edge-hosting/solution.md`](.agent-fabric/memory/edge-hosting/solution.md) — blueteam.ee unreachable from develop-qzapp but up elsewhere — 1984 Hosting firewall dropping our one egress IP

## rationale

- [`.agent-fabric/memory/edge-hosting/rationale.md`](.agent-fabric/memory/edge-hosting/rationale.md) — Where a site's deploy/upload tooling goes — the site's own repository, generic core; never agent-fabric

## workflow

- [`.agent-fabric/memory/edge-hosting/workflow/agent-store-tool-only.md`](.agent-fabric/memory/edge-hosting/workflow/agent-store-tool-only.md) — My fabric-agent-<id> repository is my secrets store: write it only through fabric-secrets, never a hand clone or push
- [`.agent-fabric/memory/edge-hosting/workflow/home-disk-footprint.md`](.agent-fabric/memory/edge-hosting/workflow/home-disk-footprint.md) — What fills the edge-hosting home on develop-qzapp, what is safe to remove in a disk cleanup, and how to record a cleanup that has no repository artifact
- [`.agent-fabric/memory/edge-hosting/workflow/publish-needs-owner-word-in-session.md`](.agent-fabric/memory/edge-hosting/workflow/publish-needs-owner-word-in-session.md) — A live upload of a site goes only on the owner's word given in my own session, for exactly the commit being uploaded

## threads

- [`.agent-fabric/memory/edge-hosting/threads.md`](.agent-fabric/memory/edge-hosting/threads.md) — Open gzapp edge item — any CSP served for admin_web/advertiser_web must allow the Stream media host in connect-src and media-src, plus blob:

## recall

- [`identities/roles/edge-hosting/recall.md`](identities/roles/edge-hosting/recall.md) — Where edge-hosting's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
