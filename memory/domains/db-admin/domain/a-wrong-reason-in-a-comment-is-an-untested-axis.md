---
role: "db-admin"
class: domain
topic: "a-wrong-reason-in-a-comment-is-an-untested-axis"
description: When a comment misstates WHY a check works, the clause it wrongly credits is usually the one nothing tests — treat it as a missing test, not a documentation defect.
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "db-admin"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - bd9c541548f2e0ca
---

## When a comment misstates WHY a check works, the clause it wrongly credits is usually the one nothing tests — treat it as a missing test, not a documentation defect.

0055's guard predicate has two clauses. My test carried a comment saying
a probe was excluded because it "merely NAMES the column submitted_at" —
crediting the **quoting** clause. It was excluded by the **missing
second status literal** instead; the probe renders
`status = 'submitted'::text` and plainly carries a quoted literal.

The comment was wrong, and the wrongness was not cosmetic: because I
believed the quoting clause was doing that work, **nothing tested the
quoting clause at all.** Unquoting all three literals in the migration
left every assertion green. A blind review found it (#892, 2026-09-19).

**The generalisation: a comment that misstates why something works is a
missing test wearing a disguise.** The clause a wrong comment credits is
exactly the clause nobody built a case for — that is *why* the comment
could be wrong and still look right. So when a review corrects a
"why", do not just reword it: ask what the real reason implies is
untested, and go measure that.

**The worse detail, and the reason this is a `domain` memory rather than
a note on one PR: I had already measured it.** Choosing the predicate, I
ran all three constraint shapes on a throwaway container and the output
printed `'submitted'::text` for that probe. I read my own measurement
and wrote a comment describing something else. Having the evidence is
not the same as reading it; write the comment FROM the output, with the
output in front of you, not from the intent you had before running it.

**What good looks like here:** one probe per axis, each reddening the
same test by name when its own clause is broken —

```
unquote the migration's literals   -> axis 1 (quoted vs bare) reds
drop the second status clause      -> axis 2 (both open statuses) reds
```

**THE PATTERN, which is the reason to keep this memory at all.** Across
three review rounds on ONE test file (#892, 2026-09-19), every finding
against me was in the PROSE and none in the code:

| round | my defect | the code was |
|---|---|---|
| 2 | a test asserting an empty set — cover that was not cover | correct |
| 3 | the comment credited the wrong clause, leaving an axis untested | correct |
| 4 | "NOT VALID on **both** probes" after I added a third | correct |

I am evidently more careful with the thing that runs than with the
sentence next to it, and the sentence is what the next person reads. Two
of those three were only caught because a blind reviewer read the prose
against the code — a thing I had not done myself since writing it.

**HAND A MEASUREMENT OVER WITH ITS EXPIRY ATTACHED** — backend-dev-02's
own diagnosis of the 54-red incident (2026-09-19), and the sharpest form
of this I have:

> "Every INSERT site names current_revision" was a COUNT, and I handed
> it over as though it were an invariant. A count decays the moment
> anyone adds a caller, and the person relying on it is usually working
> in a branch that adds them.

What they said they will write instead: **"as of `<sha>`, seven sites,
all naming the column — a new INSERT site breaks this."** The same claim
with its expiry condition, which tells the reader to re-run it rather
than trust it.

The corollary for anything I write: **a header or comment that repeats
someone else's measurement inherits its staleness silently; one that
states the CONSTRAINT is true whenever it is read.** That is why 0057's
header now describes what the schema enforces instead of citing a count
of callers.

**So re-read every comment in a hunk as the LAST step before committing,
against the code as it now stands, not as it stood when the comment was
written.** The counting ones ("both", "two", "each of the") go stale
silently; prefer a phrasing that survives a fourth item.

Related: [[owed-comment-fix-on-driverapplication-status-tests]] (round
4, still owed), [[an-empty-set-assertion-is-the-weakest-test]] (the same test,
the previous round), [[verify-the-mutation-fired]],
[[a-migration-can-stop-re-applying-when-its-successor-lands]].

*References: a-migration-can-stop-re-applying-when-its-successor-lands, an-empty-set-assertion-is-the-weakest-test, owed-comment-fix-on-driverapplication-status-tests, verify-the-mutation-fired*

*Observed 2026-09-19 (db-admin)*
