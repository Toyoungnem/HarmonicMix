"""Style musical : normalisation des genres et familles DJ.

Les tags réels sont hétérogènes (« HIP-HOP », « Hip Hop/Rap », « Urbain Actu
FR », « Electro;Techno/House;Dance »). On les ramène à une famille stable, ce
qui permet de proposer des transitions inédites *dans le bon style* : enchaîner
un morceau house avec de la pop n'a aucun intérêt même à clé égale.
"""
from __future__ import annotations

import re
from pathlib import Path

# Familles de DJ, du plus général au plus précis. L'ordre compte : les règles
# les plus spécifiques sont testées d'abord (hard techno avant techno).
FAMILIES = {
    "techno": "Techno",
    "hard techno": "Techno",
    "tech house": "House",
    "deep house": "House",
    "afro house": "Afro / Latino",
    "melodic house": "House",
    "house": "House",
    "electro": "Électro",
    "drum & bass": "Drum & Bass",
    "drum and bass": "Drum & Bass",
    "dnb": "Drum & Bass",
    "jungle": "Drum & Bass",
    "rap": "Rap / Hip-Hop",
    "hip hop": "Rap / Hip-Hop",
    "hip-hop": "Rap / Hip-Hop",
    "hiphop": "Rap / Hip-Hop",
    "urbain": "Rap / Hip-Hop",
    "trap": "Rap / Hip-Hop",
    "drill": "Rap / Hip-Hop",
    "r&b": "R&B / Soul",
    "rnb": "R&B / Soul",
    "soul": "R&B / Soul",
    "funk": "R&B / Soul",
    "afro": "Afro / Latino",
    "latino": "Afro / Latino",
    "reggaeton": "Afro / Latino",
    "dancehall": "Afro / Latino",
    "salsa": "Afro / Latino",
    "pop": "Pop",
    "mainstream": "Pop",
    "top club": "Pop",
    "top 40": "Pop",
    "top 20": "Pop",
    "variété": "Pop",
    "années 80": "Pop",
    "annees 80": "Pop",
    "90 & 2000": "Pop",
    "rock": "Rock / Indie",
    "indie": "Rock / Indie",
    "metal": "Rock / Indie",
    "ambient": "Downtempo",
    "downtempo": "Downtempo",
    "chill": "Downtempo",
    "lo-fi": "Downtempo",
    "classique": "Classique",
    "classical": "Classique",
    "jazz": "Jazz / Funk",
    "disco": "Disco",
}

# Proximité entre familles : deux familles voisines se mélangent bien, deux
# familles opposées jamais (un set house n'enchaîne pas sur du hard rock).
AFFINITY = {
    ("House", "Techno"): 0.85,
    ("House", "Électro"): 0.80,
    ("House", "Disco"): 0.75,
    ("House", "Pop"): 0.55,
    ("House", "Afro / Latino"): 0.75,
    ("House", "Downtempo"): 0.45,
    ("House", "Drum & Bass"): 0.20,
    ("House", "Rap / Hip-Hop"): 0.35,
    ("Techno", "Électro"): 0.80,
    ("Techno", "Drum & Bass"): 0.45,
    ("Techno", "Downtempo"): 0.40,
    ("Techno", "Pop"): 0.35,
    ("Techno", "Rap / Hip-Hop"): 0.30,
    ("Électro", "Pop"): 0.60,
    ("Électro", "Afro / Latino"): 0.55,
    ("Électro", "Drum & Bass"): 0.55,
    ("Pop", "Rap / Hip-Hop"): 0.75,
    ("Pop", "R&B / Soul"): 0.75,
    ("Pop", "Afro / Latino"): 0.70,
    ("Pop", "Rock / Indie"): 0.55,
    ("Pop", "Disco"): 0.65,
    ("Rap / Hip-Hop", "R&B / Soul"): 0.85,
    ("Rap / Hip-Hop", "Afro / Latino"): 0.65,
    ("Rap / Hip-Hop", "Drum & Bass"): 0.35,
    ("Afro / Latino", "R&B / Soul"): 0.70,
    ("Afro / Latino", "Disco"): 0.55,
    ("Afro / Latino", "Drum & Bass"): 0.35,
    ("R&B / Soul", "Disco"): 0.70,
    ("R&B / Soul", "Jazz / Funk"): 0.80,
    ("Disco", "Jazz / Funk"): 0.75,
    ("Downtempo", "Jazz / Funk"): 0.60,
    ("Downtempo", "Ambient"): 0.90,
    ("Downtempo", "Classique"): 0.35,
    ("Rock / Indie", "Classique"): 0.30,
}

# Certains albums portent le style dans leur nom (compilations achetées) :
# on les utilise quand le tag genre est vide.
ALBUM_HINTS = {
    "house music classics": "House",
    "house top chart": "House",
    "top chart": "Pop",
    "starter pack": "House",
    "soulful house": "House",
    "vocal soul": "House",
    "deep jazzy": "House",
    "glitterbox": "Disco",
    "house": "House",
    "techno": "Techno",
    "rap": "Rap / Hip-Hop",
    "hip hop": "Rap / Hip-Hop",
    "dancenudisco": "Disco",
    "love injection": "Disco",
    "rap francais": "Rap / Hip-Hop",
    "actu fr": "Rap / Hip-Hop",
    "afro": "Afro / Latino",
}


# Dossier -> famille, quand la bibliothèque est rangée par genre (cas fréquent
# chez les DJ : « House Com », « ap set », « mix/Contents/… »).
FOLDER_HINTS = {
    "house": "House", "techno": "Techno", "rap": "Rap / Hip-Hop",
    "hip hop": "Rap / Hip-Hop", "hip-hop": "Rap / Hip-Hop",
    "afro": "Afro / Latino", "latino": "Afro / Latino", "disco": "Disco",
    "drum and bass": "Drum & Bass", "dnb": "Drum & Bass", "edm": "Électro",
    "electro": "Électro", "pop": "Pop", "reggaeton": "Afro / Latino",
}


def folder_family(path: str | None) -> str | None:
    """Famille déduite du nom des dossiers du morceau."""
    if not path:
        return None
    parts = [part.casefold().strip() for part in Path(path).parts[:-1]]
    # D'abord les dossiers les plus précis (les plus profonds).
    for part in reversed(parts[-3:]):
        if not part:
            continue
        for hint in sorted(FOLDER_HINTS, key=len, reverse=True):
            if hint == part or hint in part:
                return FOLDER_HINTS[hint]
    return None


# Extension -> famille probable quand tout le reste manque (sets homogènes).
EXTENSION_HINTS = {
    "aif": "House", "aiff": "House", "wav": "House",
}


def extension_family(path: str | None) -> str | None:
    """Famille déduite de l'extension : WAV/AIFF = titres de club non tagués."""
    if not path:
        return None
    return EXTENSION_HINTS.get(Path(path).suffix.lstrip(".").casefold())


def album_family(album: str | None) -> str | None:
    """Famille déduite du nom d'album (compilations « House Music Classics »)."""
    if not album:
        return None
    text = str(album).strip().casefold()
    for hint, family in ALBUM_HINTS.items():
        if hint in text:
            return family
    return None


# Tags sans information de style : on ne s'en sert pas.
EMPTY_TAGS = {"music", "other", "remix", "loop samples", "sample", "inconnu",
              "unknown", "non renseigné", "divers", ""}


def normalise_family(genre: str | None) -> str | None:
    """Famille DJ d'un tag de genre, ou None si le tag n'apprend rien."""
    if not genre:
        return None
    text = str(genre).strip().casefold()
    if text in EMPTY_TAGS:
        return None
    text = re.sub(r"[_/;,]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    for key in sorted(FAMILIES, key=len, reverse=True):
        if key in text:
            return FAMILIES[key]
    return None


def style_affinity(a: str | None, b: str | None) -> float | None:
    """Compatibilité de style entre deux familles (1 = même famille)."""
    if not a or not b:
        return None
    if a == b:
        return 1.0
    if (a, b) in AFFINITY:
        return AFFINITY[(a, b)]
    if (b, a) in AFFINITY:
        return AFFINITY[(b, a)]
    return 0.15
