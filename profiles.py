"""Profils locaux sans mot de passe, compte réseau ni synchronisation."""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from pathlib import Path


class LocalProfiles:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.file = data_dir / "profiles.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._data = self._read()

    def _read(self):
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
            profiles = data.get("profiles", [])
            if profiles and any("id" in p and "name" in p for p in profiles):
                current = data.get("current", profiles[0]["id"])
                if not any(p["id"] == current for p in profiles):
                    current = profiles[0]["id"]
                return {"profiles": profiles, "current": current}
        except (OSError, ValueError, TypeError):
            pass
        return {"profiles": [{"id": "nel", "name": "Nel", "software": "serato"}],
                "current": "nel"}

    def _save(self):
        temp = self.file.with_suffix(".tmp")
        temp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.file)

    @property
    def current(self):
        return next(p for p in self._data["profiles"] if p["id"] == self._data["current"])

    @property
    def names(self):
        return [p["name"] for p in self._data["profiles"]]

    def activate_or_create(self, name: str):
        name = " ".join((name or "").split())
        if not name:
            return self.current
        existing = next((p for p in self._data["profiles"]
                         if p["name"].casefold() == name.casefold()), None)
        if existing is None:
            base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
            base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower() or "dj"
            existing = {"id": f"{base}-{uuid.uuid4().hex[:8]}",
                        "name": name, "software": self.current.get("software", "serato")}
            self._data["profiles"].append(existing)
        self._data["current"] = existing["id"]
        self._save()
        return existing

    def set_software(self, software: str):
        if software not in {"serato", "traktor"}:
            raise ValueError("Logiciel DJ non pris en charge.")
        self.current["software"] = software
        self._save()
