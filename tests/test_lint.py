#!/usr/bin/env python3
"""Behavioural tests for tools/fabric/lint.py.

Stdlib only; runnable as `python3 tests/test_lint.py`. Each case builds a
throwaway agent-fabric root in a temp directory, so nothing here touches
the real working copy. Fixtures copy the real schemas so schema validation
is actually exercised rather than skipped by `load_schema` returning None.

The corpus holds two kinds of markdown that look alike and are judged by
opposite rules. Knowledge slices carry provenance frontmatter and face the
role-template schema, the evidence rule, the budget and INDEX membership.
`identities/roles/<role>/skills/` and `commands/` hold installable payload
that role.py copies verbatim into `.claude/`, so their .md files carry
skill frontmatter and would fail every slice test at once.

The exemption is therefore narrow by construction, and each case below
pins one edge of it. **Each names the mutation it kills**:

  payload_is_exempt           <- reverting the payload branch; counting
                                 payload into `slices`
  hygiene_still_runs          <- exempting payload from the hygiene scan
  slices_are_still_linted     <- widening PAYLOAD_DIRS (e.g. adding "domain")
  exemption_is_anchored       <- widening PAYLOAD_DIRS; matching the dir
                                 name at any depth
  payload_shape_is_asserted   <- dropping payload_shape_findings
  index_need_not_list_payload <- reverting the payload branch; counting
                                 payload into `slices`

And the layout rules the split into identities/ and memory/ introduced:

  authored_classes_only_in_identities <- letting a charter-class slice
                                 into memory/ without evidence
  knowledge_not_in_identities <- letting a distilled slice sit beside the
                                 charter, where nothing indexes it
  index_lists_domain_slices   <- indexing only the project directory
  taxonomy_roles_are_catalogued <- a binding for a role nobody defined
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree, with_client, write_clients  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
scrub_process_env()

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LINT = os.path.join(ROOT, "tools", "fabric", "lint.py")
REAL_SCHEMAS = os.path.join(ROOT, "identities", "schemas")
REAL_PROJECT_SCHEMAS = os.path.join(ROOT, "projects", "schemas")
REAL_ROUTING = os.path.join(ROOT, "routing")
REAL_PROMPT = os.path.join(ROOT, "identities", "prompt")
REAL_ALIASES = os.path.join(ROOT, "runtime", "claude-code", "aliases.json")
REAL_I18N_SCHEMA = os.path.join(ROOT, "communication", "gzcoord", "i18n", "i18n.schema.json")
PROJECT = "demo"

SKILL = """---
name: webapp-testing
description: Drive a running web app with Playwright when a rendered page must be checked.
license: Apache-2.0
---

# Web Application Testing

Payload, not a claim.
"""

SLICE = """---
role: "web-dev"
class: domain
description: "A well-formed slice, shaped like the real ones"
tier: 2
distilled_at: "2026-09-06"
derived_from:
  - 1e965e01a6ef7e31
  - 7b465cbdb303fddf
---

A claim with provenance.
"""

CHARTER = """---
role: "web-dev"
class: charter
description: "The web sub-apps."
tier: 1
distilled_at: "2026-09-06"
---

# web-dev
"""

NO_FRONTMATTER = "# Just a heading\n\nNo frontmatter at all.\n"

DIRTY_SKILL = """---
name: leaky
description: Payload carrying what must never be committed.
---

Run it against ghp_ABCDEFGHIJKLMNOP in Springfield.
"""

CATALOG = {"version": 1, "roles": [{"id": "web-dev", "title": "Web sub-app developer"}]}
TAXONOMY = {
    "version": 1, "project": PROJECT,
    "projects": {"include": ["demo"], "exclude": [], "unattributed_bucket": "observer-sessions"},
    "reattribution": {"path_markers": {"include": [], "exclude": []},
                      "keywords": {"include": [], "exclude": []}},
    "roles": [{"id": "web-dev", "paths": ["apps/admin_web/"]}],
}
PROFILES = {
    "version": 2,
    "defaults": {"session": "anthropic/claude-sonnet-5"},
    "roles": {"web-dev": {"session": "z-ai/glm-5.3", "capabilities": {"code-low": "z-ai/glm-5.3-flash"}}},
    "agents": {"web-dev-01": {"session": "~z-ai/glm-flash-latest"}},
}


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def make_base(root: str) -> str:
    """A minimal agent-fabric root with the real schemas, one catalogued
    role, and one project binding it."""
    fabric = os.path.join(root, "fabric")
    shutil.copytree(REAL_SCHEMAS, os.path.join(fabric, "identities", "schemas"))
    shutil.copytree(REAL_PROJECT_SCHEMAS, os.path.join(fabric, "projects", "schemas"))
    # The real routing files (minus the profiles, which each case writes)
    # and the Claude Code alias binding, so the routing checks actually run.
    shutil.copytree(REAL_ROUTING, os.path.join(fabric, "routing"),
                    ignore=shutil.ignore_patterns("profiles.json"))
    os.makedirs(os.path.join(fabric, "runtime", "claude-code"))
    shutil.copy2(REAL_ALIASES, os.path.join(fabric, "runtime", "claude-code", "aliases.json"))
    # The launch-prompt sections every session appends; lint requires them.
    shutil.copytree(REAL_PROMPT, os.path.join(fabric, "identities", "prompt"))
    # The real dictionary schema: it is where the key shape is stated, and
    # lint READS it rather than restating it — so a fixture without it put
    # every case on a fallback branch instead of the one that ships
    # (re-review F-A on PR #28).
    os.makedirs(os.path.join(fabric, "communication", "gzcoord", "i18n"))
    shutil.copy2(REAL_I18N_SCHEMA, os.path.join(fabric, "communication", "gzcoord", "i18n", "i18n.schema.json"))
    write(os.path.join(fabric, "identities", "roles", "catalog.json"), json.dumps(CATALOG))
    write(os.path.join(fabric, "projects", PROJECT, "taxonomy.json"), json.dumps(TAXONOMY))
    write(os.path.join(fabric, "identities", "roles", "web-dev", "charter.md"), CHARTER)
    return fabric


def ident(fabric: str, *rest: str) -> str:
    return os.path.join(fabric, "identities", "roles", "web-dev", *rest)


def dom(fabric: str, *rest: str) -> str:
    return os.path.join(fabric, "memory", "domains", "web-dev", *rest)


def wc_demo(fabric: str) -> str:
    """The demo project's working copy: a sibling of the fixture fabric,
    where the project's memory lives (<wc>/.agent-fabric/memory/)."""
    return os.path.join(os.path.dirname(fabric), "wc-demo")


def proj(fabric: str, *rest: str) -> str:
    return os.path.join(wc_demo(fabric), ".agent-fabric", "memory", "web-dev", *rest)


# Links a project's index writes to fabric-side slices go through the
# sibling checkout, whatever the fixture fabric is called (layout.link_rel).
F = "../agent-fabric/"
CHARTER_LINE = f"- [`{F}identities/roles/web-dev/charter.md`]({F}identities/roles/web-dev/charter.md) — The web sub-apps.\n"


def index_for(*entries: str) -> str:
    return "# Index\n\n" + CHARTER_LINE + "".join(entries)


def run_lint(fabric: str, *extra: str) -> tuple[int, str]:
    # The demo working copy is named whenever it exists, so lint sees the
    # project's memory where it lives; a case may name it itself too.
    wc = wc_demo(fabric)
    if os.path.isdir(wc) and not any(a.startswith(f"{PROJECT}=") for a in extra):
        extra = ("--working-copy", f"{PROJECT}={wc}", *extra)
    # The caller's operator would outrank the fixture (ADR-045): the fixture is the whole tree.
    env = {k: v for k, v in os.environ.items() if k != "AGENT_FABRIC_OPERATOR"}
    proc = subprocess.run([sys.executable, LINT, "--fabric", fabric, *extra], capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout + proc.stderr


HYGIENE = {"patterns": [{"pattern": "\\bspringfield\\b", "flags": "i", "label": "city name"}]}


def with_project_hygiene(root: str) -> str:
    """A working copy for the demo project carrying its own hygiene list —
    the deployment's names are the project's to ban, not the fabric's."""
    wc = os.path.join(root, "wc-demo")
    write(os.path.join(wc, ".agent-fabric", "hygiene.json"), json.dumps(HYGIENE))
    return f"{PROJECT}={wc}"


def case_clean_base_passes() -> None:
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        code, out = run_lint(fabric)
        assert code == 0, f"a minimal well-formed root tripped the linter:\n{out}"


def case_the_callers_operator_is_not_part_of_a_fixture() -> None:
    """An exported AGENT_FABRIC_OPERATOR is the caller's, never the fixture's."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        operator = os.path.join(root, "operator")
        write(os.path.join(operator, "projects", "registry.json"), json.dumps({"projects": {"nobody": {}}}))
        saved = os.environ.get("AGENT_FABRIC_OPERATOR")
        os.environ["AGENT_FABRIC_OPERATOR"] = operator
        try:
            code, out = run_lint(fabric)
        finally:
            if saved is None:
                del os.environ["AGENT_FABRIC_OPERATOR"]
            else:
                os.environ["AGENT_FABRIC_OPERATOR"] = saved
        assert code == 0, f"the caller's operator tree was linted with the fixture:\n{out}"


def case_payload_is_exempt() -> None:
    """Well-formed payload passes. Kills: reverting the payload branch."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(ident(fabric, "skills", "webapp-testing", "SKILL.md"), SKILL)
        write(ident(fabric, "commands", "check.md"), SKILL)
        code, out = run_lint(fabric)
        assert code == 0, f"well-formed payload tripped the linter:\n{out}"


def case_hygiene_still_runs_over_payload() -> None:
    """Payload is exempt from slice checks, never from the hygiene scan."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(ident(fabric, "skills", "leaky", "SKILL.md"), DIRTY_SKILL)
        code, out = run_lint(fabric)
        assert code == 1, f"a credential in payload passed CI:\n{out}"
        assert "credential" in out, f"the token went unreported:\n{out}"
        assert "city name" not in out, f"a deployment name was banned with no project list in sight:\n{out}"
        # The city is banned by the PROJECT's list, through its working copy.
        code, out = run_lint(fabric, "--working-copy", with_project_hygiene(root))
        assert code == 1 and "city name" in out, f"the banned place name went unreported:\n{out}"


def case_a_projects_own_name_is_held_to_its_own_set() -> None:
    """A project's "scope": "others" pattern withholds a name everywhere
    but in that project's own slices; a hygiene finding names the label,
    never the hit (it lands in CI's log); a broken hygiene list is a
    finding, never a traceback. Kills: holding project slices to the
    union, echoing the hit, letting HygieneError escape main()."""
    scoped = {"patterns": [{"pattern": "\\bspringfield\\b", "flags": "i", "label": "city name", "scope": "others"}]}
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        wc = os.path.join(root, "wc-demo")
        write(os.path.join(wc, ".agent-fabric", "hygiene.json"), json.dumps(scoped))
        write(proj(fabric, "solution", "city.md"), SLICE.replace("A claim with provenance.", "The stack runs in Springfield."))
        write(dom(fabric, "domain", "city.md"), SLICE.replace("A claim with provenance.", "The stack runs in Springfield."))
        code, out = run_lint(fabric, "--working-copy", f"{PROJECT}={wc}")
        mine = [line for line in out.splitlines() if "city name" in line]
        assert any("domains/web-dev/domain/city.md" in line for line in mine), f"the fabric slice passed:\n{out}"
        assert not any("solution/city.md" in line for line in mine), f"the project's own slice was held to the union:\n{out}"
        assert "Springfield" not in out and "springfield" not in out, f"a finding echoed the withheld text:\n{out}"
        write(os.path.join(wc, ".agent-fabric", "hygiene.json"), "{not json")
        code, out = run_lint(fabric, "--working-copy", f"{PROJECT}={wc}")
        assert code == 1 and "Traceback" not in out and "hygiene.json" in out, f"a broken list was not one finding:\n{out}"


def case_secrets_are_refused_by_shape() -> None:
    """Passwords, keys and tokens assigned a value, key material and known
    token shapes are refused wherever they appear; a sentence about a
    token, a placeholder and an environment variable's name are not."""
    leaks = ["password=hunter2hunter2", "api_key: 0123456789abcdef", 'ANTHROPIC_API_KEY="sk-ant-api03-abcdefghijklmnopqrstuvwxyz"',
             "token = ZmFrZS10b2tlbi12YWx1ZQ", "AKIAIOSFODNN7EXAMPLE", "-----BEGIN RSA PRIVATE KEY-----",
             "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
             "dp.st.dev.abcdefghijklmnop", "client_secret: q1w2e3r4t5y6u7i8"]
    fine = ["the token arrives with fabric-secrets sync", "export CLAUDE_BRIDGE_AUTH_TOKEN=<value>", "token_env_file: infra/local/.env.local",
            "password: (redacted)", "api_key: ${OPENROUTER_API_KEY}", "secret: none", "A bearer token is sent on every call."]
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        for leak in leaks:
            write(dom(fabric, "domain", "leak.md"), SLICE.replace("A claim with provenance.", f"Set {leak} and retry."))
            code, out = run_lint(fabric)
            assert code == 1 and "credential" in out, f"a secret passed: {leak!r}\n{out}"
        for text in fine:
            write(dom(fabric, "domain", "leak.md"), SLICE.replace("A claim with provenance.", text))
            code, out = run_lint(fabric)
            assert code == 0, f"a harmless line was refused: {text!r}\n{out}"


def case_a_persons_name_is_refused_everywhere() -> None:
    """The fabric's own hygiene list (policies/hygiene.json) applies with no
    project list in sight: a person is named by role. Kills: dropping the
    fabric list from load_hygiene_patterns."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        os.makedirs(os.path.join(fabric, "policies"), exist_ok=True)
        # Lint prints the pattern's label as written: the fixture's label carries the advice, and the name is a fixture's.
        write(os.path.join(fabric, "policies", "hygiene.json"), json.dumps({"patterns": [
            {"pattern": "\\bAda(\\s+Fixture)?\\b", "label": "person's name -- refer to the CEO by role", "refer_as": "the CEO"}]}))
        write(dom(fabric, "domain", "named.md"), SLICE.replace("A claim with provenance.", "Ada Fixture asked for it; Ada caught the workaround."))
        code, out = run_lint(fabric)
        assert code == 1 and "person's name" in out and "the CEO" in out, f"a person's name passed, or the finding does not say what to write instead:\n{out}"
        write(dom(fabric, "domain", "named.md"), SLICE.replace("A claim with provenance.", "The CEO asked for it; the CEO caught the workaround."))
        code, out = run_lint(fabric)
        assert code == 0, f"naming the role tripped the linter:\n{out}"


def case_slices_are_still_linted() -> None:
    """Kills: widening PAYLOAD_DIRS to swallow a slice directory."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(ident(fabric, "skills", "ok", "SKILL.md"), SKILL)
        write(dom(fabric, "domain", "good.md"), SLICE)
        write(dom(fabric, "domain", "bad.md"), NO_FRONTMATTER)
        write(proj(fabric, "INDEX.md"), index_for(
            "- [`../agent-fabric/memory/domains/web-dev/domain/good.md`](../agent-fabric/memory/domains/web-dev/domain/good.md) — A well-formed slice, shaped like the real ones\n",
            "- [`../agent-fabric/memory/domains/web-dev/domain/bad.md`](../agent-fabric/memory/domains/web-dev/domain/bad.md) — x\n"))
        code, out = run_lint(fabric)
        assert code == 1, f"a slice with no frontmatter should fail:\n{out}"
        assert "domain/bad.md" in out, f"the bad slice went unreported:\n{out}"
        assert "good.md" not in out, f"the well-formed slice was flagged:\n{out}"


def case_a_cue_in_another_script_is_refused() -> None:
    """A slice's description and its headings are English like its body:
    they are the index line and what a holder reads before choosing.
    Kills: checking the body only, or only Italian."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        ru_desc = SLICE.replace('description: "A well-formed slice, shaped like the real ones"',
                                'description: "По-русски merge ветки — вливать"')
        ka_head = SLICE.replace("A claim with provenance.", "## შერწყმულია ამ დღეს\n\nA claim with provenance.")
        write(dom(fabric, "domain", "ru.md"), ru_desc)
        write(dom(fabric, "domain", "ka.md"), ka_head)
        write(dom(fabric, "domain", "good.md"), SLICE)
        write(dom(fabric, "domain", "it.md"), SLICE.replace('description: "A well-formed slice, shaped like the real ones"',
                                                            'description: "Questo valore della chiave vale anche senza sessione"'))
        write(dom(fabric, "domain", "h3.md"), SLICE.replace("A claim with provenance.", "### Русский подзаголовок\n\nA claim with provenance."))
        write(dom(fabric, "domain", "fenced.md"), SLICE.replace("A claim with provenance.", "```\n# Русский комментарий в коде\n```\n\nA claim with provenance."))
        code, out = run_lint(fabric)
        assert code == 1, out
        assert "h3.md: heading is not English" in out, "a ### heading escaped the check:\n" + out
        assert "it.md: description is not English" in out, "an Italian cue escaped the check:\n" + out
        assert "fenced.md" not in out, "a fenced code line was read as a heading:\n" + out
        assert "ru.md: description is not English" in out, out
        assert "ka.md: heading is not English" in out, out
        assert "good.md: description" not in out and "good.md: heading" not in out, out


def case_exemption_is_anchored_at_the_role_root() -> None:
    """Only `identities/roles/<role>/skills/` is payload. Keying on the
    name alone would let anyone park unlinted files under `domain/skills/`."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(dom(fabric, "domain", "skills", "sneaky.md"), NO_FRONTMATTER)
        code, out = run_lint(fabric)
        assert code == 1, f"a nested skills/ must still be linted:\n{out}"
        assert "sneaky.md" in out, f"nested payload escaped the linter:\n{out}"


def case_payload_shape_is_asserted() -> None:
    """Misplaced payload is loud here, because role.py drops it silently."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(ident(fabric, "skills", "single-file.md"), SKILL)
        os.makedirs(ident(fabric, "skills", "empty-dir"))
        write(ident(fabric, "commands", "nested", "deep.md"), SKILL)
        code, out = run_lint(fabric)
        assert code == 1, f"misplaced payload passed silently:\n{out}"
        assert "single-file.md" in out, f"a non-directory under skills/ went unreported:\n{out}"
        assert "empty-dir" in out, f"a skill with no SKILL.md went unreported:\n{out}"
        assert "commands/nested" in out, f"a directory under commands/ went unreported:\n{out}"


def case_index_need_not_list_payload() -> None:
    """A role with an INDEX.md and payload — the real web-dev shape."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(dom(fabric, "domain", "good.md"), SLICE)
        write(proj(fabric, "INDEX.md"), index_for(
            "- [`../agent-fabric/memory/domains/web-dev/domain/good.md`](../agent-fabric/memory/domains/web-dev/domain/good.md) — A well-formed slice, shaped like the real ones\n"))
        write(ident(fabric, "skills", "webapp-testing", "SKILL.md"), SKILL)
        code, out = run_lint(fabric)
        assert code == 0, f"payload was counted against the index:\n{out}"
        assert "index has drifted" not in out, f"index drift reported for payload:\n{out}"


def case_index_description_drift_is_caught() -> None:
    """An INDEX.md entry whose description no longer matches the slice."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(dom(fabric, "domain", "good.md"), SLICE)
        write(proj(fabric, "INDEX.md"), index_for(
            "- [`../agent-fabric/memory/domains/web-dev/domain/good.md`](../agent-fabric/memory/domains/web-dev/domain/good.md) — STALE WORDING\n"))
        code, out = run_lint(fabric)
        assert code != 0, f"a drifted index description was not caught:\n{out}"
        assert "STALE WORDING" in out, f"the finding does not quote the index text:\n{out}"
        assert "A well-formed slice" in out, f"the finding does not quote the slice text:\n{out}"


def case_a_sibling_working_copy_is_linted_unasked() -> None:
    """The working copies beside the checkout are linted without being
    named, so a charter edited here with the project's index describing
    the old one fails the fabric's own run before the project's CI does
    (2026-09-17). The sibling is found by its remote against the registry;
    --no-siblings turns it off. Kills: dropping the discovery, or making
    it ignore a drifted index."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(dom(fabric, "domain", "good.md"), SLICE)
        wc = wc_demo(fabric)
        write(proj(fabric, "INDEX.md"), index_for(
            "- [`../agent-fabric/memory/domains/web-dev/domain/good.md`](../agent-fabric/memory/domains/web-dev/domain/good.md) — STALE WORDING\n"))
        # a git working copy whose remote the fixture registry maps to the demo project
        _write_license_layout(fabric, {"version": 1, "projects": {
            "agent-fabric": {"license": "Apache-2.0", "remotes": ["git@github.com:gzapi-org/agent-fabric.git"]},
            "demo": {"license": "Apache-2.0", "remotes": ["git@example.com:org/demo.git"]}}}, REUSE_OK)
        subprocess.run(["git", "-C", wc, "init", "-q"], check=True, env=git_env())
        subprocess.run(["git", "-C", wc, "remote", "add", "origin", "git@example.com:org/demo.git"], check=True, env=git_env())
        proc = subprocess.run([sys.executable, LINT, "--fabric", fabric], capture_output=True, text=True)
        assert proc.returncode != 0 and "STALE WORDING" in proc.stdout + proc.stderr, f"the sibling's drifted index passed unasked:\n{proc.stdout}{proc.stderr}"
        proc = subprocess.run([sys.executable, LINT, "--fabric", fabric, "--no-siblings"], capture_output=True, text=True)
        assert proc.returncode == 0, f"--no-siblings still looked beside the checkout:\n{proc.stdout}{proc.stderr}"


def case_fabric_ref_is_one_full_commit_id() -> None:
    """A project may record the fabric commit its indexes were assembled
    against (.agent-fabric/fabric-ref), for its CI to check out instead of
    the fabric's default branch. Absent is fine; present, it is one line,
    one full lowercase commit id, newline-terminated — anything else is a
    finding naming the project. Kills: skipping the file, accepting a
    short id, or a second line."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(proj(fabric, "INDEX.md"), index_for())
        ref = os.path.join(wc_demo(fabric), ".agent-fabric", "fabric-ref")
        code, out = run_lint(fabric)
        assert code == 0, f"no fabric-ref, yet a finding:\n{out}"
        write(ref, "a" * 40 + "\n")
        code, out = run_lint(fabric)
        assert code == 0, f"a well-formed fabric-ref failed:\n{out}"
        for bad, why in (("a" * 40, "no newline"), ("A" * 40 + "\n", "uppercase"), ("a" * 7 + "\n", "short id"),
                         ("a" * 40 + "\n" + "b" * 40 + "\n", "two lines"), ("", "empty")):
            write(ref, bad)
            code, out = run_lint(fabric)
            assert code != 0 and "fabric-ref" in out, f"{why} passed:\n{out}"


def case_index_lists_domain_slices() -> None:
    """A role's domain slices live outside the project directory and must
    still be indexed there. Kills: indexing only the project directory."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(dom(fabric, "domain", "good.md"), SLICE)
        write(proj(fabric, "INDEX.md"), index_for())
        code, out = run_lint(fabric)
        assert code == 1, f"an unindexed domain slice passed:\n{out}"
        assert "does not list ../agent-fabric/memory/domains/web-dev/domain/good.md" in out, out
        # And a domain with slices that no project indexes at all is named.
        os.remove(proj(fabric, "INDEX.md"))
        os.rmdir(proj(fabric))
        code, out = run_lint(fabric)
        assert code == 1 and "indexed by no project" in out, out


def case_domain_bound_by_an_unseen_project_is_not_judged() -> None:
    """A domain whose role no VISIBLE project binds is not required to be
    indexed: another repository's CI passes only its own working copy and
    must not fail on a role that repository never holds. Kills: judging
    every domain whenever any project is visible (the 2026-09-17 queue
    failure)."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        # the fixture project binds web-dev and indexes it; a second role's
        # domain has slices and no index anywhere this run can see
        write(dom(fabric, "domain", "good.md"), SLICE)
        write(proj(fabric, "INDEX.md"), index_for(
            "- [`../agent-fabric/memory/domains/web-dev/domain/good.md`](../agent-fabric/memory/domains/web-dev/domain/good.md) — A good slice\n"))
        other = os.path.join(fabric, "memory", "domains", "db-admin", "domain", "plan.md")
        write(other, SLICE.replace('role: "web-dev"', 'role: "db-admin"'))
        cat = json.load(open(os.path.join(fabric, "identities", "roles", "catalog.json"), encoding="utf-8"))
        cat["roles"].append({"id": "db-admin", "title": "DB"})
        write(os.path.join(fabric, "identities", "roles", "catalog.json"), json.dumps(cat))
        code, out = run_lint(fabric)
        assert "indexed by no project" not in out, f"a role the visible project does not bind was judged:\n{out}"
        # …and once the visible project binds that role, the missing index is named.
        tax = dict(TAXONOMY); tax["roles"] = TAXONOMY["roles"] + [{"id": "db-admin", "paths": ["infra/db/"]}]
        write(os.path.join(fabric, "projects", PROJECT, "taxonomy.json"), json.dumps(tax))
        code, out = run_lint(fabric)
        assert code == 1 and "memory/domains/db-admin" in out and "indexed by no project" in out, out


GE_BODY = "\n# web-dev — წესდება\n\n" + ("ეს არის ქართული თარგმანი, რომელიც სრულად ქართულ დამწერლობაზეა დაწერილი. " * 6) + "\n"


def _digest_of_body(path: str) -> str:
    import hashlib
    import re as _re
    text = open(path, encoding="utf-8").read()
    body = _re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=_re.DOTALL)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _translation(digest: str, klass: str = "charter") -> str:
    return (f'---\nrole: "web-dev"\nclass: {klass}\ndescription: "ქართული წესდება"\ntier: 1\ndistilled_at: "2026-09-17"\n'
            f'translates: identities/roles/web-dev/charter.md\ntranslates_digest: {digest}\n---\n' + GE_BODY)


WORKER = """---
name: locale-worker
description: ენის როლის მხოლოდ ქართულენოვანი მუშაკი (agent-fabric) — იღებს ქართულს, პასუხობს ქართულად
model: opus
tools: TaskStop
---

შენ ხარ ქართული ენის რედაქტორი. პასუხობ მხოლოდ ქართულად.
"""


def case_locale_translation_is_a_charter_with_a_digest() -> None:
    """A locale charter is linted on its own terms (schema, class, source
    and digest) and never as a generic slice beside a worker file that
    carries no fabric frontmatter. Kills: dropping the locale/ exemption
    in lint_slices, or the translation rule itself."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(ident(fabric, "locale", "ge", "charter.md"), _translation(_digest_of_body(ident(fabric, "charter.md"))))
        write(ident(fabric, "locale", "ge", "worker.md"), WORKER)
        code, out = run_lint(fabric)
        assert code == 0, f"a well-formed translation and worker failed:\n{out}"
        # class must be charter; the source must be this role's charter
        write(ident(fabric, "locale", "ge", "charter.md"), _translation(_digest_of_body(ident(fabric, "charter.md")), klass="brief"))
        code, out = run_lint(fabric)
        assert code == 1 and "is class charter" in out, out


def case_locale_brief_translates_like_the_charter() -> None:
    """A role with a brief gets a locale brief the same way as its
    charter: class brief, translates naming the English brief, its
    digest. The schema admitted only charter.md until 2026-09-18, when
    the first brief translation was refused on arrival. Kills: narrowing
    the pattern back, or a translation naming a file that is not an
    authored identity file."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(ident(fabric, "brief.md"), CHARTER.replace("class: charter", "class: brief"))
        write(proj(fabric, "INDEX.md"), index_for(
            "- [`../agent-fabric/identities/roles/web-dev/brief.md`](../agent-fabric/identities/roles/web-dev/brief.md) — The web sub-apps.\n"))
        digest = _digest_of_body(ident(fabric, "brief.md"))
        write(ident(fabric, "locale", "ge", "brief.md"),
              _translation(digest, "brief").replace("translates: identities/roles/web-dev/charter.md",
                                                    "translates: identities/roles/web-dev/brief.md"))
        code, out = run_lint(fabric)
        assert code == 0, f"a locale brief naming its brief was refused:\n{out}"
        write(ident(fabric, "locale", "ge", "brief.md"),
              _translation(digest, "brief").replace("translates: identities/roles/web-dev/charter.md",
                                                    "translates: identities/roles/web-dev/recall.md"))
        code, out = run_lint(fabric)
        assert code != 0 and "translates" in out, f"a translation of a non-identity file passed:\n{out}"


def case_translation_lag_is_reported() -> None:
    """The English charter moves, the translation keeps the old digest:
    named as a warning, never silently served as current — and never a
    failing finding, since the source must land before its holder can
    re-render (2026-09-18). Its tokens are not judged against the moved
    source. Kills: dropping the digest comparison, or failing on lag."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(ident(fabric, "locale", "ge", "charter.md"), _translation(_digest_of_body(ident(fabric, "charter.md"))))
        assert run_lint(fabric)[0] == 0
        write(ident(fabric, "charter.md"), CHARTER + "\nA paragraph with `a-new-span` the translation does not carry yet.\n")
        code, out = run_lint(fabric)
        assert code == 0 and "the translation lags" in out and "warning:" in out, \
            f"a lag must be named and still pass — the source lands before its holder can re-render:\n{out}"
        assert "a-new-span" not in out, f"tokens of a source that moved were judged against the stale translation:\n{out}"


def case_locale_worker_shape_and_hygiene() -> None:
    """The worker file is not a slice, but its shape is asserted (the
    dispatcher's name, a description in the locale with the installer's
    marker, an alias, one inert tool) and hygiene still runs over its body."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(ident(fabric, "locale", "ge", "worker.md"), WORKER)
        assert run_lint(fabric)[0] == 0
        bad = WORKER.replace("name: locale-worker", "name: ka-worker").replace("(agent-fabric)", "").replace("tools: TaskStop\n", "tools: Read, Bash\n")
        write(ident(fabric, "locale", "ge", "worker.md"), bad)
        code, out = run_lint(fabric)
        assert code == 1, out
        for phrase in ("locale-worker", "agent-fabric` marker", "its one tool is TaskStop"):
            assert phrase in out, f"{phrase!r} not reported:\n{out}"
        # An empty tools line is the trap: it inherits every tool.
        write(ident(fabric, "locale", "ge", "worker.md"), WORKER.replace("tools: TaskStop\n", "tools:\n"))
        code, out = run_lint(fabric)
        assert code == 1 and "inherits every tool" in out, out
        # An English description is the leak: its only reader is the bridge, which reasons in the locale.
        write(ident(fabric, "locale", "ge", "worker.md"), WORKER.replace("description: ენის როლის მხოლოდ ქართულენოვანი მუშაკი (agent-fabric) — იღებს ქართულს, პასუხობს ქართულად", "description: The Georgian-only worker (agent-fabric): receives Georgian, answers Georgian"))
        code, out = run_lint(fabric)
        assert code == 1 and "not in the locale" in out, out
        write(ident(fabric, "locale", "ge", "worker.md"), WORKER + "\nRun it against ghp_ABCDEFGHIJKLMNOP.\n")
        code, out = run_lint(fabric)
        assert code == 1 and "credential" in out, f"a credential in the worker body passed:\n{out}"


EN_WITH_TOKENS = """---
role: "web-dev"
class: charter
description: "The web sub-apps."
tier: 1
distilled_at: "2026-09-06"
---

# web-dev

Run `bin/fabric-status` first, then read `docs/x.md` under
`identities/roles/web-dev/`. Ask `fabric-ctl <login>
script` for the notes. Never `/compact` mid-review; the model is
`claude-fable-5-1`. See [[blind-review-loop]] and MEMORY.md; the
placeholder {role} is filled at render. Every OBSERVATION names its lane.

```markdown
---
name: <slug>
---
```
"""
KA_WITH_TOKENS = """
# web-dev — წესდება

ჯერ გაუშვი `bin/fabric-status`, მერე წაიკითხე `docs/x.md`
`identities/roles/web-dev/`-ის ქვეშ. ჩანაწერებისთვის ჰკითხე `fabric-ctl <login> script`.
არასოდეს `/compact` შემოწმების შუაში; მოდელია `claude-fable-5-1`.
იხილე [[blind-review-loop]] და MEMORY.md; ჩანაცვლება {role} რენდერისას ივსება.
ყოველი OBSERVATION თავის ზოლს ასახელებს.

```markdown
---
name: <slug>
---
```
"""


def _translation_of(source_rel: str, klass: str, digest: str, body: str, role: str | None = "web-dev") -> str:
    head = f'---\nclass: {klass}\n' + (f'role: "{role}"\ndescription: "თარგმანი"\ntier: 1\ndistilled_at: "2026-09-17"\n' if role else '')
    return head + f'translates: {source_rel}\ntranslates_digest: {digest}\n---\n' + body


def case_protected_tokens_must_match() -> None:
    """A translation keeps every identifier the source quotes, the same
    number of times: a span that wraps at another column is the same
    span; a dropped path, a renamed command, a lost placeholder, an added
    span are each one finding naming the category. Kills: comparing prose,
    or splitting a wrapped backticked span at the newline."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(ident(fabric, "charter.md"), EN_WITH_TOKENS)
        good = _translation_of("identities/roles/web-dev/charter.md", "charter", _digest_of_body(ident(fabric, "charter.md")), KA_WITH_TOKENS)
        write(ident(fabric, "locale", "ge", "charter.md"), good)
        code, out = run_lint(fabric)
        assert code == 0, out
        bad = good.replace("`docs/x.md`", "`docs/y.md`").replace("`/compact`", "`/შეკუმშვა`").replace("{role}", "{როლი}").replace("MEMORY.md", "MEMORY-ის ფაილი") + "\nდამატებული `Bash` ბრძანება.\n"
        write(ident(fabric, "locale", "ge", "charter.md"), bad)
        code, out = run_lint(fabric)
        assert code == 1, out
        for phrase in ("backticked span '`docs/x.md`' appears 0 time(s), 1 in the source", "backticked span '`/compact`' appears 0",
                       "placeholder '{role}' appears 0", "file name 'MEMORY.md' appears 0", "backticked span '`Bash`' appears 1 time(s), 0 in the source"):
            assert phrase in out, f"{phrase!r} not reported:\n{out}"
        assert "fabric-ctl <login> script" not in out, f"a wrapped span is the same span:\n{out}"
        # An inflected locale glues a suffix to a name with a dash: the suffix is prose, the token is the name.
        write(ident(fabric, "locale", "ge", "charter.md"), good.replace("`/compact` შემოწმების", "/compact-ით შემოწმების").replace("`docs/x.md`", "docs/x.md-ში"))
        code, out = run_lint(fabric)
        assert code == 1, out
        assert "backticked span '`/compact`' appears 0" in out and "slash command '/compact' appears 1 time(s), 0 in the source" in out, out
        assert "/compact-ით" not in out and "x.md-ში" not in out and "path '/x.md'" not in out, f"the glued suffix is not part of the token:\n{out}"


def case_each_translation_names_its_source_and_lags_when_it_moves() -> None:
    """Every prompt piece a locale may translate — header, brief-missing,
    team, memory, harness — names its source and its digest; a source
    that moved is a lag finding; a wrong source path is named. Kills: a
    table that only knows the charter."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        prompt = os.path.join(fabric, "identities", "prompt")
        for name in ("header", "brief-missing", "team", "memory"):
            src = os.path.join(prompt, f"{name}.md")
            body = open(src, encoding="utf-8").read()
            ka = "\n".join("ქართული " * 8 if (not line.strip() or line.startswith("#")) and "{" not in line else line for line in body.splitlines())   # keep every token line, translate nothing else
            write(ident(fabric, "locale", "ge", f"{name}.md"), _translation_of(f"identities/prompt/{name}.md", "prompt-translation", _digest_of_body(src), ka, role=None))
        code, out = run_lint(fabric)
        assert code == 0, out
        # The source moves without growing: the test is about lag, and the
        # real prompt sits near its token budget, which an appended sentence
        # once crossed, failing the case for the wrong reason.
        team = open(os.path.join(prompt, "team.md"), encoding="utf-8").read()
        write(os.path.join(prompt, "team.md"), team.replace(" the ", " THE ", 1))
        code, out = run_lint(fabric)
        assert code == 0 and "warning: identities/roles/web-dev/locale/ge/team.md: translates identities/prompt/team.md at sha256:" in out \
            and "the translation lags" in out, f"a lag is named as a warning and does not fail (the source lands first):\n{out}"
        write(ident(fabric, "locale", "ge", "memory.md"), _translation_of("identities/prompt/team.md", "prompt-translation", "sha256:" + "0" * 64, "x {role}\n", role=None))
        code, out = run_lint(fabric)
        assert "locale/ge/memory.md: translates 'identities/prompt/team.md', not identities/prompt/memory.md" in out, out


def case_harness_translation_shape_digest_and_tokens() -> None:
    """locale/<suffix>/harness.md translates runtime/claude-code/harness/en.md:
    class harness-translation, the source's digest, every protected token
    including {memory_dir}, the flat harness budget."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        lc = os.path.join(fabric, "docs", "live-checks", "2026-09-17-x.md"); os.makedirs(os.path.dirname(lc), exist_ok=True); write(lc, "# x\n")
        src = os.path.join(fabric, "runtime", "claude-code", "harness", "en.md")
        write(src, "---\nclass: harness-source\nbuild: \"2.1.274 (Claude Code)\"\ncaptured_at: 2026-09-17\nsource: docs/live-checks/2026-09-17-x.md\n---\n"
                   "You are Claude Code. Use `Skill` for a `/<skill-name>`; load `ToolSearch(\"select:EndConversation\")` first.\n\n# Memory\n\nYour memory is at `{memory_dir}`.\n")
        ka = "შენ ხარ Claude Code. გამოიყენე `Skill` `/<skill-name>`-სთვის; ჯერ ჩატვირთე `ToolSearch(\"select:EndConversation\")`.\n\n# მეხსიერება\n\nშენი მეხსიერება არის `{memory_dir}`.\n"
        write(ident(fabric, "locale", "ge", "harness.md"), _translation_of("runtime/claude-code/harness/en.md", "harness-translation", _digest_of_body(src), ka, role=None))
        code, out = run_lint(fabric)
        assert code == 0, out
        write(ident(fabric, "locale", "ge", "harness.md"), _translation_of("runtime/claude-code/harness/en.md", "harness-translation", _digest_of_body(src), ka.replace("`{memory_dir}`", "`/home/ge/.claude/projects/x/memory/`"), role=None))
        code, out = run_lint(fabric)
        assert code == 1 and "backticked span '`{memory_dir}`' appears 0 time(s), 1 in the source" in out, out
        write(ident(fabric, "locale", "ge", "harness.md"), _translation_of("runtime/claude-code/harness/en.md", "prompt-translation", _digest_of_body(src), ka, role=None))
        code, out = run_lint(fabric)
        assert code == 1 and "class 'prompt-translation'; a locale harness is class harness-translation" in out, out


def case_harness_source_shape() -> None:
    """runtime/claude-code/harness/en.md, when a fabric carries it: class,
    build, captured_at, an existing live check as its source, the
    memory-directory placeholder exactly once. Absent, nothing is said
    (a fixture fabric). Kills: a capture with no build, or with the
    login's real memory path left in."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        assert run_lint(fabric)[0] == 0, "no capture, no finding"
        lc = os.path.join(fabric, "docs", "live-checks", "2026-09-17-x.md"); os.makedirs(os.path.dirname(lc), exist_ok=True); write(lc, "# x\n")
        good = ("---\nclass: harness-source\nbuild: \"2.1.274 (Claude Code)\"\ncaptured_at: 2026-09-17\nsource: docs/live-checks/2026-09-17-x.md\n---\n"
                "You are Claude Code.\n\n# Memory\n\nYou have a persistent file-based memory at `{memory_dir}`.\n")
        write(os.path.join(fabric, "runtime", "claude-code", "harness", "en.md"), good)
        code, out = run_lint(fabric)
        assert code == 0, out
        write(os.path.join(fabric, "runtime", "claude-code", "harness", "en.md"), good.replace("build: \"2.1.274 (Claude Code)\"\n", "").replace("{memory_dir}", "/home/x/.claude/projects/-home-x/memory/"))
        code, out = run_lint(fabric)
        assert code == 1, out
        for phrase in ("no `build`", "{memory_dir} appears 0 time(s)"):
            assert phrase in out, f"{phrase!r} not reported:\n{out}"
        write(os.path.join(fabric, "runtime", "claude-code", "harness", "en.md"), good.replace("2026-09-17-x.md", "2026-09-17-missing.md"))
        code, out = run_lint(fabric)
        assert code == 1 and "not an existing docs/live-checks/ note" in out, out


def case_prompt_templates_carry_their_placeholders() -> None:
    """identities/prompt/header.md names the login ({agent}, {host},
    {role}); a header without {agent} would read the same for every login.
    Kills: checking only {role} on every template."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        p = os.path.join(fabric, "identities", "prompt", "header.md")
        write(p, open(p, encoding="utf-8").read().replace("{agent}", "someone"))
        code, out = run_lint(fabric)
        assert code == 1 and "header.md: no {agent} placeholder" in out, out


def case_locale_file_shape() -> None:
    """locale.json fixes the search tools' country and languages, one block
    per engine; lint asserts the shapes each engine takes and a description
    in the locale. Kills: an unchecked file the server would refuse at start."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        good = ('{"tag": "ka-GE", "timezone": "Asia/Tbilisi", "serpapi": {"gl": "ge", "hl": "ka", "google_domain": "google.ge", "lr": "lang_ka", "tool_description": "ვებ-ძიება ქართულად"},'
                ' "brave": {"country": "ALL", "tool_description": "გლობალური ვებ-ძიება"}}')
        write(ident(fabric, "locale", "ge", "locale.json"), good)
        code, out = run_lint(fabric)
        assert code == 0, out
        write(ident(fabric, "locale", "ge", "locale.json"), good.replace('"gl": "ge"', '"gl": "GE"').replace('"hl": "ka"', '"hl": "KA-"').replace('"lr": "lang_ka"', '"lr": "ka"').replace("ვებ-ძიება ქართულად", "Web search in Georgian").replace('"ALL"', '"all"'))
        code, out = run_lint(fabric)
        assert code == 1, out
        for phrase in ("serpapi.gl 'GE'", "serpapi.hl 'KA-'", "serpapi.lr 'ka'", "serpapi.tool_description is not in the locale", "brave.country 'all'"):
            assert phrase in out, f"{phrase!r} not reported:\n{out}"
        write(ident(fabric, "locale", "ge", "locale.json"), '{"tag": "ka-GE", "timezone": "Asia/Tbilisi", "brave": {"country": "US", "search_lang": "en", "ui_lang": "en-US", "tool_description": "ძიება"}}')
        code, out = run_lint(fabric)
        assert code == 0, f"one engine alone, with the languages Brave has: {out}"
        write(ident(fabric, "locale", "ge", "locale.json"), good.replace('"tool_description": "ვებ-ძიება ქართულად"', '"label": "main engine", "tool_description": "ვებ-ძიება ქართულად"'))
        code, out = run_lint(fabric)
        assert code == 1 and "serpapi.label 'main engine'" in out, f"a label not in the locale is refused: {out}"
        write(ident(fabric, "locale", "ge", "locale.json"), '{"tag": "ka-GE", "timezone": "Asia/Tbilisi"}')
        code, out = run_lint(fabric)
        assert code == 1 and "no engine block" in out, out
        # The standing reminder is optional, and in the locale when present.
        write(ident(fabric, "locale", "ge", "locale.json"), good[:-1] + ', "reminder": " - იფიქრე ქართულად"}')
        code, out = run_lint(fabric)
        assert code == 0, f"a reminder in the locale passes: {out}"
        write(ident(fabric, "locale", "ge", "locale.json"), good[:-1] + ', "reminder": " - think in Georgian"}')
        code, out = run_lint(fabric)
        assert code == 1 and "reminder ' - think in Georgian' is not in the locale" in out, out
        write(ident(fabric, "locale", "ge", "locale.json"), good[:-1] + ', "reminder": "  "}')
        code, out = run_lint(fabric)
        assert code == 1 and "a non-empty line, or absent" in out, out
        write(ident(fabric, "locale", "ge", "locale.json"), good[:-1] + ', "country": "GE"}')
        code, out = run_lint(fabric)
        assert code == 1 and "unknown field(s) ['country']" in out, out
        write(ident(fabric, "locale", "ge", "locale.json"), "{not json")
        code, out = run_lint(fabric)
        assert code == 1 and "not JSON" in out, out


def case_i18n_dictionary_is_complete_and_keeps_its_identifiers() -> None:
    """An active locale's <tag>.json carries EVERY key of the default
    dictionary and no other, every value a non-empty string, and every
    identifier inside a value byte-identical — a flag, the protocol
    marker, a SPEC reference, a path. A dictionary with no non-Latin value
    is the default copied, not translated. Kills: a key that falls back
    silently for the life of a release; a translated `--replay` nobody can
    type; an English copy that looks active."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        default = {"inbox.head": "gzcoord inbox for {who}, on {channel}",
                   "replay.usage": "usage: inbox.mjs --replay <seq|message-id>",
                   "inbox.others-header": "Not addressed to you (SPEC §17):"}
        write(os.path.join(fabric, "communication", "gzcoord", "i18n", "en-US.json"), json.dumps(default))
        write(ident(fabric, "locale", "ge", "locale.json"),
              '{"tag": "ka-GE", "timezone": "Asia/Tbilisi", "brave": {"country": "ALL", "tool_description": "ძიება"}}')
        good = {"inbox.head": "ᲨᲔᲛᲝᲡᲣᲚᲘ gzcoord {who}, {channel}",
                "replay.usage": "ᲒᲐᲛᲝᲧᲔᲜᲔᲑᲐ: inbox.mjs --replay <seq|message-id>",
                "inbox.others-header": "ᲐᲠ ᲐᲠᲘᲡ ᲨᲔᲜᲗᲕᲘᲡ (SPEC §17):"}
        write(ident(fabric, "locale", "ge", "ka-GE.json"), json.dumps(good, ensure_ascii=False))
        code, out = run_lint(fabric)
        assert code == 0, out

        # No dictionary at all is not a finding: the default locale is served.
        os.remove(ident(fabric, "locale", "ge", "ka-GE.json"))
        code, out = run_lint(fabric)
        assert code == 0, f"an inactive locale is not a finding: {out}"

        short = dict(good); del short["replay.usage"]
        short["invented.key"] = "ᲠᲐᲦᲐᲪ"
        write(ident(fabric, "locale", "ge", "ka-GE.json"), json.dumps(short, ensure_ascii=False))
        code, out = run_lint(fabric)
        assert code == 1, out
        assert "1 key(s) of communication/gzcoord/i18n/en-US.json missing" in out, out
        assert "['invented.key'] are not in" in out, out

        broken = dict(good)
        broken["replay.usage"] = "ᲒᲐᲛᲝᲧᲔᲜᲔᲑᲐ: inbox.mjs --ᲒᲐᲨᲚᲐ <seq|message-id>"
        broken["inbox.others-header"] = "ᲐᲠ ᲐᲠᲘᲡ ᲨᲔᲜᲗᲕᲘᲡ (ᲡᲞᲔᲪᲘᲤᲘᲙᲐᲪᲘᲐ §17):"
        write(ident(fabric, "locale", "ge", "ka-GE.json"), json.dumps(broken, ensure_ascii=False))
        code, out = run_lint(fabric)
        assert code == 1, out
        assert "long flag '--replay'" in out, out
        assert "SPEC" in out, out

        empty = dict(good); empty["inbox.head"] = ""
        write(ident(fabric, "locale", "ge", "ka-GE.json"), json.dumps(empty, ensure_ascii=False))
        code, out = run_lint(fabric)
        assert code == 1 and "inbox.head is '' — a value is a non-empty string" in out, out

        write(ident(fabric, "locale", "ge", "ka-GE.json"), json.dumps(default))
        code, out = run_lint(fabric)
        assert code == 1 and "no value is in the locale" in out, out

        # A placeholder's NAME is an identifier the translation must keep
        # byte-identical, so counting it as Latin letters made a real
        # translation read as an English copy.
        # Every value here fails the old letter count and only the first
        # passes the new one, so the case turns on the placeholder rule
        # alone: 8 Georgian letters against 17 Latin with the placeholder
        # names counted, 8 against 7 without them.
        write(ident(fabric, "locale", "ge", "ka-GE.json"),
              json.dumps({"inbox.head": "ᲨᲔᲛᲝᲡᲣᲚᲘ gzcoord {who}, {channel}",
                          "replay.usage": "ᲒᲐᲛᲝ: inbox.mjs --replay <seq|message-id>",
                          "inbox.others-header": "ᲐᲠ (SPEC §17):"}, ensure_ascii=False))
        code, out = run_lint(fabric)
        assert code == 0, f"a placeholder-heavy translation is still a translation: {out}"

        write(ident(fabric, "locale", "ge", "ka-GE.json"), "{not json")
        code, out = run_lint(fabric)
        assert code == 1 and "not JSON" in out, out

        # A control character in a value reaches a session's context. A
        # NEWLINE most of all: it prints a second line there, which the
        # reader cannot tell from a line the tool itself wrote.
        for bad in ("\x07", "\n", "\t", "\u009b", "\u2028", "\u202e"):
            write(ident(fabric, "locale", "ge", "ka-GE.json"),
                  json.dumps({**good, "inbox.others-header": f"ᲐᲠ ᲐᲠᲘᲡ{bad} (SPEC §17):"}, ensure_ascii=False))
            code, out = run_lint(fabric)
            assert code == 1 and "carries a control character" in out, f"{bad!r} passed:\n{out}"

        # The schema states the key shape and nothing else does, so lint
        # SAYS when it cannot be read instead of quietly restating it.
        write(ident(fabric, "locale", "ge", "ka-GE.json"), json.dumps(good, ensure_ascii=False))
        schema = os.path.join(fabric, "communication", "gzcoord", "i18n", "i18n.schema.json")
        os.remove(schema)
        code, out = run_lint(fabric)
        assert code == 1 and "the key shape is stated here and nothing else states it" in out, out
        write(schema, json.dumps({"type": "object"}))
        code, out = run_lint(fabric)
        assert code == 1 and "no usable propertyNames.pattern" in out, out
        # A pattern that does not compile, and a schema that is not an
        # object: both used to leave lint as a traceback.
        for shape in (json.dumps({"propertyNames": {"pattern": "["}}), json.dumps(["not", "an", "object"])):
            write(schema, shape)
            code, out = run_lint(fabric)
            assert code == 1 and "no usable propertyNames.pattern" in out, f"{shape}:\n{out}"
        # And the schema is judged even when the default dictionary is not there.
        os.remove(schema)
        default_json = os.path.join(fabric, "communication", "gzcoord", "i18n", "en-US.json")
        os.remove(default_json)
        code, out = run_lint(fabric)
        assert code == 1 and "the key shape is stated here and nothing else states it" in out, out
        write(default_json, json.dumps(default))
        shutil.copy2(REAL_I18N_SCHEMA, schema)
        code, out = run_lint(fabric)
        assert code == 0, out


def case_non_latin_translation_budget_is_stricter() -> None:
    """A Georgian body is budgeted at the measured 1.5 characters a token,
    not four, against three times the tier-1 budget (the measured cost of
    a full rendering): a body that passes the flat estimate is refused,
    and a full rendering's size passes. Kills: using CHARS_PER_TOKEN for a
    non-Latin body; a ceiling no rendering can meet."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        # ~15 000 letters: 3 750 tokens at 4/char (under 9 000), 10 000 at 1.5/char (over)
        big = "\n# წ\n\n" + ("ქართული ტექსტი " * 1000) + "\n"
        text = _translation(_digest_of_body(ident(fabric, "charter.md"))).replace(GE_BODY, big)
        write(ident(fabric, "locale", "ge", "charter.md"), text)
        code, out = run_lint(fabric)
        assert code == 1 and "at 1.5 chars/token" in out and "locale budget 9000" in out, out
        # The first real rendering's size (11 041 characters, ~7 360 at 1.5) passes.
        real = "\n# წ\n\n" + ("ქართული ტექსტი " * 735) + "\n"
        write(ident(fabric, "locale", "ge", "charter.md"), _translation(_digest_of_body(ident(fabric, "charter.md"))).replace(GE_BODY, real))
        code, out = run_lint(fabric)
        assert code == 0, out


def case_quoted_description_round_trips() -> None:
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        inner = 'Uses the two-step "commented out, later" pattern'
        write(dom(fabric, "domain", "good.md"), SLICE.replace(
            'description: "A well-formed slice, shaped like the real ones"', f'description: "{inner}"'))
        write(proj(fabric, "INDEX.md"), index_for(
            f"- [`../agent-fabric/memory/domains/web-dev/domain/good.md`](../agent-fabric/memory/domains/web-dev/domain/good.md) — {inner}\n"))
        code, out = run_lint(fabric)
        assert code == 0, f"an unescaped-quote description was read differently than assemble reads it:\n{out}"


def case_authored_classes_only_in_identities() -> None:
    """A charter-class file under memory/ is a hand-authored claim with no
    evidence smuggled past provenance."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(proj(fabric, "charter.md"), CHARTER)
        write(proj(fabric, "INDEX.md"), index_for(
            "- [`.agent-fabric/memory/web-dev/charter.md`](.agent-fabric/memory/web-dev/charter.md) — The web sub-apps.\n"))
        code, out = run_lint(fabric)
        assert code == 1 and "belongs under identities/roles/" in out, out


def case_brief_is_identity_too() -> None:
    """The brief (how the role works, read to every session at launch) is
    the third authored class: beside the charter it lints clean and the
    index may list it; under memory/ it is refused like a charter."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        brief = CHARTER.replace("class: charter", "class: brief")
        write(ident(fabric, "brief.md"), brief)
        write(proj(fabric, "INDEX.md"), index_for(
            CHARTER_LINE +
            "- [`../agent-fabric/identities/roles/web-dev/brief.md`](../agent-fabric/identities/roles/web-dev/brief.md) — The web sub-apps.\n"))
        code, out = run_lint(fabric)
        assert code == 0, f"a brief beside its charter was refused:\n{out}"
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(proj(fabric, "brief.md"), CHARTER.replace("class: charter", "class: brief"))
        write(proj(fabric, "INDEX.md"), index_for(
            "- [`.agent-fabric/memory/web-dev/brief.md`](.agent-fabric/memory/web-dev/brief.md) — The web sub-apps.\n"))
        code, out = run_lint(fabric)
        assert code == 1 and "belongs under identities/roles/" in out, out


def case_prompt_templates_are_linted() -> None:
    """The launch-prompt sections are not slices, so they are checked by
    name: present, carrying {role}, hygiene-clean, within one budget."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        os.remove(os.path.join(fabric, "identities", "prompt", "team.md"))
        code, out = run_lint(fabric)
        assert code == 1 and "identities/prompt/team.md: missing" in out, out
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(os.path.join(fabric, "identities", "prompt", "memory.md"), "# Memory\n\nGeneric text, no placeholder.\n")
        code, out = run_lint(fabric)
        assert code == 1 and "no {role} placeholder" in out, out
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(os.path.join(fabric, "identities", "prompt", "memory.md"), "{role} " + "padding words " * 2000)
        code, out = run_lint(fabric)
        assert code == 1 and "exceeds the" in out and "budget every session pays" in out, out


def case_knowledge_not_in_identities() -> None:
    """A distilled slice beside the charter is knowledge nothing indexes."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(ident(fabric, "solution.md"), SLICE.replace("class: domain", "class: solution"))
        code, out = run_lint(fabric)
        assert code == 1 and "belongs under memory/" in out, out


def case_taxonomy_roles_are_catalogued() -> None:
    """A project may bind only roles the catalogue defines, and only with
    repository-relative paths."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        tax = dict(TAXONOMY)
        tax["roles"] = [{"id": "web-dev", "paths": ["apps/"]}, {"id": "ghost", "paths": ["/home/someone/x/"]}]
        write(os.path.join(fabric, "projects", PROJECT, "taxonomy.json"), json.dumps(tax))
        code, out = run_lint(fabric)
        assert code == 1, out
        assert "'ghost' is not in identities/roles/catalog.json" in out, out
        assert "machine-specific" in out, out


def write_profiles(fabric: str, doc: dict) -> None:
    write(os.path.join(fabric, "routing", "profiles.json"), json.dumps(doc))


def case_model_profiles_layered_file_passes() -> None:
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write_profiles(fabric, PROFILES)
        code, out = run_lint(fabric)
        assert code == 0, f"a well-formed layered profile tripped the linter:\n{out}"


def case_model_profiles_cheap_review_is_refused() -> None:
    """A row that moves the review class off the review-grade list is a
    finding; a row that moves a CODING class to a cheap model is not."""
    import copy
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        doc = copy.deepcopy(PROFILES)
        doc["agents"]["web-dev-01"]["capabilities"] = {"code-review": "z-ai/glm-5.3-flash"}
        write_profiles(fabric, doc)
        code, out = run_lint(fabric)
        assert code == 1, f"a non-review-grade review model passed:\n{out}"
        assert "agents.web-dev-01" in out and "review-grade" in out, f"the row went unnamed:\n{out}"
        doc = copy.deepcopy(PROFILES)
        doc["agents"]["web-dev-01"]["capabilities"] = {"code-high": "z-ai/glm-5.3-flash"}
        write_profiles(fabric, doc)
        code, out = run_lint(fabric)
        assert code == 0, f"a cheap coding class was review-gated:\n{out}"


def case_model_profiles_agents_are_logins() -> None:
    import copy
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        doc = copy.deepcopy(PROFILES)
        doc["agents"]["clone-74e1ddd4096a45ce"] = {"session": "z-ai/glm-5.3"}
        write_profiles(fabric, doc)
        code, out = run_lint(fabric)
        assert code == 1 and "is not a Linux login" in out, out


def case_model_profiles_unknown_role_is_refused() -> None:
    import copy
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        doc = copy.deepcopy(PROFILES)
        doc["roles"]["wed-dev"] = doc["roles"].pop("web-dev")
        write_profiles(fabric, doc)
        code, out = run_lint(fabric)
        assert code == 1, f"a typo'd role key passed:\n{out}"
        assert "roles.wed-dev" in out, f"the unknown role went unnamed:\n{out}"


def case_model_profiles_schema_is_enforced() -> None:
    import copy
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        doc = copy.deepcopy(PROFILES)
        doc["defaults"]["session"] = "Claude Sonnet"
        write_profiles(fabric, doc)
        code, out = run_lint(fabric)
        assert code == 1, f"a malformed model id passed the schema:\n{out}"
        assert "routing/profiles.json" in out, f"the file went unnamed:\n{out}"


def _write_license_layout(fabric: str, registry: dict, reuse_toml: str, licenses: tuple = ("Apache-2.0",),
                          clients: bool = True) -> None:
    """`clients=False` writes the registry as given, for a case that judges
    the clients themselves."""
    os.makedirs(os.path.join(fabric, "projects"), exist_ok=True)
    if clients:
        write_clients(os.path.join(fabric, "projects"))
        registry = with_client(registry)
    with open(os.path.join(fabric, "projects", "registry.json"), "w", encoding="utf-8") as fh:
        json.dump(registry, fh)
    with open(os.path.join(fabric, "REUSE.toml"), "w", encoding="utf-8") as fh:
        fh.write(reuse_toml)
    shutil.rmtree(os.path.join(fabric, "LICENSES"), ignore_errors=True)
    os.makedirs(os.path.join(fabric, "LICENSES"))
    for lic in licenses:
        with open(os.path.join(fabric, "LICENSES", lic + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(lic + "\n")


REUSE_OK = """version = 1
[[annotations]]
path = ["**"]
precedence = "aggregate"
SPDX-FileCopyrightText = "t"
SPDX-License-Identifier = "Apache-2.0"
"""


def case_the_repository_is_one_license() -> None:
    """Apache-2.0 throughout: REUSE.toml may assign nothing else, every
    identifier it uses has its text, every project names ITS OWN license
    as information, and no project knowledge lives here."""
    registry = {"projects": {
        "agent-fabric": {"license": "Apache-2.0"},
        PROJECT: {"license": "LicenseRef-demo-Proprietary"},
    }}
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        _write_license_layout(fabric, registry, REUSE_OK)
        code, out = run_lint(fabric)
        assert code == 0, f"a single-license layout was refused:\n{out}"
        # a second license assigned in REUSE.toml
        _write_license_layout(fabric, registry, REUSE_OK + '[[annotations]]\npath = ["projects/demo/**"]\nprecedence = "override"\nSPDX-FileCopyrightText = "t"\nSPDX-License-Identifier = "LicenseRef-demo-Proprietary"\n', licenses=("Apache-2.0", "LicenseRef-demo-Proprietary"))
        code, out = run_lint(fabric)
        assert code == 1 and "Apache-2.0 throughout" in out, f"a second license passed:\n{out}"
        # the one license has no text
        _write_license_layout(fabric, registry, REUSE_OK, licenses=())
        code, out = run_lint(fabric)
        assert code == 1 and "no LICENSES/Apache-2.0.txt" in out, f"missing license text passed:\n{out}"
        # a project naming no license at all
        _write_license_layout(fabric, {"projects": {"agent-fabric": {"license": "Apache-2.0"}, PROJECT: {}}}, REUSE_OK)
        code, out = run_lint(fabric)
        assert code == 1 and "project 'demo' names no license" in out, f"licenseless project passed:\n{out}"
        # project knowledge in the fabric
        _write_license_layout(fabric, registry, REUSE_OK)
        os.makedirs(os.path.join(fabric, "memory", "projects", PROJECT), exist_ok=True)
        code, out = run_lint(fabric)
        assert code == 1 and "lives in the project's repository" in out, f"project knowledge here passed:\n{out}"


def case_every_project_names_a_defined_client() -> None:
    """ADR-045 §5 rule 5: a working copy resolves remote -> project ->
    client, so a project's client must be one projects/clients.json
    defines. A tree is judged whenever its registry has projects."""
    registry = {"projects": {"agent-fabric": {"license": "Apache-2.0", "client": "self"},
                             PROJECT: {"license": "Apache-2.0", "client": "acme"}}}
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        _write_license_layout(fabric, registry, REUSE_OK, clients=False)
        write(os.path.join(fabric, "projects", "clients.json"),
              json.dumps({"version": 1, "clients": {"self": {}, "acme": {}}}))
        code, out = run_lint(fabric)
        assert code == 0, f"defined clients were refused:\n{out}"
        write(os.path.join(fabric, "projects", "clients.json"), json.dumps({"version": 1, "clients": {"self": {}}}))
        code, out = run_lint(fabric)
        assert code == 1 and "names client 'acme', which projects/clients.json does not define" in out, out
        os.remove(os.path.join(fabric, "projects", "clients.json"))
        code, out = run_lint(fabric)
        assert code == 1 and "names client 'self'" in out, f"a deleted clients.json passed:\n{out}"
        _write_license_layout(fabric, {"projects": {"agent-fabric": {"license": "Apache-2.0", "client": "self"},
                                                    PROJECT: {"license": "Apache-2.0"}}}, REUSE_OK, clients=False)
        code, out = run_lint(fabric)
        assert code == 1 and "project 'demo' names no client" in out, f"a project with no client passed:\n{out}"


def case_a_registry_with_projects_and_no_clients_is_a_finding() -> None:
    """Deleting clients.json and every client field must not pass lint
    (ADR-045 §5 rule 5)."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        _write_license_layout(fabric, {"projects": {"agent-fabric": {"license": "Apache-2.0"},
                                                    PROJECT: {"license": "Apache-2.0"}}}, REUSE_OK, clients=False)
        assert not os.path.exists(os.path.join(fabric, "projects", "clients.json"))
        code, out = run_lint(fabric)
        assert code == 1 and "project 'demo' names no client" in out, f"a clientless registry passed:\n{out}"


def case_the_class_list_a_reader_sees_is_the_real_one() -> None:
    """README.md and CLAUDE.md spell out the capability classes; each list
    must be exactly what routing/capabilities.json defines. The README
    said `review` for a class named code-review for days (2026-09-16)."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        classes = sorted(json.load(open(os.path.join(fabric, "routing", "capabilities.json")))["classes"])
        row = "| **CAPABILITY** | x | `routing/capabilities.json` classes: " + ", ".join(f"`{c}`" for c in classes) + " |\n"
        write(os.path.join(fabric, "README.md"), "# r\n\n" + row)
        code, out = run_lint(fabric)
        assert code == 0, f"the real list was refused:\n{out}"
        write(os.path.join(fabric, "README.md"), "# r\n\n" + row.replace("`code-review`", "`review`"))
        code, out = run_lint(fabric)
        assert code == 1 and "README.md: names capability class 'review'" in out \
            and "does not name capability class 'code-review'" in out, f"a wrong class name passed:\n{out}"
        write(os.path.join(fabric, "README.md"), "# r\n\nno classes here\n")
        code, out = run_lint(fabric)
        assert code == 1 and "class list was not found" in out, f"a README without the list passed:\n{out}"
        # CLAUDE.md's sentence is checked the same way
        write(os.path.join(fabric, "README.md"), "# r\n\n" + row)
        write(os.path.join(fabric, "CLAUDE.md"), "- **Subagents** name a capability class in `subagent_type` — the five\n  are `code-low`, `code-medium` — and the alias.\n")
        code, out = run_lint(fabric)
        assert code == 1 and "CLAUDE.md: does not name capability class 'code-high'" in out, f"CLAUDE.md drift passed:\n{out}"


def case_a_bound_and_held_role_is_not_a_candidate() -> None:
    """candidate: true is refused once a project taxonomy binds the role and
    a login named for it is placed on a host — the proof is structural
    (2026-09-18). Without a placed login, or with the flag gone, clean.
    Kills: dropping the rule, or matching a login that is not the role's."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        cat_path = os.path.join(fabric, "identities", "roles", "catalog.json")
        cat = json.load(open(cat_path, encoding="utf-8"))
        for r in cat["roles"]:
            if r["id"] == "web-dev":
                r["candidate"] = True
        write(cat_path, json.dumps(cat))
        reg = os.path.join(fabric, "runtime", "hosts", "registry.json")
        host = {"version": 1, "hosts": {"h1": {"platform": "debian", "ssh": None, "operator": "op", "fabric": "x"}}}
        write(reg, json.dumps({**host, "placement": {"db-admin": "h1", "web-developer-x": "h1"}}))
        code, out = run_lint(fabric)
        assert code == 0, f"a candidate with no login of its own was refused (web-developer-x is not web-dev's):\n{out}"
        write(reg, json.dumps({**host, "placement": {"web-dev-01": "h1"}}))
        code, out = run_lint(fabric)
        assert code == 1 and "role 'web-dev' is a candidate" in out and "web-dev-01 holds it" in out, f"a bound and held candidate passed:\n{out}"
        for r in cat["roles"]:
            r.pop("candidate", None)
        write(cat_path, json.dumps(cat))
        code, out = run_lint(fabric)
        assert code == 0, f"the flag dropped, still a finding:\n{out}"


def case_a_skill_carries_rules_not_occasions() -> None:
    """ADR-016: a skill's description says when to load it; its body names
    no date, no pull-request number and no numbered login."""
    import sys as _s
    _s.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    import lint as L
    with tempfile.TemporaryDirectory() as root:
        write(os.path.join(root, "runtime", "hosts", "registry.json"),
              json.dumps({"version": 1, "hosts": {}, "placement": {"web-dev-01": "h", "user": "h"}}))
        good = os.path.join(root, "policies", "good", "SKILL.md")
        write(good, '---\nname: good\ndescription: "Load it when a thing happens."\n---\n# Good\nThe user runs it.\n')
        assert L.skill_findings(root) == [], L.skill_findings(root)
        bad = os.path.join(root, "policies", "bad", "SKILL.md")
        write(bad, '---\nname: bad\ndescription: "A thing."\n---\n# Bad\nSince 2026-09-28 (#57), web-dev-01 does it.\n')
        got = L.skill_findings(root)
        assert any("names no occasion" in f for f in got), got
        assert any("a date" in f for f in got) and any("pull-request number" in f for f in got), got
        assert any("'web-dev-01'" in f for f in got) and not any("'user'" in f for f in got), got
        os.remove(bad)
        # The description is scanned too, and a number glued to a word counts.
        write(bad, '---\nname: bad\ndescription: "Load it when X; since 2026-09-28, web-dev-01 found it (PR#57)."\n---\n# Bad\nBody.\n')
        got = L.skill_findings(root)
        assert any("a date" in f for f in got) and any("'web-dev-01'" in f for f in got), got
        assert any("pull-request number" in f and "PR#57" in f for f in got), got
        os.remove(bad)
        write(bad, '---\nname: bad\ndescription: "Load it when X."\n---\n# Bad\nSee gzapp#12.\n')
        assert any("gzapp#12" in f for f in L.skill_findings(root)), L.skill_findings(root)
        os.remove(bad)
        loc = os.path.join(root, "identities", "roles", "r", "locale", "ru", "skills", "x", "SKILL.md")
        write(loc, '---\nname: x\ndescription: "x"\n---\n2026-01-01\n')
        assert not any("locale" in f for f in L.skill_findings(root)), "a locale's copy is its holder's"


def case_the_host_registry_is_one_host_per_id_and_placements_are_known() -> None:
    def registry(hosts, placement):
        return json.dumps({"version": 1, "hosts": hosts, "placement": placement})
    H = {"platform": "debian", "ssh": "op@h2.example", "operator": "op", "fabric": "~/projects/agent-fabric"}
    L = {"platform": "fedora-qubes", "ssh": None, "operator": "user", "fabric": "~/projects/agent-fabric"}
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        shutil.copytree(os.path.join(ROOT, "runtime", "hosts", "schema"), os.path.join(fabric, "runtime", "hosts", "schema"))
        reg = os.path.join(fabric, "runtime", "hosts", "registry.json")
        write(reg, registry({"local": L, "h2": H}, {"a": "local", "b": "h2"}))
        code, out = run_lint(fabric)
        assert code == 0, f"a sound registry was refused:\n{out}"
        write(reg, registry({"local": L, "h2": H, "h3": H}, {"a": "local"}))
        code, out = run_lint(fabric)
        assert code == 1 and "share the ssh destination" in out, f"two hosts on one destination passed:\n{out}"
        write(reg, registry({"h2": H}, {"a": "h2"}))
        code, out = run_lint(fabric)
        assert code == 1 and "exactly one host has ssh null" in out, f"no local host passed:\n{out}"
        write(reg, registry({"local": L}, {"a": "elsewhere"}))
        code, out = run_lint(fabric)
        assert code == 1 and "names host 'elsewhere', which is not registered" in out, f"an unknown placement passed:\n{out}"
        # ADR-044: a placed login's kind is agent or human.
        write(reg, json.dumps({"version": 1, "hosts": {"local": L}, "placement": {"a": "local", "deck": "local"},
                               "kinds": {"deck": "human"}}))
        code, out = run_lint(fabric)
        assert code == 0, f"a human kind was refused:\n{out}"
        write(reg, json.dumps({"version": 1, "hosts": {"local": L}, "placement": {"a": "local"}, "kinds": {"a": "robot"}}))
        code, out = run_lint(fabric)
        assert code == 1 and "'robot'" in out, f"a kind that is neither agent nor human passed:\n{out}"
        write(reg, json.dumps({"version": 1, "hosts": {"local": L}, "placement": {"a": "local"}, "kinds": {"ghost": "human"}}))
        code, out = run_lint(fabric)
        assert code == 1 and "'ghost', which is not placed" in out, f"a kind for an unplaced login passed:\n{out}"
        write(reg, registry({"Bad_Host": L}, {}))
        code, out = run_lint(fabric)
        assert code == 1 and "Bad_Host" in out, f"an id that is not a short hostname passed:\n{out}"
        write(reg, registry({"local": {**L, "role": "fabric-coordinator"}}, {}))
        code, out = run_lint(fabric)
        assert code == 1 and "role" in out, f"a role in a host entry passed (placement is never identity):\n{out}"


def case_the_agentd_selector_is_sound_and_names_placed_logins() -> None:
    L = {"platform": "fedora-qubes", "ssh": None, "operator": "op", "fabric": "~/projects/agent-fabric"}
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(os.path.join(fabric, "runtime", "hosts", "registry.json"),
              json.dumps({"version": 1, "hosts": {"local": L}, "placement": {"a": "local"}}))
        sel = os.path.join(fabric, "runtime", "control", "agentd.json")
        code, out = run_lint(fabric)
        assert code == 0, f"no selector at all was refused:\n{out}"
        write(sel, json.dumps({"description": "d", "default": "node", "python": ["a"]}))
        code, out = run_lint(fabric)
        assert code == 0, f"a sound selector was refused:\n{out}"
        for doc, want in (({"default": "node", "python": [], "node": ["a"]}, "unknown key 'node'"),
                          ({"default": "deno", "python": []}, "default is 'deno'"),
                          ({"default": "node", "python": ["ghost"]}, "python names 'ghost', which runtime/hosts/registry.json does not place")):
            write(sel, json.dumps(doc))
            code, out = run_lint(fabric)
            assert code == 1 and want in out, f"{doc} passed:\n{out}"
        write(sel, "{broken")
        code, out = run_lint(fabric)
        assert code == 1 and "agentd.json: does not parse" in out, f"a selector that is not JSON passed:\n{out}"


def case_a_managed_projects_name_stays_out_of_generic_files() -> None:
    """A project id from the registry in a role skill, the provisioning,
    a tool or the GZCoord runtime is a finding; the fabric's own remote,
    tests, READMEs and history are not."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        _write_license_layout(fabric, {"projects": {
            "agent-fabric": {"license": "Apache-2.0", "remotes": ["git@github.com:gzapi-org/agent-fabric.git"]},
            "acme.shop": {"license": "Apache-2.0", "remotes": ["git@github.com:acme/acme.shop.git"]}}}, REUSE_OK)
        code, out = run_lint(fabric)
        assert code == 0, f"the base was refused:\n{out}"
        write(ident(fabric, "skills", "probe", "SKILL.md"), SKILL + "\nRead ACME_SHOP_PORT_OFFSET first.\n")
        code, out = run_lint(fabric)
        assert code == 1 and "identities/roles/web-dev/skills/probe/SKILL.md" in out and "'ACME_SHOP_'" in out, f"a project's variable in a skill passed:\n{out}"
        write(ident(fabric, "skills", "probe", "SKILL.md"), SKILL + "\nThe acme.shop checkout is under ~/projects.\n")
        code, out = run_lint(fabric)
        assert code == 1 and "'acme.shop'" in out, f"a project's id in a skill passed:\n{out}"
        write(ident(fabric, "skills", "probe", "SKILL.md"), SKILL + "\nClone gzapi-org/agent-fabric first; see the README.\n")
        code, out = run_lint(fabric)
        assert code == 0, f"the fabric's own remote was taken for a project:\n{out}"
        os.makedirs(os.path.join(fabric, "runtime", "provisioning"), exist_ok=True)
        write(os.path.join(fabric, "runtime", "provisioning", "test_x.sh"), "# acme.shop in a test is fine\n")
        write(os.path.join(fabric, "runtime", "provisioning", "README.md"), "# acme.shop in a README is fine\n")
        code, out = run_lint(fabric)
        assert code == 0, f"a test or README was linted as generic code:\n{out}"
        write(os.path.join(fabric, "runtime", "provisioning", "x.sh"), "echo acme.shop\n")
        code, out = run_lint(fabric)
        assert code == 1 and "runtime/provisioning/x.sh:1" in out, f"provisioning naming a project passed:\n{out}"
        os.remove(os.path.join(fabric, "runtime", "provisioning", "x.sh"))
        # A shared skill under policies/ is generic (ADR-016 rule 1); the rest
        # of policies/ describes the fabric's history with its projects.
        write(os.path.join(fabric, "policies", "AUTHORITY.md"), "acme.shop's CI runs its own copy.\n")
        code, out = run_lint(fabric)
        assert code == 0, f"policies/ prose was linted as generic:\n{out}"
        write(os.path.join(fabric, "policies", "shared-thing", "SKILL.md"), SKILL + "\nThe acme.shop checkout first.\n")
        code, out = run_lint(fabric)
        assert code == 1 and "policies/shared-thing/SKILL.md" in out and "'acme.shop'" in out, \
            f"a project's id in a policy skill passed:\n{out}"


def case_review_lenses_are_named_described_and_bounded() -> None:
    """The lens directory is the vocabulary: each file names itself, has a
    one-line description, a body under the cap; general.md must exist."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        lenses = os.path.join(fabric, "runtime", "claude-code", "review", "lenses")
        write(os.path.join(lenses, "general.md"), "---\nname: general\ndescription: The ordinary review.\n---\nLook at everything.\n")
        write(os.path.join(lenses, "security.md"), "---\nname: security\ndescription: Trust boundaries.\n---\nWhere does input enter?\n")
        code, out = run_lint(fabric)
        assert code == 0, f"sound lenses were refused:\n{out}"
        write(os.path.join(lenses, "security.md"), "---\nname: secure\ndescription: Trust boundaries.\n---\nWhere does input enter?\n")
        code, out = run_lint(fabric)
        assert code == 1 and "security.md: name 'secure' must equal the filename" in out, f"a misnamed lens passed:\n{out}"
        write(os.path.join(lenses, "security.md"), "---\nname: security\ndescription: Trust boundaries.\n---\n" + ("x" * 1600) + "\n")
        code, out = run_lint(fabric)
        assert code == 1 and "the cap is 1500" in out, f"an oversized lens passed:\n{out}"
        write(os.path.join(lenses, "security.md"), "Where does input enter?\n")
        code, out = run_lint(fabric)
        assert code == 1 and "no frontmatter" in out, f"a lens without frontmatter passed:\n{out}"
        os.remove(os.path.join(lenses, "security.md")); os.remove(os.path.join(lenses, "general.md"))
        write(os.path.join(lenses, "cleanup.md"), "---\nname: cleanup\ndescription: Dead code.\n---\nWhat is unreachable now?\n")
        code, out = run_lint(fabric)
        assert code == 1 and "no general.md" in out, f"a lens directory without general passed:\n{out}"


def case_a_committed_agent_source_may_not_pin_effort() -> None:
    """The one-writer invariant: a class's level is routing/effort.json's
    and is written into the INSTALLED copy by install-agent-files.sh. A
    hand-written one in the source is the second place it is decided, and
    the one nobody updates. Kills: dropping agent_source_findings."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        agent = os.path.join(fabric, "runtime", "claude-code", "agents", "code-high.md")
        write(agent, "---\nname: code-high\ndescription: x\nmodel: opus\n---\n\nDo the work.\n")
        code, out = run_lint(fabric)
        assert code == 0, f"an agent source without a level tripped the linter:\n{out}"

        write(agent, "---\nname: code-high\ndescription: x\nmodel: opus\neffort: max\n---\n\nDo the work.\n")
        code, out = run_lint(fabric)
        assert code != 0 and "effort:" in out and "code-high.md" in out, \
            f"a hand-written effort: in a committed agent source was not refused:\n{out}"

        # The locale worker is installed the same way, so it is the same rule.
        write(agent, "---\nname: code-high\ndescription: x\nmodel: opus\n---\n\nDo the work.\n")
        worker = os.path.join(fabric, "identities", "roles", "language-culture", "locale", "ge", "worker.md")
        write(worker, "---\nname: locale-worker\ndescription: (agent-fabric) x\nmodel: opus\neffort: low\n---\n\nx\n")
        code, out = run_lint(fabric)
        assert code != 0 and "worker.md" in out, \
            f"the locale worker is outside the one-writer rule:\n{out}"


def case_decision_records_are_lint_findings() -> None:
    """docs/adr/ in a fabric is checked by tools/fabric/adr.py and each of its
    findings is a lint finding (agent-fabric ADR-001); a fabric with no
    records is not asked for any."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        code, out = run_lint(fabric)
        assert code == 0 and "adr:" not in out, out
        shutil.copytree(os.path.join(ROOT, "docs", "adr"), os.path.join(fabric, "docs", "adr"))
        idx = os.path.join(fabric, "docs", "adr", "index.json")
        with open(idx, "a", encoding="utf-8") as fh:
            fh.write(" ")
        code, out = run_lint(fabric)
        assert code == 1 and "adr: docs/adr/index.json: stale" in out, out


def case_a_committed_agent_key_needs_its_lineage() -> None:
    """ADR-038 §5 rule 2, ADR-039: lineage.json naming an agent whose key
    is not committed, an entry keyed by anything but an agent id, or a
    committed key with no lineage entry, is a finding; no identities/keys/
    at all is clean."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    AID = "019bbe31-2fff-7a2f-9849-96bdf286e011"   # a UUIDv7 born 2026-01-14T20:27:33.247Z
    with tempfile.TemporaryDirectory() as root:
        assert lint.key_lineage_findings(root) == [], "no keys committed yet is clean"
        keys = os.path.join(root, "identities", "keys")
        os.makedirs(keys)
        with open(os.path.join(keys, "lineage.json"), "w", encoding="utf-8") as fh:
            json.dump({AID: {"login": "someone", "born": "2026-01-14T20:27:33.247Z", "fingerprint": "0" * 40, "parent": None},
                       "someone-else": {"fingerprint": "1" * 40, "parent": None}}, fh)
        with open(os.path.join(keys, "stray.asc"), "w", encoding="utf-8") as fh:
            fh.write("")
        got = lint.key_lineage_findings(root)
        assert any(f"{AID} has no committed key" in f for f in got), got
        assert any("someone-else is not an agent id" in f for f in got), got
        assert any("stray.asc: no lineage.json entry" in f for f in got), got


def case_a_cited_fabric_document_must_resolve() -> None:
    """A fabric document path or 'agent-fabric ADR-NNN' cited in a tracked
    file that resolves nowhere is a finding — from the root or the citing
    file's directory; evidence, history, memory and tests are exempt; a
    deeper docs/ path is a project's example and not a fabric document."""
    with tempfile.TemporaryDirectory() as root:
        fabric = make_base(root)
        write(os.path.join(fabric, "docs", "here.md"), "# here\n")
        write(os.path.join(fabric, "communication", "gzcoord", "docs", "RELAY.md"), "# relay\n")
        write(os.path.join(fabric, "tools", "fabric", "cites.py"),
              "# see docs/here.md and docs/gone.md and agent-fabric ADR-042\n"
              "# a project's docs/scratchpad/decision.md is an example\n")
        write(os.path.join(fabric, "communication", "gzcoord", "README.md"), "see docs/RELAY.md beside me\n")
        write(os.path.join(fabric, "docs", "live-checks", "2026-09-17-x.md"), "cites docs/also-gone.md\n")
        subprocess.run(["git", "-C", fabric, "init", "-q"], check=True, env=git_env())
        subprocess.run(["git", "-C", fabric, "add", "-A"], check=True, env=git_env())
        code, out = run_lint(fabric)
        assert "tools/fabric/cites.py: cites docs/gone.md, which does not exist" in out, out
        assert "tools/fabric/cites.py: cites agent-fabric ADR-042, which does not exist" in out, out
        assert "docs/here.md, which" not in out and "scratchpad" not in out, "a resolving path or a project's example was flagged"
        assert "RELAY.md" not in out, "a path relative to the citing file's own directory resolves"
        assert "also-gone" not in out, "a live check is evidence and exempt"
        assert code == 1, "a dangling citation is a finding"


def case_arm_boundary_cases_only_leave_retired() -> None:
    """A project's arm.json lists the paths that must stay boundary: each
    must match its own patterns, and one the branch forked with leaves only
    into boundary.retired with why and whose word (reviews of #89, #90)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=git_env())
        rel = os.path.join("projects", "demo", "integration", "gh", "arm.json")
        def arm(cases, retired=None, paths="^src/|key", exempt="^docs/", changes=None, waiver_role=None):
            b = {"paths": paths, "exempt": exempt, "cases": cases}
            if retired is not None:
                b["retired"] = retired
            if changes is not None:
                b["changes"] = changes
            doc = {"boundary": b}
            if waiver_role is not None:
                doc["waiver_role"] = waiver_role
            write(os.path.join(root, rel), json.dumps(doc))
        write(os.path.join(root, "identities", "roles", "catalog.json"),
              json.dumps({"roles": [{"id": "architect-cto"}, {"id": "devex-tooling"}]}))
        arm(["src/a.rs", "lib/key.rs"])
        g("init", "-q", "-b", "main")
        g("add", "-A")
        g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
        g("branch", "base")
        assert lint.arm_boundary_findings(root, base_ref="base") == [], "cases that match: clean"
        arm(["src/a.rs"])
        got = lint.arm_boundary_findings(root, base_ref="base")
        assert any("'lib/key.rs' is dropped" in f for f in got), got
        arm(["src/a.rs"], retired={"lib/key.rs": "keys moved to crates/; architect-cto, seq 1"})
        assert lint.arm_boundary_findings(root, base_ref="base") == [], "retired with why and word: clean"
        arm(["src/a.rs"], retired={"lib/key.rs": "removed"})
        assert any("is dropped" in f for f in lint.arm_boundary_findings(root, base_ref="base")), \
            "a reason citing no approval anyone could look up (#91's review)"
        arm(["src/a.rs"], retired={"lib/key.rs": "architect-cto, 01a105c9-b3e2-779e-99ed-9a8347021555"})
        assert lint.arm_boundary_findings(root, base_ref="base") == [], "a message id is a locator"
        arm(["src/a.rs"], retired={"lib/key.rs": " "})
        assert any("is dropped" in f for f in lint.arm_boundary_findings(root, base_ref="base")), \
            "a blank reason is no reason"
        arm(["src/a.rs", "lib/key.rs"], paths="^src/")
        got = lint.arm_boundary_findings(root, base_ref="base")
        assert any("'lib/key.rs' is not boundary" in f for f in got), "a narrowed pattern its case catches"
        arm(["docs/src/x.md"], paths="src/")
        assert any("not boundary" in f for f in lint.arm_boundary_findings(root, base_ref="base")), \
            "an exempt path is no boundary case"
        write(os.path.join(root, rel), json.dumps({"boundary": {"paths": "^src/"}}))
        assert any("boundary.cases must list" in f for f in lint.arm_boundary_findings(root, base_ref="base")), \
            "no cases at all"
        # The cases are a floor (review of #91): an alternative no case
        # depends on goes, every case still matches, and only the record of
        # the change stands between that and a silent narrowing.
        arm(["src/a.rs", "lib/key.rs"], paths="^src/|key|^vendor/")
        got = lint.arm_boundary_findings(root, base_ref="base")
        assert any("changed with no new boundary.changes entry" in f for f in got), \
            ("widening the patterns needs a record too", got)
        arm(["src/a.rs", "lib/key.rs"], exempt="^docs/|^vendor/")
        assert any("changed with no new boundary.changes entry" in f
                   for f in lint.arm_boundary_findings(root, base_ref="base")), "a widened exemption, unrecorded"
        arm(["src/a.rs", "lib/key.rs"], exempt="^docs/|^vendor/", changes={"vendor": " "})
        assert any("cites no approval" in f for f in lint.arm_boundary_findings(root, base_ref="base")), \
            "a blank reason records nothing"
        arm(["src/a.rs", "lib/key.rs"], exempt="^docs/|^vendor/",
            changes={"vendor exempt": "vendored docs only; architect-cto, seq 2"})
        assert lint.arm_boundary_findings(root, base_ref="base") == [], "a relay seq is a locator"
        arm(["src/a.rs", "lib/key.rs"], exempt="^docs/|^vendor/", changes={"vendor exempt": "agreed with the team"})
        assert any("cites no approval" in f for f in lint.arm_boundary_findings(root, base_ref="base")), \
            "a change citing nothing checkable"
        arm(["src/a.rs", "lib/key.rs"], exempt="^docs/|^vendor/",
            changes={"vendor exempt": "vendored docs only; gzapi-org/InterWeave#177"})
        assert lint.arm_boundary_findings(root, base_ref="base") == [], "a recorded change: clean"
        arm(["src/a.rs", "lib/key.rs"], exempt="^docs/|^vendor/",
            changes={"vendor exempt": "vendored docs only; architect-cto, #177"})
        assert lint.arm_boundary_findings(root, base_ref="base") == [], "a bare #N is a locator"
        arm(["src/a.rs", "lib/key.rs"], exempt="^docs/|^vendor/|^third/",
            changes={"vendor exempt": "vendored docs only; architect-cto, seq 2", "third exempt": "same again"})
        assert any("'third exempt' cites no approval" in f for f in lint.arm_boundary_findings(root, base_ref="base")), \
            "a second new entry riding on the first's locator (#91's review)"
        # A record is history (#91's review): committed into the base, it
        # may be neither rewritten nor removed.
        arm(["src/a.rs", "lib/key.rs"], changes={"first": "the original rule; architect-cto, seq 3"})
        g("add", "-A")
        g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "a record")
        g("branch", "-f", "base")
        assert lint.arm_boundary_findings(root, base_ref="base") == [], "an unchanged record: clean"
        arm(["src/a.rs", "lib/key.rs"], paths="^src/|key|^vendor/",
            changes={"first": "vendor too; architect-cto, seq 3"})
        got = lint.arm_boundary_findings(root, base_ref="base")
        assert any("'first' is rewritten" in f for f in got), ("a new change under an old record", got)
        arm(["src/a.rs", "lib/key.rs"], changes={})
        assert any("'first' is removed" in f for f in lint.arm_boundary_findings(root, base_ref="base")), \
            "a record removed"
        # retired is history as much as changes is (review of #92, F2).
        arm(["src/a.rs"], changes={"first": "the original rule; architect-cto, seq 3"},
            retired={"lib/key.rs": "keys moved; architect-cto, seq 4"}, waiver_role="architect-cto")
        g("add", "-A")
        g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "retired, and a waiver role")
        g("branch", "-f", "base")
        assert lint.arm_boundary_findings(root, base_ref="base") == [], "the base as it stands: clean"
        arm(["src/a.rs"], changes={"first": "the original rule; architect-cto, seq 3"},
            retired={"lib/key.rs": "keys moved; someone else, seq 9"}, waiver_role="architect-cto")
        assert any("boundary.retired entry 'lib/key.rs' is rewritten" in f
                   for f in lint.arm_boundary_findings(root, base_ref="base")), "a retired record rewritten"
        arm(["src/a.rs"], changes={"first": "the original rule; architect-cto, seq 3"},
            retired={}, waiver_role="architect-cto")
        assert any("boundary.retired entry 'lib/key.rs' is removed" in f
                   for f in lint.arm_boundary_findings(root, base_ref="base")), "a retired record removed"
        # Who may waive is the boundary too (review of #92, F1).
        keep = {"changes": {"first": "the original rule; architect-cto, seq 3"},
                "retired": {"lib/key.rs": "keys moved; architect-cto, seq 4"}}
        arm(["src/a.rs"], waiver_role="devex-tooling", **keep)
        assert any("waiver_role changed with no new" in f for f in lint.arm_boundary_findings(root, base_ref="base")), \
            "a waiver role moved with no record"
        arm(["src/a.rs"], waiver_role="devex-tooling", retired=keep["retired"],
            changes={**keep["changes"], "waiver": "devex-tooling waives; the owner, seq 10"})
        assert lint.arm_boundary_findings(root, base_ref="base") == [], "a recorded waiver role change: clean"
        arm(["src/a.rs"], waiver_role="architect-ctoo", retired=keep["retired"],
            changes={**keep["changes"], "waiver": "typo; the owner, seq 11"})
        assert any("waiver_role 'architect-ctoo' is not a role" in f
                   for f in lint.arm_boundary_findings(root, base_ref="base")), "a misspelt waiver role"
        # A record added with no pattern change is checked too, base or none
        # (review of #92): history would otherwise keep it uncited.
        arm(["src/a.rs"], waiver_role="architect-cto", retired=keep["retired"],
            changes={**keep["changes"], "note": "agreed with the team"})
        for ref in ("base", "no-such-ref"):
            assert any("'note' cites no approval" in f for f in lint.arm_boundary_findings(root, base_ref=ref)), \
                ("an uncited record with no pattern change", ref)
        # A base whose arm.json is malformed: a finding, never a crash
        # (review of #92, round 2).
        for broken in ("{ broken", "[]"):
            write(os.path.join(root, rel), broken)
            g("add", "-A")
            g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "broken base")
            g("branch", "-f", "base")
            arm(["src/a.rs"], waiver_role="architect-cto", retired=keep["retired"], changes=keep["changes"])
            got = lint.arm_boundary_findings(root, base_ref="base")
            assert got == [], ("the repair's records are all cited: nothing to report", broken, got)
        os.remove(os.path.join(root, "identities", "roles", "catalog.json"))
        assert any("cannot be checked: identities/roles/catalog.json" in f
                   for f in lint.arm_boundary_findings(root, base_ref="base")), "an unreadable catalogue is named"
        arm(["src/a.rs"], paths="^src/")
        assert lint.arm_boundary_findings(root, base_ref="no-such-ref") == [], \
            "without a base (a project CI's depth-1 fabric checkout), nothing is compared"
        # A deleted arm.json takes its records with it (review of #92): it
        # leaves only with its project.
        write(os.path.join(root, "identities", "roles", "catalog.json"),
              json.dumps({"roles": [{"id": "architect-cto"}]}))
        write(os.path.join(root, "projects", "registry.json"), json.dumps({"projects": {"demo": {}}}))
        arm(["src/a.rs"], paths="^src/")
        g("add", "-A")
        g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "a usable arm.json")
        g("branch", "-f", "base")
        g("rm", "-q", rel)
        got = lint.arm_boundary_findings(root, base_ref="base")
        assert any("deleted while projects/registry.json still names 'demo'" in f for f in got), \
            ("an arm.json deleted under a registered project", got)
        write(os.path.join(root, "projects", "registry.json"), "{ not json")
        assert any("projects/registry.json: unreadable" in f and "cannot be judged" in f
                   for f in lint.arm_boundary_findings(root, base_ref="base")), \
            "an unreadable registry is no clean bill for a deletion (review of #96)"
        write(os.path.join(root, "projects", "registry.json"), json.dumps({"projects": {}}))
        assert lint.arm_boundary_findings(root, base_ref="base") == [], "…and allowed when the project leaves too"
        assert lint.arm_boundary_findings(root, base_ref="no-such-ref") == [], "…and nothing without a base"


def case_every_registered_project_declares_an_arm_json() -> None:
    """A project in projects/registry.json with no arm.json is a finding
    naming it: arm.sh would refuse every PR of it."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=git_env())
        g("init", "-q", "-b", "main")
        write(os.path.join(root, "projects", "registry.json"),
              json.dumps({"projects": {"has": {}, "lacks": {}}}))
        write(os.path.join(root, "projects", "has", "integration", "gh", "arm.json"), "{}")
        g("add", "-A")
        got = lint.arm_declared_findings(root)
        assert len(got) == 1 and "'lacks'" in got[0] and "'has'" not in got[0], ("one project lacks one", got)
        write(os.path.join(root, "projects", "lacks", "integration", "gh", "arm.json"), "{}")
        assert any("'lacks'" in f for f in lint.arm_declared_findings(root)), \
            "an untracked arm.json is not declared: lint reads what is tracked"
        g("add", "-A")
        assert lint.arm_declared_findings(root) == [], "every project has one: no finding"
        write(os.path.join(root, "projects", "registry.json"), "{ not json")
        assert lint.arm_declared_findings(root) == [], "an unreadable registry is reported elsewhere"


def case_instance_files_are_read_from_the_operator_tree() -> None:
    """An exported AGENT_FABRIC_OPERATOR outranks the engine tree for a
    project's arm.json and for the committed keys (ADR-045)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    from fabric_lint_rules import docs
    with tempfile.TemporaryDirectory() as root:
        engine, operator = os.path.join(root, "engine"), os.path.join(root, "operator")
        g = lambda *a: subprocess.run(["git", "-C", engine, *a], check=True, capture_output=True, env=git_env())
        good = json.dumps({"boundary": {"paths": "^src/", "exempt": "^docs/", "cases": ["src/a.rs"]}})
        write(os.path.join(engine, "projects", "demo", "integration", "gh", "arm.json"), good)
        g("init", "-q", "-b", "main")
        g("add", "-A")
        write(os.path.join(operator, "projects", "demo", "integration", "gh", "arm.json"), "{}")
        write(os.path.join(operator, "identities", "keys", "lineage.json"), "[]")
        saved = os.environ.get("AGENT_FABRIC_OPERATOR")
        try:
            os.environ.pop("AGENT_FABRIC_OPERATOR", None)
            assert lint.arm_boundary_findings(engine, base_ref="no-such-ref") == [], "the engine's own arm.json is usable"
            os.environ["AGENT_FABRIC_OPERATOR"] = operator
            got = lint.arm_boundary_findings(engine, base_ref="no-such-ref")
            assert any("not a usable arm.json" in f for f in got), ("the operator's arm.json was not the one read", got)
            if shutil.which("gpg"):
                got = docs.key_lineage_findings(engine)
                assert any("lineage.json" in f for f in got), ("the operator's keys were not the ones verified", got)
        finally:
            if saved is None:
                os.environ.pop("AGENT_FABRIC_OPERATOR", None)
            else:
                os.environ["AGENT_FABRIC_OPERATOR"] = saved


def case_bash_over_150_lines_needs_the_allowlist() -> None:
    """ADR-040 §5 rule 2: a tracked bash script over 150 lines is a finding
    unless the allowlist names it; an entry whose script is gone or short
    is stale; an entry the base list does not have is an addition."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=git_env())
        long = "#!/usr/bin/env bash\n" + "echo x\n" * 151
        write(os.path.join(root, "bin", "long-tool"), long)                 # by shebang
        write(os.path.join(root, "runtime", "long.sh"), "echo y\n" * 160)   # by extension
        write(os.path.join(root, "tools", "long.py"), "#!/usr/bin/env python3\n" + "x = 1\n" * 200)
        write(os.path.join(root, "runtime", "short.sh"), "#!/bin/sh\necho z\n")
        write(os.path.join(root, "policies", "bash-allowlist.json"),
              json.dumps({"scripts": {"runtime/long.sh": 1, "runtime/short.sh": 2}}))
        g("init", "-q", "-b", "main")
        g("add", "-A")
        g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
        g("branch", "base")
        got = lint.bash_size_findings(root, base_ref="base")
        assert any(f.startswith("bin/long-tool: 152 lines of bash") for f in got), got
        assert not any(f.startswith("runtime/long.sh:") or f.startswith("tools/long.py") for f in got), \
            "a listed script, and a Python one, pass"
        assert any("runtime/short.sh is gone or 150 lines or fewer" in f for f in got), "a stale entry is a finding"
        write(os.path.join(root, "policies", "bash-allowlist.json"),
              json.dumps({"scripts": {"runtime/long.sh": 1, "bin/long-tool": 3}}))
        got = lint.bash_size_findings(root, base_ref="base")
        assert any("bin/long-tool is added; the list only shrinks" in f for f in got), got
        assert not any(f.startswith("bin/long-tool: 152") for f in got), "listed now, so not unlisted"
        assert lint.bash_size_findings(root, base_ref="no-such-ref") == [], \
            "without a base, additions are not judged and nothing else is wrong"
        # A branch behind its base: the base has since dropped an entry the
        # branch still carries. Not an addition — the branch forked with it.
        g("checkout", "-q", "-b", "behind")
        write(os.path.join(root, "policies", "bash-allowlist.json"),
              json.dumps({"scripts": {"runtime/long.sh": 1}}))
        g("checkout", "-q", "base")
        write(os.path.join(root, "policies", "bash-allowlist.json"), json.dumps({"scripts": {}}))
        g("add", "-A")
        g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base ports runtime/long.sh away")
        g("checkout", "-q", "behind")
        write(os.path.join(root, "policies", "bash-allowlist.json"),
              json.dumps({"scripts": {"runtime/long.sh": 1}}))
        got = lint.bash_size_findings(root, base_ref="base")
        assert not any("is added" in f for f in got), f"an entry the fork point had is not an addition: {got}"


def case_a_dollar_anchored_pattern_is_not_called_with_match() -> None:
    """`$` also matches before one final newline, so `.match` accepts
    "abc\n"; .fullmatch does not. The rule reads each tracked .py file."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=git_env())
        write(os.path.join(root, "tools", "bad.py"),
              "import re\n"
              "A = re.compile(r\"^[a-z]+$\")\n"            # line 2
              "B: re.Pattern = re.compile(r'^x$', re.I)\n"  # line 3
              "def f(s):\n"
              "    if A.match(s) or B.match(s):\n"            # line 5
              "        return re.match(r'^y$', s)\n")         # line 6
        write(os.path.join(root, "tools", "good.py"),
              "import re\n"
              "A = re.compile(r\"^[a-z]+$\")\n"
              "M = re.compile(r\"^[a-z]+$\", re.M)\n"
              "N = re.compile(r\"(?m)^[a-z]+$\")\n"
              "L = re.compile(r\"^[a-z]+\\$\")\n"        # an escaped dollar is a literal
              "Z = re.compile(r\"^[a-z]+\\Z\")\n"
              "P = re.compile(r\"^[a-z]+\")\n"
              "def f(s):\n"
              "    return (A.fullmatch(s), M.match(s), N.match(s), L.match(s), Z.match(s), P.match(s), A.search(s),\n"
              "            re.match(r'^y', s), re.match(r'^y$', s, re.M), re.fullmatch(r'^y$', s))\n")
        write(os.path.join(root, "tools", "notes.txt"), "A.match(s) and re.match(r'^y$', s)\n")
        g("init", "-q", "-b", "main")
        g("add", "-A")
        got = lint.regex_dollar_findings(root)
        assert [f.split(" ")[0] for f in got] == ["tools/bad.py:5:", "tools/bad.py:5:", "tools/bad.py:6:"], got
        assert any("A.match" in f and "line 2" in f for f in got) and any("B.match" in f and "line 3" in f for f in got), got
        assert all("fullmatch" in f for f in got), got


def case_a_dollar_anchored_pattern_in_every_shape_and_scope() -> None:
    """Review of #140: an f-string pattern, an inline re.compile(...).match,
    a class attribute through self., cls. and the class's name, and a
    function's own pattern are findings; a parameter or another local that
    shares a pattern's name elsewhere is not."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=git_env())
        write(os.path.join(root, "tools", "shapes.py"),
              "import re\n"
              "K = 'x'\n"
              "F = re.compile(rf\"^{K}:(.*)$\")\n"                 # line 3
              "class C:\n"
              "    PAT = re.compile(r\"^y$\")\n"                    # line 5
              "    def m(self, s):\n"
              "        return self.PAT.match(s)\n"                    # line 7
              "    @classmethod\n"
              "    def n(cls, s):\n"
              "        return cls.PAT.match(s) or C.PAT.match(s)\n"  # line 10
              "def f(s):\n"
              "    pat = re.compile(r\"^z$\")\n"
              "    return (F.match(s), re.compile(r\"^w$\").match(s), pat.match(s),\n"  # line 13
              "            re.match(rf\"^{K}:(.*)$\", s))\n")    # line 14
        write(os.path.join(root, "tools", "scopes.py"),
              "import re\n"
              "pat = re.compile(r\"^a$\")\n"
              "def g(pat, s):\n"
              "    return pat.match(s)\n"                  # a parameter, not the module's pattern
              "def h(s):\n"
              "    pat = re.compile(r\"^a\\Z\")\n"
              "    return pat.match(s)\n"                  # a local that is not a $-pattern
              "def k(s):\n"
              "    q = re.compile(r\"^a$\")\n"
              "    return q.fullmatch(s), re.compile(rf\"^{s}$\", re.M).match(s)\n")
        g("init", "-q", "-b", "main")
        g("add", "-A")
        got = lint.regex_dollar_findings(root)
        lines = [f.split(" ")[0] for f in got]
        want = ["tools/shapes.py:7:", "tools/shapes.py:10:", "tools/shapes.py:10:", "tools/shapes.py:13:", "tools/shapes.py:13:",
                "tools/shapes.py:13:", "tools/shapes.py:14:"]
        assert sorted(lines) == sorted(want), got
        assert not any(f.startswith("tools/scopes.py") for f in got), got


def case_a_dollar_anchored_pattern_in_nested_scopes() -> None:
    """Re-review of #140: a closure's pattern is a finding; an enclosing
    function's parameter hides the module's pattern in a nested one; a
    nested function's binding is not its enclosing function's; a class's
    pattern is its own, not another class's; a class body's names are not
    the module's."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=git_env())
        write(os.path.join(root, "tools", "nested.py"),
              "import re\n"
              "M = re.compile(r\"^m$\")\n"
              "def outer(s):\n"
              "    P = re.compile(r\"^p$\")\n"
              "    def inner(t):\n"
              "        return P.match(t)\n"            # line 6: a closure, a finding
              "    return inner(s)\n"
              "def shadow(M):\n"
              "    def inner(t):\n"
              "        return M.match(t)\n"            # line 10: the outer parameter, not the module's M
              "    return inner\n"
              "def leak(s):\n"
              "    def inner(t):\n"
              "        Q = re.compile(r\"^q$\")\n"
              "        return Q.fullmatch(t)\n"
              "    Q = re.compile(r\"^q\\Z\")\n"
              "    return Q.match(s)\n"                # line 17: leak's own Q is no $-pattern
              "class A:\n"
              "    PAT = re.compile(r\"^a$\")\n"
              "class B:\n"
              "    PAT = re.compile(r\"^b\\Z\")\n"
              "    def m(self, s):\n"
              "        return self.PAT.match(s)\n"     # line 23: B's PAT, not A's
              "class D:\n"
              "    N = re.compile(r\"^n$\")\n"
              "def use(s, N):\n"
              "    return N.match(s)\n")             # line 27: a parameter; D.N is no module name
        g("init", "-q", "-b", "main")
        g("add", "-A")
        got = lint.regex_dollar_findings(root)
        assert [f.split(" ")[0] for f in got] == ["tools/nested.py:6:"], got


def case_a_dollar_anchored_pattern_through_classes_and_rebinding() -> None:
    """Review of #143: a pattern a class inherits from a base class of the
    module is followed (self. and the subclass's name); a class body's
    names, an if inside it included, are the class's and never the
    module's; a pattern bound in an if of a class body is recorded. A name
    with any $-pattern binding in its scope is reported whatever else binds
    it (over-reporting by design: fullmatch is never wrong)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=git_env())
        write(os.path.join(root, "tools", "classes.py"),
              "import re\n"
              "class A:\n"
              "    PAT = re.compile(r\"^a$\")\n"
              "class B(A):\n"
              "    def m(self, s):\n"
              "        return self.PAT.match(s)\n"     # line 6: inherited, a finding
              "x = B.PAT.match('a')\n"                 # line 7: inherited through the subclass's name
              "class D:\n"
              "    N = re.compile(r\"^n$\")\n"
              "    if True:\n"
              "        R = re.compile(r\"^r$\")\n"
              "    def m(self, s):\n"
              "        return self.R.match(s)\n"       # line 13: a pattern in the class body's if
              "y = N.match('n')\n"                     # line 14: D.N is not a module name
              "z = R.match('r')\n"                     # line 15: nor is D.R
              "S = re.compile(r\"^s$\")\n"
              "S = re.compile(r\"^s\\Z\")\n"
              "w = S.match('s')\n")                    # line 18: S has a $ binding; reported
        g("init", "-q", "-b", "main")
        g("add", "-A")
        got = lint.regex_dollar_findings(root)
        assert [f.split(" ")[0] for f in got] == ["tools/classes.py:6:", "tools/classes.py:7:", "tools/classes.py:13:",
                                                  "tools/classes.py:18:"], got


def case_a_dollar_anchored_pattern_follows_source_order() -> None:
    """Re-reviews of #143: scoping, not statement order, decides. A
    subclass that binds a name decides it (its non-$ binding ends what it
    inherits); a name with a $ binding anywhere in its scope is reported at
    every call (before and after a rebinding, in a function and at module
    level); a module-level alias of a pattern is followed."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=git_env())
        write(os.path.join(root, "tools", "order.py"),
              "import re\n"
              "class A:\n"
              "    PTN = re.compile(r\"^a$\")\n"
              "class B(A):\n"
              "    PTN = re.compile(r\"^a\\Z\")\n"
              "    def m(self, s):\n"
              "        return self.PTN.match(s)\n"     # line 7: B binds PTN without $; no finding
              "v = B.PTN.match('a')\n"                 # line 8: no finding
              "class C:\n"
              "    W = None\n"
              "    W = re.compile(r\"^w$\")\n"
              "    def m(self, s):\n"
              "        return self.W.match(s)\n"       # line 13: reported
              "S = re.compile(r\"^s$\")\n"
              "u = S.match('s')\n"                     # line 15: reported
              "A = S\n"
              "x = A.match('s')\n"                     # line 17: an alias, reported
              "S = None\n"
              "def f(t):\n"
              "    P = re.compile(r\"^p$\")\n"
              "    m = P.match(t)\n"                   # line 21: before the rebinding, reported
              "    P = None\n"
              "    return m\n")
        g("init", "-q", "-b", "main")
        g("add", "-A")
        got = lint.regex_dollar_findings(root)
        assert [f.split(" ")[0] for f in got] == ["tools/order.py:13:", "tools/order.py:15:", "tools/order.py:17:",
                                                  "tools/order.py:21:"], got


def case_a_dollar_anchored_pattern_is_followed_across_imports() -> None:
    """The pattern is bound in one file and called with .match in another:
    through `from m import NAME`, `import m` then `m.NAME`, a re-export, a
    relative import in a package. Imports that lead nowhere are skipped."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=git_env())
        t = lambda *p: os.path.join(root, "tools", *p)
        write(t("defs.py"), "import re\nIDENT = re.compile(r'^[a-z]+$')\nSAFE = re.compile(r'^[a-z]+\\Z')\n")
        write(t("hop.py"), "from defs import IDENT, SAFE\n")
        write(t("bad_from.py"), "from defs import IDENT\ndef f(s):\n    return IDENT.match(s)\n")        # line 3
        write(t("bad_attr.py"), "import sys, os\nsys.path.insert(0, os.path.dirname(__file__))\nimport defs\n"
                                "def f(s):\n    return defs.IDENT.match(s)\n")                              # line 5
        write(t("bad_hop.py"), "from hop import IDENT as I\ndef f(s):\n    return I.match(s)\n")          # line 3
        write(t("bad_alias.py"), "import defs\nX = defs.IDENT\ndef f(s):\n    return X.match(s)\n")      # line 4
        write(t("pkg", "__init__.py"), "")
        write(t("pkg", "pat.py"), "import re\nP = re.compile(r'^x$')\n")
        write(t("pkg", "core.py"), "from .pat import P\n")
        write(t("pkg", "use.py"), "from .core import P\nfrom . import pat as _pat\n"
                                  "def f(s):\n    return P.match(s), _pat.P.match(s)\n")                   # line 4, twice
        write(t("good.py"), "import defs, nowhere, os\nfrom defs import SAFE\nfrom hop import SAFE as S2\n"
                            "from missing import IDENT\nfrom os import path\nfrom . import nothing\n"
                            "def f(s):\n    return (SAFE.match(s), S2.match(s), defs.SAFE.match(s), IDENT.match(s),\n"
                            "            defs.IDENT.fullmatch(s), nowhere.X.match(s), os.path.match(s), path.match(s))\n")
        g("init", "-q", "-b", "main")
        g("add", "-A")
        got = lint.regex_dollar_findings(root)
        assert [f.split(" ")[0] for f in got] == [
            "tools/bad_alias.py:4:", "tools/bad_attr.py:5:", "tools/bad_from.py:3:", "tools/bad_hop.py:3:",
            "tools/pkg/use.py:4:", "tools/pkg/use.py:4:"], got
        assert any("IDENT" in f and "tools/defs.py:2" in f for f in got), got
        assert sum("tools/pkg/pat.py:2" in f for f in got) == 2, got


def case_a_contributor_entry_never_reaches_a_definition() -> None:
    """ADR-018 §5 rule 8: a contributor's entry names a catalogued role, is
    whole, and admits nothing that defines a role — however broad its
    rules are spelled."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        write(os.path.join(root, "identities", "roles", "catalog.json"),
              json.dumps({"roles": [{"id": "fabric-coordinator"}, {"id": "python-dev"}]}))

        def findings(*entries: dict) -> list[str]:
            write(os.path.join(root, "policies", "authority.json"),
                  json.dumps({"role_definitions": {"role": "fabric-coordinator"}, "contributors": list(entries)}))
            return lint.contributor_findings(root)

        excl = [n for n in lint.CONTRIBUTOR_NEVER if n.startswith(("tools/", "tests/"))]
        good = {"role": "python-dev", "paths": ["tools/", "tests/", "policies/bash-allowlist.json"], "excluding": excl}
        assert findings(good) == [], findings(good)
        assert findings() == [], "no contributor, nothing to say"
        assert findings({**good, "merges": True}) == [], "a boolean merges is whole"
        got = findings({**good, "merges": "yes"})
        assert any("contributors[0]: not a whole entry" in f for f in got), got
        # A malformed entry beside a whole one of the same role is still
        # judged (review of the merges branch, F4), and a second entry is one.
        got = findings({**good, "merges": True}, {**good, "merges": "yes"})
        assert any("contributors[1] (python-dev): a second entry" in f for f in got), got
        # The order `alone` exists for: the malformed entry first, a whole one
        # after it, where the role's whole entry would have hidden it.
        got = findings({**good, "merges": "yes"}, {**good, "merges": True})
        assert any("contributors[0]: not a whole entry" in f for f in got), got
        got = findings({**good, "excluding": [e for e in excl if e != "tools/fabric/guards/"]})
        assert any("rule 'tools/' reaches tools/fabric/guards/" in f for f in got), got
        # The rule modules lint.py loads are the coordinator's as lint.py is:
        # a contributor entry that reaches them without excluding them is refused.
        got = findings({**good, "excluding": [e for e in excl if e != "tools/fabric/lint_rules/"]})
        assert any("rule 'tools/' reaches tools/fabric/lint_rules/" in f for f in got), got
        assert "tools/fabric/lint_rules/" in lint.CONTRIBUTOR_NEVER
        for loaded in ("tools/fabric/layout.py", "tools/fabric/workingcopy.py", "tools/fabric/adr.py",
                       "tools/fabric/secretstore/lineage.py"):
            assert loaded in lint.CONTRIBUTOR_NEVER, f"{loaded} is loaded by lint by path: it is fenced like lint.py"
        got = findings({**good, "paths": good["paths"] + ["policies/"]})
        assert any("rule 'policies/' reaches policies/" in f for f in got), got
        # Review of #75: rules narrower than any sample file, each one a
        # definition or a guard.
        for narrow in ("identities/roles/python-dev/", "identities/roles/python-dev/charter.md",
                       "policies/githooks/commit-msg", "tools/fabric/guards/common.py",
                       "tools/fabric/lint_rules/", "tools/fabric/lint_rules/docs.py",
                       "identities/roles/catalog.json", "routing/effort.json",
                       # Re-review of #75: what registers the hooks, the
                       # workspace prompt, the helper the runner sources.
                       "runtime/claude-code/workspace/settings.json", "runtime/claude-code/workspace/CLAUDE.md",
                       "runtime/claude-code/", "tests/leak-check.sh", "tools/fabric/review_brief.py",
                       "bin/fabric-review"):
            got = findings({**good, "paths": [narrow]})
            assert any(f"rule {narrow!r} reaches" in f for f in got), (narrow, got)
        got = findings({**good, "excluding": excl + ["tools/fabric/guards/x.py"],
                        "paths": ["tools/"]})
        assert not any("reaches tools/fabric/guards/" in f for f in got), "an exclusion covering the prefix suffices"
        got = findings({**good, "excluding": [e for e in excl if e != "tools/fabric/guards/"] + ["tools/fabric/guards/x.py"]})
        assert any("reaches tools/fabric/guards/" in f for f in got), "an exclusion of one file under it does not"
        got = findings({**good, "paths": [""]})
        assert any("not a whole entry" in f for f in got), got
        got = findings({**good, "role": ["python-dev"]})
        assert any("not a whole entry" in f for f in got), got
        got = findings({**good, "role": "web-dev"})
        assert any("not in identities/roles/catalog.json" in f for f in got), got
        got = findings({**good, "role": "fabric-coordinator"})
        assert any("the owner role needs no entry" in f for f in got), got
        write(os.path.join(root, "identities", "roles", "catalog.json"), "{")
        got = findings(good)
        assert any("catalog.json: unreadable" in f for f in got), got
        write(os.path.join(root, "policies", "authority.json"), json.dumps({"contributors": {"role": "x"}}))
        assert lint.contributor_findings(root) == ["policies/authority.json: `contributors` is not a list"]


def case_the_fallback_validator_agrees_with_jsonschema() -> None:
    """On the pinned interpreter (standard library only) the structural
    fallback is the validator: each keyword it claims gives jsonschema's
    verdict on a planted pass and a planted fail, and a schema using a
    keyword it does not check is refused by name."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    cases = [
        ({"type": "object", "propertyNames": {"pattern": "^[a-z]+$"}}, {"ok": 1}, {"Bad": 1}),
        ({"type": "object", "minProperties": 1}, {"a": 1}, {}),
        ({"const": "x"}, "x", "y"),
        ({"oneOf": [{"type": "string"}, {"type": "integer"}]}, "s", 1.5),
        ({"type": "object", "patternProperties": {"^n_": {"type": "integer"}}}, {"n_a": 1}, {"n_a": "s"}),
        ({"type": "array", "minItems": 1, "maxItems": 2}, [1], []),
        ({"type": "array", "maxItems": 1}, [1], [1, 2]),
        ({"type": "string", "minLength": 2, "maxLength": 3}, "abc", "a"),
        ({"type": "string", "maxLength": 2}, "ab", "abc"),
        ({"type": "integer", "minimum": 1, "maximum": 3}, 2, 0),
        ({"type": "integer", "maximum": 3}, 3, 4),
        ({"if": {"properties": {"k": {"const": "a"}}}, "then": {"required": ["x"]}, "else": {"required": ["y"]}},
         {"k": "a", "x": 1}, {"k": "a", "y": 1}),
        ({"if": {"properties": {"k": {"const": "a"}}}, "then": {"required": ["x"]}, "else": {"required": ["y"]}},
         {"k": "b", "y": 1}, {"k": "b", "x": 1}),
        # Review of #77: Python's True == 1 is not JSON's, and both kinds of
        # property schema apply to one key.
        ({"const": 1}, 1, True),
        ({"const": False}, False, 0),
        ({"enum": [1, 2]}, 2, True),
        ({"type": "integer"}, 1.0, True),
        ({"type": "number"}, 0.5, False),
        ({"properties": {"a": {"type": "string"}}, "patternProperties": {"^a": {"minLength": 3}}}, {"a": "xyz"}, {"a": "x"}),
        # Re-review of #77: 1 and 1.0 are one value to JSON; true and 1 are two.
        ({"uniqueItems": True}, [1, True], [1, 1.0]),
    ]
    try:
        import jsonschema  # type: ignore
    except ImportError:
        jsonschema = None
    for schema, good, bad in cases:
        assert lint._structural_check(schema, good, "w") == [], (schema, good)
        assert lint._structural_check(schema, bad, "w") != [], (schema, bad)
        if jsonschema is not None:
            v = jsonschema.Draft202012Validator(schema)
            assert v.is_valid(good) and not v.is_valid(bad), ("jsonschema disagrees with the case", schema)
    assert set(k for schema, _, _ in cases for k in schema) <= lint.SCHEMA_KEYWORDS
    with tempfile.TemporaryDirectory() as root:
        g = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=git_env())
        write(os.path.join(root, "x.schema.json"),
              json.dumps({"type": "object", "properties": {"n": {"type": "integer", "multipleOf": 2}}}))
        g("init", "-q")
        g("add", "-A")
        got = lint.schema_keyword_findings(root)
        assert any("'multipleOf' is not checked without jsonschema" in f for f in got), got
        assert not any("'type'" in f or "'n'" in f for f in got), ("a property name is not a keyword", got)


def case_the_python_pin_is_checkable_and_what_ci_runs() -> None:
    """runtime/python.json names a version, https URLs that name it, 64-hex
    hashes; CI's matrix carries its minor version."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    good = {"python": "3.13.15", "release": "r", "builds": {"x86_64": {"url": "https://h/cpython-3.13.15%2Br-x.tgz", "sha256": "a" * 64}}}
    with tempfile.TemporaryDirectory() as root:
        write(os.path.join(root, ".github", "workflows", "ci.yml"), "          - { section: python, python: '3.13', node: '22' }\n")
        def got(doc):
            write(os.path.join(root, "runtime", "python.json"), json.dumps(doc))
            return lint.python_pin_findings(root)
        assert got(good) == [], got(good)
        assert any("must be https" in f for f in got({**good, "builds": {"x86_64": {**good["builds"]["x86_64"], "url": "http://h/3.13.15"}}}))
        assert any("64 hex" in f for f in got({**good, "builds": {"x86_64": {**good["builds"]["x86_64"], "sha256": "xyz"}}}))
        assert any("does not name Python" in f for f in got({**good, "python": "3.13.16"}))
        assert any("does not name Python" in f for f in got({**good, "python": "3.13.1"})), "3.13.1 is not 3.13.15's prefix match"
        os.remove(os.path.join(root, "runtime", "python.json"))
        write(os.path.join(root, "tools", "fabric", "python_pin.py"), "")
        assert any("runtime/python.json: missing" in f for f in lint.python_pin_findings(root))
        assert any("not a 3.x.y" in f for f in got({**good, "python": "3.13"}))
        assert any("no matrix leg on Python 3.14" in f for f in got({**good, "python": "3.14.0",
                   "builds": {"x86_64": {"url": "https://h/cpython-3.14.0+r", "sha256": "a" * 64}}}))


def case_the_fabrics_own_claude_settings_are_the_workspace_template() -> None:
    """agent-fabric's .claude/settings.json is the workspace template with
    the root at $CLAUDE_PROJECT_DIR: a hand edit or a template change not
    re-rendered is a finding."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        write(os.path.join(root, "runtime", "claude-code", "workspace", "settings.json"),
              json.dumps({"_comment": "c", "statusLine": {"type": "command", "command": "bash \"$AGENT_FABRIC_ROOT/s.sh\""}}))
        assert any("not runtime/claude-code/workspace/settings.json rendered" in f for f in lint.fabric_settings_findings(root))
        spec2 = importlib.util.spec_from_file_location("fs_under_test", os.path.join(os.path.dirname(LINT), "fabric_settings.py"))
        fs = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(fs)
        rendered = fs.render(root)
        assert '"$CLAUDE_PROJECT_DIR/s.sh' in rendered and "_comment" not in rendered, rendered
        write(os.path.join(root, ".claude", "settings.json"), rendered)
        assert lint.fabric_settings_findings(root) == []
        write(os.path.join(root, ".claude", "settings.json"), rendered.replace("s.sh", "other.sh"))
        assert lint.fabric_settings_findings(root), "a hand edit is a finding"


def case_project_tools_are_declared_and_never_retired() -> None:
    """projects/registry.json `tools` (bin/fabric-tools): each entry well formed,
    and a fabric cleanup (runtime/claude-code/retire-*.py RETIRED) never names a
    declared tool — the Doppler CLI was once taken from every account so."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        write(os.path.join(root, "identities", "roles", "catalog.json"), json.dumps({"roles": [{"id": "flutter-dev"}]}))
        good = {"name": "doppler", "proof": "doppler --version", "why": "w", "where": "host", "optional": True}

        def findings(tools, retired=None, spelling="RETIRED = {!r}\n"):
            write(os.path.join(root, "projects", "registry.json"),
                  json.dumps({"projects": {"p": {"tools": tools}}}))
            script = os.path.join(root, "runtime", "claude-code", "retire-x.py")
            if retired is None:
                if os.path.exists(script):
                    os.remove(script)
            else:
                write(script, spelling.format(retired))
            return lint.project_tools_findings(root)
        assert findings([good]) == [], findings([good])
        assert findings([{**good, "roles": ["flutter-dev"]}]) == []
        got = findings([{"name": "x", "proof": "x '", "where": "moon", "roles": ["nobody"], "optional": "yes"}])
        for needle in ("why missing", "where is 'moon'", "roles must be", "optional is not", "not a command line"):
            assert any(needle in f for f in got), (needle, got)
        assert findings([good], (".config/agent-fabric/secrets-source",)) == []
        got = findings([good], (".doppler", ".local/bin/doppler"))
        assert len(got) == 2 and all("a tool a project declares" in f for f in got), got
        got = findings([good], (".doppler",), "RETIRED: tuple[str, ...] = {!r}\n")
        assert len(got) == 1 and "a tool a project declares" in got[0], ("an annotated RETIRED is checked too", got)
        got = findings([good], ".doppler", "BASE = ({!r},)\nRETIRED = BASE + ()\n")
        assert len(got) == 1 and "not a literal" in got[0], ("a computed RETIRED is refused, never skipped", got)
        got = findings([good], ".doppler", "RETIRED = ()\nRETIRED += ({!r},)\n")
        assert any("not a literal" in f for f in got), ("an augmented RETIRED is refused, never skipped", got)


def case_locales_carry_the_same_files() -> None:
    """Every locale of a role carries what any other has; the dictionary
    is matched by role, each named by its own tag (the owner, 2026-10-07)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    with tempfile.TemporaryDirectory() as root:
        role = os.path.join(root, "role")
        for suffix, tag in (("ru", "ru-RU"), ("ge", "ka-GE")):
            write(os.path.join(role, "locale", suffix, "locale.json"), json.dumps({"tag": tag}))
            write(os.path.join(role, "locale", suffix, "team.md"), "x")
        write(os.path.join(role, "locale", "ru", "ru-RU.json"), "{}")
        write(os.path.join(role, "locale", "ru", "brief.md"), "x")
        got = lint.locale_alignment_findings("demo", role)
        assert len(got) == 2 and all("/ge/" in g for g in got), got
        assert any("dictionary" in g and "ru has" in g for g in got), got
        assert any("brief.md" in g for g in got), got
        write(os.path.join(role, "locale", "ge", "ka-GE.json"), "{}")
        write(os.path.join(role, "locale", "ge", "brief.md"), "x")
        assert lint.locale_alignment_findings("demo", role) == [], "aligned: clean"
        write(os.path.join(role, "locale", "ge", "worker.md"), "x")
        got = lint.locale_alignment_findings("demo", role)
        assert got and "/ru/" in got[0] and "worker.md" in got[0], "either direction"



def case_the_source_locale_translates_nothing() -> None:
    """An en-US locale is the fleet's source: it carries locale.json alone,
    asks no translation of the others, and its English text is in its
    locale (the owner, 2026-10-07: language-culture-en)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_lint_under_test", LINT)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    english = {"tag": "en-US", "timezone": "Asia/Tbilisi",
               "brave": {"country": "ALL", "label": "second index", "tool_description": "Global web search."}}
    with tempfile.TemporaryDirectory() as root:
        role = os.path.join(root, "role")
        write(os.path.join(role, "locale", "ru", "locale.json"), json.dumps({"tag": "ru-RU"}))
        write(os.path.join(role, "locale", "ru", "team.md"), "x")
        write(os.path.join(role, "locale", "en", "locale.json"), json.dumps(english))
        assert lint.locale_alignment_findings("demo", role) == [], "en asks nothing, and is asked nothing"
        write(os.path.join(role, "locale", "en", "team.md"), "x")
        got = lint.locale_alignment_findings("demo", role)
        assert len(got) == 1 and "/en/" in got[0] and "translates nothing" in got[0], got
        os.remove(os.path.join(role, "locale", "en", "team.md"))
        assert lint.locale_file_findings("demo", role) == [] or not any(
            "/en/" in f for f in lint.locale_file_findings("demo", role)), lint.locale_file_findings("demo", role)
        # The same English text in a translated locale is not in that locale.
        write(os.path.join(role, "locale", "ru", "locale.json"), json.dumps({**english, "tag": "ru-RU"}))
        got = lint.locale_file_findings("demo", role)
        assert any("/ru/" in f and "not in the locale" in f for f in got), got
        write(os.path.join(role, "locale", "en", "locale.json"), json.dumps({**english, "reminder": "Think in English"}))
        assert any("/en/" in f and "reminder in the source locale" in f
                   for f in lint.locale_file_findings("demo", role))


def main() -> int:
    cases = [
        case_clean_base_passes,
        case_locales_carry_the_same_files,
        case_project_tools_are_declared_and_never_retired,
        case_the_source_locale_translates_nothing,
        case_decision_records_are_lint_findings,
        case_bash_over_150_lines_needs_the_allowlist,
        case_arm_boundary_cases_only_leave_retired,
        case_every_registered_project_declares_an_arm_json,
        case_a_cited_fabric_document_must_resolve,
        case_a_committed_agent_key_needs_its_lineage,
        case_a_committed_agent_source_may_not_pin_effort,
        case_index_description_drift_is_caught,
        case_a_sibling_working_copy_is_linted_unasked,
        case_index_lists_domain_slices,
        case_fabric_ref_is_one_full_commit_id,
        case_quoted_description_round_trips,
        case_the_callers_operator_is_not_part_of_a_fixture,
        case_instance_files_are_read_from_the_operator_tree,
        case_payload_is_exempt,
        case_hygiene_still_runs_over_payload,
        case_secrets_are_refused_by_shape,
        case_a_projects_own_name_is_held_to_its_own_set,
        case_a_persons_name_is_refused_everywhere,
        case_slices_are_still_linted,
        case_a_cue_in_another_script_is_refused,
        case_exemption_is_anchored_at_the_role_root,
        case_payload_shape_is_asserted,
        case_index_need_not_list_payload,
        case_authored_classes_only_in_identities,
        case_brief_is_identity_too,
        case_prompt_templates_are_linted,
        case_knowledge_not_in_identities,
        case_taxonomy_roles_are_catalogued,
        case_domain_bound_by_an_unseen_project_is_not_judged,
        case_locale_translation_is_a_charter_with_a_digest,
        case_translation_lag_is_reported,
        case_locale_brief_translates_like_the_charter,
        case_locale_worker_shape_and_hygiene,
        case_protected_tokens_must_match,
        case_each_translation_names_its_source_and_lags_when_it_moves,
        case_harness_translation_shape_digest_and_tokens,
        case_harness_source_shape,
        case_prompt_templates_carry_their_placeholders,
        case_locale_file_shape,
        case_i18n_dictionary_is_complete_and_keeps_its_identifiers,
        case_non_latin_translation_budget_is_stricter,
        case_model_profiles_layered_file_passes,
        case_model_profiles_cheap_review_is_refused,
        case_model_profiles_agents_are_logins,
        case_model_profiles_unknown_role_is_refused,
        case_model_profiles_schema_is_enforced,
        case_the_repository_is_one_license,
        case_every_project_names_a_defined_client,
        case_a_registry_with_projects_and_no_clients_is_a_finding,
        case_the_class_list_a_reader_sees_is_the_real_one,
        case_a_skill_carries_rules_not_occasions,
        case_the_host_registry_is_one_host_per_id_and_placements_are_known,
        case_the_agentd_selector_is_sound_and_names_placed_logins,
        case_a_bound_and_held_role_is_not_a_candidate,
        case_a_managed_projects_name_stays_out_of_generic_files,
        case_review_lenses_are_named_described_and_bounded,
        case_a_dollar_anchored_pattern_is_not_called_with_match,
        case_a_dollar_anchored_pattern_is_followed_across_imports,
        case_a_dollar_anchored_pattern_in_every_shape_and_scope,
        case_a_dollar_anchored_pattern_in_nested_scopes,
        case_a_dollar_anchored_pattern_through_classes_and_rebinding,
        case_a_dollar_anchored_pattern_follows_source_order,
        case_a_contributor_entry_never_reaches_a_definition,
        case_the_fallback_validator_agrees_with_jsonschema,
        case_the_python_pin_is_checkable_and_what_ci_runs,
        case_the_fabrics_own_claude_settings_are_the_workspace_template,
    ]
    failures = 0
    for case in cases:
        try:
            case()
            print(f"  ok   {case.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
