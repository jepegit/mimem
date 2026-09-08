"""Non-stoichiometric chemical formulas (rule NUM-02).

Every case here came off one review paper, where ``Li3.3SnS3.3Cl0.7`` reached the audio track as
three loose decimals and failed the build three times over one string.

The scope is deliberately narrow, and the tests that pin it narrow are the ones that matter. The
first version expanded *every* formula and turned ``CO2`` into "carbon oxygen two", which nobody
says -- two existing tests caught it. Integer subscripts already work through the ordinary number
pass; it is the decimal point the number verbalizer walks past, because a digit following a
letter is a product name far more often than a quantity.
"""

from __future__ import annotations

import pytest

from mimem.config import Listener, load_profile
from mimem.verbalize import verbalize_text
from mimem.verbalize.formulas import spoken_formula, verbalize_formulas


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("Li3.3SnS3.3Cl0.7", "lithium 3.3 tin sulfur 3.3 chlorine 0.7"),
        ("LiNi0.8Mn0.1Co0.1O2", "lithium nickel 0.8 manganese 0.1 cobalt 0.1 oxygen 2"),
        ("Na0.67MnO2", "sodium 0.67 manganese oxygen 2"),
    ],
)
def test_a_fractional_subscript_is_spoken(formula: str, expected: str) -> None:
    assert spoken_formula(formula) == expected


@pytest.mark.parametrize("formula", ["CO2", "H2O", "LiFePO4", "Fe2O3"])
def test_integer_subscripts_are_left_to_the_number_pass(formula: str) -> None:
    """`CO2` reaches the audio as "CO two" already, and "carbon oxygen two" is worse."""
    assert spoken_formula(formula) is None


@pytest.mark.parametrize("token", ["NMC811", "NGB2", "AI4", "Li", "COVID19", "GPT4"])
def test_things_that_only_look_like_formulas_are_left_alone(token: str) -> None:
    """Every alphabetic group has to be a real element symbol, and there must be two of them."""
    assert spoken_formula(token) is None


@pytest.mark.parametrize(
    "prose",
    [
        "Artificial Intelligence In Chemical Engineering",
        "Computer Vision techniques",
        "We In As A Result found",
        "Section 3.3 covers this",
    ],
)
def test_ordinary_prose_survives(prose: str) -> None:
    assert verbalize_formulas(prose) == prose


def test_the_formula_reaches_the_audio_without_raw_digits() -> None:
    """Rule NUM-02, which is what failed on the real paper."""
    spoken = verbalize_text(
        "a Li3.3SnS3.3Cl0.7 solid electrolyte", load_profile("study"), Listener()
    )
    assert "3.3" not in spoken
    assert "three point three" in spoken
    assert not any(character.isdigit() for character in spoken)


def test_the_subscripts_go_through_the_profile_not_a_second_rulebook() -> None:
    """Left as digits here on purpose, so the profile's numeric fidelity applies to them."""
    assert "3.3" in (spoken_formula("Li3.3SnS3.3Cl0.7") or "")


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("LiNi.5Co.2Mn.3O2", "lithium nickel 0.5 cobalt 0.2 manganese 0.3 oxygen 2"),
        ("LiNi.8Co.1Mn.1O2", "lithium nickel 0.8 cobalt 0.1 manganese 0.1 oxygen 2"),
    ],
)
def test_a_subscript_can_lose_its_leading_zero(formula: str, expected: str) -> None:
    """Typesetters drop it constantly, and one corpus paper has it in its own title.

    `LiNi.5Co.2Mn.3O2` is the NMC-532 cathode. Because it is the title, it recurs in the
    orientation and in every callback -- 71 raw decimals in one programme from one string.
    The zero is put back before the number pass, which says nothing at all for a bare ".5".
    """
    assert spoken_formula(formula) == expected


def test_the_restored_zero_is_spoken() -> None:
    spoken = verbalize_text("a LiNi.5Co.2Mn.3O2 cell", load_profile("study"), Listener())
    assert "zero point five" in spoken
    assert not any(character.isdigit() for character in spoken)
