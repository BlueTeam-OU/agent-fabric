#!/usr/bin/env python3
"""tools/fabric/harvest_memory.py

Drain THIS AGENT's Claude memory into a claims directory the assembler
can consume.

    tools/fabric/harvest_memory.py --role architect-cto --out /tmp/drain
    tools/fabric/assemble.py --claims /tmp/drain/claims --drain /tmp/drain \\
        --project <project> --stamp $(date +%F)

    tools/fabric/harvest_memory.py --role architect-cto --bundle - > drain.tar
    tools/fabric/assemble.py --bundle drain.tar --project <project> --stamp $(date +%F)

THE BUNDLE. `--bundle FILE|-` writes the same drain as one tar — claims/,
observations.jsonl, references.json, harvest-report.json — plus a
manifest.json naming who harvested (agent, host, role, project, working
copy label, the watermark window) and the sha256 of every file. It is
the artifact that crosses a host: `bin/fabric-host <host> drain <login>`
runs this AS THE ACCOUNT on its host and streams the tar to the
coordinator, who assembles it (assemble.py --bundle verifies the
manifest first). Only the agent reads its memory; the coordinator
receives the result (review, 2026-09-16).

PROVENANCE. Every observation is stamped with the AGENT (the Linux login,
from runtime/identity.py), the HOST, the PROJECT the working copy belongs
to (projects/registry.json, by remote) and the WORKING COPY's basename as a
label. The agent is never derived from the directory; the directory only
says where the memory was written (`--working-copy`, default: cwd), which
is how Claude Code names the memory directory being drained.

The role payload lands in `<out>/claims/`, one directory below the drain
metadata, because assemble.py reads EVERY .json under `--claims` as a
role payload and would take `references.json` for one.

WHY MEMORY AND NOT TRANSCRIPTS. Earlier drains read a session-memory
plugin's store and, later, raw transcripts; both are retired. Claude's
own memory is a better input than either: a memory file is ONE fact,
written deliberately
at the moment it was learned, carrying a `why` and a `how to apply`. That
is already the shape a claim wants, so this needs no model pass, no
transcript scraping, and no redaction layer -- the input is curated text
rather than raw session bytes.

SCOPE IS PER AGENT, BY DESIGN. Each agent distils its own memories into
the shared corpus; nothing here reads another account's home directory.
The role the claims land under is given explicitly (`--role`), defaulting
to the agent's active role binding.

ROLE KNOWLEDGE IS OPT-IN. A memory reaches this corpus only if it says so,
by carrying `roles_class` in its `metadata:` block:

    metadata:
      type: feedback
      roles_class: workflow

Nothing is inferred from `type`. That was the first design here and it was
wrong in three ways at once: it needed a mapping table, a special case to
drop `user` memories, and a refusal for unrecognised types -- three
mechanisms answering one question, "does this belong in the shared repo?".
Worse, `type` cannot answer it. Memory has four types and `.roles/` has
nine classes, and `project` alone covers both live threads and durable
constraints; measured on this account's first five memories the mapping
mis-filed two of three. Asking `type` to carry that decision made the
memory author hold two taxonomies in their head and still guess.

So the memory answers directly, or it is not drained. A memory with no
`roles_class` is SKIPPED AND NAMED in the report -- an omission you can
see beats a wrong filing you cannot, and for a shared corpus that is the
right way round.

`charter` and `recall` are refused as targets. lint.py exempts exactly
those two from `derived_from`, which is what marks them hand-authored; a
derived claim must not enter through that door.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import atexit
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
from typing import Any

HERE = os.path.dirname(os.path.realpath(__file__))


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layout = _load("fabric_layout", os.path.join(HERE, "layout.py"))
identity = _load("fabric_identity", os.path.join(layout.FABRIC_ROOT, "runtime", "identity.py"))

# THE SECRET FENCE, at the harvester. The assembler substitutes a person's
# name and redacts a secret when it files a claim — but a bundle travels
# before it is assembled, and since the control plane carries it
# (runtime/control/ops.mjs `memory`) it travels as records on a channel
# every account's daemon reads and the relay keeps. So a memory whose body
# carries a credential by shape never leaves the account: the whole drain
# is refused and the file named, as a bad roles_class is. Names are left
# to the assembler's substitution, as designed (policies/hygiene.json).
try:
    CREDENTIAL_PATTERNS = [(pattern, label) for pattern, label, _refer_as in layout.load_hygiene_patterns()
                           if "credential" in label]
except layout.HygieneError as _exc:
    # A broken list cannot screen a credential: no memory leaves unscreened.
    sys.exit(f"harvest_memory: {_exc}")


def credential_hits(text: str) -> list[str]:
    return [label for pattern, label in CREDENTIAL_PATTERNS if pattern.search(text)]
SCHEMA_PATH = os.path.join(layout.FABRIC_ROOT, "identities", "schemas", "claims.schema.json")


def _schema_claim_classes():
    """The claim classes the assembler will actually accept.

    Derived from the schema, never restated: a hand-kept copy drifted from
    it and let `index` through, which aborts assembly with KeyError. A
    failure here is reported in one line naming the file, not as an
    import-time traceback in front of --help.
    """
    try:
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        return schema["properties"]["claims"]["items"]["properties"]["class"]["enum"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f"harvest_memory: cannot read the claim classes from "
                 f"{SCHEMA_PATH}: {exc}. Expected "
                 f"properties.claims.items.properties.class.enum.")


# The classes a derived claim may take. `charter` and `recall` are the two
# lint.py exempts from `derived_from`, i.e. the hand-authored ones, so they
# are listed separately and refused rather than merely absent.
# Read from the schema rather than restated here: the two drifted, and the
# harvester accepted `index`, which the assembler has no file for. An
# index is GENERATED by the assembler from the other slices, so it can
# never be a claim's class.
CLAIM_CLASSES = frozenset(_schema_claim_classes())
HAND_AUTHORED_CLASSES = frozenset({"charter", "brief", "recall"})
# Refused with their own message rather than as merely unknown: `index` is
# GENERATED by the assembler from the other slices, so "not a class" is
# less useful to a reader than why.
GENERATED_CLASSES = frozenset({"index"})

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
# A memory written in another language (a language-culture holder writes
# its own in the language it answers for, the CEO, 2026-09-17) reaches the
# corpus — which is English, a slice travels into every project — through
# the rendering it carries under this heading: the claim is what follows
# it, the original stays in the holder's home, and the observation records
# the language. A non-Latin memory without one is not lost and not
# guessed at: it is named under `needs_rendering`, and the coordinator asks
# the holder — the fleet's translator — to render it before the drain.
RENDERING_RE = re.compile(r"^##\s+English\s*$", re.MULTILINE)


def is_mostly_non_latin(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    return sum(1 for ch in letters if ord(ch) > 0x024F) * 2 >= len(letters)


def split_rendering(body: str) -> tuple[str, str | None]:
    """(original, rendering) — the rendering is what follows `## English`,
    None when the body carries no such heading."""
    m = RENDERING_RE.search(body)
    if not m:
        return body, None
    return body[:m.start()].rstrip(), body[m.end():].strip()


# The harness's spelling of a launch directory and its memory directory
# are layout's (one rule; the launch prompt reads it too).
memory_slug = layout.memory_slug
default_memory_dir = layout.default_memory_dir


def previous_watermark(working_copy: str, host: str, agent: str | None = None) -> tuple[int, str | None]:
    """The ms-epoch watermark the project's last drain recorded for this
    agent on this host, and the report it came from — (0, None) when
    there is none. Read from the working copy's own report (the assembler
    writes it under .agent-fabric/memory/). Keyed `agent@host`: every
    account on a host has its own memory store, and one mark per host let
    one account's newer drain skip another's older memories (the review
    of #41, 2026-09-26). A report keyed by host alone reads as 0 — a full
    re-read, which merge mode makes harmless."""
    report = os.path.join(working_copy, ".agent-fabric", "memory", "last-drain-report.json")
    try:
        with open(report, encoding="utf-8") as fh:
            marks = json.load(fh).get("watermarks") or {}
        return int(marks.get(f"{agent}@{host}") or 0), report
    except (OSError, ValueError, TypeError):
        return 0, None


def scalar(value: str) -> str:
    """A frontmatter value as YAML reads it: a double-quoted one is
    unescaped (`\\"` is a quote, `\\\\` a backslash), a single-quoted one
    has its doubled quote undoubled. The quotes were once only stripped,
    and a `\\"` reached the claim, its heading and the index with the
    backslash in it (a drain's blind review, 2026-09-25)."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        try:
            return json.loads(v)
        except ValueError:
            # YAML admits escapes JSON does not (`\\xe9`, a raw tab); the
            # two that matter to a cue are unescaped here rather than
            # returned raw, which was the defect this function fixes.
            return re.sub(r'\\(["\\])', r"\1", v[1:-1])
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return v


def parse_memory(path: str) -> dict[str, Any] | None:
    """Parse one memory file. Returns None for a file that is not one."""
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return None                     # MEMORY.md, or a stray note
    head, body = m.group(1), m.group(2).strip()
    meta: dict[str, str] = {}
    section = None
    for line in head.split("\n"):
        if not line.strip():
            continue
        if re.match(r"^\S+:\s*$", line):
            section = line.split(":")[0].strip()
            continue
        km = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if not km:
            continue
        key, value = km.group(1), scalar(km.group(2))
        # `metadata:` nests one level; flatten it, since `type` is the only
        # field under it that this reads.
        meta[key if section is None else f"{section}.{key}"] = value
        if not line.startswith((" ", "\t")):
            section = None
    name = meta.get("name") or os.path.splitext(os.path.basename(path))[0]
    return {
        "name": name,
        "description": meta.get("description", ""),
        # The cue a memory written in another language travels under: the
        # index line and the slice heading are English like the body, which
        # comes from the `## English` rendering (see RENDERING_RE).
        "description_en": (meta.get("metadata.description_en") or meta.get("description_en") or "").strip(),
        "type": meta.get("metadata.type") or meta.get("type", ""),
        "body": body,
        "roles_class": meta.get("metadata.roles_class") or meta.get("roles_class", ""),
        # `shared_with: web-dev, backend-dev` — the other roles that own the
        # fact; one value on one line, since the frontmatter is read flat.
        "shared_with": sorted({r for r in re.split(r"[,\s]+",
                               meta.get("metadata.shared_with") or meta.get("shared_with", "")) if r}),
        "links": sorted(set(WIKILINK_RE.findall(body))),
        "path": path,
        "mtime": int(os.path.getmtime(path)),
        "mtime_ms": int(os.path.getmtime(path) * 1000),
        # When the fact was written, as the memory itself says (the
        # harness stamps `modified` in its metadata); the file's mtime is
        # the fallback. A section rendered from this claim carries the
        # date, so two divergent sections on one topic read in time order.
        "observed_at": observed_date(meta.get("metadata.modified") or meta.get("modified"), path),
        # The author's own supersession: `merge_target: "<heading>"` in the
        # metadata block names the section this memory replaces, and the
        # assembler asks the owner nothing. The README promised the field
        # and the harvest dropped it (language-culture, 2026-09-20).
        "merge_target": (meta.get("metadata.merge_target") or meta.get("merge_target") or "").strip(),
    }


def judge_memory(parsed: dict[str, Any]) -> dict[str, Any]:
    """The drain's decision on one memory that carries a `roles_class`, in
    the order the drain gives its reasons: `refused` with a reason,
    `held` until rendered, or `taken` with the text, title and language the
    claim is built from. The harvest and the memory-write check
    (runtime/claude-code/hooks/memory-write-check.py) both call it, so a
    rule changes in one place."""
    klass, name = parsed["roles_class"], parsed["name"]
    # Hand-authored FIRST: charter and recall are not in CLAIM_CLASSES,
    # so a validity check ahead of this one reports them as unknown and
    # the specific refusal never fires.
    if klass in HAND_AUTHORED_CLASSES:
        return {"verdict": "refused", "reason": f"roles_class {klass!r} is hand-authored and cannot be derived"}
    if klass in GENERATED_CLASSES:
        return {"verdict": "refused", "reason": f"roles_class {klass!r} is generated by the "
                "assembler from the other slices, so no claim carries it"}
    bad = [r for r in parsed["shared_with"] if not re.fullmatch(r"[a-z][a-z0-9-]*", r)]
    if bad:
        return {"verdict": "refused", "reason": f"shared_with names {bad!r}, not role slugs"}
    if klass not in CLAIM_CLASSES:
        return {"verdict": "refused", "reason": f"roles_class {klass!r} is not a claim class"}
    hits = credential_hits(parsed["body"])
    if hits:
        return {"verdict": "refused", "reason": f"carries a {hits[0]} by shape; nothing of it leaves the account"}
    # A memory in another language drains through its English rendering.
    text, language = parsed["body"], None
    original, rendering = split_rendering(parsed["body"])
    # The cue counts as much as the body: an index line in another
    # script is read by every holder of the role, in every project. A
    # non-Latin description needs `description_en` beside it, or the
    # memory waits, named, like an unrendered body.
    title = parsed["description"] or name
    if is_mostly_non_latin(title):
        if not parsed["description_en"] or is_mostly_non_latin(parsed["description_en"]):
            return {"verdict": "held", "reason": "the description is not in Latin script and has no description_en"}
        title = parsed["description_en"]
    if is_mostly_non_latin(original):
        if not rendering or is_mostly_non_latin(rendering):
            return {"verdict": "held", "reason": "the body has no '## English' rendering"}
        text, language = rendering, "non-latin"
        for script_name, lo, hi in (("ka", 0x10A0, 0x10FF), ("ru", 0x0400, 0x04FF), ("el", 0x0370, 0x03FF),
                                    ("hy", 0x0530, 0x058F), ("he", 0x0590, 0x05FF), ("ar", 0x0600, 0x06FF)):
            if any(lo <= ord(ch) <= hi for ch in original):
                language = script_name
                break
    return {"verdict": "taken", "text": text, "title": title, "language": language}


def observed_date(stamp: str | None, path: str) -> str:
    """YYYY-MM-DD from an ISO stamp, else from the file's mtime (UTC)."""
    if stamp and re.match(r"^\d{4}-\d{2}-\d{2}", stamp.strip()):
        return stamp.strip()[:10]
    return time.strftime("%Y-%m-%d", time.gmtime(os.path.getmtime(path)))


def content_hash(name: str, body: str) -> str:
    """Stable id for a memory, so re-drains do not duplicate its claim.

    Over name + body, NOT the file path: a renamed file carrying the same
    fact is the same evidence, and a rewritten body is new evidence even
    under the same name. Sixteen hex chars, matching the existing
    derived_from ids in .roles/.
    """
    digest = hashlib.sha256(f"{name}\n{body}".encode("utf-8")).hexdigest()
    return digest[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--role", default=None,
                    help="role these claims belong to (default: the agent's active role)")
    ap.add_argument("--out", default=None, help="output directory (or --bundle)")
    ap.add_argument("--bundle", default=None, metavar="FILE|-",
                    help="write the drain as one tar with a manifest (- for stdout) instead of a directory")
    ap.add_argument("--memory", default=None,
                    help="memory dir (default: the one Claude Code keeps for --working-copy)")
    ap.add_argument("--working-copy", default=None,
                    help="the checkout whose memory is drained (default: cwd); sets project and label")
    ap.add_argument("--project", default=None,
                    help="logical project id (default: resolved from the working copy's remote)")
    ap.add_argument("--host", default=None, help="host label (default: hostname -s)")
    ap.add_argument("--all", action="store_true",
                    help="harvest every memory, not only those newer than the project's last drain watermark")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()
    if bool(args.out) == bool(args.bundle):
        print("harvest_memory: exactly one of --out DIR or --bundle FILE|- (the bundle is the drain as one tar)", file=sys.stderr)
        return 2
    if args.bundle:
        # The directory form, then packed: one writer for both shapes.
        args.out = tempfile.mkdtemp(prefix="harvest-bundle-")
        # write_bundle removes it after packing; every earlier return
        # (no role, no memory directory, a refused claim) would leave it.
        atexit.register(shutil.rmtree, args.out, ignore_errors=True)

    working_copy = os.path.abspath(args.working_copy or os.getcwd())
    ctx = identity.resolve_context(cwd=working_copy)
    role = args.role or ctx.get("role")
    if not role:
        print("harvest_memory: no --role given and the agent has no active role binding",
              file=sys.stderr)
        return 2
    memory_dir = args.memory or default_memory_dir(working_copy)
    if not os.path.isdir(memory_dir):
        print(f"harvest_memory: no memory directory at {memory_dir}", file=sys.stderr)
        return 2
    host = args.host or ctx["host"]
    project = args.project or ctx.get("project")
    label = ctx.get("working_copy_id") or os.path.basename(working_copy)

    # THE WATERMARK. The assembler commits, per host, the ms-epoch up to
    # which a drain read the store (last-drain-report.json, `watermarks`),
    # and reads it back from <drain>/harvest-report.json — which this
    # harvester never wrote, so every memory-era drain committed an empty
    # map, the next drain could not answer "since when", and fabric-status
    # counted undrained memories "since ever" (2026-09-15). Now: memories
    # newer than the last watermark for this host are in scope (all of
    # them under --all, or when there is no report yet), and the report
    # carries the max mtime read as the next watermark.
    since_ms, since_report = (0, None) if args.all else previous_watermark(working_copy, host, ctx["agent"])
    next_ms = since_ms
    total = 0
    before_watermark: list[str] = []

    claims: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    skipped: list[str] = []
    needs_rendering: list[str] = []
    unrendered_ms: list[int] = []
    refusals: list[str] = []

    for name in sorted(os.listdir(memory_dir)):
        if not name.endswith(".md"):
            continue
        parsed = parse_memory(os.path.join(memory_dir, name))
        if parsed is None:
            continue                    # no frontmatter: the index, not a memory
        total += 1
        if parsed["mtime_ms"] <= since_ms:
            before_watermark.append(name)   # drained already; merge mode would no-op it
            continue
        mtype = parsed["type"]
        klass = parsed["roles_class"]
        if not klass:
            skipped.append(name)        # not role knowledge, or not yet said so
            next_ms = max(next_ms, parsed["mtime_ms"])
            continue
        judged = judge_memory(parsed)
        if judged["verdict"] == "refused":
            refusals.append(f"{name}: {judged['reason']}")
            continue
        if judged["verdict"] == "held":
            # Named in every report until rendered: the watermark does
            # not pass it (the charter: "never dropped").
            needs_rendering.append(name)
            unrendered_ms.append(parsed["mtime_ms"])
            continue
        text, language, title = judged["text"], judged["language"], judged["title"]
        cid = content_hash(parsed["name"], parsed["body"])
        observations.append({
            "content_hash": cid,
            # Who learned it, where, and what it applies to — separate
            # facts. `agent` is the login; `working_copy` is a label.
            "agent": ctx["agent"],
            "host": host,
            "project": project,
            "working_copy": label,
            "session": ctx.get("session"),
            "type": mtype,
            "title": parsed["name"],
            "text": text,
            "created_at_epoch": parsed["mtime"],
            **({"language": language} if language else {}),
        })
        next_ms = max(next_ms, parsed["mtime_ms"])
        claims.append({
            "topic": parsed["name"],
            "title": title,
            "class": klass,
            "knowledge_scope": "full",
            "body": text,
            "observed_at": parsed["observed_at"],
            **({"merge_target": parsed["merge_target"]} if parsed["merge_target"] else {}),
            # Two or more owners is the assembler's route to a shared slice
            # (memory/README.md, "Four scopes"); a memory names its co-owners
            # and the drain carries them, so a fact every role needs is not
            # stuck in the harvesting role's own directory.
            **({"shared_with": parsed["shared_with"]} if parsed["shared_with"] else {}),
            # An OBJECT keyed by kind, not a list: assemble.py calls
            # .values() on this field. A memory's wikilinks are memory
            # slugs, so they get their own kind rather than being passed
            # off as artifact references.
            "citations": ({"memories": parsed["links"]} if parsed["links"] else {}),
            "evidence": [cid],
        })

    if refusals:
        # Refuse the WHOLE drain, not the offending file. A partial claims
        # file looks complete to the assembler, and the memory that was
        # skipped is exactly the one nobody knew how to file.
        print("harvest_memory: refusing rather than guessing where these "
              "belong:", file=sys.stderr)
        for r in refusals:
            print(f"  {r}", file=sys.stderr)
        return 1

    # The watermark stops below the oldest unrendered memory, whatever drained
    # after it: the next incremental drain names it again (the charter:
    # "never dropped"), at the price of re-reading what came after — which
    # the assembler dedupes by content hash.
    if unrendered_ms:
        next_ms = min(next_ms, min(unrendered_ms) - 1)
    report = {
        "role": role, "agent": ctx["agent"], "host": host, "project": project,
        "working_copy": label, "memory_dir": memory_dir,
        "claims": len(claims),
        # NAMED, not counted. A count tells you something was left out; the
        # names tell you whether it should have been.
        "skipped_no_roles_class": skipped,
        # Named too: a memory in another language that carries no English
        # rendering yet — the holder renders it, then the drain takes it.
        "needs_rendering": needs_rendering,
        # The window this drain read, in the shape the assembler carries
        # into the committed report (`harvest`, `watermarks`).
        "since_watermark": since_ms,
        "since_report": since_report,
        "next_watermark": next_ms,
        "counts": {"in_scope": total - len(before_watermark), "total": total,
                   "before_watermark": len(before_watermark), "provisional_agent": 0},
    }
    if args.dry_run:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    # The role payload goes in its own subdirectory. assemble.py treats
    # EVERY .json under --claims as a role payload, so a references.json
    # sitting beside it aborts the run with KeyError: 'role'.
    claims_dir = os.path.join(args.out, "claims")
    os.makedirs(claims_dir, exist_ok=True)
    with open(os.path.join(claims_dir, f"{role}.json"), "w", encoding="utf-8") as fh:
        # Only the keys the claims contract declares; it sets
        # additionalProperties: false, and the assembler reads these to
        # print the per-role admitted/rejected line.
        json.dump({"role": role, "claims": claims,
                   # observations_in counts every memory READ, not every
                   # one admitted: an observation is appended in the same
                   # iteration as its claim, so len(observations) equalled
                   # len(claims) for every drain and the admitted/read
                   # ratio the schema describes as an alarm was always 1.
                   # rejected counts opt-outs only; a memory whose class is
                   # unfilable aborts the whole drain and never reaches
                   # this writer.
                   "telemetry": {"observations_in": len(claims) + len(skipped),
                                 "candidates": len(claims) + len(skipped),
                                 "admitted": len(claims),
                                 "merged_into_existing": 0,
                                 "rejected": len(skipped)}},
                  fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    with open(os.path.join(args.out, "observations.jsonl"), "w", encoding="utf-8") as fh:
        for row in observations:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    # assemble.py requires this file to exist; memories cite each other by
    # name, not by git object, so there is no citation graph to build.
    with open(os.path.join(args.out, "references.json"), "w", encoding="utf-8") as fh:
        json.dump({}, fh)
        fh.write("\n")
    # What the assembler reads for the committed report's `harvest` and
    # `watermarks`: the same dict, minus the memory directory (an absolute
    # path into a home; the assembler drops such things, this never offers).
    with open(os.path.join(args.out, "harvest-report.json"), "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in report.items() if k != "memory_dir"}, fh, indent=2, sort_keys=True)
        fh.write("\n")

    if args.bundle:
        return write_bundle(args.out, args.bundle, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


BUNDLE_FILES = ("harvest-report.json", "references.json", "observations.jsonl")


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_bundle(drain: str, target: str, report: dict) -> int:
    """The drain directory as one tar: its files under their names, plus
    manifest.json first — who harvested, the window, and the digest of
    every file — so the receiver can refuse a bundle that was cut short
    or changed on the way. Deterministic (fixed mtimes, sorted names).
    The report goes to stderr: stdout may be the tar."""
    files = [f for f in BUNDLE_FILES if os.path.exists(os.path.join(drain, f))]
    files += sorted(os.path.join("claims", n) for n in os.listdir(os.path.join(drain, "claims")))
    manifest = {
        "format": "agent-fabric-drain/1",
        "agent": report["agent"], "host": report["host"], "role": report["role"],
        "project": report["project"], "working_copy": report["working_copy"],
        "since_watermark": report["since_watermark"], "next_watermark": report["next_watermark"],
        "claims": report["claims"],
        "files": {f: sha256_of(os.path.join(drain, f)) for f in files},
    }
    mbytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    out = sys.stdout.buffer if target == "-" else open(target, "wb")
    try:
        with tarfile.open(fileobj=out, mode="w|") as tar:
            info = tarfile.TarInfo("manifest.json"); info.size = len(mbytes); info.mtime = 0; info.mode = 0o644
            tar.addfile(info, io.BytesIO(mbytes))
            for f in files:
                info = tar.gettarinfo(os.path.join(drain, f), arcname=f)
                info.mtime = 0; info.uid = info.gid = 0; info.uname = info.gname = ""
                with open(os.path.join(drain, f), "rb") as fh:
                    tar.addfile(info, fh)
    finally:
        if target != "-":
            out.close()
    shutil.rmtree(drain, ignore_errors=True)
    print(json.dumps({k: v for k, v in report.items() if k != "memory_dir"}, indent=2, sort_keys=True), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
