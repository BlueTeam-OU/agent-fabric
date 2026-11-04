"""tools/fabric/control/ops/account_drift.py — `drift`, the control op: what in this account differs from
what the fabric wrote there (tools/fabric/account_drift.py; j138). A part of the ops package, whose
__init__.py is the contract every extractor here keeps.

A read, and nothing is written: the record is compared with the files, and the checkout's
`bootstrap.py --dry-run` says what it would change. The reply is the module's report —
{"status": "ok"|"drift", "counts", "findings"} — with at most FINDINGS_MAX findings
(`findings_total` and `truncated` when there are more; the counts are always whole). A check that
could not be made is {"status": "failed", "reason"}: an account whose record cannot be read is not
an account with no drift.

Paths leave the account: the files the fabric wrote in its home and the links it would make. They are
the fabric's own and the account owner's home, and no file content, hash or secret goes in the reply.
"""
from __future__ import annotations

from typing import Any, Mapping

import account_drift as core   # noqa: E402 — util puts tools/fabric on sys.path (and this package's own name is not the module's)

FINDINGS_MAX = 100


def drift_report(home: str | None = None, root: str | None = None, state: str | None = None, **opts: Any) -> dict[str, Any]:
    try:
        report = core.check(state=state, root=root, home=home, **opts)
    except core.DriftError as e:
        return {"status": "failed", "reason": str(e)[:300]}
    findings = report["findings"]
    if len(findings) > FINDINGS_MAX:
        report = {**report, "findings": findings[:FINDINGS_MAX], "findings_total": len(findings), "truncated": True}
    return report


def section(ctx: Mapping[str, Any]) -> dict[str, Any]:
    """The `drift` section for a request's context: the daemon's cached read when it has one (`drift_cached`), else a fresh one."""
    if ctx.get("drift_cached"):
        return ctx["drift_cached"]()
    return drift_report(ctx.get("home"), ctx.get("root"), **(ctx.get("drift_opts") or {}))
