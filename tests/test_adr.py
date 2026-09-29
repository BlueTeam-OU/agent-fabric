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
    # A record's Evidence paths must exist (adr.check), so the copy carries them.
    adrs, _ = adr.load(ROOT)
    for ev in {e.strip() for a in adrs for e in a["fields"].get("Evidence", "").split(",") if e.strip()}:
        src, dst = os.path.join(ROOT, ev), os.path.join(root, ev)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, dst)
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
    only(root, "is not a YYYY-MM-DD date")


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
    open(os.path.join(root, "docs/adr/history/ADR-999-amendments.md"), "w").write("# x\n\n### Amendment 2026-09-28 — y\n")
    only(root, "history/ADR-999-amendments.md: belongs to no ADR")


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
    # A date no real amendment will carry, so the case follows the corpus:
    # the history gains it, the DIGEST bullets do not.
    adr.cmd_amend(root, "1", "a rule moved", "2099-01-02")
    adr.write_index(root)
    only(root, "'2099-01-02']")


def case_new_takes_the_next_number(tmp: str) -> None:
    root = fixture(tmp)
    nxt = f"ADR-{len(adr.load(root)[0]):03d}"
    path = adr.cmd_new(root, "a-new-thing", "A new thing")
    assert path.endswith(f"{nxt}-a-new-thing.md"), path
    assert open(path, encoding="utf-8").read().startswith(f"# {nxt} — A new thing")


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
    assert len(f) == 1 and "no new Amendments row" in f[0], f
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


def case_header_dates_keep_their_own_pattern(tmp: str) -> None:
    # The body's date scan must not replace the header's anchored pattern
    # (review thread on #53): any real calendar date is a valid header date,
    # and nothing may trail it.
    assert adr.real_date("2100-01-01") and adr.real_date("1999-12-31")
    assert not adr.real_date("2026-09-27-x") and not adr.real_date("2026-09-27 ")
    root = fixture(tmp)
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nSince 2100-01-01, every record says so.\n")
    only(root, "§6 dates something (2100-01-01)")


def case_the_date_rules_hold_at_their_edges(tmp: str) -> None:
    # Review of #53: the anchor is the pattern's, not only fromisoformat's;
    # an amendment's date is a calendar date; an attribution may break
    # between "the" and "owner"; a dated path of any kind, bare or in a
    # fenced block, is not a dated sentence.
    assert adr.DATE_RE.match("2026-09-27-x") is None
    root = fixture(tmp)
    try:
        adr.main(["--root", root, "amend", "--date", "2026-02-30", "1", "x"])
        raise AssertionError("amend took an impossible date")
    except SystemExit as e:
        assert "YYYY-MM-DD" in str(e), e
    root = fixture(os.path.join(tmp, "b"))
    amend(root)
    h = os.path.join(root, "docs/adr/history/ADR-001-amendments.md")
    s = open(h, encoding="utf-8").read()
    open(h, "w", encoding="utf-8").write(s.replace("### Amendment ", "### Amendment 2026-02-30 — ghost\n\n### Amendment ", 1))
    assert any("2026-02-30" in f and "not a date" in f for f in adr.check(root)), adr.check(root)
    root = fixture(os.path.join(tmp, "c"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nKept as commit 04f4b1c (the\n  owner's rule).\n")
    only(root, "an inline attribution")
    root = fixture(os.path.join(tmp, "d"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nKept (The owner, 2026-09-13).\n")
    assert any("inline attribution" in f for f in adr.check(root)), adr.check(root)
    root = fixture(os.path.join(tmp, "e"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nSee docs/live-checks/2026-09-25-x.md and\nruntime/state/2026-09-25-y.json.\n\n```text\nat 2026-09-25 the log said so\n```\n")
    assert adr.check(root) == [], adr.check(root)


def case_impossible_dates_and_escaping_evidence(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Date:** 2026-09-27", "**Date:** 2026-13-45")
    only(root, "'2026-13-45' is not a YYYY-MM-DD date")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, ONE, "**Pillar:** P2", "**Pillar:** P2\n**Evidence:** /etc/passwd, ../../outside.md")
    only(root, "/etc/passwd is not a path inside the repository")
    only(root, "../../outside.md is not a path inside the repository")


def case_duplicate_numbers(tmp: str) -> None:
    root = fixture(tmp)
    shutil.copy(os.path.join(root, ONE), os.path.join(root, "docs/adr/ADR-001-a-twin.md"))
    only(root, "number(s) used twice: ADR-001")


def case_amendments_bookkeeping_edges(tmp: str) -> None:
    root = fixture(tmp)
    amend(root)
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    s = s.replace("\n## Amendments\n", "\n## Amendments-moved\n", 1)
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s)
    only(root, "amended, but no '## Amendments' section")
    root = fixture(os.path.join(tmp, "b"))
    amend(root)
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    head, amendments = s.split("\n## Amendments\n", 1)
    refs = head.index("\n## References")
    s = head[:refs] + "\n## Amendments\n" + amendments.rstrip("\n") + "\n" + head[refs:] + "\n"
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s)
    only(root, "'## Amendments' must be the last section")
    root = fixture(os.path.join(tmp, "c"))
    os.makedirs(os.path.join(root, "docs/adr/history"), exist_ok=True)
    open(os.path.join(root, "docs/adr/history/ADR-001-amendments.md"), "w").write("# ADR-001 — amendments\n")
    only(root, "no amendment in it — remove it")


def case_superseded_needs_an_arrow(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, ONE, "**Status:** Accepted", "**Status:** Superseded")
    only(root, "Superseded without '(→ ADR-NNN)'")


def case_no_inline_attribution(tmp: str) -> None:
    # Who decided and when are the header's and the history's; the body
    # states the decision (the owner's rule for records).
    root = fixture(tmp)
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nKept apart (the owner,\n2026-09-13) on purpose.\n")
    only(root, "an inline attribution '(the owner,")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, "docs/adr/DIGEST.md", "### ADR-001 —", "- Stray (the CEO) bullet.\n\n### ADR-001 —")
    only(root, "DIGEST.md: an inline attribution '(the CEO)")


def case_dates_only_in_the_context(tmp: str) -> None:
    # A record reads current: a date may date an incident in §1, and the
    # engine's markers and dated paths stay; the rules carry none.
    root = fixture(tmp)
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nSince 2026-09-25, every record says so.\n")
    only(root, "§6 dates something (2026-09-25)")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, ONE, "## 6. Consequences", "## 6. Consequences\n\nSee `docs/live-checks/2026-09-25-x.md` and\n[the note](../2026-09-20-y.md); rule 3 (A 2026-09-26).\n")
    edit(root, ONE, "## 2. Decision", "## 2. Decision\n\n**§5 rule 9 — withdrawn** (Amendment 2026-09-26).\n")
    assert adr.check(root) == [], adr.check(root)
    root = fixture(os.path.join(tmp, "c"))
    edit(root, ONE, "## 1. Context and Problem", "## 1. Context and Problem\n\nOn 2026-09-19 the disk filled.\n")
    assert adr.check(root) == [], adr.check(root)


def case_digest_orphan_and_readme_markers(tmp: str) -> None:
    root = fixture(tmp)
    edit(root, "docs/adr/DIGEST.md", "### ADR-001 —", "### ADR-999 — Ghost (Accepted)\n\n### ADR-001 —")
    only(root, "an entry for ADR-999, which does not exist")
    root = fixture(os.path.join(tmp, "b"))
    edit(root, "docs/adr/README.md", adr.INDEX_START, "")
    only(root, "no <!-- adr-index:start -->")


def commit_base(root: str) -> str:
    git(root, "init", "-q", "-b", "main"); git(root, "config", "core.hooksPath", "/dev/null")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="base")
    return subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def case_range_check_takes_a_git_range_and_refuses_a_bad_one(tmp: str) -> None:
    """`range-check A..B` is how git spells a range: it once crashed git
    rev-list as "A..B..HEAD". Taken as base and head; a range git cannot
    read, or a range with a second head, is refused without a traceback."""
    root = fixture(tmp)
    git(root, "init", "-q", "-b", "main"); git(root, "config", "core.hooksPath", "/dev/null")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="base")
    base = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    tool = os.path.join(ROOT, "tools", "fabric", "adr.py")
    cli = lambda *a: subprocess.run([sys.executable, tool, "--root", root, "range-check", *a], capture_output=True, text=True)  # noqa: E731
    r = cli(f"{base}..HEAD")
    assert r.returncode == 0 and "clean" in r.stdout and "Traceback" not in r.stderr, r.stdout + r.stderr
    r = cli("nosuchref..HEAD")
    assert r.returncode == 2 and "could not read" in r.stderr and "Traceback" not in r.stderr, r.stderr
    r = cli(f"{base}..HEAD", "HEAD")
    assert r.returncode == 2 and "not both" in r.stderr, r.stderr
    r = cli("..HEAD")
    assert r.returncode == 2 and "no base" in r.stderr, r.stderr


def case_range_check_counts_only_new_amendment_rows(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    edit(root, ONE, "## 6. Consequences", "| 2026-09-19 | disk full | lease added |\n\n## 6. Consequences")
    git(root, "commit", "-qa", msg="a dated row inside the body is not an amendment")
    assert len(adr.range_check(root, base)) == 1, "a dated table row outside ## Amendments hid a body edit"
    root = fixture(os.path.join(tmp, "b"))
    amend(root)
    base = commit_base(root)
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    edit(root, ONE, "| (say which § and rule) |", "| §3 |")
    git(root, "commit", "-qa", msg="an edited Effect cell is not a new row")
    assert len(adr.range_check(root, base)) == 1, "an edited existing row counted as an amendment"


def case_range_check_follows_renames_and_passes_header_only(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    git(root, "mv", ONE, "docs/adr/ADR-001-decision-records-renamed.md")
    edit(root, "docs/adr/ADR-001-decision-records-renamed.md", "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "commit", "-qa", msg="rename and rewrite")
    assert len(adr.range_check(root, base)) == 1, "a rename carrying a body edit escaped"
    root = fixture(os.path.join(tmp, "b"))
    base = commit_base(root)
    s = open(os.path.join(root, ONE), encoding="utf-8").read()
    s = s.replace("**Pillar:** P2\n\n## 1.", "**Pillar:** P2\n \n## 1.", 1)
    open(os.path.join(root, ONE), "w", encoding="utf-8").write(s)
    git(root, "commit", "-qa", msg="whitespace on the header's last line")
    assert adr.range_check(root, base) == [], "a header-only change was reported as a body edit"


def case_a_record_the_branch_adds_is_a_draft_until_merged(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    draft = os.path.relpath(adr.cmd_new(root, "a-draft", "A draft"), root)
    git(root, "add", "-A"); git(root, "commit", "-q", msg="add a draft record")
    edit(root, draft, "## 6. Consequences", "## 6. Consequences\n\nRevised before the merge.\n")
    git(root, "commit", "-qa", msg="revise the draft")
    assert adr.range_check(root, base) == [], "revising a record the branch adds is not an amendment"


def case_range_check_judges_a_renamed_record_by_its_number(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    git(root, "mv", ONE, "docs/adr/ADR-001-renamed.md")
    git(root, "commit", "-q", msg="rename only")
    edit(root, "docs/adr/ADR-001-renamed.md", "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "commit", "-qa", msg="then edit the body")
    assert len(adr.range_check(root, base)) == 1, "a body edit after a rename escaped as a new record"


def case_a_source_is_never_edited(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    edit(root, "docs/adr/sources/ADR-000-the-owners-statement.md", "I would broaden it", "I would widen it")
    git(root, "commit", "-qa", msg="touch the source")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "a verbatim source, which is never edited" in f[0], f


def case_range_check_on_a_base_without_records(tmp: str) -> None:
    root = os.path.join(tmp, "fresh")
    os.makedirs(root)
    git(root, "init", "-q", "-b", "main"); git(root, "config", "core.hooksPath", "/dev/null")
    open(os.path.join(root, "README"), "w").write("x\n")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="before any record")
    base = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    shutil.copytree(os.path.join(ROOT, "docs", "adr"), os.path.join(root, "docs", "adr"))
    git(root, "add", "-A"); git(root, "commit", "-q", msg="the records arrive")
    edit(root, ONE, "Cheaper, but it keeps", "Cheaper, yet it keeps")
    git(root, "commit", "-qa", msg="revise one before the merge")
    assert adr.range_check(root, base) == [], "a base with no docs/adr: every record is the branch's own"


def case_range_check_pairs_a_delete_and_add_of_one_record(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    body = open(os.path.join(root, ONE), encoding="utf-8").read()
    os.remove(os.path.join(root, ONE))
    head = body.split("## 1. Context and Problem", 1)[0]
    # Every section rewritten: far below -M's similarity threshold, so git
    # reports a delete and an add, never a rename.
    sections = "".join(f"## {name}\n\nRewritten {i}: " + "fresh wording " * 30 + "\n\n" for i, name in enumerate(adr.SECTIONS))
    open(os.path.join(root, "docs/adr/ADR-001-rewritten.md"), "w", encoding="utf-8").write(head + sections)
    # A source added in the same commit carries the record's number; it is
    # not the record's other half (review of #51).
    open(os.path.join(root, "docs/adr/sources/ADR-001-a-new-source.md"), "w", encoding="utf-8").write("new\n")
    git(root, "add", "-A"); git(root, "commit", "-q", msg="rename and rewrite in one go")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "ADR-001-rewritten.md" in f[0] and "source" not in f[0], f


def case_a_source_is_never_removed(tmp: str) -> None:
    root = fixture(tmp)
    base = commit_base(root)
    git(root, "rm", "-q", "docs/adr/sources/ADR-000-the-owners-statement.md")
    git(root, "commit", "-q", msg="drop the source")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "never removed" in f[0], f
    # An editorial trailer excuses a record's body edit, never a source's
    # removal or edit (review of #51).
    root = fixture(os.path.join(tmp, "b"))
    base = commit_base(root)
    git(root, "rm", "-q", "docs/adr/sources/ADR-000-the-owners-statement.md")
    git(root, "commit", "-q", msg="drop the source\n\nADR-Editorial: tidy")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "never removed" in f[0], f
    root = fixture(os.path.join(tmp, "c"))
    base = commit_base(root)
    edit(root, "docs/adr/sources/ADR-000-the-owners-statement.md", "I would broaden it", "I would widen it")
    git(root, "commit", "-qa", msg="touch the source\n\nADR-Editorial: typo")
    f = adr.range_check(root, base)
    assert len(f) == 1 and "never edited" in f[0], f
    # A rename out of sources/ is an edit of the source, trailer or not.
    for n, msg in enumerate(("move the source", "move the source\n\nADR-Editorial: tidy")):
        root = fixture(os.path.join(tmp, f"d{n}"))
        base = commit_base(root)
        git(root, "mv", "docs/adr/sources/ADR-000-the-owners-statement.md", "docs/adr/ADR-000-statement.txt")
        git(root, "commit", "-q", msg=msg)
        f = adr.range_check(root, base)
        assert len(f) == 1 and "never edited" in f[0], f


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
