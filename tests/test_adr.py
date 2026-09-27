#!/usr/bin/env python3
"""Tests for tools/fabric/adr.py: the real docs/adr/ is clean, and each
rule catches the one mutation it exists for — on a copy under TMPDIR, so
the run leaves nothing behind (run.sh's
leak check)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import adr  # noqa: E402

ZERO = "docs/adr/ADR-000-the-enduring-organization.md"
ONE = "docs/adr/ADR-001-decision-records.md"


def fixture(tmp: str) -> str:
    root = os.path.join(tmp, "fabric")
    shutil.copytree(os.path.join(ROOT, "docs", "adr"), os.path.join(root, "docs", "adr"))
    os.makedirs(os.path.join(root, "projects"))
    shutil.copy(os.path.join(ROOT, "projects", "registry.json"), os.path.join(root, "projects", "registry.json"))
    return root


def edit(root: str, rel: str, old: str, new: str, count: int = 1) -> None:
    p = os.path.join(root, rel)
    s = open(p, encoding="utf-8").read()
    assert old in s, f"fixture drifted: {old!r} not in {rel}"
    open(p, "w", encoding="utf-8").write(s.replace(old, new, count))


def only(root: str, needle: str) -> None:
    f = adr.check(root)
    assert any(needle in x for x in f), f"expected a finding with {needle!r}, got {f}"


def case_the_real_records_are_clean(tmp: str) -> None:
    assert adr.check(ROOT) == [], adr.check(ROOT)


def case_index_is_generated_and_a_stale_one_fails(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, "docs/adr/index.json", '"Decision records"', '"Decision notes"')
    only(root, "index.json: stale")
    edit(root, "docs/adr/README.md", "| Decision records |", "| Decision notes |")
    only(root, "index table is stale")
    adr.write_index(root)
    assert adr.check(root) == [], "index --write repairs both"


def case_numbers_are_contiguous_and_unique(tmp: str) -> None:
    root = fixture(tmp)
    os.rename(os.path.join(root, ONE), os.path.join(root, "docs/adr/ADR-002-decision-records.md"))
    edit(root, "docs/adr/ADR-002-decision-records.md", "# ADR-001 —", "# ADR-002 —")
    only(root, "not contiguous")


def case_heading_and_file_agree(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "# ADR-001 — Decision records", "# ADR-007 — Decision records")
    only(root, "heading says ADR-007")


def case_header_fields_and_statuses(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Scope:** ", "**Scopes:** ")
    only(root, "**Scope:** missing")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, ONE, "**Status:** Accepted", "**Status:** Approved")
    only(root, "not one of Proposed")
    root = fixture(os.path.join(tmp, "c"))
    edit(root, ONE, "**Date:** 2026-09-27", "**Date:** 27 September")
    only(root, "is not YYYY-MM-DD")


def case_accepted_needs_the_owners_word(tmp: str) -> None:
    root = fixture(tmp)
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    s = re.sub(r"^\*\*Ratified:\*\*.*\n", "", s, flags=re.M)
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s)
    only(root, "Accepted without '**Ratified:** owner")


def case_sections_in_order(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "## 3. Alternatives Considered", "## 3. Options")
    only(root, "sections must be, in order")
    root = fixture(os.path.join(tmp, "b"))
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    a, b = s.split("## 4. Rationale", 1)
    r, rest = b.split("## 5. Binding Rules", 1)
    s = a + "## 5. Binding Rules" + rest.replace("## 6. Consequences", "## 4. Rationale" + r + "## 6. Consequences", 1)
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s)
    only(root, "sections must be, in order")


def case_pillars_come_from_adr_000(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Pillar:** P2", "**Pillar:** P9")
    only(root, "P9 is not in ADR-000 §5")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, ZERO, "| P7 | Sustainable operation |", "| XX | Sustainable operation |")
    edit(root, ONE, "**Pillar:** P2", "**Pillar:** P7")
    only(root, "P7 is not in ADR-000 §5")


def case_evidence_must_exist(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Pillar:** P2", "**Pillar:** P2\n**Evidence:** docs/live-checks/nowhere.md")
    only(root, "Evidence:** docs/live-checks/nowhere.md does not exist")


def case_citations_resolve_but_another_projects_are_not_ours(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nSee ADR-044.\n")
    only(root, "cites ADR-044, which does not exist")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nLike gzapp's ADR-044 and gzapp ADR-059.\n")
    assert adr.check(root) == [], "a citation named with another registered project is that project's"


def amend(root: str, date: str = "2026-09-28", title: str = "a rule moved") -> None:
    adr.cmd_amend(root, "1", title, date)
    edit(root, "docs/adr/DIGEST.md", "- Keywords: ADR, amendment,", f"- A {date} — {title}.\n- Keywords: ADR, amendment,")
    adr.write_index(root)


def case_an_amendment_is_the_triple(tmp: str) -> None:
    root = fixture(tmp)
    amend(root)
    assert adr.check(root) == [], f"amend + DIGEST bullet + index is clean: {adr.check(root)}"
    root = fixture(os.path.join(tmp, "b"))
    amend(root)
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s.replace("| 2026-09-28 | a rule moved |", "| 2026-09-29 | a rule moved |"))
    only(root, "amendment note(s) with no table row")
    only(root, "table row(s) with no history note")


def case_one_amendment_heading_form(tmp: str) -> None:
    root = fixture(tmp)
    amend(root)
    edit(root, "docs/adr/history/ADR-001-amendments.md", "### Amendment 2026-09-28 — a rule moved", "### Amendment (i) — 2026-09-28 — a rule moved")
    only(root, "is not '### Amendment YYYY-MM-DD — Title'")


def case_no_amendment_note_inside_the_record(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "## 6. Consequences", "### Amendment 2026-09-28 — inline\n\n## 6. Consequences")
    only(root, "an '### Amendment' heading in the ADR itself")


def case_orphan_history_files(tmp: str) -> None:
    root = fixture(tmp)
    os.makedirs(os.path.join(root, "docs/adr/history"), exist_ok=True)
    open(os.path.join(root, "docs/adr/history/ADR-009-amendments.md"), "w").write("# x\n\n### Amendment 2026-09-28 — y\n")
    only(root, "history/ADR-009-amendments.md: belongs to no ADR")


def case_superseded_needs_a_point_map_to_a_real_record(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Status:** Accepted", "**Status:** Superseded (→ ADR-000)")
    edit(root, "docs/adr/DIGEST.md", "### ADR-001 — Decision records (Accepted)", "### ADR-001 — Decision records (Superseded)")
    adr.write_index(root)
    only(root, "Superseded without a point map")
    edit(root, ONE, "## 1. Context and Problem", "Point map: §5 rule 1 → ADR-000 §5 rule 4.\n\n## 1. Context and Problem")
    assert not any("point map" in x for x in adr.check(root)), adr.check(root)
    edit(root, ONE, "(→ ADR-000)", "(→ ADR-040)")
    only(root, "superseded by ADR-040, which does not exist")


def case_the_digest_follows_the_records(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, "docs/adr/DIGEST.md", "### ADR-001 — Decision records (Accepted)", "### ADR-001 — Decision records (Proposed)")
    only(root, "DIGEST.md: ADR-001 reads 'Decision records' (Proposed)")
    root = fixture(os.path.join(tmp, "b"))
    s = open(os.path.join(root, "docs/adr/DIGEST.md"), encoding="utf-8").read()
    open(os.path.join(root, "docs/adr/DIGEST.md"), "w", encoding="utf-8").write(s.split("### ADR-001")[0])
    only(root, "no entry '### ADR-001")
    root = fixture(os.path.join(tmp, "c"))
    adr.cmd_amend(root, "1", "a rule moved", "2026-09-28")
    adr.write_index(root)
    only(root, "amendment bullets [] are not its history ['2026-09-28']")


def case_new_takes_the_next_number(tmp: str) -> None:
    root = fixture(tmp)
    path = adr.cmd_new(root, "a-new-thing", "A new thing")
    assert path.endswith("ADR-002-a-new-thing.md"), path
    assert open(path, encoding="utf-8").read().startswith("# ADR-002 — A new thing")


def case_lookup_reads_the_digest(tmp: str) -> None:
    hits = adr.cmd_lookup(ROOT, ["ratify"])
    assert hits and hits[0].startswith("### ADR-001"), hits


def git(cwd: str, *a: str, msg: str | None = None) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", cwd, *a] + (["-m", msg] if msg else []), check=True, capture_output=True, env=env)


def case_range_check_refuses_an_unrecorded_body_edit(tmp: str) -> None:
    root = fixture(tmp)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "core.hooksPath", "/dev/null")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="base")
    base = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "commit", "-qa", msg="reword")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "no Amendments row" in f[0], f
    git(root, "commit", "-q", "--amend", msg="reword\n\nADR-Editorial: a word, nothing decided")
    assert adr.range_check(root, base) == [], "the trailer records an editorial edit"
    root2 = fixture(os.path.join(tmp, "b"))
    git(root2, "init", "-q", "-b", "main"); git(root2, "config", "core.hooksPath", "/dev/null")
    git(root2, "add", "-A"); git(root2, "commit", "-q", msg="base")
    base2 = subprocess.run(["git", "-C", root2, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    amend(root2)
    edit(root2, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root2, "add", "-A"); git(root2, "commit", "-q", msg="amend ADR-001")
    assert adr.range_check(root2, base2) == [], "an amendment row records the body edit"
    edit(root2, ONE, "**Ratified:** owner, 2026-09-27", "**Ratified:** owner, 2026-09-28")
    git(root2, "commit", "-qa", msg="ratified")
    assert adr.range_check(root2, base2) == [], "a header-only change (ratification) is not a body edit"


def main() -> int:
    cases = [v for k, v in globals().items() if k.startswith("case_")]
    failures = 0
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                case(tmp)
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
