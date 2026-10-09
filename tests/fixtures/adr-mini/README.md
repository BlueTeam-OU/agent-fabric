# adr-mini

Two decision records, a digest, a README table and the generated index, as
`tools/fabric/adr.py check` accepts them: the corpus `tests/test_githooks_cli.py`
commits in a scratch repository to test the pre-commit hook, in place of the
organization's records (ADR-045 §5 rule 2), which a checkout without its instance data
lacks. The records are fixtures, not decisions. ADR-001's file name and title are matched by the
test; ADR-000 is there because `adr.py check` reads the pillar table from its section 5 and
counts the records from it. Regenerate `index.json` and the README table with
`python3 tools/fabric/adr.py --root <a tree holding a copy of docs/ and tools/fabric> index --write`.
