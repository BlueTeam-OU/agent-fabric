# bash completion for fabric-ctl — installed per login at
# ~/.local/share/bash-completion/completions/fabric-ctl, where bash-completion
# lazily loads a user's own completions. Nothing to source by hand.
#
#   fabric-ctl <TAB>                 all, keygen, help and every placed login
#   fabric-ctl <login|all> <TAB>     the verbs
#   fabric-ctl <login|all> <verb> <TAB>   that verb's options and fixed words, then --json --timeout --help
#
# The logins are the keys of runtime/hosts/registry.json `placement`, every
# host's, read from the fabric checkout: one file, no network, no sudo, so a
# tab answers at once. The verbs and a verb's words are `fabric-ctl --verbs`
# and `fabric-ctl --verbs <verb>` (one per line), which read no relay either.
# A registry that cannot be read leaves `all` and the verbs: a tab never
# prints an error on the terminal, and a login that is not proposed is still
# accepted by fabric-ctl itself.
_fabric_ctl_logins() {
    local root reg
    root="${AGENT_FABRIC_ROOT:-$HOME/projects/agent-fabric}"
    reg="$root/runtime/hosts/registry.json"
    [[ -r "$reg" ]] || return 0
    python3 -c '
import json, sys
try:
    for login in json.load(open(sys.argv[1], encoding="utf-8"))["placement"]:
        print(login)
except Exception:
    pass
' "$reg" 2>/dev/null
}
_fabric_ctl() {
    local cur
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    if (( COMP_CWORD == 1 )); then
        mapfile -t COMPREPLY < <(compgen -W "all keygen help $(_fabric_ctl_logins | tr '\n' ' ')" -- "$cur")
    elif (( COMP_CWORD == 2 )) && [[ "${COMP_WORDS[1]}" != keygen && "${COMP_WORDS[1]}" != help ]]; then
        mapfile -t COMPREPLY < <(compgen -W "$(fabric-ctl --verbs 2>/dev/null | tr '\n' ' ')" -- "$cur")
    elif (( COMP_CWORD >= 3 )); then
        mapfile -t COMPREPLY < <(compgen -W "$({ fabric-ctl --verbs "${COMP_WORDS[2]}" 2>/dev/null; printf '%s\n' --json --timeout --help; } | sort -u | tr '\n' ' ')" -- "$cur")
    fi
}
complete -F _fabric_ctl fabric-ctl
