"""Flask extension singletons, initialised in the app factory."""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
# In-memory storage is the right size for this app (single PythonAnywhere instance);
# the login rate limit is a guardrail, not a hard security boundary (D3).
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
