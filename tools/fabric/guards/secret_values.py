#!/usr/bin/env python3
"""tools/fabric/guards/secret_values.py — a commit or a push that holds a value of the committing account's own secrets is
refused (agent-fabric ADR-012 §5 rule 9). Borrowed from omerta (shcherbak-ai/omerta, read 2026-10-27), stdlib only:
it searches for the account's ACTUAL values, not for shapes that look like keys, so a key of any format is caught.

CONTRACT
  values    the `export NAME=value` lines of $HOME/.config/agent-fabric/secrets.env, the file `fabric-secrets sync` writes
            for this login (ADR-038), parsed as tools/fabric/launcher/secrets.py parses them. A value under MIN_CHARS, and
            a name in IGNORE, is not searched. No file: nothing to search, every check admits. A file that exists but
            cannot be read: the check cannot judge and REFUSES.
  needles   each value as written, percent-encoded, JSON-escaped and base64-encoded (standard and URL-safe, at each of
            the three byte alignments, so a value inside a longer base64 run is found too).
  searched  staged      every staged path that differs from HEAD: the staged blob's bytes and the path's name; a gitlink
                        (mode 160000) records another repository's commit id, no content of this one, and is not read
            message     the commit message file, comment lines included (git keeps them for -m and -F), up to the scissors
                        line: what follows it is `commit -v`'s diff, which shows a removed value as well as an added one
            objects     every commit, tag and blob `git rev-list --objects <revs>` names (a commit's and a tag's whole
                        object, so the message and the headers; a blob's bytes and the path it was reached by) — what a
                        push adds (pre-push), or the whole history (the `history` verb, an audit)
  output    a finding names the VARIABLE and where: `<path>: GH_TOKEN (base64)`, `commit <oid> message: GH_TOKEN`; a
            value found in a path's name is reported without the path, which would print it. Never a value, never a
            needle. A hook shows the first 20 findings; `history` shows every one. No value is ever on git's argv: git is asked for object ids and names, and Python searches the bytes.
  argv      history [<rev-args>...]      default --all; exit 0 clean, 1 found, 2 could not judge
            The hooks import scan_staged, scan_message and scan_objects; see commit_hooks.py and githooks_prepush.py.

CI holds no account's values, so this guard is the keyboard's: pre-commit, commit-msg and pre-push, in every repository
whose hooks are the fabric's. --no-verify passes all three, which is a choice, not an accident; `history` is the audit
that finds what passed.
"""
from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
import sys
import threading
import urllib.parse

# omerta's default: shorter values are ports, flags and counts, which match ordinary text.
MIN_CHARS = 8
# Names whose value is not a secret, which secrets.env may still carry: the store's own login, which every branch name and
# message of the account holds. A port offset or a count is under MIN_CHARS and needs no entry.
IGNORE = frozenset({"AGENT_LOGIN"})
SECRETS_FILE = (".config", "agent-fabric", "secrets.env")
GIT_TIMEOUT_S = 120
SCISSORS = "# ------------------------ >8 ------------------------"
GITLINK = "160000"


class CannotJudge(Exception):
    """The check could not run; a hook refuses, the audit exits 2."""


def secrets_path(home: str | None = None) -> str:
    return os.path.join(home or os.path.expanduser("~"), *SECRETS_FILE)


def load(home: str | None = None) -> dict[str, str]:
    """name → value for every value searched. A line shlex cannot read is skipped, as the launcher skips it."""
    path = secrets_path(home)
    try:
        with open(path, encoding="utf-8", errors="surrogateescape") as fh:
            text = fh.read()
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise CannotJudge(f"cannot read {path} to check for this account's secret values ({e.strerror})") from None
    out: dict[str, str] = {}
    for line in text.split("\n"):
        if not (line.startswith("export ") and "=" in line):
            continue
        try:
            name, value = shlex.split(line[len("export "):])[0].split("=", 1)
        except (ValueError, IndexError):
            continue
        if name not in IGNORE and len(value) >= MIN_CHARS:
            out[name] = value
    return out


def _base64_runs(raw: bytes) -> set[bytes]:
    """The characters of base64 that depend on `raw` alone, at each alignment it can start at inside a longer input:
    at offset k the first ceil(8k/6) characters still hold the preceding bytes' bits, and the tail stops at the last
    character whose six bits are all raw's."""
    runs = set()
    for k in range(3):
        enc = base64.b64encode(b"\0" * k + raw).rstrip(b"=")
        run = enc[-(-8 * k // 6):(8 * (k + len(raw))) // 6]
        runs.add(run)
        runs.add(run.translate(bytes.maketrans(b"+/", b"-_")))
    return runs


def needles(values: dict[str, str]) -> list[tuple[str, str, bytes]]:
    """(name, encoding, bytes) for every form a value is searched in; one form appears once per name."""
    out: list[tuple[str, str, bytes]] = []
    for name, value in sorted(values.items()):
        raw = value.encode("utf-8", "surrogateescape")
        forms: dict[bytes, str] = {raw: "as written"}
        for enc in (urllib.parse.quote(value, safe=""), urllib.parse.quote(value), urllib.parse.quote_plus(value, safe="")):
            forms.setdefault(enc.encode(), "percent-encoded")
        for enc in (json.dumps(value)[1:-1], json.dumps(value, ensure_ascii=False)[1:-1]):
            forms.setdefault(enc.encode("utf-8", "surrogateescape"), "JSON-escaped")
        for run in _base64_runs(raw):
            forms.setdefault(run, "base64")
        out += [(name, how, form) for form, how in forms.items() if form]
    return out


def find(data: bytes, found_in: list[tuple[str, str, bytes]]) -> list[tuple[str, str]]:
    """(name, encoding) of every value `data` holds, each name once, its first form in needles() order."""
    hits: dict[str, str] = {}
    for name, how, needle in found_in:
        if name not in hits and needle in data:
            hits[name] = how
    return list(hits.items())


def _describe(where: str, hits: list[tuple[str, str]]) -> list[str]:
    return [f"{where}: {name}" + ("" if how == "as written" else f" ({how})") for name, how in hits]


def _name_hits(path: str, ns: list[tuple[str, str, bytes]]) -> list[str]:
    return [f"a file's name holds {name}" + ("" if how == "as written" else f" ({how})")
            for name, how in find(os.fsencode(path), ns)]


def _git(*args: str, binary: bool = False) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], capture_output=True, timeout=GIT_TIMEOUT_S, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise CannotJudge(f"git {args[0]} failed: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r if binary else subprocess.CompletedProcess(r.args, 0, r.stdout.decode("utf-8", "surrogateescape"), "")


def _cat(oids: list[str]):
    """(oid, type, bytes) for each object, through one `git cat-file --batch`; the ids go on its stdin from a thread,
    so a long list cannot fill both pipes at once."""
    if not oids:
        return
    p = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)

    def feed() -> None:
        # A reader that stopped early kills git, and this write then meets a closed pipe: that is the stop, not an error to
        # print after the refusal (review of #433, F7).
        try:
            p.stdin.write("".join(o + "\n" for o in oids).encode())
        except OSError:
            pass
        finally:
            try:
                p.stdin.close()
            except OSError:
                pass

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    done = False
    try:
        for _ in oids:
            header = p.stdout.readline().decode().split()
            if len(header) != 3:
                raise CannotJudge(f"git cat-file could not read an object ({' '.join(header) or 'no answer'})")
            oid, kind, size = header
            data = p.stdout.read(int(size))
            p.stdout.read(1)
            yield oid, kind, data
        done = True
    finally:
        # Stopped early, git may still be blocked writing to us and the feeder blocked writing to it: end git first, or the
        # join waits forever.
        if not done:
            p.kill()
        writer.join()
        p.stdout.close()
        if p.wait() != 0 and done:
            raise CannotJudge("git cat-file failed")


def scan_staged(ns: list[tuple[str, str, bytes]]) -> list[str]:
    """Every staged path that differs from HEAD, a merge's included: its staged blob and its name."""
    if not ns:
        return []
    paths = [p for p in _git("diff", "--cached", "-z", "--no-renames", "--name-only", "--diff-filter=ACMRT").stdout.split("\0") if p]
    if not paths:
        return []
    oids: dict[str, str] = {}
    for entry in (e for e in _git("ls-files", "-s", "-z", "--full-name").stdout.split("\0") if e):
        meta, _, name = entry.partition("\t")
        fields = meta.split()
        if len(fields) == 3 and fields[2] == "0":
            oids[name] = "" if fields[0] == GITLINK else fields[1]
    out: list[str] = []
    for path in paths:
        out += _name_hits(path, ns)
        if path not in oids:
            # Not the path: its name may be the value, and this is said before any name hit is.
            raise CannotJudge("a staged path has no stage-0 entry in the index")
    paths = [p for p in paths if oids[p]]
    by_oid: dict[str, list[str]] = {}
    for path in paths:
        by_oid.setdefault(oids[path], []).append(path)
    for oid, _, data in _cat(list(by_oid)):
        hits = find(data, ns)
        for path in by_oid[oid]:
            if not find(os.fsencode(path), ns):
                out += _describe(path, hits)
            elif hits:
                out += _describe("a file whose name holds a value", hits)
    return out


def message_body(text: str) -> str:
    """The message up to the scissors line. Comment lines stay: whether git strips them depends on how the commit was made
    (`-m` and `-F` keep them), which the hook is not told."""
    return text.split("\n" + SCISSORS + "\n", 1)[0] if not text.startswith(SCISSORS + "\n") else ""


def scan_message(text: str, ns: list[tuple[str, str, bytes]]) -> list[str]:
    return _describe("the commit message", find(message_body(text).encode("utf-8", "surrogateescape"), ns))


def scan_objects(revs: list[str], ns: list[tuple[str, str, bytes]]) -> list[str]:
    """Every commit, tag and blob reachable from revs (rev-list's own syntax: `a..b`, `x --not --remotes`, `--all`)."""
    if not ns:
        return []
    listing = _git("rev-list", "--objects", *revs).stdout
    paths: dict[str, list[str]] = {}
    order: list[str] = []
    for line in listing.split("\n"):
        if not line:
            continue
        oid, _, path = line.partition(" ")
        if oid not in paths:
            order.append(oid)
            paths[oid] = []
        if path:
            paths[oid].append(path)
    out: list[str] = []
    for oid in order:
        for path in paths[oid]:
            out += [f"{h} (object {oid[:12]})" for h in _name_hits(path, ns)]
    kinds = dict(line.split(" ", 1) for line in _git_batch_check(order))
    wanted = [o for o in order if kinds.get(o) in ("commit", "tag", "blob")]
    for oid, kind, data in _cat(wanted):
        hits = find(data, ns)
        if not hits:
            continue
        if kind == "blob":
            named = [p for p in paths[oid] if not find(os.fsencode(p), ns)]
            out += _describe(f"{named[0] if named else 'a file whose name holds a value'} (blob {oid[:12]})", hits)
        else:
            out += _describe(f"{kind} {oid[:12]}", hits)
    return out


def _git_batch_check(oids: list[str]) -> list[str]:
    """`<oid> <type>` for each object, ids on stdin."""
    if not oids:
        return []
    r = subprocess.run(["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"], input="".join(o + "\n" for o in oids),
                       capture_output=True, text=True, timeout=GIT_TIMEOUT_S)
    if r.returncode != 0:
        raise CannotJudge("git cat-file --batch-check failed")
    return [line for line in r.stdout.split("\n") if line and not line.endswith(" missing")]


def refusal(what: str, findings: list[str], cap: int | None = 20) -> str:
    shown = findings if cap is None or len(findings) <= cap else findings[:cap] + [f"… ({len(findings)} findings)"]
    return ("\n  ".join([f"{what} holds a value of this account's own secrets ({secrets_path()}):", *shown])
            + "\n  Remove it and rotate the secret if it ever left this machine (agent-fabric ADR-012 §5 rules 1, 8 and 9)."
            + "\n  The value is named by its variable only; it is never printed.")


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "history":
        print("usage: secret_values.py history [<rev-args>...]", file=sys.stderr)
        return 2
    try:
        ns = needles(load())
        if not ns:
            print(f"history: no value to search for ({secrets_path()} holds none of {MIN_CHARS}+ characters)")
            return 0
        findings = scan_objects(argv[1:] or ["--all"], ns)
    except (CannotJudge, OSError, subprocess.SubprocessError) as e:
        print(f"history: could not judge ({e})", file=sys.stderr)
        return 2
    if findings:
        print(refusal("the history", findings, cap=None))
        return 1
    print(f"history: none of {len({n for n, _, _ in ns})} values found")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
