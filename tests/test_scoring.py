"""Tests des règles musicales et du classement (sans dépendance externe).

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from metadata import AudioMetadata  # noqa: E402
from scoring import (  # noqa: E402
    bpm_match, camelot_label, camelot_number, energy_match, key_match,
    rank_candidates,
)


class CamelotTests(unittest.TestCase):
    def test_notation_camelot(self):
        self.assertEqual(camelot_number("8B"), (8, "B"))
        self.assertEqual(camelot_number("08A"), (8, "A"))
        self.assertEqual(camelot_number("12a"), (12, "A"))

    def test_notation_musicale(self):
        self.assertEqual(camelot_number("C"), (8, "B"))
        self.assertEqual(camelot_number("Cm"), (5, "A"))
        self.assertEqual(camelot_number("C#m"), (12, "A"))
        self.assertEqual(camelot_number("Dbm"), (12, "A"))
        self.assertEqual(camelot_number("Abm"), (1, "A"))
        self.assertEqual(camelot_number("G# minor"), (1, "A"))
        self.assertEqual(camelot_number("F maj"), (7, "B"))

    def test_valeurs_invalides(self):
        for value in (None, "", "13A", "H", "n/a"):
            self.assertIsNone(camelot_number(value), value)

    def test_libelle(self):
        self.assertEqual(camelot_label("Cm"), "5A")
        self.assertIsNone(camelot_label(None))


class KeyMatchTests(unittest.TestCase):
    def test_harmonie_consonante(self):
        self.assertEqual(key_match("Cm", "Cm")[0], 1.0)
        self.assertAlmostEqual(key_match("Cm", "Eb")[0], 0.95)      # relative
        self.assertAlmostEqual(key_match("Cm", "Gm")[0], 0.90)      # +1 Camelot
        self.assertAlmostEqual(key_match("Cm", "Fm")[0], 0.90)      # -1 (circularité 12A -> 1A)
        self.assertAlmostEqual(key_match("Cm", "Dm")[0], 0.72)      # +2 Camelot
        self.assertAlmostEqual(key_match("Cm", "G")[0], 0.52)       # quinte, changement de mode
        self.assertAlmostEqual(key_match("Cm", "C")[0], 0.66)       # parallèle, même tonique

    def test_relations_dissonantes(self):
        self.assertLess(key_match("Cm", "F#m")[0], 0.30)   # triton
        self.assertLess(key_match("Cm", "Em")[0], 0.40)     # tierce majeure, mineur/mineur
        self.assertLess(key_match("Cm", "G")[0], 0.60)      # pas une voisine Camelot

    def test_monotonie_par_distance(self):
        # 8A -> 9A (+1), 10A (+2), 11A (quarte, tolérée), 12A (côté opposé).
        scores = [key_match("8A", f"{number}A")[0] for number in (8, 9, 10, 11, 12)]
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])
        self.assertGreater(scores[2], scores[3])
        self.assertGreater(scores[3], scores[4])
        # 12A est la voisine de 1A (circularité de la roue).
        self.assertAlmostEqual(key_match("12A", "1A")[0], 0.90)
        self.assertAlmostEqual(key_match("1A", "12A")[0], 0.90)

    def test_metadonnees_absentes(self):
        self.assertEqual(key_match(None, "Cm"), (None, None))
        self.assertEqual(key_match("Cm", ""), (None, None))


class BpmTests(unittest.TestCase):
    def test_tempo_identique(self):
        score, delta, ratio = bpm_match(128, 128)
        self.assertEqual((score, delta, ratio), (1.0, 0.0, 1.0))

    def test_degradation_progressive(self):
        values = [bpm_match(128, bpm)[0] for bpm in (128, 130, 132, 136, 145, 160)]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertGreater(values[1], 0.85)

    def test_demi_et_double_temps(self):
        score, _, ratio = bpm_match(70, 140)
        self.assertEqual(ratio, 0.5)
        self.assertGreater(score, 0.8)
        score, _, ratio = bpm_match(140, 70)
        self.assertEqual(ratio, 2.0)
        self.assertGreater(score, 0.8)

    def test_tempo_incompatible(self):
        self.assertLess(bpm_match(128, 100)[0], 0.15)

    def test_bpm_manquant(self):
        self.assertEqual(bpm_match(None, 128), (None, None, 1.0))


class EnergyTests(unittest.TestCase):
    def test_octave_confondue(self):
        self.assertAlmostEqual(energy_match(70, 140), 1.0, places=6)

    def test_ecart_energie(self):
        self.assertGreater(energy_match(126, 132), energy_match(90, 150))


def _candidates(*items):
    """items : (path, bpm, key, transitions). Un artiste différent par piste."""
    return [(path, f"Titre {index}", f"Artiste {index}", count)
            for index, (path, _bpm, _key, count) in enumerate(items, 1)], {
        path: AudioMetadata(bpm, key) for path, bpm, key, _count in items
    }


class RankCandidatesTests(unittest.TestCase):
    def test_jamais_enchaine_mais_harmonique(self):
        candidates, metadata = _candidates(("a", 128, "8A", 0), ("b", 126, "8A", 0),
                                          ("c", 128, "5A", 0))
        result = rank_candidates("source", AudioMetadata(128, "8A"), candidates, metadata, [])
        self.assertEqual([item.path for item in result], ["a", "b"])
        self.assertTrue(all(item.category == "blue" for item in result))
        self.assertGreater(result[0].score, result[1].score)

    def test_relations_valides_pour_une_piste_inconnue(self):
        # Quinte (7A), voisine élargie (10A) et relative (8B) sont des
        # relations DJ classiques : elles doivent être proposées, pas filtrées.
        cases = [("quinte", "7A"), ("elargie", "10A"), ("relative", "8B")]
        candidates, metadata = _candidates(*[(path, 128, case, 0) for path, case in cases])
        result = rank_candidates("source", AudioMetadata(128, "8A"), candidates, metadata, [])
        self.assertEqual({item.path for item in result}, {"quinte", "elargie", "relative"})

    def test_style_departage_a_tempo_egal(self):
        candidates, metadata = _candidates(("house", 124, "8A", 0), ("rap", 124, "8A", 0))
        metadata["house"] = AudioMetadata(124, "8A", "House")
        metadata["rap"] = AudioMetadata(124, "8A", "Hip Hop/Rap")
        result = rank_candidates("source", AudioMetadata(124, "8A", "Tech House"),
                                 candidates, metadata, [])
        self.assertEqual(result[0].path, "house")
        self.assertEqual(result[0].style, "House")

    def test_style_oppose_ecarte_la_proposition(self):
        candidates, metadata = _candidates(("metal", 128, "8A", 0))
        metadata["metal"] = AudioMetadata(128, "8A", "Metal")
        result = rank_candidates("source", AudioMetadata(128, "8A", "Techno"),
                                 candidates, metadata, [])
        self.assertEqual(result, [])

    def test_une_decouverte_garantie(self):
        # Que des habitudes connues : la liste doit quand même s'ouvrir sur une
        # piste jamais enchaînée mais compatible.
        candidates, metadata = _candidates(("vu1", 128, "8A", 5), ("vu2", 128, "8A", 4))
        candidates.append(("neuf", "Titre neuf", "Artiste neuf", 0))
        metadata["neuf"] = AudioMetadata(128, "8A")
        result = rank_candidates("source", AudioMetadata(128, "8A"), candidates, metadata,
                                 [], limit=3, discovery_slots=0, guarantee_discovery=True)
        self.assertEqual(result[-1].path, "neuf")

    def test_incompatibles_ecartes(self):
        candidates, metadata = _candidates(("faux", 100, "2A", 0))
        result = rank_candidates("source", AudioMetadata(128, "8A"), candidates, metadata, [])
        self.assertEqual(result, [])

    def test_habitude_prime_sur_theorie(self):
        candidates, metadata = _candidates(("vu", 124, "8A", 3), ("theorique", 128, "8A", 0))
        result = rank_candidates("source", AudioMetadata(128, "8A"), candidates, metadata, [])
        self.assertEqual(result[0].path, "vu")
        self.assertIn(result[0].category, ("red", "orange", "yellow"))

    def test_penalite_repetition(self):
        candidates, metadata = _candidates(("deja", 128, "8A", 0))
        plain = rank_candidates("source", AudioMetadata(128, "8A"), candidates, metadata, [])
        played = rank_candidates("source", AudioMetadata(128, "8A"), candidates, metadata,
                                 ["deja"], recent_paths=["deja"])
        self.assertLess(played[0].score, plain[0].score)

    def test_places_reservees_aux_decouvertes(self):
        candidates, metadata = _candidates(
            ("vu1", 128, "8A", 4), ("vu2", 128, "8A", 3), ("vu3", 128, "8A", 2),
            ("neuf1", 128, "8A", 0), ("neuf2", 127, "8A", 0), ("neuf3", 128, "8A", 0))
        result = rank_candidates("source", AudioMetadata(128, "8A"), candidates, metadata,
                                 [], limit=4, discovery_slots=2)
        self.assertEqual(len(result), 4)
        self.assertEqual(sum(1 for item in result if item.category == "blue"), 2)
        self.assertEqual(result[0].path, "vu1")  # la meilleure habitude reste en tête

    def test_diversite_artistes(self):
        candidates = [(f"a{index}", f"Titre {index}", "Meme Artiste", 0) for index in range(4)]
        metadata = {f"a{index}": AudioMetadata(128, "8A") for index in range(4)}
        result = rank_candidates("source", AudioMetadata(128, "8A"), candidates, metadata,
                                 [], limit=4, discovery_slots=0)
        self.assertEqual(len(result), 2)

    def test_source_sans_metadonnees(self):
        candidates, metadata = _candidates(("a", 128, "8A", 1))
        result = rank_candidates("source", AudioMetadata(), candidates, metadata, [],
                                 seed_paths=["source"])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].reason)


if __name__ == "__main__":
    unittest.main()
