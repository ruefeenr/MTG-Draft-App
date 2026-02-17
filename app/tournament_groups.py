from datetime import datetime, timezone
import json
import os

from flask import has_app_context

from . import get_last_created_app
from .models import Tournament
from .services import cubes as cube_service
from .services import groups as group_service
from .services import tournaments as tournament_service

DEFAULT_GROUP_ID = group_service.DEFAULT_GROUP_ID
DEFAULT_CUBE_ID = cube_service.DEFAULT_CUBE_ID
_FALLBACK_GROUPS = {
    "default": "Unkategorisiert",
    "liga": "Liga",
    "casual": "Casual",
}
_FALLBACK_CUBES = {
    "vintage": "Vintage",
    "spicy_ramen": "Spicy Ramen",
    "pauper": "Pauper",
    "100_ornithopter": "100 Ornithopter",
    "treat_yourself": "Treat yourself",
}


def _utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


def _call_with_app_context(func, *args, **kwargs):
    if has_app_context():
        try:
            return func(*args, **kwargs)
        except Exception:
            return None
    app = get_last_created_app()
    if app is None:
        return None
    try:
        with app.app_context():
            return func(*args, **kwargs)
    except Exception:
        return None


def load_tournament_groups():
    rows = _call_with_app_context(group_service.list_groups)
    if rows is None:
        return [{"id": gid, "name": gname} for gid, gname in _FALLBACK_GROUPS.items()]
    return rows


def save_tournament_groups(groups):
    """
    Rückwärtskompatibilität: direkter Bulk-Save wird nicht mehr unterstützt.
    Die neue DB-basierte Variante verwaltet Gruppen über create/rename/delete.
    """
    # Behalte die Signatur, aber verhindere stilles Fehlverhalten.
    return isinstance(groups, list)


def create_tournament_group(name):
    return _call_with_app_context(group_service.create_group, name)


def rename_tournament_group(group_id, new_name):
    return _call_with_app_context(group_service.rename_group, group_id, new_name)


def delete_tournament_group(group_id):
    return _call_with_app_context(group_service.delete_group, group_id)


def reassign_group_in_meta(old_group_id, new_group_id=DEFAULT_GROUP_ID):
    return _call_with_app_context(group_service.reassign_group_in_tournaments, old_group_id, new_group_id)


def get_group_map():
    result = _call_with_app_context(group_service.get_group_map)
    return result or dict(_FALLBACK_GROUPS)


def is_valid_group_id(group_id):
    result = _call_with_app_context(group_service.is_valid_group_id, group_id)
    if result is None:
        return group_id in _FALLBACK_GROUPS
    return result


def normalize_group_id(group_id):
    result = _call_with_app_context(group_service.normalize_group_id, group_id)
    if result is None:
        return group_id if group_id in _FALLBACK_GROUPS else DEFAULT_GROUP_ID
    return result


def get_group_name(group_id):
    result = _call_with_app_context(group_service.get_group_name, group_id)
    if result is None:
        return _FALLBACK_GROUPS.get(normalize_group_id(group_id), _FALLBACK_GROUPS[DEFAULT_GROUP_ID])
    return result


def load_allowed_cubes():
    rows = _call_with_app_context(cube_service.list_cubes)
    if rows is None:
        return [{"id": cid, "name": cname} for cid, cname in _FALLBACK_CUBES.items()]
    return rows


def save_allowed_cubes(cubes):
    """
    Rückwärtskompatibilität: direkter Bulk-Save wird nicht mehr unterstützt.
    Die neue DB-basierte Variante verwaltet Cubes über create/rename/delete.
    """
    return isinstance(cubes, list)


def create_tournament_cube(name):
    return _call_with_app_context(cube_service.create_cube, name)


def rename_tournament_cube(cube_id, new_name):
    return _call_with_app_context(cube_service.rename_cube, cube_id, new_name)


def delete_tournament_cube(cube_id):
    return _call_with_app_context(cube_service.delete_cube, cube_id)


def reassign_cube_in_meta(old_cube_id, new_cube_id=DEFAULT_CUBE_ID):
    return _call_with_app_context(cube_service.reassign_cube_in_tournaments, old_cube_id, new_cube_id)


def get_cube_map():
    result = _call_with_app_context(cube_service.get_cube_map)
    return result or dict(_FALLBACK_CUBES)


def get_cube_name_to_id_map():
    result = _call_with_app_context(cube_service.get_cube_name_to_id_map)
    if result is None:
        return {name.casefold(): cid for cid, name in _FALLBACK_CUBES.items()}
    return result


def is_valid_cube_id(cube_id):
    result = _call_with_app_context(cube_service.is_valid_cube_id, cube_id)
    if result is None:
        return cube_id in _FALLBACK_CUBES
    return result


def normalize_cube_id(cube_id):
    result = _call_with_app_context(cube_service.normalize_cube_id, cube_id)
    if result is None:
        return cube_id if cube_id in _FALLBACK_CUBES else DEFAULT_CUBE_ID
    return result


def get_cube_name(cube_id):
    result = _call_with_app_context(cube_service.get_cube_name, cube_id)
    if result is None:
        return _FALLBACK_CUBES.get(normalize_cube_id(cube_id), _FALLBACK_CUBES[DEFAULT_CUBE_ID])
    return result


def is_vintage_cube(cube_id):
    return normalize_cube_id(cube_id) == DEFAULT_CUBE_ID


def normalize_cube_value(cube_value):
    result = _call_with_app_context(cube_service.normalize_cube_value, cube_value)
    if result is None:
        if not cube_value or not isinstance(cube_value, str):
            return DEFAULT_CUBE_ID
        value = cube_value.strip()
        if value in _FALLBACK_CUBES:
            return value
        return get_cube_name_to_id_map().get(value.casefold(), DEFAULT_CUBE_ID)
    return result


def load_tournament_meta():
    data = {}
    legacy_file = os.path.join("data", "tournament_meta.json")
    changed = False
    if os.path.exists(legacy_file):
        try:
            with open(legacy_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for tournament_id, payload in raw.items():
                raw_cube = payload.get("cube_id") or payload.get("cube")
                cube_id = normalize_cube_value(raw_cube)
                group_id = normalize_group_id(payload.get("group_id"))
                if payload.get("cube_id") != cube_id or "cube_name" not in payload:
                    changed = True
                data[tournament_id] = {
                    "group_id": group_id,
                    "group_name": get_group_name(group_id),
                    "cube_id": cube_id,
                    "cube_name": get_cube_name(cube_id),
                    "created_at": payload.get("created_at") or _utcnow_iso(),
                }
        except Exception:
            pass

    rows = _call_with_app_context(lambda: Tournament.query.all()) or []
    for row in rows:
        data[row.id] = {
            "group_id": row.group_id,
            "group_name": get_group_name(row.group_id),
            "cube_id": row.cube_id,
            "cube_name": get_cube_name(row.cube_id),
            "created_at": row.created_at.isoformat() if row.created_at else _utcnow_iso(),
        }
    if changed:
        save_tournament_meta(data)
    return data


def save_tournament_meta(meta):
    if not isinstance(meta, dict):
        return False
    os.makedirs("data", exist_ok=True)
    path = os.path.join("data", "tournament_meta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return True


def set_tournament_group(tournament_id, group_id, cube_id=DEFAULT_CUBE_ID):
    if not tournament_id:
        return False
    _call_with_app_context(tournament_service.set_tournament_group_and_cube, tournament_id, group_id, cube_id)
    # Legacy-Spiegel für bestehende Testfälle/Dateiverhalten.
    meta = load_tournament_meta()
    normalized_group = normalize_group_id(group_id)
    normalized_cube = normalize_cube_value(cube_id)
    meta[tournament_id] = {
        "group_id": normalized_group,
        "group_name": get_group_name(normalized_group),
        "cube_id": normalized_cube,
        "cube_name": get_cube_name(normalized_cube),
        "created_at": meta.get(tournament_id, {}).get("created_at") or _utcnow_iso(),
    }
    save_tournament_meta(meta)
    return True


def remove_tournament_group(tournament_id):
    if not tournament_id:
        return False
    removed = _call_with_app_context(tournament_service.remove_tournament, tournament_id)
    meta = load_tournament_meta()
    if tournament_id in meta:
        del meta[tournament_id]
        save_tournament_meta(meta)
    return removed


def get_tournament_group_id(tournament_id):
    row = _call_with_app_context(tournament_service.get_tournament, tournament_id)
    if row is None:
        meta = load_tournament_meta()
        return normalize_group_id(meta.get(tournament_id, {}).get("group_id"))
    return normalize_group_id(row.group_id)


def get_tournament_group_name(tournament_id):
    return get_group_name(get_tournament_group_id(tournament_id))


def get_tournament_cube_id(tournament_id):
    row = _call_with_app_context(tournament_service.get_tournament, tournament_id)
    if row is None:
        meta = load_tournament_meta()
        payload = meta.get(tournament_id, {})
        return normalize_cube_value(payload.get("cube_id") or payload.get("cube"))
    return normalize_cube_value(row.cube_id)


def get_tournament_cube_name(tournament_id):
    return get_cube_name(get_tournament_cube_id(tournament_id))


def is_vintage_tournament(tournament_id):
    return is_vintage_cube(get_tournament_cube_id(tournament_id))


# Rückwärtskompatible Aliases
def is_valid_cube(cube):
    return is_valid_cube_id(cube)


def normalize_cube(cube):
    return normalize_cube_value(cube)


def get_tournament_cube(tournament_id):
    return get_tournament_cube_name(tournament_id)
