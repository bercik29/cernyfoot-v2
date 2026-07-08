"""Database schema.

Designed to structurally eliminate the original app's data defects:
  * score is stored ONCE per match (Match.green_score / orange_score), so the
    redundant-per-row drift (audit §4, NEW-6) is impossible;
  * guests are a distinct participant type (Team.guest / Player.is_guest), so they
    can be excluded from standings (NEW-8);
  * admin rights are a single DB flag (Player.is_admin), one source of truth (D1);
  * seasons & holidays are data, not hard-coded lists (#10, NEW-9).
"""
from __future__ import annotations

import enum
from datetime import date, datetime, time
from typing import Optional

from flask_login import UserMixin
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from .extensions import db, login_manager

_ph = PasswordHasher()


class MatchStatus(enum.Enum):
    scheduled = "scheduled"
    cancelled = "cancelled"
    played = "played"


class Team(enum.Enum):
    green = "green"
    orange = "orange"
    unassigned = "unassigned"
    guest = "guest"


class Player(UserMixin, db.Model):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(120))
    surname: Mapped[Optional[str]] = mapped_column(String(120))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Nullable until the player claims the account and sets a password (D3).
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    signups: Mapped[list["Signup"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )

    @property
    def is_claimed(self) -> bool:
        return self.password_hash is not None

    def set_password(self, raw: str) -> None:
        self.password_hash = _ph.hash(raw)

    def check_password(self, raw: str) -> bool:
        if not self.password_hash:
            return False
        try:
            return _ph.verify(self.password_hash, raw)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def __repr__(self) -> str:
        return f"<Player {self.nickname}>"


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(Player, int(user_id))


class Season(db.Model):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    # 0=Mon .. 6=Sun; original app plays Thursday (3).
    match_weekday: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    match_start: Mapped[time] = mapped_column(Time, default=time(19, 0), nullable=False)
    match_end: Mapped[time] = mapped_column(Time, default=time(20, 0), nullable=False)

    matches: Mapped[list["Match"]] = relationship(
        back_populates="season", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Season {self.label}>"


class Match(db.Model):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus), default=MatchStatus.scheduled, nullable=False
    )
    # Score stored exactly once. Null until a result is entered.
    green_score: Mapped[Optional[int]] = mapped_column(Integer)
    orange_score: Mapped[Optional[int]] = mapped_column(Integer)

    season: Mapped["Season"] = relationship(back_populates="matches")
    signups: Mapped[list["Signup"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )

    @property
    def has_result(self) -> bool:
        return self.green_score is not None and self.orange_score is not None

    @property
    def score_str(self) -> str:
        return f"{self.green_score}:{self.orange_score}" if self.has_result else "-:-"

    def __repr__(self) -> str:
        return f"<Match {self.date.isoformat()} {self.status.value}>"


class Signup(db.Model):
    __tablename__ = "signups"
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_signup_match_player"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    team: Mapped[Team] = mapped_column(Enum(Team), default=Team.unassigned, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    match: Mapped["Match"] = relationship(back_populates="signups")
    player: Mapped["Player"] = relationship(back_populates="signups")

    def __repr__(self) -> str:
        return f"<Signup m={self.match_id} p={self.player_id} {self.team.value}>"


class Payment(db.Model):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("player_id", "season_id", name="uq_payment_player_season"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    # Keep the Slovak domain values used across the UI: 'Vyplatené' / 'Nevyplatené'.
    status: Mapped[str] = mapped_column(String(20), default="Nevyplatené", nullable=False)
    marked_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"))
    marked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    def __repr__(self) -> str:
        return f"<Payment p={self.player_id} s={self.season_id} {self.status}>"


class Holiday(db.Model):
    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="public", nullable=False)  # public|school
    description: Mapped[Optional[str]] = mapped_column(String(200))

    def __repr__(self) -> str:
        return f"<Holiday {self.date_from}..{self.date_to} {self.kind}>"


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity: Mapped[Optional[str]] = mapped_column(String(80))
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} by={self.actor_id}>"
