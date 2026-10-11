"""tools/fabric/control/ctl.py — the coordinator's side of the control plane:
post one request on the control channel, read the replies, print them
(ADR-040 Wave 8, ported from runtime/control/ctl.mjs, deleted in step s8;
bin/fabric-ctl runs this on the pinned Python).

    fabric-ctl <login|all> [status|usage|identity|keys|fabric|session|script|recall|host|disk|accounts|ping] [--json] [--timeout S]
    fabric-ctl <login|all> tokens [--days N]
    fabric-ctl <login|all> memory --out <dir>
    fabric-ctl <login|all> upgrade claude [--version V] | upgrade fabric
    fabric-ctl <login|all> secrets-sync [--expect SHA12] [--restart]
    fabric-ctl <login|all> presence | jobs | tools | local | local-prune | secrets-selftest
    fabric-ctl <login|all> tools-install <tool>
    fabric-ctl <login|all> gateway | gateway-install --version V
    fabric-ctl <login> jobs-add [--topic T] [--project P] [--priority P] [--] "<title>"
    fabric-ctl <holder> pool-add --role R [--topic T] [--project P] [--priority P] [--] "<title>"
    fabric-ctl <login|all> states [--follow] [--json]
    fabric-ctl keygen [--force]

A login becomes an address through the registry's placement
(<host>/<login>); `all` is every placement that is an agent (a human login
has no control agent, ADR-044), addressed as "*". The request goes out once;
the replies are read from the relay's history after the request's own id
(since_id, no cursor, nothing left behind) every half second until every
expected address has answered or the timeout is spent (the operation's own
budget: 20 s by default, 5 s for ping). An address that stayed silent is a
row that says so, and the exit code is 1 — a table is never short.
Stateless: a run leaves one request record and the agents' replies on the
channel, and nothing else anywhere.

THE CONTRACT, as the Node's, frozen by its tests (ctl.test.mjs, ported case
for case in tests/test_control_ctl.py) and held to the Node's tables by
parity cases until the Node was deleted (git history has them): argv and its refusals, the
request sent (keys and their order), the rows, every table byte for byte —
JavaScript's padEnd and padStart by UTF-16 code unit, toFixed's rounding
half up, String() of whatever an account sent — the bundles written by a
drain, the exit codes (0 every expected account answered and every action
succeeded; 1 a silent account, an unfinished drain or a failed action; 2 a
refusal; 3 no token, no signing key or a relay that could not be reached),
and stdout against stderr (tables and --json rows on stdout; every
`fabric-ctl: ` line on stderr).

WHERE THE PORT DIFFERS ON PURPOSE
  * A message an exception carries (an unreadable registry, a JSON parse
    error) is the language's own, as the Node's was: only that it is one
    line on stderr with exit 1 is the contract.
  * Sorting by name (hosts, Claude accounts, disk rows) uses `collate`, a
    key close to ICU's root collation, which Node's localeCompare applies:
    control characters ignorable, case after letters (lower first), the
    rest by code point. It agrees for what logins, hosts and e-mail
    addresses are made of (lowercase letters, digits, `.`, `-`, `@`); it
    differs for text ICU orders by script, accent or punctuation class.
  * The drain's bundles are written with the mode set before the bytes
    (os.open with 0600), not written and then chmod-ed.
  * A forged reply must not stop the table, where the Node throws on some
    shapes (an array read from a number or a null; a part or a bundle that
    is not an object): such a field reads as empty, a part or bundle that is
    not an object is skipped, a working_copy that is not text is written as
    String() writes it, and a memory reply whose bundles are not an array
    counts as a refused drain (exit 1), as it does there. The parity cases
    compare every table the Node prints and leave to Python what the Node
    refuses.
  * What is JavaScript's own and not a contract is not copied: a string or
    an array standing for a key's refusal record prints String.prototype.at's
    source in the Node (excluded from the corpus).
  * A relay record without an id leaves the cursor where it was (the Node
    sets it to undefined, and the next read says the history is gone).
"""
from __future__ import annotations

import base64
import binascii
import decimal
import functools
import gzip
import hashlib
import math
import os
import re
import subprocess
import sys
import time
import zlib
from typing import Any, Callable

_HERE = os.path.dirname(os.path.realpath(__file__))
# Run as a script, sys.path[0] is control/, whose secrets.py and tools.py would
# shadow the standard library's and the fabric's own: tools/fabric goes first
# instead, as control/gzcoord.py does for the same reason.
if sys.path and os.path.realpath(sys.path[0] or ".") == _HERE:
    sys.path[0] = os.path.dirname(_HERE)
elif os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

from control import js  # noqa: E402
from control.gzcoord import FABRIC_ROOT, api, inbox_root, integration_config, relay_failure, synced_token, token as gz_token, whoami as gz_whoami
from control.ops import OPS, PUBLIC_OPS
from control.pool import check_pool_args, pool_holder
from control.jobs import check_job_args
from control.selftest import SELFTEST_BUDGET_S
from control.sessions import SESSION_ID
from control.sign import ACTION_OPS, ACTION_TTL_MAX_S, generate_operator_key, public_key_from, sign_request
from control.gateway import GATEWAY_INSTALL_BUDGET_S
from control.tools import TOOL_NAME, TOOLS_INSTALL_BUDGET_S
from control.upgrade import FABRIC_UPGRADE_BUDGET_S, PIECES, UPGRADE_BUDGET_S, VERSION_RE, pinned_version
import roots

UNDEFINED = js.UNDEFINED
USAGE = (
    "usage: fabric-ctl <login|all> [status|usage|identity|keys|fabric|session|script|recall|host|disk|accounts|ping] [--json] [--timeout S]\n"
    "       fabric-ctl <login|all> tokens [--days N]\n"
    "       fabric-ctl <login|all> memory --out <dir>\n"
    "       fabric-ctl <login|all> upgrade claude [--version V]\n"
    "       fabric-ctl <login|all> upgrade fabric   (every account to this checkout's origin/main, then bootstrap)\n"
    "       fabric-ctl <login|all> secrets-sync [--expect SHA12] [--restart]\n"
    "       fabric-ctl <login|all> presence   (any placed account may ask)\n"
    "       fabric-ctl <login|all> jobs\n"
    "       fabric-ctl <login|all> tools   (each account: its missing required tools, from its hourly report)\n"
    "       fabric-ctl <login|all> tools-install <tool>   (an action: install the tool its registry pin names, on the accounts with a working copy of a project that declares it)\n"
    "       fabric-ctl <login|all> gateway   (each account: the gateway binary it has, its version and digest)\n"
    "       fabric-ctl <login|all> gateway-install --version V   (an action: install the gateway release the reviewed pin names, SHA-256 checked; a running gateway is never stopped)\n"
    "       fabric-ctl <login> jobs-add [--topic T] [--project P] [--priority P] [--] \"<title>\"\n"
    "       fabric-ctl <holder> pool-add --role R [--topic T] [--project P] [--priority P] [--] \"<title>\"\n"
    "       fabric-ctl <login|all> secrets-selftest\n"
    "       fabric-ctl <login|all> local\n"
    "       fabric-ctl <login|all> local-prune\n"
    "       fabric-ctl <login|all> states [--follow] [--json]\n"
    "       fabric-ctl keygen [--force]")

FETCH_TIMEOUT_S = 60


class CtlError(Exception):
    """What the Node threw as an Error: a refusal said in one line."""


# ── JavaScript's reading of text and numbers ────────────────────────

def pad_end(s: Any, n: int) -> str:
    s = js.string(s)
    return s + " " * max(0, n - js.length(s))


def pad_start(s: Any, n: int) -> str:
    s = js.string(s)
    return " " * max(0, n - js.length(s)) + s


def to_fixed(x: Any, digits: int) -> str:
    """Number.prototype.toFixed: the exact decimal expansion rounded half up
    (the larger n of two equally near ones), where Python's format rounds a
    tie to even; 1e21 and up are written as Number::toString writes them."""
    x = float(x)
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if abs(x) >= 1e21:
        return js.string(x)
    q = decimal.Decimal(10) ** -digits
    out = format(decimal.Decimal(abs(x)).quantize(q, rounding=decimal.ROUND_HALF_UP), "f")
    return ("-" if x < 0 else "") + out   # the spec prefixes "-" for any x < 0, so (-0.4).toFixed(0) is "-0"


_CONTROL = re.compile("[\u0000-\u001f\u007f-\u009f]")


def esc(n: Any) -> str:
    """What an account sent, printed in the operator's terminal: its C0 and C1
    control characters are shown escaped, never sent to the terminal (review
    of #92, round 4)."""
    return _CONTROL.sub(lambda m: f"\\x{ord(m.group(0)):02x}", js.string(n))


def dig(obj: Any, *path: str) -> Any:
    """obj?.a?.b: UNDEFINED where JavaScript would say undefined."""
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return UNDEFINED
        obj = obj[key]
    return obj


def first(v: Any) -> Any:
    """v?.[0]: an array's first element, a string's first character."""
    return v[0] if isinstance(v, (list, str)) and len(v) else None


def jlen(v: Any) -> Any:
    """v.length: an array's or string's, undefined for the rest."""
    return len(v) if isinstance(v, (list, str)) else UNDEFINED


def arr(v: Any) -> list:
    """A list to walk: what an account sent where an array is read, a string's
    characters (for...of walks them; map and find throw there, and nothing is
    owed to a throw), or nothing. A forged reply must not stop the table."""
    return v if isinstance(v, list) else list(v) if isinstance(v, str) else []


def is_empty(v: Any) -> bool:
    """`!v.length`: true for anything without a length, as undefined is falsy."""
    return not (isinstance(v, (list, str)) and len(v) > 0)


def nullish(v: Any, default: Any = None) -> Any:
    """`v ?? default`."""
    return default if v is None or v is UNDEFINED else v


def collate(s: str) -> tuple[str, str, str]:
    """A sort key close to ICU's root collation, which Node's localeCompare
    applies: control characters are ignorable, case differs only after letters
    do (lower before upper), and the rest is by code point."""
    plain = _CONTROL.sub("", s)
    return (plain.casefold(), plain.swapcase(), s)


# ── the request ─────────────────────────────────────────────────────

def origin_main(root: str | None = None, run: Callable[..., Any] = subprocess.run) -> str | None:
    """The commit `upgrade fabric` moves every account to: this checkout's
    origin/main after a fetch, never its HEAD — a coordinator on a branch
    must not ship the branch. A fetch that fails leaves no commit, and
    nothing is sent."""
    root = FABRIC_ROOT if root is None else root

    def git(*a: str) -> str:
        r = run(["git", "-C", root, *a], capture_output=True, text=True, timeout=FETCH_TIMEOUT_S, check=True, stdin=subprocess.DEVNULL)
        return str(r.stdout).strip()
    try:
        git("fetch", "-q", "origin", "main")
        return git("rev-parse", "origin/main")
    except (subprocess.SubprocessError, OSError):
        return None


def job_args(a: dict) -> dict:
    out: dict = {}
    if a["title"] is not None:
        out["title"] = a["title"]
    for key in ("topic", "project", "priority"):
        if a[key] is not None and a[key] is not UNDEFINED:
            out[key] = a[key]
    return out


def build_request(args: dict, *, id: str, from_: str, to: Any, cfg: dict, ts: str | None = None,  # noqa: A002
                  commit: Callable[[], Any] | None = None, version: Callable[[], Any] | None = None) -> dict:
    """The request this command sends, before it is signed: a Request
    (protocol), held to ENVELOPE_KEYS by the protocol suite for every op shape
    built here. `commit` and `version` read origin/main and the pinned
    harness, called only for an upgrade."""
    ts = js.iso_now() if ts is None else ts
    commit = commit or (lambda: origin_main())
    version = version or (lambda: pinned_version(FABRIC_ROOT))
    op = args["op"]
    cap = ACTION_TTL_MAX_S if op in ACTION_OPS else math.inf
    ttl = min(cap, max(cfg["ttl_s"], math.ceil(args["timeout"])))
    req: dict = {"v": 1, "kind": "request", "id": id, "from": from_, "to": to, "op": op, "ts": ts,
                 "ttl_s": int(ttl) if isinstance(ttl, float) and ttl.is_integer() else ttl}
    if js.truthy(args["days"]):
        req["days"] = args["days"]
    if op == "upgrade":
        if args["piece"] == "fabric":
            req["args"] = {"piece": "fabric", "commit": commit()}
        else:
            req["args"] = {"piece": args["piece"], "version": args["version"] if args["version"] is not None else version()}
    if op == "jobs-add":
        req["args"] = job_args(args)
    if op == "tools-install":
        req["args"] = {"tool": args["tool"]}
    if op == "gateway-install":
        req["args"] = {"version": args["version"]}
    if op == "pool-add":
        req["args"] = {**({"role": args["role"]} if args["role"] is not None else {}), **job_args(args)}
    if op == "secrets-sync" and (js.truthy(args["expect"]) or args["restart"]):
        req["args"] = {**({"expect": args["expect"]} if js.truthy(args["expect"]) else {}), **({"restart": True} if args["restart"] else {})}
    return req


def placements(registry: str | None = None) -> list[dict]:
    """A placed login's kind (ADR-044): an agent runs agentd and answers; a
    human runs none, so `all` never waits on one and naming one is refused."""
    registry = roots.hosts_registry(engine=FABRIC_ROOT, empty_is_set=True) if registry is None else registry
    with open(registry, encoding="utf-8", errors="replace") as fh:
        d = js.json_parse(fh.read())
    kinds = nullish(dig(d, "kinds"), {})
    placement = nullish(dig(d, "placement"), {})
    out = []
    for login in js.keys(placement) if isinstance(placement, dict) else []:
        host = placement[login]
        out.append({"login": login, "host": host, "address": f"{js.string(host)}/{login}",
                    "kind": "human" if isinstance(kinds, dict) and kinds.get(login) == "human" else "agent"})
    return out


def parse_args(argv: list[str]) -> dict:
    out: dict = {"targets": [], "op": "status", "json": False, "timeout": None, "out": None, "days": None, "piece": None, "version": None,
                 "force": False, "expect": None, "restart": False, "title": None, "topic": None, "project": None, "priority": None,
                 "role": None, "follow": False, "tool": None}
    i = 0
    n = len(argv)

    def nxt() -> Any:
        nonlocal i
        i += 1
        return argv[i] if i < n else UNDEFINED
    while i < n:
        a = argv[i]
        # A jobs-add title that starts with a dash follows `--`, as for
        # fabric-jobs itself: after it the next word is the title, never an option.
        titled = out["op"] in ("jobs-add", "pool-add")
        if titled and out["title"] is None and a == "--":
            t = nxt()
            out["title"] = None if t is UNDEFINED else t
            i += 1
            continue
        if a == "--json":
            out["json"] = True
        elif a == "--timeout":
            out["timeout"] = _number(nxt())
        elif a.startswith("--timeout="):
            out["timeout"] = _number(a[10:])
        elif a == "--out":
            out["out"] = nxt()
        elif a.startswith("--out="):
            out["out"] = a[6:]
        elif a == "--days":
            out["days"] = _number(nxt())
        elif a.startswith("--days="):
            out["days"] = _number(a[7:])
        elif a == "--version":
            out["version"] = nxt()
        elif a.startswith("--version="):
            out["version"] = a[10:]
        elif a == "--force":
            out["force"] = True
        elif a == "--expect":
            out["expect"] = nxt()
        elif a.startswith("--expect="):
            out["expect"] = a[9:]
        elif a == "--restart":
            out["restart"] = True
        elif a == "--follow":
            out["follow"] = True
        elif a == "--topic":
            out["topic"] = nxt()
        elif a.startswith("--topic="):
            out["topic"] = a[8:]
        elif a == "--project":
            out["project"] = nxt()
        elif a.startswith("--project="):
            out["project"] = a[10:]
        elif a == "--priority":
            out["priority"] = nxt()
        elif a.startswith("--priority="):
            out["priority"] = a[11:]
        elif a == "--role":
            out["role"] = nxt()
        elif a.startswith("--role="):
            out["role"] = a[7:]
        elif a in ("-h", "--help"):
            out["help"] = True
        elif a.startswith("--"):
            raise CtlError(f"unknown option {a}")
        elif a == "keygen" and not out["targets"]:
            out["op"] = "keygen"
        elif out["op"] == "tools-install" and out["tool"] is None:
            out["tool"] = a   # the word after `tools-install` is the tool, never a login
        elif out["op"] == "upgrade" and out["piece"] is None:
            out["piece"] = a   # the word after `upgrade` is the piece, never a login
        elif titled and out["title"] is None:
            out["title"] = a   # the word after `jobs-add` or `pool-add` is the title, never a login
        elif (a in OPS or a == "states") and out["targets"]:
            out["op"] = a
        else:
            out["targets"].append(a)
        i += 1
    op = out["op"]
    if out["timeout"] is None:
        out["timeout"] = (5 if op == "ping" else 120 if op == "memory" else 60 if op == "tokens" else 300 if op == "accounts"
                          else 200 if op == "disk" else (FABRIC_UPGRADE_BUDGET_S if out["piece"] == "fabric" else UPGRADE_BUDGET_S) if op == "upgrade"
                          else 240 if op == "secrets-sync" else TOOLS_INSTALL_BUDGET_S if op == "tools-install"
                          else GATEWAY_INSTALL_BUDGET_S if op == "gateway-install"
                          else SELFTEST_BUDGET_S if op == "secrets-selftest" else 20)
    if op == "upgrade" and out["piece"] not in PIECES:
        raise CtlError(f"upgrade takes a piece: {', '.join(PIECES)}")
    version = out["version"]
    if version is not None and (op not in ("upgrade", "gateway-install") or not (isinstance(version, str) and VERSION_RE.fullmatch(version))):
        raise CtlError("--version takes digits.digits.digits, with upgrade and gateway-install only")
    if op == "gateway-install" and version is None:
        raise CtlError("gateway-install takes --version V: the release the reviewed pin names")
    if version is not None and out["piece"] == "fabric":
        raise CtlError("upgrade fabric takes no --version: it moves every account to this checkout's origin/main")
    if (out["expect"] is not None or out["restart"]) and op != "secrets-sync":
        raise CtlError("--expect and --restart go with secrets-sync only")
    if out["expect"] is not None and not (isinstance(out["expect"], str) and re.fullmatch(r"[0-9a-f]{12}", out["expect"])):
        raise CtlError("--expect takes a 12-hex setup-token fingerprint (fabric-accounts templates)")
    days = out["days"]
    if days is not None and (op != "tokens" or not math.isfinite(days) or days <= 0):
        raise CtlError("--days takes a positive number of days, with tokens only")
    if (out["topic"] is not None or out["project"] is not None or out["priority"] is not None) and op not in ("jobs-add", "pool-add"):
        raise CtlError("--topic, --project and --priority go with jobs-add and pool-add only")
    if out["role"] is not None and op != "pool-add":
        raise CtlError("--role goes with pool-add only")
    # A placed agent lists and claims for itself, through fabric-jobs: the
    # claim lands on its own list, which no operator's command can write.
    if op in ("pool-list", "pool-claim"):
        raise CtlError(f"{op} is fabric-jobs's: a placed agent runs fabric-jobs {op}")
    if op == "pool-add":
        bad = check_pool_args({**({"role": out["role"]} if out["role"] is not None else {}), **job_args(out)})
        if bad:
            raise CtlError(f"pool-add: {bad}")
        if len(out["targets"]) != 1 or out["targets"][0] == "all":
            raise CtlError("pool-add names the one login that holds the pool")
    if op == "tools-install" and (out["tool"] is None or not TOOL_NAME.fullmatch(out["tool"])):
        raise CtlError("tools-install takes a tool name: fabric-ctl <login|all> tools-install <tool>")
    if out["follow"] and op != "states":
        raise CtlError("--follow goes with states only")
    if op == "jobs-add":
        bad = check_job_args(job_args(out))
        if bad:
            raise CtlError(f"jobs-add: {bad}")
        if len(out["targets"]) != 1 or out["targets"][0] == "all":
            raise CtlError("jobs-add names one login: a job is one agent's, never the fleet's")
    if op == "memory" and not js.truthy(out["out"]):
        raise CtlError("memory takes --out <dir>: where the drain bundles are written")
    t = out["timeout"]
    if not (isinstance(t, (int, float)) and math.isfinite(t) and t > 0):
        raise CtlError("--timeout takes seconds, a positive number")
    return out


def _number(v: Any) -> float:
    """Number(v) of an argv word, or of a missing one (undefined: NaN)."""
    n = js.number("undefined" if v is UNDEFINED else v)
    return int(n) if math.isfinite(n) and n.is_integer() else n


# ── the drain bundles ───────────────────────────────────────────────
#
# <out>/<login>/<working copy>.tar, each reassembled from its parts,
# gunzipped, checked against the sha256 the first reply named, and checked to
# be that login's — the tar's manifest names who harvested it, and a reply is
# only a record on a channel every token holder can write, so a bundle whose
# manifest says another agent is refused as `wrong-agent` rather than filed
# under a name it did not come from. A bundle that does not verify is not
# written, and the row says so. Directories 0700, files 0600: a drain is
# other people's memory.

def manifest_agent(tar: bytes) -> Any:
    """The harvester writes manifest.json as the first member: a 512-byte
    header (name at 0, size in octal at 124), then the bytes."""
    if len(tar) < 512 or tar[:100].decode("utf-8", "replace").split("\0", 1)[0] != "manifest.json":
        return None
    size_text = tar[124:136].decode("utf-8", "replace").split("\0", 1)[0].strip()
    m = re.match(r"[0-7]+", size_text)
    if not m:
        return None   # parseInt of a size with no octal digit is NaN: the slice is empty and does not parse
    size = int(m.group(0), 8)
    try:
        doc = js.json_parse(tar[512:512 + size].decode("utf-8", "replace"))
    except ValueError:
        return None
    agent = doc.get("agent") if isinstance(doc, dict) else None
    return None if agent is None else agent


def part_key(from_: Any, p: Any) -> str:
    return f"{js.string(from_)}\u0000{js.string(dig(p, 'slug'))}\u0000{js.string(dig(p, 'part'))}"


def write_bundles(out: str, expected: list[dict], replies: list[dict], parts: dict) -> None:
    # Two bundles of one account never share a file: the second would replace
    # the first and one memory directory would never reach the drain unsaid.
    written_now: set[str] = set()
    for e in expected:
        r = next((x for x in replies if x.get("from") == e["address"]), None)
        if r is None:
            continue
        got = list(parts.get(e["address"], {}).values())
        bundles = dig(r, "data", "memory", "bundles")
        for b in bundles if isinstance(bundles, list) else []:
            if not isinstance(b, dict) or b.get("status") != "ok":
                continue
            mine = sorted((p for p in got if js_eq(dig(p, "slug"), b.get("slug", UNDEFINED))), key=functools.cmp_to_key(by_part))
            if not js_eq(len(mine), b.get("parts", UNDEFINED)) or any(not js_eq(dig(p, "part"), i + 1) for i, p in enumerate(mine)):
                b["written"] = None
                b["status"] = "incomplete"
                continue
            try:
                tar = gzip_decompress(_b64decode("".join("" if dig(p, "chunk") in (None, UNDEFINED) else S(p["chunk"]) for p in mine)))
            except (zlib.error, binascii.Error, OSError, EOFError, KeyError, TypeError):
                b["status"] = "unreadable"
                continue
            if hashlib.sha256(tar).hexdigest() != b.get("sha256"):
                b["status"] = "sha-mismatch"
                continue
            agent = manifest_agent(tar)
            if agent != e["login"]:
                b["status"] = "wrong-agent"
                b["manifest_agent"] = agent
                continue
            # mkdir's mode and a file's apply only on creation: a directory or a
            # tar left by an earlier drain keeps its mode unless set again.
            d = os.path.join(out, e["login"])
            mkdir_private(d)
            os.chmod(d, 0o700)
            # The projects root's own memory is filed under the fabric checkout
            # too (memory_dirs): its tar is named apart from the checkout's own.
            file = os.path.join(d, f"{js_basename(b['working_copy'])}{'-projects-root' if js.truthy(b.get('projects_root')) else ''}.tar")
            if file in written_now:
                b["written"] = None
                b["status"] = "duplicate-target"
                continue
            written_now.add(file)
            fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(tar)
            b["written"] = file


def js_eq(a: Any, b: Any) -> bool:
    """a === b for JSON values: no coercion (true is not 1, "1" is not 1)."""
    if a is UNDEFINED or b is UNDEFINED:
        return a is b
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def by_part(x: Any, y: Any) -> int:
    """sort((x, y) => x.part - y.part): a NaN difference leaves the order as it was."""
    d = _js_sub(dig(x, "part"), dig(y, "part"))
    return 0 if d == 0 or math.isnan(d) else -1 if d < 0 else 1


def mkdir_private(path: str) -> None:
    """mkdir -p whose every created directory is 0700, as Node's recursive
    mkdir with a mode makes them; os.makedirs gives only the last one its mode."""
    missing = []
    p = os.path.abspath(path)
    while not os.path.isdir(p):
        missing.append(p)
        p = os.path.dirname(p)
    for d in reversed(missing):
        try:
            os.mkdir(d, 0o700)
        except FileExistsError:
            pass


def _b64decode(text: str) -> bytes:
    """Buffer.from(text, 'base64'): unpadded input is read, characters outside
    the alphabet are skipped."""
    cleaned = re.sub(r"[^A-Za-z0-9+/]", "", text.split("=", 1)[0].replace("-", "+").replace("_", "/"))   # decoding stops at the first "="
    if len(cleaned) % 4 == 1:
        cleaned = cleaned[:-1]   # one character is not a byte: dropped, as the Node drops it
    return base64.b64decode(cleaned + "=" * (-len(cleaned) % 4))


def js_basename(p: Any) -> str:
    """path.basename: a trailing separator does not make the name empty."""
    return os.path.basename(S(p).rstrip("/"))   # a non-string is written as String() does, where the Node threw


def gzip_decompress(data: bytes) -> bytes:
    """zlib.gunzipSync: members back to back and zero padding after them are
    read, any other trailing byte is refused, as gzip.decompress does."""
    return gzip.decompress(data)


# ── rows ────────────────────────────────────────────────────────────

def rows(expected: list[dict], replies: list[dict]) -> list[dict]:
    """One row per expected address from the replies collected."""
    by = {r.get("from"): r for r in replies}
    out = []
    for e in expected:
        r = by.get(e["address"])
        if r is None:
            out.append({"account": e["login"], "host": e["host"], "status": "no answer"})
            continue
        d = nullish(r.get("data"), {})

        def g(*path: str) -> Any:
            v = dig(d, *path)
            return None if v is UNDEFINED else v
        acct = dig(d, "identity", "claude_account")
        email = dig(acct, "email")
        if email is UNDEFINED or email is None:
            email = f"setup-token {S(dig(d, 'identity', 'claude_account', 'token_sha256_12'))}" if dig(acct, "via") == "setup-token" else None
        out.append({"account": e["login"], "host": e["host"], "status": "ok", "op": r["op"] if "op" in r else UNDEFINED, "latency_ms": nullish(r.get("latency_ms"), None),
                    "email": email, "role": g("identity", "role"),
                    "five_hour": g("usage", "five_hour"), "seven_day": g("usage", "seven_day"), "usage_status": g("usage", "status"),
                    "keys": g("keys"), "fabric": g("fabric"), "session": g("session"), "script": g("script"), "recall": g("recall"),
                    "tokens": g("tokens"), "memory": g("memory"), "machine": g("host"), "disk": g("disk"), "accounts": g("accounts"),
                    "upgrade": g("upgrade"), "secretsSync": g("secrets-sync"), "presence": g("presence"), "jobs": g("jobs"), "tools": g("tools"),
                    "jobsAdd": g("jobs-add"), "toolsInstall": g("tools-install"), "gateway": g("gateway"), "gatewayInstall": g("gateway-install"), "poolAdd": g("pool-add"), "local": g("local"),
                    "localPrune": g("local-prune"), "selftest": g("secrets-selftest"), "agentd": g("agentd"),
                    # Only where the control agent answered them (an older one does not): a row never says null for a section nobody asked.
                    **{k: g(k) for k in ("harness", "inbox") if dig(d, k) is not UNDEFINED}})
    return out


# What counts as success for each action; anything else fails the run.
ACTION_OK = {"upgrade": ["current", "upgraded"], "secrets-sync": ["synced"], "jobs-add": ["added"], "local-prune": ["pruned", "clean"],
             "secrets-selftest": ["pass"], "pool-add": ["added"], "tools-install": ["installed", "current", "skipped"],
             "gateway-install": ["installed", "current"]}


def targets_of(targets: list[str], placed: list[dict]) -> dict:
    """Who is asked: `all` is every agent, never a human, which has no control
    agent to answer (ADR-044 rule 4); a name must be placed and an agent."""
    if len(targets) == 1 and targets[0] == "all":
        return {"expected": [p for p in placed if p["kind"] == "agent"], "everyone": True}
    expected = []
    for t in targets:
        p = next((x for x in placed if x["login"] == t), None)
        if p is None:
            return {"refused": f"{t} is not a placed account (runtime/hosts/registry.json)"}
        if p["kind"] == "human":
            return {"refused": f"{t} is a human login (ADR-044): no control agent answers for it"}
        expected.append(p)
    return {"expected": expected}


# ── the tables ──────────────────────────────────────────────────────
#
# What an account sent is untrusted text and may have any shape: it is read
# with dig (JavaScript's `?.`: undefined for a missing or non-object step)
# and written with S (String(): "undefined", "null", "[object Object]" as the
# Node's template literals wrote them).

S = js.string
T = js.truthy


def number_of(v: Any) -> float:
    from control.agentd import number_of as n
    return n(v)


def usub(s: Any, a: int, b: int | None = None) -> str:
    """s.slice(a, b) in UTF-16 code units."""
    raw = S(s).encode("utf-16-le", "surrogatepass")
    return raw[2 * a:None if b is None else 2 * b].decode("utf-16-le", "surrogatepass")


def trim_end(s: str) -> str:
    return s.rstrip(js.SPACE)


def j(*items: Any) -> str:
    return "".join(items)


def pct(w: Any) -> str:
    u = dig(w, "utilization")
    return f"{pad_start(to_fixed(number_of(u), 0), 3)}%" if T(w) and u is not UNDEFINED and u is not None else "   -"


def at(w: Any) -> str:
    r = dig(w, "resets_at")
    return usub(r, 0, 16) if T(w) and T(r) else "-"


def _samples(p: Any) -> Any:
    n = dig(p, "hour", "samples")
    return n if isinstance(n, (int, float)) and not isinstance(n, bool) else 0


def pressure_text(answers: list) -> str:
    """The host's memory pressure line. Every daemon on a host samples the same
    machine; the one with the most samples in the hour has been up longest and
    speaks for it. some/full are PSI avg10, a % of the last ten seconds."""
    def hhmm(ts: Any) -> str:
        return f"{usub(ts, 11, 16)}Z"

    def N(n: Any) -> str:
        return "-" if n is None or n is UNDEFINED else S(n)
    oks = sorted((p for p in answers if dig(p, "status") == "ok"), key=lambda p: -_samples(p))   # stable, as Array.prototype.sort is
    best = oks[0] if oks else None
    if best is None:
        p = next((x for x in answers if dig(x, "status") == "failed"), None)
        if p is None:
            p = next((x for x in answers if T(x)), None)
        if p is None:
            return "-"
        if dig(p, "status") == "none":
            return "no samples yet"
        return f"{esc(dig(p, 'status'))}{': ' + esc(p['error']) if T(dig(p, 'error')) else ''}"
    lasts = arr(dig(best, "last"))
    last = ", ".join(f"{hhmm(dig(x, 'ts'))} {N(dig(x, 'some_avg10'))}/{N(dig(x, 'full_avg10'))} {N(dig(x, 'mem_available_mb'))} MB" for x in lasts) or "-"
    h = nullish(dig(best, "hour"), {})

    def w(label: str, x: Any, unit: str = "") -> str:
        return f"{label} {S(dig(x, 'value')) + unit + ' at ' + hhmm(dig(x, 'ts')) if T(x) else '-'}"
    return (f"last {last} (some/full avg10 %, available); worst of the hour ({N(dig(h, 'samples'))} samples): "
            f"{w('some', dig(h, 'some_avg10'))}, {w('full', dig(h, 'full_avg10'))}, {w('available', dig(h, 'mem_available_mb'), ' MB')}")


def _row(r: dict) -> str:
    return f"{pad_end(r['account'], 22)} {r['status']}"


def _unless(r: dict, u: Any) -> bool:
    """The first lines of nearly every table: not answered, or no result."""
    return r["status"] != "ok" or not T(u)


def _table_selftest(rs: list) -> list[str]:
    lines = [f"{pad_end('account', 22)} {pad_end('status', 8)} steps"]
    for r in rs:
        u = r.get("selftest")
        if _unless(r, u):
            lines.append(_row(r))
            continue
        steps_ = arr(dig(u, "steps"))
        steps = ", ".join(f"{esc(dig(s, 'step'))} {'ok' if T(dig(s, 'ok')) else 'FAIL'}" for s in steps_)
        failed = next((s for s in steps_ if not T(dig(s, "ok"))), None)
        why = nullish(dig(failed, "reason"), nullish(dig(u, "reason"), nullish(dig(u, "note"), "")))
        lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end(esc(nullish(dig(u, 'status'), 'no status')), 8)} {steps}{'  (' + esc(why) + ')' if T(why) else ''}"))
    return lines


def _table_secrets_sync(rs: list) -> list[str]:
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} {pad_end('claude sign-in', 34)} {pad_end('session', 28)} reason"]
    for r in rs:
        u = r.get("secretsSync")
        if _unless(r, u):
            lines.append(_row(r))
            continue
        cs = dig(u, "claude_sign_in")
        si = f"setup-token {S(dig(cs, 'token_sha256_12'))}" if dig(cs, "via") == "setup-token" else S(nullish(dig(cs, "via"), "-"))
        missing = dig(u, "missing")
        tail = nullish(dig(u, "reason"), nullish(dig(u, "note"), f"missing in the store: {', '.join('' if x is None else S(x) for x in missing)}" if T(missing) and isinstance(missing, list)
                                                else (f"missing in the store: {S(missing)}" if T(missing) else "")))
        lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end(S(nullish(dig(u, 'status'), 'no status')), 10)} {pad_end(si, 34)} "
                              f"{pad_end(S(nullish(dig(u, 'session'), '-')), 28)} {S(tail)}"))
    return lines


def secrets_of(f: Any) -> Any:
    v = dig(f, "secrets")
    return v if isinstance(v, (list, str)) else []


def _table_local(op: str, rs: list) -> list[str]:
    # Names and counts only: the reply never carries a value.
    lines = [f"{pad_end('account', 22)} {pad_end('working copy', 18)} {pad_end('status', 10)} {'env (secrets marked *)  permissions  other keys' if op == 'local' else 'removed / reason'}"]
    for r in rs:
        u = r.get("local") if op == "local" else r.get("localPrune")
        if _unless(r, u):
            lines.append(_row(r))
            continue
        if dig(u, "status") != "ok" and op == "local":
            lines.append(f"{pad_end(r['account'], 22)} {pad_end('', 18)} {esc(dig(u, 'status'))}{': ' + esc(u['error']) if T(dig(u, 'error')) else ''}")
            continue
        if op == "local-prune" and not T(dig(u, "files")):
            lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end('', 18)} {esc(dig(u, 'status'))}  {esc(nullish(dig(u, 'reason'), ''))}"))
            continue
        files = dig(u, "files")
        if is_empty(files):
            lines.append(f"{pad_end(r['account'], 22)} {pad_end('-', 18)} none")
            continue
        for i, f in enumerate(files):
            head = f"{pad_end('' if i else r['account'], 22)} {pad_end(esc(dig(f, 'working_copy')), 18)} {pad_end(esc(dig(f, 'status')), 10)}"
            if op == "local-prune":
                removed = dig(f, "removed")
                shown = " ".join(esc(x) for x in removed) if not is_empty(removed) else ""
                lines.append(trim_end(f"{head} {shown or esc(nullish(dig(f, 'reason'), ''))}"))
                continue
            if dig(f, "status") != "ok":
                lines.append(trim_end(head))
                continue
            env = "-" if is_empty(dig(f, "env")) else " ".join(f"{esc(n)}{'*' if n in secrets_of(f) else ''}" for n in f["env"])
            p = dig(f, "permissions")
            other = "-" if is_empty(dig(f, "keys")) else " ".join(esc(k) for k in f["keys"])
            lines.append(f"{head} {env}  allow {S(dig(p, 'allow'))}/deny {S(dig(p, 'deny'))}/ask {S(dig(p, 'ask'))}  {other}")
    return lines


def _table_jobs(rs: list) -> list[str]:
    lines: list[str] = []
    for r in rs:
        if _unless(r, r.get("jobs")):
            lines.append(_row(r))
            continue
        if dig(r.get("jobs"), "status") != "ok":
            lines.append(f"{pad_end(r['account'], 22)} jobs {S(dig(r['jobs'], 'status'))}{': ' + S(r['jobs']['error']) if T(dig(r['jobs'], 'error')) else ''}")
            continue
        jobs = r.get("jobs").get("jobs") if isinstance(r.get("jobs"), dict) else UNDEFINED
        if is_empty(jobs):
            lines.append(f"{pad_end(r['account'], 22)} no open jobs")
            continue
        # What an account sent reaches this terminal escaped (esc), like every other table.
        for i, jb in enumerate(jobs):
            prio = "normal" if dig(jb, "priority") is UNDEFINED else ("?" if jb["priority"] is None else S(jb["priority"]))
            project = dig(jb, "project")
            topic = f" [{S(jb['topic'])}]" if T(dig(jb, "topic")) else ""
            source = f" ({S(dig(jb, 'source'))})" if dig(jb, "source") != "self" else ""
            blocked = f" — on {S(jb['blocked_on'])}" if T(dig(jb, "blocked_on")) else ""
            lines.append(esc(f"{pad_end('' if i else r['account'], 22)} {pad_end(S(dig(jb, 'id')), 5)} {pad_end(S(dig(jb, 'state')), 9)} {pad_end(prio, 8)} "
                             f"{pad_end(S(project) if project is not UNDEFINED and project is not None else '-', 14)} {S(dig(jb, 'title'))}{topic}{source}{blocked}"))
    return lines


def _age(age_s: Any) -> str:
    return (f"{S(age_s)} s" if age_s < 120 else f"{S(js_round(age_s / 60))} min" if age_s < 7200 else f"{S(js_round(age_s / 3600))} h"
            if age_s < 172800 else f"{S(js_round(age_s / 86400))} days")


def js_round(x: float) -> Any:
    from control.ops import util
    return util.js_round(x)


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _table_tools(rs: list) -> list[str]:
    lines: list[str] = []
    for r in rs:
        t = r.get("tools")
        if _unless(r, t):
            lines.append(_row(r))
            continue
        if dig(t, "status") == "none":
            lines.append(f"{pad_end(r['account'], 22)} no report yet")
            continue
        if dig(t, "status") != "ok":
            lines.append(f"{pad_end(r['account'], 22)} tools {esc(dig(t, 'status'))}{': ' + esc(t['error']) if T(dig(t, 'error')) else ''}")
            continue
        if not isinstance(t.get("tools"), list) or not _finite(t.get("age_s")):
            lines.append(f"{pad_end(r['account'], 22)} tools: malformed reply")
            continue
        age = _age(t["age_s"])
        missing = [x for x in t["tools"] if T(x) and dig(x, "status") != "ok" and not T(dig(x, "optional"))]
        if not missing:
            lines.append(f"{pad_end(r['account'], 22)} nothing required is missing (report {age} old)")
            continue
        for i, x in enumerate(missing):
            lines.append(f"{pad_end('' if i else r['account'], 22)} {pad_end(esc(dig(x, 'project')), 14)} {pad_end(esc(dig(x, 'name')), 16)} {pad_end(esc(dig(x, 'status')), 8)} "
                         f"needs {esc(dig(x, 'version') if T(dig(x, 'version')) else 'any')}, {esc(dig(x, 'where') if T(dig(x, 'where')) else '?')}"
                         + (f"  (report {age} old)" if i == len(missing) - 1 else ""))
    return lines


def _table_tools_install(rs: list) -> list[str]:
    lines = []
    for r in rs:
        u = r.get("toolsInstall")
        body = r["status"] if _unless(r, u) else f"{pad_end(S(dig(u, 'status')), 9)} {S(nullish(dig(u, 'tool'), ''))} {S(nullish(dig(u, 'version'), ''))}{' ' + S(u['reason']) if T(dig(u, 'reason')) else ''}"
        lines.append(esc(trim_end(f"{pad_end(r['account'], 22)} {body}")))
    return lines


def _table_gateway(rs: list) -> list[str]:
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} {pad_end('version', 9)} {pad_end('contract', 8)} digest"]
    for r in rs:
        u = r.get("gateway")
        if _unless(r, u):
            lines.append(_row(r))
            continue
        digest = S(dig(u, "installed_sha256"))[:12] if T(dig(u, "installed_sha256")) else "-"
        why = f"  {S(u['reason'])}" if T(dig(u, "reason")) else ""
        lines.append(esc(trim_end(f"{pad_end(r['account'], 22)} {pad_end(S(nullish(dig(u, 'status'), 'no status')), 10)} "
                                  f"{pad_end(S(nullish(dig(u, 'version'), '-')), 9)} {pad_end(S(nullish(dig(u, 'contract'), '-')), 8)} {digest}{why}")))
    return lines


def _table_gateway_install(rs: list) -> list[str]:
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} {pad_end('version', 9)} {pad_end('verified sha256', 16)} reason"]
    for r in rs:
        u = r.get("gatewayInstall")
        if _unless(r, u):
            lines.append(_row(r))
            continue
        digest = S(dig(u, "sha256"))[:12] if T(dig(u, "sha256")) else "-"
        lines.append(esc(trim_end(f"{pad_end(r['account'], 22)} {pad_end(S(nullish(dig(u, 'status'), 'no status')), 10)} "
                                  f"{pad_end(S(nullish(dig(u, 'version'), '-')), 9)} {pad_end(digest, 16)} {S(nullish(dig(u, 'reason'), ''))}")))
    return lines


def _table_jobs_add(rs: list) -> list[str]:
    lines = []
    for r in rs:
        u = r.get("jobsAdd")
        body = r["status"] if _unless(r, u) else f"{S(dig(u, 'status'))}  {S(nullish(dig(u, 'job'), nullish(dig(u, 'reason'), '')))}"
        lines.append(trim_end(f"{pad_end(r['account'], 22)} {body}"))
        if T(dig(u, "warning")):
            lines.append(f"{pad_end('', 22)} {S(u['warning'])}")
    return lines


def _table_pool_add(rs: list) -> list[str]:
    lines = []
    for r in rs:
        u = r.get("poolAdd")
        if _unless(r, u):
            body = r["status"]
        elif dig(u, "status") == "added":
            job = dig(u, "job")
            body = f"added  {S(dig(job, 'id'))} {S(dig(job, 'role'))} {S(dig(job, 'priority'))}: {S(dig(job, 'title'))}"
        else:
            body = f"{S(dig(u, 'status'))}  {S(nullish(dig(u, 'reason'), ''))}"
        lines.append(esc(trim_end(f"{pad_end(r['account'], 22)} {body}")))
    return lines


def _table_presence(rs: list) -> list[str]:
    lines = [f"{pad_end('account', 22)} {pad_end('session', 12)} {pad_end('since (UTC)', 20)} {pad_end('role', 20)} project"]
    for r in rs:
        p = r.get("presence")
        if _unless(r, p):
            lines.append(_row(r))
            continue
        if dig(p, "status") != "ok":
            lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end('unknown', 12)} {S(nullish(dig(p, 'error'), ''))}"))
            continue
        since = usub(S(p["since"]), 0, 19).replace("T", " ", 1) if T(dig(p, "since")) else "-"
        sessions = dig(p, "sessions")
        online = (f"{'planning' if T(dig(p, 'planning')) else 'running'}{' ×' + S(sessions) if _gt1(sessions) else ''}") if T(dig(p, "online")) else "none"
        lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end(online, 12)} {pad_end(since, 20)} {pad_end(S(nullish(dig(p, 'role'), '-')), 20)} {S(nullish(dig(p, 'project'), '-'))}"))
    return lines


def _gt1(v: Any) -> bool:
    """`v > 1` as JavaScript compares it: a string is a number, undefined is NaN."""
    if isinstance(v, bool):
        return int(v) > 1
    if isinstance(v, (int, float)):
        return v > 1
    if isinstance(v, str):
        return number_of(v) > 1
    if v is None:
        return False
    return False if v is UNDEFINED else number_of(S(v)) > 1


def _table_upgrade(rs: list) -> list[str]:
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} {pad_end('from → to', 22)} {pad_end('session', 26)} reason"]
    for r in rs:
        u = r.get("upgrade")
        if _unless(r, u):
            lines.append(_row(r))
            continue
        if dig(u, "status") == "current":
            ft = f"{S(dig(u, 'to'))} (main)" if dig(u, "piece") == "fabric" else f"{S(dig(u, 'version'))} (pinned)"
        else:
            ft = f"{S(nullish(dig(u, 'from'), '-'))} → {S(nullish(dig(u, 'to'), '-'))}"
        # A claude upgrade reruns user-settings.py (#74) and says how it went
        # in `settings`; without it in the row, a fleet run needed a read-back
        # per account to know whether every auto-mode list was refreshed.
        first = nullish(dig(u, "reason"), dig(u, "note"))
        settings = dig(u, "settings")
        parts = [x for x in (first, f"settings {S(settings)}" if T(settings) else None) if T(x)]
        why = "; ".join(S(x) for x in parts)
        lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end(S(nullish(dig(u, 'status'), 'no status')), 10)} {pad_end(ft, 22)} {pad_end(S(nullish(dig(u, 'session'), '-')), 26)} {why}"))
    return lines


def _table_accounts(rs: list) -> list[str]:
    # One row per observed CLAUDE account, not per login: only the observer's
    # daemon has any; the rest answer `none` and are not rows.
    def meter(a: Any, kind: str) -> str:
        l = next((x for x in arr(dig(a, "limits")) if dig(x, "kind") == kind), None)
        if l is None:
            return "   -"
        return f"{pad_start(S(nullish(dig(l, 'percent'), '-')), 3)}% {usub(S(nullish(dig(l, 'resets_at'), '-')), 0, 16)}"
    lines = [f"{pad_end('claude account', 34)} {pad_end('status', 14)} {pad_end('session / resets', 22)} {pad_end('weekly / resets', 22)} "
             f"{pad_end('per-model weekly / resets', 34)} {pad_end('read at', 17)} observer"]
    n = answered = 0
    for r in rs:
        if r["status"] != "ok":
            lines.append(f"{pad_end('-', 34)} {pad_end(r['status'], 14)} ({r['account']})")
            continue
        answered += 1
        acc = r.get("accounts")
        if not T(acc) or dig(acc, "status") == "none":
            continue
        if dig(acc, "status") != "ok":
            lines.append(trim_end(f"{pad_end('-', 34)} {pad_end(S(dig(acc, 'status')), 14)} {S(nullish(dig(acc, 'error'), ''))}") + f"  ({r['account']})")
            n += 1
            continue
        for a in arr(dig(acc, "accounts")):
            n += 1
            scoped = next((x for x in arr(dig(a, "limits")) if dig(x, "kind") == "weekly_scoped"), None)
            sc = f"{meter(a, 'weekly_scoped')}{' ' + S(scoped['model']) if T(dig(scoped, 'model')) else ''}" if scoped is not None else "   -"
            who = nullish(dig(a, "email"), dig(a, "slug"))
            lines.append(f"{pad_end(S(who), 34)} {pad_end(S(dig(a, 'status')), 14)} {pad_end(meter(a, 'session'), 22)} {pad_end(meter(a, 'weekly_all'), 22)} "
                         f"{pad_end(sc, 34)} {pad_end(usub(S(nullish(dig(a, 'read_at'), '-')), 0, 16), 17)} {r['account']}{'  ' + S(a['error']) if T(dig(a, 'error')) else ''}")
    # "Nothing observed" is a finding only when a daemon said so; silence is not.
    if not n and answered:
        lines.append("no Claude account is observed — bin/fabric-accounts login <account> on the coordinator's login "
                     "(docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md)")
    return lines


def _table_ping(rs: list) -> list[str]:
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} latency"]
    for r in rs:
        lat = r.get("latency_ms")
        lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end(r['status'], 10)} {S(lat) + ' ms' if lat is not None else ''}"))
    return lines


def _table_memory(rs: list) -> list[str]:
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} bundles"]
    for r in rs:
        if r["status"] != "ok":
            lines.append(_row(r))
            continue
        mem = r.get("memory")
        if T(mem) and dig(mem, "status") != "ok":
            lines.append(f"{pad_end(r['account'], 22)} {pad_end('ok', 10)} memory {S(dig(mem, 'status'))}{': ' + S(mem['error']) if T(dig(mem, 'error')) else ''}")
            continue
        bs = nullish(dig(mem, "bundles"), [])
        if is_empty(bs):
            lines.append(f"{pad_end(r['account'], 22)} {pad_end('ok', 10)} no memory")
            continue
        for b in bs:
            rep_ = dig(b, "report")
            rep = (f"{S(dig(rep_, 'claims'))} claim(s), {S(jlen(dig(rep_, 'needs_rendering')))} need rendering, {S(jlen(dig(rep_, 'skipped_no_roles_class')))} skipped"
                   if T(rep_) else "no report")
            status = dig(b, "status")
            if status == "harvest-failed":
                why = ": " + " ".join(S(nullish(dig(b, "error"), "")).strip().split("\n")[-2:])
            elif status == "wrong-agent":
                why = f": manifest names {S(nullish(dig(b, 'manifest_agent'), 'nobody'))}"
            else:
                why = ""
            wc = dig(b, "working_copy")
            name = (js_basename(wc) + (" (projects root)" if T(dig(b, "projects_root")) else "")) if T(wc) else S(dig(b, "slug"))
            written = dig(b, "written")
            lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end('ok', 10)} {pad_end(name, 24)} {S(dig(b, 'files'))} memories  {S(status)}{why}"
                                  f"{' -> ' + S(written) if T(written) else ''}  {rep if status == 'ok' else ''}"))
    return lines


def _entries(o: Any) -> list[tuple[str, Any]]:
    """Object.entries(o): a string is its characters, an array its elements."""
    if isinstance(o, dict):
        return [(k, o[k]) for k in js.keys(o)]
    if isinstance(o, str):
        return [(str(i), c) for i, c in enumerate(o)]
    if isinstance(o, list):
        return [(str(i), v) for i, v in enumerate(o)]
    return []


def _table_script(rs: list) -> list[str]:
    def top(s: Any) -> Any:
        return None if not T(s) or dig(s, "status") != "ok" else s
    # The shares are the numeric entries but `letters` and `files`; the section's status, blocks and language ride beside them.

    def fmt(sh: Any) -> str:
        if not T(sh) or not T(dig(sh, "letters")):
            return "-"
        shares = [(k, v) for k, v in _entries(sh) if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in ("letters", "files")][:3]
        return ", ".join(f"{k} {S(v)}%" for k, v in shares) + f" ({S(sh['letters'])} letters)"

    def bins(b: Any) -> str:
        return "-" if not T(b) else f"{S(dig(b, 'only'))} only / {S(dig(b, 'mixed'))} mixed / {S(dig(b, 'latin'))} latin"

    def lang(l: Any) -> str:
        if not T(l):
            return ""
        if dig(l, "status") != "ok":
            return " — lang unavailable"
        if not T(dig(l, "paragraphs")):
            return ""
        shares = ", ".join(f"{k} {S(v)}%" for k, v in _entries(dig(l, "shares"))[:3]) or "-"
        return " — lang " + shares + (f" ({S(l['unreliable'])} unreliable)" if T(dig(l, "unreliable")) else "")

    def notes(n: Any) -> str:
        if dig(n, "status") == "not measured":
            return f"not measured: {S(dig(n, 'reason'))}"
        if not T(n) or dig(n, "status") != "ok":
            return "none"
        return f"{S(dig(n, 'files'))} file(s): {bins(dig(n, 'blocks'))}{lang(dig(n, 'language'))} — {fmt(n)}"

    def workers(w: Any) -> str:
        if not T(w) or dig(w, "status") != "ok":
            return "-"
        return (f"{S(dig(w, 'files'))} file(s): in {bins(dig(w, 'input', 'blocks'))}{lang(dig(w, 'input', 'language'))} / "
                f"out {bins(dig(w, 'text', 'blocks'))}{lang(dig(w, 'text', 'language'))}")
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} {pad_end('notes (the signature: paragraphs by script)', 70)} {pad_start('turns', 5)}  "
             f"{pad_end('text, by script', 44)} {pad_end('thinking (stored text only)', 40)} workers (input / answers)"]
    for r in rs:
        if r["status"] != "ok":
            lines.append(_row(r))
            continue
        s = top(r.get("script"))
        if s is None:
            lines.append(f"{pad_end(r['account'], 22)} {pad_end('ok', 10)} {pad_end(notes(dig(r['script'], 'notes')), 70)} {S(nullish(dig(r['script'], 'status'), '-'))}")
            continue
        tb = dig(s, "thinking_blocks")
        th = "-" if not T(tb) else f"{bins(tb)} / {S(dig(tb, 'empty'))} unreadable"
        lines.append(f"{pad_end(r['account'], 22)} {pad_end('ok', 10)} {pad_end(notes(dig(s, 'notes')), 70)} {pad_start(S(dig(s, 'turns')), 5)}  "
                     f"{pad_end(fmt(dig(s, 'text')), 44)} {pad_end(th, 40)} {workers(dig(s, 'workers'))}")
    return lines


def _table_recall(rs: list) -> list[str]:
    # Is the corpus read? One row per account: sessions in the window, how
    # many opened neither an index nor a slice, the reads by kind, and the
    # slice read most. Paths only, never text.
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} {pad_start('sessions', 8)} {pad_start('no recall', 9)} {pad_start('turns', 6)}  "
             f"{pad_start('index', 5)} {pad_start('slice', 5)} {pad_start('search', 6)} {pad_start('identity', 8)}  most read"]
    for r in rs:
        if r["status"] != "ok":
            lines.append(_row(r))
            continue
        c = r.get("recall")
        if not T(c) or dig(c, "status") != "ok":
            lines.append(f"{pad_end(r['account'], 22)} {pad_end('ok', 10)} {S(nullish(dig(c, 'status'), '-'))}")
            continue
        t0 = first(dig(c, "top"))
        most = f"{S(dig(t0, 'path'))} ({S(dig(t0, 'reads'))})" if T(t0) else "-"
        lines.append(f"{pad_end(r['account'], 22)} {pad_end('ok', 10)} {pad_start(S(dig(c, 'sessions')), 8)} {pad_start(S(dig(c, 'sessions_without_recall')), 9)} "
                     f"{pad_start(S(dig(c, 'turns')), 6)}  {pad_start(S(dig(c, 'index')), 5)} {pad_start(S(dig(c, 'slice')), 5)} {pad_start(S(dig(c, 'search')), 6)} "
                     f"{pad_start(S(dig(c, 'identity')), 8)}  {most}")
    return lines


def _G(n: Any) -> str:
    return "-" if n is None or n is UNDEFINED else S(n)


def _table_host(rs: list) -> list[str]:
    # Every daemon on a host reads the same machine, so the table is BY HOST:
    # the first answered row of each host speaks for it, the others only
    # count. A host none of whose accounts answered is a row too.
    by_host: dict[Any, list] = {}
    for r in rs:
        by_host.setdefault(r["host"], []).append(r)
    lines = [f"{pad_end('host', 16)} {pad_end('answered', 9)} {pad_end('load 1/5/15', 17)} {pad_start('cpus', 4)}  {pad_end('mem avail/total MB', 19)} "
             f"{pad_start('swap free', 9)}  {pad_end('balloon cur/max MB', 19)} disks"]
    for host, group in sorted(by_host.items(), key=lambda kv: collate(S(kv[0]))):
        oks = [r for r in group if r["status"] == "ok" and dig(r.get("machine"), "status") == "ok"]
        answered = f"{sum(1 for r in group if r['status'] == 'ok')}/{len(group)}"
        if not oks:
            # Every account failed or stayed silent: the failure text, then each account's own line.
            first = next((r for r in group if r["status"] == "ok"), None)
            f = first["machine"] if first else None
            lines.append(f"{pad_end(host, 16)} {pad_end(answered, 9)} {(S(dig(f, 'status')) + (': ' + S(f['error']) if T(dig(f, 'error')) else '')) if T(f) else 'no answer'}")
            for r in group:
                lines.append(f"{pad_end('', 16)} {pad_end('', 9)} {r['account']}: {S(nullish(dig(r['machine'], 'status'), '-')) if r['status'] == 'ok' else r['status']}")
            continue
        # The balloon's static-max is xenstore's, readable by the operator's
        # login and not by an account's: the row that has it speaks for the host.
        pick = next((r for r in oks if nullish(dig(r.get("machine"), "balloon_mb", "static_max"), None) is not None), oks[0])
        m = pick["machine"]
        loadavg = dig(m, "loadavg")
        load = " ".join(to_fixed(number_of(x), 2) for x in arr(loadavg)) if T(loadavg) else "-"
        mm = dig(m, "mem_mb")
        mem = f"{_G(dig(mm, 'available'))}/{_G(dig(mm, 'total'))}" if T(mm) else "-"
        swap = _G(dig(mm, "swap_free")) if T(mm) else "-"
        bb = dig(m, "balloon_mb")
        bal = f"{_G(dig(bb, 'current'))}/{_G(dig(bb, 'static_max'))}" if T(bb) else "none"
        disks = ", ".join(f"{S(dig(d, 'mount'))} {S(dig(d, 'avail_gb'))}G free ({S(dig(d, 'use_pct'))}%)" for d in arr(dig(m, "disk"))) or "-"
        lines.append(f"{pad_end(host, 16)} {pad_end(answered, 9)} {pad_end(load, 17)} {pad_start(_G(dig(m, 'cpus')), 4)}  {pad_end(mem, 19)} {pad_start(swap, 9)}  {pad_end(bal, 19)} {disks}")

        def lease(l: Any) -> str:
            since = dig(l, "since")
            return (f"{S(dig(l, 'name'))}{' (' + S(l['label']) + ')' if T(dig(l, 'label')) else ''}: {S(nullish(dig(l, 'holder'), '?'))}"
                    f"{' pid ' + S(l['pid']) if T(dig(l, 'pid')) else ''}{' since ' + usub(S(since), 11, 16) + 'Z' if T(since) else ''}")
        leases = "; ".join(lease(l) for l in arr(dig(m, "leases"))) or "none"
        top = ", ".join(f"{S(dig(p, 'comm'))} {S(dig(p, 'user'))} {S(dig(p, 'rss_mb'))} MB" for p in arr(dig(m, "top_rss"))[:5]) or "-"
        lines.append(f"{pad_end('', 16)} {pad_end('', 9)} leases: {leases}")
        lines.append(f"{pad_end('', 16)} {pad_end('', 9)} largest: {top}")
        lines.append(f"{pad_end('', 16)} {pad_end('', 9)} memory: {pressure_text([dig(r['machine'], 'memory_pressure') for r in oks])}")
        for r in group:
            if r["status"] != "ok":
                lines.append(f"{pad_end('', 16)} {pad_end('', 9)} {r['account']}: {r['status']}")
    return lines


def _table_keys(rs: list) -> list[str]:
    # One line per account: how many keys it holds, whether git can sign, and
    # whether its store refused a commit (ADR-042 rule 5) — a refusal is a
    # security event and is said until the store is repaired; the absent keys
    # follow, by name. Never a value.
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} {pad_end('keys', 8)} {pad_end('signing', 8)} store"]
    for r in rs:
        keys = r.get("keys")
        if r["status"] != "ok" or not isinstance(keys, list):
            lines.append(f"{pad_end(r['account'], 22)} {r['status'] if r['status'] != 'ok' else 'ok         keys ' + S(nullish(dig(keys, 'status'), '-'))}")
            continue
        named = [k for k in keys if dig(k, "name") not in ("signing key secret", "store commits verified")]
        sign = next((k for k in keys if dig(k, "name") == "signing key secret"), None)
        store = next((k for k in keys if dig(k, "name") == "store commits verified"), None)

        def refused_text(x: Any) -> str:
            return f"REFUSED {esc(dig(x, 'commit'))} at {esc(nullish(dig(x, 'at'), '?'))}: {esc(dig(x, 'reason'))}"
        if store is None:
            st = "-"
        elif T(dig(store, "refused")):
            st = refused_text(store["refused"])
        else:
            st = esc(nullish(dig(store, "state"), "verified" if T(dig(store, "present")) else "unreadable"))
        held = f"{sum(1 for k in named if T(dig(k, 'present')))}/{len(named)}"
        lines.append(f"{pad_end(r['account'], 22)} {pad_end('ok', 10)} {pad_end(held, 8)} {pad_end(('yes' if T(dig(sign, 'present')) else 'no') if sign is not None else '-', 8)} {st}")
        absent = [esc(dig(k, "name")) for k in named if not T(dig(k, "present"))]
        if absent:
            lines.append(f"{pad_end('', 22)} {pad_end('', 10)} absent: {', '.join(absent)}")
        mirrors = dig(store, "mirrors")
        for m in mirrors if isinstance(mirrors, list) else []:
            state = "refusal record unreadable" if T(dig(m, "unreadable")) else esc(m["state"]) if T(dig(m, "state")) else refused_text(m)
            lines.append(f"{pad_end('', 22)} {pad_end('', 10)} mirror of {esc(dig(m, 'agent_id'))}: {state}")
    return lines


def _table_disk(rs: list) -> list[str]:
    # One row per account, the largest home first: what /home is spent on, and
    # by whom; then the failed, then the silent, each by name. A size is
    # formatted only when it is a number; anything else the account sent is
    # shown as it came, escaped.
    def H(kb: Any) -> str:
        if kb is None or kb is UNDEFINED:
            return "-"
        if not _finite(kb):
            return esc(kb)
        return f"{to_fixed(kb / 1048576, 1)}G" if kb >= 1048576 else f"{to_fixed(kb / 1024, 0)}M" if kb >= 1024 else f"{S(kb)}K"
    lines = [f"{pad_end('account', 22)} {pad_end('status', 8)} {pad_start('total', 7)}  {pad_end('largest entry', 28)} {pad_start('target/', 7)}  target/ directories"]

    def rank(r: dict) -> int:
        d = r.get("disk")
        return 2 if r["status"] != "ok" or not T(d) else 1 if dig(d, "status") == "failed" or nullish(dig(d, "total_kb")) is None else 0

    def size(r: dict) -> float:
        return r.get("disk")["total_kb"] if rank(r) == 0 else 0

    def cmp(a: dict, b: dict) -> int:
        ra, rb = rank(a), rank(b)
        if ra != rb:
            return ra - rb
        sa, sb = size(a), size(b)
        sd = _js_sub(sb, sa)
        if sd != 0 and not (isinstance(sd, float) and math.isnan(sd)):
            return -1 if sd < 0 else 1
        ca, cb = collate(a["account"]), collate(b["account"])
        return -1 if ca < cb else 1 if ca > cb else 0
    for r in sorted(rs, key=functools.cmp_to_key(cmp)):
        d = r.get("disk")
        if _unless(r, d):
            lines.append(_row(r))
            continue
        if dig(d, "status") == "failed":
            lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end('failed', 8)} {esc(nullish(dig(d, 'error'), ''))}"))
            continue
        l0 = first(dig(d, "largest"))
        top = f"{esc(dig(l0, 'name'))} {H(dig(l0, 'kb'))}" if T(l0) else "-"
        targets = arr(dig(d, "targets"))
        shown = ", ".join(f"{esc(dig(t, 'path'))} {H(dig(t, 'kb'))}" for t in targets[:3]) + (f", +{len(targets) - 3}" if len(targets) > 3 else "")
        lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end(esc(dig(d, 'status')), 8)} {pad_start(H(dig(d, 'total_kb')), 7)}  {pad_end(top, 28)} "
                              f"{pad_start(H(dig(d, 'targets_kb')), 7)}  {shown or '-'}"))
        for e in arr(dig(d, "errors")):
            lines.append(f"{pad_end('', 22)} {pad_end('', 8)} {esc(e)}")
    return lines


def to_number(v: Any) -> float:
    """ToNumber for a JSON value: undefined is NaN, null 0, true 1, a string
    as Number() reads it, an array or object as Number(String(v))."""
    if v is UNDEFINED:
        return math.nan
    return number_of(v)


def _js_sub(a: Any, b: Any) -> float:
    return to_number(a) - to_number(b)


def js_add(a: Any, b: Any) -> Any:
    """a + b as JavaScript adds JSON values: a string, array or object on
    either side concatenates (their String()), otherwise the numbers add."""
    if any(isinstance(x, (str, list, dict)) for x in (a, b)):
        return S(a) + S(b)
    return to_number(a) + to_number(b)


def js_div(a: float, b: float) -> float:
    """a / b for doubles: x/0 is Infinity (or NaN for 0/0), never an error."""
    if b == 0:
        return math.nan if a == 0 or math.isnan(a) else math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


def js_ge(a: Any, b: float) -> bool:
    """a >= b for a number b: a string a is read as a number, NaN is never >=."""
    n = to_number(a)
    return not math.isnan(n) and n >= b


def _table_tokens(rs: list) -> list[str]:
    # Grouped by Claude account: a login's share is its direct-path
    # equivalents over the account's, from the logins that answered — the
    # meter counts what this host cannot see, so the shares are of the
    # visible spend. The broker column is the login's own key, no share.
    def M(n: Any) -> str:
        if js_ge(n, 1e9):
            return f"{to_fixed(to_number(n) / 1e9, 2)}G"
        if js_ge(n, 1e6):
            return f"{to_fixed(to_number(n) / 1e6, 1)}M"
        if js_ge(n, 1e3):
            return f"{to_fixed(to_number(n) / 1e3, 0)}k"
        return S(n)
    oks = [r for r in rs if r["status"] == "ok" and dig(r.get("tokens"), "status") == "ok"]
    days = nullish(dig(oks[0]["tokens"], "days"), "-") if oks else "-"
    by_account: dict[str, list] = {}
    for r in oks:
        by_account.setdefault(S(nullish(r["email"], "(no Claude account)")), []).append(r)

    def claude(r: dict, key: str) -> Any:
        return dig(r["tokens"], "claude", key)

    def broker(r: dict, key: str) -> Any:
        return dig(r["tokens"], "broker", key)
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} {pad_end('claude account', 30)} {pad_start('share', 6)}  {pad_start('claude equiv', 12)} "
             f"{pad_start('requests', 8)} {pad_start('cache read', 10)} {pad_start('output', 8)}  {pad_start('broker equiv', 12)} {pad_start('requests', 8)}  top model ({S(days)} days)"]
    for email, group in sorted(by_account.items(), key=lambda kv: collate(kv[0])):
        total: Any = 0
        for r in group:
            total = js_add(total, claude(r, "equiv"))

        def by_equiv(a: dict, b: dict) -> int:
            d = _js_sub(claude(b, "equiv"), claude(a, "equiv"))
            return 0 if d == 0 or math.isnan(d) else -1 if d < 0 else 1
        group.sort(key=functools.cmp_to_key(by_equiv))   # in place, as the Node's sort is: the sum line below reads the sorted order
        for r in group:
            models = _entries(dig(r["tokens"], "models"))
            top = models[0] if models else None
            if T(total):
                share = f"{pad_start(to_fixed(js_div(100 * to_number(claude(r, 'equiv')), to_number(total)), 0), 5)}%"
            else:
                share = "     -"
            lines.append(trim_end(f"{pad_end(r['account'], 22)} {pad_end('ok', 10)} {pad_end(email, 30)} {share}  {pad_start(M(claude(r, 'equiv')), 12)} "
                                  f"{pad_start(S(claude(r, 'requests')), 8)} {pad_start(M(claude(r, 'cache_read')), 10)} {pad_start(M(claude(r, 'output')), 8)}  "
                                  f"{pad_start(M(broker(r, 'equiv')), 12)} {pad_start(S(broker(r, 'requests')), 8)}  {top[0] + ' ' + M(dig(top[1], 'equiv')) if top else '-'}"))
        if len(group) > 1:
            requests: Any = 0
            for r in group:
                requests = js_add(requests, claude(r, "requests"))
            lines.append(f"{pad_end('', 22)} {pad_end('', 10)} {pad_end('= ' + email, 30)} {pad_start(' 100%', 6)}  {pad_start(M(total), 12)} {pad_start(S(requests), 8)}")
    for r in rs:
        if not (r["status"] == "ok" and dig(r.get("tokens"), "status") == "ok"):
            lines.append(f"{pad_end(r['account'], 22)} {r['status'] if r['status'] != 'ok' else 'ok         ' + pad_end(S(nullish(r['email'], '-')), 30) + ' tokens ' + S(nullish(dig(r.get('tokens'), 'status'), '-'))}")
    return lines


def _drift_cells(r: dict) -> str:
    """The harness and inbox cells of a status row (tools/fabric/drift.py), named when they are wrong and
    empty for a control agent that does not answer them: Claude Code installed against the pin, and the
    oldest message the account has not read, when it is over a day old."""
    out = ""
    h = r.get("harness")
    if isinstance(h, dict):
        if h.get("status") != "ok":
            out += "  claude ?"
        elif h.get("drift") is True:
            out += f"  claude {esc(h['installed'])} DRIFT (pin {esc(h['pinned'])})"
        elif h.get("pinned") is None:
            out += f"  claude {esc(h['installed'])} (no pin)"
        else:
            out += f"  claude {esc(h['installed'])}"
    i = r.get("inbox")
    if isinstance(i, dict) and i.get("status") != "none":
        if i.get("status") != "ok" or i.get("lagging") is None:
            out += "  inbox ?"
        elif i["lagging"]:
            out += f"  inbox LAG {_age(i['lag_s'])} ({S(i['unread'])}{'+' if i.get('capped') else ''} unread)"
    return out


def _table_status(rs: list) -> list[str]:
    lines = [f"{pad_end('account', 22)} {pad_end('status', 10)} {pad_end('claude account', 30)} {pad_start('5h', 4)}  {pad_end('5h resets (UTC)', 16)} {pad_start('7d', 4)}  "
             f"{pad_end('7d resets (UTC)', 16)} {pad_end('role', 18)} fabric"]
    for r in rs:
        if r["status"] != "ok":
            lines.append(_row(r))
            continue
        fb = r.get("fabric")
        if dig(fb, "status") == "ok":
            fab = f"{S(fb['head'])}{' (' + S(fb['behind']) + ' behind)' if T(dig(fb, 'behind')) else ''}{' dirty' if T(dig(fb, 'dirty')) else ''}"
        else:
            fab = S(nullish(dig(fb, "status"), "-"))
        usage = (f"{pct(r['five_hour'])}  {pad_end(at(r['five_hour']), 16)} {pct(r['seven_day'])}  {pad_end(at(r['seven_day']), 16)}"
                 if r.get("usage_status") == "ok" else pad_end(S(nullish(r.get("usage_status"), "-")), 42))
        lines.append(f"{pad_end(r['account'], 22)} {pad_end('ok', 10)} {pad_end(S(nullish(r['email'], '-')), 30)} {usage} {pad_end(S(nullish(r['role'], '-')), 18)} {fab}"
                     + _drift_cells(r))
    return lines


def table(op: str, rs: list) -> str:
    if op == "secrets-selftest":
        lines = _table_selftest(rs)
    elif op == "secrets-sync":
        lines = _table_secrets_sync(rs)
    elif op in ("local", "local-prune"):
        lines = _table_local(op, rs)
    elif op == "jobs":
        lines = _table_jobs(rs)
    elif op == "tools":
        lines = _table_tools(rs)
    elif op == "tools-install":
        lines = _table_tools_install(rs)
    elif op == "gateway":
        lines = _table_gateway(rs)
    elif op == "gateway-install":
        lines = _table_gateway_install(rs)
    elif op == "jobs-add":
        lines = _table_jobs_add(rs)
    elif op == "pool-add":
        lines = _table_pool_add(rs)
    elif op == "presence":
        lines = _table_presence(rs)
    elif op == "upgrade":
        lines = _table_upgrade(rs)
    elif op == "accounts":
        lines = _table_accounts(rs)
    elif op == "ping":
        lines = _table_ping(rs)
    elif op == "memory":
        lines = _table_memory(rs)
    elif op == "script":
        lines = _table_script(rs)
    elif op == "recall":
        lines = _table_recall(rs)
    elif op == "host":
        lines = _table_host(rs)
    elif op == "keys":
        lines = _table_keys(rs)
    elif op == "disk":
        lines = _table_disk(rs)
    elif op == "tokens":
        lines = _table_tokens(rs)
    else:
        lines = _table_status(rs)
    return "\n".join(lines)


# ── asking ──────────────────────────────────────────────────────────

def _out(m: str) -> None:
    sys.stdout.write(m + "\n")
    sys.stdout.flush()


def _err(m: str) -> None:
    sys.stderr.write(m + "\n")
    sys.stderr.flush()


def _agentd():
    from control import agentd
    return agentd


def main(argv: list[str] | None = None, *, registry: str | None = None, call: Callable[..., Any] | None = None,
         out: Callable[[str], None] = _out, err: Callable[[str], None] = _err, sleep: Callable[[float], None] = time.sleep,
         now: Callable[[], float] = time.time, who: dict | None = None, token: str | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = parse_args(argv)
    except CtlError as e:
        err(f"fabric-ctl: {e}")
        return 2
    if args.get("help") or (not args["targets"] and args["op"] != "keygen"):
        err(USAGE)
        return 0 if args.get("help") else 2
    if args["op"] == "keygen":
        return keygen(args, registry=registry, who=who, out=out, err=err)
    agentd = _agentd()
    picked = targets_of(args["targets"], placements(registry))
    if "refused" in picked:
        err(f"fabric-ctl: {picked['refused']}")
        return 2
    expected, everyone = picked["expected"], picked.get("everyone", False)
    if args["op"] == "pool-add":
        holder = pool_holder(agentd.control_config(), registry)
        if not expected or expected[0]["address"] != holder:
            err(f"fabric-ctl: {holder + ' holds the pool, not ' + (expected[0]['address'] if expected else 'undefined') if holder else 'no account holds the pool: several hosts and no pool_holder in runtime/control/config.json'}; nothing sent")
            return 2
    who = gz_whoami() if who is None else who
    me = {"address": f"{who['host']}/{who['agent']}"}
    cfg = agentd.control_config()
    gz = integration_config(who.get("project"))
    tok = token if token is not None else gz_token(inbox_root(who), gz if gz.get("configured") else None)
    if tok is None:
        tok = synced_token()   # `??`: a token that is empty is a token, and refused as one
    api_call = call or (lambda p, **init: api(tok, p, relay_url=cfg["relay_url"], **init))
    if args["op"] == "states":
        # A read of the channel, not a request: no daemon is asked and none
        # answers, so no operator check — the relay token is the gate.
        if not tok:
            err("fabric-ctl: no CLAUDE_BRIDGE_AUTH_TOKEN (fabric-secrets sync)")
            return 3
        # states reads milliseconds (Date.now, Date.parse); this clock counts seconds.
        return states(args, expected, call=api_call, cfg=cfg, out=out, err=err, now=lambda: now() * 1000, sleep=sleep)
    # What the daemons will answer: an operator anything, a placed account a public op (agentd accept()).
    if me["address"] not in agentd.operator_addresses(registry) and not (args["op"] in PUBLIC_OPS and me["address"] in agentd.account_addresses(registry)):
        err(f"fabric-ctl: {me['address']} is not a host operator in runtime/hosts/registry.json — no agent would answer; not sent")
        return 2
    if not tok:
        err("fabric-ctl: no CLAUDE_BRIDGE_AUTH_TOKEN (fabric-secrets sync)")
        return 3
    rid = agentd.new_id()
    # An action's signed ttl_s is how long an account may still ACCEPT it,
    # capped; how long this command waits for replies is --timeout, which for
    # a queued fleet upgrade is far longer — the last account replies long
    # after every account accepted.
    request = build_request(args, id=rid, from_=me["address"], to="*" if everyone else [e["address"] for e in expected], cfg=cfg)
    # One command, one version: the coordinator's pin travels in the signed
    # request. Left to each account, an account that had not pulled the pin
    # bump would read its own older pin and answer `current` (review of #34).
    if args["op"] == "upgrade" and args["piece"] == "fabric" and not T(request["args"]["commit"]):
        err(f"fabric-ctl: could not read origin/main in {FABRIC_ROOT} after a fetch; nothing sent")
        return 2
    if args["op"] == "upgrade" and args["piece"] != "fabric" and not T(request["args"]["version"]):
        err(f"fabric-ctl: no pinned version in {os.path.join(FABRIC_ROOT, 'runtime', 'claude-code', 'harness.json')} and no --version; nothing sent")
        return 2
    if args["op"] in ACTION_OPS:
        # An action is signed or not sent: an unsigned one is refused by every
        # daemon, and a silent table would read as agents that did not answer.
        k = signing_key()
        if "error" in k:
            err(f"fabric-ctl: {k['error']} — an action is signed or not sent")
            return 3
        try:
            request = sign_request(request, k["key"])
        except Exception as e:  # noqa: BLE001 — the signer's own words, as the Node said them
            err(f"fabric-ctl: {e}")
            return 3
    try:
        sent = api_call("/api/send", method="POST", body=js.stringify({"channel": cfg["channel"], "sender": me["address"], "content": js.stringify(request)}))
    except Exception as e:  # noqa: BLE001 — any failure of the call is said in relay_failure's words, as the Node said it
        err(f"fabric-ctl: {relay_failure(e, cfg['relay_url'])}")
        return 3
    t0 = now()
    replies: list[dict] = []
    parts: dict[str, dict] = {}
    want = {e["address"] for e in expected}   # no reply yet

    def short() -> int:
        """A memory reply is complete only when every part it announced arrived."""
        if args["op"] != "memory":
            return 0
        return sum(1 for r in replies if len(parts.get(r["from"], {})) < _int(dig(r, "data", "parts")))
    deadline = t0 + args["timeout"]
    since = sent["id"]
    while now() < deadline and (want or short()):
        try:
            page = api_call("/api/messages?" + js.search_params([("channel", cfg["channel"]), ("since_id", since), ("limit", "500"), ("full", "1")]))
        except Exception as e:  # noqa: BLE001 — the loop ends and the silent accounts are rows; the line says why
            err(f"fabric-ctl: relay read failed ({e})")
            break
        if dig(page, "warning") == "since_id_not_found":
            err("fabric-ctl: the relay no longer holds the request (history cleared); the replies cannot be read")
            break
        messages = dig(page, "messages")
        for rec in messages if isinstance(messages, list) else []:
            if not isinstance(rec, dict):
                continue
            if "id" in rec:
                since = rec["id"]
            try:
                r = js.json_parse(rec["content"])
            except (ValueError, KeyError, TypeError):
                continue
            if dig(r, "kind") != "reply" or dig(r, "in_reply_to") != rid:
                continue
            frm = dig(r, "from")
            if T(dig(r, "data", "part")):
                # Distinct parts, keyed by slug and number, the first record for a key winning:
                # a replayed or duplicated part neither completes a reply early nor breaks its reassembly.
                part = r["data"]["part"]
                m = parts.setdefault(S(frm), {})
                k = part_key(frm, part)
                if k not in m:
                    m[k] = part
                continue
            if isinstance(frm, str) and frm in want:
                r["latency_ms"] = int((now() - t0) * 1000)
                replies.append(r)
                want.discard(frm)
        if want or short():
            sleep(0.5)
    refused = 0
    if args["op"] == "memory":
        write_bundles(args["out"], expected, replies, parts)
        for r in replies:
            mem = dig(r, "data", "memory")
            if T(mem) and dig(mem, "status") != "ok":
                refused += 1
            bundles = dig(mem, "bundles")
            if isinstance(bundles, list):
                refused += sum(1 for b in bundles if dig(b, "status") not in ("ok", "no-working-copy"))
            elif bundles is not UNDEFINED and bundles is not None:
                # The Node walks a string's characters, each one a bundle with no status, and
                # throws on anything else: either way the drain is not a success.
                refused += len(bundles) if isinstance(bundles, str) else 1
    rs = rows(expected, replies)
    if args["json"]:
        for r in rs:
            out(js.stringify(r))
    else:
        out(table(args["op"], rs))
    # An action that failed on an account is a failed run, whatever else
    # answered: the first fleet upgrade printed nine failed rows and exited 0.
    action_failed = args["op"] in ACTION_OPS and any(dig(r, "data", args["op"], "status") not in ACTION_OK.get(args["op"], []) for r in replies)
    return 1 if want or short() or refused or action_failed else 0


def _int(v: Any) -> float:
    """`(r.data?.parts ?? 0)` compared with a count: a number, or what it turns into."""
    v = nullish(v, 0)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else number_of(v)


# ── states ──────────────────────────────────────────────────────────
#
# The state records agentd posts (control/sessions) on the state channel, a
# channel of their own so a burst on the control channel (a drain's hundreds
# of parts) never pushes them out of reach. The snapshot is the newest record
# per expected address among the last STATES_REPLAY there. --follow then
# waits on the channel and prints an account's row whenever it changes: a new
# record that says something new, or a record that has aged past
# STATES_STALE_MS — the account's daemon has not spoken for two heartbeats, so
# its sessions are unknown, not what it last said. Each wait returns within a
# minute and an unreachable relay is retried every five seconds, so a row goes
# unknown within a minute of its deadline, whether or not the relay answers. A
# lost cursor re-reads the snapshot, never skipping what it anchors on. With
# --json, one object per line — what a listening program reads.

STATES_REPLAY = 500
STATES_STALE_MS = 2 * 10 * 60 * 1000
UNREADABLE = "unreadable"       # control/sessions.py's: what a state record's `sessions` says when the account cannot read it
RANK = {"blocked": 3, "working": 2, "idle": 1}


def state_row(address: str, rec: Any, now: float | None = None) -> dict:
    """One account's line: the state that most wants a person, and since when."""
    now = time.time() * 1000 if now is None else now
    if not T(rec):
        return {"address": address, "state": "unknown", "sessions": [], "why": "no state record on the channel"}
    ts = js.string(rec["ts"])
    stale = now - _date_parse(ts) > STATES_STALE_MS
    unreadable = rec.get("sessions") == UNREADABLE
    sessions = rec["sessions"] if isinstance(rec.get("sessions"), list) else []
    top = None
    for s in sessions:
        if RANK.get(dig(s, "state"), 0) > RANK.get(dig(top, "state"), 0):
            top = s
    row = {"address": address, "ts": rec["ts"], "role": nullish(rec.get("role"), None), "project": nullish(rec.get("project"), None), "sessions": sessions,
           "state": "unknown" if stale or unreadable else top["state"] if top is not None else "none", "since": nullish(dig(top, "since"), None)}
    # What the top session adds (fleet-deck-attention s3), each only where agentd said it.
    for key in ("reason", "context", "activity"):
        if not (stale or unreadable) and top is not None and dig(top, key) is not UNDEFINED and dig(top, key) is not None:
            row[key] = top[key]
    # What the deck resumes (docs/fleet-deck/session-recovery.md): carried as
    # agentd wrote it, absent when it wrote none.
    if T(rec.get("last_session")):
        row["last_session"] = rec["last_session"]
        row["resumable"] = rec.get("resumable") is True
    if stale:       # an old record says nothing about now, whatever it said: this why first
        row["why"] = "no record for two heartbeats"
    elif unreadable:
        row["why"] = "the account cannot read its session state"
    return row


def _date_parse(ts: str) -> float:
    from control.ops import util
    ms = util.date_parse_ms(ts)
    return math.nan if ms is None else ms


def _str(v: Any) -> bool:
    return isinstance(v, str)


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _opt(v: Any) -> bool:
    return v is None or _str(v)


def state_record_of(rec: Any, want: set) -> dict | None:
    """The channel takes any relay-token holder's post: a record is shown only
    when every field the row reads has the shape agentd writes, so a forged one
    can mislead a row, never stop the table."""
    try:
        r = js.json_parse(dig(rec, "content"))
    except (ValueError, TypeError):
        return None
    if not isinstance(r, dict) or r.get("kind") != "state" or not _num(r.get("v")) or r["v"] != 1:
        return None
    if not isinstance(r.get("from"), str) or r["from"] not in want:
        return None
    if not (_str(r.get("ts")) and _opt(r.get("role")) and _opt(r.get("project"))):
        return None
    ls = r.get("last_session", UNDEFINED)
    if ls is not UNDEFINED and not (_str(ls) and SESSION_ID.fullmatch(ls)):
        return None
    rb = r.get("resumable", UNDEFINED)
    if rb is not UNDEFINED and not isinstance(rb, bool):
        return None
    sessions = r.get("sessions")
    if sessions == UNREADABLE:
        return r          # the account says it cannot read its session state (j68): a string, nothing to check inside it
    if not isinstance(sessions, list):
        return None
    for s in sessions:
        if not (isinstance(s, dict) and _str(s.get("session")) and _str(s.get("state")) and (s.get("since") is None or _str(s.get("since")))):
            return None
        if not _session_extras_ok(s):
            return None
    return r


def _session_extras_ok(s: dict) -> bool:
    """The optional fields of a session (fleet-deck-attention s3) have the shape agentd writes, or are absent."""
    if s.get("reason") not in (None, "permission", "question") or s.get("activity") not in (None, "recent", "quiet"):
        return False
    c = s.get("context")
    if c is None:
        return True
    # The same time form as fleet's attention_time and sessions.read_contexts: a different one would pass here and be null there.
    return (isinstance(c, dict) and isinstance(c.get("pct"), int) and not isinstance(c.get("pct"), bool)
            and 0 <= c["pct"] <= 100 and _str(c.get("at")) and bool(SAMPLE_TIME.fullmatch(c["at"])))


SAMPLE_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z", re.ASCII)
_PRINTABLE = re.compile("[\u0000-\u001f\u007f-\u009f]")


def printable(v: Any) -> str:
    """A role, project or session id is a forger's text too: in the table it
    reaches a terminal, so control characters (an escape sequence that
    retitles the window or writes the clipboard) never do."""
    return _PRINTABLE.sub("?", S(v))


def states(args: dict, expected: list[dict], *, call: Callable[..., Any], cfg: dict, out: Callable[[str], None] = _out,
           err: Callable[[str], None] = _err, now: Callable[[], float] | None = None, sleep: Callable[[float], None] = time.sleep,
           forever: bool = True) -> int:
    clock = now or (lambda: time.time() * 1000)
    want = {e["address"] for e in expected}
    channel = cfg["state_channel"]

    def line(row: dict) -> str:
        if args["json"]:
            return js.stringify(row)
        n = len(row["sessions"])
        return (f"{pad_end(row['address'], 32)} {pad_end(printable(row['state']), 8)} {pad_end(printable(nullish(row.get('role'), '-')), 18)} "
                f"{n} session{'' if n == 1 else 's'}{'  since ' + printable(row['since']) if T(row.get('since')) else ''}{'  (' + row['why'] + ')' if row.get('why') else ''}")
    latest: dict[str, dict] = {}
    shown: dict[str, str] = {}   # address → the row last printed, without its ts: a heartbeat that says nothing new prints nothing

    def show(address: str, force: bool = False) -> None:
        row = state_row(address, latest.get(address), clock())
        said = {k: v for k, v in row.items() if k != "ts"}
        # Text prints neither activity nor the context sample: a row that differs only in them is the same line.
        key = js.stringify(said) if args["json"] else line(row)
        if not force and shown.get(address) == key:
            return
        shown[address] = key
        out(line(row))

    def take(rows_: list) -> None:
        for rec in rows_:
            if not T(rec):
                continue
            r = state_record_of(rec, want)
            if r:
                latest[r["from"]] = r

    def snapshot() -> Any:
        """The newest records on the channel, read into `latest`; the last id, or None on an empty channel."""
        page = call("/api/messages?" + js.search_params([("channel", channel), ("limit", str(STATES_REPLAY)), ("full", "1")]))
        rows_ = page["messages"] if isinstance(dig(page, "messages"), list) else []
        take(rows_)
        return dig(rows_[-1], "id") if rows_ and dig(rows_[-1], "id") not in (UNDEFINED, None) else None
    try:
        last = snapshot()
    except Exception as e:  # noqa: BLE001 — any failure of the read is the relay's, said as relay_failure says it
        err(f"fabric-ctl: {relay_failure(e, cfg['relay_url'])}")
        return 3
    for e in expected:
        show(e["address"], True)
    if not args["follow"]:
        return 0 if all(a in latest for a in want) else 1
    down = False
    while True:
        # Only the relay calls are in the try: an outage is said as one, and
        # nothing a record holds can be mistaken for it.
        w = None
        try:
            if not last:
                last = snapshot()
            if last:
                w = call("/api/wait?" + js.search_params([("channel", channel), ("since_id", last), ("timeout_seconds", "55"), ("limit", "50"), ("full", "1")]))
        except Exception as e:  # noqa: BLE001 — see above
            if not down:
                err(f"fabric-ctl: relay unreachable at {cfg['relay_url']} ({e}) — retrying every 5 s")
                down = True
            # What this side cannot read has grown old all the same: a row past
            # its deadline goes unknown during the outage, not after it.
            for a in expected:
                show(a["address"])
            sleep(5)
            if not forever:
                return 0
            continue
        if down:
            err("fabric-ctl: relay is back")
            down = False
        if dig(w, "warning") == "since_id_not_found":
            last = None
        else:
            rows_ = w["messages"] if isinstance(dig(w, "messages"), list) else []
            for rec in rows_:
                if T(dig(rec, "id")):
                    last = rec["id"]
            take(rows_)
        # Every account, every turn: a record that arrived changes a row, and
        # so does one that has only grown old.
        for e in expected:
            show(e["address"])
        if not last:
            sleep(5)   # an empty channel: nothing to wait after yet
        if not forever:
            return 0


# ── the signing key ─────────────────────────────────────────────────
#
# The operator's signing key, decrypted from this login's own store at the
# moment an action is signed, and never read from the environment: ~/.bashrc
# sourced secrets.env before ADR-038 rule 9, so a synced key sat in every
# shell and subagent of the account, and a reviewer printed its environment
# (key rotated, #95). gpg hands the value to this process on its stdout pipe
# — never argv, never a file — with secret_store.py gpg()'s flags. Each way it
# can fail is its own line, and none of them carries the value.

SIGNING_KEY_NAME = "FABRIC_CONTROL_SIGNING_KEY"
DECRYPT_TIMEOUT_S = 30


def store_dir(env: dict[str, str] | None = None, home: str | None = None) -> str:
    """secret_store.py store_dir(), its `or` included: an empty variable is unset."""
    env = os.environ if env is None else env
    home = os.path.expanduser("~") if home is None else home
    return env.get("AGENT_FABRIC_SECRET_STORE") or os.path.join(home, ".local", "share", "agent-fabric", "secrets")


def signing_key(store: str | None = None, run: Callable[..., Any] = subprocess.run) -> dict:
    store = store_dir() if store is None else store
    file = os.path.join(store, "env", f"{SIGNING_KEY_NAME}.gpg")
    try:
        os.stat(store)
    except OSError as e:
        code = _code(e)
        return {"error": f"no secret store at {store} (fabric-secrets store init)" if code == "ENOENT" else f"cannot read the secret store {store} ({code})"}
    if not os.access(file, os.R_OK):
        try:
            os.stat(file)
            code = "EACCES"
        except OSError as e:
            code = _code(e)
        return {"error": f"no {SIGNING_KEY_NAME} in this login's store — fabric-ctl keygen makes it" if code == "ENOENT" else f"cannot read {file} ({code})"}
    cmd = ["gpg", "--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback", "--passphrase", "", "--decrypt", file]
    try:
        r = run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=DECRYPT_TIMEOUT_S, check=False)
    except FileNotFoundError:
        return {"error": "gpg not found; the signing key cannot be decrypted"}
    except subprocess.TimeoutExpired:
        return {"error": f"gpg --decrypt of {SIGNING_KEY_NAME} timed out after {DECRYPT_TIMEOUT_S} s"}
    except OSError as e:
        return {"error": f"gpg --decrypt of {SIGNING_KEY_NAME}: {e.strerror or e}"}
    if r.returncode != 0:
        # gpg's last line names why (no secret key, bad data); its stderr never holds the plaintext.
        lines = (r.stderr or "").strip().split("\n")
        why = lines[-1] or (f"killed by {signal_name(-r.returncode)}" if r.returncode < 0 else f"exit {r.returncode}")
        return {"error": f"gpg --decrypt of {SIGNING_KEY_NAME} failed: {why}"}
    # pass(1)'s layout: the value is the first line.
    key = js.trim((r.stdout or "").split("\n")[0])
    return {"key": key} if key else {"error": f"{SIGNING_KEY_NAME} in this login's store is empty — fabric-ctl keygen --force replaces it"}


def _code(e: OSError) -> str:
    import errno
    return errno.errorcode.get(e.errno or 0, "EIO")


def signal_name(n: int) -> str:
    import signal
    try:
        return signal.Signals(n).name
    except ValueError:
        return str(n)


def keygen(args: dict, *, registry: str | None = None, run: Callable[..., Any] = subprocess.run, who: dict | None = None,
           out: Callable[[str], None] = _out, err: Callable[[str], None] = _err) -> int:
    """The operator's signing key, made once (or rotated): the private half
    goes from this process into the operator's own store on stdin — never
    printed, never a file — and the public half into this host's
    `operator_key` in the registry, to commit like any other change. A key
    already registered is kept unless --force: a rotation invalidates every
    daemon's trust until the registry change is pulled."""
    registry = roots.hosts_registry(engine=FABRIC_ROOT, empty_is_set=True) if registry is None else registry
    who = gz_whoami() if who is None else who
    with open(registry, encoding="utf-8", errors="replace") as fh:
        reg = js.json_parse(fh.read())
    host = dig(reg, "hosts", who["host"])
    if not T(host) or nullish(dig(host, "operator"), "user") != who["agent"]:
        err(f"fabric-ctl: {who['host']}/{who['agent']} is not this host's operator in the registry; no key made")
        return 2
    if public_key_from(dig(host, "operator_key")) and not args["force"]:
        err("fabric-ctl: this host already has an operator_key; --force to rotate it")
        return 2
    k = generate_operator_key()
    run([os.path.join(FABRIC_ROOT, "bin", "fabric-secrets"), "store", "set", "--managed", "FABRIC_CONTROL_SIGNING_KEY"], input=k["privateKeySpec"],
        text=True, stdout=subprocess.DEVNULL, stderr=None, check=True, timeout=120)
    host["operator_key"] = k["publicKeySpec"]
    with open(registry, "w", encoding="utf-8") as fh:
        fh.write(js.stringify(reg, 2) + "\n")
    out(f"fabric-ctl: signing key made — private half in this login's store (FABRIC_CONTROL_SIGNING_KEY), public half in "
        f"{os.path.relpath(registry, FABRIC_ROOT)} (operator_key of {who['host']}).")
    # No sync: the key is never written into secrets.env (secrets_sync.py
    # STORE_ONLY); signing decrypts it from the store (review of #96).
    out("  next: commit the registry change; the fleet trusts it once it has pulled that commit.")
    return 0


def cli() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001 — the Node's top-level catch: one line, exit 1, never a traceback
        _err(f"fabric-ctl: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(cli())
