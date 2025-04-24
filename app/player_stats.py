import os
import json
from typing import Dict, Any, List, Set

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
    "Timetwister"
]

def get_players_data_path() -> str:
    """Gibt den Pfad zur players_data.json Datei zurück"""
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "players_data.json")

def create_default_player_data() -> Dict[str, Any]:
    """Erstellt eine Standarddatenstruktur für neue Spieler"""
    # Initialisiere alle Power Nine als False
    power_nine_dict = {card: False for card in POWER_NINE}
    
    return {
        "power_nine": power_nine_dict,
        "other_stats": {
            "wins_total": 0,
            "favorite_color": "",
            "tournaments_played": 0
        }
    }

def load_all_players_data() -> Dict[str, Dict[str, Any]]:
    """Lädt alle Spielerdaten aus der players_data.json Datei"""
    players_data_file = get_players_data_path()
    if os.path.exists(players_data_file):
        try:
            with open(players_data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Fehler beim Laden der Spielerdaten: {e}")
            return {}
    return {}

def load_player_data(player_name: str) -> Dict[str, Any]:
    """Lädt die Daten für einen bestimmten Spieler"""
    players_data = load_all_players_data()
    return players_data.get(player_name, create_default_player_data())

def save_players_data(players_data: Dict[str, Dict[str, Any]]) -> bool:
    """Speichert alle Spielerdaten in die players_data.json Datei"""
    players_data_file = get_players_data_path()
    try:
        with open(players_data_file, 'w', encoding='utf-8') as f:
            json.dump(players_data, f, indent=2)
        return True
    except (IOError, OSError) as e:
        print(f"Fehler beim Speichern der Spielerdaten: {e}")
        return False

def update_player_power_nine(player_name: str, power_nine_data: Dict[str, bool]) -> bool:
    """Aktualisiert die Power Nine Daten eines Spielers"""
    players_data = load_all_players_data()
    
    # Erstelle einen Eintrag für den Spieler, falls er noch nicht existiert
    if player_name not in players_data:
        players_data[player_name] = create_default_player_data()
    
    # Aktualisiere die Power Nine Daten
    for card in POWER_NINE:
        if card in power_nine_data:
            players_data[player_name]["power_nine"][card] = power_nine_data[card]
    
    # Speichere die aktualisierten Daten
    return save_players_data(players_data)

def get_all_players() -> Set[str]:
    """Sammelt alle Spielernamen aus allen gespeicherten Turnierdaten"""
    from collections import defaultdict
    all_players = set()
    
    # Durchsuche alle tournament_data/results.csv Einträge
    results_file = os.path.join("tournament_data", "results.csv")
    if os.path.exists(results_file):
        try:
            import csv
            with open(results_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if "Player 1" in row and row["Player 1"]:
                        all_players.add(row["Player 1"])
                    if "Player 2" in row and row["Player 2"] and row["Player 2"] != "BYE":
                        all_players.add(row["Player 2"])
        except Exception as e:
            print(f"Fehler beim Lesen der Ergebnisdatei: {e}")
    
    # Durchsuche auch die player_groups.json Dateien aller Turniere
    data_dir = "data"
    if os.path.exists(data_dir):
        for tournament_id in os.listdir(data_dir):
            tournament_dir = os.path.join(data_dir, tournament_id)
            player_groups_file = os.path.join(tournament_dir, "player_groups.json")
            if os.path.exists(player_groups_file):
                try:
                    with open(player_groups_file, 'r', encoding='utf-8') as f:
                        player_groups = json.load(f)
                        for group_players in player_groups.values():
                            all_players.update(group_players)
                except Exception as e:
                    print(f"Fehler beim Lesen der Spielergruppen für Turnier {tournament_id}: {e}")
    
    # Füge auch alle Spieler aus den bestehenden Spielerdaten hinzu
    all_players.update(load_all_players_data().keys())
    
    return all_players

def get_player_statistics(player_name: str) -> Dict[str, Any]:
    """Berechnet die Statistiken für einen Spieler über alle Turniere hinweg"""
    from collections import defaultdict
    stats = defaultdict(int)
    tournaments_played = set()
    opponents = set()
    
    # Durchsuche alle tournament_data/results.csv Einträge
    results_file = os.path.join("tournament_data", "results.csv")
    if os.path.exists(results_file):
        try:
            import csv
            with open(results_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    tournament_id = row.get("Tournament", "")
                    
                    # Überprüfe, ob der Spieler in diesem Match vorkam
                    if row.get("Player 1") == player_name:
                        # Dieser Spieler war Spieler 1
                        tournaments_played.add(tournament_id)
                        if row.get("Player 2") and row.get("Player 2") != "BYE":
                            opponents.add(row.get("Player 2"))
                        
                        # Berechne Spielergebnisse
                        score1 = int(row.get("Score 1", 0))
                        score2 = int(row.get("Score 2", 0))
                        draws = int(row.get("Draws", 0))
                        
                        stats["total_games"] += score1 + score2 + draws
                        stats["games_won"] += score1
                        stats["games_lost"] += score2
                        stats["games_draw"] += draws
                        
                        # Berechne Matchergebnisse
                        if score1 > score2:
                            stats["matches_won"] += 1
                        elif score2 > score1:
                            stats["matches_lost"] += 1
                        else:
                            stats["matches_draw"] += 1
                    
                    elif row.get("Player 2") == player_name:
                        # Dieser Spieler war Spieler 2
                        tournaments_played.add(tournament_id)
                        if row.get("Player 1"):
                            opponents.add(row.get("Player 1"))
                        
                        # Berechne Spielergebnisse
                        score1 = int(row.get("Score 1", 0))
                        score2 = int(row.get("Score 2", 0))
                        draws = int(row.get("Draws", 0))
                        
                        stats["total_games"] += score1 + score2 + draws
                        stats["games_won"] += score2
                        stats["games_lost"] += score1
                        stats["games_draw"] += draws
                        
                        # Berechne Matchergebnisse
                        if score2 > score1:
                            stats["matches_won"] += 1
                        elif score1 > score2:
                            stats["matches_lost"] += 1
                        else:
                            stats["matches_draw"] += 1
        except Exception as e:
            print(f"Fehler beim Lesen der Ergebnisdatei für Statistiken: {e}")
    
    # Berechne abgeleitete Statistiken
    stats["total_matches"] = stats["matches_won"] + stats["matches_lost"] + stats["matches_draw"]
    stats["tournaments_played"] = len(tournaments_played)
    stats["unique_opponents"] = len(opponents)
    
    # Berechne Gewinnraten
    if stats["total_matches"] > 0:
        stats["match_win_percentage"] = round(stats["matches_won"] / stats["total_matches"] * 100, 1)
    else:
        stats["match_win_percentage"] = 0.0
        
    if stats["total_games"] > 0:
        stats["game_win_percentage"] = round(stats["games_won"] / stats["total_games"] * 100, 1)
    else:
        stats["game_win_percentage"] = 0.0
    
    return dict(stats) 