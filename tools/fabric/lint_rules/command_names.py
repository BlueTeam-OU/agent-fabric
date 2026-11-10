"""tools/fabric/lint_rules/command_names.py — a fabric command has one reading (agent-fabric ADR-068 rules 3 and 7, ADR-067
command-recognition): the `fabric` table of runtime/claude-code/commands.json reaches every command in `commands` by one form,
and a hook or guard recognises a command only through tools/fabric/cli canonical(), unless policies/command-names.json admits
the module with why it cannot. tools/fabric/cli/checks.py is the definition; the pre-commit hook asks it about the staged
modules. A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

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
    # must judge one set (#516 F1). The `note:` line says the own-verbs clause was not judged; lint has no verbs to give it.
    table_found = [f for f in checks.table_findings(doc) if not f.startswith("note:")]
    return table_found + checks.tree_findings(root, _tracked(root), policy_text, doc)
