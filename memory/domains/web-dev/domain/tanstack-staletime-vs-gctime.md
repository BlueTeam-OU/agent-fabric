---
role: "web-dev"
class: domain
topic: "tanstack-staletime-vs-gctime"
description: "TanStack Query: what never serving a read from cache takes (staleTime and gcTime), and what unset refetchOn* options mean"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "web-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 23773202381c4f0c
---

## TanStack Query: what never serving a read from cache takes (staleTime and gcTime), and what unset refetchOn* options mean

In TanStack Query v5, `staleTime` decides whether a refetch happens.
`gcTime` decides whether a cached entry exists to display while that
refetch is in flight. With `staleTime: 0` and the default `gcTime`, the
cached data is still rendered during the refetch. That is
stale-while-revalidate: the old data is shown, then a new request is made.
To never display cached data, set `staleTime: 0` AND `gcTime: 0`.
Measured with a probe against the installed library: with the default
gcTime the cached value was shown, with gcTime 0 nothing was shown.

The unset `refetchOnWindowFocus`, `refetchOnReconnect` and
`refetchOnMount` options do not mean "never" or "always". They mean
"refetch if stale": `shouldFetchOn` in query-core's `queryObserver.js`
resolves `value !== false && isStale(...)`, checked at 5.104.0. So
`staleTime: 0` turns every unset trigger into "always". Where each request
has a side effect (for example, an audit row per read), set those options
explicitly to `false` on the query itself. Do not rely on an app-wide
default that someone may change for other lists.

The cost of gcTime 0 on a paged list: each page turn shows its loading
state, because no cached page can fill the gap.

**How to apply:** when a contract says "never served from cache" or "one
display, one request", set all four options on the hook. Test it with the
pattern in [[test-setup-must-separate-wrong-impl]].

Sources (GZCoord): 01a0c23b-d1a5-772b-8408-ddfdf25cd4e4,
01a0c4e1-6d6b-7dc5-a839-9449dac3edde, 01a0c232-f716-717b-8618-5fe5473c6f08.
In use: gzapp apps/admin_web/src/features/registries/api.ts (origin/main
7392f0a17).

*References: test-setup-must-separate-wrong-impl*

*Observed 2026-10-18 (web-dev)*
