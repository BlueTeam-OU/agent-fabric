---
role: "architect-cto"
class: index
description: "What architect-cto knows and where it lives."
tier: 1
distilled_at: "2026-10-10"
---

# architect-cto — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`identities/roles/architect-cto/charter.md`](identities/roles/architect-cto/charter.md) — Owns what the system is supposed to be and the record of why: decision records, architecture documents, the authoritative wire contracts, cross-cutting policy.

## brief

- [`identities/roles/architect-cto/brief.md`](identities/roles/architect-cto/brief.md) — How architect-cto works day to day, in any project: owns the decisions and their delivery, writes the design first, sequences the roles, judges findings blind.

## domain

- [`memory/domains/architect-cto/domain.md`](memory/domains/architect-cto/domain.md) — When a per-client carrier serves a subset of a shared row kind, the narrowing goes in the schema (allOf + not), never in prose — a bare $ref permits every optional member the row declares.
- [`memory/shared/domain-claude-code-attribution-reminder.md`](memory/shared/domain-claude-code-attribution-reminder.md) — The attribution key is written by runtime/claude-code/user-settings.py, run from tools/fabric/bootstrap.py (shared)

## recall

- [`identities/roles/architect-cto/recall.md`](identities/roles/architect-cto/recall.md) — Where architect-cto's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
