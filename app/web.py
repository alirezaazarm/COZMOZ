"""Flask application factory shared by development, API, and production servers."""

from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .bootstrap import ensure_initial_system_admin
from .models.client import Client
from .models.database import db
from .routes.api import api_bp
from .routes.update import update_bp
from .routes.webhook import instagram_webhook_bp, telegram_webhook_bp, bale_webhook_bp
from .utils.helpers import load_main_app_globals_from_db


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=Config.SESSION_SECRET,
        MAX_CONTENT_LENGTH=Config.MAX_UPLOAD_BYTES,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=Config.COOKIE_SECURE,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    ensure_initial_system_admin()
    Client.migrate_all_clients()
    load_main_app_globals_from_db()
    app.register_blueprint(api_bp)
    app.register_blueprint(instagram_webhook_bp)
    app.register_blueprint(telegram_webhook_bp)
    app.register_blueprint(bale_webhook_bp)
    app.register_blueprint(update_bp)

    @app.get("/healthz")
    def healthz():
        if db is None:
            return jsonify({"status": "unhealthy"}), 503
        try:
            db.client.admin.command("ping")
        except Exception:
            return jsonify({"status": "unhealthy"}), 503
        return jsonify({"status": "ok"})

    return app


app = create_app()
