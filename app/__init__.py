"""Application factory."""
from __future__ import annotations

import os

from flask import Flask, render_template
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .config import CONFIG_MAP
from .extensions import csrf, db, login_manager, migrate


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL journalling and foreign-key enforcement for SQLite.

    WAL removes the file-race problems that plagued the CSV design; FK enforcement
    keeps signups/payments referentially sound. No-ops on non-SQLite / in-memory.
    """
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass


def create_app(config_name: str | None = None) -> Flask:
    config_name = config_name or os.environ.get("FLASK_CONFIG", "dev")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(CONFIG_MAP[config_name])

    os.makedirs(app.instance_path, exist_ok=True)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Prihláste sa, prosím."
    csrf.init_app(app)

    # Register models with the mapper (side-effect import).
    from . import models  # noqa: F401

    # Blueprints
    from .main import bp as main_bp
    app.register_blueprint(main_bp)

    # Minimal error pages (styled properly in the frontend phase).
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    return app
