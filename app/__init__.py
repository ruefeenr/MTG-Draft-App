from flask import Flask

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # In Produktion sollten Sie einen sicheren Schlüssel verwenden

from app import routes

def create_app():
    app = Flask(__name__)
    from .routes import main
    app.register_blueprint(main)
    return app
