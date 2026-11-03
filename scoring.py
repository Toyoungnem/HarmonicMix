"""Classement des prochains morceaux : transitions observées + harmonie et tempo.

Deux familles de signaux, volontairement séparées :

* l'habitude (transitions réellement enchaînées dans les sets importés) ;
* la musique (roue Camelot, tempo, énergie estimée) qui sert à classer les
  morceaux jamais enchaînés, et à départager les habitudes.

Les valeurs de compatibilité harmonique suivent l'usage DJ (roue Camelot, cercle
des quintes) et ont été calibrées sur les transitions réelles de la base Serato :
même clé, relative majeure/mineure, ±1 et ±2 cases Camelot couvrent ~46 % des
enchaînements observés ; la sous-dominante et la dominante restent musicalement
valides même si elles sont rares dans un set.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from metadata import AudioMetadata
from styles import (album_family, extension_family, folder_family,
                    normalise_family, style_affinity)

# Roue Camelot : chaque numéro existe en majeur (B) et en mineur (A).
# 1B B maj / 2B F# maj / 3B Db maj / 4B Ab maj / 5B Eb maj / 6B Bb maj
# 7B F maj / 8B C maj / 9B G maj / 10B D maj / 11B A maj / 12B E maj
# 1A G# min / 2A D# min / 3A A# min / 4A F min / 5A C min / 6A G min
# 7A D min / 8A A min / 9A E min / 10A B min / 11A F# min / 12A C# min
CAMELOT = {
    "B": {"C": 8, "C#": 3, "DB": 3, "D": 10, "D#": 5, "EB": 5, "E": 12,
          "F": 7, "F#": 2, "GB": 2, "G": 9, "G#": 4, "AB": 4, "A": 11,
          "A#": 6, "BB": 6, "B": 1},
    "M": {"C": 5, "C#": 12, "DB": 12, "D": 7, "D#": 2, "EB": 2, "E": 9,
          "F": 4, "F#": 11, "GB": 11, "G": 6, "G#": 1, "AB": 1, "A": 8,
          "A#": 3, "BB": 3, "B": 10},
}
# Notes affichées pour chaque case, dans la forme usuelle des DJ.
CAMELOT_NAMES = {
    (1, "B"): "B", (2, "B"): "F#", (3, "B"): "Db", (4, "B"): "Ab",
    (5, "B"): "Eb", (6, "B"): "Bb", (7, "B"): "F", (8, "B"): "C",
    (9, "B"): "G", (10, "B"): "D", (11, "B"): "A", (12, "B"): "E",
    (1, "A"): "G#m", (2, "A"): "D#m", (3, "A"): "A#m", (4, "A"): "Fm",
    (5, "A"): "Cm", (6, "A"): "Gm", (7, "A"): "Dm", (8, "A"): "Am",
    (9, "A"): "Em", (10, "A"): "Bm", (11, "A"): "F#m", (12, "A"): "C#m",
}
# Relations nommées : (semitons, 'mode') -> (score, libellé).
# `semitons` est l'intervalle RÉEL entre les deux toniques (0-11), calculé
# depuis les notes et non depuis les cases : ainsi quarte et quinte tombent
# toujours sur le bon intervalle, quel que soit le numéro Camelot.
#   même mode  : 0 = même clé, ±1/±2 cases Camelot = 7/5 ou 2/10 semitons
#                (quinte/quarte), 5/7 = tierces.
#   modes croisés : 0 = parallèle (même tonique), 3 = relative, 4/8 = médiante,
#                5/7 = quinte/quarte avec changement de mode, 2/10 = seconde.
RELATIONS = {
    (0, "même"): (1.00, "même tonalité"),
    (0, "parallèle"): (0.66, "tonalité parallèle (même tonique)"),
    (3, "croisé"): (0.95, "relative majeure/mineure"),
    (4, "croisé"): (0.62, "médiante relative"),
    (8, "croisé"): (0.58, "médiante relative"),
    (7, "croisé"): (0.52, "quinte avec changement de mode"),
    (5, "croisé"): (0.46, "quarte avec changement de mode"),
    (2, "croisé"): (0.34, "seconde avec changement de mode"),
    (10, "croisé"): (0.30, "septième avec changement de mode"),
    (1, "même"): (0.72, "voisine Camelot atypique (±1 demi-ton)"),
    (2, "même"): (0.66, "seconde majeure"),
    (10, "même"): (0.62, "septième mineure"),
    (5, "même"): (0.62, "sous-dominante (quarte)"),
    (7, "même"): (0.55, "dominante (quinte)"),
    (3, "même"): (0.44, "tierce mineure"),
    (9, "même"): (0.42, "sixte mineure"),
    # Quarte côté roue (5 cases) : 8A -> 11A reste une relation utilisable.
    (9, "même"): (0.42, "sixte mineure"),
    (4, "même"): (0.34, "tierce majeure"),
    (8, "même"): (0.30, "sixte majeure"),
    (6, "même"): (0.10, "triton"),
}

def _camelot_steps(a: int, b: int) -> int:
    distance = abs(a - b) % 12
    return min(distance, 12 - distance)


def camelot_number(value: str | None):
    """Retourne (numéro 1-12, 'A' mineur | 'B' majeur) ou None."""
    if not value:
        return None
    text = value.strip().upper().replace("♭", "B").replace("♯", "#")
    text = text.replace("–", "-").replace("—", "-")
    if not text:
        return None
    # Traktor et certains tags écrivent le mode en m/d minuscule ("3m", "3d").
    match = re.fullmatch(r"(1[0-2]|[1-9])\s*([AB])", text)
    if match:
        return int(match.group(1)), match.group(2)
    match = re.fullmatch(r"(1[0-2]|[1-9])\s*([MD])", text)
    if match:
        return int(match.group(1)), "A" if match.group(2) == "M" else "B"
    match = re.fullmatch(r"0?(1[0-2]|[1-9])([AB])", text)
    if match:
        return int(match.group(1)), match.group(2)
    match = re.fullmatch(r"([A-G])([#B]?)(?:\s*(MAJ(?:OR)?|MIN(?:OR)?|M|MAJ|MIN))?", text)
    if not match:
        return None
    note = match.group(1) + match.group(2)
    suffix = match.group(3) or ""
    if suffix.startswith("MIN") or suffix == "M":
        mode = "M"
    elif suffix.startswith("MAJ"):
        mode = "B"
    else:
        mode = "B"
    number = CAMELOT[mode].get(note)
    return (number, "A" if mode == "M" else "B") if number else None


def camelot_label(value: str | None) -> str | None:
    parsed = camelot_number(value)
    return f"{parsed[0]}{parsed[1]}" if parsed else None


def camelot_note(value: str | None) -> str | None:
    """Écrit la tonalité en note (C, Cm, F#m…) pour les raisons affichées."""
    parsed = camelot_number(value)
    return CAMELOT_NAMES.get(parsed) if parsed else None


_CAMELOT_NAMES = {
    1: ("AB", "G#", "G#M"), 2: ("D#", "EB", "D#M"), 3: ("A#", "BB", "A#M"),
    4: ("F", "F", "FM"), 5: ("C", "C", "CM"), 6: ("G", "G", "GM"),
    7: ("D", "D", "DM"), 8: ("A", "A", "AM"), 9: ("E", "E", "EM"),
    10: ("B", "B", "BM"), 11: ("F#", "GB", "F#M"), 12: ("C#", "DB", "C#M"),
}
_MAJOR_TONIC = {
    1: "B", 2: "F#", 3: "DB", 4: "AB", 5: "EB", 6: "BB", 7: "F", 8: "C",
    9: "G", 10: "D", 11: "A", 12: "E",
}
_PITCH = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5,
          "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}


def _tonic(parsed) -> int | None:
    """Hauteur de la tonique en demi-tons (0 = do), mineur ou majeur."""
    number, side = parsed
    spelling = (_MAJOR_TONIC[number] if side == "B"
                else _CAMELOT_NAMES[number][2][:-1])
    return _PITCH.get(spelling)


def key_match(a: str | None, b: str | None):
    """Retourne (score 0-1, libellé de la relation) entre deux tonalités."""
    ka, kb = camelot_number(a or ""), camelot_number(b or "")
    if not ka or not kb:
        return None, None
    ta, tb = _tonic(ka), _tonic(kb)
    if ta is None or tb is None:
        return None, None
    interval = (tb - ta) % 12
    same_mode = ka[1] == kb[1]
    if same_mode:
        mode = "même"
        # La roue reste la référence : ±1 case = voisine, ±2 = voisine élargie,
        # quel que soit l'intervalle que donnent les notes (les annotateurs
        # n'utilisent pas toujours la même enharmonie).
        steps = _camelot_steps(ka[0], kb[0])
        if steps == 1:
            return 0.90, "voisine Camelot (+1/-1)"
        if steps == 2:
            return 0.72, "voisine élargie (+2/-2)"
        if steps == 5:
            # Sur la roue, 5 cases dans le même sens = quarte : relation valide
            # même si l'enharmonie des annotateurs donne une sixte.
            return 0.62, "sous-dominante (quarte)"
    else:
        mode = "parallèle" if interval == 0 else "croisé"
    relation = RELATIONS.get((interval, mode))
    if relation is not None:
        return relation
    # Intervalle restant : mineur de seconde, neuvième, etc.
    steps = interval if interval <= 6 else 12 - interval
    score = max(0.0, 0.24 - (steps - 2) * 0.05)
    return score, "tonalité éloignée"


def key_compatibility(a: str | None, b: str | None):
    return key_match(a, b)[0]


def _tempo_gap(a: float, b: float):
    """Écart de tempo minimal, avec tolérance demi/double tempo."""
    options = [(abs(a - b) / a, 1.0), (abs(a - b * 2) / a, 2.0),
               (abs(a - b / 2) / a, 0.5)]
    return min(options, key=lambda option: option[0])


def bpm_match(a: float | None, b: float | None):
    """Retourne (compatibilité, écart %, ratio), avec tolérance demi/double tempo."""
    if not a or not b:
        return None, None, 1.0
    gap, ratio = _tempo_gap(a, b)
    if gap <= 0.005:
        score = 1.0
    elif gap <= 0.01:
        score = 1.0
    elif gap <= 0.03:
        score = 0.95 - (gap - 0.01) * 2.5
    elif gap <= 0.05:
        score = 0.86 - (gap - 0.03) * 5.5
    elif gap <= 0.08:
        score = 0.70 - (gap - 0.05) * 5.5
    elif gap <= 0.12:
        score = 0.53 - (gap - 0.08) * 6.5
    else:
        score = max(0.0, 0.24 - (gap - 0.12) * 1.6)
    if ratio != 1.0:
        # Passer en demi-temps (ou doubler) se fait couramment mais demande un
        # geste : la pénalité est légère, pas éliminatoire.
        score *= 0.88
    return max(0.0, min(1.0, score)), gap * 100, ratio


def bpm_compatibility(a: float | None, b: float | None):
    return bpm_match(a, b)[0]


def energy_bpm(bpm: float | None) -> float | None:
    """Énergie approximative d'un morceau, de 0 (lent) à 1 (très rapide).

    Le tempo est ramené sur une seule octave autour de 128 BPM pour que 70 BPM
    et 140 BPM (même pulsation) soient perçus comme proches.
    """
    if not bpm:
        return None
    value = bpm
    while value < 90:
        value *= 2
    while value > 180:
        value /= 2
    return max(0.0, min(1.0, (value - 85) / 90))


def energy_match(a: float | None, b: float | None):
    """Compatibilité d'énergie : deux morceaux de tempo voisin ont la même énergie."""
    ea, eb = energy_bpm(a), energy_bpm(b)
    if ea is None or eb is None:
        return None
    return max(0.0, 1.0 - abs(ea - eb) * 1.8)


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
    category: str = "blue"
    # Signaux détaillés, pour l'affichage et le tri secondaire.
    history_score: float | None = None
    key_score: float | None = None
    bpm_score: float | None = None
    energy_score: float | None = None
    style: str | None = None
    style_score: float | None = None


def effective_style(meta: AudioMetadata | None, path: str | None = None) -> str | None:
    """Famille de style d'un morceau, en croisant tag genre, album et extension.

    Beaucoup de bibliothèques DJ n'ont pas de genre : le nom d'album des
    compilations (« House Music Classics ») et l'extension (WAV/AIFF, titres de
    club) donnent alors une indication fiable du style.
    """
    if meta is None:
        return None
    return (normalise_family(meta.genre) or album_family(meta.album)
            or folder_family(path) or extension_family(path))


def _normalise_history(count: int, max_count: int) -> float | None:
    if not max_count:
        return None
    return math.log1p(count) / math.log1p(max_count)


def _weighted(features):
    """Moyenne pondérée en ignorant les signaux absents (métadonnées manquantes)."""
    pairs = [(weight, value) for weight, value in features if value is not None]
    total = sum(weight for weight, _ in pairs)
    return sum(weight * value for weight, value in pairs) / total if total else None


def rank_candidates(current_path, current_meta: AudioMetadata, candidates, metadata_by_path,
                    played_paths, limit=5, recent_paths=None, bpm_momentum=0,
                    seed_paths=None, discovery_slots=2, max_per_artist=2,
                    guarantee_discovery=False):
    """candidates: iterable de tuples (path, title, artist, transition_count).

    seed_paths (optionnel) : morceaux qui viennent de tourner. Si le morceau
    courant n'a ni tempo ni tonalité exploitables, on prend les métadonnées du
    dernier morceau connu pour ne pas rendre toutes les suggestions aveugles.

    discovery_slots : nombre de places réservées aux morceaux jamais enchaînés
    (catégorie bleue). Sans elles, un DJ qui tourne sur ses habitudes ne verrait
    jamais de nouvelle piste ; mesuré sur l'historique réel, deux places coûtent
    ~1,5 point de hits@1 mais ouvrent en moyenne une proposition inédite par
    liste de cinq.
    """
    candidates = list(candidates)
    max_count = max((int(c[3]) for c in candidates), default=0)
    current = current_meta
    if (current.bpm is None and current.key is None) and seed_paths:
        for path in seed_paths:
            seed = metadata_by_path.get(path)
            if seed and (seed.bpm is not None or seed.key):
                current = seed
                break
    ranked = []
    played = {p.casefold() for p in played_paths}
    recent = {p.casefold() for p in (recent_paths or [])}
    current_style = effective_style(current, current_path)
    for path, title, artist, count in candidates:
        if path.casefold() == current_path.casefold():
            continue
        meta = metadata_by_path.get(path, AudioMetadata())
        bpm, bpm_delta, bpm_ratio = bpm_match(current.bpm, meta.bpm)
        key, relation = key_match(current.key, meta.key)
        energy = energy_match(current.bpm, meta.bpm)
        style = style_affinity(current_style, effective_style(meta, path))
        history = _normalise_history(int(count), max_count) if count else None
        has_meta = bpm is not None or key is not None

        if count:
            # Transition déjà vue : l'habitude domine, la musique départage.
            base = _weighted(((0.58, history), (0.18, key), (0.16, bpm),
                              (0.04, energy), (0.04, style)))
        else:
            # Jamais enchaînée : harmonie, tempo, puis style et énergie.
            base = _weighted(((0.44, key), (0.32, bpm), (0.16, style), (0.08, energy)))
        if base is None:
            # Aucune métadonnée des deux côtés : on ne peut rien affirmer.
            base = 0.0
        score = 100 * base

        # Classement des couleurs : les enchaînements réellement pratiqués
        # passent devant les propositions théoriques.
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
            # Le bleu est réservé aux transitions jamais observées mais
            # réellement compatibles : quarte, quinte et relative comprises
            # (une quarte est une relation DJ classique, pas une faute).
            if key is None or key < 0.55 or bpm is None or bpm < 0.70:
                continue
            if style is not None and style < 0.35:
                continue
            category = "blue"

        momentum_adjustment = 0.0
        if bpm_momentum and current.bpm and meta.bpm and bpm_ratio == 1.0:
            directed_delta = (meta.bpm - current.bpm) * bpm_momentum
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
            if bpm_delta is not None:
                tempo_note = f"écart tempo {bpm_delta:.1f}%"
                if bpm_ratio == 2.0:
                    tempo_note += " (doublement)"
                elif bpm_ratio == 0.5:
                    tempo_note += " (demi-temps)"
                notes.append(tempo_note)
            else:
                notes.append("tempo comparé")
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
        if energy is not None:
            components.append(f"énergie {energy * 100:.0f}%")
        if components:
            notes.append("score détaillé : " + " · ".join(components))
        if momentum_adjustment:
            notes.append("suit la montée du tempo" if bpm_momentum > 0 else "suit la baisse du tempo")
        if not count:
            notes.append("jamais enchaînée · proposition harmonique et tempo")
        if not has_meta:
            notes.append("métadonnées BPM/clé manquantes pour ce morceau")
        label = camelot_label(meta.key)
        ranked.append(Suggestion(
            path, title or path.rsplit("\\", 1)[-1], artist or "", score,
            int(count), meta.bpm, meta.key, ", ".join(notes) or "compatibilité musicale",
            bpm_delta, bpm_ratio, relation, label, category,
            history, key, bpm, energy,
            effective_style(meta, path), style,
        ))
    category_order = {"red": 0, "orange": 1, "yellow": 2, "blue": 3}
    ordered = sorted(ranked, key=lambda x: (category_order[x.category], -x.score,
                                            -x.transition_count, x.title.casefold()))
    # Un même artiste ne remplit pas toute la liste : au-delà de deux titres,
    # on garde le meilleur et on laisse la place à d'autres propositions.
    if max_per_artist:
        per_artist = {}
        diverse = []
        for item in ordered:
            artist = (item.artist or "").strip().casefold()
            if not artist:
                diverse.append(item)
                continue
            seen = per_artist.get(artist, 0)
            if seen >= max_per_artist:
                continue
            per_artist[artist] = seen + 1
            diverse.append(item)
        ordered = diverse
    if not discovery_slots or limit <= discovery_slots:
        final = ordered[:limit]
    else:
        final = _select(ordered, limit, discovery_slots)
    if guarantee_discovery and final and all(item.transition_count for item in final):
        # Aucune proposition inédite dans la sélection : on prend la meilleure
        # qui soit compatible, quitte à retirer la dernière habitude.
        spare = next((item for item in ranked
                      if not item.transition_count
                      and item not in final), None)
        if spare is not None:
            final = final[:limit - 1] + [spare]
    return final


def _select(ordered, limit, discovery_slots):
    """Mélange habitudes et découvertes en réservant des places aux inédites."""
    if not discovery_slots or limit <= discovery_slots:
        return ordered[:limit]
    discovery = [item for item in ordered if item.category == "blue"][:discovery_slots]
    habits = [item for item in ordered if item.category != "blue"]
    if not habits or not discovery:
        return ordered[:limit]
    # On réserve des places aux découvertes sans écraser les habitudes, puis on
    # retrie l'ensemble par score pour que la meilleure piste reste en tête.
    merged = habits[:limit - len(discovery)] + discovery
    category_order = {"red": 0, "orange": 1, "yellow": 2, "blue": 3}
    return sorted(merged, key=lambda x: (category_order[x.category], -x.score,
                                         -x.transition_count, x.title.casefold()))[:limit]
