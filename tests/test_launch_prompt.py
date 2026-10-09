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
                        os.path.join(self.root, "identities", "prompt"))
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


def _build_launch_direct(f: "Fixture", agent: str, role: str, cwd: str) -> tuple[str, bool]:
    """build_launch() with an explicit agent and cwd, inside the fixture."""
    code = ("import importlib.util, os, sys, json; "
            "spec = importlib.util.spec_from_file_location('lp', sys.argv[1]); m = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(m); t, r = m.build_launch(sys.argv[2], 'h', sys.argv[3], sys.argv[4]); sys.stdout.write(json.dumps([t, r]))")
    r = subprocess.run([sys.executable, "-c", code, os.path.join(f.root, "tools", "fabric", "launch_prompt.py"), agent, role, cwd],
                       env=f.env, capture_output=True, text=True)
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
        text = _build_direct(f, "language-culture-ge", "language-culture")
        assert text.startswith("# ვინ ხარ\n\nშენ ხარ აგენტი `language-culture-ge` ჰოსტზე `h`, როლი **language-culture**."), text[:200]
        for piece in ("_ბრიფი ჯერ არ არის._", "# გუნდი\n\nროლი language-culture გუნდში.", "# მეხსიერება\n\nlanguage-culture-ის მეხსიერება."):
            assert piece in text, piece
        assert "# Who you are" not in text and "Working with the team" not in text, "no English piece survives where the locale has one"
        assert text.index("# გუნდი") < text.index("# მეხსიერება"), "the shared sections keep their order"
        ru = _build_direct(f, "language-culture-ru", "language-culture")
        assert ru.startswith("# Who you are") and "# გუნდი" not in ru, "another suffix renders the English"
        launched, replace = _build_launch_direct(f, "language-culture-ge", "language-culture", tmp)
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
        text, replace = _build_launch_direct(f, "language-culture-ge", "language-culture", cwd)
        assert replace is True
        fabric_part = _build_direct(f, "language-culture-ge", "language-culture")
        assert text.startswith(fabric_part), "the fabric's part first"
        tail = text[len(fabric_part):]
        assert tail.startswith("\nშენ ხარ Claude Code.") and "{memory_dir}" not in tail, tail[:120]
        expected_dir = os.path.expanduser("~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", cwd) + "/memory")
        assert f"`{expected_dir}`" in tail, tail
        other, _ = _build_launch_direct(f, "language-culture-ge", "language-culture", tmp)
        assert other != text and "launch-dir" in text, "the memory directory follows the launch cwd, nothing else does"
        # --print renders for the real login (its suffix), so the locale is named after it.
        mine = os.path.join(f.root, "identities", "roles", "language-culture", "locale", LOGIN.rsplit("-", 1)[-1])
        if os.path.realpath(mine) != os.path.realpath(loc):   # on a login ending in -ge the two are one directory (the ge holder, 2026-09-17)
            shutil.copytree(loc, mine, dirs_exist_ok=True)
        f.bind("language-culture")
        r = f.run("--print")
        assert r.returncode == 0 and "replace: yes" in r.stderr and "შენ ხარ Claude Code." in r.stdout, r.stderr
        f2 = Fixture(tmp + "/2", role="backend-dev")
        r2 = f2.run("--print")
        assert r2.returncode == 0 and "replace: no" in r2.stderr and "Claude Code" not in r2.stdout, r2.stderr


def _build_direct(f: "Fixture", agent: str, role: str) -> str:
    """build() called with an explicit agent (identity.current_agent() has
    no override), inside the fixture's environment."""
    code = ("import importlib.util, os, sys; "
            "spec = importlib.util.spec_from_file_location('lp', sys.argv[1]); m = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(m); sys.stdout.write(m.build(sys.argv[2], 'h', sys.argv[3]))")
    r = subprocess.run([sys.executable, "-c", code, os.path.join(f.root, "tools", "fabric", "launch_prompt.py"), agent, role],
                       env=f.env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def case_locale_charter_is_rendered_for_the_login_suffix() -> None:
    """language-culture-ge reads locale/ge/charter.md; a login with no
    translation reads the English; both renders are byte-stable. Kills:
    always reading charter.md."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp, role="language-culture", brief=False)
        write(os.path.join(f.root, "identities", "roles", "language-culture", "locale", "ge", "charter.md"),
              "---\nrole: language-culture\nclass: charter\ndescription: \"x\"\ntier: 1\ndistilled_at: 2026-09-17\n"
              "translates: identities/roles/language-culture/charter.md\ntranslates_digest: sha256:" + "0" * 64 + "\n---\n\n"
              "# language-culture — წესდება\n\nGEORGIAN-BODY-LINE ქართულად.\n")
        ge = _build_direct(f, "language-culture-ge", "language-culture")
        assert "GEORGIAN-BODY-LINE" in ge and "CHARTER-BODY-LINE" not in ge, ge
        assert "translates_digest" not in ge, "the translation's frontmatter leaked into the prompt"
        ru = _build_direct(f, "language-culture-ru", "language-culture")
        assert "CHARTER-BODY-LINE" in ru and "GEORGIAN-BODY-LINE" not in ru, ru
        assert _build_direct(f, "language-culture-ge", "language-culture") == ge, "not byte-stable"


def case_locale_render_has_a_wider_ceiling() -> None:
    """A translation is ~1.3x the characters of its source; the locale
    render is allowed MAX_CHARS * LOCALE_CHARS_FACTOR while the English
    render keeps the ceiling. Kills: one ceiling for both."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp, role="language-culture", brief=False)
        pad = "ქართული ხაზი\n" * 1500      # ~19.5k characters of body
        head = "---\nrole: language-culture\nclass: charter\ndescription: \"x\"\ntier: 1\ndistilled_at: 2026-09-17\n---\n\n"
        write(os.path.join(f.root, "identities", "roles", "language-culture", "charter.md"), head + "# c\n\n" + pad)
        r = f.run("--print")
        assert r.returncode == 1 and "exceeds" in r.stderr, "the English render lost its ceiling"
        write(os.path.join(f.root, "identities", "roles", "language-culture", "charter.md"), head + "# c\n\nshort\n")
        write(os.path.join(f.root, "identities", "roles", "language-culture", "locale", "ge", "charter.md"), head + "# c\n\n" + pad)
        assert "ქართული ხაზი" in _build_direct(f, "language-culture-ge", "language-culture")


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


def main() -> int:
    cases = [
        case_locale_charter_is_rendered_for_the_login_suffix,
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
        case_every_catalogue_role_renders_under_the_ceiling]
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
