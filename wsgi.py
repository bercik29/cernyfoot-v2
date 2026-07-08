"""WSGI entry point.

Local dev:      flask run   (reads .flaskenv -> FLASK_APP=wsgi.py, FLASK_CONFIG=dev)
PythonAnywhere: point the web app's WSGI file at `from wsgi import app`.
"""
import os

from app import create_app

app = create_app(os.environ.get("FLASK_CONFIG", "prod"))

if __name__ == "__main__":
    app.run()
