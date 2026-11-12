# bash completion for moveto — installed by install.sh to
# <prefix>/share/bash-completion/completions/moveto, where bash-completion
# looks for lazily loaded completions (XDG_DATA_DIRS: /usr/local/share
# before /usr/share). Nothing to source by hand.
#
#   moveto <TAB>                 the accounts placed on this host
#   moveto <account> <TAB>       that account's clones, and --print / --list / --resume / --wait / --watch / --attach / --via (then ssh, sudo)
#   moveto --<TAB>               --list, --print
#
# The accounts come from the host registry (runtime/hosts/registry.json:
# every login whose placement is this host), read from the fabric checkout
# in the operator's own workspace (or the operator's, once it has its own) — a read of one file, no sudo, so a tab
# answers at once. Only when the registry cannot be read does the
# completion (after saying so on stderr, when there is no file) fall back to `moveto --list`, which walks every home through
# sudo (about two seconds). Clones are `moveto <account> --list`: one sudo,
# one home. An account that is not in the registry is still accepted by
# moveto itself; completion only proposes.
# The hosts registry, resolved as tools/fabric/roots.py hosts_registry() will once the operator's data leaves this
# checkout (agent-fabric docs/split/move-plan.md §3, step A): AGENT_FABRIC_HOSTS_REGISTRY, then the tree named by
# AGENT_FABRIC_OPERATOR, then the operator's clone when the account has one and it holds the file, then the engine checkout. Empty counts as
# unset. A clone without the file is skipped (until step B the operator's repository is empty). Otherwise the first that
# applies is the answer: a registry missing from the operator's tree is said below, never read from the engine's instead. The home is the login's, from the passwd database, never the session's $HOME (move-plan §3
# step D); a login with no home there has no clone to look for and no default engine checkout either.
_moveto_hosts_registry() {
    local op home
    if [[ -n "${AGENT_FABRIC_HOSTS_REGISTRY:-}" ]]; then
        printf '%s\n' "$AGENT_FABRIC_HOSTS_REGISTRY"
        return
    fi
    if [[ -n "${AGENT_FABRIC_OPERATOR:-}" ]]; then
        op="$AGENT_FABRIC_OPERATOR"
    else
        home="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f6)"
        if [[ -n "$home" && -f "$home/projects/blueteam-fabric/runtime/hosts/registry.json" ]]; then
            op="$home/projects/blueteam-fabric"
        elif [[ -n "${AGENT_FABRIC_ROOT:-}" ]]; then
            op="$AGENT_FABRIC_ROOT"
        elif [[ -n "$home" ]]; then
            op="$home/projects/agent-fabric"
        else
            echo "moveto completion: no home for $(id -un) in the passwd database" >&2
            return 1
        fi
    fi
    printf '%s\n' "$op/runtime/hosts/registry.json"
}
_moveto_accounts() {
    local reg host
    reg="$(_moveto_hosts_registry)" || return 0
    [[ -f "$reg" ]] || echo "moveto completion: no hosts registry at $reg" >&2
    host="$(hostname -s 2>/dev/null)"
    if [[ -r "$reg" && -n "$host" ]] && command -v jq >/dev/null 2>&1; then
        jq -r --arg h "$host" '.placement | to_entries[] | select(.value == $h) | .key' "$reg" 2>/dev/null
    else
        moveto --list 2>/dev/null | awk '{print $1}'
    fi
}
_moveto() {
    local cur prev
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    if (( COMP_CWORD == 1 )); then
        if [[ "$cur" == -* ]]; then
            mapfile -t COMPREPLY < <(compgen -W "--list" -- "$cur")
        else
            mapfile -t COMPREPLY < <(compgen -W "$(_moveto_accounts | tr '\n' ' ')" -- "$cur")
        fi
    elif [[ "$prev" == --via ]]; then
        mapfile -t COMPREPLY < <(compgen -W "ssh sudo" -- "$cur")
    elif (( COMP_CWORD == 2 )) && [[ "$prev" != -* ]]; then
        if [[ "$cur" == -* ]]; then
            mapfile -t COMPREPLY < <(compgen -W "--print --list --resume --wait --watch --attach --via" -- "$cur")
        else
            mapfile -t COMPREPLY < <(compgen -W "$(moveto "$prev" --list 2>/dev/null | tr '\n' ' ')" -- "$cur")
        fi
    fi
}
complete -F _moveto moveto
