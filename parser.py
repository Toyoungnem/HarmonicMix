from __future__ import annotations

import argparse
import json
import struct
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SESSIONS_DIR = Path.home() / "Music" / "_Serato_" / "History" / "Sessions"


@dataclass(frozen=True)
class TrackPlay:
    """Un morceau enregistré dans un fichier d'historique Serato."""

    path: str
    title: str | None
    artist: str | None
    start_time: datetime | None
    end_time: datetime | None


def _chunks(data: bytes):
    """Lit les blocs Serato de la forme: tag ASCII (4 octets), taille BE, contenu."""
    offset = 0
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError(f"En-tête incomplet à l'octet {offset}")

        try:
            tag = data[offset : offset + 4].decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Balise invalide à l'octet {offset}") from exc

        size = struct.unpack_from(">I", data, offset + 4)[0]
        start = offset + 8
        end = start + size
        if end > len(data):
            raise ValueError(f"Bloc {tag!r} tronqué à l'octet {offset}")

        yield tag, data[start:end]
        offset = end


def _fields(data: bytes) -> dict[int, bytes]:
    """Lit les champs internes d'un bloc adat (identifiant + taille + valeur)."""
    fields: dict[int, bytes] = {}
    offset = 0
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError(f"Champ adat incomplet à l'octet {offset}")

        field_id, size = struct.unpack_from(">II", data, offset)
        start = offset + 8
        end = start + size
        if end > len(data):
            raise ValueError(f"Champ adat {field_id:#x} tronqué")

        fields[field_id] = data[start:end]
        offset = end
    return fields


def _text(fields: dict[int, bytes], field_id: int) -> str | None:
    value = fields.get(field_id)
    if value is None:
        return None
    # Les chaînes observées dans les sessions Serato sont en UTF-16 big-endian.
    return value.decode("utf-16-be", errors="replace").rstrip("\0").strip() or None


def _timestamp(fields: dict[int, bytes], field_id: int) -> datetime | None:
    value = fields.get(field_id)
    if value is None or len(value) != 8:
        return None
    seconds = struct.unpack(">Q", value)[0]
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone()
    except (OverflowError, OSError, ValueError):
        return None


def parse_session(path: str | Path) -> list[TrackPlay]:
    """Parse une session Serato et retourne ses morceaux dans l'ordre du fichier."""
    session_path = Path(path)
    data = session_path.read_bytes()
    plays: list[TrackPlay] = []

    for tag, payload in _chunks(data):
        if tag != "oent":
            continue
        for child_tag, child_payload in _chunks(payload):
            if child_tag != "adat":
                continue
            fields = _fields(child_payload)
            track_path = _text(fields, 0x02)
            if not track_path:
                continue
            plays.append(
                TrackPlay(
                    path=track_path,
                    title=_text(fields, 0x06),
                    artist=_text(fields, 0x07),
                    start_time=_timestamp(fields, 0x1C),
                    end_time=_timestamp(fields, 0x1D),
                )
            )
    return plays


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Lit un fichier d'historique Serato .session")
    parser.add_argument("session", nargs="?", type=Path, help="fichier .session à lire")
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS_DIR,
                        help="dossier Serato utilisé si aucun fichier n'est indiqué")
    parser.add_argument("--json", action="store_true", help="affiche le résultat en JSON")
    args = parser.parse_args()

    session_path = args.session
    if session_path is None:
        files = list(args.sessions_dir.glob("*.session"))
        if not files:
            parser.error(f"aucun fichier .session dans {args.sessions_dir}")
        session_path = max(files, key=lambda item: item.stat().st_mtime)

    plays = parse_session(session_path)
    if args.json:
        print(json.dumps([
            {**asdict(play), "start_time": _iso(play.start_time), "end_time": _iso(play.end_time)}
            for play in plays
        ], ensure_ascii=False, indent=2))
        return

    print(f"Session : {session_path}")
    print(f"Morceaux : {len(plays)}")
    print()
    print(f"{'#':>3}  {'Début':19}  {'Fin':19}  Artiste — titre")
    for index, play in enumerate(plays, 1):
        start = _iso(play.start_time) or "—"
        end = _iso(play.end_time) or "—"
        name = " — ".join(part for part in (play.artist, play.title) if part) or play.path
        print(f"{index:>3}  {start:19}  {end:19}  {name}")


if __name__ == "__main__":
    main()
