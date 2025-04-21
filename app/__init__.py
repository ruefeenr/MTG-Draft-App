from flask import Flask
import os
from dotenv import load_dotenv

# Lade Umgebungsvariablen aus .env Datei
load_dotenv()

app = Flask(__name__)

# Secret Key aus Umgebungsvariablen oder Fallback
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or os.urandom(24)

from app import routes

def create_app():
    app = Flask(__name__)
    from .routes import main
    app.register_blueprint(main)
    return app
