"""tools/fabric/gzcoord/compose.py — write a ready-to-edit GZCoord message,
so no session hand-types a header. The command is bin/gzcoord-compose.

CONTRACT:
  argv      <TYPE> (--to <host/login> | --to-role <slug> | --broadcast)
            --subject <line> [--in-reply-to <id>] [--reply-expected yes|no]
            [--repository <org/repo>] [-o FILE] | -h | --help
  env       what gzcoord-send reads to say who this session is
            (AGENT_FABRIC_ROOT, AGENT_FABRIC_STATE_DIR, XDG_STATE_HOME);
            nothing else
  stdout    the message, or nothing with -o; --help's text
  stderr    a warning the validator raised, REPOSITORY left out and why,
            the file written, a refusal
  exit      0 composed; 1 usage (an option given twice included), a
            value with a line break, bytes that are not UTF-8 or nothing
            but blanks, or -o FILE that exists or cannot be written; 2 the
            message would be invalid (an unknown or retired type, an
            assignment toward a role, an address of the wrong shape, ROLE
            or PROJECT unknown) or refused by send (an IN-REPLY-TO that is
            not an id): the validator's own reason, in the reader's
            language

It never sends. FROM, ROLE and PROJECT are what gzcoord-send resolves for
this login (gzmsg.whoami, inbox.identity), so a composed message passes
send's FROM check. MESSAGE-ID is minted here (gzmsg.mint_id, as `gzmsg
new-id`): every composed file is a new message with its own id, which is
why -o refuses a file that exists (send keeps an id in its file, and an id
reused for other text is refused there). REPOSITORY is the working copy's
origin as <org>/<repo> unless given; when it cannot be read it is left out
(it is optional, SPEC §7.3) and stderr says why — never guessed.

The body is the type's sections as empty headings, then REFERENCES:. The
table is this tool's skeleton convention (fabric-coordinator, 2026-10-07),
not a protocol rule: SPEC §11 lets a message use any section. Toward a
role, REQUEST: is left out, since SPEC §13 makes a role-addressed message
carrying it an assignment the validator refuses; a REQUEST itself toward a
role is still refused. The whole skeleton is validated as send validates
(gzmsg.validate, width off) before anything is written.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import git  # noqa: E402
from gzcoord import gzmsg, i18n, inbox  # noqa: E402

SECTIONS: dict[str, tuple[str, ...]] = {
    "INFO": ("CONTEXT", "NOTES"),
    "OBSERVATION": ("OBSERVATION", "VERIFIED", "NOT-VERIFIED", "IMPACT", "REQUEST"),
    "QUESTION": ("CONTEXT", "QUESTION"),
    "REQUEST": ("REQUEST", "ACCEPTANCE", "DELIVER-TO"),
    "REVIEW": ("CONTEXT", "REQUEST", "IMPACT"),
    "DECISION": ("DECISION", "RATIONALE"),
    "HANDOFF": ("CONTEXT", "REQUEST"),
    "REPLY": ("REPLY",),
}

HELP = """\
usage: gzcoord-compose <TYPE> (--to <host/login> | --to-role <slug> | --broadcast)
                       --subject <line> [--in-reply-to <id>] [--reply-expected yes|no]
                       [--repository <org/repo>] [-o FILE]

Write a GZCoord message with its header filled and its sections empty, to
edit and then send with gzcoord-send. It never sends.

FROM, ROLE and PROJECT are this login's, as gzcoord-send resolves them;
MESSAGE-ID is minted; REPOSITORY is origin's <org>/<repo> unless given,
and left out (said on stderr) when it cannot be read. The message is
validated before it is written.

The sections, then REFERENCES: — a convention of this tool, not a
protocol rule (any section is allowed):
  INFO         CONTEXT: NOTES:
  OBSERVATION  OBSERVATION: VERIFIED: NOT-VERIFIED: IMPACT: REQUEST:
  QUESTION     CONTEXT: QUESTION:
  REQUEST      REQUEST: ACCEPTANCE: DELIVER-TO:
  REVIEW       CONTEXT: REQUEST: IMPACT:
  DECISION     DECISION: RATIONALE:
  HANDOFF      CONTEXT: REQUEST:
  REPLY        REPLY:
  X-<name>     (REFERENCES: only)
Toward a role (--to-role) REQUEST: is left out: it would make the message
an assignment, which goes to one login. A REQUEST toward a role is refused.

  -o FILE   write to FILE, created mode 0600; refused if FILE exists (a
            new message is a new file: send keeps the id in it)

exit: 0 composed; 1 usage (a value with a line break, bytes that are not
UTF-8, an option given twice), -o FILE exists or cannot be written; 2 the
message would be invalid, or refused by gzcoord-send (the reason)
"""

# Any line break the parser or a terminal would honour: a value carrying
# one would write a line of its own into the header (a forged key).
_BREAK = re.compile("[\r\n\v\f\x1c\x1d\x1e\x85  ]")
# origin's URL: scp-like (git@host:org/repo), or a URL with a scheme
# (https://, ssh://, git://, file:// is not a forge and is not matched).
_REMOTE = (re.compile(r"^[^/@:\s]+@[^/:\s]+:(?P<path>[^\s]+)$"),
           re.compile(r"^(?:https?|ssh|git)://[^/\s]+/(?P<path>[^\s]+)$"))
# Any scheme RFC 3986 admits, in any case: one git cannot use is printed too.
_USERINFO = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)[^/\s]*@")
_ORG_REPO = re.compile(r"^(?P<org>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?/?$")


class Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise Usage(message)


class _Once(argparse.Action):
    """argparse keeps the last of a repeated option: `--to a/b --to c/d`
    would address c/d and drop a/b without a word."""

    def __call__(self, parser, namespace, values, option_string=None):  # type: ignore[override]
        if getattr(namespace, self.dest, None) is not None:
            raise Usage(f"{option_string} given twice")
        setattr(namespace, self.dest, values)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = _Parser(prog="gzcoord-compose", add_help=False, allow_abbrev=False)
    p.add_argument("type")
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--to", action=_Once)
    where.add_argument("--to-role", action=_Once)
    where.add_argument("--broadcast", action="store_true")
    p.add_argument("--subject", required=True, action=_Once)
    p.add_argument("--in-reply-to", action=_Once)
    p.add_argument("--reply-expected", action=_Once)
    p.add_argument("--repository", action=_Once)
    p.add_argument("-o", dest="output", action=_Once)
    a = p.parse_args(argv)
    # A value is carried exactly or refused: never a forged line, a byte
    # turned into "?" on the way out, or a header the parser reads as empty.
    for flag in ("type", "to", "to_role", "subject", "in_reply_to", "reply_expected", "repository"):
        value = getattr(a, flag)
        if value is None:
            continue
        name = "TYPE" if flag == "type" else "--" + flag.replace("_", "-")
        if any("\udc80" <= c <= "\udcff" for c in value):
            raise Usage(f"{name} holds bytes that are not UTF-8")
        if _BREAK.search(value):
            raise Usage(f"{name} holds a line break; a header value is one line")
        if not gzmsg.js_trim(value):
            raise Usage(f"{name} is empty")
    return a


def origin_repository(cwd: str) -> tuple[str | None, str | None]:
    """(<org>/<repo>, None) or (None, why it was left out)."""
    # The working copy at cwd, not one a session's GIT_DIR or GIT_CONFIG_*
    # points at.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        r = git.run(cwd, "remote", "get-url", "origin", check=False, timeout=30, env=env,
                    what="git remote get-url origin")
    except git.GitError as e:
        return None, str(e)
    if r.returncode != 0:
        lines = [l for l in r.stderr.strip().splitlines() if l.strip()]
        return None, (lines[-1] if lines else f"git remote get-url origin: exit {r.returncode}")
    url = r.stdout.strip()
    for shape in _REMOTE:
        m = shape.match(url)
        if m:
            path = _ORG_REPO.match(m.group("path"))
            if path:
                return f"{path.group('org')}/{path.group('repo')}", None
    # A URL can carry a token as its user part; stderr reaches a transcript.
    return None, f"origin's URL is not <host>/<org>/<repo>: {_USERINFO.sub(r'\g<scheme>', url)}"


def skeleton(mtype: str, header: list[tuple[str, str]], to_role: bool) -> str:
    names = SECTIONS.get(mtype, ())
    if to_role:
        names = tuple(n for n in names if n != "REQUEST")
    lines = [f"[GZCOORD/1] {mtype}", *(f"{k}: {v}" for k, v in header), ""]
    for name in (*names, "REFERENCES"):
        lines += [f"{name}:", ""]
    return "\n".join(lines)


def write_new(path: str, text: str) -> None:
    """Created, never followed or replaced: O_EXCL refuses a file or a link
    already there. A failed write leaves no partial file behind."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    except BaseException:
        os.unlink(path)
        raise


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        sys.stdout.write(HELP)
        return 0
    try:
        a = parse_args(argv)
    except Usage as e:
        print(f"gzcoord-compose: {e}\n{HELP.split(chr(10) + chr(10))[0]}", file=sys.stderr)
        return 1

    who = gzmsg.whoami()
    t = i18n.t_for(who)
    tax_path = gzmsg.find_taxonomy()
    taxonomy = gzmsg.load_taxonomy(tax_path) if tax_path else None
    me = inbox.identity(who, taxonomy)
    if me.get("roleError"):
        print(f"gzcoord-compose: warning: {me['roleError']}", file=sys.stderr)

    repository = a.repository
    if repository is None:
        repository, why = origin_repository(os.getcwd())
        if repository is None:
            print(f"gzcoord-compose: REPOSITORY left out: {why}", file=sys.stderr)

    header: list[tuple[str, str]] = [("FROM", me["address"])]
    # Unknown stays unknown: a missing ROLE or PROJECT is left out, and the
    # validator below refuses the message for it.
    if me.get("slug"):
        header.append(("ROLE", me["slug"]))
    if me.get("project"):
        header.append(("PROJECT", me["project"]))
    if repository is not None:
        header.append(("REPOSITORY", repository))
    if a.to is not None:
        header.append(("TO", a.to))
    elif a.to_role is not None:
        header.append(("TO-ROLE", a.to_role))
    else:
        header.append(("BROADCAST", "true"))
    if a.in_reply_to is not None:
        header.append(("IN-REPLY-TO", a.in_reply_to))
    if a.reply_expected is not None:
        header.append(("REPLY-EXPECTED", a.reply_expected))
    header += [("MESSAGE-ID", gzmsg.mint_id()), ("SUBJECT", a.subject)]

    text = skeleton(a.type, header, a.to_role is not None)
    result = gzmsg.validate(text, taxonomy=taxonomy, max_columns=0, t=t)
    # send refuses an id that is not id-shaped where the validator only
    # warns; a composed message is one send will take.
    refused = [c for c in (gzmsg.id_complaint(k, v, t) for k, v in header if k in ("MESSAGE-ID", "IN-REPLY-TO")) if c]
    for w in result["warnings"]:
        if w not in refused:
            print(f"gzcoord-compose: warning: {w}", file=sys.stderr)
    if not result["ok"] or refused:
        for e in (*result["errors"], *refused):
            print(f"gzcoord-compose: {e}", file=sys.stderr)
        return 2

    if a.output is None:
        sys.stdout.write(text)
        return 0
    try:
        write_new(a.output, text)
    except OSError as e:
        print(f"gzcoord-compose: cannot write {a.output}: {e.strerror or e}", file=sys.stderr)
        return 1
    print(f"gzcoord-compose: written to {a.output}", file=sys.stderr)
    return 0


def run(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        return main(argv)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001 — send's last resort: one line, exit 1, never a traceback
        print(f"gzcoord-compose: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
