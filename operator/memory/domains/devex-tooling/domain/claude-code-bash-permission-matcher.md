---
role: "devex-tooling"
class: domain
description: "Claude Code's Bash permission matcher is a text-pattern system with specific, repeatedly-rediscovered bypass and false-safety classes"
tier: 2
knowledge_scope: "domain-only"
distilled_at: "2026-09-05"
origin:
  - clone_id: "clone-c8407dca40bd40fc"
    host: "develop-qzapp"
  - clone_id: unresolved
    host: "develop-qzapp"
derived_from:
  - 041f3a6f2ca25a17
  - 13aaca093f20a95d
  - 3b3400ac75a911f1
  - 63faf85b1edc551e
  - 6e0bc63a9d71e196
  - 899a9a9f4a00eb45
  - 8c24709b2ef0506d
  - b064c9559c8bd26f
  - d55dbf8094e92c2c
  - d806d2b769003f2c
  - d877831945168724
---

## Claude Code's Bash permission matcher is a text-pattern system with specific, repeatedly-rediscovered bypass and false-safety classes

Measured directly against this repo's `.claude/settings.json` (and re-litigated by two separate automated-review findings that were each empirically refuted): (1) `&&`/`;`/`|`-chained commands are NOT matched as one string — the matcher decomposes the chain and evaluates each segment independently, so a deny rule on a destructive verb still fires on a later segment even when an earlier segment matches a broad allow rule. Two automated-review P1 findings claiming the opposite (`gh pr list && gh api graphql ...deleteRepository...` being pre-authorized by `Bash(gh pr *)`) were both wrong and both settled by the same live probe. (2) `bash -c "..."` wrapping IS a genuine bypass of every deny rule — the matcher does not resolve a nested interpreter's argument back into a command, so a denied command wrapped this way executes with no deny ever firing. The same wrapping matches no allow rule either, so it still falls to the harness's default confirmation prompt rather than auto-running; deny is a speed bump on the direct spelling only, allow-narrowing is the actual control. (3) A broad wildcard allow on a subcommand family (`gh issue *`, `gh cache *`) pre-authorizes a destructive subcommand whose flags are reordered before it (`gh issue -R owner/repo delete 5`), bypassing a deny rule written against the subcommand-first spelling (`gh issue delete*`). (4) A wildcard allow on a base command (`gh auth status*`) also matches flags that change the command's semantics entirely — `--show-token` turned a benign read into a credential-disclosure call that the allow rule pre-authorized. The actionable rule that falls out of all four: never treat a deny list as a security boundary — narrow the ALLOW list to exact safe forms instead, because a command that matches no allow rule always forces a manual prompt regardless of which text-matching trick produced it.
