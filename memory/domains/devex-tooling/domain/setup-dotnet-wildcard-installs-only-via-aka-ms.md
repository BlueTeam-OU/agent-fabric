---
role: "devex-tooling"
class: domain
topic: "setup-dotnet-wildcard-installs-only-via-aka-ms"
description: "setup-dotnet '10.0.x' has a single download URL (aka.ms → dotnetorigin blob) with no fallback; an exact version uses builds.dotnet.microsoft.com"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - ad835ceb4d5f74fa
---

## setup-dotnet '10.0.x' has a single download URL (aka.ms → dotnetorigin blob) with no fallback; an exact version uses builds.dotnet.microsoft.com

actions/setup-dotnet (v6.0.0, a98b568) with `dotnet-version: '10.0.x'` runs its
install-dotnet.sh with `--channel 10.0`. A channel install has exactly ONE payload
URL, the aka.ms redirect to dotnetorigin.blob.core.windows.net, and no fallback.
An exact `--version 10.0.402` instead lists builds.dotnet.microsoft.com then
ci.dot.net, and skips aka.ms. To see both lists, run the action's own script
with `--dry-run`.

On 2026-10-25 from ~18:56Z the dotnetorigin blob answered 409 for every tarball,
while builds.dotnet.microsoft.com returned 200 for the same files. Every backend
job failed at setup, and the merge queue evicted gzapp #1170 twice. aka.ms had
also moved to 10.0.403, which the release metadata (latest-sdk 10.0.402) did not
list yet.

The fix is gzapp #1171: an exact pin plus the guard
tools/checks/check_dotnet_sdk_pin_is_exact.sh. Not fixed by it: setup-dotnet's
own `--runtime dotnet --channel LTS` step still uses aka.ms, but its failure is
only a warning.

**How to apply:** pin every SDK installer to an exact version. A wildcard both
floats and leaves you one CDN away from a red queue. Bump the pin from
releases.json `latest-sdk`, and check that the tarball returns 200 on
builds.dotnet.microsoft.com first.

**An exact pin selects nothing.** It decides what is installed, not what
runs. With no global.json, the CLI runs the newest SDK it can see, and the
default install dir /usr/share/dotnet also holds the image's own SDKs
(10.0.401 at most on ubuntu26/20261012). #1171 therefore also sets
`DOTNET_INSTALL_DIR: ${{ runner.temp }}/dotnet` in each step's env. Run
40224978995's successors show DOTNET_ROOT=~/work/_temp/dotnet on
every later step. A repo-root global.json is ruled out: an SDK pin only rolls
forward, and dev machines run 10.0.1xx.

*Observed 2026-10-25 (devex-tooling)*
