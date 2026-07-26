"""Hilfsfunktionen für atomare Datei-Schreibzugriffe.

Die App persistiert Rundendaten als CSV/JSON-Dateien. Ohne atomares Schreiben
kann ein paralleler Request (gunicorn: mehrere Worker/Threads) eine halb
geschriebene Datei lesen und mit einem 500er scheitern. Deshalb wird hier
immer zuerst in eine Tempdatei im selben Verzeichnis geschrieben und danach
per os.replace() umbenannt - das Umbenennen ist auf POSIX-Dateisystemen atomar.
"""

import os
import tempfile


def atomic_write(path, write_fn, encoding="utf-8", newline=None):
    """Schreibt eine Datei atomar.

    Args:
        path: Zielpfad der Datei.
        write_fn: Callable, das das geöffnete (Text-)Datei-Objekt erhält
            und den Inhalt schreibt.
        encoding: Text-Encoding (Default: UTF-8).
        newline: newline-Parameter für open(); für csv-Writer "" verwenden.
    """
    abs_path = os.path.abspath(path)
    directory = os.path.dirname(abs_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=directory or ".",
        prefix=os.path.basename(abs_path) + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as f:
            write_fn(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, abs_path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
