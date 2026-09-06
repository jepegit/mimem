"""The extension icon: the shape of a programme, at 256 pixels.

Drawn rather than committed as a binary blob nobody can diff, and drawn from the same palette as
the README illustrations so the thing in the extensions list looks like the thing on the
repository page.

The figure is the design in one glyph: a straight line running left to right, which is what
listening is, and three arcs carrying an idea forward over it at growing intervals, which is what
mimem adds. The copper is the accent used everywhere else for "what mimem put there".

Run it with ``uv run python packaging/make_icon.py``.
"""

from __future__ import annotations

import math
from pathlib import Path

OUT = Path(__file__).resolve().parent / "icon.png"

SIZE = 256
BG = (250, 247, 242)
INK = (28, 26, 23)
COPPER = (180, 84, 31)
FAINT = (190, 182, 172)


def _draw(pixels: list[list[tuple[int, int, int]]]) -> None:
    """Paint the glyph. Plain arithmetic on a pixel grid: no imaging library is required."""
    baseline = SIZE * 0.66
    left, right = SIZE * 0.12, SIZE * 0.88

    # The line: solid where the listener is, fading behind them (what audio does to what you
    # have already heard).
    for x in range(int(left), int(right)):
        t = (x - left) / (right - left)
        colour = _mix(FAINT, INK, min(1.0, t * 1.8))
        for dy in (-1, 0, 1):
            _put(pixels, x, int(baseline) + dy, colour)

    # Three returns of one idea, at growing intervals: the spacing effect, drawn.
    starts = (0.16, 0.34, 0.60)
    ends = (0.34, 0.60, 0.92)
    for start, end in zip(starts, ends, strict=True):
        x0, x1 = left + (right - left) * start, left + (right - left) * end
        height = (x1 - x0) * 0.62
        steps = max(64, int((x1 - x0) * 6))
        for i in range(steps + 1):
            t = i / steps
            x = x0 + (x1 - x0) * t
            y = baseline - math.sin(math.pi * t) * height
            for dx, dy in ((0, 0), (1, 0), (0, 1)):
                _put(pixels, int(x) + dx, int(y) + dy, COPPER)

    # Where the idea lands each time.
    for at in (0.16, 0.34, 0.60, 0.92):
        cx = left + (right - left) * at
        _disc(pixels, cx, baseline, 5.0, COPPER)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _put(
    pixels: list[list[tuple[int, int, int]]], x: int, y: int, colour: tuple[int, int, int]
) -> None:
    if 0 <= x < SIZE and 0 <= y < SIZE:
        pixels[y][x] = colour


def _disc(
    pixels: list[list[tuple[int, int, int]]],
    cx: float,
    cy: float,
    radius: float,
    colour: tuple[int, int, int],
) -> None:
    for y in range(int(cy - radius) - 1, int(cy + radius) + 2):
        for x in range(int(cx - radius) - 1, int(cx + radius) + 2):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius**2:
                _put(pixels, x, y, colour)


def _png(pixels: list[list[tuple[int, int, int]]]) -> bytes:
    """A minimal PNG encoder, so the build depends on nothing that is not already here."""
    import struct
    import zlib

    raw = b"".join(
        b"\x00" + b"".join(bytes(pixel) for pixel in row)  # filter byte 0 per scanline
        for row in pixels
    )

    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)  # 8-bit truecolour
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    pixels = [[BG for _ in range(SIZE)] for _ in range(SIZE)]
    _draw(pixels)
    OUT.write_bytes(_png(pixels))
    print(f"wrote {OUT.name} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
