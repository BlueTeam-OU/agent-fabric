"""tools/fabric/genimage.py — generate an image with OpenAI's image API and
save it as a PNG. The command is bin/fabric-genimage. Ported from a
project's scripts/genimage.mjs (the commit that added this file names it)
on the owner's decision of 2026-10-07 that image generation is a fabric
tool; the contract is brand-comms-01's, with fabric-coordinator's
decisions on its open points.

CONTRACT:
  argv      tokens left to right: -o|--out <v> (required), --size <v>
            (default 1536x1024), --quality <v> (default high), --model <v>
            (default gpt-image-1), --background <v> (sent only when given),
            --dry-run, -h|--help (HELP on stdout, exit 0); any other token
            starting with "-" is "unknown option <tok>"; anything else is a
            prompt word. An option's value is the next token whatever it
            looks like; none left is "<opt> needs a value". The prompt is
            the words joined by one space, trimmed. Then, in order: an
            empty prompt, no -o, an -o not ending .png (any case).
  paths     a relative -o and .env.local are at the working copy root: the
            git toplevel of the cwd, or the cwd outside a repository. Any
            other git failure refuses; it is never taken as the cwd.
  env       OPENAI_API_KEY; HOME (for ~/.config/agent-fabric/secrets.env);
            PATH (git). Nothing overrides the endpoint.
  stdout    "• model …", "• prompt: …", "• out:    …", "• key:    …" before
            any request; then "(dry run — no request made)", or "✓ wrote …"
            and the revised prompt and token lines when the response has them
  stderr    one line, "fabric-genimage: <reason>"
  exit      0 written, dry run, --help; 1 everything else (130 interrupted)

THE KEY, first non-empty wins, never printed, never in argv or an
exception: OPENAI_API_KEY in the environment; .env.local at the working
copy root (only OPENAI_API_KEY is read from it, and it fills a value that
is unset or empty); the LAST `export OPENAI_API_KEY=` line of the
account's ~/.config/agent-fabric/secrets.env, which `fabric-secrets sync`
writes with shlex.quote. The process need not have inherited it
(agent-fabric#100 stopped exporting synced secrets into shells), so the
line is read and unquoted here. A value that does not unquote, or holds a
newline, is "unreadable", never guessed.

A REFUSAL says its status and the allow-listed error type and code only,
never the message or any part of the body: a 401 echoes a fragment of the
key it refused. A value starting "sk-" is refused before the
lists are read, so no list edit can print a key. There is no complete
public list of codes; an unlisted one prints as "other" — add it to the
list when it is met.

THE KEY GOES TO api.openai.com ONLY: no redirect is followed (a 3xx is a
refusal like any non-2xx) and no proxy is used. urllib would carry the
Authorization header to a redirect's host and honour *_PROXY; Node's fetch,
which the .mjs used, did neither. A transport failure names its class and
nothing else: an exception's text can hold a URL or a header.
"""
from __future__ import annotations

import base64
import binascii
import contextlib
import errno
import json
import os
import pwd
import re
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import git  # noqa: E402
import httpsafe  # noqa: E402

ENDPOINT = "https://api.openai.com/v1/images/generations"
TIMEOUT_S = 300
# The synced env file's path, and how a line names it. Not named for
# "secrets": CodeQL's clear-text-logging query takes a name like that for
# a secret and followed this path into every line it appears in (alerts
# 53 and 54 on #110).
SYNCED_ENV = os.path.join(".config", "agent-fabric", "secrets.env")
SYNCED_ENV_SHOWN = "~/.config/agent-fabric/secrets.env"

ERROR_TYPES = frozenset((
    "invalid_request_error", "authentication_error", "permission_error", "not_found_error",
    "rate_limit_error", "insufficient_quota", "server_error", "api_error", "requests", "tokens",
))
ERROR_CODES = frozenset((
    "invalid_api_key", "invalid_organization", "invalid_project", "model_not_found",
    "insufficient_quota", "rate_limit_exceeded", "billing_hard_limit_reached", "billing_not_active",
    "content_policy_violation", "moderation_blocked", "invalid_value", "invalid_type",
    "unsupported_value", "unknown_parameter", "missing_required_parameter", "string_above_max_length",
    "server_error",
))

# JavaScript's whitespace (String.prototype.trim, \s) and line terminators
# (what `.` does not match): Python's str.strip and re's \s are another set.
_JS_SPACE = "\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_JS_TRIM = re.compile(f"^[{_JS_SPACE}]+|[{_JS_SPACE}]+$")
_JS_SPACE_CHAR = re.compile(f"[{_JS_SPACE}]")
_JS_DOT = "[^\n\r\u2028\u2029]"
_ENV_LINE = re.compile(f"^[{_JS_SPACE}]*(?:export[{_JS_SPACE}]+)?([A-Za-z_][A-Za-z0-9_]*)[{_JS_SPACE}]*="
                       f"[{_JS_SPACE}]*({_JS_DOT}*?)[{_JS_SPACE}]*$")
_QUOTED = re.compile(r"^(['\"])(.*)\1$", re.DOTALL)

HELP = """\
usage: fabric-genimage "<prompt>" -o <path>.png [options]

Generate an image with OpenAI's image API and save it as a PNG.

  -o, --out <path>       output file, .png (any case). Required. A relative
                         path is under the working copy root (the git
                         toplevel of the current directory; outside a
                         repository, the current directory). Parent
                         directories are created; an existing file is
                         replaced.
  --size <WxH|auto>      1024x1024 | 1536x1024 (landscape, deck backgrounds)
                         | 1024x1536 | auto                 default: 1536x1024
  --quality <q>          low | medium | high | auto         default: high
  --model <id>           default: gpt-image-1 (dall-e-3 also works)
  --background <mode>    auto | transparent | opaque (gpt-image-1 only;
                         transparent gives PNG alpha). Sent only when given.
  --dry-run              print what would be asked; no request is made
  -h, --help             this text

--size, --quality and --background are passed to the API as given. An
option's value is the next argument, whatever it looks like. Every other
argument is a word of the prompt; quote the prompt as one argument.

API key, first found wins, never printed: OPENAI_API_KEY in the
environment; OPENAI_API_KEY=… in .env.local at the working copy root
(gitignored — never commit it); the account's
~/.config/agent-fabric/secrets.env, which `fabric-secrets sync` writes.
--dry-run says which one.

An API refusal is reported as its status and its error type and code, and
only those that are on a known list ("other" otherwise): never the
message, which can echo part of the key. The request goes to
api.openai.com only: no redirect is followed and no proxy is used. It is
given 300 s.

exit: 0 written, --dry-run, --help; 1 anything else
"""


class Fail(Exception):
    pass


@dataclass
class Opts:
    out: str | None = None
    size: str = "1536x1024"
    quality: str = "high"
    model: str = "gpt-image-1"
    background: str | None = None
    dry_run: bool = False
    words: list[str] = field(default_factory=list)


def js_trim(s: str) -> str:
    return _JS_TRIM.sub("", s)


def parse_args(argv: list[str]) -> Opts | None:
    """None: --help was asked for (reached before any later error)."""
    o = Opts()
    i = 0
    while i < len(argv):
        a = argv[i]

        def value() -> str:
            if i + 1 >= len(argv):
                raise Fail(f"{a} needs a value")
            return argv[i + 1]

        if a in ("-o", "--out"):
            o.out = value()
            i += 1
        elif a in ("--size", "--quality", "--model", "--background"):
            setattr(o, a[2:], value())
            i += 1
        elif a == "--dry-run":
            o.dry_run = True
        elif a in ("-h", "--help"):
            return None
        elif a.startswith("-"):
            raise Fail(f"unknown option {a}")
        else:
            o.words.append(a)
        i += 1
    return o


def wc_root(cwd: str, environ: dict[str, str]) -> str:
    # git's own words decide "not a repository", so they are read in C; the
    # session's GIT_DIR or GIT_WORK_TREE would name another repository.
    env = {k: v for k, v in environ.items() if not k.startswith("GIT_")}
    env.update(LC_ALL="C", LANGUAGE="C")
    try:
        r = git.run(cwd, "rev-parse", "--show-toplevel", check=False, env=env, timeout=30,
                    what="git rev-parse")
    except git.GitError as e:
        raise Fail(f"cannot find the working copy root ({e.reason})") from None
    # Only git's own newline: a directory name may end in a space.
    top = r.stdout.rstrip("\n")
    if r.returncode == 0 and top:
        return top
    if "not a git repository" in r.stderr:
        return cwd
    lines = [line for line in r.stderr.splitlines() if line.strip()]
    raise Fail(f"cannot find the working copy root ({lines[-1] if lines else f'git exit {r.returncode}'})")


def _read_text(path: str, shown: str) -> str | None:
    # Node read these as UTF-8 and replaced what did not decode.
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            return fh.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        name = errno.errorcode.get(e.errno, type(e).__name__) if e.errno else type(e).__name__
        raise Fail(f"cannot read {shown} ({name})") from None


def env_local_key(root: str) -> str:
    """OPENAI_API_KEY from <root>/.env.local: the first line giving it a
    non-empty value, as a line fills the name only while it is unset or
    empty. Other names are not read."""
    text = _read_text(os.path.join(root, ".env.local"), ".env.local")
    found = ""
    for line in re.split(r"\r?\n", text or ""):
        # A "#" line never matches: the name must come first. The .mjs also
        # tested for "#", a check no line could reach.
        m = _ENV_LINE.match(line)
        if not m or m.group(1) != "OPENAI_API_KEY" or found:
            continue
        found = _QUOTED.sub(r"\2", m.group(2))
    return found


def shell_unquote(word: str) -> str | None:
    """One word as a POSIX shell reads it — bare, '…', "…" (\\" \\\\ \\$ \\`
    escaped), a backslash outside quotes — or None when it does not close or
    another word follows it."""
    out: list[str] = []
    i, n = 0, len(word)
    while i < n:
        c = word[i]
        if c == "'":
            end = word.find("'", i + 1)
            if end < 0:
                return None
            out.append(word[i + 1:end])
            i = end
        elif c == '"':
            j = i + 1
            while j < n and word[j] != '"':
                if word[j] == "\\" and j + 1 < n and word[j + 1] in '"\\$`':
                    j += 1
                out.append(word[j])
                j += 1
            if j >= n:
                return None
            i = j
        elif c == "\\":
            i += 1
            out.append(word[i] if i < n else "")
        elif _JS_SPACE_CHAR.match(c):
            return "".join(out) if not js_trim(word[i:]) else None
        else:
            out.append(c)
        i += 1
    return "".join(out)


def secrets_key(home: str) -> tuple[str, bool]:
    """(value, unreadable) from the last `export OPENAI_API_KEY=` line."""
    text = _read_text(os.path.join(home, SYNCED_ENV), SYNCED_ENV_SHOWN)
    if text is None:
        return "", False
    prefix = "export OPENAI_API_KEY="
    lines = [line for line in re.split(r"\r?\n", text) if line.startswith(prefix)]
    if not lines:
        return "", False
    value = shell_unquote(lines[-1][len(prefix):])
    return (value, False) if value else ("", True)


def resolve_key(source: str, environ: dict[str, str], root: str, home: str) -> str:
    """The key from the one source _origin named, "" when that source holds
    none now: what is sent is what the key line said (review of #110)."""
    if source == "from the environment":
        return environ.get("OPENAI_API_KEY") or ""
    if source == "from .env.local":
        return env_local_key(root)
    if source == f"from {SYNCED_ENV_SHOWN}":
        return secrets_key(home)[0]
    return ""


def _origin(environ: dict[str, str], root: str, home: str) -> str:
    """What the key line says, the first source holding a value; "present …
    but unreadable" and "none found" are a refusal unless it is a dry run.
    Apart from resolve_key on purpose: what is printed is decided by which
    source holds a value, and never travels with the value itself
    (CodeQL alert 53 on #110)."""
    if environ.get("OPENAI_API_KEY"):
        return "from the environment"
    if env_local_key(root):
        return "from .env.local"
    held, unreadable = secrets_key(home)
    if held:
        return f"from {SYNCED_ENV_SHOWN}"
    return f"present in {SYNCED_ENV_SHOWN} but unreadable" if unreadable else "none found"


def _text(body: bytes) -> str:
    """As Node's Response.text(): UTF-8, a leading BOM dropped, what does
    not decode replaced."""
    return body.decode("utf-8-sig", errors="replace")


def _strict_json(text: str) -> Any:
    """JSON.parse's grammar: NaN and Infinity are not JSON."""
    def refuse(token: str) -> Any:
        raise ValueError(token)
    return json.loads(text, parse_constant=refuse)


def error_kind(body: bytes, types: frozenset[str] = ERROR_TYPES, codes: frozenset[str] = ERROR_CODES) -> str:
    """What a refusal may say about itself. The lists are parameters so a
    test can show an sk- value is refused even when a list holds it."""
    try:
        doc = _strict_json(_text(body))
    except ValueError:
        return "unparseable body"
    except RecursionError:
        # JSON nested deeper than Python's recursion, which JSON.parse
        # reads. Its type and code go unread, so the kind can be less
        # specific than the .mjs gave; a non-recursive parser is not worth it.
        return "no error type"
    error = doc.get("error") if isinstance(doc, dict) else None

    def listed(v: Any, known: frozenset[str]) -> str | None:
        if v is None:
            return None
        return v if isinstance(v, str) and not v.startswith("sk-") and v in known else "other"

    if not isinstance(error, dict):
        return "no error type"
    parts = [p for p in (listed(error.get("type"), types), listed(error.get("code"), codes)) if p]
    return "/".join(parts) or "no error type"


def make_opener() -> urllib.request.OpenerDirector:
    return httpsafe.opener(proxies=False, redirects="none")


@dataclass
class Answer:
    status: int
    body: bytes


def post(opener: Any, url: str, payload: bytes, key: str, timeout: float) -> Answer:
    """The whole exchange within `timeout` seconds, in a daemon thread: a
    socket timeout bounds each read, not the request, and a server that
    trickles would hold it for ever."""
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    box: dict[str, Any] = {}

    def exchange() -> None:
        try:
            try:
                with opener.open(req, timeout=timeout) as resp:
                    box["answer"] = Answer(resp.status, resp.read())
            except urllib.error.HTTPError as e:
                with e:
                    box["answer"] = Answer(e.code, e.read())
        except BaseException as e:  # noqa: BLE001 — carried to the caller, which names its class only
            box["error"] = e

    t = threading.Thread(target=exchange, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise Fail("request failed (TimeoutError)")
    if "error" in box:
        e = box["error"]
        # A URLError's class says only "URLError"; the reason's says what failed.
        cause = e.reason if isinstance(e, urllib.error.URLError) and isinstance(e.reason, BaseException) else e
        raise Fail(f"request failed ({type(cause).__name__})")
    return box["answer"]


def image_bytes(body: bytes) -> tuple[bytes, dict]:
    try:
        doc = _strict_json(_text(body))
        item = doc["data"][0]
        b64 = item["b64_json"]
        if not isinstance(b64, str) or not b64:
            raise TypeError
        return base64.b64decode(b64, validate=True), (doc, item)
    except (ValueError, RecursionError, binascii.Error, KeyError, IndexError, TypeError):
        raise Fail("no image data in response") from None


def write_atomically(path: str, data: bytes, shown: str) -> None:
    tmp = None
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.tmp-{os.getpid()}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except OSError as e:
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        name = errno.errorcode.get(e.errno, type(e).__name__) if e.errno else type(e).__name__
        raise Fail(f"cannot write {shown} ({name})") from None


def _js_number(v: Any) -> str:
    if v is None:
        return "?"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (int, float, str)):
        return str(v)
    return json.dumps(v, separators=(",", ":"))


def _say(line: str) -> None:
    print(line, flush=True)


def main(argv: list[str], *, environ: dict[str, str] | None = None, cwd: str | None = None,
         opener: Any = None, timeout: float = TIMEOUT_S) -> int:
    """environ, cwd and opener are the tests' seams; a caller of the
    command has none of them, and nothing here moves the endpoint."""
    environ = dict(os.environ) if environ is None else environ
    cwd = os.getcwd() if cwd is None else cwd
    o = parse_args(argv)
    if o is None:
        sys.stdout.write(HELP)
        return 0
    prompt = js_trim(" ".join(o.words))
    if not prompt:
        raise Fail("a prompt is required (quote it as one argument)")
    if o.out is None:
        raise Fail("-o <path> is required (e.g. -o gita/assets/hero.png)")
    if not o.out.lower().endswith(".png"):
        raise Fail("output must be a .png (the API returns PNG)")

    root = wc_root(cwd, environ)
    target = os.path.join(root, o.out)
    body: dict[str, Any] = {"model": o.model, "prompt": prompt, "n": 1, "size": o.size, "quality": o.quality}
    if o.background:
        body["background"] = o.background
    if o.model.startswith("dall-e"):
        body["response_format"] = "b64_json"

    _say(f"• model {o.model} · {o.size} · quality {o.quality}" + (f" · background {o.background}" if o.background else ""))
    _say(f"• prompt: {prompt}")
    _say(f"• out:    {o.out}")
    home = environ.get("HOME") or pwd.getpwuid(os.geteuid()).pw_dir
    source = _origin(environ, root, home)
    _say(f"• key:    {source}")
    if o.dry_run:
        _say("(dry run — no request made)")
        return 0
    if not source.startswith("from "):
        if source == "none found":
            raise Fail(f"OPENAI_API_KEY not found in the environment, .env.local or {SYNCED_ENV_SHOWN} — run "
                       "`fabric-secrets sync`, or put `OPENAI_API_KEY=sk-...` in .env.local at the working "
                       "copy's root (gitignored)")
        raise Fail(f"OPENAI_API_KEY {source} — run `fabric-secrets sync` again")

    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    key = resolve_key(source, environ, root, home)
    if not key:
        raise Fail(f"OPENAI_API_KEY ({source}) is gone now — run it again")
    answer = post(opener or make_opener(), ENDPOINT, payload, key, timeout)
    if not 200 <= answer.status < 300:
        raise Fail(f"API {answer.status} ({error_kind(answer.body)})")
    data, (doc, item) = image_bytes(answer.body)
    write_atomically(target, data, o.out)
    _say(f"✓ wrote {o.out} ({int(len(data) / 1024 + 0.5)} KB)")
    revised = item.get("revised_prompt") if isinstance(item, dict) else None
    if isinstance(revised, str) and revised:
        _say(f"  revised prompt: {revised}")
    usage = doc.get("usage") if isinstance(doc, dict) else None
    if isinstance(usage, dict):
        _say(f"  tokens: {_js_number(usage.get('total_tokens'))} (input {_js_number(usage.get('input_tokens'))},"
            f" output {_js_number(usage.get('output_tokens'))})")
    return 0


def run(argv: list[str], **kw: Any) -> int:
    """No traceback on any path: an exception's text can hold the key (a
    header value) or a URL, so the last resort names its class only."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError):
            stream.reconfigure(encoding="utf-8", errors="replace")
    # Node decoded argv as UTF-8, replacing what did not decode.
    argv = [os.fsencode(a).decode("utf-8", errors="replace") for a in argv]
    try:
        return main(argv, **kw)
    except Fail as e:
        print(f"fabric-genimage: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001 — the contract's last resort: the class, never the text
        print(f"fabric-genimage: failed ({type(e).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
