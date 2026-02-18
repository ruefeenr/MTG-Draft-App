import os
import json
from typing import Dict, Any, Set

from flask import has_app_context
from sqlalchemy import or_

from .db import db
from .models import Match, Player, PlayerPowerNine, Round, Tournament
from .services.normalize import normalize_name
from .tournament_groups import load_tournament_meta, normalize_cube_id, normalize_group_id

# Definiere die Struktur der Power Nine Karten
POWER_NINE = [
    "Black Lotus",
    "Ancestral Recall",
    "Time Walk",
    "Mox Sapphire",
    "Mox Jet",
    "Mox Ruby",
    "Mox Pearl",
    "Mox Emerald",
    "Timetwister",
]


def _is_deleted_player_name(name: str) -> bool:
    return isinstance(name, str) and name.startswith("DELETED_PLAYER")


def _parse_legacy_score(value, default=0):
    if value is None:
        return default
    text = str(value).strip()
    if text == "":
        return default
    try:
        return int(text)
    except (TypeError, ValueError):
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return None


def get_players_data_path() -> str:
    # Rückwärtskompatibel behalten (legacy JSON), wird nicht mehr primär genutzt.
    return os.path.join("data", "players", "players_data.json")


def create_default_player_data() -> Dict[str, Any]:
    power_nine_dict = {card: False for card in POWER_NINE}
    return {
        "power_nine": power_nine_dict,
        "other_stats": {
            "wins_total": 0,
            "favorite_color": "",
            "tournaments_played": 0,
        },
    }


def load_all_players_data() -> Dict[str, Dict[str, Any]]:
    # DB-first: baue kompatible Struktur aus Player-Tabelle.
    if not has_app_context():
        file_path = get_players_data_path()
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    players_data = {}
    for row in Player.query.order_by(Player.name.asc()).all():
        players_data[row.name] = create_default_player_data()
    return players_data


def load_player_data(player_name: str) -> Dict[str, Any]:
    if not has_app_context():
        return load_all_players_data().get(player_name, create_default_player_data())
    player = Player.query.filter_by(normalized_name=normalize_name(player_name)).first()
    if not player:
        return create_default_player_data()
    return create_default_player_data()


def save_players_data(players_data: Dict[str, Dict[str, Any]]) -> bool:
    # DB-basiert nicht mehr nötig; kompatibler Erfolg.
    return isinstance(players_data, dict)


def update_player_power_nine(player_name: str, power_nine_data: Dict[str, bool]) -> bool:
    """
    Kompatibilitätsfunktion. Die turnierbezogene Persistenz passiert in routes.py
    über update_tournament_power_nine().
    """
    return isinstance(player_name, str) and isinstance(power_nine_data, dict)


def delete_player(player_name: str) -> bool:
    if not has_app_context():
        return True
    normalized = normalize_name(player_name)
    row = Player.query.filter_by(normalized_name=normalized).first()
    if row is None:
        return True
    # Spieler in Matches nicht physisch entfernen, stattdessen umbenennen.
    row.name = f"DELETED_PLAYER_{row.id[:6]}"
    row.normalized_name = normalize_name(row.name)
    db.session.commit()
    return True


def get_all_players() -> Set[str]:
    players = set()
    if has_app_context():
        players = {row.name for row in Player.query.all() if row.name and not _is_deleted_player_name(row.name)}
    legacy_players_file = get_players_data_path()
    if os.path.exists(legacy_players_file):
        try:
            with open(legacy_players_file, "r", encoding="utf-8") as f:
                players_data = json.load(f)
                players.update(name for name in players_data.keys() if name and not _is_deleted_player_name(name))
        except Exception:
            pass
    # Fallback: falls legacy-Dateien existieren, Namen ergänzen.
    results_file = os.path.join("tournament_data", "results.csv")
    if os.path.exists(results_file):
        try:
            import csv

            with open(results_file, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    p1 = row.get("Player 1")
                    p2 = row.get("Player 2")
                    if p1 and not _is_deleted_player_name(p1):
                        players.add(p1)
                    if p2 and p2 != "BYE" and not _is_deleted_player_name(p2):
                        players.add(p2)
        except Exception:
            pass
    return players


def _empty_stats():
    return {
        "matches_won": 0,
        "matches_lost": 0,
        "matches_draw": 0,
        "games_won": 0,
        "games_lost": 0,
        "games_draw": 0,
        "total_games": 0,
        "total_matches": 0,
        "tournaments_played": 0,
        "unique_opponents": 0,
        "power_nine_total": 0,
        "power_nine_counts": {card: 0 for card in POWER_NINE},
        "match_win_percentage": 0.0,
        "game_win_percentage": 0.0,
    }


def _legacy_file_based_stats(player_name: str, group_id: str = None, cube_filter: str = "all") -> Dict[str, Any]:
    import csv

    stats = _empty_stats()
    normalized_group_id = normalize_group_id(group_id) if group_id else None
    selected_cube_filter = (cube_filter or "all").strip().lower()
    normalized_cube_filter = None if selected_cube_filter == "all" else normalize_cube_id(selected_cube_filter)
    include_power_nine_stats = normalized_cube_filter == "vintage"
    tournament_meta = load_tournament_meta()

    tournaments_played = set()
    opponents = set()
    results_file = os.path.join("tournament_data", "results.csv")
    if os.path.exists(results_file):
        with open(results_file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tournament_id = row.get("Tournament", "")
                tournament_group_id = normalize_group_id(tournament_meta.get(tournament_id, {}).get("group_id"))
                tournament_cube_id = normalize_cube_id(tournament_meta.get(tournament_id, {}).get("cube_id"))
                if normalized_group_id and tournament_group_id != normalized_group_id:
                    continue
                if normalized_cube_filter and tournament_cube_id != normalized_cube_filter:
                    continue

                if row.get("Player 1") == player_name:
                    tournaments_played.add(tournament_id)
                    if row.get("Player 2") and row.get("Player 2") != "BYE" and not _is_deleted_player_name(row.get("Player 2")):
                        opponents.add(row.get("Player 2"))
                    score1 = _parse_legacy_score(row.get("Score 1", 0))
                    score2 = _parse_legacy_score(row.get("Score 2", 0))
                    draws = _parse_legacy_score(row.get("Draws", row.get("score_draws", 0)))
                    if score1 is None or score2 is None or draws is None:
                        # Defekte Legacy-Zeilen nicht für Statistik verwenden.
                        continue
                    stats["total_games"] += score1 + score2 + draws
                    stats["games_won"] += score1
                    stats["games_lost"] += score2
                    stats["games_draw"] += draws
                    if score1 > score2:
                        stats["matches_won"] += 1
                    elif score2 > score1:
                        stats["matches_lost"] += 1
                    else:
                        stats["matches_draw"] += 1
                elif row.get("Player 2") == player_name:
                    tournaments_played.add(tournament_id)
                    if row.get("Player 1") and not _is_deleted_player_name(row.get("Player 1")):
                        opponents.add(row.get("Player 1"))
                    score1 = _parse_legacy_score(row.get("Score 1", 0))
                    score2 = _parse_legacy_score(row.get("Score 2", 0))
                    draws = _parse_legacy_score(row.get("Draws", row.get("score_draws", 0)))
                    if score1 is None or score2 is None or draws is None:
                        # Defekte Legacy-Zeilen nicht für Statistik verwenden.
                        continue
                    stats["total_games"] += score1 + score2 + draws
                    stats["games_won"] += score2
                    stats["games_lost"] += score1
                    stats["games_draw"] += draws
                    if score2 > score1:
                        stats["matches_won"] += 1
                    elif score1 > score2:
                        stats["matches_lost"] += 1
                    else:
                        stats["matches_draw"] += 1

    if include_power_nine_stats:
        for tournament_id in tournaments_played:
            if normalize_cube_id(tournament_meta.get(tournament_id, {}).get("cube_id")) != "vintage":
                continue
            power_nine_file = os.path.join("data", tournament_id, "tournament_power_nine.json")
            if not os.path.exists(power_nine_file):
                continue
            try:
                with open(power_nine_file, "r", encoding="utf-8") as f:
                    payload = json.load(f).get(player_name, {})
                for card, has_card in payload.items():
                    if has_card and card in stats["power_nine_counts"]:
                        stats["power_nine_counts"][card] += 1
                        stats["power_nine_total"] += 1
            except Exception:
                continue

    stats["total_matches"] = stats["matches_won"] + stats["matches_lost"] + stats["matches_draw"]
    stats["tournaments_played"] = len(tournaments_played)
    stats["unique_opponents"] = len(opponents)
    if stats["total_matches"] > 0:
        stats["match_win_percentage"] = round(stats["matches_won"] / stats["total_matches"] * 100, 1)
    if stats["total_games"] > 0:
        stats["game_win_percentage"] = round(stats["games_won"] / stats["total_games"] * 100, 1)
    return stats


def get_player_statistics(player_name: str, group_id: str = None, cube_filter: str = "all") -> Dict[str, Any]:
    """Berechnet Spielerstatistiken DB-basiert mit optionalem Gruppen- und Cube-Filter."""
    stats = _empty_stats()
    if not has_app_context():
        return _legacy_file_based_stats(player_name, group_id=group_id, cube_filter=cube_filter)

    normalized_player_name = normalize_name(player_name)
    player = Player.query.filter_by(normalized_name=normalized_player_name).first()
    if player is None:
        # Falls DB leer ist, auf Legacy-Dateien zurückfallen.
        return _legacy_file_based_stats(player_name, group_id=group_id, cube_filter=cube_filter)

    normalized_group_id = normalize_group_id(group_id) if group_id else None
    selected_cube_filter = (cube_filter or "all").strip().lower()
    normalized_cube_filter = None if selected_cube_filter == "all" else normalize_cube_id(selected_cube_filter)
    include_power_nine_stats = normalized_cube_filter == "vintage"

    query = (
        db.session.query(Match, Round, Tournament)
        .join(Round, Match.round_id == Round.id)
        .join(Tournament, Round.tournament_id == Tournament.id)
        .filter(or_(Match.player1_id == player.id, Match.player2_id == player.id))
    )
    if normalized_group_id:
        query = query.filter(Tournament.group_id == normalized_group_id)
    if normalized_cube_filter:
        query = query.filter(Tournament.cube_id == normalized_cube_filter)

    tournaments_played = set()
    opponents = set()
    for match, _round, tournament in query.all():
        if match.score1 is None or match.score2 is None:
            # Unfertige Matches ignorieren
            continue
        tournaments_played.add(tournament.id)

        if match.player1_id == player.id:
            my_score = match.score1 or 0
            opp_score = match.score2 or 0
            draws = match.score_draws or 0
            if match.player2 and match.player2.name != "BYE" and not _is_deleted_player_name(match.player2.name):
                opponents.add(match.player2.name)
        else:
            my_score = match.score2 or 0
            opp_score = match.score1 or 0
            draws = match.score_draws or 0
            if match.player1 and not _is_deleted_player_name(match.player1.name):
                opponents.add(match.player1.name)

        stats["games_won"] += my_score
        stats["games_lost"] += opp_score
        stats["games_draw"] += draws
        stats["total_games"] += my_score + opp_score + draws

        if my_score > opp_score:
            stats["matches_won"] += 1
        elif opp_score > my_score:
            stats["matches_lost"] += 1
        else:
            stats["matches_draw"] += 1

    stats["total_matches"] = stats["matches_won"] + stats["matches_lost"] + stats["matches_draw"]
    stats["tournaments_played"] = len(tournaments_played)
    stats["unique_opponents"] = len(opponents)

    if include_power_nine_stats and tournaments_played:
        rows = (
            PlayerPowerNine.query.join(Tournament, PlayerPowerNine.tournament_id == Tournament.id)
            .filter(
                PlayerPowerNine.player_id == player.id,
                PlayerPowerNine.has_card.is_(True),
                PlayerPowerNine.tournament_id.in_(tournaments_played),
                Tournament.cube_id == "vintage",
            )
            .all()
        )
        for row in rows:
            if row.card_name in stats["power_nine_counts"]:
                stats["power_nine_counts"][row.card_name] += 1
                stats["power_nine_total"] += 1

    if stats["total_matches"] > 0:
        stats["match_win_percentage"] = round(stats["matches_won"] / stats["total_matches"] * 100, 1)
    if stats["total_games"] > 0:
        stats["game_win_percentage"] = round(stats["games_won"] / stats["total_games"] * 100, 1)

    return stats
