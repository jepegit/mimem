"""MP3, when ``ffmpeg`` happens to be installed. Never a requirement.

M7 shipped WAV only, and the reasoning was right: MP3 means ``ffmpeg``, which is a dependency
and a platform matrix, and this project's whole install is meant to be one ``uvx`` away. Then
the survey for ``docs/PLAN-ai.md`` found ``ffmpeg`` already on the development machine, which
does not change the argument -- it changes who the argument is about.

So the resolution is not to reverse the decision but to soften it. **WAV always. MP3 when
``ffmpeg`` is there and you ask for it. Never a requirement, and never a silent substitution.**
A twenty-minute programme goes from about 50 MB to about 20, which matters if it is going onto
a phone and not at all otherwise.

The conversion is deliberately dumb: write the WAV, shell out, keep both. Reimplementing an MP3
encoder to avoid a subprocess would be a strange thing to do, and reading the WAV back through
``ffmpeg`` rather than piping it means a failure leaves the WAV where you can find it.
"""

from __future__ import annotations

import shutil
import subprocess
from enum import StrEnum
from pathlib import Path

#: Long enough for a two-hour programme on a slow machine, short enough that a hung process is
#: noticed the same day.
TIMEOUT = 900.0

#: Constant bit rate, chosen for speech rather than music. 64k mono is transparent for a single
#: voice and a quarter the size of 256k.
BITRATE = "64k"


class OutputFormat(StrEnum):
    """What ``mimem speak --format`` accepts.

    Not ``Format``: :class:`mimem.speak.audio.Format` is the *sample* format -- channels, width,
    rate -- and this is the container the finished programme is written in. Two different things
    with one name would be a collision waiting for the afternoon someone imports both.
    """

    WAV = "wav"
    MP3 = "mp3"


def available() -> bool:
    """Is ``ffmpeg`` on the PATH? Asked rather than assumed, every time."""
    return shutil.which("ffmpeg") is not None


class ConversionError(RuntimeError):
    """``ffmpeg`` was asked for and could not do it."""


def to_mp3(wav: Path, *, bitrate: str = BITRATE) -> Path:
    """Convert a written WAV beside itself, and return the new path.

    The WAV is kept. It is the artefact the rest of the system is defined in terms of -- the
    timing map describes it, and a re-run reuses its cache -- so removing it to save disk would
    trade a byte count for the thing that makes an incremental re-render possible.
    """
    if not available():
        raise ConversionError(
            "ffmpeg is not on PATH, so mp3 output is unavailable. The WAV is written either "
            "way; `mimem doctor` reports whether ffmpeg is there."
        )
    if not wav.exists():
        raise ConversionError(f"{wav} does not exist")

    out = wav.with_suffix(".mp3")
    command = [
        "ffmpeg",
        "-y",  # the caller decided to overwrite by asking again
        "-loglevel",
        "error",
        "-i",
        str(wav),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        "-ac",
        "1",
        str(out),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(f"ffmpeg did not finish in {TIMEOUT:g}s") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[:300]
        raise ConversionError(f"ffmpeg failed: {detail or 'no error message'}")
    if not out.exists():  # pragma: no cover - ffmpeg returning 0 without writing
        raise ConversionError(f"ffmpeg reported success but {out} is not there")
    return out
