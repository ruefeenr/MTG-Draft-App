from flask import Flask, g, jsonify, request, session
import os
import time
import uuid
import secrets
from collections import defaultdict, deque
import logging
import json
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import ProgrammingError
from .db import db, migrate

# Lade Umgebungsvariablen aus .env Datei
load_dotenv()
_LAST_CREATED_APP = None
_RATE_LIMIT_BUCKETS = defaultdict(deque)


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
    schema_upgrade_hint = (
        "Datenbank-Schema ist veraltet. Bitte Migration ausführen: "
        "flask --app run.py db upgrade"
    )
    app.config["DB_SCHEMA_OUTDATED"] = False
    
    # Stabiler Secret Key (env oder persistiert in instance/)
    app.config['SECRET_KEY'] = _get_app_secret_key()
    default_sqlite_path = os.path.abspath("mtg_draft_app.db")
    if os.environ.get("PYTEST_CURRENT_TEST"):
        # Tests sollen isolierte lokale SQLite-DB pro temp CWD nutzen.
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{default_sqlite_path}"
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", f"sqlite:///{default_sqlite_path}")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config.setdefault("WTF_CSRF_ENABLED", os.environ.get("WTF_CSRF_ENABLED", "true").lower() == "true")
    app.config.setdefault("CSRF_EXEMPT_ENDPOINTS", {"main.login"})
    app.config.setdefault("RATE_LIMIT_ENABLED", os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true")
    app.config.setdefault("RATE_LIMIT_WINDOW_SECONDS", int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60")))
    app.config.setdefault("RATE_LIMIT_MAX_REQUESTS", int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "90")))
    app.config.setdefault(
        "RATE_LIMITED_ENDPOINTS",
        {
            "main.start_tables",
            "main.pair",
            "main.save_results",
            "main.next_round",
            "main.end_tournament",
            "main.delete_tournament",
            "main.delete_player",
        },
    )
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("SESSION_COOKIE_SECURE", os.environ.get("FLASK_ENV") == "production")
    app.config.setdefault("APP_LOGIN_ENABLED", os.environ.get("APP_LOGIN_ENABLED", "false").lower() == "true")
    app.config.setdefault("APP_LOGIN_USERNAME", os.environ.get("APP_LOGIN_USERNAME", "mtg"))
    app.config.setdefault("APP_LOGIN_PASSWORD", os.environ.get("APP_LOGIN_PASSWORD", ""))
    app.config.setdefault("APP_LOGIN_PASSWORD_HASH", os.environ.get("APP_LOGIN_PASSWORD_HASH", ""))
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
        try:
            ensure_default_groups()
            ensure_default_cubes()
        except ProgrammingError:
            # Transitional safety: if DB schema is behind the current models,
            # allow app creation so `flask db upgrade` can be executed.
            db.session.rollback()
            app.config["DB_SCHEMA_OUTDATED"] = True
            app.logger.error(schema_upgrade_hint)

    @app.context_processor
    def inject_csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return {"csrf_token": lambda: token}

    @app.before_request
    def security_before_request():
        if app.config.get("DB_SCHEMA_OUTDATED"):
            payload = {
                "success": False,
                "code": "DB_SCHEMA_OUTDATED",
                "message": schema_upgrade_hint,
            }
            if request.path.startswith("/api/"):
                return jsonify(payload), 503
            return (
                "<h1>Datenbank-Schema veraltet</h1>"
                f"<p>{schema_upgrade_hint}</p>",
                503,
                {"Content-Type": "text/html; charset=utf-8"},
            )

        g.request_started_at = time.time()
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        is_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))

        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return None

        if app.config.get("WTF_CSRF_ENABLED") and not app.testing and not is_pytest:
            csrf_exempt = app.config.get("CSRF_EXEMPT_ENDPOINTS", set())
            if request.endpoint in csrf_exempt:
                return None
            # Same-origin basic guard
            origin = request.headers.get("Origin")
            if origin and request.host_url.rstrip("/") not in origin:
                return jsonify({"success": False, "code": "CSRF_ORIGIN_MISMATCH", "message": "Ungültige Herkunft der Anfrage."}), 403

            token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            expected = session.get("csrf_token")
            if not expected or token != expected:
                if request.blueprint == "main":
                    return jsonify({"success": False, "code": "CSRF_TOKEN_INVALID", "message": "Sicherheitsprüfung fehlgeschlagen (CSRF)."}), 403

        if (
            app.config.get("RATE_LIMIT_ENABLED")
            and not app.testing
            and not is_pytest
            and request.endpoint in app.config.get("RATE_LIMITED_ENDPOINTS", set())
        ):
            window = int(app.config.get("RATE_LIMIT_WINDOW_SECONDS", 60))
            max_requests = int(app.config.get("RATE_LIMIT_MAX_REQUESTS", 90))
            remote = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
            bucket_key = f"{request.endpoint}:{remote}"
            now = time.time()
            bucket = _RATE_LIMIT_BUCKETS[bucket_key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= max_requests:
                return jsonify(
                    {
                        "success": False,
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Zu viele Anfragen. Bitte kurz warten und erneut versuchen.",
                    }
                ), 429
            bucket.append(now)

        return None

    @app.after_request
    def security_after_request(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline';"

        try:
            duration_ms = int((time.time() - getattr(g, "request_started_at", time.time())) * 1000)
            app.logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": getattr(g, "request_id", None),
                        "method": request.method,
                        "path": request.path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "tournament_id": session.get("tournament_id"),
                    }
                )
            )
        except Exception:
            pass
        return response

    @app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"status": "ok"}), 200

    if not app.logger.handlers:
        logging.basicConfig(level=logging.INFO)
    _LAST_CREATED_APP = app
    
    return app
