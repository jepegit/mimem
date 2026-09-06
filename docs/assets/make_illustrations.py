"""Generate the README and documentation illustrations, light and dark.

Two variants of each drawing, because GitHub picks between them with `<picture>` and
`prefers-color-scheme`, and an SVG referenced through `<img>` cannot see the page's theme any
other way. Generating both from one script keeps the palette in one place: the alternative is
two nearly identical files that drift the first time somebody adjusts a colour.

Run it after changing anything here:

    uv run python docs/assets/make_illustrations.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

OUT = Path(__file__).parent

#: Two system font stacks. No webfonts: an SVG loaded through `<img>` cannot fetch one, and a
#: silent fallback to Times is worse than choosing the fallback deliberately.
SERIF = "Georgia, 'Iowan Old Style', 'Palatino Linotype', serif"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace"


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    ink: str  # primary text
    muted: str  # secondary text and rules
    faint: str  # the things that are fading away
    copper: str  # the accent: what mimem adds
    copper_soft: str  # fills behind the accent
    panel: str  # card backgrounds


LIGHT = Palette(
    name="light",
    bg="#faf7f2",
    ink="#1c1a17",
    muted="#6b635a",
    faint="#c8c0b5",
    copper="#b4541f",
    copper_soft="#f2e2d6",
    panel="#f3ece3",
)

DARK = Palette(
    name="dark",
    bg="#0d0d11",
    ink="#e8e6e3",
    muted="#9a938a",
    faint="#3a3730",
    copper="#d97b3c",
    copper_soft="#2a1d14",
    panel="#17171d",
)


def _text(
    x: float,
    y: float,
    body: str,
    *,
    size: float = 15,
    fill: str,
    family: str = SANS,
    weight: str = "400",
    anchor: str = "start",
    style: str = "normal",
    spacing: str = "0",
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'font-style="{style}" letter-spacing="{spacing}" fill="{fill}" text-anchor="{anchor}">'
        f"{body}</text>"
    )


def _wrap(width: int, height: int, palette: Palette, body: str, title: str, desc: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" \
width="{width}" height="{height}" role="img" aria-labelledby="t d">
<title id="t">{title}</title>
<desc id="d">{desc}</desc>
<rect width="{width}" height="{height}" fill="{palette.bg}"/>
{body}
</svg>
"""


# -- 1. the hero -------------------------------------------------------------------------------


def hero(p: Palette) -> str:
    """A page of text becoming a programme: dense bars giving way to a shaped waveform."""
    parts: list[str] = []

    # The page: rows of text, tight and undifferentiated, the way a paper meets an engine.
    x0, y0 = 60, 158
    for row in range(7):
        y = y0 + row * 15
        width = [220, 236, 228, 240, 210, 234, 150][row]
        parts.append(
            f'<rect x="{x0}" y="{y}" width="{width}" height="5" rx="2.5" fill="{p.faint}"/>'
        )
    parts.append(
        f'<rect x="{x0 - 18}" y="{y0 - 26}" width="292" height="152" rx="6" fill="none" '
        f'stroke="{p.faint}" stroke-width="1.5"/>'
    )
    parts.append(_text(x0 - 18, y0 - 40, "a paper", size=13, fill=p.muted, spacing="0.08em"))

    # The arrow across the middle.
    parts.append(
        f'<path d="M 372 208 L 436 208" stroke="{p.copper}" stroke-width="2" fill="none" '
        f'marker-end="url(#a-{p.name})"/>'
    )

    # The programme: a waveform with structure -- loud stretches, deliberate gaps, and two
    # copper marks where a question and its silence sit.
    bars = [
        14, 22, 30, 26, 18, 28, 36, 30, 20, 26, 0, 0, 0, 34, 40, 30, 22, 28, 18, 24,
        0, 0, 0, 0, 20, 30, 38, 32, 24, 30, 22, 16, 26, 34, 28, 18,
    ]  # fmt: skip
    bx = 470
    for i, h in enumerate(bars):
        if h == 0:
            continue
        x = bx + i * 11
        gap_ahead = bars[i + 1] == 0 if i + 1 < len(bars) else False
        colour = p.copper if gap_ahead else p.ink
        parts.append(
            f'<rect x="{x}" y="{208 - h / 2}" width="5" height="{h}" rx="2.5" fill="{colour}"/>'
        )

    # The silences, named.
    for i, label in ((10, "a question"), (20, "and the time to answer it")):
        gx = bx + i * 11 + 11
        parts.append(
            f'<path d="M {gx - 6} 240 L {gx - 6} 248 L {gx + 26} 248 L {gx + 26} 240" '
            f'fill="none" stroke="{p.copper}" stroke-width="1.2"/>'
        )
        parts.append(
            _text(gx + 10, 264, label, size=12, fill=p.copper, anchor="middle", family=SANS)
        )

    parts.append(_text(bx - 4, y0 - 40, "a programme", size=13, fill=p.muted, spacing="0.08em"))

    # Wordmark and tagline, stacked: at forty-two points the wordmark is wider than any guess
    # about where to start the tagline beside it, which the first version got wrong.
    parts.append(_text(60, 64, "mimem", size=44, fill=p.ink, family=SERIF, weight="700"))
    parts.append(
        _text(
            62,
            96,
            "turn a paper into audio you actually remember",
            size=18,
            fill=p.muted,
            family=SERIF,
            style="italic",
        )
    )

    defs = (
        f'<defs><marker id="a-{p.name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        f'markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{p.copper}"/>'
        f"</marker></defs>"
    )
    return _wrap(
        900,
        300,
        p,
        defs + "\n".join(parts),
        "mimem",
        "A dense page of text on the left, an arrow, and on the right a waveform with "
        "deliberate silences marked in copper: a question, and the time to answer it.",
    )


# -- 2. the argument ---------------------------------------------------------------------------


def lanes(p: Palette) -> str:
    """Reading loops back. Listening cannot. So the text loops forward instead."""
    parts: list[str] = []
    left = 150
    right = 858
    lane_label_x = 36

    def lane(y: float, name: str, sub: str) -> None:
        parts.append(_text(lane_label_x, y - 4, name, size=17, fill=p.ink, weight="600"))
        parts.append(_text(lane_label_x, y + 16, sub, size=12.5, fill=p.muted))

    parts.append(
        _text(
            36,
            42,
            "Three ways through the same paragraph",
            size=20,
            fill=p.ink,
            family=SERIF,
            weight="700",
        )
    )

    defs = [
        f'<marker id="h-{p.name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" '
        f'markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{p.muted}"/></marker>',
        f'<marker id="c-{p.name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" '
        f'markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{p.copper}"/></marker>',
        f'<marker id="f-{p.name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" '
        f'markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{p.faint}"/></marker>',
    ]

    # -- reading: the line runs forward, and you keep going back over it.
    y = 108
    lane(y, "Reading", "you control the rate")
    parts.append(
        f'<line x1="{left}" y1="{y}" x2="{right}" y2="{y}" stroke="{p.muted}" stroke-width="2" '
        f'marker-end="url(#h-{p.name})"/>'
    )
    for start, end, label in (
        (300, 210, "re-read"),
        (520, 330, "jump back"),
        (760, 690, "picture it"),
    ):
        mid = (start + end) / 2
        parts.append(
            f'<path d="M {start} {y - 4} C {mid} {y - 46}, {mid} {y - 46}, {end} {y - 4}" '
            f'fill="none" stroke="{p.muted}" stroke-width="1.6" marker-end="url(#h-{p.name})"/>'
        )
        parts.append(_text(mid, y - 34, label, size=12, fill=p.muted, anchor="middle"))

    # -- listening: the same line, and everything behind the playhead is gone.
    y = 232
    lane(y, "Listening", "each word gone as it is spoken")
    parts.append(
        f'<line x1="{left}" y1="{y}" x2="{right}" y2="{y}" stroke="{p.muted}" stroke-width="2" '
        f'marker-end="url(#h-{p.name})"/>'
    )
    for i in range(9):
        x = left + 24 + i * 34
        parts.append(
            f'<rect x="{x}" y="{y - 20}" width="22" height="4" rx="2" fill="{p.faint}" '
            f'opacity="{0.25 + i * 0.07:.2f}"/>'
        )
    parts.append(
        f'<path d="M {left + 340} {y - 34} L {left + 250} {y - 34}" fill="none" '
        f'stroke="{p.faint}" stroke-width="1.4" marker-end="url(#f-{p.name})" '
        f'stroke-dasharray="3 3"/>'
    )
    parts.append(_text(left + 348, y - 30, "no way back", size=12, fill=p.faint, style="italic"))

    # -- mimem: the same line, with the loops built into it, pointing forward.
    y = 356
    lane(y, "mimem", "the loops are built into the text")
    parts.append(
        f'<line x1="{left}" y1="{y}" x2="{right}" y2="{y}" stroke="{p.ink}" stroke-width="2" '
        f'marker-end="url(#c-{p.name})"/>'
    )

    # a question, and the silence after it
    qx = 350
    parts.append(f'<circle cx="{qx}" cy="{y}" r="13" fill="{p.copper_soft}" stroke="{p.copper}"/>')
    parts.append(
        _text(qx, y + 5, "?", size=15, fill=p.copper, anchor="middle", weight="700", family=SERIF)
    )
    parts.append(
        f'<rect x="{qx + 15}" y="{y - 5}" width="46" height="10" rx="5" fill="{p.copper_soft}" '
        f'stroke="{p.copper}" stroke-dasharray="3 3"/>'
    )
    parts.append(_text(qx + 38, y + 34, "pause", size=12, fill=p.copper, anchor="middle"))

    # a concrete image. Further right than the other lanes' furniture because this lane's
    # caption is the longest of the three and was running underneath it.
    ix = 250
    parts.append(
        f'<rect x="{ix - 11}" y="{y - 11}" width="22" height="22" rx="4" fill="{p.copper_soft}" '
        f'stroke="{p.copper}"/>'
    )
    parts.append(f'<circle cx="{ix - 3}" cy="{y - 3}" r="3" fill="{p.copper}"/>')
    parts.append(
        f'<path d="M {ix - 8} {y + 7} L {ix - 1} {y - 1} L {ix + 8} {y + 7} Z" fill="{p.copper}"/>'
    )
    parts.append(_text(ix, y + 34, "a picture", size=12, fill=p.copper, anchor="middle"))

    # the callbacks: forward arcs at growing intervals
    for start, end in ((480, 590), (590, 800)):
        mid = (start + end) / 2
        parts.append(
            f'<path d="M {start} {y - 6} C {mid} {y - 58}, {mid} {y - 58}, {end} {y - 6}" '
            f'fill="none" stroke="{p.copper}" stroke-width="1.8" marker-end="url(#c-{p.name})"/>'
        )
    parts.append(
        _text(
            640,
            y - 52,
            "it comes back, further apart each time",
            size=12,
            fill=p.copper,
            anchor="middle",
        )
    )

    parts.append(
        _text(
            36,
            432,
            "You cannot loop back, so the text loops forward.",
            size=17,
            fill=p.ink,
            family=SERIF,
            style="italic",
        )
    )

    return _wrap(
        900,
        462,
        p,
        "<defs>" + "".join(defs) + "</defs>" + "\n".join(parts),
        "Three ways through the same paragraph",
        "Reading is a line with arrows looping backwards to re-read, jump back and picture "
        "something. Listening is the same line with the words behind the playhead fading away "
        "and no way back. mimem is the same line with a concrete image, a question followed by "
        "a pause, and forward arcs bringing an idea back at growing intervals. The caption "
        "reads: you cannot loop back, so the text loops forward.",
    )


# -- 3. the anatomy of a programme ---------------------------------------------------------------


def anatomy(p: Palette) -> str:
    """What comes out: a timeline of the parts, in the order you hear them."""
    parts: list[str] = []
    parts.append(
        _text(
            36,
            42,
            "What comes out, in the order you hear it",
            size=20,
            fill=p.ink,
            family=SERIF,
            weight="700",
        )
    )

    # Widths sum to 780, which with four twelve-pixel gaps is the 828 between the margins.
    blocks = [
        ("Orientation", "what this is, and\nhow long it takes", 140),
        ("Questions", "two to four, to hold\non to. Not answered yet", 152),
        ("Terms", "at most seven,\none line each", 108),
        ("The paper", "in segments of 45 to 90 seconds,\neach ending on a question", 232),
        ("Review", "every section's question,\nshuffled together", 148),
    ]

    x = 36
    y = 92
    for i, (title, sub, width) in enumerate(blocks):
        accent = i in (1, 4)
        parts.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="96" rx="6" '
            f'fill="{p.copper_soft if accent else p.panel}" '
            f'stroke="{p.copper if accent else p.faint}" stroke-width="1.4"/>'
        )
        parts.append(
            _text(
                x + 14,
                y + 30,
                title,
                size=15,
                fill=p.copper if accent else p.ink,
                weight="600",
            )
        )
        for j, line in enumerate(sub.split("\n")):
            parts.append(_text(x + 14, y + 52 + j * 16, line, size=12, fill=p.muted))
        x += width + 12

    # The clock underneath, with the callbacks landing on it.
    ty = 236
    parts.append(
        f'<line x1="36" y1="{ty}" x2="864" y2="{ty}" stroke="{p.faint}" stroke-width="1.5"/>'
    )
    for i in range(9):
        tick = 36 + i * 103.5
        parts.append(
            f'<line x1="{tick}" y1="{ty - 4}" x2="{tick}" y2="{ty + 4}" stroke="{p.faint}" '
            f'stroke-width="1.5"/>'
        )
    parts.append(_text(36, ty + 22, "0 min", size=11.5, fill=p.muted, family=MONO))
    parts.append(_text(864, ty + 22, "end", size=11.5, fill=p.muted, family=MONO, anchor="end"))

    # One concept's life: first met, then three re-exposures at growing gaps.
    life = [(190, "first met"), (330, "again"), (530, "and again"), (770, "in the review")]
    for i, (cx, label) in enumerate(life):
        parts.append(f'<circle cx="{cx}" cy="{ty}" r="6" fill="{p.copper}"/>')
        parts.append(_text(cx, ty + 40, label, size=11.5, fill=p.copper, anchor="middle"))
        if i:
            prev = life[i - 1][0]
            mid = (prev + cx) / 2
            parts.append(
                f'<path d="M {prev} {ty - 8} C {mid} {ty - 46}, {mid} {ty - 46}, {cx} {ty - 8}" '
                f'fill="none" stroke="{p.copper}" stroke-width="1.5" opacity="0.75"/>'
            )

    parts.append(
        _text(
            36,
            322,
            "One idea, four times, at growing intervals - which is the largest effect in the literature",
            size=13,
            fill=p.muted,
            style="italic",
            family=SERIF,
        )
    )

    return _wrap(
        900,
        344,
        p,
        "\n".join(parts),
        "What comes out, in the order you hear it",
        "Five blocks along a timeline: an orientation, two to four questions to hold on to, at "
        "most seven terms, the paper in segments of 45 to 90 seconds each ending on a question, "
        "and a review that shuffles every section's question together. Below, a clock shows one "
        "concept being met and then brought back three times at growing intervals.",
    )


def main() -> None:
    drawings = {"hero": hero, "lanes": lanes, "anatomy": anatomy}
    for name, draw in drawings.items():
        for palette in (LIGHT, DARK):
            path = OUT / f"{name}-{palette.name}.svg"
            path.write_text(draw(palette), encoding="utf-8")
            print(f"wrote {path.relative_to(OUT.parent.parent)}")


if __name__ == "__main__":
    main()
