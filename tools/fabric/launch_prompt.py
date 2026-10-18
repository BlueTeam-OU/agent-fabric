#!/usr/bin/env python3
"""tools/fabric/launch_prompt.py — the system prompt a session is born with.

>>> help
    launch_prompt.py --out FILE        render for this agent's bound role, write
                                       FILE atomically, print sha256:<hex>
    launch_prompt.py --print           render to stdout, write nothing
<<< help

runtime/openrouter/launch calls this just before exec and passes the file
to claude as `--append-system-prompt-file` (read back live on both launch
paths: docs/live-checks/2026-09-15-append-system-prompt.md). The session
therefore holds its role from its first request, in the system prompt —
which survives compaction and cannot be edited from inside — instead of
being asked to Read a charter after it starts (the old /role command).

WHO IS NOT A PARAMETER. Agent, host and role are resolved here, from the
OS and the runtime binding (runtime/identity.py); the caller names only
where the file goes. Nothing about identity can be passed in.

WHAT GOES IN, in order: the identity header; the role's charter; its brief
(how the role works, in any project — absent until written, and a missing
brief never blocks a launch); then the two sections every role shares,
identities/prompt/team.md and memory.md, with `{role}` substituted.

WHAT STAYS OUT: the project. The remit, the INDEX pointer and the working
copy follow the cwd and change with `cd`; they reach the session from the
SessionStart hook (runtime/claude-code/hooks/session-start.py), never
from this file. The filesystem is context, not identity.

BYTE-STABLE by construction: no timestamps, no session id, no cwd. The
same (agent, host, role) renders the same bytes, so the harness's prompt
prefix stays cacheable across relaunches and the digest the launcher
stamps (AGENT_FABRIC_LAUNCH_PROMPT_DIGEST) changes only when the content
did.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layout = _load("fabric_layout", os.path.join(HERE, "layout.py"))
identity = _load("fabric_identity", os.path.join(layout.FABRIC_ROOT, "runtime", "identity.py"))

FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
# ~7 000 tokens at four characters each, paid on every request of a
# session. Sized by the largest render in the catalogue: language-culture's
# English at 26.5k and brand-comms at 24.5k (2026-09-20) — a full charter,
# the fabric's longest brief and the team section together. A raise of
# layout.PROMPT_TEMPLATE_BUDGET_TOKENS (the team and memory templates)
# moves this with it; a charter or brief beyond its own lint budget is a
# lint problem upstream, not a reason to move it.
MAX_CHARS = 28_000   # 20_000 until 2026-09-18 (the owner's two rules); 21_500 and 23_000 on 2026-09-19 (one open PR per agent, the clean-test rule); 28_000 on 2026-09-20: the owner's brand-comms sections rendered 24.5k over the fabric's longest brief, and language-culture's English render 26.5k — a green PR broke a launch because nothing but the launcher checked the rendered total; tests/test_launch_prompt.py now renders every role against this number

# The header, the missing-brief line, the team and memory sections are
# templates under identities/prompt/ (lint budgets them together): the
# header carries {agent}, {host} and {role}; a role with no brief renders
# brief-missing.md. Moved out of code on 2026-09-17 so a locale can carry
# a translation of each: once per language in identities/prompt/locale/
# <locale>/, or in a role's own locale/<locale>/, which wins (_locale_path),
# rendered for the holder whose locale it is (locale_of).
HEADER_TEMPLATE = "header.md"
BRIEF_MISSING_TEMPLATE = "brief-missing.md"



def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _template(name: str) -> str:
    """A prompt template under identities/prompt/, verbatim; a missing one
    is the same failure lint names."""
    path = layout.prompt_template_path(name)
    if not os.path.isfile(path):
        raise SystemExit(f"launch_prompt: {layout.root_rel(path)} is missing (tools/fabric/lint.py names it)")
    return _read(path)


def _body(path: str) -> str:
    """A slice's markdown without its frontmatter, trailing newline kept."""
    text = FRONTMATTER_RE.sub("", _read(path), count=1)
    return text.strip("\n") + "\n"


# A locale's translation of any piece is rendered for a holder of that
# locale: the CEO's rule of 2026-09-17 that a holder who thinks in its
# language reads its own definition in it. The locale is the holder's
# holder.json `locale` (ADR-060 §5 rule 8; locale_of below), English
# for a holder that names none; never the login's name, which a rename
# changes. A locale/ directory is an authored thing lint
# validates (a source digest, a lag finding), and with none present every
# role renders as before, byte-identical. A translation is served even when lint says it lags — a
# launch never fails on a day's lag; lint is where the lag is seen. The
# real cost is tokens, not characters: measured on the first Georgian
# charter, the rendering is about the characters of its English (11 041
# against 10 931) and 2.9x the tokens (7 584 against 2 642;
# docs/live-checks/2026-09-17-language-culture-bridge.md). The character
# ceiling therefore needs little headroom — LOCALE_CHARS_FACTOR times
# MAX_CHARS — and the token cost is the CEO's accepted price for the role.
LOCALE_CHARS_FACTOR = 1.35


def locale_of(agent: str, holder: dict | None = None) -> str:
    """The locale this launch renders in (agent-fabric ADR-060 §5 rule 8):
    the holder's holder.json `locale` when it names one, else English. The
    login's suffix chose it until every holder in another language had a
    holder.json (docs/live-checks/2026-10-18-holder-locale.md); it is not
    read, so a rename never changes the language. The launcher resolves the
    same way (launcher/holder.py), so the prompt and the harness flag never
    pick two different locales."""
    settings = (holder or {}).get("holder") or {}
    tag = settings.get("locale") if isinstance(settings, dict) else None
    return tag if isinstance(tag, str) and tag else "en"


# The role-independent pieces (header, team, memory, brief-missing) are
# translated once per language, for every role, under
# identities/prompt/locale/<locale>/ (ADR-060 §5 rule 8): a holder of any
# role in that language renders them in it. A role's own locale/<locale>/
# still wins for a piece it carries, so a role may keep its own rendering.
SHARED_PIECES = ("header", "team", "memory", "brief-missing")


def _locale_path(role_dir: str, locale: str, name: str) -> str | None:
    """The locale's rendering of a piece when one exists, else None: the
    role's own identities/roles/<role>/locale/<locale>/<name>.md first, then,
    for a role-independent piece, identities/prompt/locale/<locale>/<name>.md."""
    path = os.path.join(role_dir, "locale", locale, f"{name}.md")
    if os.path.isfile(path):
        return path
    if name in SHARED_PIECES:
        shared = os.path.join(os.path.dirname(layout.prompt_template_path(HEADER_TEMPLATE)), "locale", locale, f"{name}.md")
        if os.path.isfile(shared):
            return shared
    return None


def _charter_path(role_dir: str, locale: str) -> str:
    return _locale_path(role_dir, locale, "charter") or os.path.join(role_dir, "charter.md")


def _piece(role_dir: str, locale: str, name: str, default_text: str) -> tuple[str, bool]:
    """A prompt piece: the locale's rendering (its body) when there is one,
    else the English `default_text`; and whether it was the locale's."""
    path = _locale_path(role_dir, locale, name)
    return (_body(path), True) if path else (default_text, False)


# THE HOLDER'S ADDENDA (agent-fabric ADR-060). The launcher reads them from
# the agent's own store (tools/fabric/addenda.py, which verifies them) and
# hands them over as a file; this module only places them, so it stays pure.
# Each is capped on its own, and the ceiling grows by exactly what they add:
# the shared part keeps its budget whatever a holder carries.
ADDENDUM_MAX_CHARS = 4000


def build(agent: str, host: str, role: str, holder: dict | None = None) -> str:
    """The prompt text for one (agent, host, role): the fabric's part —
    header, charter, brief (or the missing-brief line), the shared
    sections — each from the login's locale when it carries a
    translation, else the English — with the holder's charter addendum
    after the charter and its brief addendum after the brief. Pure: reads
    the repository, touches nothing else; byte-identical for every login
    without locale files and without a holder."""
    added = _addenda(role, holder)
    locale = locale_of(agent, holder)
    role_dir = layout.role_dir(role)
    charter = _charter_path(role_dir, locale)
    if not os.path.isfile(charter):
        raise SystemExit(f"launch_prompt: role {role!r} has no charter at {charter}")
    localized = charter != os.path.join(role_dir, "charter.md")
    header, loc = _piece(role_dir, locale, "header", _template(HEADER_TEMPLATE))
    localized = localized or loc
    parts = [header.replace("{agent}", agent).replace("{host}", host).replace("{role}", role)]
    # The charter and the brief carry their own H1 ("<role> — charter",
    # "<role> — brief"); only a missing brief needs a heading of its own.
    parts.append(_body(charter))
    if added["charter"]:
        parts.append(added["charter"])
    brief = os.path.join(role_dir, "brief.md")
    if os.path.isfile(brief) or _locale_path(role_dir, locale, "brief"):
        text, loc = _piece(role_dir, locale, "brief", _body(brief) if os.path.isfile(brief) else "")
        localized = localized or loc
        parts.append(text)
    else:
        text, loc = _piece(role_dir, locale, "brief-missing", _template(BRIEF_MISSING_TEMPLATE))
        localized = localized or loc
        parts.append(text.replace("{role}", role).strip("\n") + "\n")   # the piece carries its own heading (blind review of #3: it was English in a Georgian prompt)
    if added["brief"]:
        parts.append(added["brief"])
    for name in layout.PROMPT_TEMPLATES:
        path = layout.prompt_template_path(name)
        if not os.path.isfile(path):
            raise SystemExit(f"launch_prompt: {layout.root_rel(path)} is missing (tools/fabric/lint.py names it)")
        text, loc = _piece(role_dir, locale, name[:-3], _read(path))
        localized = localized or loc
        parts.append(text.replace("{role}", role).strip("\n") + "\n")
    text = "\n".join(parts)
    # Each addendum is one more joined part, so it adds its length and one
    # separator; the ceiling grows by exactly that (ADR-060 §5 rule 6).
    ceiling = (int(MAX_CHARS * LOCALE_CHARS_FACTOR) if localized else MAX_CHARS) + sum(len(a) + 1 for a in added.values() if a)
    if len(text) > ceiling:
        raise SystemExit(f"launch_prompt: {len(text)} characters for role {role!r} exceeds {ceiling}; "
                         "shorten the charter or brief (tools/fabric/lint.py budgets them)")
    return text


# THE HARNESS TEXT IN THE LOCALE. Claude Code's own system prompt is
# English and comes before the fabric's appended prompt; a holder whose
# locale (locale_of) the role carries a locale/<locale>/harness.md for (a translation of
# runtime/claude-code/harness/en.md) is launched with the whole prompt
# REPLACED instead — the fabric's part first, in the locale, then the
# harness text in the locale — because the harness offers no prepend and
# the CEO's order is the charter before it (2026-09-17). The harness
# still sends, outside the replaceable text, the function-calling
# grammar, every tool schema, the listings and CLAUDE.md, so a
# replacement changes no mechanics (docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md).
# The one login-specific span, the memory directory, is the placeholder
# {memory_dir}, filled with the directory the harness itself uses for
# the launch directory (layout.default_memory_dir) — the one
# deliberate way the rendered text varies with the cwd.
HARNESS_PLACEHOLDER = "{memory_dir}"


def render_harness(role_dir: str, locale: str, cwd: str | None = None) -> str | None:
    path = _locale_path(role_dir, locale, "harness")
    if not path:
        return None
    return _body(path).replace(HARNESS_PLACEHOLDER, layout.default_memory_dir(cwd or os.getcwd()))


def build_launch(agent: str, host: str, role: str, cwd: str | None = None,
                 holder: dict | None = None) -> tuple[str, bool]:
    """What the launcher passes: build()'s text, and — when the locale
    carries a harness translation — that text appended last, with True
    meaning the file rides --system-prompt-file (the whole prompt) instead
    of --append-system-prompt-file. Without one, build()'s bytes and False."""
    text = build(agent, host, role, holder)
    harness = render_harness(layout.role_dir(role), locale_of(agent, holder), cwd)
    if harness is None:
        return text, False
    return text + "\n" + harness, True


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def render(out: str, agent: str, host: str, role: str, holder: dict | None = None) -> str:
    """Write the prompt for (agent, host, role) to `out` atomically and
    return its digest: identity.atomic_write, like every write under
    agents/<login>/ (agent-fabric ADR-003), so a launch that dies
    mid-write leaves the previous prompt intact rather than a torn one."""
    text, replace = build_launch(agent, host, role, holder=holder)
    print(f"replace: {'yes' if replace else 'no'}", file=sys.stderr)
    directory = os.path.dirname(os.path.abspath(out)) or "."
    os.makedirs(directory, exist_ok=True)
    identity.atomic_write(out, text)
    return digest(text)


def _addenda(role: str, holder: dict | None) -> dict[str, str]:
    """The holder's two addenda as prompt pieces, each ending in one newline
    like the shared sections; empty when absent. A holder for another role,
    or an addendum over its cap, stops the render: addenda.py has verified
    them, so either means the file is not the one it wrote."""
    out = {"charter": "", "brief": ""}
    if holder is None:
        return out
    if holder.get("role") != role:
        raise SystemExit(f"launch_prompt: the holder file is for role {holder.get('role')!r}, not {role!r}")
    for name in out:
        text = holder.get(name)
        if text is None:
            continue
        if not isinstance(text, str):
            raise SystemExit(f"launch_prompt: the holder's {name} addendum is not text")
        if len(text) > ADDENDUM_MAX_CHARS:
            raise SystemExit(f"launch_prompt: the holder's {name} addendum is {len(text)} characters, "
                             f"over {ADDENDUM_MAX_CHARS} (agent-fabric ADR-060 §5 rule 6)")
        out[name] = text.strip("\n") + "\n" if text.strip() else ""
    return out


def _holder_file(path: str, role: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            holder = json.load(fh)
    except (OSError, ValueError) as e:
        raise SystemExit(f"launch_prompt: the holder file {path} could not be read ({type(e).__name__})")
    if not isinstance(holder, dict):
        raise SystemExit(f"launch_prompt: the holder file {path} is not an object")
    _addenda(role, holder)
    return holder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="launch_prompt.py", add_help=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", help="write the prompt here and print its digest")
    group.add_argument("--print", action="store_true", help="render to stdout, write nothing")
    parser.add_argument("--holder-file", help="the holder's addenda as addenda.py wrote them (ADR-060)")
    args = parser.parse_args(argv)

    agent = identity.current_agent()
    host = identity.current_host()
    binding = identity.read_binding(agent)
    role = binding.get("role")
    if not role:
        print(f"launch_prompt: agent {agent!r} has no active role binding; "
              "bind one first (fabric-role bind <role>).", file=sys.stderr)
        return 1
    holder = _holder_file(args.holder_file, role) if args.holder_file else None
    if args.print:
        text, replace = build_launch(agent, host, role, holder=holder)
        sys.stdout.write(text)
        print(f"replace: {'yes' if replace else 'no'}", file=sys.stderr)
        return 0
    print(render(args.out, agent, host, role, holder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
