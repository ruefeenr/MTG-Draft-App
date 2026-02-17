import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def _sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Nur sqlite:/// URLs werden im Drill unterstützt.")
    return Path(database_url.removeprefix("sqlite:///")).resolve()


def _assert_tournaments_table(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tournaments'"
        ).fetchone()
    if row is None:
        raise RuntimeError(f"'tournaments' Tabelle fehlt in {db_path}")


def _copy_via_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    source_db = (project_root / "ci_backup_source.db").resolve()
    source_url = f"sqlite:///{source_db.as_posix()}"
    backup_db = project_root / "ci_backup_dump.db"
    restore_db = project_root / "ci_backup_restore.db"

    for path in (source_db, backup_db, restore_db):
        if path.exists():
            path.unlink()

    env = os.environ.copy()
    env["FLASK_SECRET_KEY"] = env.get("FLASK_SECRET_KEY", "ci-backup-drill-secret")
    env["DATABASE_URL"] = source_url
    env.pop("PYTEST_CURRENT_TEST", None)

    subprocess.run(
        [sys.executable, "-m", "flask", "--app", "run.py", "db", "upgrade"],
        cwd=project_root,
        env=env,
        check=True,
    )

    # Migration-Chain anwenden und danach das aktuelle ORM-Schema materialisieren.
    os.environ.update(
        {
            "FLASK_SECRET_KEY": env["FLASK_SECRET_KEY"],
            "DATABASE_URL": source_url,
        }
    )
    os.environ.pop("PYTEST_CURRENT_TEST", None)
    from app import create_app
    from app.db import db

    app = create_app()
    with app.app_context():
        db.create_all()

    _assert_tournaments_table(source_db)
    _copy_via_backup(source_db, backup_db)
    _copy_via_backup(backup_db, restore_db)
    _assert_tournaments_table(restore_db)

    print("Backup/Restore Drill erfolgreich:", restore_db.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
