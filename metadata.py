"""Lecture facultative des tags audio locaux avec Mutagen."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    from mutagen import File as MutagenFile
except ImportError:  # l'application reste utilisable avec les seules transitions
    MutagenFile = None


@dataclass(frozen=True)
class AudioMetadata:
    bpm: float | None = None
    key: str | None = None


def _first(tags, names):
    if tags is None:
        return None
    lowered = {str(k).casefold(): v for k, v in tags.items()}
    for name in names:
        value = lowered.get(name.casefold())
        if value is not None:
            if isinstance(value, (list, tuple)):
                value = value[0] if value else None
            if value is not None:
                return str(value).strip()
    return None


def read_metadata(path: str) -> AudioMetadata:
    if MutagenFile is None or not Path(path).is_file():
        return AudioMetadata()
    try:
        audio = MutagenFile(path, easy=True)
        tags = audio.tags if audio else None
        bpm_text = _first(tags, ("bpm", "tbpm", "tmpo"))
        key = _first(tags, ("initialkey", "key", "tkey", "©key"))
        try:
            bpm = float(bpm_text.replace(",", ".")) if bpm_text else None
        except ValueError:
            bpm = None
        if bpm is not None and not 40 <= bpm <= 250:
            bpm = None
        return AudioMetadata(bpm=bpm, key=key or None)
    except Exception:
        return AudioMetadata()
