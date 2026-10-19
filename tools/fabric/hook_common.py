"""tools/fabric/hook_common.py — what the Claude Code status line and tab title
(statusline.py, tab_title.py) both ask the machine: who the agent is, and the
short host name. Imported by hooks that run on every refresh, so it imports
nothing it does not use."""
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
WHOAMI_TIMEOUT_S = 10


def agent_name() -> str:
    """The Linux login, from the canonical resolver (bin/fabric-whoami); the effective login when the resolver
    cannot run or fails. A resolver that succeeds with an empty answer is believed, as the shell hooks did."""
    try:
        r = subprocess.run([os.path.join(ROOT, "bin", "fabric-whoami")], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=WHOAMI_TIMEOUT_S)
        if r.returncode == 0:
            return os.fsdecode(r.stdout).rstrip("\n")
    except (OSError, subprocess.SubprocessError):
        pass
    import pwd
    return pwd.getpwuid(os.geteuid()).pw_name


def short_host() -> str:
    """`hostname -s`: the node name up to its first dot."""
    return os.uname().nodename.split(".")[0]


def current_directory() -> str:
    """The process's directory, else $PWD, else "": a hook started in a directory that has since been removed
    still runs, as the shell hooks' `$PWD` did, and then finds no repository."""
    try:
        return os.getcwd()
    except OSError:
        return os.environ.get("PWD", "")
