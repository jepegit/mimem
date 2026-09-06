"""Where programmes live, and how one gets made from whatever the user has.

An assistant's user does not have a working directory in mind. They have a paper — sometimes as a
file, often as a link, and quite often as an attachment the assistant can read but cannot locate
on disk. All three have to work, so :func:`resolve_source` takes a path, a URL or the text
itself.

Everything written goes under one workspace, so a build never scatters files across a machine and
the whole thing can be deleted in one go. Reading is not confined: the user is entitled to point
this at any paper they have.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unicodedata
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from mimem.config import Listener, Profile
from mimem.pipeline import BuildResult, build_all

#: Where programmes are written. One directory, so nothing is ever scattered.
WORKSPACE_ENV = "MIMEM_WORKSPACE"
DEFAULT_WORKSPACE = Path.home() / "mimem"

#: A fetched document is a network request the user asked for. Bounded, so a mistyped link
#: cannot fill a disk.
MAX_FETCH_BYTES = 80 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 60

#: Text pasted straight into the tool needs to be long enough to be a document rather than a
#: mistake -- a one-line "source" is almost always a path someone meant to pass as a path.
MIN_TEXT_CHARS = 400


class SourceError(ValueError):
    """The source could not be turned into a document."""


@dataclass(frozen=True)
class Workspace:
    root: Path

    @classmethod
    def open(cls, root: Path | str | None = None) -> Workspace:
        configured = root or os.environ.get(WORKSPACE_ENV) or DEFAULT_WORKSPACE
        path = Path(configured).expanduser()
        (path / "programmes").mkdir(parents=True, exist_ok=True)
        return cls(root=path)

    @property
    def programmes(self) -> Path:
        return self.root / "programmes"

    def directory(self, programme_id: str) -> Path:
        """The directory for a programme, refusing anything that escapes the workspace."""
        candidate = (self.programmes / programme_id).resolve()
        if not candidate.is_relative_to(self.programmes.resolve()):
            raise SourceError(f"{programme_id!r} is not a programme in this workspace")
        return candidate

    def list(self) -> list[dict[str, object]]:
        """Every programme built here, newest first."""
        out: list[dict[str, object]] = []
        for record in self.programmes.glob("*/programme.json"):
            try:
                out.append(json.loads(record.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(out, key=lambda p: str(p.get("built_at", "")), reverse=True)

    def record(self, programme_id: str) -> dict[str, object]:
        path = self.directory(programme_id) / "programme.json"
        if not path.exists():
            known = ", ".join(str(p.get("id")) for p in self.list()[:8]) or "none yet"
            raise SourceError(f"no programme {programme_id!r}. Built so far: {known}")
        loaded: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        return loaded


def slugify(text: str, fallback: str = "programme") -> str:
    """A directory name a human can recognise in a file listing."""
    normalised = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalised.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:60].strip("-")
    return slug or fallback


def resolve_source(
    path: str | None = None,
    url: str | None = None,
    text: str | None = None,
    *,
    into: Path,
) -> tuple[Path, str]:
    """Turn whatever the user has into a file on disk. Returns the file and how it arrived."""
    given = [v for v in (path, url, text) if v]
    if len(given) != 1:
        raise SourceError("give exactly one of: path, url, text")

    if path:
        source = Path(path).expanduser()
        if not source.exists():
            raise SourceError(f"no file at {source}")
        if not source.is_file():
            raise SourceError(f"{source} is not a file")
        return source, "path"

    if url:
        return _fetch(url, into), "url"

    assert text is not None
    if len(text) < MIN_TEXT_CHARS:
        raise SourceError(
            f"that is {len(text)} characters, which is too short to be a document. If it is a "
            "file path, pass it as `path` instead."
        )
    target = into / "source.md"
    target.write_text(text, encoding="utf-8")
    return target, "text"


def _fetch(url: str, into: Path) -> Path:
    """Download a document. Explicitly, over http(s) only, and bounded."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SourceError(f"only http and https can be fetched, not {parsed.scheme!r}")

    name = Path(parsed.path).name or "download"
    target = into / name
    request = urllib.request.Request(url, headers={"User-Agent": "mimem"})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_FETCH_BYTES:
                raise SourceError(f"{url} is larger than the {MAX_FETCH_BYTES // 1_000_000} MB cap")
            with tempfile.NamedTemporaryFile(delete=False) as handle:
                copied = 0
                while chunk := response.read(1 << 20):
                    copied += len(chunk)
                    if copied > MAX_FETCH_BYTES:
                        raise SourceError(
                            f"{url} is larger than the {MAX_FETCH_BYTES // 1_000_000} MB cap"
                        )
                    handle.write(chunk)
                downloaded = Path(handle.name)
    except SourceError:
        raise
    except Exception as exc:  # network, DNS, TLS, HTTP status
        raise SourceError(f"could not fetch {url}: {exc}") from exc

    if not target.suffix:
        target = target.with_suffix(".pdf" if _looks_like_pdf(downloaded) else ".txt")
    shutil.move(str(downloaded), target)
    return target


def _looks_like_pdf(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def build(
    workspace: Workspace,
    profile: Profile,
    listener: Listener | None = None,
    *,
    path: str | None = None,
    url: str | None = None,
    text: str | None = None,
    name: str | None = None,
) -> tuple[BuildResult, dict[str, object]]:
    """Build a programme into the workspace and register it."""
    staging = Path(tempfile.mkdtemp(prefix="mimem-"))
    try:
        source, arrival = resolve_source(path, url, text, into=staging)
        provisional = slugify(name or source.stem)
        out_dir = _unique(workspace.programmes / provisional)
        result = build_all(source, out_dir, profile, listener)

        programme_id = out_dir.name
        record: dict[str, object] = {
            "id": programme_id,
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "source": _describe_source(path, url),
            "arrived_as": arrival,
            "profile": profile.name,
            "listener": listener.name if listener else None,
            **result.summary(),
        }
        (out_dir / "programme.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return result, record
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _describe_source(path: str | None, url: str | None) -> str:
    """Where this came from, for the programme record."""
    if url:
        return url
    if path:
        return str(Path(path).expanduser())
    return "pasted text"


def _unique(path: Path) -> Path:
    """Never overwrite a previous programme: the old one may be mid-review."""
    if not path.exists():
        return path
    for n in range(2, 100):
        candidate = path.with_name(f"{path.name}-{n}")
        if not candidate.exists():
            return candidate
    raise SourceError(f"too many programmes named {path.name}")
