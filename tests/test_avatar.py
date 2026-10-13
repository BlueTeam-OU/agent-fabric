#!/usr/bin/env python3
"""tools/fabric/avatar.py (agent-fabric ADR-056 rule 7): the stdlib PNG decoder, the half-block drawing, the kitty
graphics escape and the cache of decoded pixels, against PNGs this test builds (a tiny fixture of each accepted type,
each of the five scanline filters, and each way a file is refused).

Each case fails when its guard is removed: every filter type undone right (a decoder that skips Paeth reads a smeared
picture); RGB and RGBA both accepted and nothing else (grey, palette, 16-bit, interlaced refused); a bad CRC, a
truncated file, a missing IEND or IHDR refused; pixel data inflated under the header's bound; the transparent weighted
by alpha; the half blocks' exact colours; the kitty escape's chunks and flags; the cache holding numbers, read back
checked, and used instead of a second decode."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "tests"))
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
import avatar  # noqa: E402


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path: str, data: str | bytes) -> None:
    with open(path, "wb" if isinstance(data, bytes) else "w", **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as fh:
        fh.write(data)


def chunk(kind: bytes, body: bytes, crc: int | None = None) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF if crc is None else crc)


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def filtered(rows: list[bytes], bpp: int, kinds: list[int]) -> bytes:
    """The scanlines with each row filtered by its kind (the encoder side of PNG's filters)."""
    out = bytearray()
    prev = bytes(len(rows[0]))
    for row, kind in zip(rows, kinds):
        out.append(kind)
        for i, x in enumerate(row):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            ref = (0, a, b, (a + b) >> 1, paeth(a, b, c))[kind]
            out.append((x - ref) & 255)
        prev = row
    return bytes(out)


def png(width: int, height: int, rows: list[bytes], *, colour: int = 2, depth: int = 8, interlace: int = 0, kinds: list[int] | None = None,
        raw: bytes | None = None, ihdr: bool = True, iend: bool = True, split: int = 1) -> bytes:
    bpp = {2: 3, 6: 4}.get(colour, 3)
    data = raw if raw is not None else filtered(rows, bpp, kinds or [0] * len(rows))
    packed = zlib.compress(data)
    step = max(1, len(packed) // split)
    idats = b"".join(chunk(b"IDAT", packed[i:i + step]) for i in range(0, len(packed), step))
    head = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, interlace)) if ihdr else b""
    return avatar.PNG_SIGNATURE + head + chunk(b"tEXt", b"Comment\0ignored") + idats + (chunk(b"IEND", b"") if iend else b"")


def picture(width: int, height: int, bpp: int) -> list[bytes]:
    """A picture with different bytes everywhere, so a wrong filter shows."""
    return [bytes((x * 7 + y * 13 + c * 29 + (x * y) % 11) & 255 for x in range(width) for c in range(bpp)) for y in range(height)]


class Decode(unittest.TestCase):
    def test_rgb_and_rgba_decode_to_their_rows_under_every_filter(self):
        for colour, bpp in ((2, 3), (6, 4)):
            rows = picture(9, 7, bpp)
            for kind in range(5):
                with self.subTest(colour=colour, filter=kind):
                    self.assertEqual(avatar.decode(png(9, 7, rows, colour=colour, kinds=[kind] * 7)), (9, 7, bpp, rows))
            with self.subTest(colour=colour, filter="a different one on each row"):
                self.assertEqual(avatar.decode(png(9, 7, rows, colour=colour, kinds=[0, 1, 2, 3, 4, 3, 1])), (9, 7, bpp, rows))

    def test_the_pixel_data_may_be_split_over_several_idat_chunks_and_other_chunks_are_ignored(self):
        rows = picture(8, 8, 3)
        self.assertEqual(avatar.decode(png(8, 8, rows, split=5))[3], rows)

    def test_what_is_not_8_bit_rgb_or_rgba_is_refused(self):
        rows = picture(4, 4, 3)
        for label, data in (("greyscale", png(4, 4, rows, colour=0, raw=bytes(4 * (1 + 4)))),
                            ("palette", png(4, 4, rows, colour=3, raw=bytes(4 * (1 + 4)))),
                            ("grey and alpha", png(4, 4, rows, colour=4, raw=bytes(4 * (1 + 8)))),
                            ("16-bit", png(4, 4, rows, depth=16)),
                            ("interlaced", png(4, 4, rows, interlace=1))):
            with self.subTest(label), self.assertRaises(avatar.Refused):
                avatar.decode(data)

    def test_a_file_that_is_damaged_is_refused_with_one_line(self):
        good = png(4, 4, picture(4, 4, 3))
        flipped = bytearray(good)
        flipped[len(avatar.PNG_SIGNATURE) + 8 + 2] ^= 0xFF                 # a byte inside IHDR: its CRC no longer fits
        for label, data in (("not a PNG", b"GIF89a" + good[6:]), ("empty", b""), ("a bad CRC", bytes(flipped)),
                            ("truncated in a chunk", good[:40]), ("truncated in a header", good[:len(avatar.PNG_SIGNATURE) + 5]),
                            ("no IEND", png(4, 4, picture(4, 4, 3), iend=False)), ("no IHDR first", png(4, 4, picture(4, 4, 3), ihdr=False)),
                            ("a zero size", png(0, 4, [b""] * 4, raw=b"")),
                            ("a size past the cap", png(avatar.MAX_DIM + 1, 1, [b""], raw=b"")),
                            ("pixel data longer than the header says", png(4, 4, [], raw=bytes(4 * (1 + 12) + 1))),
                            ("pixel data shorter than the header says", png(4, 4, [], raw=bytes(4 * (1 + 12) - 1))),
                            ("an unknown filter", png(4, 4, [], raw=(bytes([9]) + bytes(12)) * 4))):
            with self.subTest(label):
                with self.assertRaises(avatar.Refused) as ctx:
                    avatar.decode(data)
                self.assertEqual(len(str(ctx.exception).splitlines()), 1)

    def test_a_small_file_cannot_inflate_past_its_header(self):
        bomb = png(4, 4, [], raw=bytes(50_000_000))                          # compresses to a few kB, claims 4x4
        self.assertLess(len(bomb), 100_000)
        with self.assertRaisesRegex(avatar.Refused, "longer than its header"):
            avatar.decode(bomb)


class Bound(unittest.TestCase):
    def test_a_header_with_more_pixels_than_the_cap_is_refused_before_anything_is_inflated(self):
        side = int(avatar.MAX_PIXELS ** 0.5) + 1
        data = png(side, side, [b""], raw=b"")
        with self.assertRaisesRegex(avatar.Refused, "more than"):
            avatar.decode(data)
        avatar.decode(png(2, 2, picture(2, 2, 3)))                       # and the cap is not a refusal of every picture


class Draw(unittest.TestCase):
    def test_each_cell_is_the_mean_of_the_block_it_covers(self):
        # 40 x 40, left half red, right half blue, then the top band lighter: 2 x 2 source pixels per grid cell
        rows = []
        for y in range(40):
            rows.append(b"".join(bytes((200, 0, 0)) if x < 20 else bytes((0, 0, 100 if y < 20 else 50)) for x in range(40)))
        grid = avatar.cell_grid(40, 40, 3, rows)
        self.assertEqual((len(grid), len(grid[0])), (20, 20))
        self.assertEqual((grid[0][0], grid[0][19], grid[19][19]), ((200, 0, 0), (0, 0, 100), (0, 0, 50)))
        mixed = avatar.cell_grid(2, 1, 3, [bytes((10, 20, 30, 50, 60, 70))], cols=1, prows=1)
        self.assertEqual(mixed, [[(30, 40, 50)]], "a block is averaged, not sampled")

    def test_a_source_smaller_than_the_grid_is_stretched_by_nearest_block(self):
        grid = avatar.cell_grid(1, 1, 3, [bytes((9, 8, 7))])
        self.assertTrue(all(cell == (9, 8, 7) for row in grid for cell in row))

    def test_a_transparent_pixel_counts_as_black_weighted_by_its_alpha(self):
        row = bytes((200, 100, 50, 255, 200, 100, 50, 0))                      # opaque, then invisible
        self.assertEqual(avatar.cell_grid(2, 1, 4, [row], cols=2, prows=1), [[(200, 100, 50), (0, 0, 0)]])
        self.assertEqual(avatar.cell_grid(2, 1, 4, [row], cols=1, prows=1), [[(100, 50, 25)]], "half the block is invisible")

    def test_the_half_blocks_are_the_pixel_above_on_the_foreground_and_the_one_below_on_the_background(self):
        grid = [[(1, 2, 3), (4, 5, 6)], [(7, 8, 9), (10, 11, 12)]]
        self.assertEqual(avatar.half_blocks(grid), ["\x1b[38;2;1;2;3;48;2;7;8;9m▀\x1b[38;2;4;5;6;48;2;10;11;12m▀\x1b[0m"])
        full = avatar.half_blocks([[(0, 0, 0)] * avatar.COLS] * (2 * avatar.ROWS))
        self.assertEqual((len(full), full[0].count("▀")), (avatar.ROWS, avatar.COLS))

    def test_the_only_escapes_in_a_drawing_are_the_colour_sequences_it_generates(self):
        import re
        grid = avatar.cell_grid(*avatar.decode(png(30, 30, picture(30, 30, 3)))[:3], avatar.decode(png(30, 30, picture(30, 30, 3)))[3])
        for line in avatar.half_blocks(grid):
            rest = re.sub(r"\x1b\[(?:38;2;\d+;\d+;\d+;48;2;\d+;\d+;\d+|0)m", "", line)
            self.assertEqual(rest, "▀" * avatar.COLS)


class Kitty(unittest.TestCase):
    def test_the_file_is_transmitted_as_it_is_in_chunks_of_at_most_4096_with_the_flags_herdr_reads(self):
        # noise, not a pattern: how small zlib makes a pattern differs from one build to the next
        noise = [b"".join(hashlib.sha256(bytes([y, i])).digest() for i in range(9)) for y in range(60)]
        data = png(90, 60, [r[:270] for r in noise])
        self.assertGreater(len(base64.b64encode(data)), 3 * avatar.KITTY_CHUNK, "the fixture needs several chunks")
        escape = avatar.kitty_escape(data)
        parts = escape.split("\x1b\\")[:-1]
        self.assertTrue(all(p.startswith("\x1b_G") for p in parts))
        controls = [p[3:].split(";", 1) for p in parts]
        self.assertEqual(controls[0][0], "a=T,f=100,c=20,r=10,q=2,C=1,m=1")
        self.assertTrue(all(c[0] == "m=1" for c in controls[1:-1]) and controls[-1][0] == "m=0")
        self.assertTrue(all(len(c[1]) <= avatar.KITTY_CHUNK for c in controls))
        self.assertEqual(base64.b64decode("".join(c[1] for c in controls)), data, "the PNG's own bytes, nothing re-encoded")

    def test_a_single_chunk_ends_it_at_once(self):
        escape = avatar.kitty_escape(png(2, 2, picture(2, 2, 3)))
        self.assertEqual(escape.count("\x1b_G"), 1)
        self.assertIn(",m=0;", escape)

    def test_what_is_not_a_png_or_is_too_large_is_none_and_the_size_it_covers_is_the_callers(self):
        self.assertIsNone(avatar.kitty_escape(b"GIF89a"))
        self.assertIsNone(avatar.kitty_escape(avatar.PNG_SIGNATURE + bytes(avatar.MAX_FILE)))
        self.assertIn("c=30,r=12,", avatar.kitty_escape(png(2, 2, picture(2, 2, 3)), 30, 12))


class Cache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="avatar-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cache = os.path.join(self.tmp, "cache")
        self.data = png(30, 30, picture(30, 30, 3))
        self.calls = 0

    def decoder(self, data):
        self.calls += 1
        return avatar.decode(data)

    def test_a_file_is_decoded_once_and_the_cache_is_keyed_by_its_sha256_and_holds_numbers_only(self):
        first = avatar.grid_of(self.data, self.cache, self.decoder)
        second = avatar.grid_of(self.data, self.cache, self.decoder)
        self.assertEqual((self.calls, first), (1, second))
        (name,) = os.listdir(self.cache)
        import hashlib
        self.assertEqual(name, f"avatar-{hashlib.sha256(self.data).hexdigest()}.json")
        text = read_text(os.path.join(self.cache, name))
        self.assertNotIn("\x1b", text)
        self.assertEqual(sorted(json.loads(text)), ["cols", "pixels", "rows"])
        self.assertEqual(oct(os.stat(self.cache).st_mode & 0o777), "0o700")
        self.assertNotEqual(avatar.grid_of(png(30, 30, picture(30, 30, 3)[::-1]), self.cache, self.decoder), first)
        self.assertEqual(self.calls, 2, "another file, another decode")

    def test_a_cache_that_is_not_what_it_should_be_is_decoded_again_and_never_trusted(self):
        grid = avatar.grid_of(self.data, self.cache, self.decoder)
        path = os.path.join(self.cache, os.listdir(self.cache)[0])
        good = json.loads(read_text(path))
        for label, doc in (("a pixel out of range", {**good, "pixels": [[999, 0, 0]] + good["pixels"][1:]}),
                           ("too few pixels", {**good, "pixels": good["pixels"][:10]}),
                           ("a string for a pixel", {**good, "pixels": ["\x1b[31m"] + good["pixels"][1:]}),
                           ("a bool for a number", {**good, "pixels": [[True, 0, 0]] + good["pixels"][1:]}),
                           ("other dimensions", {**good, "cols": 5}), ("not an object", [])):
            with self.subTest(label):
                write(path, json.dumps(doc))
                before = self.calls
                self.assertEqual(avatar.grid_of(self.data, self.cache, self.decoder), grid)
                self.assertEqual(self.calls, before + 1)
        write(path, "{not json")
        self.assertEqual(avatar.grid_of(self.data, self.cache, self.decoder), grid)

    def test_a_cache_directory_that_cannot_be_written_costs_a_decode_not_the_avatar(self):
        blocked = os.path.join(self.tmp, "blocked")
        write(blocked, b"")
        self.assertEqual(len(avatar.grid_of(self.data, os.path.join(blocked, "sub"), self.decoder)), 2 * avatar.ROWS)

    def test_a_refused_file_raises_and_leaves_no_cache(self):
        with self.assertRaises(avatar.Refused):
            avatar.grid_of(png(4, 4, picture(4, 4, 3), colour=0, raw=bytes(20)), self.cache)
        self.assertEqual(os.listdir(self.cache) if os.path.isdir(self.cache) else [], [])


class ReadFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="avatar-read-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_only_a_regular_file_of_a_sane_size_is_read(self):
        path = os.path.join(self.tmp, "a.png")
        write(path, b"abc")
        self.assertEqual(avatar.read_file(path), b"abc")
        os.symlink(path, os.path.join(self.tmp, "link.png"))
        os.mkfifo(os.path.join(self.tmp, "fifo.png"))
        os.mkdir(os.path.join(self.tmp, "dir.png"))
        big = os.path.join(self.tmp, "big.png")
        write(big, bytes(avatar.MAX_FILE + 1))
        for name in ("link.png", "fifo.png", "dir.png", "big.png", "absent.png"):
            with self.subTest(name), self.assertRaises(avatar.Refused):
                avatar.read_file(os.path.join(self.tmp, name))


if __name__ == "__main__":
    unittest.main()
