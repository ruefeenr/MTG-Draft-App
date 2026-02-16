import re
import unicodedata


def normalize_name(value):
    compact = " ".join((value or "").strip().split())
    without_diacritics = "".join(
        ch for ch in unicodedata.normalize("NFD", compact) if unicodedata.category(ch) != "Mn"
    )
    return without_diacritics.casefold()


def slugify_group_name(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "gruppe"


def slugify_cube_name(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")
    return slug or "cube"
