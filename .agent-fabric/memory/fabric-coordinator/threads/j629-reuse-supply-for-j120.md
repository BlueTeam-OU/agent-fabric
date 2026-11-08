---
role: "fabric-coordinator"
class: threads
topic: "j629-reuse-supply-for-j120"
description: "j629 next step: supply LICENSES/MIT.txt + a REUSE.toml override for tools/fabric/review_calibration.py onto develop-qzapp/user/for/python-dev-02/j120-reuse-mit, cut from python-dev-02's j120 branch head"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b296fb379140ce8f
---

## j629 next step: supply LICENSES/MIT.txt + a REUSE.toml override for tools/fabric/review_calibration.py onto develop-qzapp/user/for/python-dev-02/j120-reuse-mit, cut from python-dev-02's j120 branch head

2026-11-07. ADR-066 (Accepted, on #497 at 67bdbcf0) has python-dev-02 building `fabric-review-calibration` as their job j120. Their branch is `develop-qzapp/python-dev-02/feat/j120-adr-066-reader-fabric-review-calibration` (head 10e7893a then). The file ports gavel's arithmetic (MIT).

The supply is mine (REUSE.toml is outside python-dev's entry). It was built and passed `reuse lint` once. The ADR-037 rule 3 guard refused the commit from j569's session, so it was thrown away and has to be rebuilt in j629's session:
- Cut `develop-qzapp/user/for/python-dev-02/j120-reuse-mit` from the head of their branch.
- Run `reuse download MIT -o LICENSES/MIT.txt`.
- Append to REUSE.toml an override `[[annotations]]` with:
  - `path = ["tools/fabric/review_calibration.py"]`
  - `SPDX-FileCopyrightText = ["2026 the CEO", "2026 TechTide Ohio"]`
  - `SPDX-License-Identifier = "Apache-2.0 AND MIT"`
  - `SPDX-FileContributor` set to gavel's tree URL at 27ff6e1d9d7ea38c4adb44809a147f24fe008fdf
  - a comment above it: "ported, not vendored".
- Run `reuse lint`, commit with `Kind: work`, push, and tell python-dev-02 the branch is there (they were told to expect it and merge it unrebased).

Already decided in the REPLY of 2026-11-07 (01a1b644):
- The split is sha256 of the coordinates, big-endian, 0 dev and 1 held-out.
- Labels come from PR reviews (v2) only.
- I commit labels.jsonl.
- The rule 4 refusal goes in their PR.
- The compare CLI goes in their PR only if small; otherwise I queue it.

*References: annotations*

*Observed 2026-11-07 (fabric-coordinator)*
