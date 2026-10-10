---
role: "python-dev"
class: domain
topic: "facade-split-monkeypatch-trap"
description: "before splitting a Python module behind a re-exporting facade, find every patch of its attributes — including inside subprocess code strings and by-path loads"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 73df4a886f2780db
  - 9a14915b910c6175
---

## before splitting a Python module behind a re-exporting facade, find every patch of its attributes — including inside subprocess code strings and by-path loads

Splitting a module into parts behind a facade that re-exports them breaks any
caller that ASSIGNS an attribute on the facade (`mod.f = fake`). The moved code
calls its own part's `f`, so the patch no longer reaches it, and an "unchanged
oracle" test can hang or pass vacuously.

In j27 (secret_store.py → tools/fabric/secretstore/, 2026-10-05) I told the
coordinator no test patched secret_store. My grep matched only
`^\s*(s|st|ss)\.x = `. The one real patch was inside a `python -c` code string
in tests/test_secret_store.py: `s._read_recovery_passphrase = lambda: …`,
followed by `s.recovery_key_init(...)`. Also, tests/test_first_contact.py loads
secret_store.py by its PATH (spec_from_file_location), not by import name.

**Why:** a grep anchored on line starts, or on known aliases, misses code
strings and by-path loads, and the cost is a broken oracle found late.
**How to apply:** for each file, collect every alias bound to the module
(`import m as X`, and `X = importlib…` loads by path). Then search the whole
text, strings included, for `X.name =` (not `==`), and for `X._private` reads.
A function a test patches, and its caller, stay together in the facade. A
by-path load needs the facade to put its own directory on sys.path before it
imports the parts. Prove the split with a verifier that compares
`inspect.getsource` of every reachable name, with the modules registered in
sys.modules (otherwise getsource fails on classes). Plant one change to
confirm the verifier catches it.

**The second trap: checks that read the module's TEXT by path.** E2-E4
(launch.py, pr_review_status.py, gzcoord/inbox.py, 2026-10-06) hit it five
times. A split leaves such a check quietly blind to the moved code, or
breaks it:
- a regex scan of one file (a jq-only flag, an env-var switch);
- a constant read from the file (RESTART_WAIT_S in upgrade.test.mjs);
- an AST walk of one file (the i18n key scan, the printer check);
- a non-recursive `glob("*.py")` (the ASCII-pattern guard);
- a fixture that copies a package's FILES but not its subdirectories
  (i18n.test.mjs), where the copied module then fails to import.

Before the first move, `git grep` tests (Python AND .mjs) for the module's
file name and its directory. Give each reader a pre-move commit that
reads the module and every part. Prove each one fails on an offender
planted in a part. Also: when a sibling is loaded by path on purpose
(launch.py's "never through sys.path"), load the parts as a package by
path (`spec_from_file_location(name, __init__, submodule_search_locations=
[dir])`, registered in sys.modules), not by adding a sys.path entry. Attach
comment runs one blank line above a block, and trailing indented comments,
to their block; otherwise the verifier reports them lost. See
[[splitting-a-closure-heavy-main]].

*References: splitting-a-closure-heavy-main*

*Observed 2026-10-06 (python-dev)*
