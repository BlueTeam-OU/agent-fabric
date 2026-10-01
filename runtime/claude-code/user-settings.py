#!/usr/bin/env python3
"""runtime/claude-code/user-settings.py — the fabric's keys in a login's
Claude Code user settings, written by bootstrap.sh on every account.

    user-settings.py <settings.json> [--dry-run]
    user-settings.py --help | -h

Any other argument that begins with "-" is refused (exit 2), never taken
for the path.

User scope reaches every session of the login whatever directory it is
launched from, so this is where a setting the fabric wants on every
agent goes. Every other key is kept as read. Prints one line in the
installer's shape (`+` written, `=` already current, `!` refused) and
exits 0; 1 when the file is unreadable, 2 on a usage error.

The keys, and why each is here:

`attribution` {commit "", pr "", sessionUrl false}. Claude Code builds
an attribution reminder from this key and injects it as a system
reminder on the first turn and again after every model switch, outside
any launch prompt — a `--system-prompt-file` does not remove it (read
back on 2.1.276, docs/live-checks/2026-09-18-attribution-reminder-off.md).
With no key set the reminder asks for a `Co-Authored-By:` trailer and a
"Generated with" footer, which policies/ban_generated_by_attribution.sh
refuses after the fact. An empty string hides each (the harness's own
schema: "Empty string hides attribution"), and with both hidden the
harness sends the opposite reminder — do not add attribution lines.
`sessionUrl` false drops the `Claude-Session:` trailer a web or Remote
Control session would add. The guard stays as the fence. The deprecated
`includeCoAuthoredBy` said the same thing; the key replaces it.

`env.DISABLE_AUTOUPDATER` "1": the fleet's Claude Code version is the one
runtime/claude-code/harness.json pins, moved by `fabric-ctl … upgrade
claude` and nothing else. `autoUpdates: false` in ~/.claude.json is NOT
that switch on a native install: the harness honours it only when
`autoUpdatesProtectedForNative` is not true (2.1.282, read from its
binary), and the coordinator's account, native and protected, installed
2.1.282 on its own on 2026-09-24. DISABLE_AUTOUPDATER is checked first,
unconditionally; it stops background updates only — `claude install <v>`,
which the upgrade uses, still works (DISABLE_UPDATES would stop that too).
Every other `env` key is kept as read.

`showThinkingSummaries` true and `verbose` true (the owner, 2026-09-20):
an agent's session is read by the person operating the fleet, not only
by the agent — the thinking summaries and the full tool output are what
lets a stalled or misdirected session be seen for what it is from its
terminal, rather than reconstructed afterwards from a transcript.

`tui` "default": the session draws in the terminal's normal screen, so
the terminal keeps its scrollback and its scrollbar works. Without the
key the harness uses its full-screen renderer on the alternate screen,
which leaves nothing to scroll back through: the coordinator's account,
set by hand with `/tui default`, scrolled; every other account did not.
The person operating the fleet reads a session's history in its
terminal, for the same reason as the two keys above.

`permissions.allow`: `Bash(<name> *)` for every command in
runtime/claude-code/commands.json — the fabric's own commands, which
bootstrap links into ~/.local/bin (the owner, 2026-09-26: no approval
for any fabric script or executable). A narrow rule, one command name
each — never one in its `not_allowed`, a wrapper that runs another
command — because in auto mode a narrow Bash rule is resolved before the
classifier while a broad one, or one naming Monitor, is set aside; a
Monitor follows the Bash rules. Every other rule the account allows,
denies or asks is kept as read, and an `ask` rule still wins.

`permissions.defaultMode` "auto" (the owner, 2026-09-26): every agent's
session starts in auto mode. Eight accounts provisioned by hand had no
mode and started in the default one, asking for what the classifier
would allow; the allow rules above assume auto.

`autoMode` (the owner, 2026-10-01): what the auto-mode classifier is told
about the fleet, from policies/auto-mode.json. A login's own wizard
(/auto-mode-setup) saw one project's transcripts and proposed a picture
true of that project alone — that project private, so confidential
material "is fine to push", on a login that also pushes to agent-fabric,
which is public. The classifier reads `autoMode` from user and managed settings
only, never a project's .claude/ (the harness's own docs), so user scope
is where the fleet's picture goes. `environment` is Claude Code's own
list (`claude auto-mode defaults`, from the pinned harness) with each
slot the policy names replaced: a "$defaults" plus the fleet's entries
would leave the built-in "Organization: None configured" beside the
fleet's own. When the defaults cannot be read, an existing `autoMode` is
kept as it is and the line says so. `allow`, `soft_deny` and `hard_deny`
are "$defaults" plus the policy's. `skillOverrides.auto-mode-setup`
"off": the wizard would write a login's own `autoMode` over the fleet's.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

# python3 -OO strips docstrings; the usage must survive it.
USAGE = (__doc__ or "user-settings.py <settings.json> [--dry-run]").strip()
ATTRIBUTION = {"commit": "", "pr": "", "sessionUrl": False}
TOP_LEVEL = {"showThinkingSummaries": True, "verbose": True, "tui": "default"}
ENV = {"DISABLE_AUTOUPDATER": "1"}
COMMANDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "commands.json")
SKILL_OVERRIDES = {"auto-mode-setup": "off"}
DEFAULTS_TIMEOUT_S = 60
SLOT = re.compile(r"^\*\*(.+?)\*\*:")


FABRIC_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The memory-write check (hooks/memory-write-check.py) at user scope, so
# it runs for every session of the account wherever it was started — a
# memory is the account's, not a project's — without asking each managed
# project to mirror a hook. Identified by its script name, so a moved
# checkout rewrites the path rather than adding a second entry.
MEMORY_CHECK = "memory-write-check.py"


def memory_check_hook() -> dict:
    return {"matcher": "Write|Edit", "hooks": [{
        "type": "command",
        "command": f'python3 "{os.path.join(FABRIC_ROOT, "runtime", "claude-code", "hooks", MEMORY_CHECK)}"',
        "timeout": 10}]}


def hooks_problem(hooks) -> str | None:
    """What makes an account's `hooks` value one this writer refuses, or
    None. One test for both callers: main() refuses on it before anything
    else, with_memory_check() raises on it, and the two cannot drift."""
    # A PostToolUse that is not a list is a mistake in the account's own
    # file: iterating it wrote its keys or characters back as entries.
    # Refused, the file left untouched, like an unreadable one.
    if isinstance(hooks, dict) and "PostToolUse" in hooks and not isinstance(hooks["PostToolUse"], list):
        return "hooks.PostToolUse is not a list"
    return None


def with_memory_check(hooks: dict) -> dict:
    """`hooks` with exactly one memory-check entry, the current one; every
    other entry kept as it was."""
    hooks = dict(hooks) if isinstance(hooks, dict) else {}
    problem = hooks_problem(hooks)
    if problem:
        raise Unreadable(problem)
    post = []
    for e in hooks.get("PostToolUse") or []:
        if not isinstance(e, dict) or not isinstance(e.get("hooks"), list):
            post.append(e)                  # not ours to judge: kept as it is
            continue
        # Only the check itself is taken out of an entry: a hook of the
        # account's own that shares the entry stays; an entry left with
        # nothing is dropped.
        kept = [h for h in e["hooks"] if not (isinstance(h, dict) and MEMORY_CHECK in str(h.get("command", "")))]
        if len(kept) == len(e["hooks"]):
            post.append(e)
        elif kept:
            post.append({**e, "hooks": kept})
    hooks["PostToolUse"] = post + [memory_check_hook()]
    return hooks


AUTO_MODE_POLICY = os.path.join(FABRIC_ROOT, "policies", "auto-mode.json")


def auto_mode_defaults() -> dict | None:
    """Claude Code's built-in auto-mode lists, from the harness on PATH, or
    None when it cannot say (no claude, a timeout, an answer that is not
    the expected object)."""
    claude = os.environ.get("AGENT_FABRIC_CLAUDE") or shutil.which("claude")
    if not claude:
        return None
    try:
        r = subprocess.run([claude, "auto-mode", "defaults"], capture_output=True, text=True,
                           timeout=DEFAULTS_TIMEOUT_S, stdin=subprocess.DEVNULL)
        doc = json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("environment"), list):
        return None
    return doc


def auto_mode() -> dict | None:
    """The fleet's `autoMode`, or None when Claude Code's defaults cannot be
    read: an environment composed without them would drop or contradict
    the built-in slots."""
    with open(AUTO_MODE_POLICY, encoding="utf-8") as fh:
        policy = json.load(fh)
    defaults = auto_mode_defaults()
    if defaults is None:
        return None
    ours = {slot: f"**{slot}**: {text}" for slot, text in policy.get("environment", {}).items()}
    environment, placed = [], set()
    for entry in defaults["environment"]:
        m = SLOT.match(entry) if isinstance(entry, str) else None
        slot = m.group(1) if m else None
        if slot in ours:
            environment.append(ours[slot])
            placed.add(slot)
        else:
            environment.append(entry)
    environment += [text for slot, text in ours.items() if slot not in placed]
    out = {"environment": environment}
    for key in ("allow", "soft_deny", "hard_deny"):
        if policy.get(key):
            out[key] = ["$defaults", *policy[key]]
    return out


def local_bin() -> str:
    return os.environ.get("AGENT_FABRIC_LOCAL_BIN") or os.path.join(os.path.expanduser("~"), ".local", "bin")


def rules() -> tuple[list[str], list[str]]:
    """(granted, withheld). A rule is granted only for a name whose
    ~/.local/bin entry IS the fabric's script: a foreign file bootstrap
    refused to replace would otherwise run under the fabric's approval
    (review of #42, 2026-09-26)."""
    with open(COMMANDS, encoding="utf-8") as fh:
        doc = json.load(fh)
    granted, withheld = [], []
    for name, rel in doc["commands"].items():
        if name in doc.get("not_allowed", {}):
            continue
        ours = os.path.realpath(os.path.join(local_bin(), name)) == os.path.realpath(os.path.join(FABRIC_ROOT, rel))
        (granted if ours else withheld).append(f"Bash({name} *)")
    return granted, withheld


def allow_rules() -> list[str]:
    return rules()[0]


class Unreadable(Exception):
    """The file exists and is not a JSON object: refused, never overwritten."""


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise Unreadable(f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise Unreadable(f"{path}: not a JSON object")
    return data


def save(path: str, data: dict) -> None:
    tmp = f"{path}.agent-fabric.tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def allowed(doc: dict) -> list:
    perms = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
    return perms.get("allow") if isinstance(perms.get("allow"), list) else []


def settled(doc: dict, auto: dict | None) -> bool:
    current = doc.get("attribution") if isinstance(doc.get("attribution"), dict) else {}
    overrides = doc.get("skillOverrides") if isinstance(doc.get("skillOverrides"), dict) else {}
    perms = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
    return (all(current.get(k) == v for k, v in ATTRIBUTION.items())
            and perms.get("defaultMode") == "auto"
            and all(r in allowed(doc) for r in allow_rules())
            and not any(r in allowed(doc) for r in rules()[1])
            and "includeCoAuthoredBy" not in doc
            and all(doc.get(k) == v for k, v in TOP_LEVEL.items())
            and doc.get("hooks") == with_memory_check(doc.get("hooks"))
            and isinstance(doc.get("env"), dict) and all(doc["env"].get(k) == v for k, v in ENV.items())
            and all(overrides.get(k) == v for k, v in SKILL_OVERRIDES.items())
            and (auto is None or doc.get("autoMode") == auto))


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(USAGE)
        return 0
    args = [a for a in argv if a != "--dry-run"]
    dry = "--dry-run" in argv
    # An unknown flag is refused, never taken for the path: `--help` once
    # wrote the fabric's keys to a file of that name in the caller's cwd.
    if len(args) != 1 or args[0].startswith("-"):
        refused = [a for a in args if a.startswith("-")]
        if refused:
            print(f"  !  {refused[0]}: not an option and not a path", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    path = args[0]
    try:
        doc = load(path)
    except Unreadable as exc:
        # One line in the installer's shape, so bootstrap can count the
        # account as NOT settled instead of reading an empty stdout as
        # "unchanged" — a traceback did exactly that.
        print(f"  !  {exc} — fabric user settings NOT written", file=sys.stderr)
        return 1
    # Checked here, once, before settled() and the dry run: a malformed
    # hooks value must refuse the same way whatever else is unsettled,
    # and a dry run must report what the real run would do.
    problem = hooks_problem(doc.get("hooks"))
    if problem:
        print(f"  !  {path}: {problem} — fabric user settings NOT written", file=sys.stderr)
        return 1
    auto = auto_mode()
    if auto is None:
        # The rest is still written; autoMode stays as it was, and says so.
        print(f"  !  {path}: Claude Code's auto-mode defaults could not be read (claude auto-mode defaults) — "
              "autoMode left as it is", file=sys.stderr)
    if settled(doc, auto):
        print(f"  =  {path} fabric user settings")
        return 0
    if dry:
        print(f"  +  {path} fabric user settings (would write)")
        return 0
    current = doc.get("attribution") if isinstance(doc.get("attribution"), dict) else {}
    doc["attribution"] = {**current, **ATTRIBUTION}
    doc.pop("includeCoAuthoredBy", None)
    doc.update(TOP_LEVEL)
    env = doc.get("env") if isinstance(doc.get("env"), dict) else {}
    doc["env"] = {**env, **ENV}
    perms = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
    granted, withheld = rules()
    perms["allow"] = [r for r in allowed(doc) if r not in withheld] + [r for r in granted if r not in allowed(doc)]
    perms["defaultMode"] = "auto"
    doc["permissions"] = perms
    doc["hooks"] = with_memory_check(doc.get("hooks"))
    overrides = doc.get("skillOverrides") if isinstance(doc.get("skillOverrides"), dict) else {}
    doc["skillOverrides"] = {**overrides, **SKILL_OVERRIDES}
    if auto is not None:
        doc["autoMode"] = auto
    save(path, doc)
    print(f"  +  {path} fabric user settings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
