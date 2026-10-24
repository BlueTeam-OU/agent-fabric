"""The second transport's carrier of GZCOORD/1 (agent-fabric ADR-064).

The names other tools use for it are exported here, so that a generic file
refers to the carrier through them and not by the transport's name."""

# The carrier name in a journal row's provenance and in the arrival log, and the
# `via` of a claim (CARRIER-CONTRACT.md §5, §6): a wire value, not a label.
CARRIER_NAME = "interweave"
# What a person reads where a dictionary line has {carrier}: the transport's own spelling.
CARRIER_LABEL = "InterWeave"

