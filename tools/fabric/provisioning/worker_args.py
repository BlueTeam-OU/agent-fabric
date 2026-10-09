"""tools/fabric/provisioning/worker_args.py — what the new-agent worker is asked,
parsed once into a value (ADR-040 Wave 5; carried from tools/fabric/
new_agent_worker.py, which handed the shell the same parse as bash text).

CONTRACT of the worker, frozen from the bash (ADR-040 §5 rule 3):
`prepare|finish <login> <role> [--claude V] [--clone <id>=<remote>]…
[--project <id>]… [--claude-account <slug>=<fp12> | --no-claude-account]
[--signing-key-next] [--via-host <id>] [--dry-run]` or `host-check <login>`; or, for a human
login (ADR-044), `prepare|finish <login> --human [--dry-run]`, where any of
the others is exit 2. --signing-key-next (finish): the orchestrator imports
the signing key after this phase, so the closing says it follows rather
than print the lines a person runs. --via-host (finish): the account is on
another host than the coordinator's, so the closing's lines reach it through
fabric-host <id>, never a local sudo. A missing phase:
USAGE, exit 2; an unknown argument, no login, no role: one line, exit 2;
--claude without a value: exit 1. Exactly as the bash shifted: a phase
with too few words keeps them, so `prepare <login>` reports the login as
an unknown argument, not "no role" (replicated, not fixed).
Every message here is the worker's own (`new-agent: …`, or
`new-agent-worker: …` for its usage), on stderr."""
from __future__ import annotations

import re
from dataclasses import dataclass

USAGE = "usage: new-agent-worker.sh prepare|finish <login> <role> ... | host-check <login> [--project <id>]..."
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
# Checked again here, whatever the caller checked: the value is spliced
# into the string as_login evals.
TARGET = re.compile(r"stable|latest|[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?")
# The Claude account finish verifies: a template's slug and its token's
# fingerprint (sha256[:12]), as the orchestrator read them from its store.
# Checked here too: the value is spliced into the string the worker evals.
CLAUDE_ACCOUNT = re.compile(r"([a-z0-9][a-z0-9-]{0,62})=([0-9a-f]{12})")
# The registry id of the host an account is reached on from the coordinator's
# (--via-host): printed in the closing's lines, so a name and nothing else.
HOST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,62}")


class Exit(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code, self.msg = code, msg


@dataclass
class WorkerArgs:
    """What the worker was asked, parsed once (the bash text of `args` is rendered from it)."""
    phase: str
    login: str
    role: str
    human: bool
    dry: bool
    claude: str
    projects: list[str]
    remote: dict[str, str]
    account: str
    no_account: bool
    signing_next: bool
    via: str


def parse_args(argv: list[str]) -> WorkerArgs:
    phase = argv[0] if argv else ""
    rest = argv[1:]
    login = rest[0] if rest else ""
    role, human = "", False
    if phase in ("prepare", "finish") and rest[1:2] == ["--human"]:
        human, rest = True, rest[2:]
    elif phase in ("prepare", "finish"):
        role = rest[1] if len(rest) > 1 else ""
        # `shift 2 || true`: with fewer than two words bash shifts none.
        rest = rest[2:] if len(rest) >= 2 else rest
    elif phase == "host-check":
        rest = rest[1:] if rest else rest
    else:
        raise Exit(2, USAGE)
    dry, claude, projects, remote, account, no_account, signing_next, via = False, "", [], {}, "", False, False, ""
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--dry-run":
            dry = True
        elif a == "--no-claude-account":
            no_account = True
        elif a == "--signing-key-next":
            signing_next = True
        elif a == "--via-host" or a.startswith("--via-host="):
            if a == "--via-host":
                if i + 1 >= len(rest):
                    raise Exit(1, f"new-agent-worker: {a} needs a value")
                i += 1
                via = rest[i]
            else:
                via = a[len("--via-host="):]
            if not HOST_ID.fullmatch(via):
                raise Exit(2, "new-agent-worker: --via-host takes a host's registry id")
        elif a == "--claude-account" or a.startswith("--claude-account="):
            if a == "--claude-account":
                if i + 1 >= len(rest):
                    raise Exit(1, f"new-agent-worker: {a} needs a value")
                i += 1
                account = rest[i]
            else:
                account = a[len("--claude-account="):]
            if not CLAUDE_ACCOUNT.fullmatch(account):
                raise Exit(2, "new-agent-worker: --claude-account takes <slug>=<12 hex of its token's sha256>")
        elif a in ("--claude", "--clone", "--project"):
            if i + 1 >= len(rest):
                raise Exit(1, f"new-agent-worker: {a} needs a value")
            v = rest[i + 1]
            i += 1
            if a == "--claude":
                claude = v
            elif a == "--project":
                projects.append(v)
            else:
                pid = v.split("=", 1)[0]
                remote[pid] = v.split("=", 1)[1] if "=" in v else v
                projects.append(pid)
        elif a.startswith("--claude="):
            claude = a[len("--claude="):]
        elif a.startswith("--clone="):
            v = a[len("--clone="):]
            pid = v.split("=", 1)[0]
            remote[pid] = v.split("=", 1)[1] if "=" in v else v
            projects.append(pid)
        else:
            raise Exit(2, f"new-agent-worker: unknown argument {a}")
        i += 1
    if not login:
        raise Exit(2, "new-agent-worker: no login")
    if phase != "host-check" and not role and not human:
        raise Exit(2, "new-agent-worker: no role")
    if account and no_account:
        raise Exit(2, "new-agent-worker: --claude-account and --no-claude-account together")
    if human and (account or no_account or claude or projects or signing_next or via):
        raise Exit(2, "new-agent-worker: --human takes no Claude account, claude, project or signing key (ADR-044)")
    return WorkerArgs(phase, login, role, human, dry, claude, projects, remote, account, no_account, signing_next, via)
