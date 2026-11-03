"""Lecture facultative des tags audio locaux avec Mutagen."""
from __future__ import annotations

import re
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
    genre: str | None = None
    album: str | None = None


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


BPM_TAGS = ("bpm", "tbpm", "tmpo", "tempo")
KEY_TAGS = ("initialkey", "key", "tkey", "©key")
GENRE_TAGS = ("genre", "tcon", "©gen")
ALBUM_TAGS = ("album", "talb", "©alb")


def _raw_tags(audio):
    """Certains logiciels DJ (Serato, Traktor, Rekordbox) écrivent leurs clés
    dans des champs privés que mutagen n'expose pas en mode easy : on lit donc
    aussi les tags bruts et les blocs TXXX/Xtra."""
    found = {}
    tags = getattr(audio, "tags", None)
    if not tags:
        return found
    try:
        names = list(tags.keys())
    except Exception:
        return found
    for name in names:
        lowered = str(name).casefold()
        if lowered.startswith(("txxx:", "----:")):
            lowered = lowered.split(":", 1)[1].rsplit(":", 1)[-1]
        try:
            value = tags[name]
        except Exception:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if isinstance(value, bytes):
            value = value.decode("utf-8", "ignore")
        if value is None:
            continue
        found.setdefault(lowered, str(value).strip())
    return found


def _number(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    if not match:
        return None
    try:
        value = float(match.group(0).replace(",", "."))
    except ValueError:
        return None
    # MP3 stocke parfois le BPM en millièmes (tmpo = 128000).
    if 40000 <= value <= 250000:
        value /= 1000
    return value if 40 <= value <= 250 else None


def read_metadata(path: str) -> AudioMetadata:
    if MutagenFile is None or not Path(path).is_file():
        return AudioMetadata()
    try:
        audio = MutagenFile(path)
        if audio is None:
            return AudioMetadata()
        try:
            easy = MutagenFile(path, easy=True)
            easy_tags = easy.tags if easy else None
        except Exception:
            easy_tags = None
        raw = _raw_tags(audio)
        bpm_text = _first(easy_tags, BPM_TAGS) or next(
            (raw[name] for name in BPM_TAGS if raw.get(name)), None)
        key = _first(easy_tags, KEY_TAGS) or next(
            (raw[name] for name in KEY_TAGS if raw.get(name)), None)
        genre = _first(easy_tags, GENRE_TAGS) or next(
            (raw[name] for name in GENRE_TAGS if raw.get(name)), None)
        album = _first(easy_tags, ALBUM_TAGS) or next(
            (raw[name] for name in ALBUM_TAGS if raw.get(name)), None)
        bpm = _number(bpm_text) or _number(raw.get("tmpo"))
        return AudioMetadata(bpm=bpm, key=key or None, genre=genre or None,
                             album=album or None)
    except Exception:
        return AudioMetadata()
