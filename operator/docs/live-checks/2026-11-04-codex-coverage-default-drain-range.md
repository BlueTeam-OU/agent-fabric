# 2026-11-04: does a Codex review of a drain-sized range now produce a coverage block post-review accepts?

**Why.** The Codex review of agent-fabric #444 (the 2026-10-31 memory drain, fabric half, 1242 changed paths) failed. Its answer listed every path, and that came to 162049 characters of coverage against the 60000 one block may hold. Codex's answer schema then got a nullable `default` entry (02fc6373, j532), and `review_codex.py` offers it for a range too large to list and carries it into the posted block (a1b33124, j105). Audit F01 (j548) had to land before any Codex review ran again. j548 is done, and the fleet was read back at fabric d56a133c on 2026-11-03. Until this run, nobody had seen a real Codex run use the entry on a range of that size.

**How.** user@develop-qzapp, on main 9715ae1c, ran `bin/fabric-review --engine codex 444 <request> --gateway chatgpt --no-post`, with codex-cli 0.162.1, `gpt-6.1-sol` and effort `high` as routed. The request was a first-round `mode: review` of #444's own range, `00616fdf..57586b82` (its base and its head; #444 is merged), with lenses general, incomplete-migration and security. `--no-post` was used because #444 is merged: a review posted there now would count toward nothing and would only add noise to the PR. Afterwards the printed body was put through what `fabric-pr post-review` checks the block with: `review_coverage.read_block`, then `check_paths` against `diff_paths(base, head)`.

**Measured on develop-qzapp, 2026-11-04, 19:32:12Z to 19:38:27Z:**

| case | result |
|---|---|
| the run | exit 0. The gateway started and Codex ran in its sandbox on the extracted head. No error item, no failed turn: the answer parsed against the schema |
| the answer's coverage | 19 paths named, each `read`. 3 lenses `applied`. `default`: `{"status": "not read", "reason": "…the remaining files were not read line by line…"}` |
| size | the coverage block is 1960 bytes and the whole body 4379 bytes, against #444's 162049 characters |
| `check_paths` against the range's 1242 paths | `""`: accounted for, with none missing and none outside the range |
| `partial_line` | `partial coverage: 0 named path(s) and every path not named not read`. The `not read` default keeps the review from counting as coverage of the head, as the schema says it must |
| labels | the finding is numbered F2, past #444's earlier labels (`label_start`) |
| findings | 1 P1 (below) |

**The finding.** Codex's F2 is real, verified on origin/main 9715ae1c. `.agent-fabric/memory/devex-tooling/workflow/dependabot-pr-review-posters.md` line 20 carries a personal GitHub handle in its `AGENT_FABRIC_REVIEW_POSTERS` example. The drain's substitution (`policies/hygiene.json`) let it through. Codex names three more slices of the same kind. They are all fixed under a job of their own, and the rule is fixed with them, not each instance alone.

**What it decides.**
- The coverage `default` works end to end on a drain-sized range. A Codex review of a memory drain can be posted again, and the next drain PR runs it with posting on.
- Only the slices Codex chose to read are named `read`. The rest fall under a `not read` default. On a drain, Codex therefore stays advisory (ADR-053; the claude review alone arms, as the owner decided), which is what the arming policy already assumes.

**Not measured here.**
- The post itself. `fabric-pr post-review` checks the block the same way (`read_block`, `check_paths`), and the gate's reading of a posted default is covered by #447's tests, not by a run here.
- A range that fits in a full listing. That path predates the entry and is unchanged.
