"""Stage 9: chunks and silences into one playable file.

The engine makes sound; this decides where it goes and how long the gaps are. Keeping those
apart is what makes ``TTS-05`` true -- the pauses that carry ``PAU-01``'s retrieval time are
inserted here, in frames, identically for every adapter, rather than requested from an engine
that may or may not honour a break marker.

The timing map that comes out is not a by-product. The whole programme is built on the claim
that a pause after a question is long enough to actually retrieve, and until now that claim was
an estimate made from a word count. The map records where every beat *actually* starts and how
long it *actually* ran, so the estimate can be checked against the audio rather than trusted.
It is also what a player needs to jump to a beat, which is where part two starts.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from mimem.ir import Script
from mimem.speak.audio import Clip, Format, decode, encode, silence
from mimem.speak.cache import CACHE_DIR, NullCache, SpeechCache, key_for
from mimem.speak.chunks import SpeechChunk, speech_chunks
from mimem.speak.engine import Engine

#: Filenames written beside the other artefacts.
AUDIO_FILE = "audio.wav"
TIMINGS_FILE = "timings.json"

Progress = Callable[[int, int, SpeechChunk, bool], None]


@dataclass(frozen=True, slots=True)
class Timing:
    """Where one beat ended up in the finished file."""

    id: str
    start: float
    speech: float
    pause: float
    estimated: float

    @property
    def end(self) -> float:
        return self.start + self.speech + self.pause

    @property
    def drift(self) -> float:
        """Actual speech length minus what the profile predicted, in seconds."""
        return self.speech - self.estimated


@dataclass(slots=True)
class Synthesis:
    """A finished programme, and what it cost to make."""

    wav: bytes
    timings: list[Timing]
    format: Format
    synthesised: int
    reused: int

    @property
    def seconds(self) -> float:
        return self.timings[-1].end if self.timings else 0.0

    @property
    def estimated_seconds(self) -> float:
        return sum(t.estimated + t.pause for t in self.timings)

    @property
    def drift(self) -> float:
        """How far the whole programme ran over or under its predicted length."""
        return self.seconds - self.estimated_seconds

    def write(self, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        audio = out_dir / AUDIO_FILE
        audio.write_bytes(self.wav)
        timings = out_dir / TIMINGS_FILE
        timings.write_text(self.timings_json(), encoding="utf-8")
        return [audio, timings]

    def timings_json(self) -> str:
        payload = {
            "audio": AUDIO_FILE,
            "format": {
                "channels": self.format.channels,
                "sample_width": self.format.sample_width,
                "frame_rate": self.format.frame_rate,
            },
            "seconds": round(self.seconds, 3),
            "estimated_seconds": round(self.estimated_seconds, 3),
            "chunks": [
                {
                    "id": t.id,
                    "start": round(t.start, 3),
                    "speech": round(t.speech, 3),
                    "pause": round(t.pause, 3),
                    "estimated": round(t.estimated, 3),
                }
                for t in self.timings
            ],
        }
        return json.dumps(payload, indent=2) + "\n"


def synthesize(
    script: Script,
    engine: Engine,
    *,
    out_dir: Path | None = None,
    use_cache: bool = True,
    progress: Progress | None = None,
) -> Synthesis:
    """Turn a script into one WAV file, reusing whatever was already synthesised.

    ``out_dir`` is where the cache lives, not where the result is written -- writing is the
    caller's decision, so that a caller can synthesise and inspect without committing anything
    to disk.
    """
    chunks = speech_chunks(script)
    if not chunks:
        raise ValueError("this script has no spoken beats")

    cache: SpeechCache | NullCache
    if use_cache and out_dir is not None:
        cache = SpeechCache(root=out_dir / CACHE_DIR)
    else:
        cache = NullCache()

    clips: list[Clip] = []
    timings: list[Timing] = []
    at = 0.0
    fingerprint = engine.fingerprint

    for index, chunk in enumerate(chunks):
        key = key_for(chunk.text, fingerprint)
        data = cache.get(key)
        reused = data is not None
        if data is None:
            data = engine.speak(chunk.text)
            cache.put(key, data)
        if progress is not None:
            progress(index, len(chunks), chunk, reused)

        clip = decode(data, source=f"{engine.name} on beat {chunk.id}")
        clips.append(clip)
        speech = clip.seconds

        pause = 0.0
        if chunk.has_pause:
            gap = silence(chunk.pause_after, clip.format)
            clips.append(gap)
            pause = gap.seconds

        timings.append(
            Timing(
                id=chunk.id,
                start=at,
                speech=speech,
                pause=pause,
                estimated=_estimated(script, chunk.id),
            )
        )
        at += speech + pause

    wav = encode(clips, source="programme")
    return Synthesis(
        wav=wav,
        timings=timings,
        format=clips[0].format,
        synthesised=cache.misses,
        reused=cache.hits,
    )


def _estimated(script: Script, beat_id: str) -> float:
    try:
        return script.beat(beat_id).est_seconds
    except KeyError:  # pragma: no cover - chunks come from the script itself
        return 0.0
