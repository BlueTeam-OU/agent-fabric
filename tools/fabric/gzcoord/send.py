"""tools/fabric/gzcoord/send.py — send ONE message over the relay. Ported
from communication/gzcoord/scripts/send.mjs (agent-fabric ADR-040 §7,
Wave 7); that path is now a shim that runs this.

CONTRACT, frozen from the Node:
  argv      <file> | -   [--dry-run] [--force]   the first argument not
            starting with `--` is the file (`-` is stdin); other flags are
            ignored, as they were
  env       what inbox reads (integration, token, AGENT_FABRIC_ROOT,
            AGENT_FABRIC_STATE_DIR), GZCOORD_JOURNAL=off,
            AGENT_FABRIC_FALLBACK_DIR and CLAUDE_PID (the fallback
            reminder), AGENT_FABRIC_JOBS_AUTO_INTAKE=1 (off unless exactly
            1), GZCOORD_PRESENCE_WAIT_MS (the presence CLI's),
            AGENT_FABRIC_HOSTS_REGISTRY / AGENT_FABRIC_OPERATOR (the hosts
            registry a REQUEST's job intake reads)
  stdout    `sent seq <n> <TYPE> <id>` and nothing else
  stderr    everything else: the id minted, warnings, refusals, presence,
            the journal's own lines, fabric-jobs's own lines, and for a
            REQUEST to a login (intake.py) one line: `queued as jN on
            <address>'s job list`, or why it was not
  exit      0 sent (a dry run: validated and resolved); 1 usage or
            unreadable input, or the id could not be written into the
            file; 2 invalid, FROM not this login, an id already sent with
            other text, a control channel, a journal that cannot keep
            the message, or (GZCOORD_JOURNAL=off) a bypass that cannot
            be recorded; 3 not configured, no token, relay unreachable,
            the token refused, or a post whose outcome is unknown (it may
            have been delivered); 4 an addressee with no session, silent, not
            placed, or presence not askable — unless --force

After a REQUEST TO a login is posted by that login's host operator, the
send may run fabric-ctl (up to two calls, 30 s each) to put the job on the
addressee's list (intake.py); a failure there is a stderr line and never
changes the exit status.

The message is normalized (a pasted body carries terminal indentation),
validated as the last step before it leaves (SPEC §1) — a message that
fails is not sent — and refused when its FROM is not this session's own
address: the sender is the login, and a message claiming another one
would be misattributed on every recipient's cursor.

A message with no MESSAGE-ID gets one here, written into the file before
anything else happens, so sending the same file again — a retry after an
unknown outcome — carries the same id and every reader discards the copy
(SPEC §7.2). Minting by hand and substituting a placeholder put a command
on the owner's screen that showed something other than what was sent
(2026-09-26). A present id is kept; a placeholder is refused. From stdin
there is no file to keep it in, and that is said; a dry run mints in
memory only.

An id travels with its file, so a scratch file reused for the NEXT message
would carry the last one's id (review of #47, R1). Each confirmed send is
recorded — id and a hash of the message — in this login's state directory
(<state>/agents/<login>/gzcoord-sent.jsonl), and an id that already went
out with other content is refused; the same message again passes. A post
whose reply was lost is not recorded, so an edited resend under that id is
not caught.

PRESENCE, and why it is the control plane's process, not a copy here: a
TO or TO-ROLE message asks whether its addressee has a session before it
leaves. That question goes over the control channel, whose request and
reply shapes are the control plane's (runtime/control/presence.mjs, kept
in Node by ADR-040 §7); a Python copy would be a second implementation of
them to keep in step. So this runs `node runtime/control/presence.mjs
check` (the coordinator's decision, 2026-10-04): one implementation,
changed once. It runs only for an addressed send, beside a wait of up to
six seconds. A timeout, a missing node or an answer that cannot be read
is "unavailable" — never present.

THE JOURNAL (ADR-041), in this process: kept before the carrier sees it,
its outcome after, once it is known (accepted, or failed when the relay
provably does not hold it; otherwise the row stays pending, "may have
reached the carrier"); a journal that cannot take it refuses the send — a
carrier may keep no copy, so a message sent unremembered could be gone
for good. GZCOORD_JOURNAL=off sends without it and says so every time:
first a "pending" line in journal-bypass.jsonl (gzcoord/bypass.py), and
a bypass that cannot be recorded is refused, exit 2; then, once the post
is over, an "accepted", "failed" or "unknown" line (said, never a
refusal, when it cannot be written).
The order is the protocol's and is kept.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import stat
import subprocess
import sys
from typing import Any, Callable

from . import bypass, gzmsg, i18n, inbox, intake, paths
from . import jsvalues as js


def fallback_marker(directory: str | None = None, pid: int | None = None) -> dict | None:
    """The fallback marker for this harness session (CLAUDE_PID), if any,
    from the login's own directory; one naming a dead pid is not one."""
    directory = os.environ.get("AGENT_FABRIC_FALLBACK_DIR",
                               os.path.join(os.path.expanduser("~"), ".cache", "agent-fabric", "fallback")) \
        if directory is None else directory
    if pid is None:
        n = js.number(os.environ.get("CLAUDE_PID", js.UNDEFINED))
        pid = int(n) if js.truthy_number(n) and js.is_integer(n) else 0
    try:
        own = os.path.join(directory, f"{pid}.json")
        if pid > 0 and os.path.exists(own):
            candidates = [own]
        else:
            candidates = [os.path.join(directory, n) for n in os.listdir(directory) if _marker_name(n)]
    except OSError:
        return None
    for f in candidates:
        try:
            if os.lstat(f).st_uid != os.getuid():
                continue
            with open(f, encoding="utf-8") as fh:
                m = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(m, dict):
            continue
        p = m.get("pid")
        if not ((isinstance(p, int) and not isinstance(p, bool)) or (isinstance(p, float) and p.is_integer())) or p <= 0:
            continue
        if not inbox.pid_alive(int(p)):
            continue
        return m
    return None


def _marker_name(n: str) -> bool:
    return n.endswith(".json") and n[:-5].isdigit() and n[:-5].isascii()


def with_message_id(text: str, mid: str) -> str:
    """The id goes last in the metadata block: every line after the header
    up to the first blank line or section marker (SPEC §6)."""
    lines = text.split("\n")
    end = 1
    while end < len(lines) and gzmsg.js_trim(lines[end]) != "" and gzmsg._KEY_LINE.match(lines[end]):
        end += 1
    lines.insert(end, f"MESSAGE-ID: {mid}")
    return "\n".join(lines)


def sent_ledger_path(who: dict) -> str:
    return os.path.join(os.path.dirname(who["binding"]), "gzcoord-sent.jsonl")


def _ledger(path: str, flags: int):
    """The ledger opened as a regular file or not at all: never followed
    through a symlink, never waited on as a FIFO (a send would hang before
    its post, and under the agent's lock in record_sent). Anything else
    there is refused with an OSError naming it."""
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f"{path} is not a regular file")
    except BaseException:
        os.close(fd)
        raise
    return fd


def spent_elsewhere(ledger: str, mid: str, sha: str, t: i18n.Printer | None = None) -> dict | None:
    t = t or inbox.en()
    try:
        with os.fdopen(_ledger(ledger, os.O_RDONLY), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
    except FileNotFoundError:
        return None   # no send recorded yet
    except OSError as e:
        # Said, not guessed: the check for a reused id is not made.
        sys.stderr.write(t("send.ledger-unreadable", {"detail": e.strerror or str(e)}) + "\n")
        return None
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("id") == mid and r.get("sha256") != sha:
            return r
    return None


class LedgerNotTrimmed(OSError):
    """The entry is in the ledger; only the trim after it failed. Not the
    ledger left unwritten: a reused id is still caught."""


def record_sent(ledger: str, entry: dict, keep: int = 5000) -> None:
    """Append, then trim the oldest past keep+1000. A trim drops the oldest
    entries, so the ledger no longer speaks for the time before what it
    keeps: its first line then says from when it does,
    {"trimmed_before": <the oldest kept entry's at>} — the journal's
    backfill reads it, or it would refuse this account's own trimmed-away
    sends as another's (episodic_import.py, review of #84). It has no id,
    so a reader looking for entries passes over it.

    Under identity.agent_lock, the append and the trim both: two sends at
    once could each read the ledger and the later rewrite drop the earlier
    one's line. The trim replaces the file whole (identity.atomic_write),
    so a kill mid-trim leaves the old ledger, never a cut one (ADR-003)."""
    identity = paths.identity()
    os.makedirs(os.path.dirname(ledger), exist_ok=True)
    with identity.agent_lock():
        fd = _ledger(ledger, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            # A fragment (a send killed mid-append) ends the ledger: this
            # entry starts on its own line, or both are lost to a reader
            # (#100's review, 3). Every writer appends under the lock, so
            # the end does not move between the read and the write.
            if os.fstat(fd).st_size and bypass.last_byte(ledger, fd) != b"\n":
                fh.write("\n")
            fh.write(js.stringify(entry) + "\n")
        with os.fdopen(_ledger(ledger, os.O_RDONLY), encoding="utf-8", errors="replace") as fh:
            entries = [x for x in fh.read().split("\n") if x]
        if len(entries) > keep + 1000:
            kept = entries[-keep:]
            try:
                at = json.loads(kept[0]).get("at")
            except (ValueError, AttributeError):
                at = None
            mark = js.stringify({"trimmed_before": at if isinstance(at, str) else _now_iso()})
            try:
                identity.atomic_write(ledger, "\n".join([mark, *kept]) + "\n")
            except OSError as exc:
                raise LedgerNotTrimmed(exc.errno, exc.strerror or str(exc)) from None


def _now_iso() -> str:
    """new Date().toISOString(): UTC, milliseconds, Z."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# The automatic REPLY intake (ADR-037 rule 5): built, tested, and off. Only
# under AGENT_FABRIC_JOBS_AUTO_INTAKE=1, which nothing sets, does a REPLY
# sent here add the message it answers; it cannot tell an undertaking from a
# decline — one reason it stays off. A REQUEST to a login is another path,
# always on (intake.py, queue_request below). The send has already
# succeeded: nothing here fails it.
JOBS = os.path.join(paths.CHECKOUT, "tools", "fabric", "jobs.py")


def auto_intake(msg: dict, env: dict | None = None,
                run: Callable[..., Any] = subprocess.run) -> dict | None:
    env = os.environ if env is None else env
    if env.get("AGENT_FABRIC_JOBS_AUTO_INTAKE") != "1":
        return None
    answered = msg.get("metadata", {}).get("IN-REPLY-TO") if isinstance(msg, dict) else None
    if not isinstance(msg, dict) or msg.get("type") != "REPLY" or not answered:
        return None
    # Bounded: it reads the relay, and a hung relay must not hold a send
    # that has already succeeded.
    try:
        r = run(["python3", JOBS, "add", "--request", answered, "--auto"], capture_output=True, text=True,
                env=dict(env), timeout=20)
        return {"status": r.returncode, "stdout": r.stdout or "", "stderr": r.stderr or "", "signal": None}
    except subprocess.TimeoutExpired:
        return {"status": None, "stdout": "", "stderr": "", "signal": "SIGTERM"}
    except OSError as e:
        return {"status": 1, "stdout": "", "stderr": str(e), "signal": None}


def journal(args: list[str], stdin: str, run: Callable[[list[str], str], dict] = inbox.run_episodic) -> dict:
    """tools/fabric/episodic.py, in this process: {status, stdout, stderr}.
    It speaks for itself on stderr, untranslated: its lines name a path or
    an id, never the message."""
    return run(args, stdin)


def _journal_off() -> bool:
    return bypass.is_off()


def _never_delivered(e: BaseException) -> bool:
    """A post that failed in a way that proves the relay does not hold the
    message: refused with a 4xx (the request was judged and turned away),
    a connection that never reached it, or a token refused before it left.
    Anything else (no answer, a timeout, a reset, a body that is not the
    relay's, a 5xx from the relay or a proxy in front of it) may come after
    the relay stored it: delivered or not is unknown."""
    status = getattr(e, "status", None)
    return ((isinstance(status, int) and 400 <= status < 500) or getattr(e, "reached", None) is False
            or isinstance(e, inbox.TokenRefused))


def _bypass_outcome(text: str, outcome: str, seq: Any = None) -> None:
    """A bypassed send's second line, once the post is over. Not a
    refusal when it cannot be written: the message has left or failed
    already, and its pending line stands for it."""
    try:
        bypass.record([bypass.entry("out", text, seq, outcome=outcome)])
    except bypass.BypassUnrecorded as e:
        sys.stderr.write(f"episodic: the send's outcome ({outcome}) is not in the bypass record: {e}\n")


# ── presence, through the control plane's own process ────────────────

PRESENCE = os.path.join(paths.CHECKOUT, "runtime", "control", "presence.mjs")


def presence_wait_ms() -> float:
    n = js.number(os.environ.get("GZCOORD_PRESENCE_WAIT_MS", js.UNDEFINED))
    return n if n > 0 else 6000.0


def check_addressees(metadata: dict, sender: str, tok: str,
                     run: Callable[..., Any] = subprocess.run) -> dict:
    """checkAddressees' answer, asked of runtime/control/presence.mjs. A
    request that could not be made comes back as {"error", "status"}; a
    timeout, a missing node or an unreadable answer is an error with no
    status — "unavailable", never present."""
    if metadata.get("BROADCAST") or (not metadata.get("TO") and not metadata.get("TO-ROLE")):
        return {"checked": False}
    body = json.dumps({"metadata": metadata, "from": sender, "token": tok})
    try:
        r = run(["node", PRESENCE, "check"], input=body, capture_output=True, text=True,
                timeout=presence_wait_ms() / 1000 + 30)
    except subprocess.TimeoutExpired:
        return {"error": "the presence check did not finish", "status": None}
    except OSError as e:
        return {"error": f"the presence check could not run ({e.strerror or e})", "status": None}
    try:
        answer = json.loads((r.stdout or "").strip().split("\n")[-1])
    except (ValueError, IndexError):
        answer = None
    if not isinstance(answer, dict) or r.returncode not in (0, 4, 5, 6):
        detail = ((r.stderr or "").strip().split("\n") or [""])[-1][:160]
        return {"error": f"the presence check gave no answer (exit {r.returncode}){': ' + detail if detail else ''}",
                "status": None}
    return answer


def asked_presence(metadata: dict, sender: str, tok: str, run: Callable[..., Any] = subprocess.run) -> dict:
    """check_addressees, with a request that could not be made read as send
    acts on it: skipped on a refused token, otherwise "unavailable"."""
    pres = check_addressees(metadata, sender, tok, run)
    if "error" not in pres:
        return pres
    # A refused token is the post's to handle: it re-reads the synced
    # token and says "refused" if that fails too (review of #38).
    if pres.get("status") in (401, 403):
        return {"checked": False, "skipped": True}
    return {"checked": True, "problems": [{"kind": "unavailable", "detail": str(pres["error"]).split("\n")[0][:160]}]}


def _read_input(file: str) -> str:
    if file == "-":
        return sys.stdin.buffer.read().decode("utf-8", errors="replace")
    with open(file, encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def main(argv: list[str]) -> int:
    # The login first, before anything is printed: every line here is then
    # the reader's, the usage line included — the call inbox made for its
    # own usage line, so the two tools agree whose language it is in.
    who = gzmsg.whoami()
    t = i18n.t_for(who)
    dry = "--dry-run" in argv
    force = "--force" in argv
    file = next((a for a in argv if not a.startswith("--")), None)
    if not file:
        print(t("send.usage"), file=sys.stderr)
        return 1
    try:
        raw = _read_input(file)
    except OSError as e:
        print(t("send.cannot-read", {"file": file, "detail": e.strerror or str(e)}), file=sys.stderr)
        return 1
    text = gzmsg.normalize(raw)
    # Only a message that parses is given an id; one that does not is left
    # to validate(), which refuses it in the dictionary's words (exit 2).
    try:
        head = gzmsg.parse(text)["metadata"]
    except gzmsg.NotGzcoord:
        head = None
    if head is not None and not head.get("MESSAGE-ID"):
        minted = gzmsg.mint_id()
        text = with_message_id(text, minted)
        if dry:
            print(t("send.id-minted-dry", {"id": minted}), file=sys.stderr)
        elif file == "-":
            print(t("send.id-minted-stdin", {"id": minted}), file=sys.stderr)
        else:
            # A fresh temporary name, created exclusively (never followed
            # through a link that sits there), renamed over the file only
            # once complete; on any failure the file is as it was and the
            # temporary is gone.
            tmp = f"{file}.tmp-{os.getpid()}-{int(datetime.datetime.now().timestamp() * 1000)}"
            try:
                with open(tmp, "x", encoding="utf-8", newline="") as fh:
                    fh.write(text)
                os.replace(tmp, file)
            except OSError as e:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                print(t("send.id-not-written", {"file": file, "detail": e.strerror or str(e)}), file=sys.stderr)
                return 1
            print(t("send.id-minted", {"id": minted, "file": file}), file=sys.stderr)

    root = inbox.inbox_root(who)
    cfg = inbox.integration_config(who.get("project"), os.environ, t)
    if not cfg["configured"]:
        print(t("send.not-configured", {"reason": cfg["reason"]}), file=sys.stderr)
        return 3
    try:
        inbox.assert_not_control_channel(cfg["channel"], t)
    except inbox.ControlChannel as e:
        print(t("send.error-not-sent", {"detail": str(e)}), file=sys.stderr)
        return 2
    relay_url, channel = cfg["relay_url"], cfg["channel"]
    tax_path = gzmsg.find_taxonomy(root)
    taxonomy = gzmsg.load_taxonomy(tax_path) if tax_path else None
    me = inbox.identity(who, taxonomy)
    if me.get("roleError"):
        print(t("send.warning", {"detail": me["roleError"]}), file=sys.stderr)

    # Validate as the last step before sending. The width check is off: the
    # bridge carries a line as written, and a warning nobody can act on is
    # noise. The refusal is the sender's line, in the sender's language.
    result = gzmsg.validate(text, taxonomy=taxonomy, max_columns=0, t=t)
    # An id complaint is repeated below as the refusal; once is enough. The
    # duplicate is found by IDENTITY, not by the English it used to start
    # with (blind review F2 on PR #28).
    meta = (result["message"] or {}).get("metadata") or {}
    also_refused = {c for c in (gzmsg.id_complaint(k, meta[k], t) if meta.get(k) else None
                                for k in ("MESSAGE-ID", "IN-REPLY-TO")) if c}
    for w in result["warnings"]:
        if w not in also_refused:
            print(t("send.warning", {"detail": w}), file=sys.stderr)
    if not result["ok"]:
        for e in result["errors"]:
            print(t("send.error", {"detail": e}), file=sys.stderr)
        print(t("send.does-not-validate"), file=sys.stderr)
        return 2
    msg = gzmsg.parse(text)
    sender = msg["metadata"].get("FROM")
    if sender != me["address"]:
        print(t("send.from-is-not-this-login", {"from": sender if sender is not None else t("send.from-missing"),
                                                "address": me["address"]}), file=sys.stderr)
        return 2
    mid = msg["metadata"].get("MESSAGE-ID", "(none)")
    # The deployment mints UUIDv7 ids and every join resolves on them; the
    # validator can only warn, so the sender is where the convention is a
    # rule: a malformed id degrades quietly and the thread cannot be
    # reconstructed later.
    for key in ("MESSAGE-ID", "IN-REPLY-TO"):
        c = gzmsg.id_complaint(key, msg["metadata"][key], t) if msg["metadata"].get(key) else None
        if c:
            print(t("send.id-refused", {"detail": c}), file=sys.stderr)
            return 2
    # This session's model fell back after a safeguard flagged a request
    # (model-fallback-note.sh leaves the marker): the flagged text is
    # contagious, so the reminder is repeated at the moment of sending. A
    # reminder, never a content check.
    fb = fallback_marker()
    if fb:
        topic = fb.get("topic")
        print(t("send.fallback-reminder", {
            "from_model": fb.get("from_model") or t("send.fallback-unknown-model"),
            "to_model": fb.get("to_model") or t("send.fallback-unknown-target"),
            "at": fb.get("at") or t("send.fallback-unknown-time"),
            "topic": topic or t("send.fallback-unknown-topic"),
            "topic_again": topic or t("send.fallback-unknown-topic-again")}), file=sys.stderr)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ledger = sent_ledger_path(who)
    spent = spent_elsewhere(ledger, mid, sha, t) if mid != "(none)" else None
    if spent:
        print(t("send.id-reused", {"id": mid, "seq": js.coalesce(js.get(spent, "seq"), "?")}), file=sys.stderr)
        return 2
    # A dry run posts nothing, not even a presence request on the control
    # channel (review of #38): it validates and resolves, and stops here.
    if dry:
        print(t("send.would-post", {"type": msg["type"], "id": mid, "address": me["address"], "channel": channel,
                                    "relay_url": relay_url}), file=sys.stderr)
        return 0
    tok = inbox.token(root, cfg)
    # Is anyone there? A message to a login with no session waits in the
    # relay until one starts, and a TO-ROLE with no running holder reaches
    # nobody now. The sender decides — --force sends anyway (the owner,
    # 2026-09-25). A broadcast is not checked.
    if tok:
        pres = asked_presence(msg["metadata"], me["address"], tok)
        # Said, never silent: the contract is that a TO is checked.
        if pres.get("skipped"):
            print(t("send.presence-skipped"), file=sys.stderr)
        for p in pres.get("problems") or []:
            kind = p.get("kind")
            if kind == "offline":
                print(t("send.presence-offline", {"address": p.get("address")}), file=sys.stderr)
            elif kind == "silent":
                print(t("send.presence-silent", {"address": p.get("address"), "seconds": presence_wait_ms() / 1000}),
                      file=sys.stderr)
            elif kind == "not-placed":
                print(t("send.presence-not-placed", {"address": p.get("address")}), file=sys.stderr)
            elif kind == "no-holder":
                holders = p.get("holders") or []
                print(t("send.presence-no-holder", {"role": p.get("role"), "holders": ", ".join(holders)}) if holders
                      else t("send.presence-no-account", {"role": p.get("role")}), file=sys.stderr)
                if p.get("silent"):
                    print(t("send.presence-some-silent", {"addresses": ", ".join(p["silent"])}), file=sys.stderr)
            else:
                print(t("send.presence-unavailable", {"detail": js.get(p, "detail")}), file=sys.stderr)
        for n in pres.get("notes") or []:
            if n.get("kind") == "planning":
                print(t("send.presence-planning", {"address": n.get("address")}), file=sys.stderr)
        if pres.get("problems"):
            if not force:
                print(t("send.presence-not-sent"), file=sys.stderr)
                return 4
            print(t("send.presence-forced"), file=sys.stderr)
    if not tok:
        print(t("send.no-token"), file=sys.stderr)
        return 3
    where = [*(["--project", who["project"]] if who.get("project") else []),
             *(["--working-copy", who["working_copy"]] if who.get("working_copy") else [])]
    kept = None
    if _journal_off():
        try:
            bypass.record([bypass.entry("out", text, outcome="pending")])
        except bypass.BypassUnrecorded as e:
            sys.stderr.write(f"episodic: not sent: {e}; the journal is bypassed only with a record of it (ADR-041)\n")
            return 2
        sys.stderr.write("episodic: GZCOORD_JOURNAL=off — this message is sent without being kept in your journal"
                         " (ADR-041)\n")
    else:
        kept = journal(["gzcoord-out-pending", *where], text)
        if kept["status"] != 0:
            sys.stderr.write(kept["stderr"] or f"episodic: the journal did not answer (exit {kept['status']})\n")
            sys.stderr.write("episodic: not sent: a message is kept before it leaves (ADR-041); GZCOORD_JOURNAL=off"
                             " sends without it\n")
            return 2

    def post(auth: str) -> Any:
        return inbox.api(auth, "/api/send", relay_url, method="POST",
                         body=js.stringify({"channel": channel, "sender": me["address"], "content": text}))

    try:
        try:
            res = post(tok)
        except inbox.RelayError as e:
            # A shell snapshot keeps a rotated token; the synced file has the current one.
            fresh = inbox.synced_token() if e.status in (401, 403) else None
            if not (fresh and fresh != tok):
                raise
            tok = fresh
            res = post(tok)
    except Exception as e:  # noqa: BLE001 — any failure of the post is the relay's, said
        # The pending row becomes a failed one only when this post provably
        # did not reach the relay and no earlier attempt's outcome is unknown
        # (an earlier one may have reached it, and this failure says nothing
        # about it: review of #78); otherwise it stays pending.
        never = _never_delivered(e)
        if _journal_off():
            _bypass_outcome(text, "failed" if never else "unknown")
        else:
            if str((kept or {}).get("stdout") or "").strip() == "unknown":
                sys.stderr.write("episodic: an earlier attempt of this message may have reached the relay; its row"
                                 " stays pending\n")
            elif not never:
                # Not "failed": the relay may hold it. The row stays pending,
                # the journal's own "may have reached the carrier".
                sys.stderr.write("episodic: this message may have reached the relay; its row stays pending\n")
            else:
                done = journal(["gzcoord-out-final", mid, "--state", "failed"], "")
                if done["status"] != 0:
                    sys.stderr.write(done["stderr"])
        status = getattr(e, "status", None)
        if status in (401, 403):
            print(t("send.token-refused", {"status": status}), file=sys.stderr)
            return 3
        if isinstance(e, inbox.TokenRefused):   # the synced token re-read after a 401
            print(f"send: {e}", file=sys.stderr)
            return 3
        if not never:
            # From a file the id was written into it, so a resend is the same
            # message and readers discard the copy; from stdin it was minted
            # in memory only, and a resend would mint another (SPEC §7.2).
            again = t("send.again-file") if file != "-" else t("send.again-stdin", {"id": mid})
            print(t("send.outcome-unknown", {"relay_url": relay_url, "detail": str(e), "again": again}), file=sys.stderr)
            return 3
        # Never delivered: either the relay answered and refused it (a 4xx),
        # or the connection never reached it — "unreachable" only for that.
        if isinstance(status, int) and 400 <= status < 500:
            print(t("send.relay-refused", {"relay_url": relay_url, "detail": str(e)}), file=sys.stderr)
        else:
            print(t("send.relay-unreachable", {"relay_url": relay_url, "detail": str(e)}), file=sys.stderr)
        return 3
    seq = js.get(res, "seq") if isinstance(res, dict) else js.UNDEFINED
    if _journal_off():
        _bypass_outcome(text, "accepted", seq)
    else:
        # The send has happened: a journal that fails now is said, never a failed send.
        done = journal(["gzcoord-out-final", mid, "--state", "accepted",
                        *(["--seq", js.string(seq)] if not js.nullish(seq) else [])], "")
        if done["status"] != 0:
            sys.stderr.write(done["stderr"] or "episodic: the sent message was not marked accepted\n")
    # Recorded only once the relay has it: a post that failed spent nothing.
    try:
        record_sent(ledger, {"id": mid, "sha256": sha, "seq": js.coalesce(seq, None), "at": _now_iso()})
    except LedgerNotTrimmed as e:
        print(t("send.ledger-not-trimmed", {"detail": e.strerror or str(e)}), file=sys.stderr)
    except OSError as e:
        print(t("send.ledger-not-written", {"detail": e.strerror or str(e)}), file=sys.stderr)
    deduplicated = res.get("deduplicated") if isinstance(res, dict) else None
    print(t("send.sent", {"seq": seq, "type": msg["type"], "id": mid,
                          "deduplicated": t("send.deduplicated") if deduplicated else ""}))
    # fabric-jobs speaks for itself, on stderr: stdout stays the one sent line.
    intake = auto_intake(msg)
    if intake:
        sys.stderr.write(f"{intake.get('stdout') or ''}{intake.get('stderr') or ''}")
        # A failed intake is said, never a quiet empty line.
        if intake.get("status") != 0:
            how = f"stopped by {intake['signal']} after 20 s" if intake.get("signal") else f"exit {intake.get('status')}"
            sys.stderr.write(f"fabric-jobs: the job intake of {msg['metadata']['IN-REPLY-TO']} did not complete ({how});"
                             f" add it with fabric-jobs add --request\n")
    # Even a resend the relay deduplicated: the first attempt may have ended
    # unknown or failed to queue, and the addressee's list check spares the duplicate.
    queue_request(msg, who)
    return 0


def queue_request(msg: dict, who: dict) -> None:
    """A REQUEST to a login, sent by its host's operator, goes on that
    login's job list too (intake.py): it reaches a session whose watch has
    lapsed at its next start. The post has succeeded: nothing here fails it,
    whatever it raises is a line."""
    meta = msg.get("metadata") or {}
    if msg.get("type") != "REQUEST" or "/" not in str(meta.get("TO", "")):
        return
    try:
        try:
            with open(paths.roots.hosts_registry(), encoding="utf-8") as fh:
                hosts = json.load(fh)
        except (OSError, ValueError) as e:
            raise RuntimeError(f"the hosts registry could not be read ({e.__class__.__name__})") from None
        job = intake.queue_for_addressee(msg, sender=who["agent"], hosts=hosts)
        if job:
            print(f"queued as {job} on {meta['TO']}'s job list", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"gzcoord: REQUEST {meta.get('MESSAGE-ID')} was not queued on {meta['TO']}'s list: {e}\n")


def run(argv: list[str]) -> int:
    """NOT through the dictionary: what failed may BE the dictionary (blind
    review F1). One line and exit 1, as the Node's last resort."""
    try:
        return main(argv)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001 — the contract's last resort
        print(f"send: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
