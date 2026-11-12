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
# A registry that cannot be read leaves `all` and the verbs, and a tab prints
# no error for it; one that resolves to no file is said in a line (the plan
# would rather a tab speak than complete from the wrong tree). A login that is not proposed is still
# accepted by fabric-ctl itself.
# The hosts registry, resolved as tools/fabric/roots.py hosts_registry() will once the operator's data leaves this
# checkout (agent-fabric docs/split/move-plan.md §3, step A): AGENT_FABRIC_HOSTS_REGISTRY, then the tree named by
# AGENT_FABRIC_OPERATOR, then the operator's clone when the account has one, then the engine checkout. Empty counts as
# unset. The first that applies is the answer: a registry missing from the operator's tree is said below, never read
# from the engine's instead. The home is the login's, from the passwd database, never the session's $HOME (move-plan §3
# step D); a login with no home there has no clone to look for and no default engine checkout either.
_fabric_ctl_hosts_registry() {
    local op home
    if [[ -n "${AGENT_FABRIC_HOSTS_REGISTRY:-}" ]]; then
        printf '%s\n' "$AGENT_FABRIC_HOSTS_REGISTRY"
        return
    fi
    if [[ -n "${AGENT_FABRIC_OPERATOR:-}" ]]; then
        op="$AGENT_FABRIC_OPERATOR"
    else
        home="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f6)"
        if [[ -n "$home" && -d "$home/projects/blueteam-fabric" ]]; then
            op="$home/projects/blueteam-fabric"
        elif [[ -n "${AGENT_FABRIC_ROOT:-}" ]]; then
            op="$AGENT_FABRIC_ROOT"
        elif [[ -n "$home" ]]; then
            op="$home/projects/agent-fabric"
        else
            echo "fabric-ctl completion: no home for $(id -un) in the passwd database" >&2
            return 1
        fi
    fi
    printf '%s\n' "$op/runtime/hosts/registry.json"
}
_fabric_ctl_logins() {
    local reg
    reg="$(_fabric_ctl_hosts_registry)" || return 0
    [[ -f "$reg" ]] || { echo "fabric-ctl completion: no hosts registry at $reg" >&2; return 0; }
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
