# bash completion for moveto — installed by install.sh to
# <prefix>/share/bash-completion/completions/moveto, where bash-completion
# looks for lazily loaded completions (XDG_DATA_DIRS: /usr/local/share
# before /usr/share). Nothing to source by hand.
#
#   moveto <TAB>                 the accounts placed on this host
#   moveto <account> <TAB>       that account's clones, and --print / --list / --resume
#   moveto --<TAB>               --list, --print
#
# The accounts come from the host registry (runtime/hosts/registry.json:
# every login whose placement is this host), read from the fabric checkout
# in the operator's own workspace — a read of one file, no sudo, so a tab
# answers at once. Only when the registry cannot be read does the
# completion fall back to `moveto --list`, which walks every home through
# sudo (about two seconds). Clones are `moveto <account> --list`: one sudo,
# one home. An account that is not in the registry is still accepted by
# moveto itself; completion only proposes.
_moveto_accounts() {
    local root reg host
    root="${AGENT_FABRIC_ROOT:-$HOME/projects/agent-fabric}"
    reg="$root/runtime/hosts/registry.json"
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
    elif (( COMP_CWORD == 2 )) && [[ "$prev" != -* ]]; then
        if [[ "$cur" == -* ]]; then
            mapfile -t COMPREPLY < <(compgen -W "--print --list --resume" -- "$cur")
        else
            mapfile -t COMPREPLY < <(compgen -W "$(moveto "$prev" --list 2>/dev/null | tr '\n' ' ')" -- "$cur")
        fi
    fi
}
complete -F _moveto moveto
