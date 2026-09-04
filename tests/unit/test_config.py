from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mimem.config import (
    Expertise,
    Listener,
    NumericFidelity,
    Profile,
    Settings,
    load_listener,
    load_profile,
)

PROFILE_NAMES = ("skim", "study", "drill")


@pytest.mark.parametrize("name", PROFILE_NAMES)
def test_shipped_profiles_load(name: str) -> None:
    p = load_profile(name)
    assert p.name == name
    assert p.segments.target_min < p.segments.target_max <= p.segments.hard_max


@pytest.mark.parametrize("name", PROFILE_NAMES)
def test_numeric_fidelity_defaults_to_exact(name: str) -> None:
    """Rule NUM-01: the listener is a researcher; the numbers are the point."""
    assert load_profile(name).numeric_fidelity is NumericFidelity.EXACT


def test_profile_rejects_an_incomprehensible_speech_rate() -> None:
    # KB 2.4: comprehension collapses beyond ~270 wpm.
    with pytest.raises(ValidationError):
        Profile(name="silly", wpm=400)


def test_seconds_for_uses_the_profile_rate() -> None:
    p = Profile(name="t", wpm=150)
    assert p.seconds_for(" ".join(["word"] * 150)) == pytest.approx(60.0)


def test_unknown_profile_lists_the_available_ones() -> None:
    with pytest.raises(FileNotFoundError, match="study"):
        load_profile("does-not-exist")


def test_profile_rejects_unknown_keys(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: bad\nwpm: 150\ntypo_here: 3\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_profile(bad)


def test_listener_defaults_are_neutral() -> None:
    listener = Listener()
    assert listener.expertise_for("anything") is Expertise.FAMILIAR
    assert not listener.knows("electrolyte")


def test_listener_expertise_and_known_terms(tmp_path: Path) -> None:
    path = tmp_path / "listener.yaml"
    path.write_text(
        "name: t\nexpertise:\n  electrochemistry: expert\nknown_terms:\n  - Electrolyte\n",
        encoding="utf-8",
    )
    listener = load_listener(path)
    assert listener.expertise_for("Electrochemistry") is Expertise.EXPERT
    assert listener.expertise_for("botany") is Expertise.FAMILIAR
    assert listener.knows("electrolyte")  # matching is case-insensitive


def test_missing_listener_file_falls_back_to_the_default() -> None:
    assert load_listener(Path("no-such-file.yaml")).name == "default"


def test_settings_point_at_the_repo_profiles() -> None:
    assert (Settings().profiles_dir / "study.yaml").exists()
