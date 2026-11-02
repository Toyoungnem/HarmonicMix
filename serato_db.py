"""Lecture seule de la base bibliothèque/historique locale de Serato DJ Lite."""
from __future__ import annotations

import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


SERATO_DB = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Serato" / "Library" / "master.sqlite"


def _track_path(portable_id: str | None) -> str:
    value = (portable_id or "").replace("/", "\\")
    if len(value) >= 3 and value[1:3] == ":\\":
        return value
    # Sur Windows, Serato stocke souvent le chemin relatif à la racine du volume.
    drive = os.environ.get("SystemDrive", "C:")
    return str(Path(drive + "\\") / value.lstrip("\\"))


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


@dataclass
class HistorySnapshot:
    plays: list[HistoryPlay]
    transitions: dict[str, Counter]
    current_play: HistoryPlay | None
    current_session_plays: list[HistoryPlay]
    active_session: bool
    signature: tuple
    last_session_timestamp: int | None


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
                SELECT h.session_id, h.id AS entry_id, h.portable_id, h.name, h.artist,
                       h.bpm, h.key, h.start_time, h.end_time, h.played,
                       s.start_time AS session_start, s.end_time AS session_end
                FROM history_entry h
                JOIN history_session s ON s.id = h.session_id
                ORDER BY h.session_id, h.start_time, h.id
            """).fetchall()
            sessions = conn.execute(
                "SELECT id, start_time, end_time FROM history_session ORDER BY id"
            ).fetchall()
        except sqlite3.Error:
            return None

        plays = [HistoryPlay(
            session_id=row["session_id"],
            path=_track_path(row["portable_id"]),
            title=(row["name"] or row["portable_id"] or "Morceau"),
            artist=(row["artist"] or ""),
            bpm=float(row["bpm"]) if row["bpm"] is not None else None,
            key=row["key"] or None,
            start_time=int(row["start_time"] or 0),
            end_time=int(row["end_time"] or 0),
            played=bool(row["played"]),
        ) for row in rows if row["portable_id"]]

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
        snapshot = HistorySnapshot(plays, dict(transitions), current_play, session_plays,
                                   active_session, signature, timestamp)
        self._snapshot = snapshot
        self._data_version = conn.execute("PRAGMA data_version").fetchone()[0]
        return snapshot

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
