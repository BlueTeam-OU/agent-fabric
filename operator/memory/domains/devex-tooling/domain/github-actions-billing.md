---
role: "devex-tooling"
class: domain
description: A nonzero Actions netAmount (filtered to the Minutes SKU) means overage IS being purchased and runners ARE still dispatching — not that the allowance is spent
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-09-05"
origin:
  - clone_id: "clone-948c9fcd4da94057"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 4b571c4d7b29cd1c
  - 5a65fe7d666c8260
  - 5c63af7cd08785e9
  - 6bfecb9fb11d0fd7
  - 6d83cf3047ac938e
  - 7be9e8ab4a45cd1b
  - 8cf30b845acf4bec
  - 9109c685efb570c5
  - 9597c1cbe9882be3
  - a83311ac07fbd2f9
  - b51734af2446d7bd
  - bbaa53c2ec533bbc
  - fba30fc0a1bb5f23
---

## GitHub Actions billing netAmount is not a reliable allowance-exhaustion signal

The GitHub Actions billing usage API reports `netAmount` (money actually billed after the plan's discount), and it's tempting to treat `netAmount > 0` as "the included minutes are spent." That check only fires on plans that purchase overage. On a plan that does NOT purchase overage, GitHub simply stops handing out runners once included minutes are exhausted — it never bills anything, so `netAmount` stays $0 forever, and a check built on it reports "healthy" while every job is actually failing to start. There is also no field in the billing API for the plan's total included-minutes limit — it has to be supplied out of band and compared against reported usage. A CI health-check script here reported "still within allowance" while the org had already exceeded its included minutes and every job was dying instantly with no runner assigned; the fix stores the plan size as an explicit configured setting and compares usage against it directly, only using the `netAmount` check for genuine overage billing.

## A CI job dying in seconds with zero steps is runner starvation, not quota exhaustion

When a GitHub Actions job fails almost instantly with an empty `runner_name`, zero steps ever run, and no log content, that is GitHub failing to hand the job a runner — a transient platform issue — and it typically clears on a plain re-run/re-queue of the same unchanged commit. It's tempting to jump to "the account's Actions minutes are exhausted" as the explanation, especially right after any billing-related change, but that diagnosis is wrong for this specific signature and wastes a cycle chasing the wrong fix. Confirm via the run's per-job API response (`runner_name`, `steps`) before touching any billing/quota logic; six jobs failing this way in one merge-queue run turned out to be pure runner starvation — the same PR merged clean on the very next attempt with no code change.

## A nonzero Actions netAmount (filtered to the Minutes SKU) means overage IS being purchased and runners ARE still dispatching — not that the allowance is spent

This sharpens the existing netAmount claim with the opposite-direction mistake this repo also made and fixed: on a plan that DOES purchase overage, `actions_allowance_spent()`-style logic that treats any nonzero `netAmount` as 'the allowance is exhausted / stalled' has the fact backwards. Money being billed for the `Minutes` SKU proves GitHub is still handing out runners for a price, which is the opposite of a stall — the plan that actually blocks is the one that bills nothing at all past the limit (job dies instantly, zero runner assigned). `netAmount: 0` therefore means nothing is being billed and says nothing on its own about whether the allowance is intact or gone; the real check is usage-against-a-configured-limit (a configured included-minutes setting), not the sign of netAmount. A second, independent bug in the same logic: netAmount must be summed only over `unitType == "Minutes"` — summing every Actions charge lets unrelated GigabyteHours (storage) billing mask a genuine runner stall, since storage costs money even while compute runners are fully exhausted.
