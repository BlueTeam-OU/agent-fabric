---
role: "python-dev"
class: domain
topic: "git-version-dependent-fixtures"
description: "fixtures and assertions that depend on the git version — empty-clone origin/HEAD, stderr wording — pass locally and fail the CI debian/fedora legs"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6ec3743799c9c77f
---

## fixtures and assertions that depend on the git version — empty-clone origin/HEAD, stderr wording — pass locally and fail the CI debian/fedora legs

A git fixture or assertion tuned to the local git passes here and fails a CI leg on another distro's git.

- A clone of an *empty* origin gets no `origin/HEAD`; git 2.48+ sets it on a later fetch (followRemoteHEAD), 2.47 never does. A fixture that clones before the first push runs `git remote set-head origin main` after the push, as a clone of a non-empty origin would have it; cases that need it unset do so on purpose.
- git's stderr wording moves between versions (a gone gitdir: "not a git repository" on 2.55, "gitfile does not point to a valid repository" on 2.56). A test asserts the tool's own quoted line (`git rev-parse failed: fatal:`), never git's exact words; code that reads git's words runs it under `LC_ALL=C` and refuses on an unrecognised text.

**Why:** two CI legs (debian git 2.47, fedora git 2.56) failed on suites green locally at 2.55; the tool was right both times, the fixture or assertion assumed a git.

**How to apply:** when a test builds a repo or reads git's text, run it once in the oldest CI image (debian:stable-slim under podman) before delivery, and sweep the same fixture shape in sibling suites (test_session_start had it too).

*Observed 2026-10-18 (python-dev)*
