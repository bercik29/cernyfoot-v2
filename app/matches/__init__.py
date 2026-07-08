from flask import Blueprint

bp = Blueprint("matches", __name__)

from . import routes  # noqa: E402,F401
