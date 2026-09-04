"""Configuration: profiles, listener model, and runtime settings.

A *profile* is how hard the document works on you (duration budget, prompt density, repetition
count). A *listener* is what you already know. The two are separate because the same profile
should behave differently for a paper in your own field than for one outside it.

Both are plain YAML so they can be edited without touching code -- see ``profiles/`` and
``listener.example.yaml``.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent.parent


class NumericFidelity(StrEnum):
    """How much numeric precision survives into the audio track (rule NUM-01).

    ``EXACT`` is the default: the listener is a researcher and the numbers are the point.
    Working-memory cost is managed by framing and repetition (NUM-01a) and digit chunking
    (NUM-01b), not by discarding digits.
    """

    EXACT = "exact"
    ROUNDED = "rounded"


class CitationVerbosity(StrEnum):
    SUPPRESS = "suppress"
    ATTRIBUTED = "attributed"


class Expertise(StrEnum):
    NOVICE = "novice"
    FAMILIAR = "familiar"
    EXPERT = "expert"


class SegmentBudget(BaseModel):
    """Segment length bounds in seconds of estimated narration (rule SEG-01)."""

    model_config = ConfigDict(extra="forbid")

    target_min: float = 45.0
    target_max: float = 90.0
    hard_max: float = 120.0


class PauseBudget(BaseModel):
    """Pause durations in seconds (rules PAU-01..03)."""

    model_config = ConfigDict(extra="forbid")

    retrieval_min: float = 3.0
    retrieval_max: float = 6.0
    imagery_min: float = 2.0
    imagery_max: float = 4.0
    segment_boundary: float = 1.2
    section_boundary: float = 2.0


class SpacingPolicy(BaseModel):
    """Within-document spacing of repeated exposures (rules SPC-01, SPC-02)."""

    model_config = ConfigDict(extra="forbid")

    min_gap_minutes: float = 3.0
    interval_ratio: float = 2.5
    repetitions_min: int = 2
    repetitions_max: int = 3


class Profile(BaseModel):
    """A named set of budgets. Loaded from ``profiles/<name>.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""

    # pacing
    wpm: float = 155.0
    duration_multiplier: float = 1.4
    segments: SegmentBudget = Field(default_factory=SegmentBudget)
    pauses: PauseBudget = Field(default_factory=PauseBudget)

    # learning design
    prompts_per_segment: int = 1
    min_prompts_per_section: int = 1
    prequestions_per_document: int = 3
    prequestions_per_section: int = 1
    spacing: SpacingPolicy = Field(default_factory=SpacingPolicy)
    review_block_multiplier: float = 1.0
    max_preload_terms: int = 7
    max_new_terms_per_segment: int = 3
    emphasis_markers_per_section: int = 1

    # verbalization
    numeric_fidelity: NumericFidelity = NumericFidelity.EXACT
    significant_figures: int = 2  # used only when numeric_fidelity is ROUNDED
    speak_statistics_verdict: bool = True
    citations: CitationVerbosity = CitationVerbosity.SUPPRESS

    @field_validator("wpm")
    @classmethod
    def _sane_wpm(cls, v: float) -> float:
        # Comprehension holds to roughly 270 wpm and falls off steeply beyond (KB 2.4).
        if not 80.0 <= v <= 270.0:
            raise ValueError(f"wpm {v} outside the comprehensible range 80-270")
        return v

    def seconds_for(self, text: str) -> float:
        """Estimated narration time for a piece of text (rule DUR-01)."""
        words = len(text.split())
        return 60.0 * words / self.wpm


class Listener(BaseModel):
    """What the listener already knows. Shifts difficulty scores, not structure."""

    model_config = ConfigDict(extra="forbid")

    name: str = "default"
    default_expertise: Expertise = Expertise.FAMILIAR
    expertise: dict[str, Expertise] = Field(default_factory=dict)
    known_terms: list[str] = Field(default_factory=list)
    lexicon: dict[str, str] = Field(default_factory=dict)  # term -> spoken form (rule SYM-03)
    wpm: float | None = None  # overrides the profile

    def expertise_for(self, domain: str | None) -> Expertise:
        if domain is None:
            return self.default_expertise
        return self.expertise.get(domain.lower(), self.default_expertise)

    def knows(self, term: str) -> bool:
        t = term.strip().lower()
        return any(t == k.strip().lower() for k in self.known_terms)


class Settings(BaseSettings):
    """Runtime settings. Environment variables use the ``MIMEM_`` prefix."""

    model_config = SettingsConfigDict(env_prefix="MIMEM_", extra="ignore")

    profiles_dir: Path = REPO_ROOT / "profiles"
    listener_file: Path | None = None
    cache_dir: Path = REPO_ROOT / ".mimem-cache"
    default_profile: str = "study"


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a YAML mapping")
    return data


def load_profile(name_or_path: str | Path, settings: Settings | None = None) -> Profile:
    """Load a profile by name (from ``profiles/``) or by explicit path."""
    settings = settings or Settings()
    path = Path(name_or_path)
    if not path.suffix:
        path = settings.profiles_dir / f"{name_or_path}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in settings.profiles_dir.glob("*.yaml"))
        raise FileNotFoundError(
            f"no profile at {path}; available: {', '.join(available) or 'none'}"
        )
    data = _read_yaml(path)
    data.setdefault("name", path.stem)
    return Profile.model_validate(data)


def load_listener(path: str | Path | None = None, settings: Settings | None = None) -> Listener:
    """Load the listener model, or return the neutral default if none is configured."""
    settings = settings or Settings()
    target = Path(path) if path is not None else settings.listener_file
    if target is None or not Path(target).exists():
        return Listener()
    return Listener.model_validate(_read_yaml(Path(target)))
