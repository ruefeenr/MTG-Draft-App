import uuid

from sqlalchemy.exc import IntegrityError

from ..db import db
from ..models import Tournament, TournamentGroup
from .normalize import normalize_name, slugify_group_name


DEFAULT_GROUP_ID = "default"
DEFAULT_GROUP_NAME = "Unkategorisiert"


def ensure_default_groups():
    defaults = [
        (DEFAULT_GROUP_ID, DEFAULT_GROUP_NAME, True),
        ("liga", "Liga", True),
        ("casual", "Casual", True),
    ]
    changed = False
    for group_id, group_name, is_system in defaults:
        group = db.session.get(TournamentGroup, group_id)
        normalized = normalize_name(group_name)
        if group is None:
            db.session.add(
                TournamentGroup(
                    id=group_id,
                    name=group_name,
                    normalized_name=normalized,
                    is_system=is_system,
                )
            )
            changed = True
        else:
            if group.name != group_name or group.normalized_name != normalized:
                group.name = group_name
                group.normalized_name = normalized
                changed = True
            if is_system and not group.is_system:
                group.is_system = True
                changed = True
    if changed:
        db.session.commit()


def list_groups():
    ensure_default_groups()
    rows = TournamentGroup.query.order_by(TournamentGroup.id != DEFAULT_GROUP_ID, TournamentGroup.name.asc()).all()
    return [{"id": row.id, "name": row.name} for row in rows]


def get_group_map():
    return {row["id"]: row["name"] for row in list_groups()}


def is_valid_group_id(group_id):
    if not group_id or not isinstance(group_id, str):
        return False
    return group_id in get_group_map()


def normalize_group_id(group_id):
    if is_valid_group_id(group_id):
        return group_id
    return DEFAULT_GROUP_ID


def get_group_name(group_id):
    return get_group_map().get(normalize_group_id(group_id), DEFAULT_GROUP_NAME)


def _generate_unique_group_id(name):
    base = slugify_group_name(name)
    if TournamentGroup.query.get(base) is None:
        return base
    while True:
        candidate = f"{base}-{uuid.uuid4().hex[:4]}"
        if TournamentGroup.query.get(candidate) is None:
            return candidate


def create_group(name):
    group_name = (name or "").strip()
    if not group_name:
        return False, "Bitte einen Gruppennamen angeben.", None
    if len(group_name) > 80:
        return False, "Gruppenname darf maximal 80 Zeichen lang sein.", None

    ensure_default_groups()
    normalized = normalize_name(group_name)
    existing = TournamentGroup.query.filter_by(normalized_name=normalized).first()
    if existing:
        return False, "Eine Gruppe mit diesem Namen existiert bereits.", None

    group_id = _generate_unique_group_id(group_name)
    row = TournamentGroup(id=group_id, name=group_name, normalized_name=normalized, is_system=False)
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, "Gruppe konnte nicht gespeichert werden.", None
    return True, f"Gruppe '{group_name}' wurde erstellt.", {"id": row.id, "name": row.name}


def rename_group(group_id, new_name):
    target_id = (group_id or "").strip()
    target_name = (new_name or "").strip()
    if not target_id:
        return False, "Ungültige Gruppen-ID."
    if target_id == DEFAULT_GROUP_ID:
        return False, "Die Standardgruppe kann nicht umbenannt werden."
    if not target_name:
        return False, "Bitte einen neuen Gruppennamen angeben."
    if len(target_name) > 80:
        return False, "Gruppenname darf maximal 80 Zeichen lang sein."

    ensure_default_groups()
    row = TournamentGroup.query.get(target_id)
    if row is None:
        return False, "Gruppe wurde nicht gefunden."

    normalized = normalize_name(target_name)
    duplicate = TournamentGroup.query.filter(
        TournamentGroup.normalized_name == normalized,
        TournamentGroup.id != target_id,
    ).first()
    if duplicate:
        return False, "Eine Gruppe mit diesem Namen existiert bereits."

    row.name = target_name
    row.normalized_name = normalized
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, "Gruppe konnte nicht umbenannt werden."
    return True, f"Gruppe wurde in '{target_name}' umbenannt."


def reassign_group_in_tournaments(old_group_id, new_group_id=DEFAULT_GROUP_ID):
    source_id = (old_group_id or "").strip()
    if not source_id:
        return 0
    target_id = normalize_group_id(new_group_id)
    affected = Tournament.query.filter(Tournament.group_id == source_id).count()
    if affected == 0:
        return 0
    Tournament.query.filter(Tournament.group_id == source_id).update({Tournament.group_id: target_id})
    db.session.commit()
    return affected


def delete_group(group_id):
    target_id = (group_id or "").strip()
    if not target_id:
        return False, "Ungültige Gruppen-ID."
    if target_id == DEFAULT_GROUP_ID:
        return False, "Die Standardgruppe kann nicht gelöscht werden."

    row = TournamentGroup.query.get(target_id)
    if row is None:
        return False, "Gruppe wurde nicht gefunden."
    db.session.delete(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, "Gruppe konnte nicht gelöscht werden."
    return True, "Gruppe wurde gelöscht."
