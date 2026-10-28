# 2026-10-28 — what a `cpu` slot's environment does to a dotnet build

Run by fabric-coordinator on develop-qzapp (10 vCPU, load 6–11 during the runs), with .NET SDK 10.0.112 (`/usr/bin/dotnet`). The question comes from agent-fabric ADR-010, amendment 2026-10-28. Item 2 says it is a guess until read back that `DOTNET_PROCESSOR_COUNT=J` bounds MSBuild's parallelism and the test runner's. Item 6 assumes that `MSBUILDDISABLENODEREUSE=1`, `DOTNET_CLI_USE_MSBUILD_SERVER=0` and `UseSharedCompilation=false` leave no process behind that would inherit the slot's descriptor. If the count variable does not bound MSBuild, the shim adds `-m:J`.

## What was measured

The workload was a synthetic solution of eight class libraries. Each library's build runs `sleep 6`, so the number of `sleep 6` processes alive at once is the number of projects being built at once. A `dotnet build all.slnx` followed a `dotnet clean` and `dotnet build-server shutdown`, and the build's processes were sampled from `/proc` every 0.3 s. A console app printed `Environment.ProcessorCount`.

| case | environment | projects at once | MSBuild nodes (peak) | wall | left 2 s after |
|---|---|---|---|---|---|
| control | none | 8 | 7 | 22.4 s | 7 nodes `/nodeReuse:true`, and a `VBCSCompiler` started during this run |
| switches only | the three switches, no count | 8 | 7 | 21.3 s | nothing |
| slot, J=5 | switches + `DOTNET_PROCESSOR_COUNT=5` | 5 | 4 | 27.6 s | nothing |
| slot, J=2 | switches + `DOTNET_PROCESSOR_COUNT=2` | 2 | 1 | 45.0 s | nothing |

`Environment.ProcessorCount` was 10 unset and 5 with `DOTNET_PROCESSOR_COUNT=5`.

The control ran last, because it leaves processes behind. The three switched runs before it started no `VBCSCompiler`: the only one on the account started at 13:28:35, inside the control's run. The control's nodes and compiler server were stopped by pid afterwards.

## What it decides

- `DOTNET_PROCESSOR_COUNT=J` bounds a build to J projects at once: the entry process plus J − 1 worker nodes. The switches alone do not bound it (eight at once, as in the control). The shim needs no `-m:J`.
- Test frameworks that size their parallelism from `Environment.ProcessorCount` (xUnit's default) see J. `dotnet test` builds its projects through the same MSBuild nodes.
- With the three switches, a build leaves nothing behind. Without them it leaves seven reuse nodes and a compiler server. Under item 6's exec those eight processes would inherit the slot's descriptor and hold the slot after the build. The switches are needed, not just tidy.

## Not verified

- A real project's `dotnet test` (gzapp's), measured under the shim. This used a synthetic solution, and the shim is not yet installed on the host.
- Test frameworks that do not read `ProcessorCount`: NUnit's `LevelOfParallelism`, and MSTest's `Parallelize` with an explicit worker count.
- The effect on load. That is the rollout's controlled measurement (the amendment's "Measured, with a control").
