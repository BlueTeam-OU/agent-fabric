---
role: "python-dev"
class: threads
topic: "j141-control-dual-carrier-state"
description: "j141 (ADR-029 rule 18 control carrier): where the code lives, what is committed, what is left (mutations, suite, review, live read-back), traps met"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b64a1503571648cc
---

## j141 (ADR-029 rule 18 control carrier): where the code lives, what is committed, what is left (mutations, suite, review, live read-back), traps met

j141, branch develop-qzapp/python-dev-02/feat/j141-adr-029-rule-18-build-control (worktree agent-fabric-j141-...), REQUEST 01a1cf18 from the owner's operator account.
Committed (2026-11-12): render adds the `fabric-control` human-client endpoint (roster.py CONTROL_ENDPOINT); GZCoord carrier refuses a `fabric-control/1 ` body both ways (framing.CONTROL_PREFIX, engine.py); `control_carrier` in runtime/control/config.json + agentd.control_config (env FABRIC_CONTROL_CARRIER, a third word raises); the whole carrier in tools/fabric/gzcoord/carrier/control_link.py (Child supervisor, Inbox, Directory, Carrier, Server socket, Session, Merge, start_for_agentd); agentd.main has handle()/deliver() shared by both carriers, `stop=` Event, EXIT_HOOKS; ctl.main dual path (_second_carrier, take(), Merge rows, DUAL_GRACE_S).
Tests: tests/test_gzcoord_carrier_control_link.py, test_control_dual.py (ctl end to end), test_control_agentd_dual.py (agentd.main in a thread), tests/fake_interweave_human.py (faithful fake child over a directory "network"), mutation runner kept in the scratch dir (list in the commit's M table).
**Traps:** (1) lint bans the managed project's name (InterWeave, interweave, INTERWEAVE) in any tools/fabric file outside tools/fabric/gzcoord/carrier/ — that is why the module lives there and ctl/agentd use CARRIER_LABEL/CARRIER_NAME/link.VIA/RELAY_ONLY_OPS. (2) the guard refuses `git commit` in a command that also contains $HOME — run tests and commit in separate calls. (3) interweave-human prints each outbound twice; a FIFO stdin cannot be reused after EOF. (4) state_dir() adds agents/<login>. (5) mutations edit the tree: never run other tests or edits meanwhile.
**State 2026-11-12:** MERGED as #571 (8 work, 3 fix). Job paused only on the two-account live read-back with python-dev-03 (their j135): they run check/render/serve/stop with J141_PEER=python-dev-02 from a worktree of the branch (now on main: tests/live_control_dual.py); I run `relay`, `ask`, then file docs/live-checks/ for the requester (docs/ outside my entry). Scratch daemons/profiles a,b in ~/agent-fabric-tmp/j141s and a host scratch path to clean after. Merge REPLY sent; ADR rule 18 prose follow-ups listed in it.

*Observed 2026-11-12 (python-dev)*
