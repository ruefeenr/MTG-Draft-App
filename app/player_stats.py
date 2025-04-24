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
    try:
        # Verwende einen Ordner im Hauptverzeichnis der Anwendung
        data_dir = os.path.abspath("data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            print(f"Datenverzeichnis wurde erstellt: {data_dir}")
        
        # Verwende den Unterordner 'players' für Spielerdaten
        players_dir = os.path.join(data_dir, "players")
        if not os.path.exists(players_dir):
            os.makedirs(players_dir, exist_ok=True)
            print(f"Spielerverzeichnis wurde erstellt: {players_dir}")
        
        # Rückgabe des vollständigen Pfads zur Datei
        file_path = os.path.join(players_dir, "players_data.json")
        print(f"Verwende Spielerdatendatei: {file_path}")
        return file_path
    except Exception as e:
        print(f"Fehler beim Erstellen des Dateipfads: {str(e)}")
        # Fallback auf relativen Pfad im aktuellen Verzeichnis
        return os.path.join("data", "players_data.json")

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

def delete_player(player_name: str) -> bool:
    """Löscht einen Spieler aus allen gespeicherten Daten (players_data.json und Turnierdaten)"""
    try:
        success = True
        
        # 1. Aus players_data.json löschen
        players_data_file = get_players_data_path()
        data_dir = os.path.dirname(players_data_file)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            print(f"Datenverzeichnis wurde erstellt: {data_dir}")
        
        players_data = load_all_players_data()
        
        # Prüfe, ob der Spieler in den Spielerdaten existiert
        if player_name in players_data:
            # Entferne den Spieler aus den Daten
            print(f"Entferne Spieler '{player_name}' aus Spielerdaten")
            del players_data[player_name]
            
            # Speichere die aktualisierten Daten
            if not save_players_data(players_data):
                print(f"Fehler beim Speichern der Daten nach dem Löschen von '{player_name}'")
                success = False
        else:
            print(f"Spieler '{player_name}' wurde nicht in der players_data.json gefunden")

        # 2. Aus tournament_data/results.csv entfernen (ersetze Spielernamen mit "DELETED_PLAYER")
        results_file = os.path.join("tournament_data", "results.csv")
        if os.path.exists(results_file):
            try:
                import csv
                # Lese die aktuelle Datei
                rows = []
                with open(results_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    header = reader.fieldnames
                    
                    for row in reader:
                        # Ersetze den Spielernamen, wenn er vorkommt
                        if row.get("Player 1") == player_name:
                            row["Player 1"] = "DELETED_PLAYER"
                        if row.get("Player 2") == player_name:
                            row["Player 2"] = "DELETED_PLAYER"
                        rows.append(row)
                
                # Schreibe die aktualisierte Datei
                with open(results_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=header)
                    writer.writeheader()
                    writer.writerows(rows)
                
                print(f"Spieler '{player_name}' wurde aus den Turnierergebnissen entfernt")
            except Exception as e:
                print(f"Fehler beim Aktualisieren der Ergebnisdatei: {e}")
                success = False
        
        # 3. Aus player_groups.json Dateien in allen Turnierordnern entfernen
        data_dir = "data"
        if os.path.exists(data_dir):
            for tournament_id in os.listdir(data_dir):
                tournament_dir = os.path.join(data_dir, tournament_id)
                player_groups_file = os.path.join(tournament_dir, "player_groups.json")
                
                if os.path.exists(player_groups_file) and os.path.isfile(player_groups_file):
                    try:
                        # Lese die aktuelle player_groups.json
                        with open(player_groups_file, 'r', encoding='utf-8') as f:
                            player_groups = json.load(f)
                        
                        # Prüfe jede Gruppe und entferne den Spieler
                        modified = False
                        for group_name, group_players in player_groups.items():
                            if player_name in group_players:
                                player_groups[group_name] = [p for p in group_players if p != player_name]
                                modified = True
                                print(f"Spieler '{player_name}' aus Gruppe '{group_name}' in Turnier '{tournament_id}' entfernt")
                        
                        # Speichere die aktualisierte Datei, wenn Änderungen vorgenommen wurden
                        if modified:
                            with open(player_groups_file, 'w', encoding='utf-8') as f:
                                json.dump(player_groups, f, indent=2)
                    except Exception as e:
                        print(f"Fehler beim Aktualisieren der Spielergruppen für Turnier {tournament_id}: {e}")
                        success = False
        
        # 4. Aus den Rundendateien (rounds/round_X.csv) in allen Turnierordnern entfernen
        if os.path.exists(data_dir):
            for tournament_id in os.listdir(data_dir):
                tournament_dir = os.path.join(data_dir, tournament_id)
                rounds_dir = os.path.join(tournament_dir, "rounds")
                
                if os.path.exists(rounds_dir) and os.path.isdir(rounds_dir):
                    for round_file in os.listdir(rounds_dir):
                        if round_file.startswith("round_") and round_file.endswith(".csv"):
                            round_path = os.path.join(rounds_dir, round_file)
                            try:
                                import csv
                                # Lese die aktuelle Datei
                                rows = []
                                with open(round_path, 'r', newline='', encoding='utf-8') as f:
                                    reader = csv.DictReader(f)
                                    header = reader.fieldnames
                                    
                                    for row in reader:
                                        # Ersetze den Spielernamen, wenn er vorkommt
                                        if row.get("player1") == player_name:
                                            row["player1"] = "DELETED_PLAYER"
                                        if row.get("player2") == player_name:
                                            row["player2"] = "DELETED_PLAYER"
                                        rows.append(row)
                                
                                # Schreibe die aktualisierte Datei
                                with open(round_path, 'w', newline='', encoding='utf-8') as f:
                                    writer = csv.DictWriter(f, fieldnames=header)
                                    writer.writeheader()
                                    writer.writerows(rows)
                                
                                print(f"Spieler '{player_name}' wurde aus Runde {round_file} im Turnier '{tournament_id}' entfernt")
                            except Exception as e:
                                print(f"Fehler beim Aktualisieren der Rundendatei {round_file}: {e}")
                                success = False
        
        if success:
            print(f"Spieler '{player_name}' wurde erfolgreich aus allen Daten entfernt")
        else:
            print(f"Es gab Probleme beim vollständigen Entfernen des Spielers '{player_name}'")
            
        return success
    except Exception as e:
        print(f"Unerwarteter Fehler beim Löschen des Spielers '{player_name}': {str(e)}")
        return False

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
                    if "Player 1" in row and row["Player 1"] and row["Player 1"] != "DELETED_PLAYER":
                        all_players.add(row["Player 1"])
                    if "Player 2" in row and row["Player 2"] and row["Player 2"] != "DELETED_PLAYER" and row["Player 2"] != "BYE":
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
                            all_players.update([p for p in group_players if p != "DELETED_PLAYER"])
                except Exception as e:
                    print(f"Fehler beim Lesen der Spielergruppen für Turnier {tournament_id}: {e}")
    
    # Füge auch alle Spieler aus den bestehenden Spielerdaten hinzu
    players_data = load_all_players_data()
    all_players.update([p for p in players_data.keys() if p != "DELETED_PLAYER"])
    
    return all_players

def get_player_statistics(player_name: str) -> Dict[str, Any]:
    """Berechnet die Statistiken für einen Spieler über alle Turniere hinweg"""
    from collections import defaultdict
    stats = defaultdict(int)
    tournaments_played = set()
    opponents = set()
    power_nine_count = 0  # Gesamtzähler für alle Power Nine Karten über alle Turniere
    
    # Dictionary für die individuelle Zählung jeder Power Nine Karte
    power_nine_individual_counts = {card: 0 for card in POWER_NINE}
    
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
                        if row.get("Player 2") and row.get("Player 2") != "BYE" and row.get("Player 2") != "DELETED_PLAYER":
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
                        if row.get("Player 1") and row.get("Player 1") != "DELETED_PLAYER":
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
    
    # Durchsuche alle tournament_power_nine.json Dateien für diesen Spieler
    data_dir = "data"
    if os.path.exists(data_dir):
        for tournament_id in os.listdir(data_dir):
            # Überprüfe, ob der Spieler an diesem Turnier teilgenommen hat
            if tournament_id in tournaments_played:
                tournament_dir = os.path.join(data_dir, tournament_id)
                power_nine_file = os.path.join(tournament_dir, "tournament_power_nine.json")
                
                if os.path.exists(power_nine_file):
                    try:
                        with open(power_nine_file, 'r', encoding='utf-8') as f:
                            tournament_power_nine = json.load(f)
                            # Wenn der Spieler Power Nine Karten in diesem Turnier hatte
                            if player_name in tournament_power_nine:
                                # Für jede Karte individuell zählen
                                player_p9 = tournament_power_nine[player_name]
                                for card, has_card in player_p9.items():
                                    if has_card:
                                        # Erhöhe die Gesamtzahl
                                        power_nine_count += 1
                                        # Erhöhe die individuelle Zählung für diese Karte
                                        if card in power_nine_individual_counts:
                                            power_nine_individual_counts[card] += 1
                    except Exception as e:
                        print(f"Fehler beim Lesen der Power Nine Daten für Turnier {tournament_id}: {e}")
    
    # Berechne abgeleitete Statistiken
    stats["total_matches"] = stats["matches_won"] + stats["matches_lost"] + stats["matches_draw"]
    stats["tournaments_played"] = len(tournaments_played)
    stats["unique_opponents"] = len(opponents)
    stats["power_nine_total"] = power_nine_count  # Hinzufügen der Power Nine Gesamtzahl
    
    # Füge die individuellen Zählungen für jede Power Nine Karte hinzu
    stats["power_nine_counts"] = power_nine_individual_counts
    
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