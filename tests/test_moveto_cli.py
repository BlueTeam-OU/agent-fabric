#!/usr/bin/env python3
"""moveto's target resolution — the half testable without spawning an
interactive shell: `--print` runs the whole resolution path and stops
before the exec — its completion, and the entering shell's fabric pull.
Ported from runtime/provisioning/moveto/test_moveto.sh (ADR-040 Wave 6),
case for case.

WHAT THE MOCKS DO AND DO NOT PROVE. `getent` and `sudo` are replaced on
PATH, because the fixture accounts do not exist and the suite must not
need root. The sudo mock RECORDS the argv it was handed and then runs the
command as the caller — so an assertion can check WHICH ACCOUNT was asked
for, which is the tool's only privilege boundary, but nothing here proves
the kernel honoured it. An earlier version of this mock silently
discarded `-u`, and deleting both sudo gates from the tool left the suite
green. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "runtime", "provisioning", "moveto")
UNDER_TEST = os.path.join(SRC, "moveto")
ACCOUNTS = ("solo", "odd", "many", "empty", "nodir", "spaced", "esc", "onlyfab")
ESC_CLONE = "good\x1b]0;INJECTED\x07tail"


def main() -> int:
    fails = 0

    def check(label: str, want: str, got: str) -> None:
        nonlocal fails
        good = want in got
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good:
            print(f"      want substring: {want!r}\n      got: {got!r}")
        fails += not good

    def check_absent(label: str, forbidden: str, got: str) -> None:
        nonlocal fails
        good = forbidden not in got
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good:
            print(f"      must NOT contain: {forbidden!r}\n      got: {got!r}")
        fails += not good

    def check_status(label: str, want: int, got: int) -> None:
        nonlocal fails
        good = want == got
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": expected exit {want}, got {got}"))
        fails += not good

    host = subprocess.run(["hostname", "-s"], stdout=subprocess.PIPE, text=True, check=True, timeout=10).stdout.strip()

    with tempfile.TemporaryDirectory() as sandbox:
        bin_, sudo_log, home = f"{sandbox}/bin", f"{sandbox}/sudo.log", f"{sandbox}/home"
        os.makedirs(bin_)

        def put(path: str, text: str, mode: int = 0o644) -> None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(path, mode)

        # Fixtures, each earning its place:
        #   solo    the template layout, clone named after the account
        #   odd     ONE clone named differently — the only fixture that can
        #           tell "title = account" from "title = clone basename"
        #   many    several clones: must refuse to guess
        #   empty   projects/ exists but holds nothing
        #   nodir   no projects/ at all — a different state, a different answer
        #   spaced  one clone whose name contains a space
        #   esc     one clone whose name contains ESC and BEL
        os.makedirs(f"{home}/solo/projects/solo")
        # Beside the clone: the workspace CLAUDE.md and the control-plane
        # checkout bootstrap.sh puts in every ~/projects. Neither is a clone.
        put(f"{home}/solo/projects/CLAUDE.md", "workspace\n")
        os.makedirs(f"{home}/solo/projects/agent-fabric")
        os.makedirs(f"{home}/odd/projects/weird-name")
        for c in ("alpha", "beta", "gamma"):
            os.makedirs(f"{home}/many/projects/{c}")
        # An account like python-dev-01: ~/projects holds the workspace CLAUDE.md and the control-plane checkout, nothing else.
        put(f"{home}/onlyfab/projects/CLAUDE.md", "workspace\n")
        os.makedirs(f"{home}/onlyfab/projects/agent-fabric")
        os.makedirs(f"{home}/onlyfab/projects/.claude")        # the workspace settings directory bootstrap writes: not a clone
        os.makedirs(f"{home}/empty/projects")
        os.makedirs(f"{home}/nodir")
        os.makedirs(f"{home}/spaced/projects/spaced backup")
        os.makedirs(f"{home}/esc/projects/{ESC_CLONE}")
        # A bound role for two of them: --list prints it beside the account.
        put(f"{home}/solo/.local/state/agent-fabric/agents/solo/binding.json",
            '{"agent": "solo", "role": "web-dev", "updated_at": "x"}\n')
        put(f"{home}/esc/.local/state/agent-fabric/agents/esc/binding.json",
            '{"agent": "esc", "role": "evil\x1b]0;X\x07role"}\n')

        put(f"{bin_}/getent", "#!/usr/bin/env bash\n"
            'if [[ "$1" == "passwd" && $# -eq 2 ]]; then\n'
            f'    for u in {" ".join(ACCOUNTS)}; do\n'
            f'        [[ "$2" == "$u" ]] && {{ echo "$u:x:2000:2000::{home}/$u:/bin/bash"; exit 0; }}\n'
            "    done\n    exit 2\nfi\n"
            'if [[ "$1" == "passwd" && $# -eq 1 ]]; then\n'
            f'    for u in {" ".join(ACCOUNTS)}; do echo "$u:x:2000:2000::{home}/$u:/bin/bash"; done\n'
            "    exit 0\nfi\nexit 2\n", 0o755)
        # Records the requested account, then runs the command as the caller.
        # SUDO_DENY makes it refuse: the only way to the "cannot become" branch.
        put(f"{bin_}/sudo", "#!/usr/bin/env bash\n"
            'want=""\n'
            'while [[ $# -gt 0 ]]; do\n'
            '    case "$1" in\n        -n|-H) shift ;;\n        -u) want="$2"; shift 2 ;;\n        *) break ;;\n    esac\ndone\n'
            f'echo "as=$want argv=$*" >> "{sudo_log}"\n'
            '[[ -n "${SUDO_DENY:-}" ]] && exit 1\n'
            'exec "$@"\n', 0o755)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        env["PATH"] = f"{bin_}:{env.get('PATH', '')}"

        def mv(*args: str, **extra: str) -> tuple[int, str]:
            r = subprocess.run([UNDER_TEST, *args], env={**env, **extra}, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=60)
            return r.returncode, r.stdout.decode("utf-8", "surrogateescape")

        print("1. the destination is the workspace, titled by the role instance")
        st, out = mv("solo", "--print")
        check_status("exits 0", 0, st)
        check("resolves ~/projects — the place a session launches from", "/home/solo/projects\n", out)
        check_absent("not the clone", "/home/solo/projects/solo", out)
        check("title is the account", "title: solo", out)
        st, out = mv("solo", "--resume", "--print")
        check_status("--resume --print exits 0", 0, st)
        check("--resume --print says the resume follows", "then: fabric-resume", out)
        st, out = mv("solo", "--wait", "--print")
        check("--wait --print says the Enter and the resume follow", "then: Enter to activate, then fabric-resume", out)
        st, out = mv("solo", "--print", "--watch")
        check("--watch --print says the watch follows", "then: fabric-watch", out)
        st, out = mv("solo", "--wait", "--watch", "--print")
        check_status("two modes together: exit 1", 1, st)
        check("…said", "moveto: one of --wait, --resume, --watch at a time", out)
        listed = mv("solo", "--list")[1]
        check_absent("the workspace CLAUDE.md is not a clone", "CLAUDE.md", listed)
        check_absent("the agent-fabric checkout is not a clone", "agent-fabric", listed)

        print("1b. a clone named differently changes nothing: still the workspace")
        st, out = mv("odd", "--print")
        check_status("exits 0", 0, st)
        check("resolves the workspace", "/home/odd/projects\n", out)
        check("title is the account", "title: odd", out)

        print("2. several clones: the workspace, no guessing needed")
        st, out = mv("many", "--print")
        check_status("exits 0", 0, st)
        check("resolves the workspace", "/home/many/projects\n", out)
        check("title is the account", "title: many", out)

        print("3. several clones, one named: enters it and titles by clone")
        st, out = mv("many", "beta", "--print")
        check_status("exits 0", 0, st)
        check("resolves the named clone", "/home/many/projects/beta", out)
        check("title is the clone", "title: beta", out)
        st, out = mv("solo", "solo", "--print")
        check("a single clone named explicitly is entered", "/home/solo/projects/solo", out)
        check("…titled by the account", "title: solo", out)

        print("4. empty projects/ is enterable; missing projects/ is not provisioned")
        st, out = mv("empty", "--print")
        check_status("empty exits 0", 0, st)
        check("empty resolves the workspace (bootstrap may still run there)", "/home/empty/projects\n", out)
        st, out = mv("nodir", "--print")
        check_status("missing exits 1", 1, st)
        check("missing says not provisioned", "not provisioned yet", out)

        print("5. unknown account and unknown clone fail loudly")
        st, out = mv("nosuchuser", "--print")
        check_status("unknown account exits 1", 1, st)
        check("names the account", "no such account: nosuchuser", out)
        st, out = mv("solo", "nosuchclone", "--print")
        check_status("unknown clone exits 1", 1, st)
        check("names the path", "no such directory", out)

        print("6. --list shows accounts WITH clones and omits those without")
        st, out = mv("--list")
        check_status("exits 0", 0, st)
        check("lists the template account", "solo", out)
        check("lists a multi-clone account's clones", "gamma", out)
        check_absent("omits an account whose projects/ is empty", "empty", out)
        check_absent("omits an account with no projects/ at all", "nodir", out)
        # `moveto --list` names the control-plane checkout among an account's clones (Fleet Deck makes a tab of every
        # account it lists); `moveto <account> --list` and entering still treat it as no clone to name.
        check("the role sits between the account and its clones", f"{'solo':<24} {'web-dev':<20} agent-fabric solo", out)
        check("an account holding only the control-plane checkout is listed, naming it", f"{'onlyfab':<24} {'-':<20} agent-fabric\n", out)
        check_absent("its own clone listing still names no clone to enter", "agent-fabric", mv("onlyfab", "--list")[1])
        st, out_ = mv("onlyfab", "--print")
        check("entering it is still the workspace", "/home/onlyfab/projects\n", out_)
        check("an account with no binding shows -", f"{'many':<24} {'-':<20}", out)
        check("a role's control characters are stripped", "evil]0;Xrole", out)

        print("7. a clone name containing a space is usable, not a wrong path")
        st, out = mv("spaced", "spaced backup", "--print")
        check_status("exits 0", 0, st)
        check("resolves the spaced clone", "/home/spaced/projects/spaced backup", out)

        print("8. control characters in a clone name never reach the terminal")
        out = mv("--list")[1]
        check("the printable part still shows", "good", out)
        check_absent("no ESC", "\x1b", out)
        check_absent("no BEL", "\x07", out)
        out = mv("esc", ESC_CLONE, "--print")[1]
        check_absent("title carries no ESC either", "\x1b", out)

        print("9. the named clone must be a single segment")
        st, out = mv("solo", "../../etc", "--print")
        check_status("traversal exits 1", 1, st)
        check("says why", "single name under", out)
        check_absent("no path was resolved", "title:", out)

        print("10. the target account is what sudo is asked for")
        put(sudo_log, "")
        mv("solo", "--print")
        with open(sudo_log, encoding="utf-8") as fh:
            log = fh.read()
        # Naming the COMMANDS matters: "as=solo" somewhere is satisfied by the
        # can-I-become gate alone, so dropping -u from the enumeration and the
        # existence check would go unnoticed.
        check("the clone listing ran as the target", "as=solo argv=find", log)
        check("the directory check ran as the target", "as=solo argv=test -d", log)
        check_absent("never a bare sudo with no -u", "as= ", log)

        print("11. an account we cannot become is refused, not guessed at")
        st, out = mv("solo", "--print", SUDO_DENY="1")
        check_status("exits 1", 1, st)
        check("says it cannot become the account", "cannot become 'solo'", out)

        print("12. tab completion: accounts from the host registry, clones from the tool")
        # A fabric checkout whose registry places two accounts on this host
        # and one elsewhere; the completion reads it with no sudo and
        # proposes only ours. It calls `moveto` by name for clones: the tool
        # under test, through the same mocked getent and sudo.
        comp_root = f"{sandbox}/comp-root"
        put(f"{comp_root}/runtime/hosts/registry.json",
            f'{{"placement":{{"alpha-01":"{host}","beta-01":"{host}","gamma-01":"elsewhere"}}}}\n')
        os.symlink(UNDER_TEST, f"{bin_}/moveto")

        def complete(*words: str) -> str:
            """COMPREPLY, one per line; the cursor is on the last word."""
            script = ('source "$1"; shift; COMP_WORDS=("$@"); COMP_CWORD=$(( $# - 1 )); _moveto; '
                      'printf "%s\\n" "${COMPREPLY[@]}"')
            r = subprocess.run(["bash", "-c", script, "_", os.path.join(SRC, "completion.bash"), *words],
                               env={**env, "AGENT_FABRIC_ROOT": comp_root}, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=60)
            return r.stdout
        out = complete("moveto", "")
        check("proposes the accounts placed on this host", "alpha-01", out)
        check("and the other one", "beta-01", out)
        check_absent("not an account placed elsewhere", "gamma-01", out)
        out = complete("moveto", "be")
        check("narrows on the prefix", "beta-01", out)
        check_absent("and drops the rest", "alpha-01", out)
        out = complete("moveto", "--")
        check("a dash completes the flag", "--list", out)
        out = complete("moveto", "alpha-01", "--")
        check("second-word flags", "--print", out)
        # `moveto <account> --list` runs the tool: "many" has three clones.
        out = complete("moveto", "many", "")
        check("clones come from moveto <account> --list", "beta", out)
        out = complete("moveto", "many", "ga")
        check("and narrow on the prefix", "gamma", out)
        check_absent("dropping the rest", "alpha", out)

        print("enter: a fabric that cannot be fast-forwarded is said with git's own reason")
        eh = f"{sandbox}/enterhome"
        os.makedirs(f"{eh}/projects")
        subprocess.run(["git", "init", "-q", f"{eh}/projects/agent-fabric"], env=env, check=True, timeout=30)
        subprocess.run(["git", "-C", f"{eh}/projects/agent-fabric", "remote", "add", "origin",
                        f"{sandbox}/no-such-origin.git"], env=env, check=True, timeout=30)

        def enter(**extra: str) -> str:
            r = subprocess.run(["bash", os.path.join(SRC, "enter"), f"{eh}/projects", "t"],
                               env={**env, "HOME": eh, "XDG_CONFIG_HOME": f"{eh}/.config", **extra},
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                               timeout=120)
            return r.stderr
        err = enter()
        check("the reason is git's first error line", "does not appear to be a git repository", err)
        check_absent("…never the old guess", "offline, or the clone is not on main", err)
        # A hung network: git is killed by the timeout before it writes a word.
        put(f"{sandbox}/hungbin/git", '#!/bin/sh\ncase " $* " in *" pull "*) exit 124 ;; esac\n'
            f'exec {shutil.which("git")} "$@"\n', 0o755)
        err = enter(PATH=f"{sandbox}/hungbin:{env['PATH']}")
        check("a silent timeout is said as one", "not fast-forwarded (git pull timed out after 30 s)", err)

        print("enter: a clone ahead of origin/main is said, with its count")
        origin = f"{sandbox}/origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], env=env, check=True, timeout=30)
        fab = f"{eh}/projects/agent-fabric"
        g = ["git", "-C", fab, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "-C", fab, "remote", "set-url", "origin", origin], env=env, check=True, timeout=30)
        subprocess.run([*g, "checkout", "-q", "-b", "main"], env=env, check=True, timeout=30)
        subprocess.run([*g, "commit", "-q", "--allow-empty", "--no-verify", "-m", "base"], env=env, check=True,
                       timeout=30)
        subprocess.run([*g, "push", "-q", "origin", "main"], env=env, check=True, timeout=30)
        err = enter()
        check_absent("level with origin: nothing said", "ahead of origin/main", err)
        for n in ("one", "two"):
            subprocess.run([*g, "commit", "-q", "--allow-empty", "--no-verify", "-m", n], env=env, check=True,
                           timeout=30)
        err = enter()
        check("two local commits: said, with the count", "agent-fabric is 2 commit(s) ahead of origin/main", err)
        put(f"{sandbox}/norevbin/git", '#!/bin/sh\ncase " $* " in *" rev-list "*) exit 128 ;; esac\n'
            f'exec {shutil.which("git")} "$@"\n', 0o755)
        err = enter(PATH=f"{sandbox}/norevbin:{env['PATH']}")
        check("a count git cannot give is said as unknown, never as level",
              "commits beyond origin/main are unknown", err)

        print("enter's modes: --wait waits for one Enter before anything runs; --watch runs fabric-watch")
        log = f"{sandbox}/enter.log"
        put(f"{sandbox}/logbin/git", f'#!/bin/sh\ncase " $* " in *" pull "*) echo pull >> "{log}" ;; esac\n'
            f'exec {shutil.which("git")} "$@"\n', 0o755)
        os.makedirs(f"{fab}/bin", exist_ok=True)
        for tool in ("fabric-resume", "fabric-watch"):
            put(f"{fab}/bin/{tool}", f'#!/bin/sh\necho "{tool} $#" >> "{log}"\n', 0o755)

        def entered(mode: str, typed: str | None) -> tuple[str, str, str]:
            """(the first stdout line, the log before any input, the log and stderr at the end)."""
            if os.path.exists(log):
                os.remove(log)
            p = subprocess.Popen(["bash", os.path.join(SRC, "enter"), f"{eh}/projects", "t", mode],
                                 env={**env, "HOME": eh, "XDG_CONFIG_HOME": f"{eh}/.config",
                                      "PATH": f"{sandbox}/logbin:{env['PATH']}"},
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            first = p.stdout.readline() if mode == "--wait" else ""
            before = open(log).read() if os.path.exists(log) else ""
            _, err = p.communicate(typed or "", timeout=120)
            return first, before, (open(log).read() if os.path.exists(log) else "") + err
        me_ = subprocess.run(["id", "-un"], stdout=subprocess.PIPE, text=True, check=True, timeout=10).stdout.strip()
        first, before, after = entered("--wait", "anything typed\n")
        check("--wait: its one line", f"{me_} - Enter to activate\n", first)
        check_status("…and nothing has run before the Enter (no pull, no resume)", 0, len(before))
        check("after Enter: the refresh, then exactly fabric-resume, with no argument",
              "pull\nfabric-resume 0\n", after)
        first, before, after = entered("--wait", None)
        check("--wait, input ended first: a plain shell, said", "input ended before Enter; a plain shell", after)
        check_absent("…and nothing resumed", "fabric-resume", after)
        _, _, after = entered("--watch", None)
        check("--watch: the refresh, then fabric-watch", "pull\nfabric-watch 0\n", after)
        check_absent("…and no resume", "fabric-resume", after)
        _, _, after = entered("--bogus", None)
        check("an unknown mode: said, a plain shell", "unknown mode '--bogus'; a plain shell", after)
        check_absent("…running nothing", "fabric-", after)
        os.remove(f"{fab}/bin/fabric-watch")
        _, _, after = entered("--watch", None)
        check("--watch with no fabric-watch in the checkout: said", "no fabric-watch in", after)

    print(f"\ntest_moveto_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
