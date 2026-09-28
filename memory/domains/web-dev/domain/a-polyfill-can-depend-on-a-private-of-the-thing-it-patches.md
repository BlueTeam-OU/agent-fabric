---
role: "web-dev"
class: domain
topic: "a-polyfill-can-depend-on-a-private-of-the-thing-it-patches"
description: when a dependency bump breaks a DOM API, check whether the test harness — not the library — implements it, by reading a private
tier: 2
knowledge_scope: full
distilled_at: "2026-09-28"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - e1dca96302520931
---

## when a dependency bump breaks a DOM API, check whether the test harness — not the library — implements it, by reading a private

`URL.createObjectURL` is implemented by **neither** jsdom 30.0.1 nor
30.1.0. vitest's jsdom environment supplies it, and gets the bytes by
reading jsdom's private `Symbol(impl)` off a Blob instance to reach
`._buffer` — located by `Object.getOwnPropertySymbols(...)[0]`, under
its own comment "this is cursed". jsdom 30.1.0 stopped exposing that
symbol as an own property of a Blob, so the lookup yields `undefined`
and the failure surfaces as `Cannot read properties of undefined
(reading '_buffer')` — inside our component's line, which makes it read
like our bug.

**Why:** the blast radius of a bump is not bounded by the bumped
package's public API. A harness that patches a gap in a library may be
reading that library's internals to do it, and then a patch-level
release breaks a seam neither side documents.

**How to apply:** when a bump breaks a browser API in tests, first ask
*who implements this API here* — load the library alone in plain node
and call it. If the library never had it, the harness is the dependant
and no amount of reshaping the test's inputs will help; the fix is to
hold the version or move the harness. State the innocent bumps too: in
gzapp #924, vitest 5.0.0 and 5.0.1 carried a byte-identical
`createCompatUtils`, which is what proved jsdom was the sole cause.
Also check whether the manifest range is actually holding anything —
`^30.0.1` permits 30.1.0, so only the lockfile was pinning it.
See [[exhaust-the-upgrade-chain-before-declaring-a-blocker]].

**A hold needs two levers, and they are not redundant** (devex-tooling
corrected me on this, 2026-09-21). I offered the manifest pin as a
possibly-duplicate second statement of the dependabot `ignore` and
worried the two would disagree. Wrong conclusion from the right
worry — they close different reachability paths:

- the `ignore` stops the weekly dependabot PR proposing the held
  version, which a manifest range cannot do (dependabot widens ranges
  itself);
- `~A.B.C` stops a **fresh resolve** — a lockfile-less install, a
  `pnpm update`, a new workspace member — which never consults the
  ignore at all, and which the lockfile only accidentally prevents.

Ship both, and keep them in step with a check rather than with care:
gzapp's `tools/checks/check_dependabot_holds_match_manifests.sh`
matches every `versions: [">=X"]` ignore against every manifest range
for that dependency and fails when one is lifted without the other.
Landed as e546e917 (theirs) + e2d736ce (my supply), merged to main in
**#927 / `9dc8c3c3`** on 2026-09-21. Verified on main: both pins and
the ignore present, the guard green, jsdom resolving 30.0.1.

**How the dependabot PR ended, which is not what anyone planned.**
#924 was never rebased: seven seconds after #927 merged, dependabot
**closed it itself** — "Looks like these dependencies are no longer
being updated by Dependabot, so this is no longer needed." That is its
standard move when a grouped PR's config changes underneath it; it
drops the PR and regenerates the group on schedule rather than
rebasing in place. So the `@dependabot rebase` step everyone was
holding had no target. The regrouped web PR (the other fourteen
updates, without jsdom) arrives on the next Monday run, or sooner if
the owner clicks "Check for updates" — a click only they can make.

*References: exhaust-the-upgrade-chain-before-declaring-a-blocker*

*Observed 2026-09-21 (web-dev)*
