#!/usr/bin/env python3
"""tests/test_launch_prompt.py — the launch prompt is built from the
binding, byte-stable, and never names the project.

Runs tools/fabric/launch_prompt.py against a throwaway agent-fabric root
and a throwaway state directory, as tests/test_role.py does: the real
modules copied in, a fixture charter and brief, the real prompt sections.
"""
from __future__ import annotations

import hashlib
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile

import socket
HOST = socket.gethostname().split('.')[0]
ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
import pwd
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
LOGIN = pwd.getpwuid(os.geteuid()).pw_name   # the agent is the login, never $USER (unset in a container)


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class Fixture:
    def __init__(self, tmp: str, role: str = "backend-dev", brief: bool = True):
        self.root = os.path.join(tmp, "fabric")
        self.state = os.path.join(tmp, "state")
        for rel in ("tools/fabric/layout.py", "tools/fabric/workingcopy.py", "tools/fabric/roots.py",
                    "tools/fabric/launch_prompt.py", "runtime/identity.py"):
            os.makedirs(os.path.dirname(os.path.join(self.root, rel)), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, rel), os.path.join(self.root, rel))
        shutil.copytree(os.path.join(ROOT, "identities", "prompt"),
                        os.path.join(self.root, "identities", "prompt"),
                        ignore=shutil.ignore_patterns("locale"))   # the real translations: each case writes the ones it needs
        write(os.path.join(self.root, "identities", "roles", role, "charter.md"),
              f"---\nrole: {role}\nclass: charter\ndescription: \"x\"\ntier: 1\ndistilled_at: 2026-09-15\n---\n\n"
              f"# {role} — charter\n\nCHARTER-BODY-LINE for {role}.\n")
        if brief:
            write(os.path.join(self.root, "identities", "roles", role, "brief.md"),
                  f"---\nrole: {role}\nclass: brief\ndescription: \"y\"\ntier: 1\ndistilled_at: 2026-09-15\n---\n\n"
                  f"# {role} — brief\n\nBRIEF-BODY-LINE for {role}.\n")
        self.bind(role)
        self.env = {**os.environ, "AGENT_FABRIC_ROOT": self.root, "AGENT_FABRIC_STATE_DIR": self.state}

    def bind(self, role: str | None) -> None:
        # The binding a fabric-role bind would have written: keyed by the
        # login (identity.read_binding refuses another agent's record).
        d = os.path.join(self.state, "agents", LOGIN)
        os.makedirs(d, exist_ok=True)
        rec = {"agent": LOGIN, "host": HOST, "updated_at": "2026-09-15T00:00:00Z"}
        if role:
            rec["role"] = role
        write(os.path.join(d, "binding.json"), json.dumps(rec))

    def run(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, os.path.join(self.root, "tools", "fabric", "launch_prompt.py"), *argv],
                              env=self.env, capture_output=True, text=True)


def case_header_names_agent_host_role() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        r = f.run("--print")
        assert r.returncode == 0, r.stderr
        assert f"agent `{LOGIN}`" in r.stdout and "**backend-dev**" in r.stdout, r.stdout
        assert "`fabric-whoami`" in r.stdout and "bin/fabric-whoami" not in r.stdout and "relaunch" in r.stdout


def case_charter_and_brief_bodies_without_frontmatter() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        out = f.run("--print").stdout
        assert "CHARTER-BODY-LINE for backend-dev" in out and "BRIEF-BODY-LINE for backend-dev" in out
        assert "class: charter" not in out and "distilled_at" not in out, "frontmatter leaked into the prompt"
        assert out.index("— charter") < out.index("— brief") < out.index("Working with the team") \
            < out.index("Your long-term memory"), "sections out of order"


def case_shared_sections_are_rendered_for_the_role() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        out = f.run("--print").stdout
        assert "{role}" not in out, "an unsubstituted placeholder reached the prompt"
        assert "memory/domains/backend-dev/" in out and ".agent-fabric/roles/backend-dev.md" in out
        assert "REPLY-EXPECTED: yes" in out and "roles_class" in out


def case_missing_brief_is_a_placeholder_not_a_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp, brief=False)
        r = f.run("--print")
        assert r.returncode == 0, r.stderr
        assert "No brief has been distilled" in r.stdout and "backend-dev — brief" in r.stdout


def case_missing_charter_is_a_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        os.remove(os.path.join(f.root, "identities", "roles", "backend-dev", "charter.md"))
        r = f.run("--print")
        assert r.returncode == 1 and "no charter" in r.stderr, r.stderr


def case_no_binding_is_a_failure_naming_fabric_role() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        f.bind(None)
        r = f.run("--print")
        assert r.returncode == 1 and "(fabric-role bind" in r.stderr and "bin/fabric-role" not in r.stderr, r.stderr


def case_out_writes_the_file_and_prints_its_digest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        out = os.path.join(tmp, "state", "agents", LOGIN, "launch-prompt.md")
        r = f.run("--out", out)
        assert r.returncode == 0, r.stderr
        printed = r.stdout.strip()
        assert printed.startswith("sha256:"), r.stdout
        with open(out, "rb") as fh:
            assert printed == "sha256:" + hashlib.sha256(fh.read()).hexdigest(), "digest is not of the file's bytes"
        assert not [n for n in os.listdir(os.path.dirname(out)) if n.startswith(".tmp-")], \
            "a temporary file was left beside the prompt"


def case_byte_stable_across_builds_and_cwds() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        a = f.run("--print").stdout
        elsewhere = os.path.join(tmp, "elsewhere")
        os.makedirs(elsewhere)
        b = subprocess.run([sys.executable, os.path.join(f.root, "tools", "fabric", "launch_prompt.py"), "--print"],
                           env=f.env, capture_output=True, text=True, cwd=elsewhere).stdout
        assert a == b, "the prompt depends on something other than (agent, host, role)"
        assert tmp not in a, "a fixture path (a cwd or working copy) reached the prompt"


def case_nothing_about_who_can_be_passed_in() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        r = f.run("--print", "--role", "db-admin")
        assert r.returncode == 2, "an identity argument was accepted"


def case_oversized_prompt_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        write(os.path.join(f.root, "identities", "roles", "backend-dev", "brief.md"),
              "---\nrole: backend-dev\nclass: brief\n---\n\n# backend-dev — brief\n\n" + ("padding line\n" * 2000))
        r = f.run("--print")
        assert r.returncode == 1 and "exceeds" in r.stderr, r.stderr


def _locale_holder(role: str, locale: str | None) -> dict | None:
    """The holder dict the launcher hands over for a holder.json naming only
    a locale; None (no holder.json) when no locale is given."""
    return None if locale is None else {"role": role, "charter": None, "brief": None, "holder": {"locale": locale}}


def _build_launch_direct(f: "Fixture", agent: str, role: str, cwd: str, locale: str | None = None) -> tuple[str, bool]:
    """build_launch() with an explicit agent and cwd, inside the fixture."""
    code = ("import importlib.util, os, sys, json; "
            "spec = importlib.util.spec_from_file_location('lp', sys.argv[1]); m = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(m); t, r = m.build_launch(sys.argv[2], 'h', sys.argv[3], sys.argv[4], json.loads(sys.argv[5])); "
            "sys.stdout.write(json.dumps([t, r]))")
    r = subprocess.run([sys.executable, "-c", code, os.path.join(f.root, "tools", "fabric", "launch_prompt.py"), agent, role, cwd,
                        json.dumps(_locale_holder(role, locale))], env=f.env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text, replace = json.loads(r.stdout)
    return text, replace


def case_every_piece_comes_from_the_locale_when_it_carries_one() -> None:
    """locale/<suffix>/{header,brief-missing,team,memory}.md replace their
    English for the login of that suffix, placeholders filled; another
    suffix and a login without locale files render the English bytes.
    Kills: a locale rule that knows only the charter."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp, role="language-culture", brief=False)
        loc = os.path.join(f.root, "identities", "roles", "language-culture", "locale", "ge")
        fm = lambda src: f"---\nclass: prompt-translation\ntranslates: identities/prompt/{src}.md\ntranslates_digest: sha256:x\n---\n"
        write(os.path.join(loc, "header.md"), fm("header") + "# ვინ ხარ\n\nშენ ხარ აგენტი `{agent}` ჰოსტზე `{host}`, როლი **{role}**.\n")
        write(os.path.join(loc, "brief-missing.md"), fm("brief-missing") + "_ბრიფი ჯერ არ არის._\n")
        write(os.path.join(loc, "team.md"), fm("team") + "# გუნდი\n\nროლი {role} გუნდში.\n")
        write(os.path.join(loc, "memory.md"), fm("memory") + "# მეხსიერება\n\n{role}-ის მეხსიერება.\n")
        text = _build_direct(f, "language-culture-ge", "language-culture", locale="ge")
        assert text.startswith("# ვინ ხარ\n\nშენ ხარ აგენტი `language-culture-ge` ჰოსტზე `h`, როლი **language-culture**."), text[:200]
        for piece in ("_ბრიფი ჯერ არ არის._", "# გუნდი\n\nროლი language-culture გუნდში.", "# მეხსიერება\n\nlanguage-culture-ის მეხსიერება."):
            assert piece in text, piece
        assert "# Who you are" not in text and "Working with the team" not in text, "no English piece survives where the locale has one"
        assert text.index("# გუნდი") < text.index("# მეხსიერება"), "the shared sections keep their order"
        ru = _build_direct(f, "language-culture-ru", "language-culture", locale="ru")
        assert ru.startswith("# Who you are") and "# გუნდი" not in ru, "another suffix renders the English"
        launched, replace = _build_launch_direct(f, "language-culture-ge", "language-culture", tmp, locale="ge")
        assert launched == text and replace is False, "no harness translation: build()'s bytes, append"


def case_harness_translation_is_appended_last_and_replaces() -> None:
    """locale/<suffix>/harness.md: appended after the fabric's part, its
    {memory_dir} filled with the harness's own directory for the launch
    cwd, and the flag says the file replaces the whole prompt; --print
    and --out say so on stderr. Kills: rendering the harness before the
    charter, or leaving the placeholder in."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp, role="language-culture", brief=False)
        loc = os.path.join(f.root, "identities", "roles", "language-culture", "locale", "ge")
        write(os.path.join(loc, "harness.md"), "---\nclass: harness-translation\ntranslates: runtime/claude-code/harness/en.md\ntranslates_digest: sha256:x\n---\n"
                                              "შენ ხარ Claude Code.\n\n# მეხსიერება\n\nშენი მეხსიერება არის `{memory_dir}`.\n")
        cwd = os.path.join(tmp, "launch.dir"); os.makedirs(cwd)
        text, replace = _build_launch_direct(f, "language-culture-ge", "language-culture", cwd, locale="ge")
        assert replace is True
        fabric_part = _build_direct(f, "language-culture-ge", "language-culture", locale="ge")
        assert text.startswith(fabric_part), "the fabric's part first"
        tail = text[len(fabric_part):]
        assert tail.startswith("\nშენ ხარ Claude Code.") and "{memory_dir}" not in tail, tail[:120]
        expected_dir = os.path.expanduser("~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", cwd) + "/memory")
        assert f"`{expected_dir}`" in tail, tail
        other, _ = _build_launch_direct(f, "language-culture-ge", "language-culture", tmp, locale="ge")
        assert other != text and "launch-dir" in text, "the memory directory follows the launch cwd, nothing else does"
        # --print renders for the real login; the locale is its holder.json's, handed over as the launcher does.
        held = os.path.join(tmp, "holder.json")
        write(held, json.dumps(_locale_holder("language-culture", "ge")))
        f.bind("language-culture")
        r = f.run("--print", "--holder-file", held)
        assert r.returncode == 0 and "replace: yes" in r.stderr and "შენ ხარ Claude Code." in r.stdout, r.stderr
        f2 = Fixture(tmp + "/2", role="backend-dev")
        r2 = f2.run("--print")
        assert r2.returncode == 0 and "replace: no" in r2.stderr and "Claude Code" not in r2.stdout, r2.stderr


def _build_direct(f: "Fixture", agent: str, role: str, locale: str | None = None) -> str:
    """build() called with an explicit agent (identity.current_agent() has
    no override), inside the fixture's environment; `locale` is the
    holder.json locale, none when not given."""
    code = ("import importlib.util, json, os, sys; "
            "spec = importlib.util.spec_from_file_location('lp', sys.argv[1]); m = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(m); sys.stdout.write(m.build(sys.argv[2], 'h', sys.argv[3], json.loads(sys.argv[4])))")
    r = subprocess.run([sys.executable, "-c", code, os.path.join(f.root, "tools", "fabric", "launch_prompt.py"), agent, role,
                        json.dumps(_locale_holder(role, locale))], env=f.env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def case_locale_charter_is_rendered_for_the_holder_locale() -> None:
    """A holder whose holder.json says ge reads locale/ge/charter.md; the
    same login with no holder.json reads the English, whatever its name
    ends in; both renders are byte-stable. Kills: always reading
    charter.md, and choosing the locale from the login's suffix."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp, role="language-culture", brief=False)
        write(os.path.join(f.root, "identities", "roles", "language-culture", "locale", "ge", "charter.md"),
              "---\nrole: language-culture\nclass: charter\ndescription: \"x\"\ntier: 1\ndistilled_at: 2026-09-17\n"
              "translates: identities/roles/language-culture/charter.md\ntranslates_digest: sha256:" + "0" * 64 + "\n---\n\n"
              "# language-culture — წესდება\n\nGEORGIAN-BODY-LINE ქართულად.\n")
        holder = {"role": "language-culture", "charter": None, "brief": None, "holder": {"locale": "ge"}}
        ge = _build_holder(f, "language-culture-ge", "language-culture", holder)
        assert "GEORGIAN-BODY-LINE" in ge and "CHARTER-BODY-LINE" not in ge, ge
        assert "translates_digest" not in ge, "the translation's frontmatter leaked into the prompt"
        bare = _build_direct(f, "language-culture-ge", "language-culture")
        assert "CHARTER-BODY-LINE" in bare and "GEORGIAN-BODY-LINE" not in bare, "the login's suffix chose the locale"
        assert _build_holder(f, "language-culture-ge", "language-culture", holder) == ge, "not byte-stable"


def case_locale_render_has_a_wider_ceiling() -> None:
    """A translation is ~1.3x the characters of its source; the locale
    render is allowed MAX_CHARS * LOCALE_CHARS_FACTOR while the English
    render keeps the ceiling. Kills: one ceiling for both."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp, role="language-culture", brief=False)
        pad = "ქართული ხაზი\n" * 1900      # ~24.7k characters of body
        head = "---\nrole: language-culture\nclass: charter\ndescription: \"x\"\ntier: 1\ndistilled_at: 2026-09-17\n---\n\n"
        write(os.path.join(f.root, "identities", "roles", "language-culture", "charter.md"), head + "# c\n\n" + pad)
        r = f.run("--print")
        assert r.returncode == 1 and "exceeds" in r.stderr, "the English render lost its ceiling"
        write(os.path.join(f.root, "identities", "roles", "language-culture", "charter.md"), head + "# c\n\nshort\n")
        write(os.path.join(f.root, "identities", "roles", "language-culture", "locale", "ge", "charter.md"), head + "# c\n\n" + pad)
        assert "ქართული ხაზი" in _build_direct(f, "language-culture-ge", "language-culture", locale="ge")


def case_every_catalogue_role_renders_under_the_ceiling() -> None:
    """The launcher refuses a prompt over MAX_CHARS at launch — and until
    2026-09-20 nothing before the launch checked the RENDERED total: the
    lint budgets the charter and the brief each, the suite rendered
    fixtures, and a brand-comms charter that passed both broke that
    account's launch. Every role in the REAL catalogue renders here, for
    a plain (non-locale) agent, under the ceiling; a failure names the
    role and the size, the way the launcher does."""
    roles = [r["id"] for r in json.load(open(os.path.join(ROOT, "identities", "roles", "catalog.json")))["roles"]]
    assert roles, "the catalogue names roles"
    code = ("import importlib.util, sys, json; "
            "spec = importlib.util.spec_from_file_location('lp', sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
            "out = {}\n"
            "for role in sys.argv[2:]:\n"
            "    try:\n"
            "        t, _ = m.build_launch('test-agent', 'test-host', role); out[role] = len(t)\n"
            "    except SystemExit as exc:\n"
            "        out[role] = str(exc)\n"
            "sys.stdout.write(json.dumps({'max': m.MAX_CHARS, 'sizes': out}))")
    # The tree under test, not whatever AGENT_FABRIC_ROOT names in a session's environment.
    r = subprocess.run([sys.executable, "-c", code, os.path.join(ROOT, "tools", "fabric", "launch_prompt.py"), *roles],
                       env={**os.environ, "AGENT_FABRIC_ROOT": ROOT}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    over = [f"{role}: {size}" for role, size in got["sizes"].items() if not isinstance(size, int) or size > got["max"]]
    assert not over, f"rendered prompt over MAX_CHARS={got['max']} — shorten the charter or brief, or move the ceiling with its reason: " + "; ".join(over)


def _holder(f: "Fixture", tmp: str, **fields) -> str:
    """A holder file as tools/fabric/addenda.py writes it (ADR-060)."""
    doc = {"role": "backend-dev", "agent_id": "01a00000-0000-7000-8000-000000000000", "charter": None, "brief": None,
           "holder": None, "against": {}, "store_sha": "a" * 40, "addenda_commit": "b" * 40, **fields}
    path = os.path.join(tmp, "launch-holder.json")
    write(path, json.dumps(doc, ensure_ascii=False))
    return path


def case_holder_addenda_follow_their_shared_piece() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        plain = f.run("--print").stdout
        both = f.run("--print", "--holder-file", _holder(f, tmp, charter="CHARTER-ADDENDUM-LINE\n",
                                                          brief="BRIEF-ADDENDUM-LINE\n")).stdout
        order = [both.index(s) for s in ("CHARTER-BODY-LINE", "CHARTER-ADDENDUM-LINE",
                                          "BRIEF-BODY-LINE", "BRIEF-ADDENDUM-LINE")]
        assert order == sorted(order), f"pieces out of order: {order}"
        assert both.replace("CHARTER-ADDENDUM-LINE\n\n", "").replace("BRIEF-ADDENDUM-LINE\n\n", "") == plain, \
            "the addenda changed something besides their own place"
        only_charter = f.run("--print", "--holder-file", _holder(f, tmp, charter="CHARTER-ADDENDUM-LINE")).stdout
        assert "CHARTER-ADDENDUM-LINE" in only_charter and "BRIEF-ADDENDUM-LINE" not in only_charter
        only_brief = f.run("--print", "--holder-file", _holder(f, tmp, brief="BRIEF-ADDENDUM-LINE")).stdout
        assert only_brief.index("BRIEF-BODY-LINE") < only_brief.index("BRIEF-ADDENDUM-LINE")
        empty = f.run("--print", "--holder-file", _holder(f, tmp)).stdout
        assert empty == plain, "a holder with no addenda is not today's prompt"


def case_holder_addendum_follows_brief_missing_too() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp, brief=False)
        out = f.run("--print", "--holder-file", _holder(f, tmp, brief="BRIEF-ADDENDUM-LINE")).stdout
        assert out.index("No brief has been distilled") < out.index("BRIEF-ADDENDUM-LINE"), out[:400]


def case_holder_digest_moves_with_the_addendum_alone() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        out = os.path.join(tmp, "state", "agents", LOGIN, "launch-prompt.md")
        d1 = f.run("--out", out, "--holder-file", _holder(f, tmp, charter="ONE")).stdout.strip()
        d2 = f.run("--out", out, "--holder-file", _holder(f, tmp, charter="ONE", store_sha="c" * 40)).stdout.strip()
        d3 = f.run("--out", out, "--holder-file", _holder(f, tmp, charter="TWO")).stdout.strip()
        assert d1 == d2, "the digest moved with a field that is not rendered"
        assert d1 != d3, "the digest did not move with the addendum's text"


def case_holder_file_for_another_role_or_oversized_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        r = f.run("--print", "--holder-file", _holder(f, tmp, role="db-admin", charter="X"))
        assert r.returncode == 1 and "not 'backend-dev'" in r.stderr, r.stderr
        r = f.run("--print", "--holder-file", _holder(f, tmp, charter="x" * 4001))
        assert r.returncode == 1 and "over 4000" in r.stderr, r.stderr
        bad = os.path.join(tmp, "bad.json")
        write(bad, "{not json")
        r = f.run("--print", "--holder-file", bad)
        assert r.returncode == 1 and "could not be read" in r.stderr, r.stderr


def case_holder_ceiling_grows_by_the_addenda_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        size = len(f.run("--print").stdout)
        brief = os.path.join(f.root, "identities", "roles", "backend-dev", "brief.md")
        head = "---\nrole: backend-dev\nclass: brief\n---\n\n# backend-dev — brief\n\n"
        pad = 28000 - size
        for _ in range(3):   # the shared part exactly at MAX_CHARS: no slack to hide an off-by-one
            write(brief, head + "p" * pad + "\n")
            pad += 28000 - len(f.run("--print").stdout)
        shared = f.run("--print")
        assert shared.returncode == 0 and len(shared.stdout) == 28000, f"the fixture is not at the ceiling: {len(shared.stdout)}"
        r = f.run("--print", "--holder-file", _holder(f, tmp, charter="a" * 3999, brief="b" * 3999))
        assert r.returncode == 0, "addenda within their cap pushed a shared part under MAX_CHARS over the ceiling: " + r.stderr
        text = r.stdout
        assert "a" * 3999 in text and "b" * 3999 in text


def case_holder_georgian_addendum_is_kept_as_written() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        ka = "ქართული დამატება: სამართალი საქართველოს მიხედვით.\n"
        out = f.run("--print", "--holder-file", _holder(f, tmp, charter=ka)).stdout
        assert ka in out, "the Georgian addendum was not rendered byte for byte"


def _build_holder(f: "Fixture", agent: str, role: str, holder: dict) -> str:
    """build() with a holder dict, as --holder-file would hand it over."""
    code = ("import importlib.util, json, os, sys; "
            "spec = importlib.util.spec_from_file_location('lp', sys.argv[1]); m = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(m); sys.stdout.write(m.build(sys.argv[2], 'h', sys.argv[3], json.loads(sys.argv[4])))")
    r = subprocess.run([sys.executable, "-c", code, os.path.join(f.root, "tools", "fabric", "launch_prompt.py"), agent, role,
                        json.dumps(holder)], env=f.env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def case_holder_locale_chooses_the_rendering_not_the_suffix() -> None:
    """ADR-060 §5 rule 8: holder.json's locale picks locale/<locale>/ for a
    login whose suffix is another; without one, English, never the suffix."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp, role="legal-expert", brief=False)
        write(os.path.join(f.root, "identities", "roles", "legal-expert", "locale", "ge", "charter.md"),
              "---\nclass: charter\nrole: legal-expert\ntranslates: identities/roles/legal-expert/charter.md\ntranslates_digest: sha256:x\n---\n\n# ქარტია\n")
        holder = {"role": "legal-expert", "charter": None, "brief": None, "holder": {"locale": "ge"}}
        renamed = _build_holder(f, "legal-expert-tbilisi", "legal-expert", holder)
        assert "# ქარტია" in renamed and "CHARTER-BODY-LINE" not in renamed, "holder.json's locale did not choose the rendering"
        by_suffix = _build_direct(f, "legal-expert-ge", "legal-expert")
        assert "# ქარტია" not in by_suffix and "CHARTER-BODY-LINE" in by_suffix, "without a holder the suffix chose the locale"
        english = _build_holder(f, "legal-expert-ge", "legal-expert", {**holder, "holder": {"locale": "en"}})
        assert "CHARTER-BODY-LINE" in english, "a holder whose locale is en got the suffix's rendering"


def case_shared_pieces_render_per_language_for_every_role() -> None:
    """identities/prompt/locale/<locale>/ renders header, team, memory and
    brief-missing for any role's holder in that language; a role's own
    rendering of a piece wins over the shared one."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp, role="legal-expert", brief=False)
        shared = os.path.join(f.root, "identities", "prompt", "locale", "ge")
        fm = lambda src: f"---\nclass: prompt-translation\ntranslates: identities/prompt/{src}.md\ntranslates_digest: sha256:x\n---\n"
        write(os.path.join(shared, "header.md"), fm("header") + "# ვინ ხარ\n\n`{agent}` `{host}` **{role}**.\n")
        write(os.path.join(shared, "team.md"), fm("team") + "# გუნდი\n")
        write(os.path.join(shared, "memory.md"), fm("memory") + "# მეხსიერება\n")
        write(os.path.join(shared, "brief-missing.md"), fm("brief-missing") + "_ბრიფი არ არის._\n")
        text = _build_direct(f, "legal-expert-ge", "legal-expert", locale="ge")
        for piece in ("# ვინ ხარ", "# გუნდი", "# მეხსიერება", "_ბრიფი არ არის._"):
            assert piece in text, piece
        for english in ("# Who you are", "Working with the team", "Your long-term memory"):
            assert english not in text, f"an English section survived: {english}"
        own = os.path.join(f.root, "identities", "roles", "legal-expert", "locale", "ge", "team.md")
        write(own, fm("team") + "# გუნდი, იურისტისთვის\n")
        assert "# გუნდი, იურისტისთვის" in _build_direct(f, "legal-expert-ge", "legal-expert", locale="ge"), "the role's own rendering lost"
        assert "# Who you are" in _build_direct(f, "legal-expert-ru", "legal-expert", locale="ru"), "another locale got Georgian"


def main() -> int:
    cases = [
        case_locale_charter_is_rendered_for_the_holder_locale,
        case_every_piece_comes_from_the_locale_when_it_carries_one,
        case_harness_translation_is_appended_last_and_replaces,
        case_locale_render_has_a_wider_ceiling,
        case_header_names_agent_host_role,
        case_charter_and_brief_bodies_without_frontmatter,
        case_shared_sections_are_rendered_for_the_role,
        case_missing_brief_is_a_placeholder_not_a_failure,
        case_missing_charter_is_a_failure,
        case_no_binding_is_a_failure_naming_fabric_role,
        case_out_writes_the_file_and_prints_its_digest,
        case_byte_stable_across_builds_and_cwds,
        case_nothing_about_who_can_be_passed_in,
        case_oversized_prompt_is_refused,
        case_every_catalogue_role_renders_under_the_ceiling,
        case_holder_addenda_follow_their_shared_piece,
        case_holder_addendum_follows_brief_missing_too,
        case_holder_digest_moves_with_the_addendum_alone,
        case_holder_file_for_another_role_or_oversized_is_refused,
        case_holder_ceiling_grows_by_the_addenda_only,
        case_holder_georgian_addendum_is_kept_as_written,
        case_holder_locale_chooses_the_rendering_not_the_suffix,
        case_shared_pieces_render_per_language_for_every_role]
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
