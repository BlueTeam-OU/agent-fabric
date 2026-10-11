"""tools/fabric/launcher/settings.py — the settings scopes, and the model pins no committed scope may carry.
A part of tools/fabric/launch.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
from fabric_launcher.base import die, say
from fabric_launcher.currency import toplevel


# A settings-scope pin outranks the profile's exports (ori composes the
# child env as settings-env-first for the four alias keys; Claude Code
# merges every scope's env block into the process, local > project >
# user), so the launcher refuses rather than race — in EVERY scope. The
# predicate: env.ANTHROPIC_* (not only _DEFAULT_ — ANTHROPIC_MODEL is a
# pin too), env.CLAUDE_CODE_SUBAGENT_MODEL, modelOverrides. NOT a top-
# level `model`: that is the session default, which the explicit
# `--model <session>` this launcher passes outranks. An unreadable file
# is not evidence of pins. $PWD's .claude/ is scanned as well when the
# launch directory is not the toplevel, and the managed-policy file
# (root-owned; outranks every other scope) — a missing file is skipped.
def settings_scopes(home: str, cwd: str) -> list[str]:
    # Derived from the launch directory ONLY — never inherited. The scopes this
    # fence inspects must be the scopes the child loads, and the child starts
    # in $PWD: an inherited REPO_ROOT pointing at another clone let the fence
    # pass on that clone's clean .claude/ while exec'ing in this one, pinned
    # (a review finding on a managed project's PR #679, judged CONFIRMED).
    repo_root = toplevel(cwd) or cwd
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "")
    return ["/etc/claude-code/managed-settings.json",
            f"{home}/.claude/settings.json", f"{home}/.claude/settings.local.json",
            f"{config_dir}/settings.json" if config_dir else "",
            f"{repo_root}/.claude/settings.json", f"{repo_root}/.claude/settings.local.json",
            f"{cwd}/.claude/settings.json", f"{cwd}/.claude/settings.local.json"]


def settings_pins(path: str) -> list[str] | None:
    """The pins a settings file carries; None for a file that is JSON but
    not an object (the bash crashed there and the launch went on)."""
    try:
        # utf-8-sig: a byte-order mark must not make a pinning file read as pin-free.
        with open(path, encoding="utf-8-sig") as fh:
            d = json.load(fh) or {}
    except Exception:
        return []
    return pins_of(d)


def pins_of(d: object) -> list[str] | None:
    if not isinstance(d, dict):
        return None
    bad = []
    env = d.get("env") or {}
    if isinstance(env, dict):
        # env.CLAUDE_CODE_EFFORT_LEVEL is merged into the CHILD by the harness,
        # so a settings scope carrying it walks straight past the process-env
        # refusal below — the scan and that refusal have to name the same
        # variables or neither is a fence (review of 2026-09-23, F1).
        bad += sorted("env." + k for k in env
                      if k.startswith("ANTHROPIC_")
                      or k in ("CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE",
                               "CLAUDE_CODE_EFFORT_LEVEL"))
    if "modelOverrides" in d:
        bad.append("modelOverrides")
    # Only `maxEffortLevel` here, and NOT effortLevel/modelSettings, which the
    # committed-scope guard still refuses. Two reasons, both measured:
    #   - precedence. `--effort` (turnEffort) is resolved BEFORE the configured
    #     level that effortLevel and modelSettings feed, so the launcher's own
    #     flag already outranks them. maxEffortLevel is different in kind: it
    #     is a CAP, and the LOWEST value across all scopes wins, so nothing the
    #     launcher passes can raise it back.
    #   - the harness writes modelSettings itself. `/effort` persists
    #     `modelSettings.<model>.effortLevel` into ~/.claude/settings.json
    #     ("saved as your default for new sessions"), so refusing it here would
    #     stop a launch on every account that has ever used the command — found
    #     when this fence refused its own author's account.
    # A COMMITTED scope is different: nothing should pin anything there and no
    # harness writes to it, so all four stay refused in
    # policies/check_repo_settings_carry_no_model_pins.sh.
    bad += [k for k in ("maxEffortLevel",) if k in d]
    return bad


def refuse_pins(scopes: list[str], local_override: str) -> None:
    for f in scopes:
        if not f or not os.path.isfile(f):
            continue
        pins = settings_pins(f)
        if pins is None:
            say(f"launch: {f} is not a JSON object; not read for model pins.")
        elif pins:
            die(f"{f} carries model pins ({' '.join(pins)}), which would silently outrank the profile. "
                f"Remove them; per-agent tiers go through {local_override}.")
    if os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL"):
        die("CLAUDE_CODE_SUBAGENT_MODEL is set in the environment; it overrides every subagent's model "
            "regardless of the review gate. Unset it.")
    if os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE"):
        die("CLAUDE_CODE_SUBAGENT_MODEL_FORCE is set; it discards every dispatch's own model. Unset it.")
    # Same bug class as the two above, for the other routed dimension. Read
    # out of 2.1.280: this variable outranks --effort, /effort AND an agent
    # file's effort:, and process environment reaches every subagent — so one
    # value here flattens every per-class level the fabric writes. `unset` and
    # `auto` are not neutral: both mean "ignore the configured level and use
    # the model's own default", which defeats the routing just as thoroughly
    # (docs/live-checks/2026-09-23-effort-registry.md).
    # Presence, not emptiness: an EXPORTED-but-empty value is still set, and
    # the harness reads the variable rather than testing it for emptiness.
    # "For any value" has to include the empty one (review of 2026-09-23).
    if "CLAUDE_CODE_EFFORT_LEVEL" in os.environ:
        die(f"CLAUDE_CODE_EFFORT_LEVEL is set to '{os.environ['CLAUDE_CODE_EFFORT_LEVEL']}'; it outranks every "
            "per-class effort the fabric writes, in every subagent. Unset it (routing/effort.json is where a "
            "level is decided).")


def cli_settings_values(args: list[str]) -> list[str]:
    """The values of every `--settings X` / `--settings=X`, wherever they stand: a
    bare `--` can be an option's value (`-n -- --settings ...`), and claude goes on
    parsing options after it, so stopping there was a bypass. A prompt that merely
    contains the word is refused too, the safe side."""
    out: list[str] = []
    for i, a in enumerate(args):
        if a == "--settings" and i + 1 < len(args):
            out.append(args[i + 1])
        elif a.startswith("--settings="):
            out.append(a.split("=", 1)[1])
    return out


# What claude trims off a --settings value before it decides JSON from path (its JS
# trim, plus a byte-order mark the launcher would otherwise take for a path character).
JS_BLANKS = " \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a" \
            "\u2028\u2029\u202f\u205f\u3000\ufeff"


def refuse_cli_settings(args: list[str], cwd: str, local_override: str) -> None:
    """A `--settings` the caller passes is one more settings scope, and the
    harness loads it above the files fenced by refuse_pins: it gets the same
    pin test. Only for the providers that have no ori fence of their own to
    override (see argv.refuse_passthrough).

    The launcher cannot be sure how claude will classify a value, so it tests
    BOTH readings: the text as inline JSON, and the value as a file relative to the
    launch directory. A reading that does not exist is skipped; a value neither
    reading can read is the harness's refusal (it says so), not evidence of pins."""
    for value in cli_settings_values(args):
        text = value.strip(JS_BLANKS)
        found: list[tuple[str, list[str] | None]] = []
        if text.startswith("{"):
            try:
                found.append(("the --settings value", pins_of(json.loads(text) or {})))
            except ValueError:
                pass
        for candidate in (value, text):
            where = candidate if os.path.isabs(candidate) else os.path.join(cwd, candidate)
            if candidate and os.path.isfile(where):
                found.append((where, settings_pins(where)))
        for where, pins in found:
            if pins is None:
                say(f"launch: {where} is not a JSON object; not read for model pins.")
            elif pins:
                die(f"{where} carries model pins ({' '.join(pins)}), which would silently outrank the profile. "
                    f"Remove them; per-agent tiers go through {local_override}.")
