"""Configuration objects, all driven by environment variables.

No hard-coded absolute paths, secrets, or season definitions live here — that was
one of the core defects of the original app (audit §6 #16, NEW-2). Match timing is a
single configurable pair of values instead of five scattered cutoffs.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'cernyfoot.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Localisation
    TIMEZONE = os.environ.get("TIMEZONE", "Europe/Bratislava")
    LANGUAGE = os.environ.get("LANGUAGE", "sk")

    # Single source of truth for match timing (replaces 5 hard-coded cutoffs).
    SIGNUP_DEADLINE = os.environ.get("SIGNUP_DEADLINE", "18:45")  # HH:MM local
    MATCH_LOCK = os.environ.get("MATCH_LOCK", "19:05")            # HH:MM local

    # Auth guardrail (owner decision D3: no strength rules, rate-limit instead).
    LOGIN_RATELIMIT = os.environ.get("LOGIN_RATELIMIT", "10 per minute")


class DevConfig(Config):
    DEBUG = True


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    LOGIN_RATELIMIT = "1000 per minute"


class ProdConfig(Config):
    DEBUG = False


CONFIG_MAP = {
    "dev": DevConfig,
    "test": TestConfig,
    "prod": ProdConfig,
}
