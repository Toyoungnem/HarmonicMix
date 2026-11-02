"""Classement des prochains morceaux (transitions, BPM et roue Camelot)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from metadata import AudioMetadata

CAMELot = {
    "B": {"C": 8, "C#": 3, "DB": 3, "D": 10, "D#": 5, "EB": 5, "E": 12,
          "F": 7, "F#": 2, "GB": 2, "G": 9, "G#": 4, "AB": 4, "A": 11,
          "A#": 6, "BB": 6, "B": 1},
    "M": {"C": 5, "C#": 12, "DB": 12, "D": 7, "D#": 2, "EB": 2, "E": 9,
          "F": 4, "F#": 11, "GB": 11, "G": 6, "G#": 1, "AB": 1, "A": 8,
          "A#": 3, "BB": 3, "B": 10},
}


def camelot_number(value: str | None):
    if not value:
        return None
    text = value.strip().upper().replace("♭", "B").replace("♯", "#")
    match = re.fullmatch(r"(1[0-2]|[1-9])\s*([AB])", text)
    if match:
        return int(match.group(1)), match.group(2)
    match = re.fullmatch(r"([A-G])([#B]?)(?:\s*(?:MAJ(?:OR)?|MIN(?:OR)?|M))?", text)
    if not match:
        return None
    note = match.group(1) + match.group(2)
    # A bare trailing m is common in Serato tags; explicit M means minor too.
    mode = "M" if re.search(r"(?:MIN(?:OR)?|M)$", text) else "B"
    number = CAMELot[mode].get(note)
    return (number, "A" if mode == "M" else "B") if number else None


def bpm_match(a: float | None, b: float | None):
    """Retourne (compatibilité, écart %, ratio), avec tolérance demi/double tempo."""
    if not a or not b:
        return None, None, 1.0
    options = [(abs(a - b) / a, 1.0), (abs(a - b * 2) / a, 2.0),
               (abs(a - b / 2) / a, 0.5)]
    gap, ratio = min(options, key=lambda option: option[0])
    if gap <= 0.01:
        score = 1.0
    elif gap <= 0.03:
        score = 0.92 - (gap - 0.01) * 6
    elif gap <= 0.05:
        score = 0.80 - (gap - 0.03) * 7.5
    elif gap <= 0.08:
        score = 0.65 - (gap - 0.05) * 5
    elif gap <= 0.12:
        score = 0.50 - (gap - 0.08) * 7.5
    else:
        score = max(0.0, 0.20 - (gap - 0.12) * 1.5)
    if ratio != 1.0:
        score *= 0.86
    return max(0.0, min(1.0, score)), gap * 100, ratio


def bpm_compatibility(a: float | None, b: float | None):
    return bpm_match(a, b)[0]


def key_match(a: str | None, b: str | None):
    ka, kb = camelot_number(a or ""), camelot_number(b or "")
    if not ka or not kb:
        return None, None
    distance = abs(ka[0] - kb[0])
    distance = min(distance, 12 - distance)
    same_mode = ka[1] == kb[1]
    if distance == 0 and same_mode:
        return 1.0, "même tonalité"
    if distance == 0:
        return 0.94, "relative majeure/mineure"
    if distance == 1 and same_mode:
        return 0.88, "voisine Camelot"
    if distance == 1:
        return 0.42, "voisine avec changement de mode"
    if distance == 2 and same_mode:
        return 0.55, "mouvement de deux cases"
    return max(0.0, 0.20 - (distance - 2) * 0.035), "tonalité éloignée"


def key_compatibility(a: str | None, b: str | None):
    return key_match(a, b)[0]


@dataclass(frozen=True)
class Suggestion:
    path: str
    title: str
    artist: str
    score: float
    transition_count: int
    bpm: float | None
    key: str | None
    reason: str
    bpm_delta_pct: float | None = None
    bpm_ratio: float = 1.0
    key_relation: str | None = None
    camelot: str | None = None
    category: str = "yellow"


def rank_candidates(current_path, current_meta: AudioMetadata, candidates, metadata_by_path,
                    played_paths, limit=5, recent_paths=None, bpm_momentum=0):
    """candidates: iterable de tuples (path, title, artist, transition_count)."""
    candidates = list(candidates)
    max_count = max((int(c[3]) for c in candidates), default=0)
    ranked = []
    played = {p.casefold() for p in played_paths}
    recent = {p.casefold() for p in (recent_paths or [])}
    for path, title, artist, count in candidates:
        if path.casefold() == current_path.casefold():
            continue
        meta = metadata_by_path.get(path, AudioMetadata())
        bpm, bpm_delta, bpm_ratio = bpm_match(current_meta.bpm, meta.bpm)
        key, relation = key_match(current_meta.key, meta.key)
        history = (math.log1p(count) / math.log1p(max_count)) if max_count else None
        if count:
            if count >= 2 and count == max_count:
                category = "red"
            elif count >= 3 and count >= max_count * 0.5:
                category = "red"
            elif count >= 2:
                category = "orange"
            else:
                category = "yellow"
        else:
            # Le bleu est réservé aux transitions jamais observées mais réellement
            # compatibles à la fois en tempo et en tonalité.
            if key is None or key < 0.88 or bpm is None or bpm < 0.80:
                continue
            category = "blue"
        # Les transitions observées gardent le poids principal; le tempo et la clé
        # départagent les habitudes. En fallback, seule la compatibilité musicale compte.
        if count:
            features = [(weight, value) for weight, value in (
                (0.60, history), (0.20, bpm), (0.20, key)
            ) if value is not None]
        else:
            features = [(weight, value) for weight, value in (
                (0.55, key), (0.45, bpm)
            ) if value is not None]
        total_weight = sum(weight for weight, _ in features)
        score = 100 * sum(weight * value for weight, value in features) / total_weight if total_weight else 0.0

        momentum_adjustment = 0.0
        if bpm_momentum and current_meta.bpm and meta.bpm and bpm_ratio == 1.0:
            directed_delta = (meta.bpm - current_meta.bpm) * bpm_momentum
            if 0 < directed_delta <= 8:
                momentum_adjustment = 3.0
            elif directed_delta < -5:
                momentum_adjustment = -3.0
        score += momentum_adjustment

        if path.casefold() in played:
            score *= 0.82
        if path.casefold() in recent:
            score *= 0.68
        notes = []
        if count:
            notes.append(f"enchaînée {count} fois")
        if bpm is not None:
            notes.append(f"écart tempo {bpm_delta:.1f}%" if bpm_delta is not None else "tempo comparé")
        if key is not None:
            notes.append(relation or "tonalité comparée")
        if path.casefold() in played:
            notes.append("déjà jouée dans cette session · pénalité de répétition")
        if path.casefold() in recent:
            notes.append("jouée récemment · pénalité renforcée")
        components = []
        if count and history is not None:
            components.append(f"habitude {history * 100:.0f}%")
        if key is not None:
            components.append(f"tonalité {key * 100:.0f}%")
        if bpm is not None:
            components.append(f"tempo {bpm * 100:.0f}%")
        if components:
            notes.append("score détaillé : " + " · ".join(components))
        if momentum_adjustment:
            notes.append("suit la montée du tempo" if bpm_momentum > 0 else "suit la baisse du tempo")
        if not count:
            notes.append("jamais enchaînée · bonne compatibilité BPM et tonalité")
        ranked.append(Suggestion(path, title or path.rsplit("\\", 1)[-1], artist or "", score,
                                int(count), meta.bpm, meta.key, ", ".join(notes) or "compatibilité musicale",
                                bpm_delta, bpm_ratio, relation,
                                (f"{camelot_number(meta.key)[0]}{camelot_number(meta.key)[1]}"
                                 if camelot_number(meta.key) else None), category))
    category_order = {"red": 0, "orange": 1, "yellow": 2, "blue": 3}
    return sorted(ranked, key=lambda x: (category_order[x.category], -x.score, -x.transition_count,
                                         x.title.casefold()))[:limit]

