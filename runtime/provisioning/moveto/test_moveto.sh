#!/usr/bin/env bash
# tools/moveto/test_moveto.sh
#
# Behavioural tests for moveto's target resolution — the half testable without
# spawning an interactive shell. `--print` exists for exactly this: it runs the
# whole resolution path and stops before the exec.
#
# WHAT THE MOCKS DO AND DO NOT PROVE. `getent` and `sudo` are replaced on PATH,
# because the fixture accounts do not exist and the suite must not need root.
# The sudo mock RECORDS the argv it was handed and then runs the command as the
# caller — so an assertion can check WHICH ACCOUNT was asked for, which is the
# tool's only privilege boundary, but nothing here proves the kernel honoured
# it. An earlier version of this mock silently discarded `-u`, and deleting
# both sudo gates from the tool left the suite green.
#
# Exit codes:
#   0  all assertions passed
#   1  one or more assertions failed

set -uo pipefail

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" && pwd )"
UNDER_TEST="$SCRIPT_DIR/moveto"

[[ -f "$UNDER_TEST" ]] || { echo "test: $UNDER_TEST not found" >&2; exit 1; }

failures=0
SANDBOX=""
cleanup() { [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"; }
trap cleanup EXIT

SANDBOX="$(mktemp -d)"
BIN="$SANDBOX/bin"; mkdir -p "$BIN"
SUDO_LOG="$SANDBOX/sudo.log"

# Fixtures, each earning its place:
#   solo    the template layout, clone named after the account
#   odd     ONE clone named differently — the only fixture that can tell
#           "title = account" from "title = clone basename", because under the
#           template those two strings are identical
#   many    several clones: must refuse to guess
#   empty   projects/ exists but holds nothing
#   nodir   no projects/ at all — a different state, needing a different answer
#   spaced  one clone whose name contains a space
#   esc     one clone whose name contains ESC and BEL
mkdir -p "$SANDBOX/home/solo/projects/solo"
# Beside the clone: the workspace CLAUDE.md and the control-plane checkout
# that bootstrap.sh puts in every ~/projects. Neither is a clone.
printf 'workspace\n' > "$SANDBOX/home/solo/projects/CLAUDE.md"
mkdir -p "$SANDBOX/home/solo/projects/agent-fabric"
mkdir -p "$SANDBOX/home/odd/projects/weird-name"
mkdir -p "$SANDBOX/home/many/projects/"{alpha,beta,gamma}
mkdir -p "$SANDBOX/home/empty/projects"
mkdir -p "$SANDBOX/home/nodir"
mkdir -p "$SANDBOX/home/spaced/projects/spaced backup"
mkdir -p "$SANDBOX/home/esc/projects/$(printf 'good\033]0;INJECTED\007tail')"

# A bound role for two of them: --list prints it beside the account.
mkdir -p "$SANDBOX/home/solo/.local/state/agent-fabric/agents/solo" "$SANDBOX/home/esc/.local/state/agent-fabric/agents/esc"
printf '{"agent": "solo", "role": "web-dev", "updated_at": "x"}\n' > "$SANDBOX/home/solo/.local/state/agent-fabric/agents/solo/binding.json"
printf '{"agent": "esc", "role": "evil\033]0;X\007role"}\n' > "$SANDBOX/home/esc/.local/state/agent-fabric/agents/esc/binding.json"

ACCOUNTS="solo odd many empty nodir spaced esc"

cat > "$BIN/getent" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "passwd" && \$# -eq 2 ]]; then
    for u in $ACCOUNTS; do
        [[ "\$2" == "\$u" ]] && { echo "\$u:x:2000:2000::$SANDBOX/home/\$u:/bin/bash"; exit 0; }
    done
    exit 2
fi
if [[ "\$1" == "passwd" && \$# -eq 1 ]]; then
    for u in $ACCOUNTS; do echo "\$u:x:2000:2000::$SANDBOX/home/\$u:/bin/bash"; done
    exit 0
fi
exit 2
EOF

# Records the requested account, then runs the command as the caller. SUDO_DENY
# makes it refuse, which is the only way to reach the "cannot become" branch.
cat > "$BIN/sudo" <<EOF
#!/usr/bin/env bash
want=""
while [[ \$# -gt 0 ]]; do
    case "\$1" in
        -n|-H) shift ;;
        -u) want="\$2"; shift 2 ;;
        *) break ;;
    esac
done
echo "as=\$want argv=\$*" >> "$SUDO_LOG"
[[ -n "\${SUDO_DENY:-}" ]] && exit 1
exec "\$@"
EOF
chmod 755 "$BIN/getent" "$BIN/sudo"
export PATH="$BIN:$PATH"

check() { # <label> <expected-substring> <actual>
    if [[ "$3" == *"$2"* ]]; then printf '  ok   %s\n' "$1"
    else printf '  FAIL %s\n       want substring: %s\n       got: %s\n' "$1" "$2" "$3"; failures=$((failures+1)); fi
}
check_absent() { # <label> <forbidden-substring> <actual>
    if [[ "$3" != *"$2"* ]]; then printf '  ok   %s\n' "$1"
    else printf '  FAIL %s\n       must NOT contain: %s\n       got: %s\n' "$1" "$2" "$3"; failures=$((failures+1)); fi
}
check_status() { # <label> <expected> <actual>
    if [[ "$3" == "$2" ]]; then printf '  ok   %s\n' "$1"
    else printf '  FAIL %s: expected exit %s, got %s\n' "$1" "$2" "$3"; failures=$((failures+1)); fi
}

echo "1. the destination is the workspace, titled by the role instance"
out=$("$UNDER_TEST" solo --print 2>&1); st=$?
check_status "exits 0" 0 "$st"
check "resolves ~/projects — the place a session launches from" "/home/solo/projects
" "$out"
check_absent "not the clone" "/home/solo/projects/solo" "$out"
check "title is the account" "title: solo" "$out"
listed=$("$UNDER_TEST" solo --list 2>&1)
check_absent "the workspace CLAUDE.md is not a clone" "CLAUDE.md" "$listed"
check_absent "the agent-fabric checkout is not a clone" "agent-fabric" "$listed"

echo "1b. a clone named differently changes nothing: still the workspace"
out=$("$UNDER_TEST" odd --print 2>&1); st=$?
check_status "exits 0" 0 "$st"
check "resolves the workspace" "/home/odd/projects
" "$out"
check "title is the account" "title: odd" "$out"

echo "2. several clones: the workspace, no guessing needed"
out=$("$UNDER_TEST" many --print 2>&1); st=$?
check_status "exits 0" 0 "$st"
check "resolves the workspace" "/home/many/projects
" "$out"
check "title is the account" "title: many" "$out"

echo "3. several clones, one named: enters it and titles by clone"
out=$("$UNDER_TEST" many beta --print 2>&1); st=$?
check_status "exits 0" 0 "$st"
check "resolves the named clone" "/home/many/projects/beta" "$out"
check "title is the clone" "title: beta" "$out"
out=$("$UNDER_TEST" solo solo --print 2>&1); st=$?
check "a single clone named explicitly is entered" "/home/solo/projects/solo" "$out"
check "…titled by the account" "title: solo" "$out"

echo "4. empty projects/ is enterable; missing projects/ is not provisioned"
out=$("$UNDER_TEST" empty --print 2>&1); st=$?
check_status "empty exits 0" 0 "$st"
check "empty resolves the workspace (bootstrap may still run there)" "/home/empty/projects
" "$out"
out=$("$UNDER_TEST" nodir --print 2>&1); st=$?
check_status "missing exits 1" 1 "$st"
check "missing says not provisioned" "not provisioned yet" "$out"

echo "5. unknown account and unknown clone fail loudly"
out=$("$UNDER_TEST" nosuchuser --print 2>&1); st=$?
check_status "unknown account exits 1" 1 "$st"
check "names the account" "no such account: nosuchuser" "$out"
out=$("$UNDER_TEST" solo nosuchclone --print 2>&1); st=$?
check_status "unknown clone exits 1" 1 "$st"
check "names the path" "no such directory" "$out"

echo "6. --list shows accounts WITH clones and omits those without"
out=$("$UNDER_TEST" --list 2>&1); st=$?
check_status "exits 0" 0 "$st"
check "lists the template account" "solo" "$out"
check "lists a multi-clone account's clones" "gamma" "$out"
check_absent "omits an account whose projects/ is empty" "empty" "$out"
check_absent "omits an account with no projects/ at all" "nodir" "$out"
check "the role sits between the account and its clones" "$(printf '%-24s %-20s %s' solo web-dev solo)" "$out"
check "an account with no binding shows -" "$(printf '%-24s %-20s' many -)" "$out"
check "a role's control characters are stripped" "evil]0;Xrole" "$out"

echo "7. a clone name containing a space is usable, not a wrong path"
out=$("$UNDER_TEST" spaced "spaced backup" --print 2>&1); st=$?
check_status "exits 0" 0 "$st"
check "resolves the spaced clone" "/home/spaced/projects/spaced backup" "$out"

echo "8. control characters in a clone name never reach the terminal"
out=$("$UNDER_TEST" --list 2>&1)
check "the printable part still shows" "good" "$out"
check_absent "no ESC" "$(printf '\033')" "$out"
check_absent "no BEL" "$(printf '\007')" "$out"
out=$("$UNDER_TEST" esc "$(printf 'good\033]0;INJECTED\007tail')" --print 2>&1)
check_absent "title carries no ESC either" "$(printf '\033')" "$out"

echo "9. the named clone must be a single segment"
out=$("$UNDER_TEST" solo ../../etc --print 2>&1); st=$?
check_status "traversal exits 1" 1 "$st"
check "says why" "single name under" "$out"
check_absent "no path was resolved" "title:" "$out"

echo "10. the target account is what sudo is asked for"
: > "$SUDO_LOG"
"$UNDER_TEST" solo --print >/dev/null 2>&1
log=$(cat "$SUDO_LOG" 2>/dev/null)
# Naming the COMMANDS matters: asserting only that "as=solo" appears somewhere
# is satisfied by the can-I-become gate alone, so dropping -u from the
# enumeration and the existence check would go unnoticed.
check "the clone listing ran as the target" "as=solo argv=find" "$log"
check "the directory check ran as the target" "as=solo argv=test -d" "$log"
check_absent "never a bare sudo with no -u" "as= " "$log"

echo "11. an account we cannot become is refused, not guessed at"
out=$(SUDO_DENY=1 "$UNDER_TEST" solo --print 2>&1); st=$?
check_status "exits 1" 1 "$st"
check "says it cannot become the account" "cannot become 'solo'" "$out"

echo "12. tab completion: accounts from the host registry, clones from the tool"
# A fabric checkout whose registry places two accounts on this host and one
# elsewhere; the completion reads it with no sudo and proposes only ours.
COMP_ROOT="$(mktemp -d)"; mkdir -p "$COMP_ROOT/runtime/hosts"
printf '{"placement":{"alpha-01":"%s","beta-01":"%s","gamma-01":"elsewhere"}}\n' "$(hostname -s)" "$(hostname -s)" > "$COMP_ROOT/runtime/hosts/registry.json"
# The completion calls `moveto` by name for clones: the tool under test,
# through the same mocked getent/sudo the rest of this suite uses.
ln -sf "$UNDER_TEST" "$BIN/moveto"
complete_words() {  # complete_words <words...> -> COMPREPLY lines; the cursor is on the last word
    ( export AGENT_FABRIC_ROOT="$COMP_ROOT"
      # shellcheck disable=SC1090
      source "$SCRIPT_DIR/completion.bash"
      COMP_WORDS=("$@"); COMP_CWORD=$(( $# - 1 )); _moveto; printf '%s\n' "${COMPREPLY[@]}" )
}
out=$(complete_words moveto "")
check "proposes the accounts placed on this host" "alpha-01" "$out"
check "and the other one" "beta-01" "$out"
check_absent "not an account placed elsewhere" "gamma-01" "$out"
out=$(complete_words moveto "be")
check "narrows on the prefix" "beta-01" "$out"
check_absent "and drops the rest" "alpha-01" "$out"
out=$(complete_words moveto "--")
check "a dash completes the flag" "--list" "$out"
# the second word: --print / --list, or the account's clones through the tool's own listing
out=$(complete_words moveto alpha-01 "--")
check "second-word flags" "--print" "$out"
# `moveto <account> --list` runs the tool: the fixture account "many" has three clones
out=$(complete_words moveto many "")
check "clones come from moveto <account> --list" "beta" "$out"
out=$(complete_words moveto many "ga")
check "and narrow on the prefix" "gamma" "$out"
check_absent "dropping the rest" "alpha" "$out"
rm -rf "$COMP_ROOT"

echo "enter: a fabric that cannot be fast-forwarded is said with git's own reason"
EH="$SANDBOX/enterhome"; mkdir -p "$EH/projects"
git init -q "$EH/projects/agent-fabric"
git -C "$EH/projects/agent-fabric" remote add origin "$SANDBOX/no-such-origin.git"
err="$(HOME="$EH" XDG_CONFIG_HOME="$EH/.config" bash "$SCRIPT_DIR/enter" "$EH/projects" "t" </dev/null 2>&1 >/dev/null)"
check "the reason is git's first error line" "does not appear to be a git repository" "$err"
check_absent "…never the old guess" "offline, or the clone is not on main" "$err"

echo
if [[ $failures -eq 0 ]]; then echo "test_moveto: all assertions passed"; exit 0; fi
echo "test_moveto: $failures assertion(s) failed"
exit 1
