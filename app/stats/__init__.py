from flask import Blueprint

bp = Blueprint("stats", __name__)

from . import routes  # noqa: E402,F401
