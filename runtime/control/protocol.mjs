// runtime/control/protocol.mjs — the control plane's four envelopes (ADR-029):
// what ctl and presence send, what agentd accepts and answers with, what
// it announces when it comes up, and what its account's sessions are
// doing. JSDoc typedefs for a reader, and each envelope's keys as data,
// because no checker reads JSDoc here (agent-fabric typing is option (B),
// j28): runtime/control/tests/protocol.test.mjs holds the envelopes the
// code builds to these keys (agentd's replies and their parts, presence's
// request, ctl's request in every op shape it builds, the up and state
// records), so a typedef that drifts from the code fails a test rather
// than claiming a shape that is gone.
//
// Not GZCoord: these ride the relay's control channel as JSON, and
// gzcoord.mjs (the relay client) never reads them.

/**
 * A request: an operator's (or, for a public op, a placed account's) ask.
 * An action op is signed (`sig`, runtime/control/sign.mjs) and lives at
 * most ACTION_TTL_MAX_S.
 * @typedef {object} Request
 * @property {1} v
 * @property {'request'} kind
 * @property {string} id                 a UUIDv7
 * @property {string} from               the asker's address, host/login
 * @property {string | string[]} to      addresses, or '*' for every account
 * @property {string} op                 one of agentd's OPS
 * @property {string} ts                 ISO 8601, UTC
 * @property {number} [ttl_s]            seconds it is answered for
 * @property {number} [days]             a window, for the ops that take one
 * @property {object} [args]             an action's arguments
 * @property {string} [sig]              Ed25519 over the rest, base64
 */

/**
 * A reply: one account's answer to one request (a memory reply is followed
 * by more replies, each carrying one part).
 * @typedef {object} Reply
 * @property {1} v
 * @property {'reply'} kind
 * @property {string} id
 * @property {string} in_reply_to        the request's id
 * @property {string} from               the answering account's address
 * @property {string} op
 * @property {string} ts
 * @property {boolean} ok
 * @property {object} [data]             the op's answer, and agentd's own
 */

/**
 * Up: what agentd posts once when it starts, so ctl can tell a restart.
 * @typedef {object} Up
 * @property {1} v
 * @property {'up'} kind
 * @property {string} from
 * @property {string} ts
 */

/**
 * State: what an account's sessions are doing (runtime/control/sessions.mjs),
 * posted by agentd when it changes and on a heartbeat (ADR-029 rule 16).
 * @typedef {object} State
 * @property {1} v
 * @property {'state'} kind
 * @property {string} from
 * @property {string} ts
 * @property {{session: string, state: 'working'|'blocked'|'idle', since: string}[]} sessions
 *                                       every live session; empty when none runs
 * @property {string} [role]             the account's bound role
 * @property {string} [project]          the binding's project
 * @property {string} [last_session]     the binding's last session id (Fleet Deck: the id a resume brings back)
 * @property {boolean} [resumable]       whether that session's transcript is on the account (fabric-resume resumes it while the directory it ran in still exists, else starts fresh)
 * @property {string[]} [waits_on]       the GZCoord message ids the account's blocked jobs wait on, when any (ADR-037 rule 8)
 */

export const ENVELOPE_KEYS = Object.freeze({
  request: Object.freeze({ required: ['v', 'kind', 'id', 'from', 'to', 'op', 'ts'], optional: ['ttl_s', 'days', 'args', 'sig'] }),
  reply: Object.freeze({ required: ['v', 'kind', 'id', 'in_reply_to', 'from', 'op', 'ts', 'ok'], optional: ['data'] }),
  up: Object.freeze({ required: ['v', 'kind', 'from', 'ts'], optional: [] }),
  state: Object.freeze({ required: ['v', 'kind', 'from', 'ts', 'sessions'], optional: ['role', 'project', 'last_session', 'resumable', 'waits_on'] }),
});
