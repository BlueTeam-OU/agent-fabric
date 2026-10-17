"""tools/fabric/addenda_check.py — the validator of a holder's addenda (agent-fabric ADR-060 §5 rules 1, 6, 9).

STUB: the signature other stages base on; the checks land in the next commit."""
from __future__ import annotations


def validate(role: str, aid: str, name: str, raw: bytes) -> list[str]:
    """Findings (empty = valid) for the file `name` of `settings/roles/<role>/`
    in the store of agent id `aid`, whose bytes are `raw`."""
    return []
