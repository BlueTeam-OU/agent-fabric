# The holder's locale, read from holder.json — 2026-10-18

ADR-060 §5 rule 8 makes a holder's locale its `holder.json`'s, with the
login's suffix kept as a fallback until no holder depends on it. Until this
check no store held a `holder.json`: the three holders whose locale is not
English — legal-expert-ge, language-culture-ge and language-culture-ru —
rendered in their language only through the suffix. Whether a real install
renders the same prompt from `holder.json`, before the fallback is removed,
needs a live read-back.

**Run.** 2026-10-18 between about 05:30Z and 05:43Z, on develop-qzapp, main at
0a4382a0 (#295 merged; the fleet distributed at e256eb04, #294). The
coordinator refreshed its mirror of each store and installed with
`fabric-secrets child roles-put --approval
owner-2026-10-17-plan-smooth-dreaming-tide-stage3-holder-json`:
`{"locale": "<ge|ru>", "timezone": "Asia/Tbilisi", "search": {"country":
"ge"}}`, the values each locale's `locale.json` already gave. For
legal-expert-ge, whose directory `roles-put` replaces whole, the set was its
installed Georgian addenda and glosses, taken from the mirror's HEAD, beside
the new file; the addenda's sha256s equal the ones language-culture-ge's two
passes name, so the install carries the same `Reviewed-By` trailers. Each
holder then ran `fabric-secrets sync`, relaunched into a fresh session and
read back from it.

## Result

| holder | role | install commit | `fabric-status` addenda line | headings |
|---|---|---|---|---|
| legal-expert-ge | legal-expert | f82a566 | `store f82a566fe919  addenda commit f82a566fe919` | Georgian ("ვინ ხარ", "გუნდთან მუშაობა", "შენი გრძელვადიანი მეხსიერება"), its addendum's heading too |
| language-culture-ge | language-culture | 1ff0d9d | `store 1ff0d9deead4  addenda commit 1ff0d9deead4` | Georgian, all 12 top-level headings |
| language-culture-ru | language-culture | f9efd9d | `store f9efd9d79822  addenda commit f9efd9d79822` | Russian ("Кто ты", "Работа в команде") |

- No launch refused, and none printed a prompt-drift line: each launch's
  prompt file hashes to the digest it was launched with
  (language-culture-ge: `fabric-status --json` drift null, store_moved and
  addenda_changed false).
- language-culture-ru's session runs with TZ Asia/Tbilisi, from `holder.json`.
- `tools/fabric/lint.py` reports no addenda or locale finding over the
  coordinator's mirrors after the installs.

## Afterwards: language-culture-en

Retiring the fallback showed one more dependant. language-culture-en, whose
locale is English, took its timezone (Asia/Tbilisi) and search country (ge)
from `locale/en/locale.json` because its suffix named that locale; with no
suffix fallback a login without `holder.json` has no timezone or country,
and applying English's facts to every such login would put Asia/Tbilisi on
logins that never had a timezone. Its store got a `holder.json` naming
`en`, Asia/Tbilisi and ge (install commit a954eba, its two English addenda
unchanged beside it), so it keeps both.

## What it decides

Every holder whose locale is not English now names it in `holder.json`, and
renders from it as it did from its login's suffix; so does the one English
holder that took deployment facts from its locale. The suffix fallback has no
remaining dependant: a holder without `holder.json` is English, which is what
the suffix gave every other login (no other suffix names a locale). Stage 6
can remove it.
