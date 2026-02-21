from datetime import datetime, timezone
import uuid

from sqlalchemy import UniqueConstraint, CheckConstraint

from .db import db


def _uuid_str():
    return str(uuid.uuid4())


def _utcnow():
    return datetime.now(timezone.utc)


class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.String(36), primary_key=True, default=_uuid_str)
    name = db.Column(db.String(80), nullable=False, unique=True)
    normalized_name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class TournamentGroup(db.Model):
    __tablename__ = "tournament_groups"

    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    normalized_name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    is_system = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class Cube(db.Model):
    __tablename__ = "cubes"

    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    normalized_name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    is_system = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)


class Tournament(db.Model):
    __tablename__ = "tournaments"

    id = db.Column(db.String(36), primary_key=True, default=_uuid_str)
    status = db.Column(db.String(16), nullable=False, default="running")
    current_round = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)

    group_id = db.Column(db.String(64), db.ForeignKey("tournament_groups.id"), nullable=False)
    cube_id = db.Column(db.String(64), db.ForeignKey("cubes.id"), nullable=False)

    group = db.relationship("TournamentGroup", lazy="joined")
    cube = db.relationship("Cube", lazy="joined")
    rounds = db.relationship("Round", back_populates="tournament", cascade="all, delete-orphan")
    table_configs = db.relationship("TableConfig", back_populates="tournament", cascade="all, delete-orphan")
    players = db.relationship("TournamentPlayer", back_populates="tournament", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('running', 'ended')", name="ck_tournament_status"),
    )


class TableConfig(db.Model):
    __tablename__ = "table_configs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey("tournaments.id"), nullable=False, index=True)
    table_index = db.Column(db.Integer, nullable=False)
    table_size = db.Column(db.Integer, nullable=False)
    group_key = db.Column(db.String(32), nullable=False)

    tournament = db.relationship("Tournament", back_populates="table_configs")
    players = db.relationship("TournamentPlayer", back_populates="table_config")

    __table_args__ = (
        UniqueConstraint("tournament_id", "table_index", name="uq_table_configs_tournament_table_index"),
        CheckConstraint("table_size IN (6, 8, 10, 12)", name="ck_table_configs_table_size"),
    )


class TournamentPlayer(db.Model):
    __tablename__ = "tournament_players"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey("tournaments.id"), nullable=False, index=True)
    table_config_id = db.Column(db.Integer, db.ForeignKey("table_configs.id"), nullable=False, index=True)
    player_id = db.Column(db.String(36), db.ForeignKey("players.id"), nullable=False, index=True)
    seat_order = db.Column(db.Integer, nullable=True)
    is_dropout = db.Column(db.Boolean, default=False, nullable=False)

    tournament = db.relationship("Tournament", back_populates="players")
    table_config = db.relationship("TableConfig", back_populates="players")
    player = db.relationship("Player")

    __table_args__ = (
        UniqueConstraint("tournament_id", "player_id", name="uq_tournament_players_unique_player_per_tournament"),
    )


class Round(db.Model):
    __tablename__ = "rounds"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey("tournaments.id"), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    tournament = db.relationship("Tournament", back_populates="rounds")
    matches = db.relationship("Match", back_populates="round", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tournament_id", "number", name="uq_rounds_tournament_number"),
    )


class Match(db.Model):
    __tablename__ = "matches"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False, index=True)
    table_number = db.Column(db.Integer, nullable=False)
    table_size = db.Column(db.Integer, nullable=False)
    group_key = db.Column(db.String(32), nullable=False)
    player1_id = db.Column(db.String(36), db.ForeignKey("players.id"), nullable=True)
    player2_id = db.Column(db.String(36), db.ForeignKey("players.id"), nullable=True)
    player1_name_snapshot = db.Column(db.String(80), nullable=True)
    player2_name_snapshot = db.Column(db.String(80), nullable=True)
    is_bye = db.Column(db.Boolean, default=False, nullable=False)
    score1 = db.Column(db.Integer, nullable=True)
    score2 = db.Column(db.Integer, nullable=True)
    score_draws = db.Column(db.Integer, nullable=True)
    dropout1 = db.Column(db.Boolean, default=False, nullable=False)
    dropout2 = db.Column(db.Boolean, default=False, nullable=False)

    round = db.relationship("Round", back_populates="matches")
    player1 = db.relationship("Player", foreign_keys=[player1_id])
    player2 = db.relationship("Player", foreign_keys=[player2_id])

    __table_args__ = (
        UniqueConstraint("round_id", "table_number", name="uq_matches_round_table"),
    )


class PlayerPowerNine(db.Model):
    __tablename__ = "player_power_nine"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tournament_id = db.Column(db.String(36), db.ForeignKey("tournaments.id"), nullable=False, index=True)
    player_id = db.Column(db.String(36), db.ForeignKey("players.id"), nullable=False, index=True)
    card_name = db.Column(db.String(64), nullable=False)
    has_card = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("tournament_id", "player_id", "card_name", name="uq_power_nine_tournament_player_card"),
    )
