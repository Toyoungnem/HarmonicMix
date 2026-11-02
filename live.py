"""Repère la dernière piste locale citée dans le journal courant de Serato.

Serato DJ Lite n'écrit pas toujours le morceau du deck dans un .session pendant
la lecture. Son journal local contient les chemins des pistes dont il charge
les données audio; c'est la meilleure indication locale disponible en direct.
"""
from __future__ import annotations

import re
from pathlib import Path

LOG_DIR = Path.home() / "Music" / "_Serato_" / "Logs"
_AUDIO_PATH = re.compile(
    r"([A-Za-z]:[/\\].*?\.(?:mp3|wav|aiff|aif|flac|m4a|ogg|wma))(?=$|[`'\"?\s])",
    re.IGNORECASE,
)
_AUDIO_SUFFIX = re.compile(r"\.(?:mp3|wav|aiff|aif|flac|m4a|ogg|wma)$", re.IGNORECASE)


def latest_logged_track(log_dir: Path = LOG_DIR) -> tuple[str, float] | None:
    """Retourne le chemin audio le plus récemment demandé dans le dernier log."""
    logs = list(log_dir.glob("*.log"))
    if not logs:
        return None
    logfile = max(logs, key=lambda p: p.stat().st_mtime_ns)
    try:
        lines = logfile.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if "was requested" not in line and "Creating audio cache store resource" not in line and "temporary stems file for" not in line:
            continue
        matches = _AUDIO_PATH.findall(line)
        if matches:
            path = matches[-1].replace("/", "\\")
            if _AUDIO_SUFFIX.search(path):
                return path, logfile.stat().st_mtime
    return None
