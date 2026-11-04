# ADR-002 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-17 — Holder addenda (ADR-060)

ADR-060 (accepted 2026-10-17) adds a holder's charter and brief addenda, from the agent's own store, after the shared charter and brief. Rule 4's order gains the two slots, and its same-bytes promise now names the addenda among the inputs. Rules 8 and 9 stand: the charter and brief are still the role's; an addendum is the holder's, installed by its parent.

### Amendment 2026-11-04 — Rebind reads the other host's binding

External review F10: `read_binding` refused a binding written on another host and advised `fabric-role bind`, which read the same binding through `read_binding` and refused it, so a login moved between hosts had no locked way to rebind. Rule 7 now says how the rebind happens: `bind` and `unbind` read the other host's binding (`read_binding(other_host=True)`) under the agent lock, check its copies for adaptation where they are, and replace it; a rollback writes the original text back rather than re-stamping it with this host. Every other reader still refuses it.
