"""Stage 9: chunks, silences, engines and the cache (rules TTS-02..05, milestone M7).

The properties worth testing here are not "does it make a WAV". They are the three claims the
design makes about synthesis and cannot check by listening:

- the audio contains exactly the beats the audit trail says it does, in that order;
- the pauses are the planner's, to the frame, whichever engine spoke;
- editing one beat re-synthesises one beat.
"""

from __future__ import annotations

import io
import json
import wave
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mimem.ir import Beat, BeatType, Script, Section, Segment, SourceMeta
from mimem.render import render_manifest
from mimem.speak import (
    Format,
    SpeechCache,
    key_for,
    speech_chunks,
    synthesize,
)
from mimem.speak.audio import AudioError, Clip, decode, encode, silence
from mimem.speak.engine import EngineOptions, SilentEngine, create

TONE_FORMAT = Format(channels=1, sample_width=2, frame_rate=22050)


@dataclass
class CountingEngine:
    """An engine that makes a fixed noise and remembers everything it was asked to say."""

    name: str = "counting"
    seconds_per_word: float = 0.4
    said: list[str] = field(default_factory=list)
    fmt: Format = TONE_FORMAT

    @property
    def fingerprint(self) -> str:
        return f"counting/{self.seconds_per_word:g}"

    def voices(self) -> list[object]:
        return []

    def speak(self, text: str) -> bytes:
        self.said.append(text)
        return encode([silence(len(text.split()) * self.seconds_per_word, self.fmt)])


def _beat(beat_id: str, text: str, *, pause: float = 0.0, est: float = 1.0) -> Beat:
    return Beat(
        id=beat_id,
        type=BeatType.EXPOSITION,
        text=text,
        est_seconds=est,
        pause_after=pause,
        spans=[],
        generated=True,
    )


def _script(*beats: Beat) -> Script:
    segment = Segment(id="seg1", section_id="sec1", beats=list(beats))
    section = Section(id="sec1", title="A section", segments=[segment])
    return Script(
        doc_id="doc1",
        source=SourceMeta(format="markdown"),
        profile="study",
        sections=[section],
    )


# -- chunks ---------------------------------------------------------------------------------


def test_a_beat_with_no_text_is_not_a_chunk() -> None:
    """An engine handed an empty string returns nothing, or a click."""
    script = _script(_beat("a", "Something."), _beat("b", "   "), _beat("c", "More."))
    assert [c.id for c in speech_chunks(script)] == ["a", "c"]


def test_the_chunks_are_the_ones_the_manifest_lists() -> None:
    """The audit trail claims to describe the audio, so the two lists have to be one list.

    They are built in different modules from the same `Beat.spoken`, and this is the assertion
    that keeps them that way -- the drift would be invisible in both files separately.
    """
    script = _script(
        _beat("a", "First."), _beat("b", ""), _beat("c", "Second.", pause=4.0), _beat("d", "Third.")
    )
    manifest = json.loads(render_manifest(script))
    assert [c["id"] for c in manifest["chunks"]] == [c.id for c in speech_chunks(script)]


def test_a_chunk_carries_the_pause_that_follows_it() -> None:
    script = _script(_beat("q", "What sets the floor?", pause=6.0))
    chunk = speech_chunks(script)[0]
    assert chunk.pause_after == 6.0
    assert chunk.has_pause


# -- audio ----------------------------------------------------------------------------------


def test_silence_is_exactly_as_long_as_asked() -> None:
    assert silence(2.5, TONE_FORMAT).seconds == pytest.approx(2.5)


def test_joining_two_formats_is_refused() -> None:
    """Concatenating 22 kHz onto 44 kHz plays half the programme at the wrong pitch."""
    a = silence(1.0, TONE_FORMAT)
    b = silence(1.0, Format(channels=1, sample_width=2, frame_rate=44100))
    with pytest.raises(AudioError, match="would change pitch"):
        encode([a, b])


def test_a_non_wav_response_is_reported_as_such() -> None:
    """Engines fail by returning an error page far more often than by returning bad audio."""
    with pytest.raises(AudioError, match="did not return a WAV"):
        decode(b'{"error": "quota exceeded"}', source="openai")


def test_an_empty_response_is_reported_as_such() -> None:
    with pytest.raises(AudioError, match="no audio at all"):
        decode(b"", source="piper")


def test_a_round_trip_preserves_length() -> None:
    clip = silence(3.0, TONE_FORMAT)
    assert decode(encode([clip])).seconds == pytest.approx(3.0)


# -- assembly -------------------------------------------------------------------------------


def test_the_pause_lands_in_the_audio_as_real_silence() -> None:
    """PAU-01's thinking time only exists if it is in the file."""
    engine = CountingEngine(seconds_per_word=0.5)
    script = _script(_beat("q", "one two", pause=5.0), _beat("a", "three four"))
    result = synthesize(script, engine, use_cache=False)
    # two words at half a second each, twice, plus the five-second gap
    assert result.seconds == pytest.approx(1.0 + 5.0 + 1.0)
    assert result.timings[0].pause == pytest.approx(5.0)
    assert result.timings[1].start == pytest.approx(6.0)


def test_the_timing_map_matches_the_file_it_describes() -> None:
    engine = CountingEngine()
    script = _script(_beat("a", "one two three"), _beat("b", "four", pause=2.0), _beat("c", "five"))
    result = synthesize(script, engine, use_cache=False)
    with wave.open(io.BytesIO(result.wav)) as handle:
        actual = handle.getnframes() / handle.getframerate()
    assert actual == pytest.approx(result.seconds)
    assert result.timings[-1].end == pytest.approx(result.seconds)


def test_the_engine_is_asked_for_the_beat_text_and_nothing_else() -> None:
    """No SSML, no markers, no wrapper -- TTS-02 says prosody is punctuation only."""
    engine = CountingEngine()
    script = _script(_beat("a", "A sentence."), _beat("b", "Another one.", pause=3.0))
    synthesize(script, engine, use_cache=False)
    assert engine.said == ["A sentence.", "Another one."]


def test_two_engines_produce_the_same_structure(tmp_path: Path) -> None:
    """Rule TTS-05: engine choice must not change the content."""
    script = _script(_beat("a", "one two"), _beat("b", "three", pause=4.0), _beat("c", "four"))
    fast = synthesize(script, CountingEngine(seconds_per_word=0.2), use_cache=False)
    slow = synthesize(script, CountingEngine(seconds_per_word=0.8), use_cache=False)

    assert [t.id for t in fast.timings] == [t.id for t in slow.timings]
    assert [t.pause for t in fast.timings] == [t.pause for t in slow.timings]
    assert fast.seconds < slow.seconds  # only the speech differs, and only in length


def test_a_script_with_nothing_to_say_is_an_error() -> None:
    with pytest.raises(ValueError, match="no spoken beats"):
        synthesize(_script(_beat("a", "  ")), SilentEngine(), use_cache=False)


def test_the_drift_is_measured_against_the_profiles_estimate() -> None:
    """The first time the pipeline can check its own duration arithmetic against speech."""
    engine = CountingEngine(seconds_per_word=1.0)
    script = _script(_beat("a", "one two three", est=1.0))
    result = synthesize(script, engine, use_cache=False)
    assert result.timings[0].estimated == 1.0
    assert result.timings[0].drift == pytest.approx(2.0)
    assert result.drift == pytest.approx(2.0)


# -- cache ----------------------------------------------------------------------------------


def test_the_second_run_synthesises_nothing(tmp_path: Path) -> None:
    script = _script(_beat("a", "one two"), _beat("b", "three four"))
    first = CountingEngine()
    synthesize(script, first, out_dir=tmp_path)
    second = CountingEngine()
    result = synthesize(script, second, out_dir=tmp_path)

    assert second.said == []
    assert result.synthesised == 0
    assert result.reused == 2


def test_editing_one_beat_resynthesises_one_beat(tmp_path: Path) -> None:
    """The whole reason chunk ids are content-addressed (rule TTS-03)."""
    before = _script(_beat("a", "one two"), _beat("b", "three four"), _beat("c", "five six"))
    synthesize(before, CountingEngine(), out_dir=tmp_path)

    after = _script(_beat("a", "one two"), _beat("b", "three FIVE"), _beat("c", "five six"))
    engine = CountingEngine()
    result = synthesize(after, engine, out_dir=tmp_path)

    assert engine.said == ["three FIVE"]
    assert (result.synthesised, result.reused) == (1, 2)


def test_changing_voice_does_not_replay_the_old_one(tmp_path: Path) -> None:
    """Text alone as the key is a bug that looks exactly like --voice being ignored."""
    script = _script(_beat("a", "one two"))
    synthesize(script, CountingEngine(seconds_per_word=0.2), out_dir=tmp_path)
    other = CountingEngine(seconds_per_word=0.9)
    synthesize(script, other, out_dir=tmp_path)
    assert other.said == ["one two"]


def test_identical_text_is_synthesised_once(tmp_path: Path) -> None:
    """The retrieval cue is said many times in a programme and sounds the same each time."""
    script = _script(
        _beat("a", "Take a few seconds.", pause=5.0),
        _beat("b", "Something else."),
        _beat("c", "Take a few seconds.", pause=5.0),
    )
    engine = CountingEngine()
    result = synthesize(script, engine, out_dir=tmp_path)
    assert engine.said == ["Take a few seconds.", "Something else."]
    assert result.reused == 1
    assert len(result.timings) == 3  # ...but it is still heard three times


def test_an_interrupted_write_is_not_served_as_audio(tmp_path: Path) -> None:
    """A zero-byte file from a killed run must look absent, not like a broken engine."""
    cache = SpeechCache(root=tmp_path)
    key = key_for("hello", "engine/x")
    cache.path_for(key).parent.mkdir(parents=True, exist_ok=True)
    cache.path_for(key).write_bytes(b"")
    assert cache.get(key) is None


def test_the_cache_key_covers_both_text_and_engine() -> None:
    assert key_for("a", "e1") != key_for("b", "e1")
    assert key_for("a", "e1") != key_for("a", "e2")
    assert key_for("a", "e1") == key_for("a", "e1")


# -- writing --------------------------------------------------------------------------------


def test_writing_produces_a_playable_file_and_its_map(tmp_path: Path) -> None:
    script = _script(_beat("a", "one two", pause=2.0), _beat("b", "three"))
    result = synthesize(script, CountingEngine(), out_dir=tmp_path)
    written = result.write(tmp_path)

    assert [p.name for p in written] == ["audio.wav", "timings.json"]
    with wave.open(str(tmp_path / "audio.wav")) as handle:
        assert handle.getnframes() > 0
    payload = json.loads((tmp_path / "timings.json").read_text(encoding="utf-8"))
    assert payload["audio"] == "audio.wav"
    assert [c["id"] for c in payload["chunks"]] == ["a", "b"]
    assert payload["seconds"] == pytest.approx(result.seconds, abs=0.01)


# -- adapters -------------------------------------------------------------------------------


def test_every_named_engine_can_be_created() -> None:
    from mimem.speak import ENGINES

    for name in ENGINES:
        engine = create(name)
        assert engine.name == name
        assert engine.fingerprint


def test_an_unknown_engine_lists_the_known_ones() -> None:
    from mimem.speak import EngineError

    # This example used to be "elevenlabs", which stopped being unknown in M12.
    with pytest.raises(EngineError, match="silent"):
        create("a-voice-that-does-not-exist")


def test_piper_takes_its_model_from_either_flag() -> None:
    """Piper's voice *is* a file, so --voice and --model mean the same thing to it."""
    assert create("piper", EngineOptions(voice="a.onnx")).fingerprint.endswith("a.onnx")
    assert create("piper", EngineOptions(model="b.onnx")).fingerprint.endswith("b.onnx")


def test_the_openai_adapter_asks_for_wav() -> None:
    """The default is MP3, which does not concatenate."""
    import mimem.speak.engine as engine_module

    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return encode([silence(0.5, TONE_FORMAT)])

    def fake_urlopen(request: object, timeout: float = 0.0) -> FakeResponse:
        captured["url"] = request.full_url  # type: ignore[attr-defined]
        captured["body"] = json.loads(request.data)  # type: ignore[attr-defined]
        captured["headers"] = request.headers  # type: ignore[attr-defined]
        return FakeResponse()

    original = engine_module.urllib.request.urlopen
    engine_module.urllib.request.urlopen = fake_urlopen  # type: ignore[assignment]
    try:
        engine = create("openai", EngineOptions(base_url="http://localhost:8000/v1", api_key="k"))
        engine.speak("hello")
    finally:
        engine_module.urllib.request.urlopen = original  # type: ignore[assignment]

    assert captured["url"] == "http://localhost:8000/v1/audio/speech"
    assert captured["body"]["response_format"] == "wav"  # type: ignore[index]
    assert captured["body"]["input"] == "hello"  # type: ignore[index]


def test_a_non_http_base_url_is_refused() -> None:
    """`--base-url file:///etc/passwd` should not reach urlopen."""
    from mimem.speak import EngineError

    engine = create("openai", EngineOptions(base_url="file:///etc"))
    with pytest.raises(EngineError, match="http or https"):
        engine.speak("hello")


def test_the_silent_engine_makes_audio_of_a_plausible_length() -> None:
    clip = decode(SilentEngine().speak(" ".join(["word"] * 150)))
    assert clip.seconds == pytest.approx(60.0, rel=0.01)
    assert isinstance(clip, Clip)
