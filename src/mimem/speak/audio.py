"""WAV in, WAV out: the one audio representation the adapters agree on.

Every engine returns WAV bytes and assembly concatenates them, which is a decision worth
stating plainly. WAV is uncompressed and large -- a forty-minute programme is a few hundred
megabytes -- and the obvious alternative is to have each adapter return MP3 and stitch those.
That would mean either shelling out to ``ffmpeg`` (a dependency the project does not have, on
a platform matrix it does not want) or decoding MPEG frames by hand. WAV is in the standard
library, exact, and losslessly concatenable; a listener who wants a small file can convert one
at the end, once, with a tool of their choosing.

The strictness here is deliberate. Two WAV files with different sample rates concatenate into
something that plays at the wrong pitch for half its length, and nothing in the format objects.
So the format of the first chunk becomes the format of the programme, and any chunk that
disagrees is an error naming both -- because the alternative is an audio file that is quietly,
audibly wrong in the middle.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass


class AudioError(RuntimeError):
    """A WAV that cannot be read, or that does not match the rest of the programme."""


@dataclass(frozen=True, slots=True)
class Format:
    """The three fields that have to match before two clips can be joined."""

    channels: int
    sample_width: int
    frame_rate: int

    def __str__(self) -> str:
        kind = {1: "mono", 2: "stereo"}.get(self.channels, f"{self.channels}ch")
        return f"{self.frame_rate} Hz {self.sample_width * 8}-bit {kind}"


@dataclass(frozen=True, slots=True)
class Clip:
    """Decoded audio: raw frames plus the format they are in."""

    format: Format
    frames: bytes

    @property
    def seconds(self) -> float:
        bytes_per_frame = self.format.channels * self.format.sample_width
        if bytes_per_frame == 0:  # pragma: no cover - Format validates this on read
            return 0.0
        return len(self.frames) / bytes_per_frame / self.format.frame_rate


def decode(data: bytes, *, source: str = "audio") -> Clip:
    """Read WAV bytes into frames, or say what is wrong with them.

    Engines fail by returning something that is not audio far more often than they fail by
    returning bad audio: an HTTP error body, a shell error message, an empty file. Those all
    arrive here, so this is where they have to be caught and named.
    """
    if not data:
        raise AudioError(f"{source} returned no audio at all")
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            fmt = Format(
                channels=handle.getnchannels(),
                sample_width=handle.getsampwidth(),
                frame_rate=handle.getframerate(),
            )
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError) as exc:
        preview = data[:120].decode("utf-8", errors="replace").strip()
        raise AudioError(f"{source} did not return a WAV file ({exc}): {preview!r}") from exc
    if fmt.channels == 0 or fmt.sample_width == 0 or fmt.frame_rate == 0:
        raise AudioError(f"{source} returned a WAV with no format: {fmt}")
    return Clip(format=fmt, frames=frames)


def silence(seconds: float, fmt: Format) -> Clip:
    """A clip of exactly this many seconds of nothing, in this format."""
    frames = max(0, round(seconds * fmt.frame_rate))
    return Clip(format=fmt, frames=b"\x00" * (frames * fmt.channels * fmt.sample_width))


def encode(clips: list[Clip], *, source: str = "programme") -> bytes:
    """Join clips into one WAV file, refusing to join formats that differ."""
    if not clips:
        raise AudioError(f"{source} has nothing to write")
    fmt = clips[0].format
    for index, clip in enumerate(clips[1:], start=1):
        if clip.format != fmt:
            raise AudioError(
                f"{source} chunk {index} is {clip.format}, but the programme is {fmt}; "
                "joining them would change pitch part-way through"
            )

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(fmt.channels)
        handle.setsampwidth(fmt.sample_width)
        handle.setframerate(fmt.frame_rate)
        for clip in clips:
            handle.writeframes(clip.frames)
    return buffer.getvalue()
