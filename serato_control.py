"""Envoi d'une sélection de piste à Serato DJ Lite sous Windows."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path


def _press_keys(*keys: int) -> None:
    """Envoie une combinaison clavier avec l'API Windows, sans bibliothèque externe."""
    user32 = ctypes.windll.user32
    key_up = 0x0002
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, key_up, 0)


def search_track_in_serato(root, path: str, title: str, artist: str,
                           on_complete) -> None:
    """Recherche sans bloquer Tkinter : chaque étape est planifiée avec ``after``.

    Ctrl+F ouvre la recherche globale de Serato. Le premier résultat filtré reste
    sélectionné pour que le DJ choisisse ensuite le deck et le moment du chargement.
    """
    if os.name != "nt":
        raise RuntimeError("La recherche directe est disponible sous Windows uniquement.")
    track_path = Path(path)

    hwnd = ctypes.windll.user32.FindWindowW(None, "Serato DJ Lite")
    if not hwnd:
        raise RuntimeError("Serato DJ Lite est introuvable. Ouvre-le puis réessaie.")

    # Serato reçoit les frappes sans modifier l'épinglage ni la position du panneau.
    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    try:
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        query = title.strip() if title and title.strip() else (artist or "").strip()
        if not query:
            query = track_path.stem
        root.clipboard_clear()
        root.clipboard_append(query)
    except Exception as exc:
        raise RuntimeError(f"Impossible de démarrer la recherche dans Serato : {exc}") from exc

    def finish(error=None):
        # Le panneau reste à sa place et au premier plan, même pendant la recherche.
        on_complete(error)

    def select_result():
        try:
            _press_keys(0x28)  # Première piste filtrée
            root.after(60, lambda: finish())
        except Exception as exc:
            finish(f"Impossible de sélectionner le résultat Serato : {exc}")

    def paste_query():
        try:
            _press_keys(0x11, 0x41)  # Ctrl+A
            _press_keys(0x11, 0x56)  # Ctrl+V
            # Laisse Serato terminer son filtrage sans bloquer la fenêtre de suggestions.
            root.after(900, select_result)
        except Exception as exc:
            finish(f"Impossible d'envoyer la recherche à Serato : {exc}")

    def open_search():
        try:
            _press_keys(0x11, 0x46)  # Ctrl+F
            root.after(140, paste_query)
        except Exception as exc:
            finish(f"Impossible d'ouvrir la recherche Serato : {exc}")

    # Le court délai laisse Windows donner le focus à Serato, sans bloquer l'interface.
    root.after(140, open_search)
