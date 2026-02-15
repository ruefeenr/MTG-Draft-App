from flask import Flask
import os
from dotenv import load_dotenv

# Lade Umgebungsvariablen aus .env Datei
load_dotenv()

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
    app = Flask(__name__)
    
    # Stabiler Secret Key (env oder persistiert in instance/)
    app.config['SECRET_KEY'] = _get_app_secret_key()
    
    # Registriere Blueprints
    from .routes import main
    app.register_blueprint(main)
    
    return app

# Erstelle die Anwendung
app = create_app()
