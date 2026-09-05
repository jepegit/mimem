"""Stage 8: the four files.

One script, four views of it, and the differences between them are the point.

``audio.md`` is what the engine reads and nothing else: no numbers, no brackets, no markup, no
page references, no citations. ``study.md`` is the same programme with everything the audio track
had to leave behind -- the exact source sentence behind every beat, its page, the numbers before
verbalization (rule ``NUM-06``), and a locator for every claim (rule ``GRD-04``). The knowledge
base is explicit that these should not be the same text (§4.6): a written companion that is a
transcript of the audio is a worse document than either.

``cards.json`` is the retrieval pool, the seed for part two. ``manifest.json`` is the audit
trail: every concept with its scores and its exposure log, the spacing hand-off, everything the
budget dropped, and one chunk per beat so that part two can re-synthesise only what changed
(rule ``TTS-03``).

Pauses live in the manifest, not in the audio text. A break marker inside ``audio.md`` would be
either unspeakable characters (``TTS-01``) or words the engine would read aloud; the durations
belong in the chunk list, where the engine adapter (``TTS-05``) can turn them into whatever that
engine understands. What the *listener* gets in the audio track is the spoken cue -- "take a few
seconds" -- which works even on an engine that ignores breaks entirely.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mimem.ir import Beat, BeatType, Script, text_sha256

#: Beat types whose text is ours rather than the source's, marked in study.md so a reader can
#: always tell (rule VOI-02).
_SCAFFOLDING_LABEL = {
    BeatType.ORIENTATION: "orientation",
    BeatType.PREQUESTION: "prequestion",
    BeatType.PREQUESTION_CLOSE: "closes a prequestion",
    BeatType.PRELOAD: "term pre-load",
    BeatType.POSITION: "where we are",
    BeatType.TRANSITION: "transition",
    BeatType.EMPHASIS: "emphasis",
    BeatType.RECAP: "recap",
    BeatType.PROMPT: "prompt",
    BeatType.REVIEW: "review",
}


@dataclass
class Artefacts:
    """The rendered outputs, in memory."""

    audio: str
    study: str
    cards: str
    manifest: str

    def write(self, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for name, content in (
            ("audio.md", self.audio),
            ("study.md", self.study),
            ("cards.json", self.cards),
            ("manifest.json", self.manifest),
        ):
            path = out_dir / name
            path.write_text(content, encoding="utf-8")
            written.append(path)
        return written


def render(script: Script) -> Artefacts:
    """Render every artefact from one script."""
    return Artefacts(
        audio=render_audio(script),
        study=render_study(script),
        cards=render_cards(script),
        manifest=render_manifest(script),
    )


# -- audio ---------------------------------------------------------------------------------


def render_audio(script: Script) -> str:
    """The narration track: speakable text, one paragraph per beat."""
    lines = [beat.text.strip() for beat in script.beats() if beat.text.strip()]
    return "\n\n".join(lines) + "\n"


# -- study ---------------------------------------------------------------------------------


def render_study(script: Script) -> str:
    """The written companion: the source, its locators, and what the audio track dropped."""
    out: list[str] = [f"# {script.source.title or 'Untitled'}\n"]
    if script.source.authors:
        out.append(f"*{', '.join(script.source.authors[:6])}*\n")
    out.append(
        f"Programme: {script.est_seconds / 60:.0f} minutes, profile `{script.profile}`"
        + (f", listener `{script.listener}`" if script.listener else "")
        + ".\n"
    )

    out.append("\n## Before you start\n")
    out.extend(_study_beat(b) for b in script.opening)

    for section in script.sections:
        out.append(f"\n## {section.title}\n")
        for segment in section.segments:
            for beat in segment.beats:
                out.append(_study_beat(beat))

    if script.review:
        out.append("\n## Review\n")
        out.extend(_study_beat(b) for b in script.review)

    if script.dropped:
        out.append("\n## Cut to fit the duration budget\n")
        out.append(
            "Nothing here was in the source; these are beats mimem generated and then cut "
            "(rules DUR-02, COH-05).\n"
        )
        for record in script.dropped:
            out.append(f"- *{record.beat_type.value}* ({record.rule}): {record.text}")

    if script.notes:
        out.append("\n## Notes from the planner\n")
        out.extend(f"- {note}" for note in script.notes)
    return "\n".join(out).strip() + "\n"


def _study_beat(beat: Beat) -> str:
    """One beat in the written track: the source sentence, its page, and who wrote it."""
    label = _SCAFFOLDING_LABEL.get(beat.type)
    body = (beat.written_text or beat.text).strip()

    if beat.type is BeatType.PROMPT:
        return f"\n**Q.** {body}\n"
    if beat.type is BeatType.ANSWER:
        return f"**A.** {body}  <sub>{_locator(beat)}</sub>\n"
    if beat.generated:
        return f"\n*{label or 'generated'}:* {body}\n"
    return f"\n{body}  <sub>{_locator(beat)}</sub>\n"


def _locator(beat: Beat) -> str:
    """Rule GRD-04: every claim points back at a page you can open."""
    if not beat.spans:
        return "generated"
    pages = sorted({s.page for s in beat.spans if s.page})
    if pages:
        return "p" + ", p".join(str(p) for p in pages)
    return beat.spans[0].block_id[:10]


# -- cards ---------------------------------------------------------------------------------


def render_cards(script: Script) -> str:
    """The retrieval pool (rule RET-05), the hand-off to part two."""
    payload = {
        "schema_version": script.schema_version,
        "doc_id": script.doc_id,
        "profile": script.profile,
        "cards": [c.model_dump(mode="json") for c in script.cards],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


# -- manifest ------------------------------------------------------------------------------


def render_manifest(script: Script) -> str:
    """The audit trail: scores, exposures, spacing, drops, and one chunk per beat."""
    chunks = [
        {
            "id": beat.id,
            "type": beat.type.value,
            "at_seconds": round(at, 1),
            "est_seconds": round(beat.est_seconds, 1),
            "pause_after": round(beat.pause_after, 1),
            "sha256": text_sha256(beat.text),
            "generated": beat.generated,
            "rules": beat.rules,
        }
        for beat, at in script.timeline()
        if beat.text.strip()
    ]
    payload = {
        "schema_version": script.schema_version,
        "doc_id": script.doc_id,
        "generated_at": script.generated_at.isoformat(),
        "source": script.source.model_dump(mode="json"),
        "profile": script.profile,
        "listener": script.listener,
        "duration": {
            "estimated_seconds": round(script.est_seconds, 1),
            "budget_seconds": round(script.budget_seconds, 1),
            "within_budget": script.est_seconds <= script.budget_seconds,
        },
        "structure": {
            "sections": [
                {
                    "id": s.id,
                    "title": s.title,
                    "segments": len(s.segments),
                    "est_seconds": round(s.est_seconds, 1),
                }
                for s in script.sections
            ],
            "beats": len(script.beats()),
            "cards": len(script.cards),
        },
        "concepts": {
            cid: {
                "canonical": c.canonical,
                "difficulty": round(c.difficulty, 3),
                "importance": round(c.importance, 3),
                "budget": round(c.budget, 3),
                "signals": c.signals,
                "exposures": [e.model_dump(mode="json") for e in c.exposures],
            }
            for cid, c in script.registry.items()
            if c.exposures
        },
        "schedule": [s.model_dump(mode="json") for s in script.schedule],
        "dropped": [d.model_dump(mode="json") for d in script.dropped],
        "notes": script.notes,
        "chunks": chunks,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
