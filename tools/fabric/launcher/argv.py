"""tools/fabric/launcher/argv.py — the command line: what the harness is passed, refused, asked for, resumed.
A part of tools/fabric/launch.py, whose docstring is the contract."""
from __future__ import annotations

import os
from fabric_launcher.base import PROMPT_FLAGS, VALUE_OPTIONS, PATH_OPTIONS, die


# ── argv ────────────────────────────────────────────────────────────────
# --print may sit anywhere in the arguments; as $1 only, `launch --verbose
# --print` passed it through to claude and exec'd a real session.
# --provider openrouter (default) | anthropic: the same resolution and the
# same refusals, then `ori claude` with every class exported as a
# composite, or plain `claude` with only the tier aliases the profile
# binds exported — an alias nothing binds is left to the harness, and the
# review pin goes through the agent file. Either way the session is the
# fabric's: bound role, gated review model, no pin outside the profile.
def parse_argv(argv: list[str]) -> tuple[bool, str, list[str]]:
    print_only, provider, args, prev = False, "openrouter", [], ""
    for arg in argv:
        if arg == "--print":
            print_only = True
        elif prev == "--provider":
            provider = arg
        elif arg.startswith("--provider="):
            provider = arg[len("--provider="):]
        elif arg == "--provider":
            pass
        else:
            args.append(arg)
        prev = arg
    return print_only, provider, args


def refuse_passthrough(args: list[str], provider: str = "openrouter") -> None:
    """Pass-through args must not be able to fence ori out of OpenRouter. The
    --settings refusal is ori's: on anthropic and gateway there is no
    fence of the launcher's to override, so a caller's --settings (a live check's
    hook) is let through here and tested for model pins by
    settings.refuse_cli_settings instead."""
    for arg in args:
        if (arg == "--settings" or arg.startswith("--settings=")) and provider == "openrouter":
            die("passing --settings would disable ori's provider fence (its own\n"
                "  --settings carries apiKeyHelper and blanks every other provider\n"
                "  variable). Launch without it; per-session settings go through the\n"
                "  profile layers, not the CLI.")
        if arg == "--setting-sources" or arg.startswith("--setting-sources="):
            die("passing --setting-sources would disable ori's provider fence.")
        # The role reaches the session through the launcher's own
        # --append-system-prompt-file; a caller's --system-prompt* would replace
        # or shadow it (and claude itself refuses --append-system-prompt beside
        # the -file form). Nothing a session needs is passed this way.
        name = arg.split("=", 1)[0]
        if name in PROMPT_FLAGS:
            die(f"passing {name} is refused: the role's system prompt is the\n"
                "  launcher's (tools/fabric/launch_prompt.py -> --append-system-prompt-file,\n"
                "  or --system-prompt-file for a locale that carries the harness text);\n"
                "  a second one would replace or shadow it.")


def asks_help(args: list[str]) -> bool:
    """claude's own help, asked before any `--`: no session will dispatch,
    so nothing of the account's is rewritten for it."""
    for a in args:
        if a == "--":
            return False
        if a in ("-h", "--help"):
            return True
    return False


def wants_opening(args: list[str]) -> bool:
    opening, expect_value = True, False
    for a in args:
        if expect_value:
            expect_value = False
            if not a.startswith("-"):
                continue
        if a in ("-p", "-v", "--version", "-h", "--help", "--"):
            opening = False
        elif a in VALUE_OPTIONS:
            expect_value = True
        elif a.startswith("-"):
            pass
        else:
            opening = False   # a positional word: the caller's own prompt
    if os.environ.get("AGENT_FABRIC_NO_OPENING"):
        opening = False
    return opening


def resumes(args: list[str]) -> bool:
    """Whether a launch resumes a session, by any spelling claude takes."""
    from fabric_launcher.base import RESUME_FLAGS
    return any(a in RESUME_FLAGS or any(a.startswith(f + "=") for f in RESUME_FLAGS if f.startswith("--"))
               for a in args)


def without_resume(orig_args: list[str]) -> list[str]:
    """The caller's own resume flags are replaced by the one that names the
    session just stopped; everything else is passed on as given."""
    from fabric_launcher.base import RESUME_BARE, RESUME_VALUED
    nxt, skip = [], False
    for a in orig_args:
        if skip:
            skip = False
            if not a.startswith("-"):
                continue
        if a in RESUME_BARE or a.startswith(tuple(f + "=" for f in RESUME_VALUED if f.startswith("--"))):
            continue
        if a in RESUME_VALUED:
            skip = True
            continue
        nxt.append(a)
    return nxt


def absolute_path_options(args: list[str], cwd: str) -> list[str]:
    """A path relative to here would name nothing there: the values of the
    options that take paths are made absolute first, spaced or `=`, existing
    or not — and nothing else, since a model or provider name can match a
    file here too. One value each, as the opening scan reads them: a second
    word is the caller's prompt, and such a launch is never relaunched
    fresh. A --settings value that is JSON is not a path."""
    out, takes = list(args), False
    for i, a in enumerate(out):
        if a in PATH_OPTIONS:
            takes = True
            continue
        name, eq, v = a.partition("=")
        if eq and name in PATH_OPTIONS:
            if v and not v.startswith(("/", "{")):
                out[i] = f"{name}={cwd}/{v}"
            takes = False
            continue
        if a.startswith("-"):
            takes = False
            continue
        if not takes:
            continue
        if not a.startswith(("/", "{")):
            out[i] = f"{cwd}/{a}"
        takes = False
    return out
