from sqlalchemy.exc import IntegrityError

from ..db import db
from ..models import Player
from .normalize import normalize_name


def get_or_create_player(player_name):
    cleaned = (player_name or "").strip()
    if not cleaned:
        return None
    normalized = normalize_name(cleaned)
    existing = Player.query.filter_by(normalized_name=normalized).first()
    if existing:
        return existing
    row = Player(name=cleaned, normalized_name=normalized)
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return Player.query.filter_by(normalized_name=normalized).first()
    return row


def list_player_names():
    rows = Player.query.order_by(Player.name.asc()).all()
    return [row.name for row in rows]
