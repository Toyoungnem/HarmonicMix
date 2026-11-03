"""Lecture seule de la base bibliothèque/historique locale de Serato DJ Lite."""
from __future__ import annotations

import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SERATO_DB = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Serato" / "Library" / "master.sqlite"


def _track_path(portable_id: str | None) -> str:
    value = (portable_id or "").replace("/", "\\")
    if len(value) >= 3 and value[1:3] == ":\\":
        return value
    # Sur Windows, Serato stocke souvent le chemin relatif à la racine du volume.
    drive = os.environ.get("SystemDrive", "C:")
    return str(Path(drive + "\\") / value.lstrip("\\"))


# Serato enregistre parfois un chemin relatif dont le dossier racine a changé
# (téléchargements last.fm : tout arrive sous un dossier « Contents/… »). On
# cherche alors les derniers segments du chemin sous les dossiers musique.
_MUSIC_ROOTS = [Path.home() / "Music", Path.home() / "Musique",
                Path.home() / "Desktop", Path.home() / "Downloads"]
_RESOLVED: dict[str, str] = {}
_INDEX: dict[str, str] | None = None


def _music_index() -> dict[str, str]:
    """Index « 4 derniers dossiers + nom du fichier » -> chemin réel.

    Construit une seule fois (parcours des dossiers musique), puis réutilisé :
    sans ce cache, résoudre 6 500 chemins coûtait plusieurs minutes.
    """
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    index: dict[str, str] = {}
    for root in _MUSIC_ROOTS:
        if not root.is_dir():
            continue
        for folder, _dirs, files in os.walk(root):
            parts = Path(folder).parts
            tail = os.path.join(*parts[-4:]) if len(parts) >= 4 else os.path.join(*parts)
            for name in files:
                index.setdefault(os.path.join(tail, name).casefold(), os.path.join(folder, name))
                index.setdefault(os.path.join(parts[-1], name).casefold(),
                                 os.path.join(folder, name))
    _INDEX = index
    return index


def _resolve_path(path: str) -> str:
    """Chemin réel d'un fichier Serato, en corrigeant les chemins déplacés."""
    known = _RESOLVED.get(path)
    if known is not None:
        return known
    resolved = path
    if not os.path.isfile(path):
        index = _music_index()
        parts = Path(path).parts[1:]
        if parts:
            for size in (4, 3, 2, 1):
                if len(parts) < size:
                    continue
                candidate = index.get(os.path.join(*parts[-size:]).casefold())
                if candidate:
                    resolved = candidate
                    break
    _RESOLVED[path] = resolved
    return resolved


def _row_dict(row) -> dict:
    """Ligne sqlite3 -> dictionnaire (accès par clé .get sans lever d'erreur)."""
    if row is None:
        return {}
    try:
        return dict(row)
    except (TypeError, ValueError):
        return {}


def _first_text(*values) -> str:
    """Premier texte non vide parmi les valeurs proposées."""
    for value in values:
        if value is None:
            continue
        try:
            text = str(value).strip()
        except Exception:
            continue
        if text:
            return text
    return ""


@dataclass(frozen=True)
class HistoryPlay:
    session_id: int
    path: str
    title: str
    artist: str
    bpm: float | None
    key: str | None
    start_time: int
    end_time: int
    played: bool
    genre: str = ""
    album: str = ""


@dataclass
class HistorySnapshot:
    plays: list[HistoryPlay]
    transitions: dict[str, Counter]
    current_play: HistoryPlay | None
    current_session_plays: list[HistoryPlay]
    active_session: bool
    signature: tuple
    last_session_timestamp: int | None
    session_count: int = 0
    played_track_count: int = 0
    session_activity: list[dict] | None = None


class SeratoLibrary:
    """Lit master.sqlite sans jamais écrire dans la base que Serato utilise."""

    def __init__(self, db_path: Path = SERATO_DB):
        self.db_path = db_path
        self._connection = None
        self._data_version = None
        self._snapshot = None

    def _connect(self):
        if self._connection is None:
            if not self.db_path.is_file():
                return None
            uri = self.db_path.resolve().as_uri() + "?mode=ro"
            self._connection = sqlite3.connect(uri, uri=True, timeout=1.5,
                                                isolation_level=None)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA busy_timeout=1500")
        return self._connection

    def _probe_signature(self, conn):
        count, last_entry_id = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM history_entry"
        ).fetchone()
        session = conn.execute(
            "SELECT id, start_time, end_time FROM history_session ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if session:
            last_entry = conn.execute("""
                SELECT id, start_time, end_time, played
                FROM history_entry WHERE session_id=? ORDER BY id DESC LIMIT 1
            """, (session["id"],)).fetchone()
        else:
            last_entry = None
        return (count, last_entry_id,
                tuple(session) if session else None,
                tuple(last_entry) if last_entry else None)

    def load(self, force: bool = False) -> HistorySnapshot | None:
        if not self.db_path.is_file():
            return None
        conn = self._connect()
        if conn is None:
            return None
        try:
            data_version = conn.execute("PRAGMA data_version").fetchone()[0]
            if self._snapshot is not None and not force and data_version == self._data_version:
                return self._snapshot
            signature = self._probe_signature(conn)
            if self._snapshot is not None and not force and signature == self._snapshot.signature:
                self._data_version = data_version
                return self._snapshot
            rows = conn.execute("""
                SELECT h.session_id, h.id AS entry_id, h.portable_id, h.name, h.artist, h.genre,
                       h.bpm, h.key, h.start_time, h.end_time, h.played,
                       s.start_time AS session_start, s.end_time AS session_end
                FROM history_entry h
                JOIN history_session s ON s.id = h.session_id
                ORDER BY h.session_id, h.start_time, h.id
            """).fetchall()
            sessions = conn.execute(
                "SELECT id, start_time, end_time FROM history_session ORDER BY id"
            ).fetchall()
            # Métadonnées de bibliothèque : genre réel, commentaires, pochette.
            try:
                metadata_rows = conn.execute(
                    "SELECT portable_id, genre, name, artist, album FROM asset"
                ).fetchall()
            except sqlite3.Error:
                metadata_rows = []
        except sqlite3.Error:
            return None
        library = {_track_path(row["portable_id"]).casefold(): _row_dict(row)
                   for row in metadata_rows if row["portable_id"]}

        plays = []
        for row in rows:
            if not row["portable_id"]:
                continue
            raw_path = _track_path(row["portable_id"])
            track_path = _resolve_path(raw_path)
            extra = _row_dict(library.get(raw_path.casefold()))
            plays.append(HistoryPlay(
                session_id=row["session_id"],
                path=track_path,
                title=(row["name"] or extra.get("name") or row["portable_id"] or "Morceau"),
                artist=(row["artist"] or extra.get("artist") or ""),
                bpm=float(row["bpm"]) if row["bpm"] is not None else None,
                key=row["key"] or None,
                start_time=int(row["start_time"] or 0),
                end_time=int(row["end_time"] or 0),
                played=bool(row["played"]),
                genre=_first_text(row["genre"], extra.get("genre")),
                album=extra.get("album") or "",
            ))

        transitions: dict[str, Counter] = defaultdict(Counter)
        grouped: dict[int, list[HistoryPlay]] = defaultdict(list)
        for play in plays:
            if play.played:
                grouped[play.session_id].append(play)
        for session_plays in grouped.values():
            for previous, following in zip(session_plays, session_plays[1:]):
                if previous.path.casefold() != following.path.casefold():
                    transitions[previous.path.casefold()][following.path.casefold()] += 1

        latest_session = sessions[-1] if sessions else None
        active_session = bool(latest_session and latest_session["end_time"] in (None, -1))
        active_id = latest_session["id"] if latest_session else None
        timestamp = None
        if latest_session:
            timestamp = latest_session["end_time"]
            if timestamp in (None, -1, 0):
                timestamp = latest_session["start_time"]
            timestamp = int(timestamp) if timestamp else None
        session_plays = [p for p in plays if p.session_id == active_id and p.played]
        active_deck_plays = [p for p in session_plays if p.end_time == -1]
        current_play = max(active_deck_plays or session_plays,
                           key=lambda p: (p.start_time, p.session_id), default=None)
        session_activity = []
        for session in sessions:
            session_plays_for_stats = grouped.get(session["id"], [])
            transition_total = sum(
                1 for first, second in zip(session_plays_for_stats, session_plays_for_stats[1:])
                if first.path.casefold() != second.path.casefold())
            session_timestamp = session["end_time"]
            if session_timestamp in (None, -1, 0):
                session_timestamp = session["start_time"]
            try:
                date_label = datetime.fromtimestamp(int(session_timestamp)).strftime("%d/%m")
            except (TypeError, ValueError, OSError, OverflowError):
                date_label = f"Set {len(session_activity) + 1}"
            genres = Counter(play.genre.strip() for play in session_plays_for_stats if play.genre.strip())
            bpms = [play.bpm for play in session_plays_for_stats if play.bpm]
            session_activity.append({
                "label": date_label,
                "tracks": len(session_plays_for_stats),
                "transitions": transition_total,
                "genres": dict(genres),
                "average_bpm": round(sum(bpms) / len(bpms), 1) if bpms else None,
            })

        snapshot = HistorySnapshot(plays, dict(transitions), current_play, session_plays,
                                   active_session, signature, timestamp,
                                   len(sessions), sum(1 for play in plays if play.played),
                                   session_activity)
        self._snapshot = snapshot
        self._data_version = conn.execute("PRAGMA data_version").fetchone()[0]
        return snapshot

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
