from flask import Flask
import os
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool
from .db import db, migrate

# Lade Umgebungsvariablen aus .env Datei
load_dotenv()
_LAST_CREATED_APP = None


def get_last_created_app():
    return _LAST_CREATED_APP

def _generate_secret_key():
    """Generiert einen sicheren Secret Key."""
    return os.urandom(32).hex()

def _get_app_secret_key():
    """
    Liefert einen stabilen Secret Key:
    1) FLASK_SECRET_KEY aus Umgebung/.env
    2) persistierter Key in instance/secret_key
    """
    env_key = os.environ.get("FLASK_SECRET_KEY")
    if env_key:
        return env_key

    instance_dir = "instance"
    secret_key_path = os.path.join(instance_dir, "secret_key")
    os.makedirs(instance_dir, exist_ok=True)

    if os.path.exists(secret_key_path):
        try:
            with open(secret_key_path, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    return key
        except OSError:
            pass

    key = _generate_secret_key()
    try:
        with open(secret_key_path, "w", encoding="utf-8") as f:
            f.write(key)
    except OSError:
        # Fallback: weiterhin funktional, aber nicht persistent
        return _generate_secret_key()
    return key

def create_app():
    global _LAST_CREATED_APP
    app = Flask(__name__)
    
    # Stabiler Secret Key (env oder persistiert in instance/)
    app.config['SECRET_KEY'] = _get_app_secret_key()
    default_sqlite_path = os.path.abspath("mtg_draft_app.db")
    if os.environ.get("PYTEST_CURRENT_TEST"):
        # Tests sollen isolierte lokale SQLite-DB pro temp CWD nutzen.
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{default_sqlite_path}"
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", f"sqlite:///{default_sqlite_path}")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"poolclass": NullPool}

    db.init_app(app)
    migrate.init_app(app, db)
    # Modelle explizit laden, damit Flask-Migrate Metadaten kennt.
    from . import models  # noqa: F401
    from .services.cubes import ensure_default_cubes
    from .services.groups import ensure_default_groups
    
    # Registriere Blueprints
    from .routes import main
    app.register_blueprint(main)

    # Für Greenfield-Setup ohne Datenmigration:
    # Tabellen bei Bedarf automatisch anlegen und Defaults sicherstellen.
    with app.app_context():
        db.create_all()
        ensure_default_groups()
        ensure_default_cubes()
    _LAST_CREATED_APP = app
    
    return app
