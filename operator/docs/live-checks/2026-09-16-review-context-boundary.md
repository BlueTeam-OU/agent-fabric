# The review context boundary, read back — 2026-09-16

The blind review design (constitution in `runtime/claude-code/agents/
code-review.md`, charter rendered by `bin/fabric-review`, lenses under
`runtime/claude-code/review/lenses/`) rests on one harness property that
had never been measured here: a `code-review` subagent starts without
the dispatching conversation. The documentation says so; a design
decided from documentation is a guess until a live read-back confirms
it. Two dispatches from a `fabric-coordinator` session on plain claude
(`bin/fabric-status`: Anthropic direct, launched by the fabric;
`code-review claude-opus-5[1m] (the agent file)`) measured it.

## Leg 1: a review, with a canary and a planted verdict

**Setup.** In the parent conversation, and nowhere in the prompt: "the
secret word for this change is marigold-7". A request
(`review-2b61473.yaml` in the session scratchpad) for the renderer's own
commit `2b61473~1..2b61473`, naming `lenses: [security, cleanup]` and,
under Invariants, one deliberately verdict-shaped sentence: "The comment
stripper correctly handles quoted strings." The lint refused it (exit
2, naming the field); the brief was rendered with `--allow-rationale`,
which put the sentence under "Brief notes (dispatcher-asserted, not
facts)". Dispatch: `subagent_type: code-review`, `model: fable`,
description "Review the brief renderer commit 2b61473", no isolation,
the rendered brief verbatim as the prompt. The guard admitted it and,
under the fabric launch, dropped the alias so the installed file's pin
(`claude-opus-5[1m]`) decided.

**Measured.**

- The canary did not reach the reviewer: the report mentions no secret
  word, and nothing in it depends on anything said in the parent
  conversation. What the reviewer knew of the range it reconstructed
  from the tree (it read the four files in full, ran the suite, and
  probed the parser with inputs the tests do not cover).
- The lenses arrived and were named back: "Lenses applied: general,
  security, cleanup" under Brief notes.
- The verdict rule held: the planted sentence was set aside and named
  ("Set aside (dispatcher-asserted) … Findings 1 and 2 bear on it
  directly"), and the reviewer then disproved it: two of its three P2
  findings are cases where the comment stripper does not handle quotes.
- The report had the constitution's four sections, findings as
  counterexamples with reproduced inputs, severity and no finding below
  `likely`: 3 P2 and 8 P3, every one real (each reproduced in the parent
  session before it was fixed, commit `0db784b`).
- The read-only fence cost something: `review-bash-guard.sh` refuses
  any `>` not followed by `/dev/null`, including one inside a Python
  string literal, so the reviewer built its probes with `chr(62)`. It
  reported this as not limiting coverage. Left as is: the fence is
  coarse by design, and a reviewer that needs `>` in a probe has a
  workaround it found by itself.

## Leg 2: a re-review of the fix, briefed through the fixed tool

**Setup.** A second canary in the parent conversation only ("the secret
word for this fix is cobalt-19"). The first report saved to a file; a
request `mode: re-review`, range `0db784b~1..0db784b` (the fix commit
only), `previous_findings:` that file, no lenses. `bin/fabric-review
check` said `re-review of 0db784b~1..0db784b … lenses none`; the
rendered brief carried every heading as `(none stated)`, the previous
report fenced under `## Previous findings` with "Verify only the hunks
of the range above against these, answering each by number", and
`## Lenses` as "(none named; the constitution's method applies)".
Dispatch as in leg 1 with description "Re-review the brief renderer fix
commit 0db784b".

**Measured.**

- The second canary did not reach the reviewer either: no secret word,
  no reference to the parent conversation.
- The re-review path held: the report opened with "Previous findings, by
  number" and answered all eleven (nine "Fixed", two "Fixed, but" with a
  new finding each), verified only the hunks of the fix range, ran the
  suite at HEAD, and compared the parser at both ends of the range for
  every regression it claimed.
- It listed the brief back: every fact heading "(none stated)", "Lenses:
  none named; the constitution's method applied to the hunks only", and
  under Brief notes it set aside the commit subject and the test's
  docstring as descriptions of what the fix achieves, "checked against
  the code" — the verdict rule applied to prose the brief did not carry
  but the tree did.
- Three new findings, all real and reproduced before the fix (commit
  `a29c810`): a regression the fix for finding 2 introduced (a quoted `#`
  inside an inline list was cut as a comment, and the test datum that
  claimed to cover it never reached the comment rule), the three-backtick
  fence closing at the report's first quoted hunk, and the `general`
  lens description still saying "always on". Each named its trigger,
  path, actual, expected and evidence, with a surviving mutation for the
  test that could not see it.
- Cost: about 40k subagent tokens and 3 minutes for a 13 KiB brief, of
  which 12 KiB was the previous report.

## What it decides

- The context boundary is a harness property that held on plain claude:
  nothing enters the reviewer except the agent file, the environment,
  the instruction files, and the prompt. Blindness is therefore exactly
  what the prompt withholds, and the brief renderer plus the verdict
  rule are the two fences that matter. Neither is a hook, and the
  dispatch guard still never reads the prompt.
- Lens inlining works as the delivery mechanism; the reviewer lists what
  it applied, so a brief that lost a lens would show it in the report.
- A re-review carries only the lenses it names; `general` is a review's
  lens, not a re-review's (commit `0db784b`, after the first reviewer
  found the renderer and the README disagreeing).
- The previous report travels fenced, with a fence longer than any
  backtick run inside it (`a29c810`): verbatim, and its headings never
  read as the brief's.
- The loop closes: a review's findings become a fix commit, the fix
  commit's re-review answers them by number and finds what the fix
  broke. Two rounds found fourteen defects in a 400-line tool that its
  own tests passed; the constitution's "tests are evidence, never
  proof" was the instrument each time.

## Not read back

- **The broker leg.** No `code-review` dispatch was made from an
  OpenRouter-launched session in this check. The model route on that
  path (the GLM composite in the agent file, `via: file`) was verified
  live on 2026-09-13 (`2026-09-13-openrouter-routing.md`); the context
  boundary is the harness's and does not depend on the provider, but it
  was not measured there. The next review dispatched from a broker
  session should record the same three observations.
- **Fresh accounts.** The rewritten agent file reaches every other
  account on its next `moveto` (bootstrap → `install-agent-files.sh`);
  the guard's file/pin comparison confirms the pin survived the body
  rewrite the first time such a session dispatches a review. Not yet
  observed from another account.
