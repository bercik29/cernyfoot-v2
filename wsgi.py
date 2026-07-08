"""WSGI entry point.

Local dev:      flask run   (reads .flaskenv -> FLASK_APP=wsgi.py, FLASK_CONFIG=dev)
PythonAnywhere: point the web app's WSGI file at `from wsgi import app`
                (see DEPLOY.md — a .env next to this file supplies SECRET_KEY etc.)
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402 — .env must be loaded before config is read

app = create_app(os.environ.get("FLASK_CONFIG", "prod"))

if __name__ == "__main__":
    app.run()
