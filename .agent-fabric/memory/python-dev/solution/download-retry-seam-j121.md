---
role: "python-dev"
class: solution
topic: "download-retry-seam-j121"
description: "python_pin._download bounded retry (j121, folded on #520): transient set, seams, push credential"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 452957b2e360363b
---

## python_pin._download bounded retry (j121, folded on #520): transient set, seams, push credential

`tools/fabric/python_pin.py` `_download(url, dest, urlopen=, sleep=)` retries 5xx HTTPError, URLError and TimeoutError 3 times (RETRY_BACKOFF 2/5/10 s), one stderr line per retry; 4xx fails at once; "wb" per attempt, dest unlinked on final failure. Test: `download_retry` in tests/test_python_pin.py, five mutations all killed (commit 99e5f668, folded on #520 as 60301fc6).

**Why:** a 504 reddened the stripped nightly's first step (2026-11-08).
**How to apply:** a supply branch is `for/user/<what>`; push needs `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push` (see [[git-signing-key-for-agent-accounts]]). `fabric-jobs switch` refuses until the memory dir changed.

*References: git-signing-key-for-agent-accounts*

*Observed 2026-11-09 (python-dev)*
