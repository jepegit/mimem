"""Turn numbers into words (rules NUM-01, NUM-01b, NUM-02, NUM-03).

Two jobs, often confused:

**Normalization** -- ``3.14 mA`` has to become words before it reaches the TTS engine. Neural
engines do some of this internally and unpredictably, and reading a number *wrongly* is the
worst defect this system can produce, so we do it here where it can be tested.

**Framing** -- exact numbers are the default for this project (rule NUM-01), which means the
working-memory cost has to be paid back some other way. Rule NUM-01b is the cheap half: a long
run of digits is chunked with a comma, so "zero point zero eight three seven" is spoken as
"zero point zero eight, three seven" and the listener gets somewhere to breathe.

Written from scratch rather than via a number-to-words library, because what we need is not
"render 1234 in English" but a specific set of *spoken* conventions -- chunking, magnitude
framing, unit attachment, scientific notation as a lecturer would say it -- that any library
would have to be overridden to produce.
"""

from __future__ import annotations

import re
from decimal import Decimal

from mimem.config import NumericFidelity
from mimem.verbalize.units import UNIT_TOKEN, spoken_unit

ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
SCALES = ("", " thousand", " million", " billion", " trillion", " quadrillion")
#: Ordinals are formed from the *last word* of the cardinal, which handles every size:
#: "twenty one" -> "twenty first", "one hundred" -> "one hundredth".
ORDINAL_STEMS = {
    "one": "first",
    "two": "second",
    "three": "third",
    "five": "fifth",
    "eight": "eighth",
    "nine": "ninth",
    "twelve": "twelfth",
}
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

#: Above this many digits after the decimal point, the run is chunked (rule NUM-01b).
CHUNK_THRESHOLD = 3
CHUNK_SIZE = 2

_MINUS = "-−–—"

#: A number immediately before a unit token, meaning the unit belongs to it.
_NUMBER_BEFORE = re.compile(r"\d[\d,.]*\s*$")


def _under_thousand(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        tens, rest = divmod(n, 10)
        return TENS[tens] + (f" {ONES[rest]}" if rest else "")
    hundreds, rest = divmod(n, 100)
    out = f"{ONES[hundreds]} hundred"
    return f"{out} and {_under_thousand(rest)}" if rest else out


def int_to_words(n: int) -> str:
    """``1234`` -> ``one thousand two hundred and thirty four``."""
    if n == 0:
        return "zero"
    negative, n = n < 0, abs(n)
    groups: list[str] = []
    scale = 0
    trailing_small = n % 1000
    while n:
        n, group = divmod(n, 1000)
        if group:
            groups.append(_under_thousand(group) + SCALES[scale])
        scale += 1
    # "one thousand and twenty six", not "one thousand twenty six": the connective goes in
    # when the final group is under a hundred and something precedes it.
    if len(groups) > 1 and 0 < trailing_small < 100:
        groups[0] = f"and {groups[0]}"
    words = " ".join(reversed(groups))
    return f"minus {words}" if negative else words


def digits_to_words(digits: str) -> str:
    """Read digits one at a time, chunked once the run gets long (rule NUM-01b)."""
    words = [ONES[int(d)] for d in digits if d.isdigit()]
    if len(words) <= CHUNK_THRESHOLD:
        return " ".join(words)
    chunks = [words[i : i + CHUNK_SIZE] for i in range(0, len(words), CHUNK_SIZE)]
    return ", ".join(" ".join(chunk) for chunk in chunks)


def ordinal_to_words(n: int) -> str:
    """``23`` -> ``twenty third``; ``20`` -> ``twentieth``; ``100`` -> ``one hundredth``."""
    head, _, last = int_to_words(n).rpartition(" ")
    if last in ORDINAL_STEMS:
        last = ORDINAL_STEMS[last]
    elif last.endswith("y"):
        last = f"{last[:-1]}ieth"
    else:
        last = f"{last}th"
    return f"{head} {last}".strip()


def time_to_words(hour: int, minute: int) -> str:
    """``14:30`` -> ``fourteen thirty``; ``9:05`` -> ``nine oh five``; ``14:00`` -> ``fourteen
    hundred hours``."""
    if minute == 0:
        return f"{int_to_words(hour)} hundred hours"
    if minute < 10:
        return f"{int_to_words(hour)} oh {ONES[minute]}"
    return f"{int_to_words(hour)} {int_to_words(minute)}"


def _round_significant(text: str, digits: int) -> str:
    value = Decimal(text)
    if value == 0:
        return "0"
    return f"{value:.{digits}g}"


def number_to_words(
    text: str,
    *,
    fidelity: NumericFidelity = NumericFidelity.EXACT,
    significant_figures: int = 2,
) -> str:
    """Verbalize a single numeric literal such as ``-1,234.56``."""
    cleaned = text.strip().replace(",", "").replace("−", "-").replace("+", "")
    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("-")
    if not cleaned or not cleaned[0].isdigit():
        return text

    if fidelity is NumericFidelity.ROUNDED:
        cleaned = _round_significant(cleaned, significant_figures)
        if "e" in cleaned or "E" in cleaned:  # rounding may produce exponent form
            mantissa, _, exponent = cleaned.lower().partition("e")
            return _scientific_words(mantissa, exponent, negative=negative)

    whole, _, fraction = cleaned.partition(".")
    words = int_to_words(int(whole or 0))
    if fraction:
        words = f"{words} point {digits_to_words(fraction)}"
    return f"minus {words}" if negative else words


def _scientific_words(mantissa: str, exponent: str, *, negative: bool = False) -> str:
    mantissa_words = number_to_words(mantissa)
    exponent = exponent.strip().replace("−", "-").lstrip("+")
    exp_value = int(exponent)
    exp_words = int_to_words(abs(exp_value))
    power = f"minus {exp_words}" if exp_value < 0 else exp_words
    words = f"{mantissa_words} times ten to the power {power}"
    return f"minus {words}" if negative and not mantissa_words.startswith("minus") else words


def _attach_unit(value_text: str, unit: str | None, words: str) -> str:
    """Append the spoken unit, matching singular or plural to the value (rule NUM-03).

    When the trailing token is *not* a unit it is re-emitted unchanged. That matters: the unit
    pattern cannot tell "350 mAh" from "350 cells" before looking the symbol up, and dropping
    the word instead of putting it back deletes source text -- "0.05 and 1.50 V" lost its "and"
    and its "1" that way.
    """
    if not unit:
        return words
    try:
        plural = Decimal(value_text.replace(",", "").replace("−", "-")) != 1
    except Exception:
        plural = True
    spoken = spoken_unit(unit, plural=plural)
    return f"{words} {spoken if spoken else unit}"


class NumberVerbalizer:
    """Rewrites every numeric construction in a piece of text into words."""

    def __init__(
        self,
        *,
        fidelity: NumericFidelity = NumericFidelity.EXACT,
        significant_figures: int = 2,
    ) -> None:
        self.fidelity = fidelity
        self.significant_figures = significant_figures
        num = r"[-−+]?\d[\d,]*(?:\.\d+)?"
        unit = rf"(?:\s*(?P<u{{n}}>{UNIT_TOKEN.pattern}))?"
        self._passes: list[tuple[re.Pattern[str], str]] = [
            (re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b"), "date"),
            (re.compile(r"\b(?P<h>\d{1,2}):(?P<mi>\d{2})(?::(?P<s>\d{2}))?\b"), "time"),
            (
                re.compile(
                    rf"(?P<mant>{num})\s*(?:[eE](?P<exp1>[-−+]?\d+)"
                    rf"|[×x·]\s*10\s*\^?\s*(?P<exp2>[-−]?\s*\d+))" + unit.format(n="1")
                ),
                "scientific",
            ),
            (
                re.compile(rf"(?P<a>{num})\s*(?:±|\+/[-−])\s*(?P<b>{num})" + unit.format(n="2")),
                "plusminus",
            ),
            # A dash between two numbers is a range. Requiring a digit on *both* sides is what
            # keeps "COVID-19" and "4680-cell" intact: neither has a digit before the dash.
            (
                re.compile(
                    rf"(?<![\w.])(?P<lo>\d[\d,]*(?:\.\d+)?)\s*[{_MINUS}]\s*"
                    rf"(?P<hi>\d[\d,]*(?:\.\d+)?)" + unit.format(n="3")
                ),
                "range",
            ),
            (re.compile(r"(?<![\w.])(?P<ord>\d+)(?:st|nd|rd|th)\b"), "ordinal"),
            # Digits welded to letters name a thing rather than count one: NMC811 is a cathode,
            # R2 a metric, H2O a molecule. Read them digit by digit -- "N M C eight hundred and
            # eleven" would be a different object entirely. The whole token is captured so the
            # handler can check it against the unit lexicon first, because "cm2" is an exponent
            # and belongs to the number that precedes it.
            (
                # The trailing decimal is part of the name, not a number after it. "AM1.5" is
                # the standard solar spectrum, and the pattern used to stop at "AM1" and then
                # refuse the match because a decimal followed -- so nothing claimed the token
                # at all and "1.5" reached the audio as a bare number. The plain pass could not
                # take it either: it will not start on a digit that follows a letter.
                re.compile(
                    r"(?<![\w.])(?P<token>(?=\w*[A-Za-z])(?=\w*\d)[A-Za-z0-9]+(?:\.\d+)?)"
                    r"(?!\w)(?!\.\d)"
                ),
                "designation",
            ),
            # "2.3.1" is a section number, a version or a clause reference -- never a decimal.
            # The plain pass reads only one decimal group, so it said "two point three" and
            # walked away from ".1", which then reached the audio track as a digit. Matched
            # before "plain" so the whole run is claimed at once; two dots minimum, because one
            # dot is an ordinary number and belongs to the pass below.
            (
                re.compile(r"(?<![\w.])(?P<levels>\d+(?:\.\d+){2,})(?!\d)(?!\.\d)"),
                "levelled",
            ),
            (re.compile(rf"(?<![\w.])(?P<v>{num})" + unit.format(n="4")), "plain"),
        ]

    # -- per-pattern handlers ------------------------------------------------------------

    def _words(self, text: str) -> str:
        return number_to_words(
            text, fidelity=self.fidelity, significant_figures=self.significant_figures
        )

    def _handle(self, kind: str, m: re.Match[str]) -> str:
        if kind == "date":
            day, month, year = int(m["d"]), int(m["m"]), int(m["y"])
            month_name = MONTHS[month - 1] if 1 <= month <= 12 else int_to_words(month)
            return f"the {ordinal_to_words(day)} of {month_name} {int_to_words(year)}"
        if kind == "time":
            return time_to_words(int(m["h"]), int(m["mi"]))
        if kind == "scientific":
            exponent = m["exp1"] or (m["exp2"] or "").replace(" ", "")
            words = _scientific_words(m["mant"], exponent)
            return _attach_unit("2", m.group("u1"), words)
        if kind == "plusminus":
            words = f"{self._words(m['a'])} plus or minus {self._words(m['b'])}"
            return _attach_unit(m["b"], m.group("u2"), words)
        if kind == "range":
            words = f"{self._words(m['lo'])} to {self._words(m['hi'])}"
            return _attach_unit(m["hi"], m.group("u3"), words)
        if kind == "ordinal":
            return ordinal_to_words(int(m["ord"]))
        if kind == "levelled":
            return " point ".join(int_to_words(int(p)) for p in m["levels"].split("."))
        if kind == "designation":
            token = m["token"]
            unit = spoken_unit(token)
            if unit is not None:
                # "5 cm2" -- leave it for the plain pass, which attaches it to its number.
                # "mAh cm2" with nothing in front is a table fragment: no number is coming, so
                # speak the unit here or its digits reach the engine.
                if _NUMBER_BEFORE.search(m.string[: m.start()]):
                    return token
                return unit
            spoken = re.sub(r"\d+", lambda d: f" {digits_to_words(d.group(0))} ", token)
            return re.sub(r"\s*\.\s*(?=\w)", " point ", spoken).strip()
        words = self._words(m["v"])
        return _attach_unit(m["v"], m.group("u4"), words)

    def __call__(self, text: str) -> str:
        for pattern, kind in self._passes:
            text = pattern.sub(lambda m, k=kind: self._handle(k, m), text)  # type: ignore[misc]
        return text


def verbalize_numbers(
    text: str,
    *,
    fidelity: NumericFidelity = NumericFidelity.EXACT,
    significant_figures: int = 2,
) -> str:
    """Convenience wrapper around :class:`NumberVerbalizer`."""
    return NumberVerbalizer(fidelity=fidelity, significant_figures=significant_figures)(text)
