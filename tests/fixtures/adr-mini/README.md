# adr-mini

Two decision records, a digest, a README table and the generated index, as
`tools/fabric/adr.py check` accepts them: the corpus `tests/test_githooks_cli.py`
commits in a scratch repository to test the pre-commit hook, in place of the
organization's records (ADR-045 §5 rule 2), which a checkout without its instance data
lacks. The records are fixtures, not decisions; their file names and titles follow the
two live records the hook's cases name (ADR-001's file name and title are matched by the
test). Regenerate `index.json` and the README table with
`python3 tools/fabric/adr.py --root <a copy of docs/ beside tools/fabric> index --write`.
