#!/usr/bin/env python3
"""tools/fabric/lint_rules/hidden.py: hidden Unicode in text an agent reads (j305), judged by tools/fabric/hidden_unicode.py.

Stdlib only; runnable as `python3 tests/test_lint_hidden.py`. Each case builds a throwaway agent-fabric root with tests/test_lint.py's
make_base, makes it a git repository (the rule reads `git ls-files`) and runs lint on it. **Each names the mutation it kills**:

  charter_is_judged        <- hidden_unicode_findings not wired into lint.main; the scan skipped
  skill_is_judged          <- agent_text.is_agent_text narrowed to identities/roles/*/charter.md
  project_slice_is_labelled <- the working copies not walked; the `<pid>:` label dropped
  cr_is_refused            <- the file opened in text mode with universal newlines (a CR becomes an LF)
  emoji_zwj_passes         <- the scan replaced by a bare Cf test
  only_agent_text_is_judged <- is_agent_text widened to every file, or the project branch widened past .agent-fabric/
  not_utf8_is_one_finding  <- the UnicodeDecodeError left to escape
  locale_value_is_judged   <- _control_in_value reduced to the old C0/C1/bidi class (a ZWSP and a tag character pass)
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile

from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
from git_env import git_env  # noqa: E402
from test_lint import PROJECT, ident, make_base, proj, run_lint, wc_demo, write  # noqa: E402

TMP = tempfile.mkdtemp(prefix="lint-hidden-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

ZWSP = "​"
RLO = "‮"
TAG_A = "\U000E0041"
HEAD = "hidden Unicode in text an agent reads (tools/fabric/hidden_unicode.py)"


def track(*repos: str) -> None:
    for repo in repos:
        if os.path.isdir(repo):
            subprocess.run(["git", "-C", repo, "init", "-q"], check=True, env=git_env())
            subprocess.run(["git", "-C", repo, "add", "-A"], check=True, env=git_env())


def lint(fabric: str) -> tuple[int, str]:
    track(fabric, wc_demo(fabric))
    return run_lint(fabric)


def hits(out: str) -> list[str]:
    return [line.strip() for line in out.splitlines() if HEAD in line]


def fresh() -> str:
    return make_base(tempfile.mkdtemp(dir=TMP))


def case_charter_is_judged() -> None:
    fabric = fresh()
    charter = ident(fabric, "charter.md")
    with open(charter, encoding="utf-8") as fh:
        text = fh.read()
    write(charter, text.replace("\n", f"\nab{ZWSP}cd\n", 1))
    code, out = lint(fabric)
    assert code == 1, out
    line = text[: text.index("\n") + 1].count("\n") + 1
    want = f"identities/roles/web-dev/charter.md:{line}:3: U+200B ZERO WIDTH SPACE (format): {HEAD}"
    assert want in out, f"{want!r} not in:\n{out}"


def case_skill_is_judged() -> None:
    fabric = fresh()
    write(ident(fabric, "skills", "x", "SKILL.md"), f"---\nname: x\ndescription: d\n---\n\nbody {RLO}\n")
    code, out = lint(fabric)
    assert code == 1 and any(h.startswith("identities/roles/web-dev/skills/x/SKILL.md:6:6: U+202E") for h in hits(out)), out


def case_project_slice_is_labelled() -> None:
    fabric = fresh()
    write(proj(fabric, "INDEX.md"), f"# Index\n{TAG_A}\n")
    code, out = lint(fabric)
    assert any(h.startswith(f"{PROJECT}:.agent-fabric/memory/web-dev/INDEX.md:2:1: U+E0041 ") for h in hits(out)), out


def case_cr_is_refused() -> None:
    fabric = fresh()
    with open(os.path.join(fabric, "AGENTS.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write("one\r\ntwo\n")
    code, out = lint(fabric)
    assert any(h.startswith("AGENTS.md:1:4: U+000D ") for h in hits(out)), out


def case_emoji_zwj_passes() -> None:
    fabric = fresh()
    write(os.path.join(fabric, "AGENTS.md"), "family \U0001F468‍\U0001F469‍\U0001F467 ok\n")
    code, out = lint(fabric)
    assert hits(out) == [], out


def case_only_agent_text_is_judged() -> None:
    fabric = fresh()
    write(os.path.join(fabric, "tools", "x.py"), f"# {ZWSP}\n")
    write(os.path.join(wc_demo(fabric), "docs", "adr", "ADR-057.md"), f"project truth {ZWSP}\n")
    write(os.path.join(wc_demo(fabric), "CLAUDE.md"), f"project truth {ZWSP}\n")
    write(os.path.join(wc_demo(fabric), "src", "x.json"), json.dumps({"a": ZWSP}))
    write(os.path.join(wc_demo(fabric), ".agent-fabric", "notes.txt"), f"a {ZWSP}\n")
    write(ident(fabric, "notes.txt"), f"a {ZWSP}\n")
    code, out = lint(fabric)
    assert hits(out) == [], f"text outside the fabric's remit was judged:\n{out}"


def case_not_utf8_is_one_finding() -> None:
    fabric = fresh()
    with open(os.path.join(fabric, "AGENTS.md"), "wb") as fh:
        fh.write(b"caf\xe9\n")
    code, out = lint(fabric)
    bad = [line for line in map(str.strip, out.splitlines()) if line.startswith("AGENTS.md: cannot be read as UTF-8")]
    assert len(bad) == 1 and "Traceback" not in out, out


def case_locale_value_is_judged() -> None:
    """A dictionary value is held to the scanner, and to one line: tests/test_lint.py pins the C0/C1/bidi members; these are the
    ones only hidden_unicode.py knows."""
    fabric = fresh()
    default_path = os.path.join(fabric, "communication", "gzcoord", "i18n", "en-US.json")
    write(default_path, json.dumps({"inbox.head": "hello"}))
    for bad in (ZWSP, TAG_A, "﻿"):
        write(default_path, json.dumps({"inbox.head": f"hel{bad}lo"}))
        code, out = run_lint(fabric)
        assert code == 1 and "inbox.head carries a control character (U+" in out, f"{bad!r} passed:\n{out}"


CASES = [case_charter_is_judged, case_skill_is_judged, case_project_slice_is_labelled, case_cr_is_refused, case_emoji_zwj_passes,
         case_only_agent_text_is_judged, case_not_utf8_is_one_finding, case_locale_value_is_judged]


def main() -> int:
    failures = 0
    for case in CASES:
        try:
            case()
            print(f"  ok   {case.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
