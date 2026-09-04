"""Build a synthetic two-column paper PDF for the ingestion tests.

Real journal PDFs cannot be committed (licensing) and downloading one at test time makes the
suite non-hermetic. So we build a paper that has the properties we actually need to test, and we
control them exactly:

* full-width title / authors / affiliation / abstract over a two-column body;
* a running head and a page number on every page;
* numbered IMRaD headings;
* a paragraph that breaks across the column boundary mid-sentence;
* hyphenated line breaks of both kinds (join: "electro-lyte"; keep: "in-situ", "Li-ion");
* a figure caption, a display equation, and a reference list.

Run directly to regenerate the committed fixture:

    python tests/fixtures/make_paper_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
MARGIN_L, MARGIN_R = 50.0, 50.0
TOP = PAGE_H - 56.0
BOTTOM = 60.0
GUTTER = 22.0
FULL_W = PAGE_W - MARGIN_L - MARGIN_R
COL_W = (FULL_W - GUTTER) / 2
COL_X = (MARGIN_L, MARGIN_L + COL_W + GUTTER)

BODY_SIZE = 9.3
BODY_LEAD = 11.4
PARA_GAP = 7.0

RUNNING_HEAD = "Journal of Synthetic Electrochemistry 12 (2026) 100042"

# Each body item is (style, lines). Lines are pre-broken on purpose: that is how we control
# where the hyphenated breaks fall.
Body = list[tuple[str, list[str]]]


def _abstract() -> list[str]:
    return [
        "Abstract  Silicon-graphite composite anodes lose capacity faster than graphite alone,",
        "and the usual explanation blames fracture of the active particles. We show instead that",
        "the dominant loss channel is repeated repair of the solid electrolyte interphase after",
        "volume-driven cracking. Cells cycled 500 times at 0.5 C retained 82.1 +/- 1.4 % of their",
        "initial capacity, corresponding to a mean loss of 0.0837 % per cycle (p < 0.001).",
    ]


def _column_body() -> Body:
    return [
        ("h1", ["1. Introduction"]),
        (
            "p",
            [
                "Lithium-ion cells with silicon-bearing anodes",
                "promise higher energy density, but they fade",
                "quickly. The conventional account attributes",
                "this to mechanical failure of the particles",
                "themselves. Careful in-",
                "situ measurements suggest a different picture.",
            ],
        ),
        (
            "p",
            [
                "During the first charge, a small amount of the",
                "electro-",
                "lyte decomposes at the negative electrode and",
                "builds a passivating crust. Once the crust",
                "covers the surface it blocks the reaction that",
                "created it, which is why the process is",
            ],
        ),
        # -- the paragraph above continues in the next column, mid-sentence --
        (
            "p-cont",
            [
                "self-limiting under normal conditions. In a Li-",
                "ion cell with a graphite anode this is the end",
                "of the story.",
            ],
        ),
        ("h1", ["2. Experimental"]),
        (
            "p",
            [
                "Half cells were assembled in an argon-filled",
                "glovebox with an oxygen level below 0.5 ppm.",
                "Electrodes were cycled between 0.05 and 1.50 V",
                "at a rate of 0.5 C using a battery cycler.",
            ],
        ),
        ("h1", ["3. Results and Discussion"]),
        (
            "p",
            [
                "Capacity declined smoothly over 500 cycles",
                "with no abrupt step, which is the signature of",
                "a process that repeats a little every cycle",
                "rather than a single mechanical failure.",
            ],
        ),
        ("eq", ["C(t) = C0 exp(-t / tau)                     (1)"]),
        (
            "cap",
            [
                "Figure 1. Discharge capacity versus cycle number",
                "for silicon-graphite (circles) and graphite",
                "(squares) anodes over 500 cycles at 0.5 C.",
            ],
        ),
        (
            "p",
            [
                "Fitting Eq. 1 to the data gives a time constant",
                "of 612 cycles. The fit is good (R2 = 0.994),",
                "and the residuals show no structure.",
            ],
        ),
        (
            "p",
            [
                "Post-mortem imaging supports the interpretation.",
                "Particles recovered from cycled electrodes were",
                "largely intact, while the surface layer had",
                "grown from roughly 20 nm after formation to",
                "roughly 140 nm after 500 cycles. If fracture of",
                "the particles were the dominant mechanism we",
                "would expect the opposite pattern: fragmented",
                "particles under a thin, stable layer.",
            ],
        ),
        (
            "p",
            [
                "The measured lithium inventory loss accounts for",
                "94 % of the observed capacity fade, leaving",
                "little room for a second mechanism of",
                "comparable size. Two competing explanations,",
                "binder failure and current-collector corrosion,",
                "were ruled out by control experiments in which",
                "each was suppressed independently without",
                "changing the fade rate.",
            ],
        ),
        (
            "p",
            [
                "Three practical consequences follow. First, any",
                "coating that keeps the interphase intact through",
                "a volume change should extend life more than a",
                "coating that merely strengthens the particle.",
                "Second, cycling protocols that reduce the depth",
                "of the volume swing should help, and shallow",
                "cycling did indeed reduce the fade rate to",
                "0.0311 % per cycle in a separate series.",
                "Third, a lithium reservoir in the cell would",
                "postpone rather than prevent the loss.",
            ],
        ),
        ("h1", ["4. Conclusions"]),
        (
            "p",
            [
                "Capacity fade in silicon-graphite anodes is",
                "dominated by lithium consumed in rebuilding",
                "the interphase, not by particle fracture.",
            ],
        ),
        ("h1", ["Acknowledgements"]),
        (
            "p",
            [
                "This work was supported by the Research",
                "Council of Norway under grant 000000. The",
                "authors thank the beamline staff.",
            ],
        ),
        ("h1", ["References"]),
        (
            "ref",
            [
                "[1] E. Peled, J. Electrochem. Soc. 126 (1979)",
                "2047-2051.",
            ],
        ),
        (
            "ref",
            [
                "[2] M. Winter, B. Barnett, K. Xu, Chem. Rev.",
                "118 (2018) 11433-11456.",
            ],
        ),
        (
            "ref",
            [
                "[3] M. N. Obrovac, L. Christensen, Electrochem.",
                "Solid-State Lett. 7 (2004) A93-A96.",
            ],
        ),
    ]


class _Writer:
    def __init__(self, path: Path) -> None:
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.c.setTitle("Interphase repair, not particle fracture, limits silicon anode life")
        self.c.setAuthor("A. Researcher, B. Colleague")
        self.page = 1
        self.col = 0
        self.y = TOP
        self._page_furniture()

    # -- page furniture ---------------------------------------------------------------

    def _page_furniture(self) -> None:
        self.c.setFont("Helvetica", 7.2)
        self.c.drawString(MARGIN_L, PAGE_H - 34.0, RUNNING_HEAD)
        self.c.drawCentredString(PAGE_W / 2, 36.0, str(self.page))

    def new_page(self) -> None:
        self.c.showPage()
        self.page += 1
        self.col = 0
        self.y = TOP
        self._page_furniture()

    # -- full-width front matter ------------------------------------------------------

    def full_lines(
        self, lines: list[str], size: float, lead: float, font: str = "Helvetica"
    ) -> None:
        self.c.setFont(font, size)
        for line in lines:
            self.c.drawString(MARGIN_L, self.y, line)
            self.y -= lead
        self.y -= PARA_GAP

    def start_columns(self) -> None:
        self.column_top = self.y
        self.col = 0

    # -- two-column body --------------------------------------------------------------

    def column_lines(self, lines: list[str], size: float, lead: float, font: str) -> None:
        needed = len(lines) * lead
        if self.y - needed < BOTTOM:
            self._next_column()
        self.c.setFont(font, size)
        for line in lines:
            if self.y < BOTTOM:
                self._next_column()
                self.c.setFont(font, size)
            self.c.drawString(COL_X[self.col], self.y, line)
            self.y -= lead
        self.y -= PARA_GAP

    def _next_column(self) -> None:
        if self.col == 0:
            self.col = 1
            self.y = self.column_top
        else:
            self.new_page()
            self.column_top = TOP
            self.col = 0
            self.y = TOP

    def force_column_break(self) -> None:
        self._next_column()

    def save(self) -> None:
        self.c.save()


def build(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    w = _Writer(path)

    w.full_lines(
        ["Interphase repair, not particle fracture,", "limits silicon anode life"],
        16.0,
        19.0,
        "Helvetica-Bold",
    )
    w.full_lines(["A. Researcher, B. Colleague, C. Third"], 10.0, 12.0)
    w.full_lines(
        ["Institute for Energy Technology, Kjeller, Norway. a.researcher@example.org"],
        7.6,
        9.5,
        "Helvetica-Oblique",
    )
    w.full_lines(_abstract(), 8.6, 10.6)
    w.full_lines(["Keywords: lithium-ion, silicon anode, interphase, capacity fade"], 8.0, 10.0)
    w.start_columns()

    for style, lines in _column_body():
        if style == "h1":
            w.column_lines(lines, 10.6, 13.0, "Helvetica-Bold")
        elif style == "cap":
            w.column_lines(lines, 8.2, 10.0, "Helvetica-Oblique")
        elif style == "eq":
            w.column_lines(lines, 9.6, 13.0, "Helvetica-Oblique")
        elif style == "ref":
            w.column_lines(lines, 8.2, 10.0, "Helvetica")
        elif style == "p-cont":
            # The paragraph before this one must end at a column boundary, mid-sentence.
            w.force_column_break()
            w.column_lines(lines, BODY_SIZE, BODY_LEAD, "Helvetica")
        else:
            w.column_lines(lines, BODY_SIZE, BODY_LEAD, "Helvetica")

    w.save()
    return path


DEFAULT_PATH = Path(__file__).parent / "docs" / "synthetic-paper.pdf"

if __name__ == "__main__":
    print(build(DEFAULT_PATH))
