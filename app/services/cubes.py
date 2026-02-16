import uuid

from sqlalchemy.exc import IntegrityError

from ..db import db
from ..models import Cube, Tournament
from .normalize import normalize_name, slugify_cube_name


DEFAULT_CUBE_ID = "vintage"
DEFAULT_CUBE_NAME = "Vintage"


def ensure_default_cubes():
    defaults = [
        (DEFAULT_CUBE_ID, DEFAULT_CUBE_NAME, True),
        ("spicy_ramen", "Spicy Ramen", True),
        ("pauper", "Pauper", True),
        ("100_ornithopter", "100 Ornithopter", True),
        ("treat_yourself", "Treat yourself", True),
    ]
    changed = False
    for cube_id, cube_name, is_system in defaults:
        cube = db.session.get(Cube, cube_id)
        normalized = normalize_name(cube_name)
        if cube is None:
            db.session.add(Cube(id=cube_id, name=cube_name, normalized_name=normalized, is_system=is_system))
            changed = True
        else:
            if cube.name != cube_name or cube.normalized_name != normalized:
                cube.name = cube_name
                cube.normalized_name = normalized
                changed = True
            if is_system and not cube.is_system:
                cube.is_system = True
                changed = True
    if changed:
        db.session.commit()


def list_cubes():
    ensure_default_cubes()
    rows = Cube.query.order_by(Cube.id != DEFAULT_CUBE_ID, Cube.name.asc()).all()
    return [{"id": row.id, "name": row.name} for row in rows]


def get_cube_map():
    return {row["id"]: row["name"] for row in list_cubes()}


def get_cube_name_to_id_map():
    return {row["name"].casefold(): row["id"] for row in list_cubes()}


def is_valid_cube_id(cube_id):
    if not cube_id or not isinstance(cube_id, str):
        return False
    return cube_id in get_cube_map()


def normalize_cube_id(cube_id):
    if is_valid_cube_id(cube_id):
        return cube_id
    return DEFAULT_CUBE_ID


def get_cube_name(cube_id):
    return get_cube_map().get(normalize_cube_id(cube_id), DEFAULT_CUBE_NAME)


def normalize_cube_value(cube_value):
    if not cube_value or not isinstance(cube_value, str):
        return DEFAULT_CUBE_ID
    value = cube_value.strip()
    if is_valid_cube_id(value):
        return value
    return get_cube_name_to_id_map().get(value.casefold(), DEFAULT_CUBE_ID)


def _generate_unique_cube_id(name):
    base = slugify_cube_name(name)
    if base == DEFAULT_CUBE_ID:
        base = f"{base}_custom"
    if Cube.query.get(base) is None:
        return base
    while True:
        candidate = f"{base}_{uuid.uuid4().hex[:4]}"
        if Cube.query.get(candidate) is None:
            return candidate


def create_cube(name):
    cube_name = (name or "").strip()
    if not cube_name:
        return False, "Bitte einen Cube-Namen angeben.", None
    if len(cube_name) > 80:
        return False, "Cube-Name darf maximal 80 Zeichen lang sein.", None

    ensure_default_cubes()
    normalized = normalize_name(cube_name)
    existing = Cube.query.filter_by(normalized_name=normalized).first()
    if existing:
        return False, "Ein Cube mit diesem Namen existiert bereits.", None

    cube_id = _generate_unique_cube_id(cube_name)
    row = Cube(id=cube_id, name=cube_name, normalized_name=normalized, is_system=False)
    db.session.add(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, "Cube konnte nicht gespeichert werden.", None
    return True, f"Cube '{cube_name}' wurde erstellt.", {"id": row.id, "name": row.name}


def rename_cube(cube_id, new_name):
    target_id = (cube_id or "").strip()
    target_name = (new_name or "").strip()
    if not target_id:
        return False, "Ungültige Cube-ID."
    if target_id == DEFAULT_CUBE_ID:
        return False, "Der Standard-Cube kann nicht umbenannt werden."
    if not target_name:
        return False, "Bitte einen neuen Cube-Namen angeben."
    if len(target_name) > 80:
        return False, "Cube-Name darf maximal 80 Zeichen lang sein."

    ensure_default_cubes()
    row = Cube.query.get(target_id)
    if row is None:
        return False, "Cube wurde nicht gefunden."

    normalized = normalize_name(target_name)
    duplicate = Cube.query.filter(Cube.normalized_name == normalized, Cube.id != target_id).first()
    if duplicate:
        return False, "Ein Cube mit diesem Namen existiert bereits."

    row.name = target_name
    row.normalized_name = normalized
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, "Cube konnte nicht umbenannt werden."
    return True, f"Cube wurde in '{target_name}' umbenannt."


def reassign_cube_in_tournaments(old_cube_id, new_cube_id=DEFAULT_CUBE_ID):
    source_id = (old_cube_id or "").strip()
    if not source_id:
        return 0
    target_id = normalize_cube_id(new_cube_id)
    affected = Tournament.query.filter(Tournament.cube_id == source_id).count()
    if affected == 0:
        return 0
    Tournament.query.filter(Tournament.cube_id == source_id).update({Tournament.cube_id: target_id})
    db.session.commit()
    return affected


def delete_cube(cube_id):
    target_id = (cube_id or "").strip()
    if not target_id:
        return False, "Ungültige Cube-ID."
    if target_id == DEFAULT_CUBE_ID:
        return False, "Der Standard-Cube kann nicht gelöscht werden."

    row = Cube.query.get(target_id)
    if row is None:
        return False, "Cube wurde nicht gefunden."
    db.session.delete(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, "Cube konnte nicht gelöscht werden."
    return True, "Cube wurde gelöscht."
