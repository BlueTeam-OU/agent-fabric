// A module hook for recording what the Node validator was asked, while it
// still exists (agent-fabric ADR-040 §7: both validators agree on every
// message the suite holds before the Node one goes). Loaded with
//   NODE_OPTIONS="--import <this file>"  GZCOORD_PARITY_RECORD=<file.jsonl>
// it rewrites gzmsg.mjs as it loads: validate, parse and normalize keep
// their code and gain a wrapper that appends each call's input and the
// Node's own answer to the record, one JSON object per line. Children
// inherit NODE_OPTIONS, so the commands the suite spawns record too.
// Test tooling only: nothing in the fabric loads it.
import { register } from 'node:module';
register('./record-loader.mjs', import.meta.url);
