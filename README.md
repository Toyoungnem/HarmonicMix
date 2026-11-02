# Harmonic Mix

Assistant local de suggestions de transitions pour Serato DJ Lite. Le classement combine les transitions observées dans les sets, le BPM et la tonalité Camelot. L'application ne capte pas le son et fonctionne hors ligne.

## Démarrer

Pour lancer le programme avec Python :

```powershell
python -m pip install -r requirements.txt
python app.py
```

Sous Windows, `build_exe.bat` génère une application autonome dans `dist/HarmonicMix.exe`. Python n'est alors pas nécessaire pour l'utiliser. La base locale de l'application est conservée dans `%LOCALAPPDATA%/HarmonicMix`.

## Utilisation

- L'écran d'accueil affiche la dernière piste et permet d'ouvrir le panneau de suggestions.
- Les suggestions rouges, orange et jaunes s'appuient sur les transitions observées ; les bleues sont des propositions harmoniques sans transition connue.
- Sélectionne une suggestion puis **Chercher dans Serato** pour filtrer la bibliothèque. Choisis ensuite le deck dans Serato.
- Le panneau vérifie les changements de l'historique toutes les cinq secondes et reste épinglé au premier plan par défaut.

## Données

- `serato_db.py` lit la base Serato en lecture seule, normalement située dans `%LOCALAPPDATA%/Serato/Library/master.sqlite`.
- Les fichiers `.session` sont recherchés dans `%USERPROFILE%/Music/_Serato_/History/Sessions`.
- `parser.py` lit les sessions en repli ; `scoring.py` calcule la compatibilité ; `ui.py` contient l'interface.
- `suggestions.sqlite3`, les journaux personnels, les sessions et les fichiers générés (`build/`, `dist/`) sont ignorés par Git pour protéger les données locales.

## Dépendances

```powershell
python -m pip install -r requirements.txt
```

Les dépendances sont listées dans `requirements.txt`. PyInstaller n'est nécessaire que pour reconstruire l'exécutable avec `build_exe.bat`.
