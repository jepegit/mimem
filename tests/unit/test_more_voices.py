"""ElevenLabs, and MP3 when ffmpeg is there (M12).

The ElevenLabs tests run against a fake endpoint, because what is worth pinning is the shape of
the request and the fact that **the API does not return a WAV**. The MP3 tests are real: ffmpeg
is either installed or the test skips, and where it is installed the conversion actually runs.
"""

from __future__ import annotations

import io
import json
import shutil
import wave
from pathlib import Path
from typing import Any

import pytest

from mimem.speak import create
from mimem.speak.audio import Format as SampleFormat
from mimem.speak.audio import decode, encode, silence
from mimem.speak.elevenlabs import (
    DEFAULT_RATE,
    PCM_RATES,
    ElevenLabsEngine,
    wrap_pcm,
)
from mimem.speak.encode import ConversionError, OutputFormat, available, to_mp3
from mimem.speak.engine import ENGINES, EngineError, EngineOptions

PCM = b"\x00\x01" * 4410  # a fifth of a second of 16-bit mono at 22.05 kHz


class FakeAPI:
    """Stands in for `urlopen`, and records what it was asked for."""

    def __init__(self, payload: bytes, *, status: int | None = None) -> None:
        self.payload = payload
        self.status = status
        self.requests: list[Any] = []

    def __call__(self, request: Any, timeout: float = 0.0) -> Any:
        self.requests.append(request)
        if self.status is not None:
            import urllib.error

            return _raise(urllib.error.HTTPError("u", self.status, "err", {}, io.BytesIO(b"no")))
        return _Response(self.payload)


def _raise(exc: BaseException) -> Any:
    raise exc


class _Response:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._data


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def apply(api: FakeAPI) -> FakeAPI:
        import mimem.speak.elevenlabs as module

        monkeypatch.setattr(module.urllib.request, "urlopen", api)
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
        return api

    return apply


# -- the header the API does not send --------------------------------------------------------


def test_raw_pcm_becomes_a_readable_wav() -> None:
    """The whole reason this adapter is a file rather than a branch."""
    clip = decode(wrap_pcm(PCM))
    assert clip.format == SampleFormat(channels=1, sample_width=2, frame_rate=DEFAULT_RATE)
    assert clip.seconds == pytest.approx(0.2, abs=0.01)


def test_headerless_pcm_would_not_have_decoded() -> None:
    """Which is what makes the wrapping load-bearing rather than tidy."""
    from mimem.speak.audio import AudioError

    with pytest.raises(AudioError, match="did not return a WAV"):
        decode(PCM, source="elevenlabs")


def test_the_default_rate_matches_the_other_engines() -> None:
    """A programme half-rendered by SAPI and half by this must still concatenate."""
    from mimem.speak.engine import SILENT_FORMAT

    assert SILENT_FORMAT.frame_rate == DEFAULT_RATE


def test_wrapped_audio_joins_with_another_engines() -> None:
    theirs = decode(wrap_pcm(PCM))
    ours = silence(0.5, SampleFormat(channels=1, sample_width=2, frame_rate=DEFAULT_RATE))
    joined = decode(encode([theirs, ours]))
    assert joined.seconds == pytest.approx(0.7, abs=0.02)


# -- the request -----------------------------------------------------------------------------


def test_it_asks_for_pcm_not_mp3(patched) -> None:  # type: ignore[no-untyped-def]
    """MP3 is the API's default and does not concatenate."""
    api = patched(FakeAPI(PCM))
    ElevenLabsEngine().speak("hello")
    assert f"output_format=pcm_{DEFAULT_RATE}" in api.requests[0].full_url


def test_the_voice_is_in_the_path_and_the_key_in_a_header(patched) -> None:  # type: ignore[no-untyped-def]
    api = patched(FakeAPI(PCM))
    ElevenLabsEngine(voice="abc123").speak("hello")
    request = api.requests[0]
    assert "/text-to-speech/abc123" in request.full_url
    assert request.get_header("Xi-api-key") == "test-key"
    assert json.loads(request.data)["text"] == "hello"


def test_a_rate_the_api_does_not_serve_is_refused() -> None:
    with pytest.raises(EngineError, match="serves PCM at"):
        ElevenLabsEngine(api_key="k", rate=12345).speak("hello")


def test_every_offered_rate_wraps(monkeypatch: pytest.MonkeyPatch) -> None:
    for rate in PCM_RATES:
        assert decode(wrap_pcm(PCM, rate)).format.frame_rate == rate


def test_no_key_says_which_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(EngineError, match="ELEVENLABS_API_KEY"):
        ElevenLabsEngine().speak("hello")


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "rejected the key"),
        (422, "unknown voice id"),
        (429, "rate-limiting or the character quota"),
        (500, "returned 500"),
    ],
)
def test_failures_say_what_to_do(status: int, expected: str, patched) -> None:  # type: ignore[no-untyped-def]
    patched(FakeAPI(b"", status=status))
    with pytest.raises(EngineError, match=expected):
        ElevenLabsEngine().speak("hello")


def test_voices_are_named_not_just_numbered(patched) -> None:  # type: ignore[no-untyped-def]
    """The ids are opaque, so a listing of ids alone would be no help."""
    payload = json.dumps(
        {"voices": [{"voice_id": "v1", "name": "Rachel", "labels": {"accent": "american"}}]}
    ).encode()
    patched(FakeAPI(payload))
    found = ElevenLabsEngine().voices()
    assert (found[0].id, found[0].name, found[0].locale) == ("v1", "Rachel", "american")


def test_an_empty_response_is_an_error(patched) -> None:  # type: ignore[no-untyped-def]
    patched(FakeAPI(b""))
    with pytest.raises(EngineError, match="no audio"):
        ElevenLabsEngine().speak("hello")


# -- the registry ----------------------------------------------------------------------------


def test_elevenlabs_is_selectable_by_name() -> None:
    engine = create("elevenlabs", EngineOptions(voice="v9", model="m2"))
    assert engine.name == "elevenlabs"
    assert "v9" in engine.fingerprint
    assert "m2" in engine.fingerprint


def test_switching_voice_changes_the_cache_key() -> None:
    """Per-character billing makes replaying the wrong voice expensive as well as wrong."""
    a = create("elevenlabs", EngineOptions(voice="v1")).fingerprint
    b = create("elevenlabs", EngineOptions(voice="v2")).fingerprint
    assert a != b


def test_it_is_listed_as_an_engine() -> None:
    assert "elevenlabs" in ENGINES


# -- mp3 -------------------------------------------------------------------------------------


needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def test_the_format_enum_is_not_the_sample_format() -> None:
    """Two different things that were briefly both called `Format`."""
    assert SampleFormat != OutputFormat.WAV
    assert [f.value for f in OutputFormat] == ["wav", "mp3"]


def test_availability_is_asked_rather_than_assumed() -> None:
    assert available() == (shutil.which("ffmpeg") is not None)


@needs_ffmpeg
def test_a_wav_converts_and_the_wav_is_kept(tmp_path: Path) -> None:
    """The WAV is the artefact everything else is defined in terms of."""
    wav = tmp_path / "audio.wav"
    fmt = SampleFormat(channels=1, sample_width=2, frame_rate=22050)
    wav.write_bytes(encode([silence(2.0, fmt)]))

    mp3 = to_mp3(wav)
    assert mp3.name == "audio.mp3"
    assert mp3.stat().st_size > 0
    assert wav.exists(), "the timing map describes the WAV; removing it breaks re-rendering"


@needs_ffmpeg
def test_the_mp3_is_much_smaller(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    fmt = SampleFormat(channels=1, sample_width=2, frame_rate=22050)
    wav.write_bytes(encode([silence(20.0, fmt)]))
    assert to_mp3(wav).stat().st_size < wav.stat().st_size / 2


@needs_ffmpeg
def test_a_missing_input_is_an_error(tmp_path: Path) -> None:
    """Needs ffmpeg, which is the point of the marker rather than an inconvenience.

    `to_mp3` checks availability *before* the input, because "this machine cannot make MP3s at
    all" is more useful than "that file is missing". So without ffmpeg this raises the other
    error and the test is meaningless -- which is exactly what CI reported, on a machine where
    ffmpeg is absent and mine where it is not.
    """
    with pytest.raises(ConversionError, match="does not exist"):
        to_mp3(tmp_path / "nope.wav")


def test_without_ffmpeg_it_says_the_wav_is_written_anyway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing optional tool is a smaller result, not a failed run."""
    monkeypatch.setattr("mimem.speak.encode.shutil.which", lambda name: None)
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    with pytest.raises(ConversionError, match="written either way"):
        to_mp3(wav)


@needs_ffmpeg
def test_a_wav_that_is_not_a_wav_fails_rather_than_writing_rubbish(tmp_path: Path) -> None:
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"this is not audio")
    with pytest.raises(ConversionError, match="ffmpeg failed"):
        to_mp3(bad)


def test_a_real_wav_round_trips_through_wave(tmp_path: Path) -> None:
    """Guard on the fixture itself: if this stops being a WAV the mp3 tests mean nothing."""
    fmt = SampleFormat(channels=1, sample_width=2, frame_rate=22050)
    data = encode([silence(1.0, fmt)])
    with wave.open(io.BytesIO(data)) as handle:
        assert handle.getframerate() == 22050
