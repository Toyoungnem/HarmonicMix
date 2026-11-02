"""Lecture seule de la collection et des historiques NML de Traktor."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

from serato_db import HistoryPlay, HistorySnapshot


def find_traktor_roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    bases = (
        home / "Documents" / "Native Instruments",
        home / "Music" / "Native Instruments",
    )
    found = []
    for base in bases:
        if base.is_dir():
            found.extend(p for p in base.glob("Traktor*") if p.is_dir())
    return sorted(set(found), key=lambda p: p.stat().st_mtime_ns, reverse=True)


def _normal_key(value: str) -> str:
    value = value.replace("\\", "/").replace("/:", "/")
    return "/".join(part for part in value.strip("/: ").casefold().split("/") if part)


def _location_path(location: ET.Element) -> str:
    directory = location.get("DIR", "").replace("\\", "/")
    parts = [part.strip(":/") for part in directory.strip("/").split("/:")]
    parts = [part for part in parts if part]
    filename = location.get("FILE", "")
    volume = location.get("VOLUME", "")
    if re.fullmatch(r"[A-Za-z]:", volume):
        return str(Path(volume + "/") / Path(*parts) / filename)
    if re.match(r"^[A-Za-z]:[/\\]", filename):
        return str(Path(filename))
    return str(Path(*parts, filename)) if parts else filename


def _camelot_key(value: str | None) -> str | None:
    if not value:
        return None
    match = re.fullmatch(r"\s*(1[0-2]|[1-9])\s*([md])\s*", value, re.IGNORECASE)
    if match:
        return f"{match.group(1)}{'A' if match.group(2).casefold() == 'm' else 'B'}"
    return value


def _collection_index(collection_file: Path) -> tuple[dict[str, dict], list[dict]]:
    if not collection_file.is_file():
        return {}, []
    root = ET.parse(collection_file).getroot()
    by_key: dict[str, dict] = {}
    tracks = []
    for entry in root.findall("./COLLECTION/ENTRY"):
        location = entry.find("LOCATION")
        if location is None:
            continue
        path = _location_path(location)
        tempo = entry.find("TEMPO")
        info = entry.find("INFO")
        track = {
            "path": path,
            "title": entry.get("TITLE") or Path(path).stem,
            "artist": entry.get("ARTIST", ""),
            "bpm": _float(tempo.get("BPM")) if tempo is not None else None,
            "key": _camelot_key(info.get("KEY")) if info is not None else None,
        }
        aliases = {
            _normal_key(entry.get("TRACKID", "")),
            _normal_key(path),
            _normal_key("/".join(Path(path).parts[-3:])),
            _normal_key(Path(path).name),
        }
        for alias in aliases:
            if alias:
                by_key.setdefault(alias, track)
        tracks.append(track)
    return by_key, tracks


def _float(value: str | None) -> float | None:
    try:
        number = float(value) if value is not None else None
        return number if number and 40 <= number <= 250 else None
    except (TypeError, ValueError):
        return None


def _lookup_track(key: str, index: dict[str, dict]) -> dict | None:
    normalized = _normal_key(key)
    if normalized in index:
        return index[normalized]
    matches = [(alias, track) for alias, track in index.items()
               if normalized.endswith("/" + alias) or alias.endswith("/" + normalized)]
    if matches:
        return max(matches, key=lambda pair: len(pair[0]))[1]
    basename = _normal_key(Path(key.replace("\\", "/")).name)
    return index.get(basename)


class TraktorLibrary:
    """Lit les fichiers NML de Traktor sans jamais les modifier."""

    def __init__(self, roots: list[Path] | None = None):
        self.roots = roots
        self._signature = None
        self._snapshot = None

    def _root(self) -> Path | None:
        roots = self.roots if self.roots is not None else find_traktor_roots()
        for root in roots:
            if (root / "History").is_dir() or (root / "collection.nml").is_file():
                return root
        return None

    @staticmethod
    def _history_entries(file: Path):
        root = ET.parse(file).getroot()
        entries = []
        for entry in root.findall(".//PLAYLISTS//PLAYLIST/ENTRY"):
            extended = entry.find("EXTENDEDDATA")
            if extended is not None and extended.get("EXTENDEDTYPE") not in (None, "HistoryData"):
                continue
            primary = entry.find("PRIMARYKEY")
            if primary is not None and primary.get("KEY"):
                entries.append(primary.get("KEY"))
        return entries

    def load(self, force: bool = False) -> HistorySnapshot | None:
        root = self._root()
        if root is None:
            return None
        collection_file = root / "collection.nml"
        history_dir = root / "History"
        files = sorted(history_dir.glob("*.nml"), key=lambda p: (p.stat().st_mtime_ns, p.name)) \
            if history_dir.is_dir() else []
        signature = (
            (collection_file.name, collection_file.stat().st_size, collection_file.stat().st_mtime_ns)
            if collection_file.is_file() else None,
            tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in files),
        )
        if self._snapshot is not None and not force and signature == self._signature:
            return self._snapshot
        try:
            index, tracks = _collection_index(collection_file)
        except (OSError, ET.ParseError):
            index, tracks = {}, []
        sessions: list[tuple[Path, list[HistoryPlay]]] = []
        for session_id, file in enumerate(files, 1):
            try:
                keys = self._history_entries(file)
            except (OSError, ET.ParseError):
                continue
            session = []
            for position, key in enumerate(keys):
                track = _lookup_track(key, index) or {
                    "path": key, "title": Path(key.replace("\\", "/")).stem,
                    "artist": "", "bpm": None, "key": None,
                }
                session.append(HistoryPlay(session_id, track["path"], track["title"],
                                           track["artist"], track["bpm"], track["key"],
                                           position, position + 1, True))
            if session:
                sessions.append((file, session))

        transitions: dict[str, Counter] = defaultdict(Counter)
        for _, session in sessions:
            for previous, following in zip(session, session[1:]):
                if previous.path.casefold() != following.path.casefold():
                    transitions[previous.path.casefold()][following.path.casefold()] += 1

        all_plays = []
        seen_paths = set()
        session_id = len(sessions)
        for track in tracks:
            key = track["path"].casefold()
            if key not in seen_paths:
                all_plays.append(HistoryPlay(session_id, track["path"], track["title"],
                                             track["artist"], track["bpm"], track["key"],
                                             0, 0, False))
                seen_paths.add(key)
        for _, session in sessions:
            for play in session:
                if play.path.casefold() not in seen_paths:
                    all_plays.append(play)
                    seen_paths.add(play.path.casefold())

        latest_file, latest_plays = sessions[-1] if sessions else (None, [])
        timestamp = int(latest_file.stat().st_mtime) if latest_file else None
        current_play = latest_plays[-1] if latest_plays else None
        snapshot = HistorySnapshot(all_plays, dict(transitions), current_play,
                                   latest_plays, False, signature, timestamp)
        self._snapshot, self._signature = snapshot, signature
        return snapshot
