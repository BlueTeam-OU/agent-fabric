#!/usr/bin/env python3
"""tools/fabric/review_codex.py — the second review engine: Codex reviews a
PR's head one-shot, with the review class's brief, through a gateway of its
own (agent-fabric ADR-053 rules 1-5; bin/fabric-review --engine is the front
door).

    fabric-review --engine codex PR REQUEST[.yaml|.json] [--gateway chatgpt [--codex-home DIR]]
                  [--model M] [--effort LEVEL] [--timeout MIN] [--allow-rationale] [--no-post]

THE MODEL AND ITS LEVEL come from routing (agent-fabric ADR-005, ADR-006):
the openai column's code-review in routing/capabilities.json — gpt-6.1-sol,
the owner's decision of 2026-10-12 — merged with this login's layers as
`fabric-model list` shows them (routing/profiles.json, the local layer
bin/fabric-model writes), and admitted by routing/policies/review-grade.json;
its level from routing/effort.json (high on openai, chosen by the owner the
same day), fitted to the model by tools/fabric/routing.py's openai adapter
and spelled `-c model_reasoning_effort="<level>"`. --model or
AGENT_FABRIC_CODEX_MODEL names another model for one run, --effort or
AGENT_FABRIC_CODEX_EFFORT another level; routing is read only for what they
leave unnamed, and a routing answer that cannot be read (no openai column, a
malformed layer, a model outside the review grade) refuses, saying why,
before anything runs. The routed level is sent on --gateway chatgpt, the
backend the openai column was decided for; the environment's gateway, whose
backend the fabric does not know, gets a level only when one is asked for
(review of #224, F2).

THE GATEWAY, one of two ways. With --gateway chatgpt, review_gateway.py
starts one for this review from the ChatGPT sign-in in DIR (default
~/.codex-chatgpt), provides the two settings below and the account id, and
stops it before anything is posted; every refusal of its (the sign-in, a
token with too little life left, a gateway without plan schema 1 or the
openai-responses protocol) comes before it starts. Without --gateway, the
settings come from the environment:
  AGENT_FABRIC_CODEX_BASE_URL  the ROOT of a gateway process serving
                               openai-responses (http(s)://host:port, no path:
                               Codex posts /responses to the root, ADR-053 §1)
  AGENT_FABRIC_CODEX_KEY       that gateway's local key; it reaches Codex as
                               this variable in Codex's environment, never in
                               a file or an argument
  AGENT_FABRIC_CODEX_MODEL     optional: a model for this run instead of the
                               routed one (--model overrides it); a posted
                               review names whichever ran
  AGENT_FABRIC_CODEX_BIN       the codex binary (default: `codex` on PATH)
  AGENT_FABRIC_CODEX_ACCOUNT_ID  optional: a ChatGPT account id (a UUID),
                               sent by Codex as the provider's
                               ChatGPT-Account-ID header (config.toml's
                               http_headers); the ChatGPT backend needs it
                               beside the token, and it is no secret
  AGENT_FABRIC_CODEX_EFFORT    optional: Codex's model_reasoning_effort for
                               this run (--effort overrides it): none,
                               minimal, low, medium, high or xhigh, passed
                               as -c; without it, routing's level on
                               --gateway chatgpt and none here
Missing the base URL or the key refuses before anything runs, and posts
nothing.

WHAT RUNS. The brief is review_brief.render() of REQUEST, byte for byte, with
the engine's answer-shape section appended and nothing else (rule 1). The
request must be a ranged one whose head is the PR's current head: the review
is posted against the PR's head, so a request for any other commit would be
counted as a review of something it never read. That head is `git archive`d
into a scratch directory (never the working copy) and `codex exec` runs there
once per attempt (an attempt is repeated only when the model is at capacity,
below) with --sandbox read-only, a time budget for each run (20 minutes unless
--timeout; it is not a total: see below), CODEX_HOME and HOME inside the
scratch, and an environment built from an allowlist, so no ANTHROPIC_*/CLAUDE_*
variable, no OPENAI_API_KEY and no ~/.codex reaches it (rules 2-3). CODEX_HOME holds a config.toml whose
model_providers entry carries the gateway: Codex's built-in OpenAI provider
ignores OPENAI_BASE_URL, so a variable alone would send the review to
api.openai.com. The scratch lives under the account's temporary directory
(TMPDIR), outside every working copy and every home's hidden directories —
the places the review class's bash guard refuses to read — and is removed on
every path: success, refusal, failure, timeout, and SIGTERM/SIGHUP/SIGINT.

WHAT THE RUN MUST SHOW. Codex runs with --json, its stdout the JSONL event
stream (its own log lines on stderr, kept apart), and the run is a failed
review unless that stream shows it read the code: no `error` item (the
missing tool host, codex-code-mode-host, is named as such), no failed turn,
at least one command_execution that completed with exit code 0, and a final
agent message. A Codex installed without its tool host ran no command and
answered {"findings": []} from the brief alone, which was posted as a clean
review (2026-10-12); a run that read nothing is never posted.

WHAT IS POSTED. Codex's last message must be ONE JSON object valid against
runtime/claude-code/review/codex-answer.schema.json (also handed to
--output-schema). Anything else — no message, prose, a fence, two objects, a
finding without a fix — is a failed review: nothing is posted and the reason
is said (rule 4). A valid answer is rendered with the engine, the model and the level sent on
its first line and posted by `fabric-pr post-review PR --model codex` from the
request's repository; --no-post prints it instead. Rule 5 is the reader's:
each finding is judged by the review class before it is answered.

WHEN THE MODEL IS UNAVAILABLE. A failed turn whose own message says the chosen
model is at capacity ("Selected model is at capacity", the provider's, and
transient) is run again — a fresh scratch, gateway and sandbox proof each time —
after 10 s, then 20 s, then 60 s, and then stops. A failed turn whose message
says the allowance is spent (Codex's "You've hit your usage limit…", "Quota
exceeded", a workspace out of credits or at its spend cap: ours, until the
window resets) is NOT retried, because a wait of a minute cannot end it: it is
reported at once, with the reset time when the message gives one. Both end in
exit 3 and say which kind; any other failed turn stays a failed review, exit 1,
never retried. The messages are the strings of the pinned Codex 0.162.1
binary (tests/test_review_codex.py pins them); a message that matches none of
them is not guessed at. No review is posted on any of these. --timeout is each
run's budget, so a capacity spell can take up to four of them plus the 90 s of
waits.

Codex is an additional review, never a blocking one (the owner, 2026-10-13):
when the model is unavailable the claude review alone arms, and the arm needs
a fact on the PR to read. So an unavailable model (exit 3, either kind) posts,
once per head, a COMMENT review of that commit whose first line is UNAVAILABLE_MARKER's
(format_marker; verdicts.unavailable_of, the arm's reader, is the one parser) and one
human line. It is not posted when a Codex review of that head already stands
on the PR or an unavailable statement for it does, and never on any other
failure: a crash is no statement about availability. When the PR cannot be
read to check that, nothing is posted and a warning says so (unknown stays
unknown); two runs racing on one head can both post, and the arm reads the
first. With --no-post the comment is printed to stdout instead, unchecked.

THE LEDGER. A run that started Codex appends one row (v1, tools/fabric/ledger.py) to
<state>/agents/<login>/ledger.jsonl, the file the SubagentStop hook appends the Claude rows to, whatever
became of the run and before the scratch is gone: token counts from the events' turn.completed usage (a
review costs what a failed or refused one costs too), summed over the capacity retries, and the wall time
of the runs, waits excluded. Counts are the account's meter, not a bill: Codex's input_tokens is taken to
include the cached and the cache-write tokens (the Responses API's usage), so input is the remainder;
that is the API's documented shape, not measured against the live backend. turns and first_turn_context are
unknown (null): the events report a turn's total, not its API calls. The status says what became of the
run: completed, failed, timeout, cancelled (a signal), or allowance-exhausted, the over-allowance model
apart from every other failure (the owner's refinement, 2026-10-14); a model at capacity after its retries
is `failed`, status_source codex:capacity. A refusal before Codex started writes no row. The row never
holds the brief, the answer or any message text. A ledger that cannot be written warns on stderr and
changes neither the review nor the exit status: a measurement never stands in a review's way.

exit 0 posted (or printed); 1 refused or a failed review, nothing posted;
2 usage; 3 the model is unavailable (at capacity after the retries, or over
the allowance), no review posted, the unavailable review above.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gh  # noqa: E402
import ledger  # noqa: E402
import review_brief  # noqa: E402
import review_gateway  # noqa: E402
import routing  # noqa: E402
from github.review_status.base import Die  # noqa: E402
from github.review_status.config import read_config  # noqa: E402
from github.review_status.verdicts import classify, engine_of, unavailable_of  # noqa: E402
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
ENV_ACCOUNT_ID, ENV_EFFORT = "AGENT_FABRIC_CODEX_ACCOUNT_ID", "AGENT_FABRIC_CODEX_EFFORT"
# The ChatGPT account id is a UUID; the shape is checked because it is written into config.toml as a header value.
ACCOUNT_ID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
# Codex's model_reasoning_effort values (codex 0.162.1), what --effort and AGENT_FABRIC_CODEX_EFFORT may name. What
# is sent when neither names one is routing's (routing/effort.json, providers.openai), on --gateway chatgpt only:
# the environment's gateway sends no level unless one is asked for, as before the --gateway path existed (review
# of #224, F2).
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")
# The class the engine runs and the routing column it reads (routing/capabilities.json providers.openai).
CAPABILITY, PROVIDER = "code-review", "openai"
# Codex's environment is built from these and nothing else: a denylist of
# the session's credentials would miss the next one a launcher adds. Locale
# and CA settings only; HOME, TMPDIR and CODEX_HOME are the scratch's.
CHILD_ENV_PASS = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "TZ", "TERM", "SSL_CERT_FILE", "SSL_CERT_DIR")
MAX_ANSWER_BYTES = 1 << 20
# Codex's own egress, outside the gateway: with the plugin feature on a run executes `git ls-remote` and `git fetch` of a GitHub plugin
# repository and opens other connections (strace, codex 0.162.1, a local gateway: 11 git executions and 7 non-loopback connects in 30 s).
# `plugins = false` alone ended all of it in that trial (no git, loopback only); the other features that reach out are switched off
# beside it, so a later version that moves the fetch to one of them does not reopen it. A feature a version does not know is ignored.
EGRESS_FEATURES = ("plugins", "remote_plugin", "plugin_sharing", "apps", "in_app_updates")
SANDBOX_PROOF_TIMEOUT_S = 60
EXIT_UNAVAILABLE = 3
CAPACITY, ALLOWANCE = "capacity", "allowance"
# The fact the arm reads (the owner's policy of 2026-10-13: Codex never blocks). One line, fixed fields, no free text:
# the backend's words stay in the human line below it.
UNAVAILABLE_MARKER = "<!-- agent-fabric-engine-unavailable v1 engine={engine} head={head} reason={reason} at={at} -->"
# The waits before the first, second and third retry of a run whose model was at capacity, then stop (the owner,
# 2026-10-13). Time is an input: tests replace both of these.
CAPACITY_RETRY_DELAYS_S = (10, 20, 60)
_sleep = time.sleep
# What Codex 0.162.1 puts in a failed turn's message when the model cannot be had, read from its binary. The
# apostrophe in "You’ve" is U+2019. Anything not listed is an ordinary failed turn, never retried.
CAPACITY_MESSAGES = ("Selected model is at capacity",)
ALLOWANCE_MESSAGES = ("You\u2019ve hit your usage limit", "Quota exceeded", "Your workspace is out of credits",
                      "You hit your spend cap")
RESET_TIME = re.compile(r"[Tt]ry again at ([^.\n]{1,60})")
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


class RunTimeout(FailedReview):
    """Codex did not answer within the run's budget (the ledger's status `timeout`)."""


class ModelUnavailable(FailedReview):
    """The turn failed because the chosen model cannot be had: kind CAPACITY (the provider's, transient) or
    ALLOWANCE (ours, until its window resets). A caller tells it from a defect by its own exit status."""

    def __init__(self, kind: str, backend: str, reset: str | None = None) -> None:
        super().__init__(backend)
        self.kind, self.backend, self.reset = kind, backend, reset
        self.runs = 1

    def report(self) -> str:
        runs = self.runs
        if self.kind == CAPACITY:
            return (f"the Codex model is unavailable: at capacity, the provider's and transient (after {runs} run(s), "
                    f"retried after {', '.join(f'{d:g}' for d in CAPACITY_RETRY_DELAYS_S)} s) — Codex said: {self.backend}")
        when = f"it resets {self.reset}" if self.reset else "the backend gave no reset time"
        return (f"the Codex model is unavailable: over the allowance, ours, until its window resets ({when}); "
                f"not retried — Codex said: {self.backend}")


class _Signalled(BaseException):
    """A termination signal, raised so every `finally` below runs."""


# --- settings ----------------------------------------------------------------

def settings(environ: dict[str, str]) -> tuple[str, str]:
    """(base_url, key) of the environment's gateway, or Refused naming every missing one."""
    return gateway_settings(environ)


def gateway_settings(environ: dict[str, str]) -> tuple[str, str]:
    """(base_url, key) of the gateway, checked: its root, and neither the session's URL nor its credential."""
    base = (environ.get(ENV_BASE_URL) or "").strip()
    key = environ.get(ENV_KEY) or ""
    missing = [n for n, v in ((ENV_BASE_URL, base), (ENV_KEY, key)) if not v]
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
    return base.rstrip("/"), key


class Route:
    """This login's routing for the engine: code-review on openai, merged with its layers, as `fabric-model list`
    resolves it. Read only when an override leaves something unnamed; Refused when it cannot be read."""

    def __init__(self) -> None:
        why = "the routing answer for code-review on openai cannot be read"
        try:
            identity = _identity()
            self.agent = identity.current_agent()
            self.role = identity.read_binding(self.agent).get("role")
            # The local layer's path from the identity beside this file, never another tree's: routing's own
            # local_override_path loads runtime/identity.py from the routing root, which a test may point elsewhere.
            self.local = routing.load_local(path=os.path.join(identity.agent_state_dir(self.agent),
                                                              routing.LOCAL_OVERRIDE))
            self.resolved = routing.resolve(CAPABILITY, PROVIDER, self.role, self.agent, self.local)
        except (KeyError, ValueError, OSError) as e:
            raise Refused(f"{why}: {e.args[0] if isinstance(e, KeyError) and e.args else e} — or name the model "
                          f"and the level for this run (--model or {ENV_MODEL}, --effort or {ENV_EFFORT}); nothing "
                          "was run or posted") from None
        except SystemExit as e:  # runtime/identity.py refuses a broken binding by exiting
            raise Refused(f"{why}: {e} — nothing was run or posted") from None

    def model(self) -> str:
        """The routed model, when it is the one that runs. The review grade gates it as the launcher gates the
        review class's (routing/policies/review-grade.json): a layer is where an unreviewed model would otherwise
        arrive. An explicit --model is the operator's own for one run, names itself on the posted review, and is
        not gated — nor refused for a routed model it replaces."""
        model = self.resolved["model"]
        if not routing.review_grade_ok(model, provider=PROVIDER):
            raise Refused(f"the routing answer for {CAPABILITY} on {PROVIDER} is {model!r} (from "
                          f"{self.resolved['source']}), which routing/policies/review-grade.json does not admit; "
                          "nothing was run or posted")
        return model

    def effort(self, model: str) -> str | None:
        """Routing's level for `model` — the routed one, or an override, fitted by the openai adapter — or None
        when it knows of none to send."""
        try:
            e = routing.effort_for(CAPABILITY, PROVIDER, model, self.role, self.agent, self.local)
        except (KeyError, ValueError) as err:
            raise Refused(f"the routed reasoning level cannot be read: {err}; nothing was run or posted") from None
        return e.get("level")


def _identity():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def codex_settings(environ: dict[str, str], model_flag: str | None, route: Route | None = None) -> tuple[str, str]:
    """(model, codex binary): what Codex is asked for and what runs it, both needed before any gateway starts. The
    model is --model, else AGENT_FABRIC_CODEX_MODEL, else routing's (`route`, read here if not given)."""
    model = (model_flag or environ.get(ENV_MODEL) or "").strip()
    if not model:
        model = (route or Route()).model()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", model):
        raise Refused(f"model {model!r} is not a model name")
    binary = environ.get(ENV_BIN) or shutil.which("codex", path=environ.get("PATH")) or ""
    if not binary or not os.access(binary, os.X_OK):
        raise Refused(f"no codex binary ({ENV_BIN}, or `codex` on PATH); nothing was run or posted")
    return model, binary


def account_id(environ: dict[str, str]) -> str | None:
    """AGENT_FABRIC_CODEX_ACCOUNT_ID, UUID-shaped, or None when unset or empty."""
    value = (environ.get(ENV_ACCOUNT_ID) or "").strip()
    if not value:
        return None
    if not ACCOUNT_ID.fullmatch(value):
        raise Refused(f"{ENV_ACCOUNT_ID} is not an account id (a UUID); nothing was run or posted")
    return value


def effort(environ: dict[str, str], flag: str | None, routed: str | None) -> str | None:
    """--effort, else AGENT_FABRIC_CODEX_EFFORT, else `routed` (None: Codex's own); one of Codex's levels."""
    value = flag or environ.get(ENV_EFFORT) or routed
    if value is None:
        return None
    value = value.strip()
    if value not in EFFORTS:
        raise Refused(f"reasoning effort {value!r} is not one of {', '.join(EFFORTS)}")
    return value


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


def codex_home(scratch: str, base_url: str, account: str | None = None) -> str:
    """An isolated CODEX_HOME: the gateway as the one provider, the key read
    from ENV_KEY in Codex's environment, nothing persisted that outlives it.
    With an account id, the provider sends it as ChatGPT-Account-ID on every
    request: the ChatGPT backend needs it beside the bearer token, the gateway
    passes it through (it strips only credential carriers), and it is not a
    secret, so a static header is where it belongs."""
    home = os.path.join(scratch, "codex-home")
    os.makedirs(home, mode=0o700)
    headers = f"http_headers = {{ {_toml_str('ChatGPT-Account-ID')} = {_toml_str(account)} }}\n" if account else ""
    with open(os.path.join(home, "config.toml"), "w", encoding="utf-8") as f:
        f.write(f"model_provider = {_toml_str(PROVIDER_ID)}\n"
                'approval_policy = "never"\nsandbox_mode = "read-only"\n\n'
                '[history]\npersistence = "none"\n\n'
                "[features]\n" + "".join(f"{name} = false\n" for name in EGRESS_FEATURES) + "\n"
                f"[model_providers.{PROVIDER_ID}]\n"
                f'name = "agent-fabric gateway (openai-responses)"\n'
                f"base_url = {_toml_str(base_url)}\n"
                'wire_api = "responses"\n'
                f"env_key = {_toml_str(ENV_KEY)}\n"
                + headers)
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

START_PROBE_EXIT, REFUSED_PROBE_EXIT, WRITTEN_PROBE_EXIT = 42, 43, 7


def prove_sandbox(binary: str, workdir: str, env: dict[str, str]) -> None:
    """The read-only sandbox must start and must refuse a write, or the review does not run. Codex's sandbox is bubblewrap, which needs
    unprivileged user namespaces; a host that refuses them (CI's Ubuntu 24.04) fails the review with one line and runs nothing wider:
    no fallback to a sandbox that writes or to none, and nothing in this module names one (ADR-053 rule 2).

    Each probe answers with an exit status of its own, which the sandbox hands back from the command it ran: a sandbox that exits 0
    without running anything proves nothing (the start probe wants START_PROBE_EXIT, the write probe REFUSED_PROBE_EXIT, and
    WRITTEN_PROBE_EXIT says the write happened). The write is tried at a path of a fresh random name in the extract, which the pull
    request controls: a fixed name could be planted (a file, a dangling link, a link to /dev/null) to make a sound sandbox look broken.
    A probe that outlives SANDBOX_PROOF_TIMEOUT_S is ended with its whole process group, as run_codex ends Codex."""
    probe = os.path.join(workdir, f".fabric-write-probe-{secrets.token_hex(8)}")
    for label, command, wanted in (
            ("start", ["/bin/sh", "-c", f"exit {START_PROBE_EXIT}"], START_PROBE_EXIT),
            ("refuse a write", ["/bin/sh", "-c", f'touch "$1" 2>/dev/null && exit {WRITTEN_PROBE_EXIT}; exit {REFUSED_PROBE_EXIT}', "sh", probe],
             REFUSED_PROBE_EXIT)):
        argv = [binary, "sandbox", "-P", ":read-only", "-C", workdir, "--", *command]
        p = subprocess.Popen(argv, env=env, cwd=workdir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=True)
        try:
            try:
                _, err = p.communicate(timeout=SANDBOX_PROOF_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                raise FailedReview(f"the read-only sandbox did not {label} within {SANDBOX_PROOF_TIMEOUT_S} s; no wider one is used") from None
        finally:
            if p.poll() is None or _group_alive(p.pid):
                _end_group(p)
        if p.returncode != wanted:
            why = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", err.decode("utf-8", "replace").replace(env.get(ENV_KEY, "\0"), "[key]"))[-200:].strip()
            if p.returncode == WRITTEN_PROBE_EXIT and label == "refuse a write":
                raise FailedReview("the read-only sandbox cannot refuse a write (exit 7); no wider one is used")
            ran = "ran nothing it was asked" if p.returncode == 0 else f"exit {p.returncode}"
            raise FailedReview(f"the read-only sandbox cannot {label} ({ran}: {why}); no wider one is used")
    if os.path.lexists(probe):
        raise FailedReview("the sandbox let a write through; no review is run in a writable tree")


class Observed:
    """What the ledger row is made of: each run's events, in order, with the wall time it took."""

    def __init__(self) -> None:
        self.runs: list[CodexRun] = []
        self.started_at: str | None = None   # the first run's start, UTC
        self.seconds = 0.0
        self.status: tuple[str, str] | None = None   # (status, status_source) of the run's end
        self.facts: dict = {}                          # ledger_row's keyword arguments that the review knows


    def add(self, run: CodexRun, started_at: str, seconds: float) -> None:
        self.runs.append(run)
        self.started_at = self.started_at or started_at
        self.seconds += seconds


def run_codex(binary: str, model: str, workdir: str, scratch: str, env: dict[str, str], prompt: str,
              timeout_s: float, effort_level: str | None = None, observed: Observed | None = None) -> str:
    """The run, and its events handed to `observed` on every way out, the
    failed ones included: what a failed review cost is what the ledger is for."""
    started_at, t0 = _utc_now(), time.monotonic()
    try:
        return _run_codex(binary, model, workdir, scratch, env, prompt, timeout_s, effort_level)
    finally:
        if observed is not None:
            observed.add(read_events(os.path.join(scratch, "codex-events.jsonl")), started_at, time.monotonic() - t0)


def _run_codex(binary: str, model: str, workdir: str, scratch: str, env: dict[str, str], prompt: str,
               timeout_s: float, effort_level: str | None) -> str:
    """Codex's last message, or FailedReview: also when its event stream
    shows it read nothing (read_events). Its process group is ended on every
    way out, so nothing it started outlives the scratch."""
    answer = os.path.join(scratch, "last-message.json")
    events = os.path.join(scratch, "codex-events.jsonl")
    log = os.path.join(scratch, "codex.log")
    argv = [binary, "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check", "--cd", workdir,
            "--model", model, *routing.effort_spelling(PROVIDER, effort_level),
            "--output-schema", SCHEMA_PATH, "--output-last-message", answer, "--color", "never", "-"]
    # stdout is the JSONL event stream and nothing else; Codex's own log lines go to stderr, kept apart.
    with open(events, "wb") as evf, open(log, "wb") as logf:
        p = subprocess.Popen(argv, cwd=workdir, env=env, stdin=subprocess.PIPE, stdout=evf, stderr=logf,
                             start_new_session=True)
        try:
            try:
                p.communicate(prompt.encode("utf-8"), timeout=timeout_s)
            except subprocess.TimeoutExpired:
                raise RunTimeout(f"codex did not answer within {timeout_s / 60:g} minutes") from None
        finally:
            if p.poll() is None or _group_alive(p.pid):
                _end_group(p)
    run = read_events(events)
    if run.failed and (gone := unavailable(run.failed)):
        raise gone
    if p.returncode != 0:
        # Codex's turn message is the backend's text, untrusted: one line, bounded, as judge_run says it.
        raise FailedReview(f"codex exited {p.returncode}: "
                           + (_one_line(run.failed)[:500] if run.failed else _tail(log)))
    judge_run(run)
    if os.path.isfile(answer):
        with open(answer, "rb") as f:
            raw = f.read(MAX_ANSWER_BYTES + 1)
    elif run.last_message is not None:
        raw = run.last_message.encode("utf-8")
    else:
        raise FailedReview(f"codex wrote no answer: {_tail(log)}")
    if len(raw) > MAX_ANSWER_BYTES:
        raise FailedReview(f"the answer is over {MAX_ANSWER_BYTES} bytes")
    return raw.decode("utf-8", "replace")


USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")


class CodexRun:
    """What `codex exec --json` said it did: its error items, its commands, its last agent message."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.commands = 0            # command_execution items completed with exit code 0
        self.commands_failed = 0     # ...completed otherwise
        self.last_message: str | None = None
        self.failed: str | None = None   # turn.failed's message
        self.events = 0
        self.thread_id: str | None = None
        # The sum over turn.completed events of each usage field; a field no turn reported stays None.
        self.usage: dict[str, int | None] = dict.fromkeys(USAGE_FIELDS)


def read_events(path: str) -> CodexRun:
    """The JSONL stream of `codex exec --json` (codex 0.162.1): thread.started,
    turn.started, item.started/item.completed with item.type command_execution
    (status completed|failed, exit_code), agent_message (text) or error
    (message), turn.completed or turn.failed (error.message). A top-level
    {"type": "error"} is a transient retry ("Reconnecting... 1/5"): what it
    leads to is turn.failed or not, so only that counts. A line that is not
    JSON is skipped, never trusted."""
    run = CodexRun()
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return run
    with f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            run.events += 1
            kind, item = ev.get("type"), ev.get("item")
            if kind == "thread.started" and isinstance(ev.get("thread_id"), str):
                run.thread_id = ev["thread_id"][:200]
            if kind == "turn.completed" and isinstance(ev.get("usage"), dict):
                for field in USAGE_FIELDS:
                    if (n := ledger.count(ev["usage"].get(field))) is not None:
                        run.usage[field] = (run.usage[field] or 0) + n
            if kind == "turn.failed":
                err = ev.get("error")
                run.failed = str(err.get("message") if isinstance(err, dict) else err or "the turn failed")
            if kind != "item.completed" or not isinstance(item, dict):
                continue
            if item.get("type") == "error":
                run.errors.append(str(item.get("message") or "(no message)"))
            elif item.get("type") == "command_execution":
                if item.get("status") == "completed" and item.get("exit_code") == 0:
                    run.commands += 1
                else:
                    run.commands_failed += 1
            elif item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                run.last_message = item["text"]
    return run


def unavailable(message: str) -> ModelUnavailable | None:
    """The kind of unavailability a failed turn's message states, or None. The message is the backend's text,
    untrusted: only the fixed phrases above decide, and the reset time is quoted from it, bounded."""
    if any(m in message for m in CAPACITY_MESSAGES):
        return ModelUnavailable(CAPACITY, _one_line(message)[:300])
    if any(m in message for m in ALLOWANCE_MESSAGES):
        reset = RESET_TIME.search(message)
        return ModelUnavailable(ALLOWANCE, _one_line(message)[:300], _one_line(reset.group(1)).strip() if reset else None)
    return None


def judge_run(run: CodexRun) -> None:
    """FailedReview unless the run read the code: an answer from a run that ran
    no command is an answer from the brief alone, and 'no findings' from it
    would be posted as a clean review (2026-10-12: every Codex review so far,
    its tool host missing, answered {"findings": []} this way)."""
    if run.failed:
        raise FailedReview(f"Codex's turn failed: {_one_line(run.failed)[:500]}")
    if not run.events:
        raise FailedReview("Codex printed no events (codex exec --json); it cannot be shown to have read anything")
    host = next((e for e in run.errors if "code-mode host" in e or "codex-code-mode-host" in e), None)
    if host:
        raise FailedReview("Codex ran no command: its tool host is missing (codex-code-mode-host); install Codex whole "
                           f"with `fabric-tools --install codex` — Codex said: {_one_line(host)[:400]}")
    # Every error item refuses, Codex's "Model metadata for `X` not found" among them: it falls back to generic
    # metadata for a model outside its catalog, and the routed model (gpt-6.1-sol, routing/capabilities.json's
    # openai column) is in the catalog of the pinned 0.162.1, so on the routed path it is a misconfiguration.
    if run.errors:
        raise FailedReview(f"Codex reported an error during the run, so its answer is not trusted: "
                           f"{'; '.join(_one_line(e)[:300] for e in run.errors[:3])}")
    if not run.commands:
        raise FailedReview(f"Codex ran no command that succeeded ({run.commands_failed} failed), so it read none of "
                           "the code; an answer from the brief alone is not a review")
    if run.last_message is None:
        raise FailedReview("Codex's run ended without an agent message")


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


def format_marker(head: str, reason: str, at: str, engine: str = ENGINE) -> str:
    """The writer is stricter than the reader (verdicts.unavailable_of, the one parser, the arm's): a marker this
    engine emits always has a full head and one of its two reasons."""
    if not re.fullmatch(r"[0-9a-f]{40}", head) or reason not in (CAPACITY, ALLOWANCE):
        raise ValueError(f"not an unavailable marker's head or reason: {head!r}, {reason!r}")
    return UNAVAILABLE_MARKER.format(engine=engine, head=head, reason=reason, at=at)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def unavailable_comment(e: "ModelUnavailable", head: str, at: str) -> str:
    """The body: the marker, then one human line that carries the backend's words only as a bounded one-liner."""
    if e.kind == ALLOWANCE:
        when = e.reset or "the backend gave no reset time"
        why = f"over the ChatGPT allowance ({when})"
    else:
        why = f"the model stayed at capacity after {e.runs} run(s)"
    why = why.replace("`", "'")
    return (f"{format_marker(head, e.kind, at)}\n"
            f"Codex could not review `{head[:12]}`: {why}; the claude review alone arms, per the owner's policy.\n")


def announce_unavailable(repo: str, pr: str, head: str, e: "ModelUnavailable") -> str:
    """Post the unavailable statement once for this head, as a COMMENT review pinned to it: the carrier the arm reads
    (devex-tooling, 2026-10-13), which GitHub ties to the commit. Not the review marker's first line, so it is never
    taken for coverage. Returns "posted" or what already stands. What stands is judged as the arm judges it
    (verdicts.classify: only the PR's author or a listed poster is the engine's statement or a blind review), so a
    stranger's copy of the marker cannot stop the real one and leave the arm waiting on Codex. Raises gh.GhError
    when the PR cannot be read or the post is not confirmed; the caller turns that into a warning, because the exit
    status stays the model's."""
    global _posting
    slug = gh.this_repo(repo)
    author = (gh.api(f"repos/{slug}/pulls/{pr}") or {}).get("user", {}).get("login")
    reviews = [r for r in gh.api(f"repos/{slug}/pulls/{pr}/reviews?per_page=100", paginate=True)
               if r.get("commit_id") == head]
    try:
        counted = classify(reviews, author, read_config(os.environ))
    except Die as err:
        raise gh.GhError("the arm's review configuration", str(err)) from None
    if any(engine_of(r) == ENGINE for r in counted.blind):
        return "a Codex review of this head stands"
    for r in counted.unavailable:
        m = unavailable_of(r)
        if m and m["engine"] == ENGINE and m["head"] == head:
            return "an unavailable statement for this head stands"
    # A signal from here on may have reached GitHub; before it, nothing was written.
    _posting = True
    gh.api(f"repos/{slug}/pulls/{pr}/reviews", method="POST",
           body={"body": unavailable_comment(e, head, _utc_now()), "event": "COMMENT", "commit_id": head})
    return "posted"


def render_review(model: str, head: str, rng: str, findings: list[dict], effort_level: str | None = None) -> str:
    """The body post-review gets. Its first line names the engine, the model
    that ran (rule 4) and the level sent, or that none was; post-review puts
    its marker above it."""
    order = {"P1": 0, "P2": 1, "P3": 2}
    counts = {lv: sum(f["level"] == lv for f in findings) for lv in order}
    level = f"`{effort_level}`" if effort_level else "Codex's default"
    out = [f"**Engine:** Codex · **model:** `{model}` · **effort:** {level} — the second review engine "
           "(agent-fabric ADR-053), "
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


# Set once the post's child may have started: a signal after it cannot say "nothing posted", and a review
# cannot be unsent (post_review.py).
_posting = False


def post(repo: str, pr: str, body: str) -> int:
    global _posting
    _posting = True
    r = subprocess.run([os.path.join(FABRIC_ROOT, "bin", "fabric-pr"), "post-review", pr, "--model", ENGINE],
                       cwd=repo, input=body, text=True, timeout=180)
    return r.returncode


# --- the ledger --------------------------------------------------------------

PURPOSE = "second-engine-review"


def run_status(e: BaseException) -> tuple[str, str]:
    """The ledger's (status, status_source) for the run an exception ended."""
    if isinstance(e, ModelUnavailable):
        return ("allowance-exhausted", "codex:usage-limit") if e.kind == ALLOWANCE else ("failed", "codex:capacity")
    if isinstance(e, RunTimeout):
        return "timeout", "codex:timeout"
    if isinstance(e, _Signalled):
        return "cancelled", "codex:signal"
    if isinstance(e, FailedReview):
        return "failed", "codex:failed-review"
    return "failed", "codex:error"


def ledger_row(observed: Observed, *, brief: str, pr: str, head: str,
               model: str, level: str | None, now: str) -> dict:
    """Row v1 of a Codex review run (tools/fabric/ledger.py; the module docstring has the token semantics).
    A brief with the dispatch header gives the header's fields alone; one without gives the two facts this review
    holds (the PR it was told, the head it read), as a row with attribution "inferred". The repository stays
    unknown then: the request names a working copy's path, and owner/name is the header's to derive (a PR is
    never read out of free text, a repository out of a path)."""
    attribution, fields = ledger.dispatch_header(brief)
    if attribution == "inferred":
        fields = {"pr": int(pr), "head_sha": head}
    usage = {f: sum(r.usage[f] for r in observed.runs if r.usage[f] is not None) if any(r.usage[f] is not None for r in observed.runs)
             else None for f in USAGE_FIELDS}
    total, cached, written = usage["input_tokens"], usage["cached_input_tokens"], usage["cache_write_input_tokens"]
    fresh = None if total is None else total - (cached or 0) - (written or 0)
    return {
        "schema_version": ledger.SCHEMA_VERSION, "engine": ENGINE, "attribution": attribution,
        "purpose": fields.get("purpose", PURPOSE), "description": None,
        **{k: fields.get(k) for k in (*ledger.HEADER_IDENT[:4], "repository", "pr", "review_id", "review_round",
                                      "evidence", "base_sha", "head_sha")},
        "started_at": fields.get("started_at") or observed.started_at,
        "session_id": next((r.thread_id for r in observed.runs if r.thread_id), None),
        "agent_id": None, "agent_type": None, "tool_use_id": None,
        "status": (observed.status or ("failed", "codex:error"))[0],
        "status_source": (observed.status or ("failed", "codex:error"))[1], "completed_at": now,
        "wall_time": round(observed.seconds, 3), "turns": None,
        "input": fresh if fresh is not None and fresh >= 0 else None, "cache_write": written, "cache_read": cached,
        "output": usage["output_tokens"], "reasoning": usage["reasoning_output_tokens"], "first_turn_context": None,
        "model": model, "provider": PROVIDER, "effort": level,
    }


def write_ledger(environ: dict[str, str], observed: Observed) -> None:
    """Never raises: a measurement does not stand in a review's way, and says when it could not be made."""
    try:
        ledger.append(ledger.path(environ), ledger_row(observed, now=_utc_now(), **observed.facts))
    except (OSError, ValueError, TypeError, KeyError) as err:
        print(f"fabric-review: the ledger row could not be written ({err}); the review is unaffected", file=sys.stderr)


# --- the run -----------------------------------------------------------------

def review(pr: str, request: str, **kw) -> int:
    """_review, then the ledger row of the Codex runs it made, on every way out (an answer, a failure, a
    timeout, a signal); the runs' events were handed over by run_codex before its scratch was removed."""
    observed = Observed()
    try:
        return _review(pr, request, observed=observed, **kw)
    except BaseException as e:
        observed.status = observed.status or run_status(e)
        raise
    finally:
        # No run, no row: a refusal before Codex started cost nothing and is no dispatch (the hook writes
        # none for a subagent that made no API call either).
        if observed.runs:
            write_ledger(kw["environ"], observed)


def _review(pr: str, request: str, *, model_flag: str | None, timeout_min: float, allow_rationale: bool,
            no_post: bool, environ: dict[str, str], observed: Observed, gateway: str | None = None,
            signin_home: str | None = None, effort_flag: str | None = None) -> int:
    """With `gateway` None the gateway is the environment's (ENV_BASE_URL, ENV_KEY); with "chatgpt",
    review_gateway.py starts one of its own for this review and stops it before anything is posted."""
    if gateway is None:
        settings(environ)   # every missing setting named at once, before anything else
        account_id(environ)
    explicit_model = bool((model_flag or environ.get(ENV_MODEL) or "").strip())
    explicit_effort = bool(effort_flag or environ.get(ENV_EFFORT))
    # Routing is read only for what the overrides leave unnamed, and before anything starts: its refusal is one.
    route = Route() if not explicit_model or (gateway and not explicit_effort) else None
    model, binary = codex_settings(environ, model_flag, route)
    level = effort(environ, effort_flag, route.effort(model) if gateway and route else None)
    req, brief = load_request(request, allow_rationale)
    repo = req["repository"]
    head = range_head(req)
    if pr_head(repo, pr) != head:
        raise Refused(f"the request's head {head[:12]} is not PR #{pr}'s head: a review is posted against the PR's "
                      "head, so it must be the one read (update the request's range)")
    root = scratch_root(repo, environ)
    observed.facts = {"brief": brief, "pr": pr, "head": head, "model": model, "level": level}

    def attempt() -> list[dict]:
        # Everything a run needs is made here and gone when it ends, so a retry is as fresh as the first run.
        # Every refusal of the gateway's (the sign-in, its token's lifetime, the installed gateway) comes before it starts.
        provider = (review_gateway.serve(review_gateway.prepare(gateway, environ, signin_home, timeout_min * 60), model, environ)
                    if gateway else contextlib.nullcontext({}))
        with provider as provided:
            # What the gateway provides lives in this dict and Codex's environment only, never os.environ: the
            # post's child (fabric-pr) and anything else this process starts never inherit the local key.
            env_run = {**environ, **provided}
            base_url, key = gateway_settings(env_run)
            scratch = tempfile.mkdtemp(prefix="fabric-review-codex.", dir=root)
            try:
                workdir = os.path.join(scratch, "head")
                extract(repo, head, workdir)
                env = child_env(environ, scratch, codex_home(scratch, base_url, account_id(env_run)), key)
                prompt = brief.rstrip("\n") + "\n" + ANSWER_SHAPE
                prove_sandbox(binary, workdir, env)
                return parse_answer(run_codex(binary, model, workdir, scratch, env, prompt, timeout_min * 60, level, observed))
            finally:
                shutil.rmtree(scratch, ignore_errors=True)

    runs = 0
    while True:
        runs += 1
        try:
            findings = attempt()
            break
        except ModelUnavailable as e:
            # An allowance is spent for hours: a wait of a minute cannot help, so only the provider's capacity is retried.
            if e.kind != CAPACITY or runs > len(CAPACITY_RETRY_DELAYS_S):
                e.runs = runs
                if no_post:
                    sys.stdout.write(unavailable_comment(e, head, _utc_now()))
                else:
                    try:
                        print(f"fabric-review: unavailable statement on PR #{pr}: "
                              f"{announce_unavailable(repo, pr, head, e)}", file=sys.stderr)
                    except (gh.GhError, OSError, ValueError, TypeError, AttributeError) as err:
                        # The exit status stays the model's; an unreadable PR is not a licence to guess either way.
                        print(f"fabric-review: could not post or check the unavailable statement on PR #{pr}: {err}",
                              file=sys.stderr)
                raise
            _sleep(CAPACITY_RETRY_DELAYS_S[runs - 1])
    observed.status = ("completed", "codex:answer")   # the run's; what happens to its answer after is not
    if not no_post and pr_head(repo, pr) != head:
        raise Refused(f"PR #{pr} moved while Codex read {head[:12]}; nothing posted — run it on the new head")
    body = render_review(model, head, req["range"], findings, level)
    if no_post:
        sys.stdout.write(body)
        return 0
    return 0 if post(repo, pr, body) == 0 else 1


def _raise_signal(signum, _frame):
    raise _Signalled(signum)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    usage = ("usage: fabric-review --engine codex PR REQUEST [--gateway chatgpt [--codex-home DIR]] [--model M] "
             "[--effort LEVEL] [--timeout MINUTES, per run] [--allow-rationale] [--no-post]")
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
        if a in ("--model", "--timeout", "--gateway", "--codex-home", "--effort"):
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
    if "--gateway" in opts and opts["--gateway"] not in review_gateway.GATEWAYS:
        print(f"fabric-review: --gateway {opts['--gateway']!r}: the gateways are: {', '.join(review_gateway.GATEWAYS)}",
              file=sys.stderr)
        return 2
    if "--codex-home" in opts and "--gateway" not in opts:
        print("fabric-review: --codex-home names the sign-in a --gateway reads; without --gateway it means nothing",
              file=sys.stderr)
        return 2
    if "--effort" in opts and opts["--effort"] not in EFFORTS:
        print(f"fabric-review: --effort {opts['--effort']!r}: one of {', '.join(EFFORTS)}", file=sys.stderr)
        return 2
    for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(s, _raise_signal)
    try:
        return review(pos[0], pos[1], model_flag=opts.get("--model"), timeout_min=timeout_min,
                      allow_rationale=flags["--allow-rationale"], no_post=flags["--no-post"],
                      environ=dict(os.environ), gateway=opts.get("--gateway"), signin_home=opts.get("--codex-home"),
                      effort_flag=opts.get("--effort"))
    except (Refused, review_gateway.Refused) as e:
        print(f"fabric-review: refused: {e}", file=sys.stderr)
        return 1
    except ModelUnavailable as e:
        print(f"fabric-review: {e.report()}; no review posted", file=sys.stderr)
        return EXIT_UNAVAILABLE
    except FailedReview as e:
        print(f"fabric-review: the Codex review failed, nothing posted: {e}", file=sys.stderr)
        return 1
    except review_brief.RequestError as e:
        print("fabric-review: the request does not render:\n  " + "\n  ".join(e.problems), file=sys.stderr)
        return 1
    except _Signalled as e:
        print(f"fabric-review: stopped by signal {e.args[0]}; the scratch is removed, "
              + ("what was being posted (the review, or the unavailable statement) may have been posted: look at the PR" if _posting else "nothing posted"), file=sys.stderr)
        return 128 + int(e.args[0])
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as e:
        print(f"fabric-review: {e}; nothing posted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
