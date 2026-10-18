---
role: "devex-tooling"
class: solution
topic: "settings-validate-test-env"
description: "agent-fabric-settings tools/test_validate_policies.py exits 1 without FABRIC and SETTINGS_REPO=<owner>/<name>"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ff4f34949ceb7652
---

## agent-fabric-settings tools/test_validate_policies.py exits 1 without FABRIC and SETTINGS_REPO=<owner>/<name>

In both agent-fabric-settings repos (BlueTeam-OU, gzapi-org), `tools/test_validate_policies.py` exits 1 with only a usage line unless `FABRIC=<agent-fabric checkout>` and `SETTINGS_REPO=<owner>/<name>` are set (a path, not a slug, fails two tests). CI sets both in `.github/workflows/validate.yml`. Seen on gzapi-org settings #4 (2026-10-13).

*Observed 2026-10-13 (devex-tooling)*
