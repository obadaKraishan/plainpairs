"""The Kaggle mirror's cover image, drawn by code (standard library only).

560 by 280 pixels, the size Kaggle asks for: the CLI crops a 560 by 280 header and a centred
280 by 280 thumbnail, so the name and both columns sit inside the centre too. The name is
drawn from a small built-in pixel font; below it, two columns of abstract lines stand for the
two readers: long, dense lines for the prescriber text on the left, shorter, spaced lines with
headings and bullets for the patient text on the right. No word from any label is drawn.

``python -m plainpairs.cover OUT.png`` writes it; the tracked copy is ``kaggle_cover.png``
next to this file, and a test checks that this code draws exactly its pixels.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

WIDTH, HEIGHT = 560, 280
TRACKED = Path(__file__).with_name("kaggle_cover.png")

PAPER = (247, 245, 240)
INK = (31, 41, 55)
RULE = (214, 209, 200)
PRESCRIBER = (124, 131, 142)
PATIENT = (15, 118, 110)
PATIENT_HEAD = (17, 85, 80)

#: 5 by 7 glyphs for the letters of the name.
GLYPHS = {
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "l": ("01100", "00100", "00100", "00100", "00100", "00100", "01110"),
    "a": ("00000", "00000", "01110", "00001", "01111", "10001", "01111"),
    "i": ("00100", "00000", "01100", "00100", "00100", "00100", "01110"),
    "n": ("00000", "00000", "10110", "11001", "10001", "10001", "10001"),
    "r": ("00000", "00000", "10110", "11001", "10000", "10000", "10000"),
    "s": ("00000", "00000", "01111", "10000", "01110", "00001", "11110"),
}
NAME = "PlainPairs"
SCALE = 4

#: Line lengths as shares of the column's width; 0 is a paragraph break.
PRESCRIBER_LINES = (1.0, 0.97, 0.99, 0.94, 0.63, 0, 1.0, 0.96, 0.98, 0.95, 0.71, 0, 1.0, 0.93, 0.58)
#: ("h", share) a heading, ("b", share) a bulleted line, ("", 0) a break.
PATIENT_LINES = (
    ("h", 0.55),
    ("b", 0.72),
    ("b", 0.50),
    ("", 0),
    ("h", 0.46),
    ("b", 0.66),
    ("b", 0.58),
    ("", 0),
    ("h", 0.60),
    ("b", 0.44),
)


def _canvas() -> list[bytearray]:
    return [bytearray(bytes(PAPER) * WIDTH) for _ in range(HEIGHT)]


def _rect(img: list[bytearray], x0: int, y0: int, x1: int, y1: int, rgb: tuple[int, ...]) -> None:
    """Fill the pixels x0 <= x < x1, y0 <= y < y1 (clipped to the canvas)."""
    x0, x1 = max(0, x0), min(WIDTH, x1)
    for y in range(max(0, y0), min(HEIGHT, y1)):
        img[y][3 * x0 : 3 * x1] = bytes(rgb) * (x1 - x0)


def _name(img: list[bytearray], top: int) -> int:
    """Draw the name centred at ``top``; return the y below it."""
    cell = 5 * SCALE
    gap = SCALE
    width = len(NAME) * cell + (len(NAME) - 1) * gap
    x = (WIDTH - width) // 2
    for ch in NAME:
        for r, row in enumerate(GLYPHS[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    px, py = x + c * SCALE, top + r * SCALE
                    _rect(img, px, py, px + SCALE, py + SCALE, INK)
        x += cell + gap
    return top + 7 * SCALE


def draw() -> list[bytearray]:
    """The cover's pixels, row by row (RGB)."""
    img = _canvas()
    below = _name(img, 26)
    _rect(img, 240, below + 12, 320, below + 15, PATIENT)  # a short rule under the name
    top, bottom = below + 34, HEIGHT - 26
    _rect(img, 279, top, 281, bottom, RULE)  # the line between the two readers
    left, right = 44, 262
    y = top
    for share in PRESCRIBER_LINES:
        if share:
            _rect(img, left, y, left + round((right - left) * share), y + 4, PRESCRIBER)
        y += 10
    left, right = 298, 516
    y = top
    for kind, share in PATIENT_LINES:
        if kind == "h":
            _rect(img, left, y, left + round((right - left) * share), y + 8, PATIENT_HEAD)
            y += 20
        elif kind == "b":
            _rect(img, left, y, left + 6, y + 6, PATIENT)
            _rect(img, left + 14, y, left + 14 + round((right - left - 14) * share), y + 6, PATIENT)
            y += 16
        else:
            y += 10
    return img


def png(img: list[bytearray]) -> bytes:
    """An 8-bit RGB PNG of the rows, no filter, zlib level 9."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\x00" + bytes(row) for row in img)
    header = struct.pack(">IIBBBBB", len(img[0]) // 3, len(img), 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def read_png(data: bytes) -> tuple[tuple[int, int], bytes]:
    """The size and the raw scanlines of a PNG this module wrote (for the test)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, size, idat = 8, (0, 0), b""
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos : pos + 4])
        kind, body = data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + n]
        if kind == b"IHDR":
            size = struct.unpack(">II", body[:8])
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    return size, zlib.decompress(idat)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    out = Path(args[0]) if args else TRACKED
    out.write_bytes(png(draw()))
    print(f"Wrote {out} ({WIDTH} x {HEIGHT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
