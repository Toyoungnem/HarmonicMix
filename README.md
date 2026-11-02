# Harmonic Mix

[⬇️ Télécharger Harmonic Mix pour Windows](https://github.com/Toyoungnem/HarmonicMix/releases/latest/download/HarmonicMix.exe) · [Voir la release](https://github.com/Toyoungnem/HarmonicMix/releases/latest)

Assistant local de suggestions de transitions pour Serato DJ Lite ou Traktor. Le classement combine les transitions observées dans les sets, le BPM et la tonalité Camelot. L'application ne capte pas le son et fonctionne hors ligne.

## Démarrer

### Version Windows prête à lancer

[Télécharger HarmonicMix.exe](https://github.com/Toyoungnem/HarmonicMix/releases/latest/download/HarmonicMix.exe), puis double-cliquer sur le fichier téléchargé. Python n'est pas nécessaire. Serato DJ Lite ou Traktor doit être installé séparément, et Harmonic Mix utilise les historiques présents sur l'ordinateur.

### Depuis les sources

Pour lancer le programme avec Python :

```powershell
python -m pip install -r requirements.txt
python app.py
```

Sous Windows, `build_exe.bat` génère une application autonome dans `dist/HarmonicMix.exe`. Python n'est alors pas nécessaire pour l'utiliser. La base locale de l'application est conservée dans `%LOCALAPPDATA%/HarmonicMix`.

## Utilisation

- Sur l'écran d'accueil, choisis **Serato DJ** ou **Traktor**. Ce choix et le nom du profil restent enregistrés localement.
- L'écran d'accueil affiche la piste de référence et permet d'ouvrir le panneau de suggestions.
- Les suggestions rouges, orange et jaunes s'appuient sur les transitions observées ; les bleues sont des propositions harmoniques sans transition connue.
- Sélectionne une suggestion puis **Chercher dans…** pour lancer la recherche dans le logiciel choisi. Vérifie le résultat puis charge-le sur le deck.
- Le panneau vérifie les changements d'historique toutes les cinq secondes et reste épinglé au premier plan par défaut.

Les profils sont de simples espaces de données locaux, sans mot de passe, chiffrement ni synchronisation. Ils conviennent pour séparer les bibliothèques sur un même PC, pas pour protéger les données entre utilisateurs du même compte Windows.

## Traktor

- Le lecteur Traktor lit en local `collection.nml` et les playlists `.nml` dans le dossier `History` des dossiers `Documents/Native Instruments/Traktor*` ou `Music/Native Instruments/Traktor*`.
- Traktor enregistre ses playlists d'historique à la fermeture. Harmonic Mix affiche donc la dernière session archivée et apprend les transitions entre les morceaux de ces sessions ; le suivi live Traktor n'est pas pris en charge.
- Le bouton de recherche utilise le champ de recherche du logiciel ouvert. Vérifie le résultat avant de charger une piste.
- La prise en charge a été développée sans installation locale de Traktor : confirme-la avec une bibliothèque et une session `.nml` réelles sur le PC de ton ami.

## Données

- `serato_db.py` lit la base Serato en lecture seule, normalement située dans `%LOCALAPPDATA%/Serato/Library/master.sqlite`.
- `traktor_db.py` lit la collection et les sessions Traktor NML en lecture seule.
- Les fichiers `.session` sont recherchés dans `%USERPROFILE%/Music/_Serato_/History/Sessions`.
- `parser.py` lit les sessions Serato en repli ; `scoring.py` calcule la compatibilité ; `ui.py` contient l'interface ; `profiles.py` gère les profils locaux.
- Les bases SQLite, les sessions et les fichiers générés (`build/`, `dist/`) sont ignorés par Git pour protéger les données locales.

## Dépendances

```powershell
python -m pip install -r requirements.txt
```

Les dépendances sont listées dans `requirements.txt`. PyInstaller n'est nécessaire que pour reconstruire l'exécutable avec `build_exe.bat`.
