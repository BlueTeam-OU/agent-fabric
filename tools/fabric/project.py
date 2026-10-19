#!/usr/bin/env python3
"""tools/fabric/project.py — `fabric-project import`: write a new managed
project's fabric-side files from a sibling (agent-fabric skill repo-lifecycle
§B steps 2-4; bin/fabric-project is its shim).

CONTRACT
  argv      import --id ID --like SIBLING --client CLIENT --remote R
            [--remote R ...] --default-branch B --license SPDX --role ROLE
            [--role ROLE ...] [--title T] [--working-copy DIR]
            [--like-working-copy DIR] [--with-compliance] [--with-trial]
            [--with-pr-tools] [--write]
            Without --write nothing is written: the plan is printed.
  env       AGENT_FABRIC_OPERATOR (through roots, to find the sibling's checkout
            beside this one), PATH (git). GIT_* is dropped at the start: a hook's
            GIT_DIR would aim every git call, the sibling lookup's included, at
            another repository. The tree it edits is the one this file sits in.
  stdin     not read
  stdout    the plan (each file, with its size), a diff of projects/registry.json,
            and what was written; --help
  stderr    every refusal, prefixed `fabric-project: `, any file a failed
            write had already created, and each stub remit with why it is one
  exit      0 planned or written; 2 refused (a bad argument, an id or a remote
            already registered, an unknown client, sibling or role, a file
            that exists, anything it cannot read); 1 a write that failed
            part-way (the files it had created are named)

Writes (never commits, never pushes, never overwrites a file):
  projects/registry.json                one entry, inserted as text after the
                                        last one so every other byte stays
  projects/<id>/integration/...         the sibling's files, its id replaced
  <working copy>/.agent-fabric/taxonomy.json, roles/<role>.md, fabric-ref

Choices a reader would otherwise have to guess:
  - the entry takes the sibling's keys in the sibling's order; client, remotes,
    default branch and licence come from the flags, the title from --title
    (else the sibling's, which the plan flags), `moved_from` is never copied,
    and tools (and agent_env / plain_env, where the sibling has them) are
    empty: what a project needs is its own to declare;
  - the sibling's id is replaced where it stands alone as a word, or as the
    directory under `projects/`; never inside a repository name
    (`owner/<id>`), a dotted or dashed identifier (`<id>.decks`,
    `<id>-claude2`) or a channel (`<id>:`). Every line that still names the
    sibling after that is listed, since the prose is the sibling's too;
  - the taxonomy is built fresh, not copied: the sibling's path rules describe
    its tree. Each role gets an empty rule to be filled by fabric-coordinator;
  - a remit is the sibling's with only its frontmatter `project:` set; a role
    the sibling lacks, or every role when its working copy is not found, gets a
    stub naming fabric-coordinator as author, marked `[stub remit]` in the plan
    and named on stderr;
  - fabric-ref is the full commit id of this repository's origin/main as last
    fetched.
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import json
import os
import re
import stat
import subprocess
import sys

# A dry run writes nothing, and the bytecode of the modules it imports is a write.
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import roots  # noqa: E402
import workingcopy  # noqa: E402

ID_RE = re.compile(r"[a-z]([a-z0-9.-]*[a-z0-9])?")
GIT_TIMEOUT_S = 30
# Only where the sibling uses the verb, and only when asked (the skill: they
# exist "only where the project uses those fabric-pr verbs").
OPT_IN = {
    "gh/compliance.json": "--with-compliance",
    "gh/trial.json": "--with-trial",
    "pr-tools.json": "--with-pr-tools",
}

HELP = __doc__


class Refused(Exception):
    pass


def say(msg: str) -> None:
    sys.stdout.flush()
    print(f"fabric-project: {msg}", file=sys.stderr)


def _load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        raise Refused(f"cannot read {path}: {e}")
    if not isinstance(doc, dict):
        raise Refused(f"{path} is not a JSON object")
    return doc


def replace_id(text: str, old: str, new: str) -> str:
    # The optional directory prefix is consumed so `owner/<id>` can be told
    # from `projects/<id>`; a lookbehind cannot be variable-width.
    pattern = re.compile(r"(?<![\w.\-])((?:[\w.\-]+/)?)" + re.escape(old) + r"(?![\w\-:@]|\.\w)")

    def sub(m: re.Match) -> str:
        return m.group(0) if m.group(1) not in ("", "projects/") else m.group(1) + new

    return pattern.sub(sub, text)


def build_entry(like: dict, args: argparse.Namespace, today: str) -> dict:
    values = {
        "client": args.client,
        "title": args.title if args.title is not None else like.get("title", args.id),
        "remotes": list(args.remote),
        "default_branch": args.default_branch,
        "taxonomy": like.get("taxonomy", ".agent-fabric/taxonomy.json"),
        "memory": like.get("memory", ".agent-fabric/memory"),
        "integration": f"projects/{args.id}/integration",
        "license": args.license,
        "agent_env": {},
        "plain_env": [],
        "note": f"imported {today}",
        "tools": [],
    }
    # agent_env and plain_env follow the sibling: a project without them has
    # none to declare, and an empty pair would be noise in its entry.
    keys = [k for k in like if k in values]
    for k in ("note", "tools"):
        if k not in keys:
            keys.append(k)
    return {k: values[k] for k in keys}


def insert_entry(raw: str, pid: str, entry: dict) -> str:
    """The registry is hand-formatted (tools lists are inline); a re-dump would
    rewrite it all, so the new entry goes in as text after the last one."""
    tail = "\n    }\n  }\n}\n"
    if not raw.endswith(tail):
        raise Refused("projects/registry.json does not end as the importer expects (its last project, then the "
                      "projects object, then the file); add the entry by hand")
    body = json.dumps(entry, indent=2, ensure_ascii=False).replace("\n", "\n    ")
    out = raw[: -len(tail)] + "\n    },\n    " + json.dumps(pid) + ": " + body + "\n  }\n}\n"
    try:
        old, new = json.loads(raw)["projects"], json.loads(out)["projects"]
    except (ValueError, KeyError):
        raise Refused("projects/registry.json does not parse after the insertion; nothing written")
    if set(new) != set(old) | {pid} or any(new[k] != old[k] for k in old) or new[pid] != entry:
        raise Refused("projects/registry.json changed beyond the new entry; nothing written")
    return out


def taxonomy_doc(pid: str, roles: list[str]) -> dict:
    return {
        "version": 1,
        "project": pid,
        "note": "Binding rules for this project, imported as a skeleton: each role's paths and keywords are "
                "fabric-coordinator's to fill from the repository.",
        "projects": {"include": [pid], "exclude": [], "unattributed_bucket": "observer-sessions"},
        "reattribution": {"path_markers": {"include": [], "exclude": []},
                          "keywords": {"include": [pid], "exclude": []}},
        "roles": [{"id": r, "paths": [], "keywords": [], "types": []} for r in roles],
    }


def _frontmatter_project(text: str, pid: str, where: str) -> str:
    m = re.match(r"---\n(.*?\n)---\n", text, re.S)
    if not m or len(re.findall(r"^project:.*$", m.group(1), re.M)) != 1:
        raise Refused(f"{where}: no frontmatter with exactly one `project:` line to set")
    front = re.sub(r"^project:.*$", f"project: {pid}", m.group(1), count=1, flags=re.M)
    return "---\n" + front + text[m.end() - 4:]


def stub_remit(role: str, pid: str) -> str:
    return (f"---\nrole: {role}\nclass: remit\nproject: {pid}\n"
            f"description: \"What {role} covers in {pid}: not written yet.\"\n"
            "origin:\n  - agent: fabric-coordinator\n---\n\n"
            f"# {role} — remit in {pid}\n\n"
            "Not written yet. fabric-coordinator writes this remit; until it does, the role's charter is the\n"
            "whole of what it is told about this project.\n")


def _git_origin_main() -> str:
    try:
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--verify", "origin/main^{commit}"],
                           capture_output=True, text=True, timeout=GIT_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Refused(f"cannot read origin/main of {ROOT}: {e}")
    sha = r.stdout.strip()
    if r.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise Refused(f"cannot read origin/main of {ROOT} (git said: {r.stderr.strip() or sha!r}); fetch first")
    return sha


def _decode(data: bytes, where: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise Refused(f"{where} is not UTF-8: {e}")


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as e:
        raise Refused(f"cannot read {path}: {e}")


def plan(args: argparse.Namespace, root: str, today: str) -> tuple[list[dict], str, str, list[str]]:
    """Everything that can be refused is refused here, before the first
    write: returns (files, old registry text, new registry text, residue)."""
    if not ID_RE.fullmatch(args.id) or ".." in args.id:
        raise Refused(f"--id {args.id!r}: a lowercase letter, then lowercase letters, digits, '.' or '-', "
                      "ending in a letter or digit, no '..'")
    for flag, value in (("--default-branch", args.default_branch), ("--license", args.license), ("--title", args.title),
                        # An unset shell variable arrives as "": truthiness below would read it as "flag absent".
                        ("--working-copy", args.working_copy), ("--like-working-copy", args.like_working_copy)):
        if value is not None and not value.strip():
            raise Refused(f"{flag} is empty")
    if not args.remote:
        raise Refused("at least one --remote is required")
    if len(set(args.remote)) != len(args.remote) or len(set(args.role)) != len(args.role):
        raise Refused("a --remote or --role is given twice")
    reg_path = roots.projects_registry(root=root)
    raw = _decode(_read_bytes(reg_path), reg_path)
    projects = _load_json(reg_path).get("projects") or {}
    if args.id in projects:
        raise Refused(f"--id {args.id}: already registered in projects/registry.json")
    # Whatever else projects/ holds (schemas/, registry.json, clients.json) is not an id;
    # a directory of only integration/ is a half-finished import, left to the per-file refusal.
    held = os.path.join(roots.projects_dir(root=root), args.id)
    # A symlink at either level would carry the writes out of the tree.
    if os.path.lexists(held) and not (os.path.isdir(held) and not os.path.islink(held)
                                      and not os.path.islink(os.path.join(held, "integration"))
                                      and set(os.listdir(held)) <= {"integration"}):
        raise Refused(f"--id {args.id}: projects/{args.id} exists and is not a registered project")
    if args.like not in projects:
        raise Refused(f"--like {args.like}: not a registered project")
    # The registry's own comparison (what resolves a clone to a project), so a
    # spelling it calls the same repository is never accepted here: an entry
    # appended behind a registered one is shadowed without any error.
    taken = {workingcopy.canonical_remote(r): pid for pid, p in projects.items()
             for r in (p.get("remotes") or []) + (p.get("moved_from") or [])}
    for r in args.remote:
        key = workingcopy.canonical_remote(r)
        if key is None:
            raise Refused(f"--remote {r}: not a remote repository URL")
        if key in taken:
            raise Refused(f"--remote {r}: already registered to {taken[key]}")
    clients = _load_json(roots.clients_registry(root=root)).get("clients") or {}
    if args.client not in clients:
        raise Refused(f"--client {args.client}: not in projects/clients.json (known: {', '.join(sorted(clients))})")
    catalog = {r.get("id") for r in _load_json(roots.role_catalog(root=root)).get("roles") or []}
    for role in args.role:
        if role not in catalog:
            raise Refused(f"--role {role}: not in identities/roles/catalog.json")

    like = projects[args.like]
    entry = build_entry(like, args, today)
    new_raw = insert_entry(raw, args.id, entry)

    files: list[dict] = []
    residue: list[str] = []
    src_dir = roots.project_integration(args.like, root=root)
    dst_dir = roots.project_integration(args.id, root=root)
    present = set()
    for base, dirs, names in os.walk(src_dir):
        dirs.sort()
        for d in dirs:
            if os.path.islink(os.path.join(base, d)):
                raise Refused(f"{os.path.join(base, d)} is a symlink; not copied")
        for name in sorted(names):
            full = os.path.join(base, name)
            rel = os.path.relpath(full, src_dir)
            if os.path.islink(full):
                raise Refused(f"{full} is a symlink; not copied")
            present.add(rel)
            flag = OPT_IN.get(rel)
            if flag and not getattr(args, flag[2:].replace("-", "_")):
                continue
            data = _read_bytes(full)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text is not None:
                swapped = replace_id(text, args.like, args.id)
                data = swapped.encode("utf-8")
                residue += [f"projects/{args.id}/integration/{rel}:{n}: {line.strip()[:100]}"
                            for n, line in enumerate(swapped.splitlines(), 1) if args.like.lower() in line.lower()]
            files.append({"path": os.path.join(dst_dir, rel), "data": data, "mode": os.stat(full).st_mode & 0o777})
    for rel, flag in OPT_IN.items():
        if getattr(args, flag[2:].replace("-", "_")) and rel not in present:
            raise Refused(f"{flag}: --like {args.like} has no integration/{rel}")
    if not files:
        raise Refused(f"--like {args.like}: projects/{args.like}/integration holds nothing to copy")

    if args.working_copy:
        wc = os.path.abspath(args.working_copy)
        if not os.path.isdir(wc):
            raise Refused(f"--working-copy {args.working_copy}: not a directory")
        af = os.path.join(wc, ".agent-fabric")
        tax = taxonomy_doc(args.id, args.role)
        schema = _load_json(os.path.join(roots.projects_dir(root=root), "schemas", "taxonomy.schema.json"))
        from lint_rules.schema import validate_json
        bad = validate_json(schema, tax, "taxonomy.json")
        if bad:
            raise Refused("the taxonomy it built does not validate: " + "; ".join(bad))
        files.append({"path": os.path.join(af, "taxonomy.json"),
                      "data": (json.dumps(tax, indent=2, ensure_ascii=False) + "\n").encode(), "mode": 0o644})
        like_wc = args.like_working_copy
        if like_wc and not os.path.isdir(like_wc):
            raise Refused(f"--like-working-copy {like_wc}: not a directory")
        if not like_wc:
            like_wc = workingcopy.sibling_working_copies(root).get(args.like)
        for role in args.role:
            why = ""
            src = os.path.join(like_wc, ".agent-fabric", "roles", f"{role}.md") if like_wc else None
            if src and os.path.exists(src):
                text = _frontmatter_project(_decode(_read_bytes(src), src), args.id, src)
            else:
                text = stub_remit(role, args.id)
                why = (f"{src} does not exist" if src else
                       f"{args.like}'s working copy was not found beside this one: pass --like-working-copy DIR")
            files.append({"path": os.path.join(af, "roles", f"{role}.md"), "data": text.encode(), "mode": 0o644, "stub": why})
        files.append({"path": os.path.join(af, "fabric-ref"), "data": (_git_origin_main() + "\n").encode(), "mode": 0o644})
    elif args.like_working_copy:
        raise Refused("--like-working-copy without --working-copy has nothing to write into")

    # Every directory between projects/<id> and a planned file, not only the two
    # the check above names: a link at any of them carries the write out of the tree.
    for f in files:
        if f["path"].startswith(dst_dir + os.sep):
            here = os.path.dirname(f["path"])
            while here != os.path.dirname(held):
                if os.path.islink(here):
                    raise Refused(f"{here} is a symlink; nothing is written through it")
                here = os.path.dirname(here)
    for f in files:
        if os.path.lexists(f["path"]):
            raise Refused(f"{f['path']} exists; nothing is overwritten")
    return files, raw, new_raw, residue


def write_all(files: list[dict], reg_path: str, new_raw: str) -> None:
    made: list[str] = []
    try:
        for f in files:
            os.makedirs(os.path.dirname(f["path"]), exist_ok=True)
            # O_EXCL: a file that appeared since the plan is not overwritten.
            fd = os.open(f["path"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, f["mode"])
            made.append(f["path"])
            with os.fdopen(fd, "wb") as fh:
                fh.write(f["data"])
            os.chmod(f["path"], f["mode"])
        # Last: the registry entry is what makes the project exist, so a
        # failure before it leaves files and no project, and a rerun says so.
        # The file's own mode and place are kept: a replace takes the umask's
        # mode, and over a symlink it would swap the link for a file.
        target = os.path.realpath(reg_path)
        tmp = target + ".import.tmp"
        with open(tmp, "x", encoding="utf-8") as fh:
            fh.write(new_raw)
        os.chmod(tmp, stat.S_IMODE(os.stat(target).st_mode))
        os.replace(tmp, target)
    except OSError as e:
        if made:
            say("written before the failure, remove or keep: " + ", ".join(made))
        raise OSError(f"write failed: {e}") from e


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="fabric-project import", add_help=False)
    ap.add_argument("--id", required=True)
    ap.add_argument("--like", required=True)
    ap.add_argument("--client", required=True)
    ap.add_argument("--remote", action="append", default=[])
    ap.add_argument("--default-branch", required=True)
    ap.add_argument("--license", required=True)
    ap.add_argument("--role", action="append", default=[])
    ap.add_argument("--title")
    ap.add_argument("--working-copy")
    ap.add_argument("--like-working-copy")
    for flag in OPT_IN.values():
        ap.add_argument(flag, action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    return ap


def run(argv: list[str], root: str = ROOT, today: str | None = None) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(HELP)
        return 0 if argv else 2
    if argv[0] != "import":
        raise Refused(f"unknown subcommand {argv[0]!r}; the only one is import")
    ap = parser()
    ap.error = lambda msg: (_ for _ in ()).throw(Refused(msg))  # type: ignore[method-assign]
    args = ap.parse_args(argv[1:])
    if args.help:
        print(HELP)
        return 0
    if not args.role:
        raise Refused("at least one --role is required")
    today = today or datetime.date.today().isoformat()
    files, raw, new_raw, residue = plan(args, root, today)
    reg_path = roots.projects_registry(root=root)
    # ROOT is the checkout this file sits in, not the cwd: through a link in
    # ~/.local/bin the writes land there, so the plan has to say where.
    print(("writing" if args.write else "dry run, nothing written; would write") + f" {len(files) + 1} files; the fabric tree is {root}, working-copy files are absolute:")
    for f in files:
        print(f"  {os.path.relpath(f['path'], root) if f['path'].startswith(root + os.sep) else f['path']}  ({len(f['data'])} bytes)"
              + ("  [stub remit]" if f.get("stub") else ""))
    for f in files:
        if f.get("stub"):
            say(f"stub remit for {os.path.basename(f['path'])[:-3]}: {f['stub']}")
    print("  projects/registry.json  (one entry added)")
    print("".join(l if l.endswith("\n") else l + "\n" for l in difflib.unified_diff(
        raw.splitlines(True), new_raw.splitlines(True), "a/projects/registry.json", "b/projects/registry.json", n=2)), end="")
    like = _load_json(reg_path)["projects"][args.like]
    if args.title is None:
        print(f"note: the title is {args.like}'s ({like.get('title')!r}); --title sets it")
    if residue:
        print(f"still naming {args.like} after the replacement (the copied prose is {args.like}'s, review it):")
        for line in residue:
            print(f"  {line}")
    if args.write:
        write_all(files, reg_path, new_raw)
        print("written; nothing committed or pushed")
    return 0


def main() -> int:
    sys.stdout.reconfigure(errors="surrogateescape")
    sys.stderr.reconfigure(errors="surrogateescape")
    for name in [k for k in os.environ if k.startswith("GIT_")]:
        del os.environ[name]
    try:
        return run(sys.argv[1:])
    except Refused as e:
        say(str(e))
        return 2
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    except OSError as e:
        say(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
