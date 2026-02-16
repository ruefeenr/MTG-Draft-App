import json
import os
import re
import unicodedata
import uuid
from datetime import datetime

DEFAULT_GROUP_ID = "default"
DEFAULT_CUBE_ID = "vintage"

DEFAULT_GROUPS = [
    {"id": DEFAULT_GROUP_ID, "name": "Unkategorisiert"},
    {"id": "liga", "name": "Liga"},
    {"id": "casual", "name": "Casual"},
]

DEFAULT_CUBES = [
    {"id": "vintage", "name": "Vintage"},
    {"id": "spicy_ramen", "name": "Spicy Ramen"},
    {"id": "pauper", "name": "Pauper"},
    {"id": "100_ornithopter", "name": "100 Ornithopter"},
    {"id": "treat_yourself", "name": "Treat yourself"},
]


def _data_dir():
    return "data"


def _groups_file():
    return os.path.join(_data_dir(), "tournament_groups.json")


def _cubes_file():
    return os.path.join(_data_dir(), "tournament_cubes.json")


def _meta_file():
    return os.path.join(_data_dir(), "tournament_meta.json")


def _ensure_data_dir():
    os.makedirs(_data_dir(), exist_ok=True)


def load_tournament_groups():
    """Lädt verfügbare Turniergruppen; fällt robust auf Defaults zurück."""
    _ensure_data_dir()
    path = _groups_file()
    if not os.path.exists(path):
        return DEFAULT_GROUPS.copy()

    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if not isinstance(loaded, list):
                return DEFAULT_GROUPS.copy()

            valid = []
            seen_ids = set()
            for group in loaded:
                if not isinstance(group, dict):
                    continue
                group_id = (group.get("id") or "").strip()
                group_name = (group.get("name") or "").strip()
                if not group_id or not group_name or group_id in seen_ids:
                    continue
                seen_ids.add(group_id)
                valid.append({"id": group_id, "name": group_name})

            if not valid:
                return DEFAULT_GROUPS.copy()

            if DEFAULT_GROUP_ID not in seen_ids:
                valid.insert(0, {"id": DEFAULT_GROUP_ID, "name": "Unkategorisiert"})
            return valid
    except (IOError, OSError, json.JSONDecodeError):
        return DEFAULT_GROUPS.copy()

def save_tournament_groups(groups):
    """Speichert Turniergruppen robust in data/tournament_groups.json."""
    if not isinstance(groups, list):
        return False

    normalized_groups = []
    seen_ids = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = (group.get("id") or "").strip()
        group_name = (group.get("name") or "").strip()
        if not group_id or not group_name or group_id in seen_ids:
            continue
        seen_ids.add(group_id)
        normalized_groups.append({"id": group_id, "name": group_name})

    # Default-Gruppe muss immer vorhanden und stabil benannt sein.
    if DEFAULT_GROUP_ID not in seen_ids:
        normalized_groups.insert(0, {"id": DEFAULT_GROUP_ID, "name": "Unkategorisiert"})
    else:
        normalized_groups = [
            {"id": group["id"], "name": ("Unkategorisiert" if group["id"] == DEFAULT_GROUP_ID else group["name"])}
            for group in normalized_groups
        ]
        normalized_groups.sort(key=lambda group: group["id"] != DEFAULT_GROUP_ID)

    _ensure_data_dir()
    path = _groups_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(normalized_groups, f, indent=2, ensure_ascii=False)
        return True
    except (IOError, OSError):
        return False


def _slugify_group_name(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "gruppe"


def _generate_unique_group_id(name, existing_ids):
    base_slug = _slugify_group_name(name)
    if base_slug not in existing_ids:
        return base_slug
    while True:
        candidate = f"{base_slug}-{uuid.uuid4().hex[:4]}"
        if candidate not in existing_ids:
            return candidate


def _slugify_cube_name(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")
    return slug or "cube"


def _generate_unique_cube_id(name, existing_ids):
    base_slug = _slugify_cube_name(name)
    if base_slug == DEFAULT_CUBE_ID:
        base_slug = f"{base_slug}_custom"
    if base_slug not in existing_ids:
        return base_slug
    while True:
        candidate = f"{base_slug}_{uuid.uuid4().hex[:4]}"
        if candidate not in existing_ids:
            return candidate


def create_tournament_group(name):
    group_name = (name or "").strip()
    if not group_name:
        return False, "Bitte einen Gruppennamen angeben.", None
    if len(group_name) > 80:
        return False, "Gruppenname darf maximal 80 Zeichen lang sein.", None

    groups = load_tournament_groups()
    if any((group.get("name") or "").strip().casefold() == group_name.casefold() for group in groups):
        return False, "Eine Gruppe mit diesem Namen existiert bereits.", None

    existing_ids = {group["id"] for group in groups if isinstance(group, dict) and group.get("id")}
    group_id = _generate_unique_group_id(group_name, existing_ids)
    new_group = {"id": group_id, "name": group_name}
    groups.append(new_group)
    if not save_tournament_groups(groups):
        return False, "Gruppe konnte nicht gespeichert werden.", None
    return True, f"Gruppe '{group_name}' wurde erstellt.", new_group


def rename_tournament_group(group_id, new_name):
    target_group_id = (group_id or "").strip()
    target_name = (new_name or "").strip()
    if not target_group_id:
        return False, "Ungültige Gruppen-ID."
    if target_group_id == DEFAULT_GROUP_ID:
        return False, "Die Standardgruppe kann nicht umbenannt werden."
    if not target_name:
        return False, "Bitte einen neuen Gruppennamen angeben."
    if len(target_name) > 80:
        return False, "Gruppenname darf maximal 80 Zeichen lang sein."

    groups = load_tournament_groups()
    index = next((i for i, group in enumerate(groups) if group.get("id") == target_group_id), -1)
    if index == -1:
        return False, "Gruppe wurde nicht gefunden."
    if any(
        i != index and (group.get("name") or "").strip().casefold() == target_name.casefold()
        for i, group in enumerate(groups)
    ):
        return False, "Eine Gruppe mit diesem Namen existiert bereits."

    groups[index]["name"] = target_name
    if not save_tournament_groups(groups):
        return False, "Gruppe konnte nicht umbenannt werden."

    # Namen in bestehenden Turnier-Metadaten synchron halten.
    meta = load_tournament_meta()
    changed = False
    for entry in meta.values():
        if not isinstance(entry, dict):
            continue
        if (entry.get("group_id") or "").strip() == target_group_id:
            if entry.get("group_name") != target_name:
                entry["group_name"] = target_name
                changed = True
    if changed:
        save_tournament_meta(meta)
    return True, f"Gruppe wurde in '{target_name}' umbenannt."


def delete_tournament_group(group_id):
    target_group_id = (group_id or "").strip()
    if not target_group_id:
        return False, "Ungültige Gruppen-ID."
    if target_group_id == DEFAULT_GROUP_ID:
        return False, "Die Standardgruppe kann nicht gelöscht werden."

    groups = load_tournament_groups()
    filtered_groups = [group for group in groups if group.get("id") != target_group_id]
    if len(filtered_groups) == len(groups):
        return False, "Gruppe wurde nicht gefunden."
    if not save_tournament_groups(filtered_groups):
        return False, "Gruppe konnte nicht gelöscht werden."
    return True, "Gruppe wurde gelöscht."


def reassign_group_in_meta(old_group_id, new_group_id=DEFAULT_GROUP_ID):
    """Setzt alle Turniere mit alter Gruppe auf eine neue Gruppe um."""
    source_group_id = (old_group_id or "").strip()
    if not source_group_id:
        return 0
    target_group_id = normalize_group_id(new_group_id)

    meta = load_tournament_meta()
    changed = False
    affected = 0
    for entry in meta.values():
        if not isinstance(entry, dict):
            continue
        raw_group_id = (entry.get("group_id") or "").strip()
        normalized_entry_group = normalize_group_id(raw_group_id)
        if raw_group_id == source_group_id or normalized_entry_group == source_group_id:
            entry["group_id"] = target_group_id
            entry["group_name"] = get_group_name(target_group_id)
            affected += 1
            changed = True

    if changed:
        save_tournament_meta(meta)
    return affected


def get_group_map():
    groups = load_tournament_groups()
    return {group["id"]: group["name"] for group in groups}


def is_valid_group_id(group_id):
    if not group_id or not isinstance(group_id, str):
        return False
    return group_id in get_group_map()


def normalize_group_id(group_id):
    if is_valid_group_id(group_id):
        return group_id
    return DEFAULT_GROUP_ID


def get_group_name(group_id):
    group_map = get_group_map()
    normalized = normalize_group_id(group_id)
    return group_map.get(normalized, "Unkategorisiert")


def load_allowed_cubes():
    """Lädt verfügbare Cubes; fällt robust auf Defaults zurück."""
    _ensure_data_dir()
    path = _cubes_file()
    if not os.path.exists(path):
        return [cube.copy() for cube in DEFAULT_CUBES]

    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if not isinstance(loaded, list):
                return [cube.copy() for cube in DEFAULT_CUBES]

            valid = []
            seen_ids = set()
            for cube in loaded:
                if not isinstance(cube, dict):
                    continue
                cube_id = (cube.get("id") or "").strip()
                cube_name = (cube.get("name") or "").strip()
                if not cube_id or not cube_name or cube_id in seen_ids:
                    continue
                seen_ids.add(cube_id)
                valid.append({"id": cube_id, "name": cube_name})

            if not valid:
                return [cube.copy() for cube in DEFAULT_CUBES]

            if DEFAULT_CUBE_ID not in seen_ids:
                valid.insert(0, {"id": DEFAULT_CUBE_ID, "name": "Vintage"})
            return valid
    except (IOError, OSError, json.JSONDecodeError):
        return [cube.copy() for cube in DEFAULT_CUBES]


def save_allowed_cubes(cubes):
    """Speichert Cubes robust in data/tournament_cubes.json."""
    if not isinstance(cubes, list):
        return False

    normalized_cubes = []
    seen_ids = set()
    for cube in cubes:
        if not isinstance(cube, dict):
            continue
        cube_id = (cube.get("id") or "").strip()
        cube_name = (cube.get("name") or "").strip()
        if not cube_id or not cube_name or cube_id in seen_ids:
            continue
        seen_ids.add(cube_id)
        normalized_cubes.append({"id": cube_id, "name": cube_name})

    # Vintage muss immer vorhanden und stabil benannt sein.
    if DEFAULT_CUBE_ID not in seen_ids:
        normalized_cubes.insert(0, {"id": DEFAULT_CUBE_ID, "name": "Vintage"})
    else:
        normalized_cubes = [
            {"id": cube["id"], "name": ("Vintage" if cube["id"] == DEFAULT_CUBE_ID else cube["name"])}
            for cube in normalized_cubes
        ]
        normalized_cubes.sort(key=lambda cube: cube["id"] != DEFAULT_CUBE_ID)

    _ensure_data_dir()
    path = _cubes_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(normalized_cubes, f, indent=2, ensure_ascii=False)
        return True
    except (IOError, OSError):
        return False


def create_tournament_cube(name):
    cube_name = (name or "").strip()
    if not cube_name:
        return False, "Bitte einen Cube-Namen angeben.", None
    if len(cube_name) > 80:
        return False, "Cube-Name darf maximal 80 Zeichen lang sein.", None

    cubes = load_allowed_cubes()
    if any((cube.get("name") or "").strip().casefold() == cube_name.casefold() for cube in cubes):
        return False, "Ein Cube mit diesem Namen existiert bereits.", None

    existing_ids = {cube["id"] for cube in cubes if isinstance(cube, dict) and cube.get("id")}
    cube_id = _generate_unique_cube_id(cube_name, existing_ids)
    new_cube = {"id": cube_id, "name": cube_name}
    cubes.append(new_cube)
    if not save_allowed_cubes(cubes):
        return False, "Cube konnte nicht gespeichert werden.", None
    return True, f"Cube '{cube_name}' wurde erstellt.", new_cube


def rename_tournament_cube(cube_id, new_name):
    target_cube_id = (cube_id or "").strip()
    target_name = (new_name or "").strip()
    if not target_cube_id:
        return False, "Ungültige Cube-ID."
    if target_cube_id == DEFAULT_CUBE_ID:
        return False, "Der Standard-Cube kann nicht umbenannt werden."
    if not target_name:
        return False, "Bitte einen neuen Cube-Namen angeben."
    if len(target_name) > 80:
        return False, "Cube-Name darf maximal 80 Zeichen lang sein."

    cubes = load_allowed_cubes()
    index = next((i for i, cube in enumerate(cubes) if cube.get("id") == target_cube_id), -1)
    if index == -1:
        return False, "Cube wurde nicht gefunden."
    if any(
        i != index and (cube.get("name") or "").strip().casefold() == target_name.casefold()
        for i, cube in enumerate(cubes)
    ):
        return False, "Ein Cube mit diesem Namen existiert bereits."

    cubes[index]["name"] = target_name
    if not save_allowed_cubes(cubes):
        return False, "Cube konnte nicht umbenannt werden."

    # Namen in bestehenden Turnier-Metadaten synchron halten.
    meta = load_tournament_meta()
    changed = False
    for entry in meta.values():
        if not isinstance(entry, dict):
            continue
        if (entry.get("cube_id") or "").strip() == target_cube_id:
            if entry.get("cube_name") != target_name:
                entry["cube_name"] = target_name
                changed = True
    if changed:
        save_tournament_meta(meta)
    return True, f"Cube wurde in '{target_name}' umbenannt."


def delete_tournament_cube(cube_id):
    target_cube_id = (cube_id or "").strip()
    if not target_cube_id:
        return False, "Ungültige Cube-ID."
    if target_cube_id == DEFAULT_CUBE_ID:
        return False, "Der Standard-Cube kann nicht gelöscht werden."

    cubes = load_allowed_cubes()
    filtered_cubes = [cube for cube in cubes if cube.get("id") != target_cube_id]
    if len(filtered_cubes) == len(cubes):
        return False, "Cube wurde nicht gefunden."
    if not save_allowed_cubes(filtered_cubes):
        return False, "Cube konnte nicht gelöscht werden."
    return True, "Cube wurde gelöscht."


def reassign_cube_in_meta(old_cube_id, new_cube_id=DEFAULT_CUBE_ID):
    """Setzt alle Turniere mit altem Cube auf einen neuen Cube um."""
    source_cube_id = (old_cube_id or "").strip()
    if not source_cube_id:
        return 0
    target_cube_id = normalize_cube_id(new_cube_id)

    meta = load_tournament_meta()
    changed = False
    affected = 0
    for entry in meta.values():
        if not isinstance(entry, dict):
            continue
        raw_cube_id = (entry.get("cube_id") or "").strip()
        normalized_entry_cube = normalize_cube_id(raw_cube_id)
        if raw_cube_id == source_cube_id or normalized_entry_cube == source_cube_id:
            entry["cube_id"] = target_cube_id
            entry["cube_name"] = get_cube_name(target_cube_id)
            affected += 1
            changed = True

    if changed:
        save_tournament_meta(meta)
    return affected


def get_cube_map():
    return {cube["id"]: cube["name"] for cube in load_allowed_cubes()}


def get_cube_name_to_id_map():
    return {cube["name"].casefold(): cube["id"] for cube in load_allowed_cubes()}


def is_valid_cube_id(cube_id):
    if not cube_id or not isinstance(cube_id, str):
        return False
    return cube_id in get_cube_map()


def normalize_cube_id(cube_id):
    if is_valid_cube_id(cube_id):
        return cube_id
    return DEFAULT_CUBE_ID


def get_cube_name(cube_id):
    cube_map = get_cube_map()
    normalized = normalize_cube_id(cube_id)
    return cube_map.get(normalized, "Vintage")

def is_vintage_cube(cube_id):
    return normalize_cube_id(cube_id) == DEFAULT_CUBE_ID


def normalize_cube_value(cube_value):
    """
    Normalisiert Cube-Input auf `cube_id`.
    Unterstützt neue IDs sowie alte Display-Namen aus Legacy-Daten.
    """
    if not cube_value or not isinstance(cube_value, str):
        return DEFAULT_CUBE_ID
    value = cube_value.strip()
    if is_valid_cube_id(value):
        return value
    return get_cube_name_to_id_map().get(value.casefold(), DEFAULT_CUBE_ID)


def load_tournament_meta():
    """Lädt Turnier-Metadaten (Turnier-ID -> Gruppen/Cube-Infos)."""
    _ensure_data_dir()
    path = _meta_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                changed = False
                for tournament_id, entry in data.items():
                    if not isinstance(entry, dict):
                        data[tournament_id] = {
                            "group_id": DEFAULT_GROUP_ID,
                            "group_name": get_group_name(DEFAULT_GROUP_ID),
                            "cube_id": DEFAULT_CUBE_ID,
                            "cube_name": get_cube_name(DEFAULT_CUBE_ID),
                            "created_at": datetime.now().isoformat(),
                        }
                        changed = True
                        continue

                    raw_group_id = entry.get("group_id")
                    normalized_group = normalize_group_id(raw_group_id)
                    if raw_group_id != normalized_group:
                        entry["group_id"] = normalized_group
                        changed = True

                    expected_group_name = get_group_name(entry.get("group_id"))
                    if entry.get("group_name") != expected_group_name:
                        entry["group_name"] = expected_group_name
                        changed = True

                    raw_cube_id = entry.get("cube_id")
                    raw_legacy_cube = entry.get("cube")
                    normalized_cube_id = normalize_cube_value(raw_cube_id or raw_legacy_cube)
                    if entry.get("cube_id") != normalized_cube_id:
                        entry["cube_id"] = normalized_cube_id
                        changed = True

                    expected_cube_name = get_cube_name(normalized_cube_id)
                    if entry.get("cube_name") != expected_cube_name:
                        entry["cube_name"] = expected_cube_name
                        changed = True

                    if "cube" in entry:
                        entry.pop("cube", None)
                        changed = True

                    if not entry.get("created_at"):
                        entry["created_at"] = datetime.now().isoformat()
                        changed = True

                if changed:
                    save_tournament_meta(data)
                return data
            return {}
    except (IOError, OSError, json.JSONDecodeError):
        return {}


def save_tournament_meta(meta):
    _ensure_data_dir()
    path = _meta_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        return True
    except (IOError, OSError):
        return False


def set_tournament_group(tournament_id, group_id, cube_id=DEFAULT_CUBE_ID):
    if not tournament_id:
        return False
    normalized_group = normalize_group_id(group_id)
    normalized_cube_id = normalize_cube_value(cube_id)
    meta = load_tournament_meta()
    existing = meta.get(tournament_id, {}) if isinstance(meta.get(tournament_id), dict) else {}
    meta[tournament_id] = {
        "group_id": normalized_group,
        "group_name": get_group_name(normalized_group),
        "cube_id": normalized_cube_id,
        "cube_name": get_cube_name(normalized_cube_id),
        "created_at": existing.get("created_at") or datetime.now().isoformat(),
    }
    return save_tournament_meta(meta)


def remove_tournament_group(tournament_id):
    if not tournament_id:
        return False
    meta = load_tournament_meta()
    if tournament_id in meta:
        del meta[tournament_id]
        return save_tournament_meta(meta)
    return True


def get_tournament_group_id(tournament_id):
    if not tournament_id:
        return DEFAULT_GROUP_ID
    meta = load_tournament_meta()
    entry = meta.get(tournament_id, {})
    return normalize_group_id(entry.get("group_id"))


def get_tournament_group_name(tournament_id):
    group_id = get_tournament_group_id(tournament_id)
    return get_group_name(group_id)


def get_tournament_cube_id(tournament_id):
    if not tournament_id:
        return DEFAULT_CUBE_ID
    meta = load_tournament_meta()
    entry = meta.get(tournament_id, {})
    return normalize_cube_value(entry.get("cube_id") or entry.get("cube"))


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
