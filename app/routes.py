from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
import uuid
import random
import itertools
import ast
import os
import csv
from datetime import datetime
from collections import defaultdict
import json
import base64

# Debug-Modus - auf False setzen für Produktionsumgebung
DEBUG = True

main = Blueprint('main', __name__)

def debug_emoji(text, prefix=""):
    """Hilft bei der Identifizierung von Problemen mit Unicode-Symbolen wie dem 🦵"""
    if not DEBUG:
        return text
    
    if text and isinstance(text, str):
        has_leg = "🦵" in text
        byte_repr = str(text.encode('utf-8'))
        print(f"{prefix} Text: '{text}', Enthält 🦵: {has_leg}, Bytes: {byte_repr}")
    else:
        print(f"{prefix} Kein Text oder kein String: {type(text)}")
    return text

def is_player_marked(player_name):
    """Prüft, ob ein Spieler als Dropout markiert ist (anhand der Session)"""
    if not player_name or not isinstance(player_name, str):
        return False
    marked_players = session.get("leg_players_set", [])
    return player_name in marked_players

def mark_player(player_name):
    """Fügt das 🦵-Symbol zu einem Spielernamen hinzu, wenn er in der markierten Liste ist."""
    if not player_name or not isinstance(player_name, str):
        return player_name
    
    marked_players = session.get("leg_players_set", [])
    if player_name in marked_players:
        if "🦵" not in player_name:  # Stelle sicher, dass das Symbol nur einmal hinzugefügt wird
            return f"{player_name} 🦵"
    return player_name

def get_display_name(player_name):
    """Gibt den Anzeigenamen für einen Spieler zurück, inkl. 🦵-Symbol wenn markiert"""
    if not player_name or not isinstance(player_name, str):
        return player_name
    
    # Für BYE, verwende das 🦵-Symbol als Anzeigename
    if player_name == "BYE":
        return "🦵"
    
    # Für markierte Spieler füge das 🦵-Symbol hinzu
    if is_player_marked(player_name):
        return f"{player_name} 🦵"
    
    return player_name

def generate_secret_key():
    """Generiert einen sicheren Secret Key"""
    return base64.b64encode(os.urandom(32)).decode('utf-8')

def get_secret_key():
    """
    Holt den Secret Key aus der Konfigurationsdatei oder erstellt einen neuen.
    Der Key wird in einer Datei gespeichert, damit er über Neustarts hinweg bestehen bleibt.
    """
    config_dir = "config"
    config_file = os.path.join(config_dir, "secret_key.txt")
    
    # Prüfe ob eine Umgebungsvariable gesetzt ist
    if os.environ.get('FLASK_SECRET_KEY'):
        return os.environ.get('FLASK_SECRET_KEY')
    
    # Erstelle das Konfig-Verzeichnis, falls es nicht existiert
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    
    # Versuche den Key aus der Datei zu lesen
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return f.read().strip()
        except:
            pass  # Falls das Lesen fehlschlägt, generieren wir einen neuen Key
    
    # Generiere einen neuen Key und speichere ihn
    secret_key = generate_secret_key()
    try:
        with open(config_file, 'w') as f:
            f.write(secret_key)
        return secret_key
    except:
        # Fallback für den Fall, dass wir nicht in die Datei schreiben können
        return generate_secret_key()

# Setze den Secret Key
main.secret_key = get_secret_key()

def find_all_valid_groupings(player_count, allowed_sizes):
    """
    Findet alle möglichen Gruppierungen für die gegebene Spieleranzahl.
    
    Args:
        player_count: Gesamtzahl der Spieler
        allowed_sizes: Liste der erlaubten Tischgrössen
    
    Returns:
        Liste von Tupeln mit möglichen Gruppierungen
    """
    print(f"Suche Gruppierungen für {player_count} Spieler mit erlaubten Größen {allowed_sizes}")
    valid_groupings = []
    
    def find_combinations(remaining_players, current_grouping):
        print(f"  Prüfe: Verbleibend={remaining_players}, Aktuell={current_grouping}")
        if remaining_players == 0:
            # Wenn alle Spieler verteilt sind, füge die Gruppierung hinzu
            sorted_grouping = tuple(sorted(current_grouping))
            if sorted_grouping not in valid_groupings:
                print(f"  Gefunden: {sorted_grouping}")
                valid_groupings.append(sorted_grouping)
            return
        
        # Probiere jede erlaubte Tischgrösse
        for size in sorted(allowed_sizes, reverse=True):
            if size <= remaining_players:
                find_combinations(remaining_players - size, current_grouping + [size])
    
    # Starte die rekursive Suche
    find_combinations(player_count, [])
    print(f"Gefundene Gruppierungen: {valid_groupings}")
    return valid_groupings

@main.route("/", methods=["GET"])
def index():
    return render_template("index.html", players_text="")

@main.route("/api/groupings", methods=["POST"])
def api_groupings():
    players = request.json.get("players", [])
    group_sizes = request.json.get("group_sizes", [])
    try:
        allowed_sizes = [int(size) for size in group_sizes if int(size) in [6, 8, 10, 12]]
    except ValueError:
        return jsonify([])
    groupings = find_all_valid_groupings(len(players), allowed_sizes)
    return jsonify(groupings)

def validate_player_name(name):
    """Validiert einen Spielernamen"""
    if not name or len(name.strip()) == 0:
        return False
    if len(name) > 50:  # Maximale Länge
        return False
    return True

@main.route("/pair", methods=["POST"])
def pair():
    if not session.get("tournament_id"):
        session["tournament_id"] = str(uuid.uuid4())

    tournament_id = session["tournament_id"]
    data_dir = os.path.join("data", tournament_id)
    os.makedirs(data_dir, exist_ok=True)

    # Initialisiere die Liste der markierten Spieler, nur wenn sie nicht existiert
    if "leg_players_set" not in session:
        session["leg_players_set"] = []  # Als leere Liste initialisieren
    
    # Verarbeite die Spielerliste - ohne Markierung in dieser Phase
    original_players = request.form.getlist("players")
    
    # Überprüfe auf doppelte Spielernamen
    seen_players = set()
    duplicate_players = [p for p in original_players if p in seen_players or seen_players.add(p)]
    
    if duplicate_players:
        return render_template("index.html", 
                               error=f"Doppelte Spielernamen gefunden: {', '.join(duplicate_players)}. Bitte geben Sie eindeutige Namen ein.",
                               players_text="\n".join(original_players))
    
    players = original_players  # Keine Markierung in dieser Phase
    
    group_sizes = request.form.getlist("group_sizes")
    
    try:
        # Konvertiere Gruppengrößen zu Integers und validiere sie
        allowed_sizes = [int(size) for size in group_sizes]
        if not allowed_sizes:
            return render_template("index.html", 
                                error="Bitte wählen Sie mindestens eine Tischgrösse aus.",
                                players_text="\n".join(players))
        
        # Finde mögliche Gruppierungen
        groupings = find_all_valid_groupings(len(players), allowed_sizes)
        
        if not groupings:
            return render_template("index.html", 
                                error=f"Keine gültige Gruppierung für {len(players)} Spieler mit den Tischgrössen {allowed_sizes} möglich.",
                                players_text="\n".join(players))
        
        # Wähle die erste gültige Gruppierung
        selected_grouping = groupings[0]
        
        # Mische die Spieler
        # Setze einen konstanten Seed für Reproduzierbarkeit
        random.seed(42)
        random.shuffle(players)
        
        pairings = []
        match_list = []
        start = 0
        table_nr = 1

        # Speichere die Spielergruppen in der Session und in einer JSON-Datei
        player_groups = {}
        
        for group_size in selected_grouping:
            # Hole die Spieler für diese Gruppe
            group = players[start:start + group_size]
            group_players = group.copy()  # Kopiere die Liste für die Session
            
            # Wenn die Tischgröße bereits vorhanden ist, füge die Spieler hinzu statt zu überschreiben
            size_key = str(group_size)
            if size_key in player_groups:
                player_groups[size_key].extend(group_players)
            else:
                player_groups[size_key] = group_players  # Speichere als String-Key
                
            pairings.append(group)
            start += group_size

            # Erstelle Matches für diese Gruppe
            shuffled = group.copy()
            random.shuffle(shuffled)

            for i in range(0, len(shuffled) - 1, 2):
                p1 = shuffled[i]
                p2 = shuffled[i + 1] if i + 1 < len(shuffled) else None
                if p2:
                    match_list.append({
                        "table": table_nr,
                        "player1": p1,
                        "player2": p2,
                        "score1": "",  # Leerer String statt '0'
                        "score2": "",  # Leerer String statt '0'
                        "table_size": str(group_size)  # Speichere als String
                    })
                    table_nr += 1

        # Speichere die Spielergruppen in einer JSON-Datei
        with open(os.path.join(data_dir, "player_groups.json"), "w") as f:
            json.dump(player_groups, f)

        session["player_groups"] = player_groups

        # Bestimme die aktuelle Runde und Gesamtanzahl der Runden
        current_round = 1
        total_rounds = 1
        
        # Speichere die erste Runde
        rounds_dir = os.path.join(data_dir, 'rounds')
        os.makedirs(rounds_dir, exist_ok=True)
        round_file = os.path.join(rounds_dir, f'round_{current_round}.csv')
        
        with open(round_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['table', 'player1', 'player2', 'score1', 'score2', 'table_size'])
            writer.writeheader()
            writer.writerows(match_list)
        
        # Leite zur show_round Route weiter
        return redirect(url_for('main.show_round', round_number=current_round))
    
    except ValueError as e:
        return render_template("index.html", 
                            error=f"Fehler bei der Verarbeitung der Gruppengrößen: {str(e)}",
                            players_text="\n".join(players))
    except Exception as e:
        return render_template("index.html", 
                            error=f"Ein unerwarteter Fehler ist aufgetreten: {str(e)}",
                            players_text="\n".join(players))

def ensure_data_directory():
    """Stellt sicher, dass das Datenverzeichnis existiert"""
    results_dir = "tournament_data"
    if not os.path.exists(results_dir):
        try:
            os.makedirs(results_dir)
        except OSError as e:
            print(f"Fehler beim Erstellen des Verzeichnisses: {e}")
            return False
    return True

@main.route("/save_results", methods=["POST"])
def save_results():
    tournament_id = session.get("tournament_id", "unknown")
    if not tournament_id:
        return redirect(url_for("main.index"))

    print("\n\n=== SAVE_RESULTS AUFGERUFEN ===")
    print(f"Tournament ID: {tournament_id}")
    
    # Formular-Daten holen
    table = request.form.get("table")
    player1 = request.form.get("player1")
    player2 = request.form.get("player2")
    score1 = request.form.get("score1", "0")
    score2 = request.form.get("score2", "0")
    current_round = request.form.get("current_round", "1")
    dropout1 = request.form.get("dropout1") == "true"
    dropout2 = request.form.get("dropout2") == "true"
    table_size = request.form.get("table_size", "6")  # Standardwert 6, falls nicht angegeben
    
    print(f"Daten aus Formular: Tisch {table}, {player1} vs {player2}, Ergebnis: {score1}-{score2}, Tischgrösse: {table_size}, Runde: {current_round}")
    print(f"Dropout1: {dropout1}, Dropout2: {dropout2}")
    
    # In results.csv speichern
    results_file = os.path.join("tournament_data", "results.csv")
    os.makedirs("tournament_data", exist_ok=True)
    file_exists = os.path.isfile(results_file)
    
    try:
        with open(results_file, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow(["Tournament", "Timestamp", "Table", "Player 1", "Score 1", "Player 2", "Score 2"])
            writer.writerow([tournament_id, datetime.now().isoformat(), table, player1, score1, player2, score2])
        print(f"Ergebnis in results.csv gespeichert")
    except Exception as e:
        print(f"Fehler beim Speichern in results.csv: {e}")
        return redirect(url_for("main.show_round", round_number=int(current_round)))

    
    # In Rundendatei aktualisieren
    try:
        data_dir = os.path.join("data", tournament_id)
        rounds_dir = os.path.join(data_dir, "rounds")
        round_file = os.path.join(rounds_dir, f"round_{current_round}.csv")
        
        print(f"Versuche, Ergebnis in {round_file} zu aktualisieren")
        
        if not os.path.exists(round_file):
            print(f"FEHLER: Rundendatei existiert nicht: {round_file}")
            return redirect(url_for("main.show_round", round_number=int(current_round)))
        
        # Datei lesen
        matches = []
        fieldnames = []
        try:
            with open(round_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                print(f"Feldnamen in CSV: {fieldnames}")
                
                # Stelle sicher, dass alle benötigten Felder in fieldnames sind
                required_fields = ['table', 'player1', 'player2', 'score1', 'score2', 'table_size', 'dropout1', 'dropout2', 'display_player1', 'display_player2']
                for field in required_fields:
                    if field not in fieldnames:
                        fieldnames.append(field)
                        print(f"Feldname '{field}' zur CSV hinzugefügt")
                
                # Lese alle Matches
                for row in reader:
                    # Stelle sicher, dass jedes Match alle Felder hat
                    for field in fieldnames:
                        if field not in row:
                            row[field] = ""
                    matches.append(row)
                    
            print(f"Matches aus Datei gelesen: {len(matches)}")
        except Exception as e:
            print(f"Fehler beim Lesen der Rundendatei: {e}")
            return redirect(url_for("main.show_round", round_number=int(current_round)))
        
        # Match finden und aktualisieren
        match_found = False
        for match in matches:
            print(f"Vergleiche Match: Tisch {match.get('table', 'unbekannt')} mit {table}")
            if str(match.get("table", "")) == str(table):
                print(f"Tisch gefunden! Spieler: {match.get('player1', '')} vs {match.get('player2', '')}")
                
                # Aktualisiere alle relevanten Werte
                match["score1"] = score1
                match["score2"] = score2
                match["dropout1"] = "true" if dropout1 else "false"
                match["dropout2"] = "true" if dropout2 else "false"
                
                # Stelle sicher, dass table_size als String gesetzt ist
                match["table_size"] = str(table_size)
                
                # Aktualisiere die display_player Felder
                if "display_player1" not in match or not match["display_player1"]:
                    match["display_player1"] = match["player1"]
                if "display_player2" not in match or not match["display_player2"]:
                    match["display_player2"] = match["player2"]
                
                # Füge Spieler zur markierten Liste hinzu oder entferne sie, basierend auf dropout-Status
                marked_players = session.get("leg_players_set", [])
                
                # Für Spieler 1
                if dropout1 and match['player1'] not in marked_players:
                    marked_players.append(match['player1'])
                    match['display_player1'] = get_display_name(match['player1'])
                    print(f"🦵-Status zu Spieler 1 hinzugefügt: {match['player1']}")
                elif not dropout1 and match['player1'] in marked_players:
                    marked_players.remove(match['player1'])
                    match['display_player1'] = match['player1']
                    print(f"🦵-Status von Spieler 1 entfernt: {match['player1']}")
                
                # Für Spieler 2 (wenn nicht BYE)
                if match['player2'] != "BYE":
                    if dropout2 and match['player2'] not in marked_players:
                        marked_players.append(match['player2'])
                        match['display_player2'] = get_display_name(match['player2'])
                        print(f"🦵-Status zu Spieler 2 hinzugefügt: {match['player2']}")
                    elif not dropout2 and match['player2'] in marked_players:
                        marked_players.remove(match['player2'])
                        match['display_player2'] = match['player2']
                        print(f"🦵-Status von Spieler 2 entfernt: {match['player2']}")
                
                # Aktualisiere die Session
                session["leg_players_set"] = marked_players
                
                match_found = True
                print(f"Match aktualisiert: {match}")
                break
        
        if not match_found:
            print(f"WARNUNG: Kein passendes Match für Tisch {table} gefunden!")
        
        # Debug-Ausgabe aller zu speichernder Matches
        print("\nAlle Matches, die gespeichert werden:")
        for i, match in enumerate(matches):
            table_size_value = match.get("table_size", "nicht gesetzt")
            print(f"Match {i+1}: Tisch {match.get('table', '')}, {match.get('player1', '')} vs {match.get('player2', '')}, Score: {match.get('score1', '')}-{match.get('score2', '')}, Tischgrösse: {table_size_value}")
        
        # Datei zurückschreiben
        try:
            with open(round_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(matches)
            print(f"Rundendatei erfolgreich aktualisiert")
        except Exception as e:
            print(f"Fehler beim Schreiben der Rundendatei: {e}")
    except Exception as e:
        import traceback
        print(f"Allgemeiner Fehler bei Rundendatei: {e}")
        print(traceback.format_exc())
    
    # Zurück zur Rundenansicht
    print(f"Leite weiter zu Runde {current_round}")
    return redirect(url_for("main.show_round", round_number=int(current_round)))

def calculate_mtg_stats(results_file, tournament_id):
    """Berechnet MTG-spezifische Turnierstatistiken"""
    stats = defaultdict(lambda: {
        'match_wins': 0,
        'match_losses': 0,
        'match_draws': 0,
        'game_wins': 0,
        'game_losses': 0,
        'game_draws': 0,
        'opponents': set(),
        'points': 0
    })
    
    try:
        with open(results_file, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row["Tournament"] != tournament_id:
                    continue

                p1, p2 = row["Player 1"], row["Player 2"]
                s1, s2 = int(row["Score 1"]), int(row["Score 2"])
                
                # Game Wins berechnen
                stats[p1]['game_wins'] += s1
                stats[p1]['game_losses'] += s2
                stats[p2]['game_wins'] += s2
                stats[p2]['game_losses'] += s1
                
                # Match Wins berechnen
                if s1 > s2:
                    stats[p1]['match_wins'] += 1
                    stats[p1]['points'] += 3
                    stats[p2]['match_losses'] += 1
                elif s2 > s1:
                    stats[p2]['match_wins'] += 1
                    stats[p2]['points'] += 3
                    stats[p1]['match_losses'] += 1
                else:
                    stats[p1]['match_draws'] += 1
                    stats[p2]['match_draws'] += 1
                    stats[p1]['points'] += 1
                    stats[p2]['points'] += 1
                
                # Gegner für Tiebreaker
                stats[p1]['opponents'].add(p2)
                stats[p2]['opponents'].add(p1)

    except (IOError, OSError) as e:
        print(f"Fehler beim Lesen der Ergebnisse: {e}")
        return {}

    return stats


def calculate_tiebreakers(stats):
    """Berechnet MTG Tiebreaker (OMW%, GWP%)"""
    tiebreakers = {}
    
    for player, player_stats in stats.items():
        # Opponent Match Win %
        opp_match_wins = 0
        opp_matches = 0
        for opp in player_stats['opponents']:
            if opp in stats:
                opp_match_wins += stats[opp]['match_wins']
                opp_matches += (stats[opp]['match_wins'] + 
                              stats[opp]['match_losses'] + 
                              stats[opp]['match_draws'])
        
        omw = (opp_match_wins / opp_matches * 100) if opp_matches > 0 else 0
        
        # Game Win %
        total_games = (player_stats['game_wins'] + 
                      player_stats['game_losses'] + 
                      player_stats['game_draws'])
        gwp = (player_stats['game_wins'] / total_games * 100) if total_games > 0 else 0
        
        tiebreakers[player] = {
            'omw': round(omw, 1),
            'gwp': round(gwp, 1)
        }
    
    return tiebreakers

def get_player_opponents(tournament_id, current_round):
    """Lädt die Gegner-Historie für alle Spieler aus den vorherigen Runden."""
    data_dir = os.path.join("data", tournament_id)
    opponents = defaultdict(list)
    
    # Gehe durch alle bisherigen Runden
    for round_num in range(1, current_round + 1):
        round_file = os.path.join(data_dir, "rounds", f"round_{round_num}.csv")
        if os.path.exists(round_file):
            with open(round_file, "r", encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for match in reader:
                    player1 = match["player1"]
                    player2 = match["player2"]
                    # Debug: Markierte Spieler überprüfen
                    if player1 in session.get("leg_players_set", []) or player2 in session.get("leg_players_set", []):
                        print(f"Gegner-Historie Runde {round_num}: {player1} vs {player2}")
                    # Speichere auch die Runde, in der sie gegeneinander gespielt haben
                    opponents[player1].append((player2, round_num))
                    opponents[player2].append((player1, round_num))
    
    return opponents

@main.route("/next_round", methods=["POST"])
def next_round():
    tournament_id = session.get("tournament_id")
    if not tournament_id:
        return redirect(url_for("main.index"))

    data_dir = os.path.join("data", tournament_id)
    rounds_dir = os.path.join(data_dir, "rounds")
    os.makedirs(rounds_dir, exist_ok=True)

    # Lade die Spielergruppen
    player_groups_file = os.path.join(data_dir, 'player_groups.json')
    if not os.path.exists(player_groups_file):
        return redirect(url_for('main.index', error="Spielergruppen nicht gefunden"))
    
    with open(player_groups_file, 'r', encoding='utf-8') as f:
        player_groups = json.load(f)
    
    # Stelle sicher, dass die markierten Spieler in der Session bleiben
    if "leg_players_set" not in session:
        session["leg_players_set"] = []
    
    # Debug-Ausgabe der markierten Spieler
    marked_players = session.get("leg_players_set", [])
    print(f"Markierte Spieler (mit 🦵): {marked_players}")
    
    # Bestimme die aktuelle Runde
    current_round = len([f for f in os.listdir(rounds_dir) if f.startswith('round_') and f.endswith('.csv')])

    # Berechne den Leaderboard für die aktuelle Runde
    leaderboard = calculate_leaderboard(tournament_id, current_round)
    
    # Lade die Gegner-Historie
    opponents = get_player_opponents(tournament_id, current_round)
    
    # Erstelle neue Paarungen für die nächste Runde
    match_list = []
    table_nr = 1

    # Erstelle Paarungen für jede Gruppe separat
    for group_size, group_players in player_groups.items():
        # Entferne markierte Spieler aus der aktiven Liste
        active_players = [p for p in group_players if not is_player_marked(p)]
        print(f"Aktive Spieler in Gruppe {group_size}: {active_players}")
        
        # Sortiere aktive Spieler nach Punkten für bessere Paarungen
        sorted_players = []
        for player in active_players:
            player_stats = next((p for p in leaderboard if p[0] == player), None)
            if player_stats:
                sorted_players.append((player, int(player_stats[1]), player))
            else:
                sorted_players.append((player, 0, player))
        
        # Sortiere nach Punkten (absteigend) und dann nach Namen
        sorted_players.sort(key=lambda x: (-x[1], x[2]))
        sorted_players = [p[0] for p in sorted_players]
        
        if len(sorted_players) % 2 != 0:
            # Der niedrigstplatzierte Spieler bekommt ein BYE
            bye_player = sorted_players.pop()
            match_list.append({
                "table": str(table_nr),
                "player1": bye_player,
                "player2": "BYE",
                "score1": "2",  # Automatischer Sieg für den Spieler
                "score2": "0",
                "table_size": group_size
            })
            table_nr += 1
            print(f"BYE-Match: {bye_player} vs BYE mit automatischem Ergebnis 2:0")
        
        # Matche die restlichen Spieler
        for i in range(0, len(sorted_players), 2):
            if i + 1 < len(sorted_players):
                p1, p2 = sorted_players[i], sorted_players[i+1]
                
                # Prüfe, ob sie bereits gegeneinander gespielt haben
                player1_opponents = [opp[0] for opp in opponents.get(p1, [])]
                if p2 in player1_opponents and i + 2 < len(sorted_players):
                    # Versuche, einen anderen Gegner zu finden
                    for j in range(i+2, len(sorted_players), 2):
                        if j + 1 < len(sorted_players):
                            alt_p2 = sorted_players[j]
                            alt_p1 = sorted_players[j+1]
                            alt_p1_opponents = [opp[0] for opp in opponents.get(alt_p1, [])]
                            alt_p2_opponents = [opp[0] for opp in opponents.get(alt_p2, [])]
                            
                            if p1 not in alt_p2_opponents and p2 not in alt_p1_opponents:
                                # Tausche die Gegner
                                sorted_players[i+1], sorted_players[j] = sorted_players[j], sorted_players[i+1]
                                sorted_players[j+1], sorted_players[i+2] = sorted_players[i+2], sorted_players[j+1]
                                p2 = alt_p2
                                break
                
                match_list.append({
                    "table": str(table_nr),
                    "player1": p1,
                    "player2": p2,
                    "score1": "",
                    "score2": "",
                    "table_size": group_size
                })
                table_nr += 1
                print(f"Match: {p1} vs {p2}")

    # Speichere die neue Runde
    next_round_number = current_round + 1
    next_round_file = os.path.join(rounds_dir, f'round_{next_round_number}.csv')
    
    with open(next_round_file, 'w', newline='', encoding='utf-8') as f:
        # Stelle sicher, dass die 🦵-Symbole bei den Spielernamen erhalten bleiben
        for match in match_list:
            # Bereite die display_player Felder vor
            match['display_player1'] = match['player1']
            match['display_player2'] = match['player2']
            
            if is_player_marked(match['player1']):
                match['display_player1'] = get_display_name(match['player1'])
                print(f"next_round: Setze display_player1 für {match['player1']} auf {match['display_player1']}")
            
            if match['player2'] != "BYE" and is_player_marked(match['player2']):
                match['display_player2'] = get_display_name(match['player2'])
                print(f"next_round: Setze display_player2 für {match['player2']} auf {match['display_player2']}")
            elif match['player2'] == "BYE":
                match['display_player2'] = "BYE"
                
            # Debug-Ausgabe für Spielernamen in der Runde
            print(f"Match: {match['display_player1']} vs {match['display_player2']} (Original: {match['player1']} vs {match['player2']})")
                
        # Verwende erweiterte Feldliste mit display_player Feldern
        writer = csv.DictWriter(f, fieldnames=['table', 'player1', 'player2', 'score1', 'score2', 'table_size', 'display_player1', 'display_player2'])
        writer.writeheader()
        writer.writerows(match_list)

    # Speichere die BYE Matches in der results.csv
    results_file = os.path.join("tournament_data", "results.csv")
    file_exists = os.path.isfile(results_file)
    
    with open(results_file, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["Tournament", "Timestamp", "Table", "Player 1", "Score 1", "Player 2", "Score 2"])
        
        # Speichere BYE Matches automatisch
        for match in match_list:
            if match["player2"] == "BYE":
                writer.writerow([
                    tournament_id,
                    datetime.now().isoformat(),
                    match["table"],
                    match["player1"],
                    "2",  # Automatischer Sieg
                    match["player2"],
                    "0"
                ])

    # Leite zur show_round Route weiter
    return redirect(url_for('main.show_round', round_number=next_round_number))

@main.route("/start_tournament", methods=["GET"])
def start_tournament():
    # Vollständiges Zurücksetzen der Session beim Start eines neuen Turniers
    session.clear()
    session["tournament_id"] = str(uuid.uuid4())
    # Explizit die Liste der markierten Spieler zurücksetzen
    session["leg_players_set"] = []
    return redirect(url_for("main.index"))

@main.route("/continue_tournament", methods=["GET"])
def continue_tournament():
    """
    Setzt ein laufendes Turnier fort.
    
    Ablauf:
    1. Prüft die Turnier-ID
    2. Lädt die letzten Ergebnisse
    3. Berechnet die aktuellen Statistiken
    4. Zeigt das aktuelle Leaderboard und die letzten Paarungen
    """
    # 1. Turnier-ID prüfen
    tid = session.get("tournament_id")
    if not tid:
        return redirect("/")

    # 2. Datenverzeichnis und Datei prüfen
    if not ensure_data_directory():
        return "<h2>Fehler: Datenverzeichnis nicht verfügbar!</h2><p><a href='/'>Zurück</a></p>"

    results_file = os.path.join("tournament_data", "results.csv")
    if not os.path.exists(results_file):
        return "<h2>Keine gespeicherten Resultate gefunden.</h2><p><a href='/'>Zurück</a></p>"

    # 3. Letzte Runde finden
    try:
        with open(results_file, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            rows = [row for row in reader if row["Tournament"] == tid]

        if not rows:
            return "<h2>Keine gespeicherten Resultate für dieses Turnier gefunden.</h2><p><a href='/'>Zurück</a></p>"

        # Sortiere nach Zeitstempel und finde die letzte Runde
        rows.sort(key=lambda x: x["Timestamp"], reverse=True)
        last_timestamp = rows[0]["Timestamp"]
        last_round = [r for r in rows if r["Timestamp"] == last_timestamp]

    except (IOError, OSError) as e:
        return f"<h2>Fehler beim Lesen der Ergebnisse: {str(e)}</h2><p><a href='/'>Zurück</a></p>"

    # 4. Paarungen der letzten Runde vorbereiten
    pairings = defaultdict(list)
    match_list = []
    players_set = set()

    for r in last_round:
        t = int(r["Table"])
        p1 = r["Player 1"]
        p2 = r["Player 2"]
        pairings[t].extend([p1, p2])
        match_list.append({
            "table": t,
            "player1": p1,
            "player2": p2
        })
        players_set.update([p1, p2])

    # 5. Spielergruppen vorbereiten
    group_list = []
    for t in sorted(pairings.keys()):
        unique_players = sorted(set(pairings[t]))
        group_list.append(unique_players)

    # 6. Statistiken berechnen
    stats = calculate_mtg_stats(results_file, tid)
    tiebreakers = calculate_tiebreakers(stats)

    # 7. Leaderboard erstellen
    leaderboard = []
    for player, player_stats in stats.items():
        omw = calculate_opponents_match_percentage(player, stats)
        gw = calculate_game_win_percentage(player_stats)
        leaderboard.append((
            player,
            player_stats['points'],
            f"{player_stats['total_wins']} - {player_stats['total_losses']}",  # Gesamtsumme aller Siege und Niederlagen
            f"{omw:.2%}",
            f"{gw:.2%}"
        ))

    # Sortiere nach Punkten, OMW% und GW%
    leaderboard.sort(key=lambda x: (-int(x[1]), -float(x[3].replace('%', '')), -float(x[4].replace('%', '')), x[0]))

    return render_template("pair.html", 
                         pairings=group_list, 
                         matches=match_list, 
                         leaderboard=leaderboard)

@main.route("/end_tournament", methods=["POST"])
def end_tournament():
    tournament_id = session.get("tournament_id")
    if not tournament_id:
        return redirect(url_for("main.index"))
    
    # Berechne den finalen Leaderboard
    data_dir = os.path.join("data", tournament_id)
    rounds_dir = os.path.join(data_dir, "rounds")
    if os.path.exists(rounds_dir):
        total_rounds = len([f for f in os.listdir(rounds_dir) if f.startswith("round_") and f.endswith(".csv")])
        final_leaderboard = calculate_leaderboard(tournament_id, total_rounds)
    else:
        final_leaderboard = []
    
    # Lade die Spielergruppen
    player_groups = {}
    player_groups_file = os.path.join(data_dir, "player_groups.json")
    if os.path.exists(player_groups_file):
        with open(player_groups_file, "r") as f:
            player_groups = json.load(f)
    
    # Rendere die Endstand-Seite
    tournament_data = {
        "id": tournament_id,
        "end_date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "total_rounds": total_rounds,
        "player_groups": player_groups
    }
    
    # Speichere die Turnierdaten für spätere Referenz
    tournament_results_dir = "tournament_results"
    os.makedirs(tournament_results_dir, exist_ok=True)
    
    results_file = os.path.join(tournament_results_dir, f"{tournament_id}_results.json")
    with open(results_file, "w") as f:
        json.dump({
            "tournament_data": tournament_data,
            "final_leaderboard": final_leaderboard
        }, f)
    
    # Entferne alle Session-Daten
    session.clear()
    
    return render_template(
        "tournament_end.html",
        tournament_data=tournament_data,
        leaderboard=final_leaderboard
    )

@main.route("/round/<int:round_number>")
def show_round(round_number):
    tournament_id = session.get("tournament_id")
    if not tournament_id:
        return redirect(url_for("main.index"))
    
    print(f"\n\n=== SHOW_ROUND AUFGERUFEN: Runde {round_number} ===")
    print(f"Tournament ID: {tournament_id}")

    data_dir = os.path.join("data", tournament_id)
    rounds_dir = os.path.join(data_dir, "rounds")
    
    # Stelle sicher, dass die markierten Spieler in der Session bleiben
    if "leg_players_set" not in session:
        session["leg_players_set"] = []
    
    # Debug-Ausgabe der markierten Spieler
    marked_players = session.get("leg_players_set", [])
    print(f"Markierte Spieler in show_round: {marked_players}")

    # Lade die player_groups
    player_groups_file = os.path.join(data_dir, "player_groups.json")
    player_groups = {}
    if os.path.exists(player_groups_file):
        with open(player_groups_file, "r", encoding="utf-8") as f:
            player_groups = json.load(f)
        print(f"Player Groups geladen: {player_groups.keys()}")
    else:
        print(f"WARNUNG: player_groups.json nicht gefunden in {player_groups_file}")
    
    # Erstelle eine Map von Spielern zu ihrer Gruppengröße
    player_to_table_size = {}
    for table_size, players in player_groups.items():
        for player in players:
            player_to_table_size[player] = table_size

    # Lade die Dropouts
    dropouts_file = os.path.join(data_dir, "dropouts.json")
    dropouts = {}
    if os.path.exists(dropouts_file):
        with open(dropouts_file, "r", encoding="utf-8") as f:
            dropouts = json.load(f)

    # Lade die Matches für die angegebene Runde
    round_file = os.path.join(rounds_dir, f"round_{round_number}.csv")
    print(f"Versuche, Rundendatei zu laden: {round_file}")
    
    try:
        if not os.path.exists(round_file):
            print(f"FEHLER: Rundendatei existiert nicht: {round_file}")
            return redirect(url_for("main.index", error=f"Runde {round_number} nicht gefunden"))
        
        matches = []
        
        with open(round_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            print(f"CSV-Header: {fieldnames}")
            
            # Prüfe, ob alle benötigten Felder vorhanden sind
            required_fields = ['table', 'player1', 'player2', 'score1', 'score2', 'table_size']
            for field in required_fields:
                if field not in fieldnames:
                    print(f"WARNUNG: Wichtiges Feld '{field}' fehlt in der CSV-Datei")
            
            for row in reader:
                # Konvertiere die Zeilen in ein Dictionary, wenn es eine einfache Zeile ist
                match_data = row
                if isinstance(row, list) and len(row) >= 5:
                    match_data = {
                        "table": row[0],
                        "player1": row[1],
                        "player2": row[2],
                        "score1": row[3] if row[3] else "0",
                        "score2": row[4] if row[4] else "0",
                        "table_size": row[5] if len(row) > 5 else "6"
                    }
                
                # Stelle sicher, dass alle Werte als Strings vorliegen und leere Werte einen Standardwert haben
                for key, value in match_data.items():
                    if value is None:
                        match_data[key] = ""
                    else:
                        match_data[key] = str(value)
                
                # Stelle sicher, dass table_size gesetzt ist und als String vorliegt
                if 'table_size' not in match_data or not match_data['table_size']:
                    # Versuche, die table_size aus player_to_table_size zu ermitteln
                    player1 = match_data.get('player1', '')
                    player2 = match_data.get('player2', '')
                    if player1 in player_to_table_size:
                        match_data['table_size'] = str(player_to_table_size[player1])
                    elif player2 != "BYE" and player2 in player_to_table_size:
                        match_data['table_size'] = str(player_to_table_size[player2])
                    else:
                        # Standardwert als Fallback
                        match_data['table_size'] = "6"
                    print(f"table_size für Match {match_data.get('table', '')} auf {match_data['table_size']} gesetzt")
                
                # Stelle sicher, dass alle erforderlichen Felder vorhanden sind
                if 'dropout1' not in match_data:
                    match_data['dropout1'] = 'false'
                if 'dropout2' not in match_data:
                    match_data['dropout2'] = 'false'
                
                # Überprüfe auf display_player Felder und aktualisiere wenn nötig
                if 'display_player1' not in match_data or not match_data['display_player1']:
                    # Wenn das Feld nicht vorhanden ist, generiere es neu
                    match_data['display_player1'] = get_display_name(match_data['player1'])
                if 'display_player2' not in match_data or not match_data['display_player2']:
                    match_data['display_player2'] = get_display_name(match_data['player2'])
                
                # Stelle sicher, dass die 🦵-Markierung sichtbar bleibt
                if is_player_marked(match_data['player1']):
                    match_data['display_player1'] = get_display_name(match_data['player1'])
                    print(f"show_round: Setze display_player1 für {match_data['player1']} auf {match_data['display_player1']}")
                if is_player_marked(match_data['player2']) and match_data['player2'] != "BYE":
                    match_data['display_player2'] = get_display_name(match_data['player2'])
                    print(f"show_round: Setze display_player2 für {match_data['player2']} auf {match_data['display_player2']}")
                elif match_data['player2'] == "BYE":
                    match_data['display_player2'] = "BYE"
                
                # Extrahiere und konvertiere Scores
                try:
                    score1 = int(match_data['score1']) if match_data['score1'] else 0
                    score2 = int(match_data['score2']) if match_data['score2'] else 0
                except ValueError:
                    print(f"WARNUNG: Ungültige Scores für Match {match_data.get('table', '')}: {match_data.get('score1', '')}-{match_data.get('score2', '')}")
                    score1 = 0
                    score2 = 0
                
                match_data['score1'] = str(score1)
                match_data['score2'] = str(score2)
                
                # Überprüfe auf Drop-Outs
                dropout1 = match_data.get('dropout1') == 'true'
                dropout2 = match_data.get('dropout2') == 'true'
                if dropouts and str(round_number) in dropouts:
                    dropout1 = dropout1 or match_data['player1'] in dropouts[str(round_number)]
                    dropout2 = dropout2 or match_data['player2'] in dropouts[str(round_number)]
                
                # Aktualisiere dropout-Flags
                match_data['dropout1'] = 'true' if dropout1 else 'false'
                match_data['dropout2'] = 'true' if dropout2 else 'false'
                
                # Erstelle das Match-Objekt (verwende direkt das Dictionary)
                matches.append(match_data)
                print(f"Match geladen: Tisch {match_data['table']}, {match_data['player1']} vs {match_data['player2']}, Größe: {match_data['table_size']}")
        
        print(f"Insgesamt {len(matches)} Matches geladen")
        
        # Gruppiere Matches nach Tischgrösse für Debugging
        table_sizes = {}
        for match in matches:
            size = match['table_size']
            if size not in table_sizes:
                table_sizes[size] = []
            table_sizes[size].append(match)
        
        for size, matches_in_size in table_sizes.items():
            print(f"Tischgrösse {size}: {len(matches_in_size)} Matches")
        
        # Berechne den aktuellen Leaderboard
        leaderboard = calculate_leaderboard(tournament_id, round_number)
        print(f"Leaderboard Länge: {len(leaderboard)}")
        if leaderboard:
            print(f"Erste drei Einträge: {leaderboard[:min(3, len(leaderboard))]}")
        
        # Ermittle die Gesamtzahl der Runden
        total_rounds = 0
        for file in os.listdir(rounds_dir):
            if file.startswith("round_") and file.endswith(".csv"):
                round_num = int(file.split("_")[1].split(".")[0])
                total_rounds = max(total_rounds, round_num)
        
        print(f"Template wird gerendert mit: current_round={round_number}, {len(matches)} Matches, {len(leaderboard)} Spieler im Leaderboard")
        return render_template(
            "pair.html",
            current_round=round_number,
            matches=matches,
            leaderboard=leaderboard,
            marked=session.get("leg_players_set", []),
            player_groups=player_groups,
            total_rounds=total_rounds,
            is_player_marked=is_player_marked
        )
    
    except Exception as e:
        import traceback
        print(f"Fehler in show_round: {e}")
        print(traceback.format_exc())
        return redirect(url_for("main.index", error=f"Fehler beim Laden der Runde {round_number}: {str(e)}"))

def calculate_opponents_match_percentage(player, stats):
    """Berechnet den OMW% (Opponents Match Win Percentage) für einen Spieler."""
    if player not in stats:
        return 0.0
    
    # Sammle alle Gegner des Spielers
    opponents = []
    for opponent, opponent_stats in stats.items():
        if opponent == player:  # Überspringe den Spieler selbst
            continue
        # Prüfe, ob dieser Spieler ein Gegner war
        if opponent in stats.get(player, {}).get('opponents', []):
            opponents.append(opponent)
    
    if not opponents:  # Wenn keine Gegner gefunden wurden
        return 0.0
    
    # Berechne den durchschnittlichen Match-Win-Prozentsatz der Gegner
    total_win_percentage = 0.0
    for opponent in opponents:
        opponent_stats = stats[opponent]
        # Verwende die in calculate_leaderboard verwendeten Schlüsselnamen
        total_matches = opponent_stats['wins'] + opponent_stats['losses']
        if total_matches > 0:
            win_percentage = opponent_stats['wins'] / total_matches
        else:
            win_percentage = 0.0
        total_win_percentage += win_percentage
    
    return total_win_percentage / len(opponents) if opponents else 0.0

def calculate_game_win_percentage(player_stats):
    """Berechnet den GW% (Game Win Percentage) für einen Spieler."""
    total_games = player_stats['wins'] + player_stats['losses']
    if total_games == 0:
        return 0.0
    return player_stats['wins'] / total_games

def calculate_opponents_game_win_percentage(player, stats):
    """Berechnet den OGW% (Opponents Game Win Percentage) für einen Spieler."""
    if player not in stats:
        return 0.0
    
    # Sammle alle Gegner des Spielers
    opponents = []
    for opponent, opponent_stats in stats.items():
        if opponent == player:  # Überspringe den Spieler selbst
            continue
        # Prüfe, ob dieser Spieler ein Gegner war
        if opponent in stats.get(player, {}).get('opponents', []):
            opponents.append(opponent)
    
    if not opponents:  # Wenn keine Gegner gefunden wurden
        return 0.0
    
    # Berechne den durchschnittlichen Game-Win-Prozentsatz der Gegner
    total_game_win_percentage = 0.0
    for opponent in opponents:
        opponent_stats = stats[opponent]
        # Berechne den GW% für jeden Gegner
        total_games = opponent_stats['total_wins'] + opponent_stats['total_losses']
        if total_games > 0:
            game_win_percentage = opponent_stats['total_wins'] / total_games
        else:
            game_win_percentage = 0.0
        total_game_win_percentage += game_win_percentage
    
    return total_game_win_percentage / len(opponents) if opponents else 0.0

def calculate_leaderboard(tournament_id, up_to_round):
    """Berechnet den Leaderboard basierend auf den Ergebnissen bis zur angegebenen Runde."""
    data_dir = os.path.join("data", tournament_id)
    stats = defaultdict(lambda: {'points': 0, 'matches': 0, 'wins': 0, 'losses': 0, 'opponents': [], 'total_wins': 0, 'total_losses': 0})
    
    # Debug-Ausgabe
    print(f"Berechne Leaderboard für Turnier {tournament_id} bis Runde {up_to_round}")
    
    # Gehe durch alle Runden bis zur angegebenen Runde
    for round_num in range(1, up_to_round + 1):
        round_file = os.path.join(data_dir, "rounds", f"round_{round_num}.csv")
        if os.path.exists(round_file):
            print(f"Verarbeite Runde {round_num}")
            try:
                with open(round_file, "r") as f:
                    reader = csv.DictReader(f)
                    for match in reader:
                        player1 = match["player1"]
                        player2 = match["player2"]
                        
                        # Wenn es ein BYE Match ist, bekommt der aktive Spieler 2 Siege
                        if player2 == "BYE":
                            score1 = 2
                            score2 = 0
                        # Nur wenn beide Scores eingetragen sind
                        elif match["score1"] and match["score2"]:
                            score1 = int(match["score1"])
                            score2 = int(match["score2"])
                        else:
                            continue  # Überspringe Matches ohne Ergebnis
                            
                        # Debug-Ausgabe
                        print(f"  Match: {player1} vs {player2}, Ergebnis: {score1}-{score2}")
                        
                        # Aktualisiere die Gegner-Listen
                        stats[player1]['opponents'].append(player2)
                        stats[player2]['opponents'].append(player1)
                        
                        # Aktualisiere die Statistiken für beide Spieler
                        if score1 > score2:
                            stats[player1]['points'] += 3
                            stats[player1]['wins'] += 1
                            stats[player2]['losses'] += 1
                        elif score2 > score1:
                            stats[player2]['points'] += 3
                            stats[player2]['wins'] += 1
                            stats[player1]['losses'] += 1
                        
                        # Aktualisiere die Gesamtsiege und -niederlagen
                        stats[player1]['total_wins'] += score1
                        stats[player1]['total_losses'] += score2
                        stats[player2]['total_wins'] += score2
                        stats[player2]['total_losses'] += score1
                        
                        stats[player1]['matches'] += 1
                        stats[player2]['matches'] += 1
            except (IOError, OSError) as e:
                print(f"Fehler beim Lesen der Runde {round_num}: {e}")
        else:
            print(f"Runde {round_num} nicht gefunden")

    # Debug-Ausgabe der Statistiken
    for player, player_stats in stats.items():
        print(f"Spieler: {player}, Punkte: {player_stats['points']}, Siege: {player_stats['wins']}, Niederlagen: {player_stats['losses']}")

    # Erstelle den Leaderboard
    leaderboard = []
    for player, player_stats in stats.items():
        omw = calculate_opponents_match_percentage(player, stats)
        gw = calculate_game_win_percentage(player_stats)
        ogw = calculate_opponents_game_win_percentage(player, stats)
        leaderboard.append((
            player,
            player_stats['points'],
            f"{player_stats['total_wins']} - {player_stats['total_losses']}",  # Gesamtsumme aller Siege und Niederlagen
            f"{omw:.2%}",
            f"{gw:.2%}",
            f"{ogw:.2%}"
        ))

    # Sortiere nach Punkten, OMW%, GW% und OGW% (gemäß der vorgegebenen Reihenfolge der Tiebreaker)
    leaderboard.sort(key=lambda x: (
        -int(x[1]),  # Punkte (absteigend)
        -float(x[3].replace('%', '')),  # OMW% (absteigend)
        -float(x[4].replace('%', '')),  # GW% (absteigend)
        -float(x[5].replace('%', '')),  # OGW% (absteigend)
        x[0]  # Bei Gleichstand alphabetisch nach Namen (aufsteigend)
    ))
    return leaderboard