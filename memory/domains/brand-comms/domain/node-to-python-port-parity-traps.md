---
role: "brand-comms"
class: domain
topic: "node-to-python-port-parity-traps"
description: "Porting a Node script to Python (ADR-040 Wave 10): where the two runtimes differ silently, and how to run the old script as an oracle without touching the clone."
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "brand-comms-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 6845bcbd59e8cbea
---

## Porting a Node script to Python (ADR-040 Wave 10): where the two runtimes differ silently, and how to run the old script as an oracle without touching the clone.

Differences that read alike and are not, each of which broke the
gzapp.decks port:
- `spawnSync` of a missing binary returns `status: null`, which callers
  treat as a failure and move on from. `subprocess.run` raises. Route
  every external command through one wrapper that returns a failed result.
- JavaScript truthiness: `{}` and `[]` are truthy, while Python's `not {}`
  is True. Compare with `is None`.
- `path.join` joins an absolute part and resolves `../`. `os.path.join`
  drops what precedes an absolute part and resolves nothing. Use
  `normpath("/".join(parts))`.
- `readdirSync` is sorted byte-wise (libuv), so `sorted()` matches it.
  `localeCompare` is ICU order: `_` before `-`, then digits, then letters,
  lower case before upper.
- `Number()` accepts `0x`, `0o`, `0b` and `Infinity`, and reads `""` as 0.
  `float()` accepts `inf` and `1_0`. A huge hex literal is Infinity, not
  an OverflowError.
- `RegExp.test(x)` coerces a non-string with `String()`. Python crashes
  on it.
- `\p{Script=…}` has no stdlib equivalent. The `unicodedata` name
  approximates it and misreads about 750 code points.
- `open(p, "w")` truncates before a read in the same expression, so read
  first, then write.
- Text mode turns `\r\n` into `\n`. Use `newline=""` for byte parity.
- Importing a sibling module writes `__pycache__/`, which dirties the
  tree. Set `sys.dont_write_bytecode = True`.

**How to apply:** build the oracle as a fresh `git worktree` per run,
with the old script restored from the base commit, and a stub for any
renderer. Pass excludes through `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0=core.excludesFile`
in the run's environment, never through `info/exclude`: every worktree
shares that file, and writing to it hid my new files from git in my own
clone. Tags made in a worktree are the clone's own, so delete any a test
creates.

*Observed 2026-10-19 (brand-comms)*
