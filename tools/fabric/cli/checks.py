"""tools/fabric/cli/checks.py — the two checks ADR-068 puts in lint (rules 3 and 7). Wiring them into lint and the
pre-commit hook, the catalogue entry and the exceptions file (policies/command-names.json) are the control plane's.

table_findings(doc, own_verbs) — the `fabric` table against `commands` (rule 3), one finding per fault:
- the table is missing or malformed;
- a command in `commands` that no form reaches, or that two forms reach (the dispatcher `fabric` itself is in `commands`
  so bootstrap links it, and is reached by no form);
- a form that names a command not in `commands` (the dispatcher included: `fabric fabric` would loop);
- a verb the noun lists although the noun's own command also takes it as a verb. Which verbs a command takes lives in
  its module, not in a table, so the caller supplies `own_verbs` {command: verbs}; without it that clause is not judged
  and the finding list says so.

literal_findings(rel, text, names, allowed) / tree_findings(...) — the mechanism's checker (rule 7): a literal that names
a `commands` command in a comparison (==, !=, in, not in), a regex (a re.* call) or a str.startswith/endswith/find/
rfind/index/count call, in runtime/claude-code/hooks/*.py or tools/fabric/guards/*.py (tools/fabric/cli/, the owner, is outside both), is a finding: the module
recognises a command by name instead of asking canonical(). The policy file lists the modules admitted whole, each with
why it cannot ask; an entry that admits nothing is a finding.

It is a static reader and under-reports: a name held in a variable (`CMD = "fabric-pr"; x == CMD`), a literal built at
run time, or a name in an f-string's expression is not seen; a literal in a docstring or a message is not a comparison
and is not judged. A name is a whole token: not inside a longer name (`fabric-pr-x`), a directory (`tools/fabric/`), a
file (`fabric.py`); a `bin/` prefix and a regex's `\\b` before it count as part of the token's edge."""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import warnings

from . import table

POLICY = "policies/command-names.json"
POLICY_KEY = "recognisers"
JUDGED_DIRS = ("runtime/claude-code/hooks/", "tools/fabric/guards/")
STR_METHODS = frozenset({"startswith", "endswith", "find", "rfind", "index", "count"})
RE_FUNCS = frozenset({"compile", "match", "search", "fullmatch", "findall", "finditer", "sub", "subn", "split"})
NAME_CHARS = re.compile(r"[\w.-]")


def table_findings(doc: object, own_verbs: dict[str, set[str]] | None = None) -> list[str]:
    if not isinstance(doc, dict):
        return ["commands.json: not a JSON object"]
    try:
        commands = table.commands_of(doc)
        nouns = table.nouns_of(doc)
    except table.TableError as exc:
        return [str(exc)]
    reached: dict[str, list[str]] = {}
    out: list[str] = []
    for noun in sorted(nouns):
        entry = nouns[noun]
        if "command" in entry:
            reached.setdefault(entry["command"], []).append(f"fabric {noun}")
        for verb, cmd in sorted(entry.get("verbs", {}).items()):
            reached.setdefault(cmd, []).append(f"fabric {noun} {verb}")
            taken = (own_verbs or {}).get(entry.get("command", ""), set())
            if verb in taken:
                out.append(f"fabric.nouns.{noun}.verbs.{verb}: {entry['command']} takes `{verb}` as its own verb, so the form "
                           f"`fabric {noun} {verb}` would reach {cmd}, not what `{entry['command']} {verb}` does")
    for cmd, forms in sorted(reached.items()):
        if cmd not in commands:
            out.append(f"{', '.join(forms)}: names {cmd}, which is not in `commands`")
        elif cmd == "fabric":
            out.append(f"{', '.join(forms)}: names the dispatcher itself")
        elif len(forms) > 1:
            out.append(f"{cmd} is reached by {len(forms)} forms ({', '.join(forms)}); one command, one form")
    out += [f"{cmd}: in `commands` and reached by no `fabric` form" for cmd in sorted(commands) if cmd != "fabric" and cmd not in reached]
    if "fabric" not in commands:
        out.append("`fabric` is not in `commands`: bootstrap would not link the dispatcher (rule 8)")
    if own_verbs is None:
        out.append("note: own_verbs not supplied; the clause 'no listed verb that the noun's own command takes' was not judged")
    return out


def _token_in(text: str, name: str) -> bool:
    start = text.find(name)
    while start != -1:
        end = start + len(name)
        before = text[:start]
        if before.endswith("\\b"):                       # a regex's word boundary, not a name character
            before = before[:-2]
        in_bin = before.endswith("bin/")
        if in_bin:
            before = before[:-4]
        edge_before = not before or not NAME_CHARS.match(before[-1]) and (in_bin or before[-1] != "/")
        edge_after = end == len(text) or not (NAME_CHARS.match(text[end]) or text[end] == "/")
        if edge_before and edge_after:
            return True
        start = text.find(name, start + 1)
    return False


def _names_in(text: str, names: list[str]) -> list[str]:
    return [n for n in names if _token_in(text, n)]


def _literals(node: ast.AST) -> list[ast.Constant]:
    """The string constants of a comparison's operand or a call's argument: itself, or the elements of a literal
    tuple, list or set; an f-string's text parts."""
    if isinstance(node, ast.Constant):
        return [node] if isinstance(node.value, str) else []
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [c for e in node.elts for c in _literals(e)]
    if isinstance(node, ast.JoinedStr):
        return [c for v in node.values for c in _literals(v)]
    return []


def _call_kind(call: ast.Call) -> str | None:
    fn = call.func
    if isinstance(fn, ast.Attribute):
        if fn.attr in STR_METHODS:
            return "string test"
        if isinstance(fn.value, ast.Name) and fn.value.id == "re" and fn.attr in RE_FUNCS:
            return "regex"
        if fn.attr in ("match", "search", "fullmatch", "sub", "findall"):   # a compiled pattern's method has its pattern elsewhere
            return None
    return None


def sites(text: str, names: list[str], rel: str = "<module>") -> list[tuple[int, str, str]]:
    """[(line, name, how)] of each command name a comparison, regex or string test spells; [] for a module that does not parse
    (ruff refuses it in CI)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)   # the scanned file's own invalid escape is its own lint's
            tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return []
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            operands, how = [node.left, *node.comparators], "comparison"
        elif isinstance(node, ast.Call) and _call_kind(node):
            operands, how = list(node.args), _call_kind(node)
        else:
            continue
        for operand in operands:
            for const in _literals(operand):
                found += [(const.lineno, n, how) for n in _names_in(const.value, names)]
    return sorted(set(found))


def literal_findings(rel: str, text: str, names: list[str], allowed: dict[str, str]) -> list[str]:
    if rel in allowed:
        return []
    return [f"{rel}:{line}: {how} names the command `{name}`; ask tools/fabric/cli canonical() (ADR-068 rule 7), or "
            f"list the module in {POLICY} with why it cannot"
            for line, name, how in sites(text, names, rel)]


def parse_allowed(text: str) -> dict[str, str]:
    """{module path: why it is admitted}; ValueError when the text is not JSON. An entry that is not a string pair admits nothing."""
    doc = json.loads(text)
    entries = doc.get(POLICY_KEY) if isinstance(doc, dict) else None
    return {k: v for k, v in entries.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(entries, dict) else {}


def judged_path(rel: str) -> bool:
    return rel.endswith(".py") and rel.startswith(JUDGED_DIRS) and "/testdata/" not in rel


def tree_findings(root: str, tracked: list[str], policy_text: str | None, doc: dict) -> list[str]:
    """Every finding over `tracked` (paths relative to root). `policy_text` None: no policy file, nothing admitted."""
    try:
        allowed = parse_allowed(policy_text) if policy_text is not None else {}
    except ValueError as exc:
        return [f"{POLICY}: cannot be read as JSON ({exc.__class__.__name__}); command names are not judged"]
    try:
        names = sorted(table.commands_of(doc))
    except table.TableError as exc:
        return [f"{exc}; command names are not judged"]
    present = set(tracked)
    out = [f"{POLICY}: {m} admits nothing — {'it is not a judged path' if m in present else 'no such module'}; remove the entry"
           for m in sorted(allowed) if m not in present or not judged_path(m)]
    for rel in sorted(r for r in tracked if judged_path(r)):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            continue   # tracked and deleted in the work tree: the index is judged by the commit hook
        except (OSError, UnicodeDecodeError) as exc:
            out.append(f"{rel}: cannot be read as UTF-8 ({exc.__class__.__name__}); command names are not judged")
            continue
        out += literal_findings(rel, text, names, allowed)
        if rel in allowed and not sites(text, names, rel):
            out.append(f"{POLICY}: {rel} admits nothing — the module no longer names a command; remove the entry")
    return out


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="ADR-068 findings: the fabric table against commands, and hooks naming a command.")
    ap.add_argument("--root", default=table.ROOT)
    args = ap.parse_args(argv)
    try:
        doc = table.load(args.root)
    except table.TableError as exc:
        print(f"checks: {exc}", file=sys.stderr)
        return 2
    ls = subprocess.run(["git", "-C", args.root, "ls-files", "-z", "--", "*.py"], capture_output=True, timeout=60,
                        stdin=subprocess.DEVNULL, check=False)
    if ls.returncode != 0:
        print(f"checks: git ls-files failed in {args.root}", file=sys.stderr)
        return 2
    tracked = [p for p in os.fsdecode(ls.stdout).split("\0") if p]
    try:
        with open(os.path.join(args.root, POLICY), encoding="utf-8") as fh:
            policy_text: str | None = fh.read()
    except FileNotFoundError:
        policy_text = None
    except (OSError, UnicodeDecodeError) as exc:
        print(f"checks: {POLICY}: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    found = [f for f in table_findings(doc) if not f.startswith("note:")] + tree_findings(args.root, tracked, policy_text, doc)
    for line in found:
        print(line)
    return 1 if found else 0
