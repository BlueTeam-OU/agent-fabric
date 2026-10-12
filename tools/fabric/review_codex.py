#!/usr/bin/env python3
"""tools/fabric/review_codex.py — the second review engine: Codex reviews a
PR's head one-shot, with the review class's brief, through a gateway of its
own (agent-fabric ADR-053 rules 1-5; bin/fabric-review --engine is the front
door).

    fabric-review --engine codex PR REQUEST[.yaml|.json] [--model M] [--timeout MIN]
                  [--allow-rationale] [--no-post]

SETTINGS, from the environment only (the launcher's Codex profile sets them;
until it does, every run refuses, ADR-053 §6):
  AGENT_FABRIC_CODEX_BASE_URL  the ROOT of a gateway process serving
                               openai-responses (http(s)://host:port, no path:
                               Codex posts /responses to the root, ADR-053 §1)
  AGENT_FABRIC_CODEX_KEY       that gateway's local key; it reaches Codex as
                               this variable in Codex's environment, never in
                               a file or an argument
  AGENT_FABRIC_CODEX_MODEL     the model Codex asks the gateway for (--model
                               overrides); a posted review names it
  AGENT_FABRIC_CODEX_BIN       the codex binary (default: `codex` on PATH)
Missing the base URL, the key or the model refuses before anything runs, and
posts nothing.

WHAT RUNS. The brief is review_brief.render() of REQUEST, byte for byte, with
the engine's answer-shape section appended and nothing else (rule 1). The
request must be a ranged one whose head is the PR's current head: the review
is posted against the PR's head, so a request for any other commit would be
counted as a review of something it never read. That head is `git archive`d
into a scratch directory (never the working copy) and `codex exec` runs ONCE
there with --sandbox read-only, a time budget (20 minutes unless --timeout),
CODEX_HOME and HOME inside the scratch, and an environment built from an
allowlist, so no ANTHROPIC_*/CLAUDE_* variable, no OPENAI_API_KEY and no
~/.codex reaches it (rules 2-3). CODEX_HOME holds a config.toml whose
model_providers entry carries the gateway: Codex's built-in OpenAI provider
ignores OPENAI_BASE_URL, so a variable alone would send the review to
api.openai.com. The scratch lives under the account's temporary directory
(TMPDIR), outside every working copy and every home's hidden directories —
the places the review class's bash guard refuses to read — and is removed on
every path: success, refusal, failure, timeout, and SIGTERM/SIGHUP/SIGINT.

WHAT IS POSTED. Codex's last message must be ONE JSON object valid against
runtime/claude-code/review/codex-answer.schema.json (also handed to
--output-schema). Anything else — no message, prose, a fence, two objects, a
finding without a fix — is a failed review: nothing is posted and the reason
is said (rule 4). A valid answer is rendered with the engine and model on its
first line and posted by `fabric-pr post-review PR --model codex` from the
request's repository; --no-post prints it instead. Rule 5 is the reader's:
each finding is judged by the review class before it is answered.

exit 0 posted (or printed); 1 refused or a failed review, nothing posted;
2 usage.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import review_brief  # noqa: E402
from lint_rules.schema import validate_json  # noqa: E402 — the fleet's no-dependency validator (ADR-040)

# The engine's own files, beside this one: the schema is the contract this
# code validates against, and fabric-pr the one this checkout ships, never
# another tree's that AGENT_FABRIC_ROOT may name.
FABRIC_ROOT = os.path.dirname(os.path.dirname(HERE))
SCHEMA_PATH = os.path.join(FABRIC_ROOT, "runtime", "claude-code", "review", "codex-answer.schema.json")
ENGINE = "codex"
DEFAULT_TIMEOUT_MIN = 20.0
PROVIDER_ID = "fabric-gateway"
ENV_BASE_URL, ENV_KEY, ENV_MODEL, ENV_BIN = (
    "AGENT_FABRIC_CODEX_BASE_URL", "AGENT_FABRIC_CODEX_KEY", "AGENT_FABRIC_CODEX_MODEL", "AGENT_FABRIC_CODEX_BIN")
# Codex's environment is built from these and nothing else: a denylist of
# the session's credentials would miss the next one a launcher adds. Locale
# and CA settings only; HOME, TMPDIR and CODEX_HOME are the scratch's.
CHILD_ENV_PASS = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TZ", "TERM", "SSL_CERT_FILE", "SSL_CERT_DIR")
MAX_ANSWER_BYTES = 1 << 20
# The answer-shape section is the only text the engine adds to the brief
# (ADR-053 rule 1): where it stands and what to answer, never anything
# about the change.
ANSWER_SHAPE = """## Answer (the engine's shape, agent-fabric ADR-053 rule 4)
Your working directory is an extract (`git archive`) of the range's head, without history; the
range's history is in the repository named above. Both are read-only for you.
Answer with ONE JSON object and nothing else — no prose, no code fence:
{"findings": [{"level": "P1|P2|P3", "file": "<path from the repository root>", "line": <line at the head, >= 1>,
  "scenario": "<the inputs or state and the steps that make it fail>",
  "expected": "<what must happen instead>", "fix": "<the smallest change that makes it hold>"}]}
P1 breaks a requirement or invariant on a path that runs; P2 is a defect a reachable input or state
triggers; P3 is anything else worth fixing. A finding about code the range did not change is
reported only if the range makes it reachable. No findings: {"findings": []}.
"""


class Refused(Exception):
    """Nothing ran that could post; the message says why."""


class FailedReview(Exception):
    """Codex ran and the review failed; nothing is posted."""


class _Signalled(BaseException):
    """A termination signal, raised so every `finally` below runs."""


# --- settings ----------------------------------------------------------------

def settings(environ: dict[str, str], model_flag: str | None) -> tuple[str, str, str, str]:
    """(base_url, key, model, codex binary), or Refused naming every missing one."""
    base = (environ.get(ENV_BASE_URL) or "").strip()
    key = environ.get(ENV_KEY) or ""
    model = (model_flag or environ.get(ENV_MODEL) or "").strip()
    missing = [n for n, v in ((ENV_BASE_URL, base), (ENV_KEY, key), (ENV_MODEL + " or --model", model)) if not v]
    if missing:
        raise Refused(f"not set: {', '.join(missing)} — the Codex engine runs only through a gateway serving "
                      "openai-responses, with its local key (agent-fabric ADR-053 rule 3); nothing was run or posted")
    parts = urlsplit(base)
    if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password
            or parts.path not in ("", "/") or parts.query or parts.fragment):
        raise Refused(f"{ENV_BASE_URL} must be the root of the gateway (http(s)://host:port), not {base!r}")
    # The session's own Anthropic gateway and credential must never reach
    # Codex (rule 3): the same URL or the same secret given twice is a
    # misconfiguration, not a second gateway.
    session_url = (environ.get("ANTHROPIC_BASE_URL") or "").strip().rstrip("/")
    if session_url and base.rstrip("/") == session_url:
        raise Refused(f"{ENV_BASE_URL} is the session's ANTHROPIC_BASE_URL; Codex needs its own Responses gateway")
    if key in {environ.get(n) or "" for n in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")} - {""}:
        raise Refused(f"{ENV_KEY} is the session's Anthropic credential; Codex takes its gateway's local key")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", model):
        raise Refused(f"model {model!r} is not a model name")
    binary = environ.get(ENV_BIN) or shutil.which("codex", path=environ.get("PATH")) or ""
    if not binary or not os.access(binary, os.X_OK):
        raise Refused(f"no codex binary ({ENV_BIN}, or `codex` on PATH); nothing was run or posted")
    return base.rstrip("/"), key, model, binary


# --- the request and the head ------------------------------------------------

def _git(repo: str, *args: str) -> str:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise Refused(f"git {' '.join(args)} in {repo}: {r.stderr.strip() or 'failed'}")
    return r.stdout.strip()


def load_request(path: str, allow_rationale: bool) -> tuple[dict, str]:
    """The request and its rendered brief, unchanged (rule 1)."""
    with open(path, encoding="utf-8") as f:
        req = review_brief.parse_request(f.read())
    brief = review_brief.render(req, allow_rationale=allow_rationale)
    if not req.get("range"):
        raise Refused("the Codex engine reviews a pushed head: the request needs a range, not a diff file")
    return req, brief


def range_head(req: dict) -> str:
    head = req["range"].split("..", 1)[1]
    return _git(req["repository"], "rev-parse", "--verify", "-q", f"{head}^{{commit}}")


def pr_head(repo: str, pr: str) -> str:
    """The PR's head commit as GitHub has it now; post-review pins the review there."""
    r = subprocess.run(["gh", "pr", "view", pr, "--json", "headRefOid,state"], cwd=repo, capture_output=True,
                       text=True, timeout=60, stdin=subprocess.DEVNULL)
    try:
        oid = json.loads(r.stdout).get("headRefOid") if r.returncode == 0 else None
    except (ValueError, AttributeError):
        oid = None
    if not isinstance(oid, str) or not re.fullmatch(r"[0-9a-f]{40}", oid):
        raise Refused(f"could not read the head of PR #{pr}: {r.stderr.strip() or r.stdout.strip()[:200]}")
    return oid


# --- the scratch -------------------------------------------------------------

def scratch_root(repo: str, environ: dict[str, str]) -> str:
    """The account's temporary directory, refused if it lies inside the
    working copy (rule 2) or a home's hidden directory, where the review
    class's guard would refuse to read it."""
    root = os.path.realpath(tempfile.gettempdir())
    top = os.path.realpath(repo)
    home = os.path.realpath(environ.get("HOME") or os.path.expanduser("~"))
    inside = lambda p, d: p == d or p.startswith(d.rstrip("/") + "/")  # noqa: E731
    hidden = inside(root, home) and any(part.startswith(".") for part in os.path.relpath(root, home).split("/"))
    if inside(root, top) or hidden or root == home:
        raise Refused(f"the temporary directory {root} is inside the working copy or a home's hidden directory; "
                      "point TMPDIR elsewhere")
    return root


def extract(repo: str, commit: str, dest: str) -> None:
    """`git archive` of the commit into dest; the working copy is only read."""
    os.makedirs(dest, mode=0o700)
    p = subprocess.Popen(["git", "-C", repo, "archive", "--format=tar", commit], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=p.stdout, mode="r|") as tar:
            tar.extractall(dest, filter="data")
    finally:
        p.stdout.close()
        err = p.stderr.read().decode("utf-8", "replace")
        p.stderr.close()
        rc = p.wait(timeout=60)
    if rc != 0:
        raise Refused(f"git archive {commit[:12]} failed: {err.strip()}")


def _toml_str(s: str) -> str:
    return json.dumps(s)  # a JSON string is a valid TOML basic string for what is written here


def codex_home(scratch: str, base_url: str) -> str:
    """An isolated CODEX_HOME: the gateway as the one provider, the key read
    from ENV_KEY in Codex's environment, nothing persisted that outlives it."""
    home = os.path.join(scratch, "codex-home")
    os.makedirs(home, mode=0o700)
    with open(os.path.join(home, "config.toml"), "w", encoding="utf-8") as f:
        f.write(f"model_provider = {_toml_str(PROVIDER_ID)}\n"
                'approval_policy = "never"\nsandbox_mode = "read-only"\n\n'
                '[history]\npersistence = "none"\n\n'
                f"[model_providers.{PROVIDER_ID}]\n"
                f'name = "agent-fabric gateway (openai-responses)"\n'
                f"base_url = {_toml_str(base_url)}\n"
                'wire_api = "responses"\n'
                f"env_key = {_toml_str(ENV_KEY)}\n")
    return home


def child_env(environ: dict[str, str], scratch: str, home: str, key: str) -> dict[str, str]:
    env = {k: environ[k] for k in CHILD_ENV_PASS if environ.get(k)}
    for d in ("home", "tmp"):
        os.makedirs(os.path.join(scratch, d), mode=0o700, exist_ok=True)
    env.update(HOME=os.path.join(scratch, "home"), TMPDIR=os.path.join(scratch, "tmp"), CODEX_HOME=home,
               NO_COLOR="1", **{ENV_KEY: key})
    assert not any(k.startswith(("ANTHROPIC_", "CLAUDE", "OPENAI_")) for k in env), "a session credential in Codex's env"
    return env


# --- running Codex once ------------------------------------------------------

def run_codex(binary: str, model: str, workdir: str, scratch: str, env: dict[str, str], prompt: str,
              timeout_s: float) -> str:
    """Codex's last message, or FailedReview. Its process group is ended on
    every way out, so nothing it started outlives the scratch."""
    answer = os.path.join(scratch, "last-message.json")
    log = os.path.join(scratch, "codex.log")
    argv = [binary, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--cd", workdir, "--model", model,
            "--output-schema", SCHEMA_PATH, "--output-last-message", answer, "--color", "never", "-"]
    with open(log, "wb") as logf:
        p = subprocess.Popen(argv, cwd=workdir, env=env, stdin=subprocess.PIPE, stdout=logf, stderr=subprocess.STDOUT,
                             start_new_session=True)
        try:
            try:
                p.communicate(prompt.encode("utf-8"), timeout=timeout_s)
            except subprocess.TimeoutExpired:
                raise FailedReview(f"codex did not answer within {timeout_s / 60:g} minutes") from None
        finally:
            if p.poll() is None or _group_alive(p.pid):
                _end_group(p)
    if p.returncode != 0:
        raise FailedReview(f"codex exited {p.returncode}: {_tail(log)}")
    if not os.path.isfile(answer):
        raise FailedReview(f"codex wrote no answer: {_tail(log)}")
    with open(answer, "rb") as f:
        raw = f.read(MAX_ANSWER_BYTES + 1)
    if len(raw) > MAX_ANSWER_BYTES:
        raise FailedReview(f"the answer is over {MAX_ANSWER_BYTES} bytes")
    return raw.decode("utf-8", "replace")


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _end_group(p: subprocess.Popen) -> None:
    for sig, wait in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            break
        try:
            p.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            continue
        if not _group_alive(p.pid):
            break


def _tail(path: str, limit: int = 1500) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return "(no output)"
    text = text.strip()
    return ("…" + text[-limit:]) if len(text) > limit else (text or "(no output)")


# --- the answer --------------------------------------------------------------

def parse_answer(text: str) -> list[dict]:
    """The findings of ONE JSON object valid against the schema, or FailedReview."""
    def no_duplicates(pairs):
        out: dict = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f"key {k!r} given twice")
            out[k] = v
        return out

    def no_constant(name):
        raise ValueError(f"{name} is not JSON")

    try:
        doc = json.loads(text.strip(), object_pairs_hook=no_duplicates, parse_constant=no_constant)
    except ValueError as e:
        raise FailedReview(f"the answer is not one JSON object ({e})") from None
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    problems = validate_json(schema, doc, "answer")
    if problems:
        raise FailedReview("the answer does not match codex-answer.schema.json: " + "; ".join(problems[:10]))
    for i, finding in enumerate(doc["findings"]):
        file = finding["file"].strip()
        if file.startswith("/") or ".." in file.split("/"):
            raise FailedReview(f"answer/findings[{i}]/file: {file!r} is not a path inside the repository")
    return doc["findings"]


def _one_line(s: str) -> str:
    return " ".join(s.split())


def render_review(model: str, head: str, rng: str, findings: list[dict]) -> str:
    """The body post-review gets. Its first line names the engine and model
    (rule 4); post-review puts its marker above it."""
    order = {"P1": 0, "P2": 1, "P3": 2}
    counts = {lv: sum(f["level"] == lv for f in findings) for lv in order}
    out = [f"**Engine:** Codex · **model:** `{model}` — the second review engine (agent-fabric ADR-053), "
           f"head `{head[:12]}`, range `{rng}`.",
           "",
           "Each finding is judged by the review class before it is answered (ADR-053 rule 5).",
           ""]
    if not findings:
        out.append("No findings.")
    else:
        out.append("Findings: " + ", ".join(f"{counts[lv]} {lv}" for lv in order if counts[lv]) + ".")
        out.append("")
        for n, f in enumerate(sorted(findings, key=lambda f: order[f["level"]]), 1):
            out += [f"{n}. **{f['level']}** `{_one_line(f['file'])}:{f['line']}`",
                    f"   - **Scenario:** {_one_line(f['scenario'])}",
                    f"   - **Expected:** {_one_line(f['expected'])}",
                    f"   - **Fix:** {_one_line(f['fix'])}"]
    return "\n".join(out) + "\n"


def post(repo: str, pr: str, body: str) -> int:
    r = subprocess.run([os.path.join(FABRIC_ROOT, "bin", "fabric-pr"), "post-review", pr, "--model", ENGINE],
                       cwd=repo, input=body, text=True, timeout=180)
    return r.returncode


# --- the run -----------------------------------------------------------------

def review(pr: str, request: str, *, model_flag: str | None, timeout_min: float, allow_rationale: bool,
           no_post: bool, environ: dict[str, str]) -> int:
    base_url, key, model, binary = settings(environ, model_flag)
    req, brief = load_request(request, allow_rationale)
    repo = req["repository"]
    head = range_head(req)
    if pr_head(repo, pr) != head:
        raise Refused(f"the request's head {head[:12]} is not PR #{pr}'s head: a review is posted against the PR's "
                      "head, so it must be the one read (update the request's range)")
    scratch = tempfile.mkdtemp(prefix="fabric-review-codex.", dir=scratch_root(repo, environ))
    try:
        workdir = os.path.join(scratch, "head")
        extract(repo, head, workdir)
        env = child_env(environ, scratch, codex_home(scratch, base_url), key)
        prompt = brief.rstrip("\n") + "\n" + ANSWER_SHAPE
        findings = parse_answer(run_codex(binary, model, workdir, scratch, env, prompt, timeout_min * 60))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if not no_post and pr_head(repo, pr) != head:
        raise Refused(f"PR #{pr} moved while Codex read {head[:12]}; nothing posted — run it on the new head")
    body = render_review(model, head, req["range"], findings)
    if no_post:
        sys.stdout.write(body)
        return 0
    return 0 if post(repo, pr, body) == 0 else 1


def _raise_signal(signum, _frame):
    raise _Signalled(signum)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    usage = ("usage: fabric-review --engine codex PR REQUEST [--model M] [--timeout MINUTES] "
             "[--allow-rationale] [--no-post]")
    if args[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    if not args or args[0] != ENGINE:
        print(f"fabric-review: --engine {args[0] if args else '(none)'}: the engines are: {ENGINE}\n{usage}",
              file=sys.stderr)
        return 2
    args = args[1:]
    opts: dict[str, str] = {}
    flags = {"--allow-rationale": False, "--no-post": False}
    pos: list[str] = []
    while args:
        a = args.pop(0)
        if a in ("--model", "--timeout"):
            if not args:
                print(f"fabric-review: {a} needs a value\n{usage}", file=sys.stderr)
                return 2
            opts[a] = args.pop(0)
        elif a in flags:
            flags[a] = True
        elif a.startswith("-"):
            print(f"fabric-review: unknown option {a}\n{usage}", file=sys.stderr)
            return 2
        else:
            pos.append(a)
    if len(pos) != 2 or not re.fullmatch(r"[1-9][0-9]*", pos[0]):
        print(usage, file=sys.stderr)
        return 2
    try:
        timeout_min = float(opts.get("--timeout", DEFAULT_TIMEOUT_MIN))
    except ValueError:
        timeout_min = -1
    if not 0 < timeout_min <= 24 * 60:
        print(f"fabric-review: --timeout {opts.get('--timeout')!r} is not a number of minutes", file=sys.stderr)
        return 2
    for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(s, _raise_signal)
    try:
        return review(pos[0], pos[1], model_flag=opts.get("--model"), timeout_min=timeout_min,
                      allow_rationale=flags["--allow-rationale"], no_post=flags["--no-post"],
                      environ=dict(os.environ))
    except Refused as e:
        print(f"fabric-review: refused: {e}", file=sys.stderr)
        return 1
    except FailedReview as e:
        print(f"fabric-review: the Codex review failed, nothing posted: {e}", file=sys.stderr)
        return 1
    except review_brief.RequestError as e:
        print("fabric-review: the request does not render:\n  " + "\n  ".join(e.problems), file=sys.stderr)
        return 1
    except _Signalled as e:
        print(f"fabric-review: stopped by signal {e.args[0]}; the scratch is removed, nothing posted", file=sys.stderr)
        return 128 + int(e.args[0])
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as e:
        print(f"fabric-review: {e}; nothing posted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
