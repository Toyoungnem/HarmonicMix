"""Extraction locale et légère des pochettes intégrées aux fichiers audio."""
from __future__ import annotations

from pathlib import Path

try:
    from mutagen import File as MutagenFile
except ImportError:  # Les pochettes restent facultatives.
    MutagenFile = None


def read_cover(path: str, fallback: str | None = None) -> bytes | None:
    """Pochette du fichier ; si elle manque et qu'un `fallback` est fourni
    (autre morceau, même album), on essaie ce fichier avant d'abandonner."""
    """Renvoie les données de la première pochette embarquée, sans accès réseau."""
    if MutagenFile is None or not path or not Path(path).is_file():
        return read_cover(fallback) if fallback and fallback != path else None
    try:
        audio = MutagenFile(path, easy=False)
        if audio is None:
            return read_cover(fallback) if fallback and fallback != path else None

        pictures = getattr(audio, "pictures", None)
        if pictures:
            data = getattr(pictures[0], "data", None)
            if data:
                return bytes(data)

        tags = getattr(audio, "tags", None)
        if tags is None:
            return None

        # MP3 / ID3
        getall = getattr(tags, "getall", None)
        if callable(getall):
            for picture in getall("APIC"):
                data = getattr(picture, "data", None)
                if data:
                    return bytes(data)

        # MP4 / M4A
        for key in ("covr", "COVR"):
            try:
                values = tags.get(key)
            except (AttributeError, TypeError):
                values = None
            if values:
                return bytes(values[0])
    except Exception:
        return read_cover(fallback) if fallback and fallback != path else None
    # Rien dans ce fichier : on tente le morceau voisin du même album.
    return read_cover(fallback) if fallback and fallback != path else None
