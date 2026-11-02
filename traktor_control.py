"""Recherche asynchrone d'une suggestion dans le navigateur Traktor."""
from __future__ import annotations

import ctypes
import os

from serato_control import _press_keys


def _find_traktor_window():
    user32 = ctypes.windll.user32
    found = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd, _extra):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if "traktor" in buffer.value.casefold():
                found.append(hwnd)
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return found[0] if found else None


def search_track_in_traktor(root, title: str, artist: str, on_complete) -> None:
    if os.name != "nt":
        raise RuntimeError("La recherche Traktor est disponible sous Windows uniquement.")
    hwnd = _find_traktor_window()
    if not hwnd:
        raise RuntimeError("Traktor est introuvable. Ouvre-le puis réessaie.")
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    query = title.strip() if title and title.strip() else (artist or "").strip()
    if not query:
        raise ValueError("Cette suggestion n'a pas de titre à rechercher.")
    root.clipboard_clear()
    root.clipboard_append(query)

    def finish(error=None):
        on_complete(error)

    def focus_results():
        try:
            # Dans Traktor, Tab passe du champ de recherche à la liste filtrée.
            _press_keys(0x09)
            root.after(60, finish)
        except Exception as exc:
            finish(f"Impossible de sélectionner le résultat Traktor : {exc}")

    def enter_query():
        try:
            _press_keys(0x11, 0x41)  # Ctrl+A
            _press_keys(0x11, 0x56)  # Ctrl+V
            root.after(800, focus_results)
        except Exception as exc:
            finish(f"Impossible d'envoyer la recherche à Traktor : {exc}")

    def open_search():
        try:
            _press_keys(0x11, 0x46)  # Ctrl+F
            root.after(150, enter_query)
        except Exception as exc:
            finish(f"Impossible d'ouvrir la recherche Traktor : {exc}")

    root.after(150, open_search)
