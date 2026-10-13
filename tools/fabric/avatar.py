#!/usr/bin/env python3
"""tools/fabric/avatar.py — an agent's avatar on a terminal (agent-fabric ADR-056 rule 7), for fabric-watch's identity
header. Two ways, chosen by the caller:

  kitty_escape(png)   the PNG file as it is, transmitted by the kitty graphics protocol (direct transmission, PNG
                      f=100, base64 in chunks of 4096, placed over COLS x ROWS cells, cursor left where it was). No
                      decoding: the pane host parses it and shows it on its own terminal.
  half_blocks(grid)   the picture drawn with Unicode upper half blocks (U+2580) in 24-bit colour, COLS columns by
                      ROWS rows of text, from a COLS x 2*ROWS grid of RGB triples that cell_grid(decode(png)) gives.

decode(data) reads a PNG with the standard library only: 8-bit RGB (colour type 2) or RGBA (6), not interlaced, every
chunk's CRC checked, IHDR first and IEND last. Anything else — another colour type or depth, interlacing, a bad CRC, a
truncated file, a size past MAX_DIM, more pixel data than the header allows — is `Refused` with one line, and the
caller shows no avatar. The pixel data is inflated under a bound, so a small file cannot become a large one.

THE GRID IS CACHED, NOT THE ESCAPES. grid_of(path, cache_dir) decodes a file once: the 400 numbers go to
`<cache_dir>/avatar-<sha256 of the file>.json`, and the next call reads them back (checked: 0..255, the right count).
The escape sequences are generated from those numbers at every draw, so no escape is ever read from a file.

Nothing here writes outside cache_dir, runs a command or reads any file but the one named.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import struct
import tempfile
import zlib
from collections.abc import Iterator
from operator import mul

COLS, ROWS = 20, 10
MAX_FILE = 8 << 20
MAX_DIM = 8192
MAX_PIXELS = 1 << 20           # the Python scanline loop costs ~1 s per million pixels: a header past this is refused before inflate
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
KITTY_CHUNK = 4096
UPPER_HALF = "▀"
CHANNELS = {2: 3, 6: 4}


class Refused(Exception):
    """A file that is not an avatar this module draws; the message is one line and names no content."""


def chunks(data: bytes) -> Iterator[tuple[bytes, bytes]]:
    """(type, body) of each chunk, CRC checked, from the signature to IEND; Refused on anything short of that."""
    if not data.startswith(PNG_SIGNATURE):
        raise Refused("not a PNG file")
    pos, first, ended = len(PNG_SIGNATURE), True, False
    while pos < len(data):
        if pos + 8 > len(data):
            raise Refused("truncated PNG (a chunk header)")
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        end = pos + 8 + length + 4
        if end > len(data):
            raise Refused("truncated PNG (a chunk)")
        body = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", data[end - 4:end])
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise Refused("PNG chunk fails its CRC")
        if first and kind != b"IHDR":
            raise Refused("PNG does not begin with IHDR")
        first = False
        yield kind, body
        pos = end
        if kind == b"IEND":
            ended = True
            break
    if not ended:
        raise Refused("PNG has no IEND")


def inflate(compressed: bytes, limit: int) -> bytes:
    d = zlib.decompressobj()
    try:
        out = d.decompress(compressed, limit + 1)
        if d.unconsumed_tail or len(out) > limit:
            raise Refused("PNG pixel data is longer than its header says")
        out += d.flush()
    except zlib.error:
        raise Refused("PNG pixel data does not inflate") from None
    if len(out) != limit:
        raise Refused("PNG pixel data is shorter than its header says")
    return out


def unfilter(raw: bytes, width: int, height: int, bpp: int) -> list[bytes]:
    """The scanlines of `raw` with each row's filter undone (PNG filters 0-4)."""
    stride = width * bpp
    rows: list[bytes] = []
    prev = bytes(stride)
    pos = 0
    for _ in range(height):
        kind = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if kind == 0:
            pass
        elif kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif kind == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif kind == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        else:
            raise Refused("PNG scanline with an unknown filter")
        prev = bytes(line)
        rows.append(prev)
    return rows


def decode(data: bytes) -> tuple[int, int, int, list[bytes]]:
    """(width, height, channels, rows) of an 8-bit RGB or RGBA, non-interlaced PNG; Refused otherwise."""
    header: bytes | None = None
    idat: list[bytes] = []
    for kind, body in chunks(data):
        if kind == b"IHDR":
            header = body
        elif kind == b"IDAT":
            idat.append(body)
    if header is None or len(header) != 13:
        raise Refused("PNG has no usable IHDR")
    width, height, depth, colour, compression, filtering, interlace = struct.unpack(">IIBBBBB", header)
    if not (1 <= width <= MAX_DIM and 1 <= height <= MAX_DIM):
        raise Refused(f"PNG size {width}x{height} is outside 1..{MAX_DIM}")
    if width * height > MAX_PIXELS:
        raise Refused(f"PNG size {width}x{height} is more than {MAX_PIXELS} pixels")
    if depth != 8 or colour not in CHANNELS:
        raise Refused("PNG is not 8-bit RGB or RGBA")
    if compression != 0 or filtering != 0:
        raise Refused("PNG compression or filter method is unknown")
    if interlace != 0:
        raise Refused("PNG is interlaced")
    bpp = CHANNELS[colour]
    raw = inflate(b"".join(idat), height * (1 + width * bpp))
    return width, height, bpp, unfilter(raw, width, height, bpp)


def cell_grid(width: int, height: int, bpp: int, rows: list[bytes], cols: int = COLS, prows: int = 2 * ROWS) -> list[list[tuple[int, int, int]]]:
    """prows x cols RGB triples: each the mean of the source block it covers (a transparent pixel counts as black,
    weighted by its alpha). A source smaller than the grid is stretched by nearest block."""
    xs = [(x * width // cols, max(x * width // cols + 1, (x + 1) * width // cols)) for x in range(cols)]
    ys = [(y * height // prows, max(y * height // prows + 1, (y + 1) * height // prows)) for y in range(prows)]
    grid: list[list[tuple[int, int, int]]] = []
    for y0, y1 in ys:
        sums = [[0, 0, 0, 0] for _ in range(cols)]          # r, g, b (times alpha when there is one), pixel count
        for row in rows[y0:y1]:
            for x, (x0, x1) in enumerate(xs):
                cell = sums[x]
                if bpp == 4:
                    alpha = row[3 + 4 * x0:3 + 4 * x1:4]
                    for c in range(3):
                        cell[c] += sum(map(mul, row[c + 4 * x0:c + 4 * x1:4], alpha))
                else:
                    for c in range(3):
                        cell[c] += sum(row[c + 3 * x0:c + 3 * x1:3])
                cell[3] += x1 - x0
        scale = 255 if bpp == 4 else 1
        grid.append([tuple(min(255, c // (cell[3] * scale)) for c in cell[:3]) for cell in sums])
    return grid


def half_blocks(grid: list[list[tuple[int, int, int]]]) -> list[str]:
    """ROWS strings of COLS upper half blocks: foreground the pixel above, background the one below, in 24-bit colour.
    The only escapes this module makes; every number in them is an int of 0..255 taken from the grid."""
    lines = []
    for r in range(0, len(grid) - 1, 2):
        cells = []
        for top, bottom in zip(grid[r], grid[r + 1]):
            t = [int(v) & 255 for v in top]
            b = [int(v) & 255 for v in bottom]
            cells.append(f"\x1b[38;2;{t[0]};{t[1]};{t[2]};48;2;{b[0]};{b[1]};{b[2]}m{UPPER_HALF}")
        lines.append("".join(cells) + "\x1b[0m")
    return lines


def kitty_escape(png: bytes, cols: int = COLS, rows: int = ROWS) -> str | None:
    """The kitty graphics commands that transmit and place `png` as it is over cols x rows cells, or None when the
    bytes are not a PNG or too large. a=T transmits and displays, f=100 is PNG, q=2 asks for no reply, C=1 leaves the
    cursor where it was (so the text beside the image can be written), m=1 on every chunk but the last. Generated from
    the file's bytes, base64-encoded: no byte of it is text from anywhere."""
    if not png.startswith(PNG_SIGNATURE) or len(png) > MAX_FILE:
        return None
    encoded = base64.standard_b64encode(png).decode("ascii")
    parts = [encoded[i:i + KITTY_CHUNK] for i in range(0, len(encoded), KITTY_CHUNK)]
    out = []
    for i, part in enumerate(parts):
        more = 0 if i == len(parts) - 1 else 1
        control = f"a=T,f=100,c={int(cols)},r={int(rows)},q=2,C=1,m={more}" if i == 0 else f"m={more}"
        out.append(f"\x1b_G{control};{part}\x1b\\")
    return "".join(out)


def read_file(path: str) -> bytes:
    """The file's bytes, opened without following a link, refused unless a regular file of MAX_FILE bytes or fewer."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as e:
        raise Refused(f"cannot open the avatar ({e.strerror or e.errno})") from None
    # Before fdopen: a directory opens read-only and fdopen then raises IsADirectoryError, a traceback in place of a refusal.
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise Refused("the avatar is not a regular file")
    with os.fdopen(fd, "rb") as fh:
        data = fh.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise Refused(f"the avatar is over {MAX_FILE} bytes")
    return data


def grid_of(data: bytes, cache_dir: str, decoder=decode) -> list[list[tuple[int, int, int]]]:
    """The 2*ROWS x COLS grid of the PNG `data`, from the cache when it holds it, else decoded and cached."""
    key = hashlib.sha256(data).hexdigest()
    path = os.path.join(cache_dir, f"avatar-{key}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        flat = doc["pixels"]
        if (doc.get("cols"), doc.get("rows")) == (COLS, 2 * ROWS) and isinstance(flat, list) and len(flat) == COLS * 2 * ROWS \
                and all(isinstance(p, list) and len(p) == 3 and all(type(v) is int and 0 <= v <= 255 for v in p) for p in flat):
            return [[tuple(p) for p in flat[r * COLS:(r + 1) * COLS]] for r in range(2 * ROWS)]
    except (OSError, ValueError, KeyError, TypeError):
        pass                                                  # absent or unusable: decode again
    width, height, bpp, rows = decoder(data)
    grid = cell_grid(width, height, bpp, rows)
    try:
        os.makedirs(cache_dir, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=cache_dir, prefix=".avatar-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"cols": COLS, "rows": 2 * ROWS, "pixels": [list(p) for row in grid for p in row]}, fh)
        os.replace(tmp, path)
    except OSError:
        pass                                                  # a cache that cannot be written costs a decode next time
    return grid
