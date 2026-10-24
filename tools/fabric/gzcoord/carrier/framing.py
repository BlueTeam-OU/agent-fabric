"""tools/fabric/gzcoord/carrier/framing.py — one GZCoord message as the payloads
the InterWeave data socket carries, and back (ADR-064 §5 rules 7, 8).

CONTRACT (the carrier-to-carrier wire; InterWeave knows none of it, the
payload is opaque to the transport, ADR-0055 decision 3):
  message   media type MEDIA_MESSAGE[;ce=<codec>]; the payload is the
            message text as UTF-8, compressed when it exceeds CEILING.
  chunk     media type MEDIA_CHUNK: one JSON header line, "\\n", then the
            slice. The header names the MESSAGE-ID, the slice's index and
            the count, the codec of the whole, and the sha256 of the
            whole as sent (compressed). A message is chunked only when
            its compressed form still exceeds CEILING.
  receipt   media type MEDIA_RECEIPT: the MESSAGE-ID as UTF-8 text, sent
            by the receiving carrier after its journal append; never a
            GZCoord message.
CEILING is InterWeave's 48 KiB payload ceiling (ADR-0026), which does not
rise for any client. A reassembled message whose digest differs from the
header's is refused, never delivered half-right.
"""
from __future__ import annotations

import hashlib
import json
import zlib
from dataclasses import dataclass

CEILING = 49152
MEDIA_MESSAGE = "application/vnd.agentfabric.gzcoord.v1"
MEDIA_CHUNK = "application/vnd.agentfabric.gzcoord-chunk.v1"
MEDIA_RECEIPT = "application/vnd.agentfabric.gzcoord-receipt.v1"
# A header line is bounded so a hostile chunk cannot make the parser read a
# payload-sized "header"; the slice room is what is left under CEILING.
HEADER_MAX = 512
# A message that needs more chunks than this is refused at the sender: the
# fleet's largest journal row is 58 KB (two chunks at most), and a larger count would let one
# send fill a peer's reassembly table.
MAX_CHUNKS = 16
MAX_TEXT = 4 * 1024 * 1024


class FramingError(Exception):
    """A payload that is not one this carrier sends, or cannot be sent."""


def _deflate(data: bytes) -> bytes:
    return zlib.compress(data, 9)


def _inflate(data: bytes, limit: int) -> bytes:
    d = zlib.decompressobj()
    out = d.decompress(data, limit + 1)
    if len(out) > limit or d.unconsumed_tail or not d.eof:
        raise FramingError("compressed message is truncated or past the size bound")
    return out


# One codec, behind compress/decompress: the codec is between carriers only
# (the daemon never opens a payload), and the pinned interpreter has zlib but
# no brotli (fabric-coordinator, 2026-10-24: ADR-064 rule 8 amended to
# deflate).
CODEC = "deflate"


def compress(data: bytes) -> tuple[str, bytes]:
    return CODEC, _deflate(data)


def decompress(codec: str, data: bytes, limit: int = MAX_TEXT) -> bytes:
    if codec != CODEC:
        raise FramingError(f"unknown content-encoding {codec!r}")
    return _inflate(data, limit)


@dataclass(frozen=True)
class Payload:
    media_type: str
    data: bytes


def encode(message_id: str, text: str) -> list[Payload]:
    """The payloads that carry `text`, in send order."""
    raw = text.encode("utf-8")
    if len(raw) > MAX_TEXT:
        raise FramingError("message is past the size bound")
    if len(raw) <= CEILING:
        return [Payload(MEDIA_MESSAGE, raw)]
    codec, body = compress(raw)
    if len(body) <= CEILING:
        return [Payload(f"{MEDIA_MESSAGE};ce={codec}", body)]
    digest = hashlib.sha256(body).hexdigest()
    slice_room = CEILING - HEADER_MAX - 1
    pieces = [body[i:i + slice_room] for i in range(0, len(body), slice_room)]
    if len(pieces) > MAX_CHUNKS:
        raise FramingError("message needs more chunks than the carrier sends")
    out = []
    for i, piece in enumerate(pieces):
        header = json.dumps({"id": message_id, "i": i, "of": len(pieces),
                             "ce": codec, "sha256": digest}, separators=(",", ":"))
        out.append(Payload(MEDIA_CHUNK, header.encode("ascii") + b"\n" + piece))
    return out


def encoding_of(payloads: list[Payload]) -> str:
    """How `encode` carried a message: plain, compressed or chunked (the
    parity report counts the last two, rule 11)."""
    if len(payloads) > 1 or payloads[0].media_type == MEDIA_CHUNK:
        return "chunked"
    return "compressed" if ";ce=" in payloads[0].media_type else "plain"


def decode_message(media_type: str, data: bytes) -> str:
    base, _, params = media_type.partition(";")
    if base != MEDIA_MESSAGE:
        raise FramingError("not a message payload")
    codec = ""
    if params:
        key, _, value = params.partition("=")
        if key.strip() != "ce" or not value:
            raise FramingError("unknown media type parameter")
        codec = value.strip()
    raw = decompress(codec, data) if codec else data
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise FramingError("message is not UTF-8") from e


def parse_chunk(data: bytes) -> tuple[dict, bytes]:
    head, sep, piece = data.partition(b"\n")
    if not sep or len(head) > HEADER_MAX:
        raise FramingError("chunk has no bounded header")
    try:
        h = json.loads(head)
    except ValueError as e:
        raise FramingError("chunk header is not JSON") from e
    ok = (isinstance(h, dict) and set(h) == {"id", "i", "of", "ce", "sha256"}
          and isinstance(h["id"], str) and isinstance(h["ce"], str)
          and isinstance(h["sha256"], str)
          and type(h["i"]) is int and type(h["of"]) is int
          and 1 < h["of"] <= MAX_CHUNKS and 0 <= h["i"] < h["of"])
    if not ok:
        raise FramingError("chunk header is not well formed")
    return h, piece


class Reassembler:
    """Chunks of messages in flight, held in memory: a restart loses the
    partial ones, and the sender's retry (rule 7) resends every chunk."""

    MAX_IN_FLIGHT = 16

    def __init__(self) -> None:
        self._open: dict[tuple[str, str], dict] = {}

    def add(self, source: str, data: bytes) -> tuple[str, str] | None:
        """Take one chunk from `source`; (message_id, text) when it
        completes a message, else None."""
        h, piece = parse_chunk(data)
        key = (source, h["id"])
        entry = self._open.get(key)
        if entry is None:
            if len(self._open) >= self.MAX_IN_FLIGHT:
                self._open.pop(next(iter(self._open)))
            entry = self._open[key] = {"h": h, "parts": {}}
        elif {k: entry["h"][k] for k in ("of", "ce", "sha256")} != {
                k: h[k] for k in ("of", "ce", "sha256")}:
            del self._open[key]
            raise FramingError("chunks of one message disagree")
        entry["parts"][h["i"]] = piece
        if len(entry["parts"]) < h["of"]:
            return None
        del self._open[key]
        body = b"".join(entry["parts"][i] for i in range(h["of"]))
        if hashlib.sha256(body).hexdigest() != h["sha256"]:
            raise FramingError("reassembled message fails its digest")
        raw = decompress(h["ce"], body)
        try:
            return h["id"], raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise FramingError("message is not UTF-8") from e
