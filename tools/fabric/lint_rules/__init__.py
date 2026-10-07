"""tools/fabric/lint_rules/ — the rule modules of tools/fabric/lint.py, the corpus
linter. That module is the command; it loads this package by path as
fabric_lint_rules, never through sys.path, and each part is one family of
rules or what several share. Never named lint/: a package beside lint.py
would shadow the module on import."""
