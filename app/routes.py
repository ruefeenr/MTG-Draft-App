from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
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
    Holt den Secret Key aus der Umgebungsvariable oder generiert einen neuen.
    Die Priorität ist:
    1. Umgebungsvariable FLASK_SECRET_KEY
    2. Lokale .env Datei (wenn vorhanden)
    3. In Entwicklungsumgebungen: Datei im .gitignore-geschützten Verzeichnis
    4. Fallback: Temporärer Secret Key (nicht persistent)
    """
    # 1. Prüfe ob eine Umgebungsvariable gesetzt ist
    if os.environ.get('FLASK_SECRET_KEY'):
        return os.environ.get('FLASK_SECRET_KEY')
    
    # 2. Versuche aus .env-Datei zu laden, falls python-dotenv installiert ist
    try:
        from dotenv import load_dotenv
        load_dotenv()  # Lädt Variablen aus .env in die Umgebung
        if os.environ.get('FLASK_SECRET_KEY'):
            return os.environ.get('FLASK_SECRET_KEY')
    except ImportError:
        # python-dotenv ist nicht installiert - ignorieren
        pass
    
    # 3. Im Entwicklungsmodus: Nutze eine Datei in einem sicheren, .gitignore-geschützten Verzeichnis
    config_dir = "instance"  # Flask-Standard für nicht-versionierte Konfiguration
    config_file = os.path.join(config_dir, "secret_key")
    
    if DEBUG:  # Nur im Debug-Modus verwenden wir die Datei
        # Erstelle das Konfig-Verzeichnis, falls es nicht existiert
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        # Versuche den Key aus der Datei zu lesen
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    key = f.read().strip()
                    if key:  # Stellen sicher, dass der Key nicht leer ist
                        return key
            except:
                pass  # Bei Fehlern einfach einen neuen Key generieren
        
        # Generiere einen neuen Key und speichere ihn
        secret_key = generate_secret_key()
        try:
            with open(config_file, 'w') as f:
                f.write(secret_key)
            print("HINWEIS: Ein neuer Secret Key wurde in 'instance/secret_key' generiert")
            print("WICHTIG: Dieses Verzeichnis sollte in .gitignore aufgenommen werden!")
            return secret_key
        except Exception as e:
            print(f"WARNUNG: Secret Key konnte nicht gespeichert werden: {e}")
    
    # 4. Fallback: Temporärer Key (Achtung: ändert sich bei jedem Neustart!)
    print("WARNUNG: Verwende temporären Secret Key - Sessions gehen bei Neustart verloren!")
    print("EMPFEHLUNG: Setzen Sie FLASK_SECRET_KEY als Umgebungsvariable für Persistenz.")
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

def get_last_tournaments(limit=5):
    """Lädt die letzten abgeschlossenen Turniere aus dem tournament_results Verzeichnis"""
    tournament_results_dir = "tournament_results"
    if not os.path.exists(tournament_results_dir):
        return []
    
    # Alle Turnier-Dateien finden
    tournament_files = []
    for file in os.listdir(tournament_results_dir):
        if file.endswith("_results.json"):
            file_path = os.path.join(tournament_results_dir, file)
            try:
                # Dateiinformationen laden
                stat_info = os.stat(file_path)
                modified_time = stat_info.st_mtime
                tournament_files.append((file_path, modified_time))
            except Exception as e:
                print(f"Fehler beim Laden von {file}: {str(e)}")
    
    # Nach Änderungsdatum sortieren (neueste zuerst)
    tournament_files.sort(key=lambda x: x[1], reverse=True)
    
    # Die letzten X Turniere laden
    last_tournaments = []
    for file_path, _ in tournament_files[:limit]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tournament_data = json.load(f)
                
                # Finde den Gewinner (erster Eintrag im Leaderboard)
                winner_name = "Unbekannt"
                if tournament_data.get('final_leaderboard') and len(tournament_data['final_leaderboard']) > 0:
                    winner_name = tournament_data['final_leaderboard'][0][0]
                
                # Tournament-ID aus dem Dateinamen extrahieren
                tournament_id = os.path.basename(file_path).replace('_results.json', '')
                
                # Erstelle ein kompaktes Turnierformat
                tournament_info = {
                    'id': tournament_id,
                    'winner': winner_name,
                    'date': tournament_data.get('tournament_data', {}).get('end_date', 'Unbekannt'),
                    'rounds': tournament_data.get('tournament_data', {}).get('total_rounds', 0),
                    'leaderboard': tournament_data.get('final_leaderboard', [])
                }
                last_tournaments.append(tournament_info)
        except Exception as e:
            print(f"Fehler beim Verarbeiten von {file_path}: {str(e)}")
    
    return last_tournaments

@main.route("/", methods=["GET"])
def index():
    # Lade die letzten 5 Turniere für die Startseite
    last_tournaments = get_last_tournaments(5)
    return render_template("index.html", players_text="", last_tournaments=last_tournaments)

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
        
        # Zähler für gleiche Tischgrößen
        table_size_counters = {}
        
        for group_size in selected_grouping:
            # Hole die Spieler für diese Gruppe
            group = players[start:start + group_size]
            group_players = group.copy()  # Kopiere die Liste für die Session
            
            # Erstelle einen zusammengesetzten Schlüssel mit Zähler
            size_str = str(group_size)
            if size_str in table_size_counters:
                table_size_counters[size_str] += 1
            else:
                table_size_counters[size_str] = 1
                
            # Zusammengesetzter Schlüssel: Tischgröße-Zähler
            composite_key = f"{size_str}-{table_size_counters[size_str]}"
            player_groups[composite_key] = group_players
                
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
                        "table_size": str(group_size),  # Speichere als String
                        "group_key": composite_key  # Speichere den zusammengesetzten Schlüssel
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
        
        with open(round_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['table', 'player1', 'player2', 'score1', 'score2', 'table_size', 'group_key'])
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
        return jsonify({"success": False, "message": "Kein aktives Turnier gefunden."}), 400
    
    # Prüfe, ob das Turnier bereits beendet wurde
    tournament_ended = check_tournament_status(tournament_id)
    
    if tournament_ended:
        # Wenn das Turnier bereits beendet ist, gebe eine Fehlermeldung zurück
        return jsonify({"success": False, "message": "Das Turnier wurde bereits beendet."}), 400

    print("\n\n=== SAVE_RESULTS AUFGERUFEN ===")
    print(f"Tournament ID: {tournament_id}")
    
    # Formular-Daten holen
    table = request.form.get("table")
    player1 = request.form.get("player1")
    player2 = request.form.get("player2")
    score1 = request.form.get("score1", "0")
    score2 = request.form.get("score2", "0")
    score_draws = request.form.get("score_draws", "0")  # Neues Feld für Unentschieden
    current_round = request.form.get("current_round", "1")
    dropout1 = request.form.get("dropout1") == "true"
    dropout2 = request.form.get("dropout2") == "true"
    table_size = request.form.get("table_size", "6")  # Standardwert 6, falls nicht angegeben
    
    # Prüfe auf Power Nine Daten
    player1_power_nine = request.form.get("player1_power_nine")
    player2_power_nine = request.form.get("player2_power_nine")
    player1_name = request.form.get("player1_name")
    player2_name = request.form.get("player2_name")
    
    print(f"Daten aus Formular: Tisch {table}, {player1} vs {player2}, Ergebnis: {score1}-{score2}-{score_draws}, Tischgrösse: {table_size}, Runde: {current_round}")
    print(f"Dropout1: {dropout1}, Dropout2: {dropout2}")
    
    # Verarbeite Power Nine Daten, falls vorhanden
    if player1_power_nine and player1_name:
        try:
            power_nine_data = json.loads(player1_power_nine)
            print(f"Power Nine Daten für {player1_name} empfangen: {power_nine_data}")
            update_tournament_power_nine(tournament_id, player1_name, power_nine_data)
            
            # Aktualisiere auch die globalen Statistiken für den Spieler
            from .player_stats import update_player_power_nine
            update_player_power_nine(player1_name, power_nine_data)
        except Exception as e:
            print(f"Fehler bei der Verarbeitung der Power Nine Daten für {player1_name}: {e}")
    
    if player2_power_nine and player2_name and player2_name != "BYE":
        try:
            power_nine_data = json.loads(player2_power_nine)
            print(f"Power Nine Daten für {player2_name} empfangen: {power_nine_data}")
            update_tournament_power_nine(tournament_id, player2_name, power_nine_data)
            
            # Aktualisiere auch die globalen Statistiken für den Spieler
            from .player_stats import update_player_power_nine
            update_player_power_nine(player2_name, power_nine_data)
        except Exception as e:
            print(f"Fehler bei der Verarbeitung der Power Nine Daten für {player2_name}: {e}")
    
    # In results.csv speichern
    results_file = os.path.join("tournament_data", "results.csv")
    os.makedirs("tournament_data", exist_ok=True)
    file_exists = os.path.isfile(results_file)
    
    try:
        with open(results_file, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow(["Tournament", "Timestamp", "Table", "Player 1", "Score 1", "Player 2", "Score 2", "Draws"])
            writer.writerow([tournament_id, datetime.now().isoformat(), table, player1, score1, player2, score2, score_draws])
        print(f"Ergebnis in results.csv gespeichert")
    except Exception as e:
        print(f"Fehler beim Speichern in results.csv: {e}")
        return jsonify({"success": False, "message": f"Fehler beim Speichern der Ergebnisse: {str(e)}"}), 500

    
    # In Rundendatei aktualisieren
    try:
        data_dir = os.path.join("data", tournament_id)
        rounds_dir = os.path.join(data_dir, "rounds")
        round_file = os.path.join(rounds_dir, f"round_{current_round}.csv")
        
        print(f"Versuche, Ergebnis in {round_file} zu aktualisieren")
        
        if not os.path.exists(round_file):
            print(f"FEHLER: Rundendatei existiert nicht: {round_file}")
            return jsonify({"success": False, "message": f"Rundendatei existiert nicht: {round_file}"}), 404
        
        # Datei lesen
        matches = []
        fieldnames = []
        try:
            with open(round_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                print(f"Feldnamen in CSV: {fieldnames}")
                
                # Stelle sicher, dass alle benötigten Felder in fieldnames sind
                required_fields = ['table', 'player1', 'player2', 'score1', 'score2', 'score_draws', 'table_size', 
                                  'dropout1', 'dropout2', 'display_player1', 'display_player2', 'group_key']
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
            return jsonify({"success": False, "message": f"Fehler beim Lesen der Rundendatei: {str(e)}"}), 500
        
        # Match finden und aktualisieren
        match_found = False
        match_data = None
        for match in matches:
            print(f"Vergleiche Match: Tisch {match.get('table', 'unbekannt')} mit {table}")
            if str(match.get("table", "")) == str(table):
                print(f"Tisch gefunden! Spieler: {match.get('player1', '')} vs {match.get('player2', '')}")
                
                # Aktualisiere alle relevanten Werte
                match["score1"] = score1
                match["score2"] = score2
                match["score_draws"] = score_draws  # Neues Feld für Unentschieden
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
                match_data = match.copy()
                print(f"Match aktualisiert: {match}")
                break
        
        if not match_found:
            print(f"WARNUNG: Kein passendes Match für Tisch {table} gefunden!")
            return jsonify({"success": False, "message": f"Kein Match für Tisch {table} gefunden."}), 404
        
        # Debug-Ausgabe aller zu speichernder Matches
        print("\nAlle Matches, die gespeichert werden:")
        for i, match in enumerate(matches):
            table_size_value = match.get("table_size", "nicht gesetzt")
            print(f"Match {i+1}: Tisch {match.get('table', '')}, {match.get('player1', '')} vs {match.get('player2', '')}, Score: {match.get('score1', '')}-{match.get('score2', '')}-{match.get('score_draws', '0')}, Tischgrösse: {table_size_value}")
        
        # Datei zurückschreiben
        try:
            with open(round_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(matches)
            print(f"Rundendatei erfolgreich aktualisiert")
        except Exception as e:
            print(f"Fehler beim Schreiben der Rundendatei: {e}")
            return jsonify({"success": False, "message": f"Fehler beim Schreiben der Rundendatei: {str(e)}"}), 500
    except Exception as e:
        import traceback
        print(f"Allgemeiner Fehler bei Rundendatei: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": f"Allgemeiner Fehler: {str(e)}"}), 500
    
    # Erfolgsantwort mit aktualisierten Matchdaten zurückgeben
    response_data = {
        "success": True,
        "message": "Ergebnis erfolgreich gespeichert",
        "match": {
            "table": table,
            "player1": player1,
            "player2": player2,
            "score1": score1,
            "score2": score2,
            "score_draws": score_draws,
            "dropout1": "true" if dropout1 else "false",
            "dropout2": "true" if dropout2 else "false",
            "display_player1": match_data.get("display_player1", player1) if match_data else player1,
            "display_player2": match_data.get("display_player2", player2) if match_data else player2
        }
    }
    
    # Zurück zur Rundenansicht (für nicht-Ajax Anfragen als Fallback)
    print(f"Ergebnis erfolgreich gespeichert, JSON-Antwort wird gesendet")
    return jsonify(response_data)

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
                
                # Unentschieden berücksichtigen, falls vorhanden
                draws = 0
                if "Draws" in row and row["Draws"]:
                    draws = int(row["Draws"])
                
                # Game Wins und Draws berechnen
                stats[p1]['game_wins'] += s1
                stats[p1]['game_losses'] += s2
                stats[p1]['game_draws'] += draws
                stats[p2]['game_wins'] += s2
                stats[p2]['game_losses'] += s1
                stats[p2]['game_draws'] += draws
                
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
                    # Bei Gleichstand als Unentschieden werten
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
    
    # Prüfe, ob das Turnier bereits beendet wurde - konsistente Prüfung
    tournament_ended = check_tournament_status(tournament_id)
    
    if tournament_ended:
        # Wenn das Turnier bereits beendet ist, leite zur letzten Runde um
        data_dir = os.path.join("data", tournament_id)
        rounds_dir = os.path.join(data_dir, "rounds")
        if os.path.exists(rounds_dir):
            total_rounds = len([f for f in os.listdir(rounds_dir) if f.startswith("round_") and f.endswith(".csv")])
            return redirect(url_for("main.show_round", round_number=total_rounds))
        else:
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
    for group_key, group_players in player_groups.items():
        # Extrahiere die Tischgröße aus dem zusammengesetzten Schlüssel
        table_size = group_key.split('-')[0]
        
        # Entferne markierte Spieler aus der aktiven Liste
        active_players = [p for p in group_players if not is_player_marked(p)]
        print(f"Aktive Spieler in Gruppe {group_key}: {active_players}")
        
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
                "score_draws": "0",  # Keine Unentschieden bei BYE-Matches
                "table_size": table_size,
                "group_key": group_key  # Speichere den zusammengesetzten Schlüssel
            })
            table_nr += 1
            print(f"BYE-Match: {bye_player} vs BYE mit automatischem Ergebnis 2:0:0")
        
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
                    "score_draws": "",  # Leeres Feld für Unentschieden
                    "table_size": table_size,
                    "group_key": group_key  # Speichere den zusammengesetzten Schlüssel
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
                
        # Verwende erweiterte Feldliste mit display_player Feldern und group_key
        writer = csv.DictWriter(f, fieldnames=['table', 'player1', 'player2', 'score1', 'score2', 'score_draws', 'table_size', 'group_key', 'display_player1', 'display_player2'])
        writer.writeheader()
        writer.writerows(match_list)

    # Speichere die BYE Matches in der results.csv
    results_file = os.path.join("tournament_data", "results.csv")
    file_exists = os.path.isfile(results_file)
    
    with open(results_file, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["Tournament", "Timestamp", "Table", "Player 1", "Score 1", "Player 2", "Score 2", "Draws"])
        
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
                    "0",
                    "0"   # Keine Unentschieden bei BYE
                ])

    # Leite zur show_round Route weiter
    return redirect(url_for('main.show_round', round_number=next_round_number))

@main.route("/start_tournament", methods=["GET"])
def start_tournament():
    # Vollständiges Zurücksetzen - vor dem Zugriff auf alte Turnier-ID
    session.clear()
    
    # Generiere eine neue Turnier-ID
    new_tournament_id = str(uuid.uuid4())
    session["tournament_id"] = new_tournament_id
    
    # Explizit die Liste der markierten Spieler zurücksetzen
    session["leg_players_set"] = []
    
    # Explizit den Turnierstatus zurücksetzen
    session["tournament_ended"] = False
    
    # Erstelle ein neues Datenverzeichnis für das Turnier
    data_dir = os.path.join("data", new_tournament_id)
    os.makedirs(data_dir, exist_ok=True)
    
    # Lösche die end_time.txt aus dem neuen Verzeichnis, falls sie durch einen
    # Race Condition bereits existieren sollte (unwahrscheinlich, aber sicher ist sicher)
    end_time_file = os.path.join(data_dir, "end_time.txt")
    if os.path.exists(end_time_file):
        try:
            os.remove(end_time_file)
            print(f"Unerwartete end_time.txt für neues Turnier {new_tournament_id} gelöscht")
        except Exception as e:
            print(f"Fehler beim Löschen einer unerwarteten end_time.txt: {e}")
    
    # Leere tournament_power_nine.json Datei erstellen
    power_nine_file = os.path.join(data_dir, "tournament_power_nine.json")
    with open(power_nine_file, 'w', encoding='utf-8') as f:
        json.dump({}, f)
    
    print(f"Neues Turnier mit ID {new_tournament_id} wurde erfolgreich gestartet")
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
        ogw = calculate_opponents_game_win_percentage(player, stats)
        
        # Formatiere das Ergebnis als Match-Ergebnisse (Wins-Losses-Draws)
        # Verwende die Match-Siege und -Niederlagen statt der Spielergebnisse
        if player_stats['draws'] > 0:
            game_score = f"{player_stats['wins']} - {player_stats['losses']} - {player_stats['draws']}"
        else:
            game_score = f"{player_stats['wins']} - {player_stats['losses']}"
            
        leaderboard.append((
            player,
            player_stats['points'],
            game_score,  # Format: Match-Wins - Match-Losses - Match-Draws
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
        "player_groups": player_groups,
        "is_ended": True  # Markiere das Turnier als beendet
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
    
    # Speichere den Status des Turniers in der Session
    # Entferne nicht die tournament_id, damit der Benutzer zurückkehren kann
    session["tournament_ended"] = True
    
    # Erstelle eine end_time.txt-Datei im Turnierverzeichnis für konsistente Endstatus-Prüfung
    end_time_file = os.path.join(data_dir, "end_time.txt")
    with open(end_time_file, "w", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%d.%m.%Y %H:%M"))
    
    return render_template(
        "tournament_end.html",
        tournament_data=tournament_data,
        leaderboard=final_leaderboard
    )

@main.route("/round/<int:round_number>")
def show_round(round_number):
    """Zeigt die Paarungen und Ergebnisse für eine bestimmte Runde an"""
    tournament_id = session.get('tournament_id')
    
    # Parameter für konsistente Turnierstatusmarkierung
    ensure_marked_as_ended = request.args.get('ensure_marked_as_ended') == 'true'
    
    # Überprüfen, ob ein aktuelles Turnier existiert
    if not tournament_id:
        return redirect(url_for('main.index'))

    data_dir = os.path.join("data", tournament_id)
    
    # Wenn ensure_marked_as_ended=true, stelle sicher, dass die end_time.txt existiert
    if ensure_marked_as_ended:
        end_time_file = os.path.join(data_dir, "end_time.txt")
        if not os.path.exists(end_time_file):
            try:
                with open(end_time_file, "w", encoding="utf-8") as f:
                    f.write(datetime.now().strftime("%d.%m.%Y %H:%M"))
                session["tournament_ended"] = True
                print(f"Turnier {tournament_id} wurde als beendet markiert durch ensure_marked_as_ended Parameter")
            except Exception as e:
                print(f"Fehler beim Erstellen der end_time.txt: {e}")
    
    # Überprüfen, ob die angeforderte Runde gültig ist
    round_file = os.path.join(data_dir, "rounds", f"round_{round_number}.csv")
    if not os.path.exists(round_file):
        # Keine Rundendatei gefunden - zurück zum Index leiten
        flash(f"Runde {round_number} existiert nicht.")
        return redirect(url_for('main.index'))
        
    # Bestimme die maximale Rundenzahl
    total_rounds = 0
    rounds_dir = os.path.join(data_dir, "rounds")
    if os.path.exists(rounds_dir):
        for filename in os.listdir(rounds_dir):
            if filename.startswith("round_") and filename.endswith(".csv"):
                round_num = int(filename.strip("round_").strip(".csv"))
                total_rounds = max(total_rounds, round_num)
    
    # Lade die aktuellen Rundendaten
    matches = []
    with open(round_file, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            # Setze Standardwerte für Felder, falls sie nicht existieren
            if 'player1' not in row or 'player2' not in row:
                continue
            
            # Transformiere Rohdaten in ein passendes Format für unser Template
            match = {
                'player1': row['player1'],
                'player2': row['player2'],
                'table': row.get('table', ''),
                'score1': row.get('score1', '0'),
                'score2': row.get('score2', '0'),
                'score_draws': row.get('score_draws', '0'),
                'dropout1': row.get('dropout1', 'false'),
                'dropout2': row.get('dropout2', 'false'),
                'table_size': row.get('table_size', ''),
                'group_key': row.get('group_key', row.get('table_size', '')),
                'display_player1': row['player1'],
                'display_player2': row['player2'],
            }
            
            # Füge 🦵-Symbol für markierte Spieler hinzu
            if row.get('dropout1', 'false') == 'true' and '🦵' not in match['display_player1']:
                match['display_player1'] += ' 🦵'
            if row.get('dropout2', 'false') == 'true' and '🦵' not in match['display_player2']:
                match['display_player2'] += ' 🦵'
                
            matches.append(match)
    
    # Lade das Leaderboard für das Turnier bis zu dieser Runde
    leaderboard = calculate_leaderboard(tournament_id, round_number)
    
    # Prüfe, ob das Turnier beendet ist - zweifache Prüfung für Konsistenz
    tournament_ended = check_tournament_status(tournament_id)
    
    # Lade Spielerdaten für Power Nine
    from .player_stats import POWER_NINE
    
    # Lade die turnierspezifischen Power Nine Daten anstelle der globalen Daten
    all_players_data = {}
    tournament_power_nine = get_tournament_power_nine(tournament_id)
    
    # Erstelle ein Dictionary mit den Spielerdaten für das Template
    for match in matches:
        player1 = match['player1']
        player2 = match['player2']
        
        # Füge Spieler 1 hinzu, falls noch nicht vorhanden
        if player1 not in all_players_data:
            all_players_data[player1] = {
                'power_nine': tournament_power_nine.get(player1, {})
            }
            # Stelle sicher, dass alle Power Nine Karten vorhanden sind
            for card in POWER_NINE:
                if card not in all_players_data[player1]['power_nine']:
                    all_players_data[player1]['power_nine'][card] = False
        
        # Füge Spieler 2 hinzu, falls noch nicht vorhanden und kein BYE
        if player2 != "BYE" and player2 not in all_players_data:
            all_players_data[player2] = {
                'power_nine': tournament_power_nine.get(player2, {})
            }
            # Stelle sicher, dass alle Power Nine Karten vorhanden sind
            for card in POWER_NINE:
                if card not in all_players_data[player2]['power_nine']:
                    all_players_data[player2]['power_nine'][card] = False
    
    return render_template(
        'pair.html',
        tournament_id=tournament_id,
        matches=matches,
        current_round=round_number,
        total_rounds=total_rounds,
        leaderboard=leaderboard,
        tournament_ended=tournament_ended,
        all_players_data=all_players_data
    )

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
        # Match Win Percentage berechnen: Siege / (Siege + Niederlagen)
        # Unentschieden sind im Zähler nicht enthalten, aber im Nenner
        total_matches = opponent_stats['wins'] + opponent_stats['losses'] + opponent_stats['draws']
        if total_matches > 0:
            win_percentage = opponent_stats['wins'] / total_matches
        else:
            win_percentage = 0.0
        
        # In den MTG-Turnierregeln gilt ein Minimum von 33.33% (1/3) für OMW
        win_percentage = max(win_percentage, 1/3)
        
        total_win_percentage += win_percentage
    
    return total_win_percentage / len(opponents) if opponents else 0.0

def calculate_game_win_percentage(player_stats):
    """Berechnet den GW% (Game Win Percentage) für einen Spieler."""
    # Zähle die totalen Spiele
    total_games = player_stats['total_wins'] + player_stats['total_losses'] + player_stats['total_draws']
    if total_games == 0:
        return 0.0
    
    # Berechne Game Win Percentage: (Siege) / (Gesamtzahl aller Spiele)
    # Unentschieden zählen nur im Nenner mit
    return player_stats['total_wins'] / total_games

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
        total_games = opponent_stats['total_wins'] + opponent_stats['total_losses'] + opponent_stats['total_draws']
        if total_games > 0:
            game_win_percentage = opponent_stats['total_wins'] / total_games
        else:
            game_win_percentage = 0.0
        
        # Minimum von 33.33% für Game Win Percentage
        game_win_percentage = max(game_win_percentage, 1/3)
        
        total_game_win_percentage += game_win_percentage
    
    return total_game_win_percentage / len(opponents) if opponents else 0.0

def calculate_leaderboard(tournament_id, up_to_round):
    """Berechnet den Leaderboard basierend auf den Ergebnissen bis zur angegebenen Runde."""
    data_dir = os.path.join("data", tournament_id)
    stats = defaultdict(lambda: {'points': 0, 'matches': 0, 'wins': 0, 'losses': 0, 'draws': 0, 'opponents': [], 'total_wins': 0, 'total_losses': 0, 'total_draws': 0})
    
    # Debug-Ausgabe
    print(f"Berechne Leaderboard für Turnier {tournament_id} bis Runde {up_to_round}")
    
    # Gehe durch alle Runden bis zur angegebenen Runde
    for round_num in range(1, up_to_round + 1):
        round_file = os.path.join(data_dir, "rounds", f"round_{round_num}.csv")
        if os.path.exists(round_file):
            print(f"Verarbeite Runde {round_num}")
            try:
                with open(round_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for match in reader:
                        player1 = match["player1"]
                        player2 = match["player2"]
                        
                        # Wenn es ein BYE Match ist, bekommt der aktive Spieler 2 Siege
                        if player2 == "BYE":
                            score1 = 2
                            score2 = 0
                            score_draws = 0
                        # Nur wenn beide Scores eingetragen sind
                        elif match["score1"] and match["score2"]:
                            score1 = int(match["score1"])
                            score2 = int(match["score2"])
                            
                            # Unentschieden berücksichtigen, falls vorhanden
                            score_draws = 0
                            if "score_draws" in match and match["score_draws"]:
                                score_draws = int(match["score_draws"])
                        else:
                            continue  # Überspringe Matches ohne Ergebnis
                            
                        # Debug-Ausgabe
                        print(f"  Match: {player1} vs {player2}, Ergebnis: {score1}-{score2}-{score_draws}")
                        
                        # Aktualisiere die Gegner-Listen
                        if player2 != "BYE":
                            stats[player1]['opponents'].append(player2)
                            stats[player2]['opponents'].append(player1)
                        else:
                            # Bei BYE nur für Spieler 1 einen Gegner hinzufügen
                            stats[player1]['opponents'].append(player2)
                        
                        # Aktualisiere die Statistiken für beide Spieler
                        if score1 > score2:
                            stats[player1]['points'] += 3  # 3 Punkte für Sieg
                            stats[player1]['wins'] += 1
                            stats[player2]['losses'] += 1
                        elif score2 > score1:
                            stats[player2]['points'] += 3  # 3 Punkte für Sieg
                            stats[player2]['wins'] += 1
                            stats[player1]['losses'] += 1
                        else:
                            # Bei Gleichstand als Unentschieden werten
                            stats[player1]['points'] += 1  # 1 Punkt für Unentschieden
                            stats[player2]['points'] += 1  # 1 Punkt für Unentschieden
                            stats[player1]['draws'] += 1
                            stats[player2]['draws'] += 1
                        
                        # Aktualisiere die Gesamtsiege, -niederlagen und -unentschieden
                        stats[player1]['total_wins'] += score1
                        stats[player1]['total_losses'] += score2
                        stats[player1]['total_draws'] += score_draws
                        stats[player2]['total_wins'] += score2
                        stats[player2]['total_losses'] += score1
                        stats[player2]['total_draws'] += score_draws
                        
                        stats[player1]['matches'] += 1
                        stats[player2]['matches'] += 1
            except (IOError, OSError) as e:
                print(f"Fehler beim Lesen der Runde {round_num}: {e}")
        else:
            print(f"Runde {round_num} nicht gefunden")

    # Debug-Ausgabe der Statistiken
    for player, player_stats in stats.items():
        print(f"Spieler: {player}, Punkte: {player_stats['points']}, Siege: {player_stats['wins']}, Niederlagen: {player_stats['losses']}, Unentschieden: {player_stats['draws']}")

    # Erstelle den Leaderboard
    leaderboard = []
    for player, player_stats in stats.items():
        omw = calculate_opponents_match_percentage(player, stats)
        gw = calculate_game_win_percentage(player_stats)
        ogw = calculate_opponents_game_win_percentage(player, stats)
        
        # Formatiere das Ergebnis als Match-Ergebnisse (Wins-Losses-Draws)
        # Verwende die Match-Siege und -Niederlagen statt der Spielergebnisse
        if player_stats['draws'] > 0:
            game_score = f"{player_stats['wins']} - {player_stats['losses']} - {player_stats['draws']}"
        else:
            game_score = f"{player_stats['wins']} - {player_stats['losses']}"
            
        leaderboard.append((
            player,
            player_stats['points'],
            game_score,  # Format: Match-Wins - Match-Losses - Match-Draws
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

@main.route("/delete_tournament/<tournament_id>", methods=["POST"])
def delete_tournament(tournament_id):
    """Löscht die Daten eines vergangenen Turniers"""
    # Pfade zu den Turnierdaten
    tournament_results_dir = "tournament_results"
    results_file = os.path.join(tournament_results_dir, f"{tournament_id}_results.json")
    
    # Prüfe, ob das Turnier existiert
    if not os.path.exists(results_file):
        return jsonify({"success": False, "message": "Turnier nicht gefunden"}), 404
    
    try:
        # Lösche die Turnierdatei
        os.remove(results_file)
        
        # Lösche auch die zugehörigen Daten im data-Verzeichnis
        data_dir = os.path.join("data", tournament_id)
        if os.path.exists(data_dir) and os.path.isdir(data_dir):
            import shutil
            shutil.rmtree(data_dir)
        
        return jsonify({"success": True, "message": "Turnier erfolgreich gelöscht"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Fehler beim Löschen: {str(e)}"}), 500

@main.route("/players")
def players_list():
    """Zeigt eine Übersichtsseite mit allen Spielern"""
    # Importiere das player_stats Modul
    from .player_stats import get_all_players, load_player_data, get_player_statistics
    
    # Sammle alle Spieler
    all_players = get_all_players()
    
    # Bereite die Spielerdaten für die Anzeige vor
    players_data = {}
    for player in all_players:
        # Überspringe gelöschte Spieler
        if player == "DELETED_PLAYER":
            continue
            
        # Lade Spielerdaten und Statistiken
        player_data = load_player_data(player)
        player_stats = get_player_statistics(player)
        
        # Verwende die neue Gesamtzahl der Power Nine Karten aus den Statistiken
        power_nine_count = player_stats.get("power_nine_total", 0)
        
        # Speichere strukturierte Daten für die Anzeige
        players_data[player] = {
            "power_nine_count": power_nine_count,
            "tournaments_played": player_stats.get("tournaments_played", 0),
            "match_win_percentage": player_stats.get("match_win_percentage", 0),
            "total_matches": player_stats.get("total_matches", 0)
        }
    
    # Sortiere die Spieler nach Gewinnrate (absteigend)
    sorted_players = dict(sorted(
        players_data.items(), 
        key=lambda item: item[1]["match_win_percentage"], 
        reverse=True
    ))
    
    return render_template(
        "players_list.html",
        players=sorted_players
    )

@main.route("/player/<player_name>")
def player_profile(player_name):
    """Zeigt das Profil eines Spielers an"""
    # Verhindere Zugriff auf gelöschte Spieler
    if player_name == "DELETED_PLAYER":
        flash("Dieser Spieler existiert nicht mehr.")
        return redirect(url_for('main.players_list'))
    
    # Importiere das player_stats Modul
    from .player_stats import load_player_data, get_player_statistics, POWER_NINE
    
    # Lade Spielerdaten
    player_data = load_player_data(player_name)
    player_stats = get_player_statistics(player_name)
    
    return render_template(
        "player_profile.html",
        player_name=player_name,
        player_data=player_data,
        player_stats=player_stats,
        power_nine=POWER_NINE
    )

@main.route("/player/<player_name>/delete", methods=["POST"])
def delete_player(player_name):
    """Löscht einen Spieler aus allen Daten"""
    # Importiere das player_stats Modul
    from .player_stats import delete_player, get_players_data_path, load_all_players_data
    
    # Debug-Logs
    print(f"Versuche Spieler '{player_name}' aus allen Daten zu löschen")
    print(f"Spielerdaten-Datei: {get_players_data_path()}")
    players_data = load_all_players_data()
    print(f"Vorhandene Spieler in players_data.json: {list(players_data.keys())}")
    
    # Lösche den Spieler aus allen Daten
    success = delete_player(player_name)
    
    if success:
        # Zeige Erfolgsmeldung an
        return jsonify({"success": True, "message": f"Spieler {player_name} wurde erfolgreich aus allen Daten entfernt"})
    else:
        # Zeige Fehlermeldung an
        return jsonify({"success": False, "message": f"Es gab ein Problem beim Löschen des Spielers {player_name}. Bitte überprüfen Sie die Logs."})

@main.route("/api/player/<player_name>/power_nine", methods=["GET"])
def get_player_power_nine(player_name):
    """API-Route zum Abrufen der Power Nine Karten eines Spielers im aktuellen Turnier"""
    # Importiere die POWER_NINE-Konstante
    from .player_stats import POWER_NINE
    
    # Hole die aktuelle Turnier-ID aus der Session
    tournament_id = session.get("tournament_id")
    if not tournament_id:
        # Wenn kein Turnier aktiv ist, gib leere Power Nine Daten zurück
        return jsonify({
            "success": True,
            "player_name": player_name,
            "power_nine": {card: False for card in POWER_NINE}
        })
    
    # Lade die turnierspezifischen Power Nine Daten
    tournament_power_nine = get_tournament_power_nine(tournament_id)
    
    # Hole die Power Nine Daten für den Spieler im aktuellen Turnier
    # oder gib ein leeres Dictionary zurück, wenn keine Daten vorhanden sind
    power_nine = tournament_power_nine.get(player_name, {})
    
    # Stelle sicher, dass alle Power Nine Karten im Dictionary enthalten sind
    for card in POWER_NINE:
        if card not in power_nine:
            power_nine[card] = False
    
    return jsonify({
        "success": True,
        "player_name": player_name,
        "power_nine": power_nine
    })

@main.route("/api/player/<player_name>/power_nine", methods=["POST"])
def update_player_power_nine_api(player_name):
    """API-Route zum Aktualisieren der Power Nine Karten eines Spielers"""
    # Importiere das player_stats Modul
    from .player_stats import update_player_power_nine, POWER_NINE
    
    # Hole die Power Nine Daten aus dem Request
    power_nine_data = request.json
    
    if not power_nine_data:
        return jsonify({
            "success": False,
            "message": "Keine Power Nine Daten im Request."
        })
    
    # Hole die aktuelle Turnier-ID aus der Session
    tournament_id = session.get("tournament_id")
    if not tournament_id:
        return jsonify({
            "success": False,
            "message": "Kein aktives Turnier gefunden."
        })
    
    # Aktualisiere die Power Nine Daten für das aktuelle Turnier
    success = update_tournament_power_nine(tournament_id, player_name, power_nine_data)
    
    if success:
        # Aktualisiere auch die globalen Statistiken für den Spieler
        # Dies addiert die Power Nine Karten zu den Gesamtstatistiken
        update_player_power_nine(player_name, power_nine_data)
        
        return jsonify({
            "success": True,
            "message": f"Power Nine Karten für {player_name} wurden aktualisiert."
        })
    else:
        return jsonify({
            "success": False,
            "message": f"Fehler beim Aktualisieren der Power Nine Karten für {player_name}."
        })

def update_tournament_power_nine(tournament_id, player_name, power_nine_data):
    """
    Aktualisiert die Power Nine Karten eines Spielers für ein bestimmtes Turnier.
    Diese Funktion speichert die Daten in einer tournament_power_nine.json Datei
    im Datenverzeichnis des Turniers.
    """
    try:
        data_dir = os.path.join("data", tournament_id)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
        
        # Dateiname für die Power Nine Daten des Turniers
        power_nine_file = os.path.join(data_dir, "tournament_power_nine.json")
        
        # Lade die bestehenden Daten oder erstelle ein neues Dictionary
        tournament_power_nine = {}
        if os.path.exists(power_nine_file):
            with open(power_nine_file, 'r', encoding='utf-8') as f:
                tournament_power_nine = json.load(f)
        
        # Aktualisiere die Daten für den Spieler
        tournament_power_nine[player_name] = power_nine_data
        
        # Speichere die Daten zurück in die Datei
        with open(power_nine_file, 'w', encoding='utf-8') as f:
            json.dump(tournament_power_nine, f, indent=2)
        
        return True
    except Exception as e:
        print(f"Fehler beim Aktualisieren der Power Nine Daten für Turnier {tournament_id}, Spieler {player_name}: {e}")
        return False

def get_tournament_power_nine(tournament_id):
    """
    Holt die Power Nine Karten für alle Spieler in einem bestimmten Turnier.
    """
    try:
        data_dir = os.path.join("data", tournament_id)
        power_nine_file = os.path.join(data_dir, "tournament_power_nine.json")
        
        if os.path.exists(power_nine_file):
            with open(power_nine_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Wenn keine Datei existiert, gib ein leeres Dictionary zurück
        return {}
    except Exception as e:
        print(f"Fehler beim Laden der Power Nine Daten für Turnier {tournament_id}: {e}")
        return {}

def check_tournament_status(tournament_id):
    """
    Überprüft konsistent den Status eines Turniers (beendet oder nicht).
    
    Diese Funktion führt eine zweifache Prüfung durch:
    1. Prüft den Session-Status (session["tournament_ended"])
    2. Prüft, ob die end_time.txt Datei existiert
    
    Bei Inkonsistenzen wird die Session aktualisiert.
    
    Args:
        tournament_id: Die ID des zu prüfenden Turniers
        
    Returns:
        bool: True wenn das Turnier beendet ist, False sonst
    """
    if not tournament_id:
        return False
    
    # Prüfe Session-Variable
    session_tournament_ended = session.get("tournament_ended", False)
    
    # Prüfe Datei
    data_dir = os.path.join("data", tournament_id)
    end_time_file = os.path.join(data_dir, "end_time.txt")
    file_tournament_ended = os.path.exists(end_time_file)
    
    # Verwende BEIDE Statusprüfungen - wenn EINER True ist, ist das Turnier beendet
    tournament_ended = session_tournament_ended or file_tournament_ended
    
    # Stelle sicher, dass Session und Datei konsistent sind
    if session_tournament_ended != file_tournament_ended:
        session["tournament_ended"] = tournament_ended
        print(f"Warnung: Inkonsistenter Turnierstatus korrigiert - Session: {session_tournament_ended}, Datei: {file_tournament_ended}, Final: {tournament_ended}")
    
    return tournament_ended