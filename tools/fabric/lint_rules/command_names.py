"""tools/fabric/lint_rules/command_names.py — a fabric command has one reading (agent-fabric ADR-068 rules 3 and 7, ADR-067
command-recognition): the `fabric` table of runtime/claude-code/commands.json reaches every command in `commands` by one form,
and a hook or guard recognises a command only through tools/fabric/cli canonical(), unless policies/command-names.json admits
the module with why it cannot. tools/fabric/cli/checks.py is the definition; the pre-commit hook asks it about the staged
modules. A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import ast
import importlib.util
import os
import sys

from .base import _tracked

_FABRIC = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def _load_cli() -> None:
    # The package by path, as tools/fabric/cli/fabric.py loads itself: nothing on sys.path answers for its relative imports,
    # and a fixture fabric's own tools/fabric/cli must not stand in for the one lint ships with.
    cli = os.path.join(_FABRIC, "cli")
    spec = importlib.util.spec_from_file_location("fabric_cli", os.path.join(cli, "__init__.py"), submodule_search_locations=[cli])
    sys.modules["fabric_cli"] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sys.modules["fabric_cli"])


_load_cli()
from fabric_cli import checks, table  # noqa: E402

# Where a noun's own command keeps its verbs, for rule 3's clause "no listed verb the noun's own command takes": the
# verbs live in each module, not in a table (checks.py), so lint reads them there, statically, and judges the clause
# instead of dropping its `note:`. ("dict", NAME): the keys of a module-level NAME = {...}; ("choices", ARG): the choices
# of add_argument(ARG, ...). A noun with both a command and verbs whose command is not here is a finding, so the next one
# cannot pass unjudged.
OWN_VERB_SOURCES: dict[str, tuple[str, str, str]] = {
    "fabric-review": ("tools/fabric/review_cli.py", "dict", "ROUTES"),
    "fabric-reflect": ("tools/fabric/reflect.py", "choices", "action"),
}


def _read_verbs(path: str, shape: str, name: str) -> set[str] | None:
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    for node in ast.walk(tree):
        if (shape == "dict" and isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Dict)
                and any(isinstance(t, ast.Name) and t.id == name for t in (node.targets if isinstance(node, ast.Assign) else [node.target]))):
            keys = node.value.keys
        elif (shape == "choices" and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument" and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == name):
            keys = next((k.value.elts for k in node.keywords if k.arg == "choices" and isinstance(k.value, (ast.Tuple, ast.List, ast.Set))), None)
            if keys is None:
                return None
        else:
            continue
        if not all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in keys):
            return None
        return {k.value for k in keys if not k.value.startswith("-")}   # an option (`--engine`) is not a verb a noun can list
    return None


def _own_verbs(root: str, doc: object) -> tuple[dict[str, set[str]], list[str]]:
    try:
        nouns = table.nouns_of(doc)
    except table.TableError:
        return {}, []   # table_findings says the table is malformed
    own: dict[str, set[str]] = {}
    out: list[str] = []
    for noun, entry in sorted(nouns.items()):
        cmd = entry.get("command")
        if cmd is None or not entry.get("verbs") or cmd in own:
            continue
        if cmd not in OWN_VERB_SOURCES:
            out.append(f"fabric.nouns.{noun}: {cmd} takes its own verbs and lists more, and lint does not know where its verbs "
                       f"are (OWN_VERB_SOURCES in tools/fabric/lint_rules/command_names.py); rule 3's own-verb clause is not judged")
            continue
        rel, shape, name = OWN_VERB_SOURCES[cmd]
        try:
            verbs = _read_verbs(os.path.join(root, rel), shape, name)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            verbs, why = None, exc.__class__.__name__
        else:
            why = f"no {shape} {name} of string verbs"
        if verbs is None:
            out.append(f"{rel}: {cmd}'s own verbs cannot be read ({why}); rule 3's own-verb clause is not judged for it")
            continue
        own[cmd] = verbs
    return own, out


def command_name_findings(root: str) -> list[str]:
    if not os.path.exists(os.path.join(root, table.COMMANDS_FILE)):
        return []   # a fixture or stripped copy with no command table has no commands to recognise; bootstrap refuses a real one
    try:
        doc = table.load(root)
    except table.TableError as exc:
        return [f"{exc}; command names are not judged"]
    try:
        with open(os.path.join(root, checks.POLICY), encoding="utf-8") as fh:
            policy_text: str | None = fh.read()
    except FileNotFoundError:
        policy_text = None   # instance data (ADR-045 rule 2): a stripped engine copy admits nothing and judges all
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{checks.POLICY}: cannot be read ({exc.__class__.__name__}); command names are not judged"]
    # Not narrowed by ruff's exclude (base._not_ours): the pre-commit hook judges every path judged_path names, and the two
    # must judge one set (#516 F1). own_verbs is always supplied, so table_findings adds no `note:` line.
    own, unread = _own_verbs(root, doc)
    return checks.table_findings(doc, own) + unread + checks.tree_findings(root, _tracked(root), policy_text, doc)
