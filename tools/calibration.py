"""Calibration du classement sur l'historique Serato réel (lecture seule).

Mesure le taux de réussite des suggestions en masquant une partie des
transitions réellement jouées : on retire 30 % des enchaînements de l'apprentis-
sage, puis on vérifie si le morceau qui suivait vraiment apparaît dans le
top 1/3/5 proposé.

    python tools/calibration.py            # mesure
    python tools/calibration.py --legacy   # compare à l'ancien moteur (clé/2 poids)

Rien n'est écrit : la base Serato est ouverte en mode lecture seule.
"""
from __future__ import annotations

import random
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scoring  # noqa: E402
from metadata import AudioMetadata  # noqa: E402
from serato_db import SERATO_DB  # noqa: E402


def load_pairs(db_path: Path):
    connection = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute("""
        SELECT h.session_id, h.portable_id, h.name, h.artist, h.bpm, h.key
        FROM history_entry h
        WHERE h.played = 1
        ORDER BY h.session_id, h.start_time, h.id
    """).fetchall()
    connection.close()
    sessions: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        sessions[row["session_id"]].append(row)
    pairs = []
    for session_id, plays in sessions.items():
        for position, (first, second) in enumerate(zip(plays, plays[1:])):
            if first["portable_id"] != second["portable_id"]:
                pairs.append((session_id, position, first, second))
    return rows, pairs


def _legacy_rank(source, candidates, metadata):
    """Ancien moteur : filtre 0.88 / 0.80 puis score 55 % clé, 45 % tempo."""
    scored = []
    for path in candidates:
        key = scoring.key_compatibility(metadata[source].key, metadata[path].key)
        bpm = scoring.bpm_compatibility(metadata[source].bpm, metadata[path].bpm)
        if key is None or key < 0.88 or bpm is None or bpm < 0.80:
            continue
        scored.append((path, 0.55 * key + 0.45 * bpm))
    return [path for path, _ in sorted(scored, key=lambda item: -item[1])[:5]]


def measure(legacy=False, seed=1, holdout_ratio=0.3, unseen_pool=20):
    if not SERATO_DB.is_file():
        print(f"Base Serato introuvable : {SERATO_DB}")
        return
    rows, pairs = load_pairs(SERATO_DB)
    metadata = {row["portable_id"]: AudioMetadata(row["bpm"] or None, row["key"] or None)
                for row in rows}
    names = {row["portable_id"]: (row["name"], row["artist"] or "") for row in rows}
    played_ids = [row["portable_id"] for row in rows]
    random.seed(seed)
    holdout = {(session, position) for session, position, _, _ in pairs
               if random.random() < holdout_ratio}
    by_source = defaultdict(list)
    for session, position, first, second in pairs:
        by_source[first["portable_id"]].append((session, position, second["portable_id"]))

    hits = Counter()
    total = 0
    for session, position, first, second in pairs:
        if (session, position) in holdout:
            continue
        source = first["portable_id"]
        counts = Counter()
        for other_session, other_position, target in by_source[source]:
            if (other_session, other_position) == (session, position):
                continue
            counts[target] += 1
        candidates = [(path, names[path][0], names[path][1], count)
                      for path, count in counts.items()]
        if not legacy:
            for path in random.sample(played_ids, unseen_pool):
                if path not in counts and path != source:
                    candidates.append((path, names[path][0], names[path][1], 0))
            suggestions = scoring.rank_candidates(source, metadata[source], candidates,
                                                  metadata, [], limit=5)
            top = [item.path for item in suggestions]
        else:
            top = _legacy_rank(source, list(counts), metadata)
        total += 1
        for k in (1, 3, 5):
            if second["portable_id"] in top[:k]:
                hits[k] += 1
    if not total:
        print("Pas assez de transitions pour mesurer.")
        return
    label = "ancien moteur" if legacy else "moteur actuel"
    print(f"{label} · {total} transitions évaluées")
    for k in (1, 3, 5):
        print(f"  hits@{k} : {hits[k] / total * 100:5.1f} %")


if __name__ == "__main__":
    measure(legacy="--legacy" in sys.argv)
