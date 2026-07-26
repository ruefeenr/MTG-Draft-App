from sqlalchemy.exc import IntegrityError

from ..db import db
from ..models import Player
from .normalize import normalize_name


def _is_deleted_player_name(name: str) -> bool:
    return isinstance(name, str) and name.startswith("DELETED_PLAYER")


def get_or_create_player(player_name):
    cleaned = (player_name or "").strip()
    if not cleaned:
        return None
    normalized = normalize_name(cleaned)
    existing = Player.query.filter_by(normalized_name=normalized).first()
    if existing:
        return existing
    # Savepoint statt commit/rollback: Ein Unique-Konflikt (paralleler Request
    # legt denselben Spieler an) darf nicht die äussere Transaktion des
    # Aufrufers (z.B. _sync_round_to_db) zurückrollen.
    try:
        with db.session.begin_nested():
            row = Player(name=cleaned, normalized_name=normalized)
            db.session.add(row)
    except IntegrityError:
        return Player.query.filter_by(normalized_name=normalized).first()
    return row


def list_player_names():
    rows = Player.query.order_by(Player.name.asc()).all()
    return [row.name for row in rows if row.name and not _is_deleted_player_name(row.name)]
