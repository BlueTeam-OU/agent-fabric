---
role: "python-dev"
class: solution
topic: "j57-locale-suffix-retired-delivered"
description: "j57 ADR-060 stage 6 delivered — launch-locale.json record, en without holder.json carries no TZ/country, test traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a025903c3e3c1b94
---

## j57 ADR-060 stage 6 delivered — launch-locale.json record, en without holder.json carries no TZ/country, test traps

Branch develop-qzapp/python-dev-02/for/user/locale-suffix-retire, head 3832a522, REPLY sent (seq 303408). The launcher records the resolved locale in `<state dir>/launch-locale.json` ({"locale": tag}); `tools/fabric/launch_locale.py` has read()/record(); i18n and activity read it, absent/unusable = "en".

**Why:** with no holder.json, locale is "en" but with NO timezone/country (en/locale.json has Asia/Tbilisi; applying it would put that TZ on every login). Left as a decision for the user.
**How to apply:** tests that read the record go through `AGENT_FABRIC_STATE_DIR` in os.environ (i18n ignores its `env` param for it). Fixtures that copy launcher parts (test_launch.py two-launchers) must list launch_locale.py. Never `cat > /dev/null` in a chained command (hangs on stdin); test_launch_cli prints unset env as `TZ=` (empty), not absent. launch_prompt/install_agent_files still use the suffix until the user's branch changes them.

*Observed 2026-10-18 (python-dev)*
