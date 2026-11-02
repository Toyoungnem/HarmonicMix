"""Contrôleur : lecture Serato, calcul des suggestions et cycle d'actualisation."""
from __future__ import annotations

import os
import ctypes
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from shutil import copy2
from tkinter import simpledialog

from database import HistoryDatabase
from artwork import read_cover
from live import latest_logged_track
from metadata import AudioMetadata, MutagenFile, read_metadata
from parser import DEFAULT_SESSIONS_DIR, TrackPlay, parse_session
from serato_db import HistoryPlay, SeratoLibrary
from scoring import camelot_number, rank_candidates
from serato_control import search_track_in_serato
from traktor_control import search_track_in_traktor
from profiles import LocalProfiles
from traktor_db import TraktorLibrary, find_traktor_roots
import customtkinter as ctk

from ui import COLORS, SuggestionUI

APP_DIR = Path(__file__).resolve().parent
LOCAL_DATA_DIR = Path(os.environ.get(
    "LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "HarmonicMix"


class SuggestionApp:
    """Orchestre les données; la fenêtre et son style vivent dans ui.py."""

    def __init__(self, root):
        self.root = root
        self.profiles = LocalProfiles(LOCAL_DATA_DIR)
        self.profile = self.profiles.current
        self.db = self._profile_database(self.profile)
        self.software = self.profile.get("software", "serato")
        self.meta_cache: dict[str, AudioMetadata] = {}
        self.native_library = SeratoLibrary()
        self.traktor_library = TraktorLibrary()
        self.native_snapshot = None
        self.history_plays = []
        self.legacy_transition_counts = {}
        self.native_metadata = {}
        self.last_native_signature = None
        self.using_serato_database = False
        self.using_traktor = False
        self.current_session: Path | None = None
        self.current_play = None
        self.session_plays = []
        self.live_log_time = None
        self.search_busy = False
        self.search_refresh_pause_until = 0.0
        self.search_cooldown_generation = 0
        self.cover_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hm-cover")
        self.cover_requests = set()
        self.ui = SuggestionUI(
            root,
            on_refresh=lambda: self.refresh(schedule=False),
            on_close=self.close,
            on_search=self.search_suggestion,
            on_profile_select=self.change_profile,
            on_software_select=self.select_software,
            on_stats=self.show_stats,
            on_cover_request=self._request_cover,
            profile_name=self.profile["name"],
            software=self.software,
        )
        self.refresh()

    def _profile_database(self, profile):
        if profile["id"] == "nel":
            path = LOCAL_DATA_DIR / "suggestions.sqlite3"
            legacy = APP_DIR / "suggestions.sqlite3"
            if not path.exists() and legacy.is_file() and legacy.resolve() != path.resolve():
                try:
                    copy2(legacy, path)
                except OSError:
                    pass
        else:
            path = LOCAL_DATA_DIR / "profiles" / profile["id"] / "suggestions.sqlite3"
        return HistoryDatabase(path)

    def change_profile(self):
        existing = ", ".join(self.profiles.names)
        name = simpledialog.askstring(
            "Profil local", f"Entre un profil existant ou un nouveau nom.\nProfils : {existing}",
            parent=self.root)
        if not name or not name.strip():
            return
        self.profile = self.profiles.activate_or_create(name)
        self.db = self._profile_database(self.profile)
        self.software = self.profile.get("software", "serato")
        self.meta_cache.clear()
        self.current_play = None
        self.native_snapshot = None
        self.last_native_signature = None
        self.ui.set_profile(self.profile["name"])
        self.ui.set_software(self.software)
        self.refresh(schedule=False)

    def select_software(self, software):
        if software == self.software:
            return
        self.software = software
        self.profiles.set_software(software)
        self.profile = self.profiles.current
        self.ui.set_software(software)
        self.current_play = None
        self.native_snapshot = None
        self.last_native_signature = None
        self.refresh(schedule=False)

    def show_stats(self):
        self.ui.show_stats(self._transition_statistics())

    def _transition_statistics(self):
        software_name = "Serato DJ" if self.software == "serato" else "Traktor"
        if self.native_snapshot is not None and (self.using_serato_database or self.using_traktor):
            title_by_path = {play.path.casefold(): play.title for play in self.history_plays}
            transitions = []
            for source, destinations in self.native_snapshot.transitions.items():
                for target, count in destinations.items():
                    transitions.append({
                        "source_path": source,
                        "source_title": title_by_path.get(source, Path(source).stem),
                        "target_path": target,
                        "target_title": title_by_path.get(target, Path(target).stem),
                        "count": int(count),
                    })
            transitions.sort(key=lambda row: (-row["count"],
                                               row["source_title"].casefold(),
                                               row["target_title"].casefold()))
            stats = {
                "sessions": self.native_snapshot.session_count,
                "tracks": self.native_snapshot.played_track_count,
                "transitions": transitions,
                "session_activity": self.native_snapshot.session_activity or [],
            }
        elif self.using_traktor:
            stats = {"sessions": 0, "tracks": 0, "transitions": [], "session_activity": []}
        else:
            stats = self.db.transition_statistics()

        destinations = {}
        for row in stats["transitions"]:
            key = row["target_path"].casefold()
            entry = destinations.setdefault(key, {
                "title": row["target_title"] or Path(row["target_path"]).stem,
                "path": row["target_path"],
                "count": 0,
            })
            entry["count"] += row["count"]
        stats["destinations"] = sorted(
            destinations.values(), key=lambda item: (-item["count"], item["title"].casefold()))[:5]
        stats["distinct_transitions"] = len(stats["transitions"])
        stats["transition_count"] = sum(row["count"] for row in stats["transitions"])
        stats["top_transitions"] = stats["transitions"][:10]
        stats["software"] = software_name
        stats["last_session"] = self._last_session_date() or "Aucune session trouvée"
        stats["active_session"] = bool(
            self.using_serato_database and self.native_snapshot
            and self.native_snapshot.active_session
        )
        return stats

    def _last_session_date(self):
        timestamp = None
        if self.native_snapshot is not None:
            timestamp = self.native_snapshot.last_session_timestamp
        if timestamp is None and self.current_session and self.current_session.is_file():
            try:
                timestamp = int(self.current_session.stat().st_mtime)
            except OSError:
                pass
        return datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y") if timestamp else ""

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
        if self.search_busy or time.monotonic() < self.search_refresh_pause_until:
            if schedule:
                self.root.after(1200, self.refresh)
            return
        try:
            if self.software == "traktor":
                snapshot = self.traktor_library.load(force=not schedule)
                self.using_serato_database = False
                self.using_traktor = True
                if snapshot and snapshot.plays and snapshot.current_play:
                    changed = snapshot.signature != self.last_native_signature
                    if changed or self.current_play is None:
                        self.native_snapshot = snapshot
                        self.history_plays = snapshot.plays
                        self.session_plays = snapshot.current_session_plays
                        self.current_play = snapshot.current_play
                        self.native_metadata = {
                            play.path.casefold(): AudioMetadata(play.bpm, play.key)
                            for play in snapshot.plays
                        }
                        self.legacy_transition_counts = {}
                        self.last_native_signature = snapshot.signature
                        self._update_display()
                else:
                    self.native_snapshot = snapshot
                    self.current_play = None
                    self.history_plays = []
                    self.session_plays = []
                    self.native_metadata = {}
                    roots = find_traktor_roots()
                    location = str(roots[0]) if roots else (
                        str(Path.home() / "Documents" / "Native Instruments" / "Traktor*"))
                    self.ui.render(
                        "Aucune session Traktor archivée", location,
                        "HISTORIQUE TRAKTOR INTROUVABLE", COLORS["gold"], [],
                    )
            else:
                self.using_traktor = False
                self.traktor_library = TraktorLibrary()
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
                    changed, newest = self.db.refresh(DEFAULT_SESSIONS_DIR)
                    if changed or self.current_play is None:
                        self._load_session_fallback(newest)
                        self._update_display()
        except (OSError, ValueError, ET.ParseError) as exc:
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
            row = next((r for r in self.db.all_plays()
                        if r["path"].casefold() == path.casefold()), None)
            self.current_play = TrackPlay(
                path, (row["title"] if row else None) or Path(path).stem,
                (row["artist"] if row else None), None, None)
        else:
            self.current_play = parsed[-1] if parsed else None
        self.history_plays = [HistoryPlay(
            0, row["path"], row["title"] or Path(row["path"]).stem,
            row["artist"] or "", None, None, 0, 0, True)
            for row in self.db.all_plays()]
        self.session_plays = [HistoryPlay(
            0, play.path, play.title or Path(play.path).stem, play.artist or "",
            None, None, 0, 0, True) for play in parsed]
        self.legacy_transition_counts = {}
        if self.current_play:
            self.legacy_transition_counts = {
                row[0].casefold(): int(row[3])
                for row in self.db.transition_counts(self.current_play.path)
            }
        self.native_metadata = {}

    def _update_display(self):
        play = self.current_play
        if not play:
            name = "Traktor" if self.using_traktor else "Serato"
            self.ui.render(
                f"En attente de {name}",
                ("Ferme Traktor pour enregistrer une session dans History." if self.using_traktor
                 else str(DEFAULT_SESSIONS_DIR)),
                "HISTORIQUE TRAKTOR INTROUVABLE" if self.using_traktor else "HISTORIQUE",
                COLORS["gold"], [],
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
        serato_session_open = False
        if self.using_traktor:
            timestamp = self.native_snapshot.last_session_timestamp if self.native_snapshot else None
            date_text = datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y") if timestamp else ""
            status = f"SESSION TRAKTOR · {date_text}" if date_text else "HISTORIQUE TRAKTOR"
            status_color = COLORS["violet"]
        elif self.using_serato_database and self.native_snapshot.active_session and serato_open:
            status, status_color = "● EN DIRECT", COLORS["mint"]
            serato_session_open = True
        elif serato_open and self.live_log_time and time.time() - self.live_log_time < 120:
            status, status_color = "● SERATO", COLORS["mint"]
            serato_session_open = True
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

        if self.using_serato_database or self.using_traktor:
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
        recent_paths = [track.path for track in self.session_plays[-4:-1]]
        recent_bpms = [track.bpm for track in self.session_plays[-4:]
                       if track.bpm is not None]
        bpm_momentum = 0
        if len(recent_bpms) >= 2 and recent_bpms[-1] - recent_bpms[0] >= 2:
            bpm_momentum = 1
        elif len(recent_bpms) >= 2 and recent_bpms[-1] - recent_bpms[0] <= -2:
            bpm_momentum = -1
        suggestions = rank_candidates(
            play.path, current_meta, candidates, metadata, played_paths,
            recent_paths=recent_paths,
            bpm_momentum=bpm_momentum,
        )

        display_title = play.title or Path(play.path).name
        display_detail = "  ·  ".join(details) or (
            "Historique Traktor" if self.using_traktor else "Session Serato active")
        if not self.using_traktor and not serato_session_open:
            display_title = self._last_session_date() or "Aucune session enregistrée"
            display_detail = ""

        self.ui.render(
            display_title,
            display_detail,
            status, status_color, suggestions,
            session_date=self._last_session_date(),
            session_detail=("Traktor · session archivée" if self.using_traktor
                            else "Serato DJ · historique local"),
            cover_path=play.path,
        )
        if getattr(self.ui, "active_page", "") == "stats":
            self.show_stats()

    def _metadata(self, path):
        native = self.native_metadata.get(path.casefold())
        if native and (native.bpm is not None or native.key):
            return native
        if path not in self.meta_cache:
            self.meta_cache[path] = read_metadata(path)
        return self.meta_cache[path]

    def _request_cover(self, path):
        key = str(path).casefold()
        if key in self.cover_requests:
            return
        self.cover_requests.add(key)
        future = self.cover_executor.submit(read_cover, str(path))

        def complete(result):
            try:
                data = result.result()
            except Exception:
                data = None
            self.cover_requests.discard(key)
            try:
                self.root.after(0, self.ui.set_cover, str(path), data)
            except Exception:
                pass

        future.add_done_callback(complete)

    def search_suggestion(self, suggestion):
        if self.search_busy:
            self.ui.show_search_result(
                "Recherche déjà en cours. Attends qu'elle se termine…", busy=True)
            return
        self.search_busy = True
        software_name = "Serato DJ" if self.software == "serato" else "Traktor"
        self.ui.show_search_result(
            f"Recherche de « {suggestion.title} » dans {software_name}…",
            busy=True,
        )
        try:
            complete = lambda error: self._search_finished(suggestion, error)
            if self.software == "traktor":
                search_track_in_traktor(self.root, suggestion.title, suggestion.artist, complete)
            else:
                search_track_in_serato(
                    self.root, suggestion.path, suggestion.title,
                    suggestion.artist, on_complete=complete,
                )
        except (OSError, RuntimeError, ValueError) as exc:
            self._search_finished(suggestion, str(exc))

    def _search_finished(self, suggestion, error):
        self.search_busy = False
        # Laisse le logiciel DJ terminer son filtrage avant la prochaine lecture
        # de sa base SQLite, susceptible d'être occupée pendant la recherche.
        self.search_refresh_pause_until = time.monotonic() + 4.0
        self.search_cooldown_generation += 1
        generation = self.search_cooldown_generation
        if error:
            self.ui.show_search_result(error, success=False, pause_refresh=True)
        else:
            software_name = "Traktor" if self.software == "traktor" else "Serato"
            self.ui.show_search_result(
                f"Recherche envoyée dans {software_name}. Vérifie le résultat puis choisis le deck.",
                pause_refresh=True,
            )
        self.root.after(4000, lambda: self._resume_search_refresh(generation))

    def _resume_search_refresh(self, generation):
        if generation != self.search_cooldown_generation:
            return
        self.search_refresh_pause_until = 0.0
        if not self.search_busy:
            self.ui.refresh_button.configure(state="normal")

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
        self.cover_executor.shutdown(wait=False, cancel_futures=True)
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
