import json
import os
from datetime import datetime

DEFAULT_GROUP_ID = "default"

DEFAULT_GROUPS = [
    {"id": DEFAULT_GROUP_ID, "name": "Unkategorisiert"},
    {"id": "liga", "name": "Liga"},
    {"id": "casual", "name": "Casual"},
]


def _data_dir():
    return "data"


def _groups_file():
    return os.path.join(_data_dir(), "tournament_groups.json")


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

            # Garantiert, dass die Default-Gruppe immer vorhanden ist.
            if DEFAULT_GROUP_ID not in seen_ids:
                valid.insert(0, {"id": DEFAULT_GROUP_ID, "name": "Unkategorisiert"})
            return valid
    except (IOError, OSError, json.JSONDecodeError):
        return DEFAULT_GROUPS.copy()


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


def load_tournament_meta():
    """Lädt Turnier-Metadaten (Turnier-ID -> Gruppeninfos)."""
    _ensure_data_dir()
    path = _meta_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
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


def set_tournament_group(tournament_id, group_id):
    if not tournament_id:
        return False
    normalized_group = normalize_group_id(group_id)
    meta = load_tournament_meta()
    meta[tournament_id] = {
        "group_id": normalized_group,
        "group_name": get_group_name(normalized_group),
        "created_at": datetime.now().isoformat(),
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
