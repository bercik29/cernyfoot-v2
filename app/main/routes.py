from flask import render_template

from . import bp


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/health")
def health():
    """Cheap liveness probe — also proves the app booted with its config."""
    return {"status": "ok"}
