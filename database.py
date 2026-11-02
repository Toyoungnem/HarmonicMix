"""Import des sessions et graphe de transitions stockés en SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from parser import parse_session


class HistoryDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS plays (
                    session TEXT NOT NULL, position INTEGER NOT NULL,
                    path TEXT NOT NULL, title TEXT, artist TEXT,
                    start_time TEXT, end_time TEXT,
                    PRIMARY KEY (session, position)
                );
                CREATE INDEX IF NOT EXISTS plays_path ON plays(path);
            """)

    def connect(self):
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def signature(folder: Path):
        files = sorted(folder.glob("*.session"))
        return tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in files)

    def refresh(self, folder: Path) -> tuple[bool, str | None]:
        """Réimporte si les fichiers ont changé; renvoie (modifié, session récente)."""
        files = sorted(folder.glob("*.session"), key=lambda p: (p.stat().st_mtime_ns, p.name))
        signature = self.signature(folder)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            old = db.execute("SELECT value FROM settings WHERE key='signature'").fetchone()
            if old and old[0] == repr(signature):
                return False, str(files[-1]) if files else None
            db.execute("DELETE FROM plays")
            for file in files:
                try:
                    plays = parse_session(file)
                except (OSError, ValueError):
                    # Serato peut être en train d'écrire la session : l'import suivant réessaiera.
                    continue
                db.executemany(
                    "INSERT INTO plays VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(str(file), i, p.path, p.title, p.artist,
                      p.start_time.isoformat() if p.start_time else None,
                      p.end_time.isoformat() if p.end_time else None)
                     for i, p in enumerate(plays)],
                )
            db.execute("INSERT OR REPLACE INTO settings VALUES ('signature', ?)", (repr(signature),))
            db.commit()
        return True, str(files[-1]) if files else None

    def all_plays(self):
        with self.connect() as db:
            return db.execute("SELECT * FROM plays ORDER BY session, position").fetchall()

    def transition_counts(self, source_path: str):
        with self.connect() as db:
            return db.execute("""
                SELECT b.path, COALESCE(b.title, ''), COALESCE(b.artist, ''), COUNT(*) AS count
                FROM plays a JOIN plays b ON a.session=b.session AND b.position=a.position+1
                WHERE lower(a.path)=lower(?) AND lower(b.path)<>lower(a.path)
                GROUP BY lower(b.path), b.path, b.title, b.artist
                ORDER BY count DESC
            """, (source_path,)).fetchall()

