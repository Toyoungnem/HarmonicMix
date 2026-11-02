"""Contrôleur : lecture Serato, calcul des suggestions et cycle d'actualisation."""
from __future__ import annotations

import os
import ctypes
import time
from datetime import datetime
from pathlib import Path
import sys

from database import HistoryDatabase
from live import latest_logged_track
from metadata import AudioMetadata, MutagenFile, read_metadata
from parser import DEFAULT_SESSIONS_DIR, TrackPlay, parse_session
from serato_db import HistoryPlay, SeratoLibrary
from scoring import camelot_number, rank_candidates
from serato_control import search_track_in_serato
import customtkinter as ctk

from ui import COLORS, SuggestionUI

if getattr(sys, "frozen", False):
    APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "HarmonicMix"
else:
    APP_DIR = Path(__file__).resolve().parent
DB = HistoryDatabase(APP_DIR / "suggestions.sqlite3")


class SuggestionApp:
    """Orchestre les données; la fenêtre et son style vivent dans ui.py."""

    def __init__(self, root):
        self.root = root
        self.meta_cache: dict[str, AudioMetadata] = {}
        self.native_library = SeratoLibrary()
        self.native_snapshot = None
        self.history_plays = []
        self.legacy_transition_counts = {}
        self.native_metadata = {}
        self.last_native_signature = None
        self.using_serato_database = False
        self.current_session: Path | None = None
        self.current_play = None
        self.session_plays = []
        self.live_log_time = None
        self.ui = SuggestionUI(
            root,
            on_refresh=lambda: self.refresh(schedule=False),
            on_close=self.close,
            on_search=self.search_suggestion,
        )
        self.refresh()

    def _latest_session(self):
        files = list(DEFAULT_SESSIONS_DIR.glob("*.session"))
        return max(files, key=lambda p: (p.stat().st_mtime_ns, p.name)) if files else None

    @staticmethod
    def _serato_is_running():
        if os.name != "nt":
            return False
        try:
            return bool(ctypes.windll.user32.FindWindowW(None, "Serato DJ Lite"))
        except (AttributeError, OSError):
            return False

    def refresh(self, schedule=True):
        try:
            snapshot = self.native_library.load(force=not schedule)
            if snapshot and snapshot.plays:
                self.using_serato_database = True
                changed = snapshot.signature != self.last_native_signature
                if changed or self.current_play is None:
                    self.native_snapshot = snapshot
                    self.history_plays = snapshot.plays
                    self.session_plays = snapshot.current_session_plays
                    self.current_play = snapshot.current_play or max(
                        snapshot.plays, key=lambda p: p.start_time, default=None)
                    self.native_metadata = {
                        play.path.casefold(): AudioMetadata(play.bpm, play.key)
                        for play in snapshot.plays
                    }
                    self.legacy_transition_counts = {}
                    self.last_native_signature = snapshot.signature
                    self._update_display()
            else:
                self.using_serato_database = False
                changed, newest = DB.refresh(DEFAULT_SESSIONS_DIR)
                if changed or self.current_play is None:
                    self._load_session_fallback(newest)
                    self._update_display()
        except (OSError, ValueError) as exc:
            self.ui.show_error(f"Lecture impossible : {exc}")
        if schedule:
            self.root.after(5000, self.refresh)

    def _load_session_fallback(self, newest):
        file = Path(newest) if newest else None
        self.current_session = file
        parsed = parse_session(file) if file and file.is_file() else []
        logged = latest_logged_track()
        self.live_log_time = logged[1] if logged else None
        if logged:
            path = logged[0]
            row = next((r for r in DB.all_plays()
                        if r["path"].casefold() == path.casefold()), None)
            self.current_play = TrackPlay(
                path, (row["title"] if row else None) or Path(path).stem,
                (row["artist"] if row else None), None, None)
        else:
            self.current_play = parsed[-1] if parsed else None
        self.history_plays = [HistoryPlay(
            0, row["path"], row["title"] or Path(row["path"]).stem,
            row["artist"] or "", None, None, 0, 0, True)
            for row in DB.all_plays()]
        self.session_plays = [HistoryPlay(
            0, play.path, play.title or Path(play.path).stem, play.artist or "",
            None, None, 0, 0, True) for play in parsed]
        self.legacy_transition_counts = {}
        if self.current_play:
            self.legacy_transition_counts = {
                row[0].casefold(): int(row[3])
                for row in DB.transition_counts(self.current_play.path)
            }
        self.native_metadata = {}

    def _update_display(self):
        play = self.current_play
        if not play:
            self.ui.render(
                "En attente de Serato", str(DEFAULT_SESSIONS_DIR),
                "HISTORIQUE", COLORS["gold"], [],
            )
            return

        current_meta = self._metadata(play.path)
        current_key = camelot_number(current_meta.key or "")
        details = []
        if play.artist:
            details.append(play.artist)
        if current_meta.bpm:
            details.append(f"{current_meta.bpm:g} BPM")
        if current_meta.key:
            key_label = current_meta.key
            if current_key:
                key_label += f" · {current_key[0]}{current_key[1]}"
            details.append(key_label)

        serato_open = self._serato_is_running()
        if self.using_serato_database and self.native_snapshot.active_session and serato_open:
            status, status_color = "● EN DIRECT", COLORS["mint"]
        elif serato_open and self.live_log_time and time.time() - self.live_log_time < 120:
            status, status_color = "● SERATO", COLORS["mint"]
        elif self.history_plays:
            timestamp = (self.native_snapshot.last_session_timestamp
                         if self.using_serato_database and self.native_snapshot
                         else None)
            if timestamp is None and self.current_session and self.current_session.is_file():
                try:
                    timestamp = int(self.current_session.stat().st_mtime)
                except OSError:
                    pass
            date_text = datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y") if timestamp else ""
            status = f"SESSION TERMINÉE · {date_text}" if date_text else "SESSION TERMINÉE"
            status_color = COLORS["gold"]
        elif serato_open:
            status, status_color = "SERATO OUVERT · EN ATTENTE", COLORS["violet"]
        else:
            status, status_color = "HISTORIQUE", COLORS["gold"]

        if self.using_serato_database:
            counts = self.native_snapshot.transitions.get(play.path.casefold(), {})
        else:
            counts = self.legacy_transition_counts

        unique = {}
        counted_paths = set()
        current_identity = self._track_identity(play.title, play.artist, play.path)
        for row in self.history_plays:
            if row.path.casefold() == play.path.casefold():
                continue
            identity = self._track_identity(row.title, row.artist, row.path)
            if identity == current_identity:
                continue
            item = unique.setdefault(identity, [row.path, row.title, row.artist, 0])
            path_key = row.path.casefold()
            if path_key not in counted_paths:
                item[3] += counts.get(path_key, 0)
                counted_paths.add(path_key)

        candidates = list(unique.values())
        metadata = {path: self._metadata(path) for path, *_ in candidates}
        played_paths = {track.path for track in self.session_plays}
        suggestions = rank_candidates(
            play.path, current_meta, candidates, metadata, played_paths)

        self.ui.render(
            play.title or Path(play.path).name,
            "  ·  ".join(details) or "Session Serato active",
            status, status_color, suggestions,
        )

    def _metadata(self, path):
        native = self.native_metadata.get(path.casefold())
        if native and (native.bpm is not None or native.key):
            return native
        if path not in self.meta_cache:
            self.meta_cache[path] = read_metadata(path)
        return self.meta_cache[path]

    def search_suggestion(self, suggestion):
        self.ui.show_search_result(f"Recherche en cours : {suggestion.title}…")
        try:
            search_track_in_serato(
                self.root, suggestion.path, suggestion.title,
                suggestion.artist,
                on_complete=lambda error: self._search_finished(suggestion, error),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self.ui.show_search_result(str(exc), success=False)

    def _search_finished(self, suggestion, error):
        if error:
            self.ui.show_search_result(error, success=False)
        else:
            self.ui.show_search_result(
                f"Trouvé dans Serato : {suggestion.title}. Choisis ensuite le deck."
            )

    @staticmethod
    def _track_identity(title, artist, path):
        import unicodedata

        def clean(value):
            value = unicodedata.normalize("NFKC", value or "")
            value = "".join(ch for ch in value if unicodedata.category(ch) not in ("Cf", "Cc"))
            return " ".join(value.casefold().split())

        return clean(title) or clean(Path(path).stem), clean(artist)

    def close(self):
        self.native_library.close()
        self.root.destroy()


def main():
    root = ctk.CTk()
    icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "HarmonicMix.ico"
    if icon.is_file():
        try:
            root.iconbitmap(str(icon))
        except Exception:
            pass
    SuggestionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
