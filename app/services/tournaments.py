from datetime import datetime, timezone

from ..db import db
from ..models import Tournament
from .cubes import DEFAULT_CUBE_ID, normalize_cube_value
from .groups import DEFAULT_GROUP_ID, normalize_group_id


def create_tournament(tournament_id, group_id=DEFAULT_GROUP_ID, cube_id=DEFAULT_CUBE_ID, status="running"):
    normalized_group_id = normalize_group_id(group_id)
    normalized_cube_id = normalize_cube_value(cube_id)
    tournament = Tournament(
        id=tournament_id,
        group_id=normalized_group_id,
        cube_id=normalized_cube_id,
        status=status,
        current_round=1,
    )
    db.session.add(tournament)
    db.session.commit()
    return tournament


def get_tournament(tournament_id):
    if not tournament_id:
        return None
    return db.session.get(Tournament, tournament_id)


def ensure_tournament(tournament_id, group_id=DEFAULT_GROUP_ID, cube_id=DEFAULT_CUBE_ID):
    row = get_tournament(tournament_id)
    if row:
        return row
    return create_tournament(tournament_id=tournament_id, group_id=group_id, cube_id=cube_id)


def set_tournament_group_and_cube(tournament_id, group_id, cube_id):
    row = ensure_tournament(tournament_id, group_id=group_id, cube_id=cube_id)
    row.group_id = normalize_group_id(group_id)
    row.cube_id = normalize_cube_value(cube_id)
    db.session.commit()
    return row


def remove_tournament(tournament_id):
    row = get_tournament(tournament_id)
    if row is None:
        return True
    db.session.delete(row)
    db.session.commit()
    return True


def set_tournament_status(tournament_id, status):
    row = get_tournament(tournament_id)
    if row is None:
        return None
    row.status = status
    if status == "ended":
        row.ended_at = datetime.now(timezone.utc)
    db.session.commit()
    return row
