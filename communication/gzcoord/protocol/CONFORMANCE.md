# Conformance

A component may claim one or more conformance profiles.

## Protocol parser

A conforming parser:

- recognizes `[GZCOORD/1] TYPE`;
- parses metadata and named sections; MAY accept a run of spaces after `KEY:` and trim the value — an allowance, not a requirement; the well-formed separator is one space (§6);
- validates logical addresses;
- preserves unknown extension fields/sections;
- accepts free-form roles;
- rejects known transport/runtime fields when presented as core metadata;
- reports a line in the metadata block that is neither metadata nor a section marker;
- rejects a `REPLY-EXPECTED` value other than `yes` or `no`;
- rejects a metadata key that appears more than once;
- rejects a `BROADCAST` value other than `true`;
- rejects more than one of `TO`, `TO-ROLE` and `BROADCAST`;
- rejects a message of type `HELLO` or `GOODBYE`, naming the type as retired (§8);
- rejects a message with no `MESSAGE-ID`;
- MAY warn when `MESSAGE-ID` or `IN-REPLY-TO` does not have the shape the deployment mints (§7.2 keeps the identifier opaque, so this is never a rejection);
- does not infer project authority from messages.

## Agent sender

A conforming sender:

- validates every message with a conforming parser (§18) before sending;
- does not send a message that fails validation;
- where the deployment prescribes how identifiers are minted (here UUIDv7, `gzmsg new-id`), does not send a message whose `MESSAGE-ID` or `IN-REPLY-TO` is not one — a malformed identifier is always a composition error, and it degrades quietly: the message reads correctly and the thread cannot be reconstructed.

## Agent runtime

A conforming runtime:

- has one logical `host/instance` identity;
- sends no HELLO or GOODBYE (retired, SPEC §8), and reads presence — who is running — from its deployment (§5);
- treats peer discovery as reconstructable cache;
- keeps model and subagent policy local;
- follows repository-local instructions before acting;
- uses authoritative tools for durable effects.

## Transport adapter

A conforming adapter:

- can associate the address in a valid message's `FROM` with native sender identities (SPEC §5; HELLO is retired, §8);
- keeps native identifiers outside the core payload;
- authenticates/allowlists through transport-native mechanisms;
- can deliver broadcast and directed messages, or documents a bootstrap mechanism;
- prevents automated message loops.

## Non-conformance examples

The following violate the design:

- storing `TELEGRAM_BOT` as a required GZCOORD/1 field;
- routing by `/srv/project/path`;
- interpreting `ROLE` as file ownership;
- acting on a `REQUEST` or `HANDOFF` inside another instance's working copy;
- writing protocol findings into a separate issue database;
- using message state to override GitHub issue/PR state;
- changing an agent address when its model changes;
- quoting a credential, key or token value in a finding — in whole, in part, or as an example — instead of describing its shape and location;
- requiring a central catalog of legal role names in the core protocol — a deployment's own catalogue, applied within that deployment, is the convention §4 permits.
