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

main = Blueprint('main', __name__)

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
        allowed_sizes: Liste der erlaubten Tischgrößen
    
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
        
        # Probiere jede erlaubte Tischgröße
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

    players = request.form.getlist("players")
    group_sizes = request.form.getlist("group_sizes")
    
    try:
        # Konvertiere Gruppengrößen zu Integers und validiere sie
        allowed_sizes = [int(size) for size in group_sizes]
        if not allowed_sizes:
            return render_template("index.html", 
                                error="Bitte wählen Sie mindestens eine Tischgröße aus.",
                                players_text="\n".join(players))
        
        # Finde mögliche Gruppierungen
        groupings = find_all_valid_groupings(len(players), allowed_sizes)
        
        if not groupings:
            return render_template("index.html", 
                                error=f"Keine gültige Gruppierung für {len(players)} Spieler mit den Tischgrößen {allowed_sizes} möglich.",
                                players_text="\n".join(players))
        
        # Wähle die erste gültige Gruppierung
        selected_grouping = groupings[0]
        
        # Mische die Spieler
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
            player_groups[str(group_size)] = group_players  # Speichere als String-Key
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

    player1_list = request.form.getlist("player1")
    player2_list = request.form.getlist("player2")
    table_list = request.form.getlist("table")
    score1_list = request.form.getlist("score1")
    score2_list = request.form.getlist("score2")

    results = zip(table_list, player1_list, player2_list, score1_list, score2_list)
    results_data = list(results)  # Konvertiere zu Liste für mehrfache Verwendung
    
    # Validierung der Ergebnisse
    for _, _, _, s1, s2 in results_data:
        try:
            score1 = int(s1)
            score2 = int(s2)
            if score1 < 0 or score2 < 0:
                return "<h2>Fehler: Negative Punktzahlen sind nicht erlaubt!</h2><p><a href='/'>Zurück</a></p>"
        except ValueError:
            return "<h2>Fehler: Ungültige Punktzahlen!</h2><p><a href='/'>Zurück</a></p>"

    # Stelle sicher, dass das Verzeichnis existiert
    if not ensure_data_directory():
        return "<h2>Fehler: Konnte Datenverzeichnis nicht erstellen!</h2><p><a href='/'>Zurück</a></p>"

    results_file = os.path.join("tournament_data", "results.csv")
    file_exists = os.path.isfile(results_file)

    try:
        with open(results_file, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow(["Tournament", "Timestamp", "Table", "Player 1", "Score 1", "Player 2", "Score 2"])

            for table, p1, p2, s1, s2 in results_data:
                writer.writerow([tournament_id, datetime.now().isoformat(), table, p1, s1, p2, s2])
    except (IOError, OSError) as e:
        return f"<h2>Fehler beim Speichern: {str(e)}</h2><p><a href='/'>Zurück</a></p>"

    return "<h2>Resultate gespeichert!</h2><p><a href='/'>Zurück zur Startseite</a></p>"

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
    for round_num in range(1, current_round):
        round_file = os.path.join(data_dir, "rounds", f"round_{round_num}.csv")
        if os.path.exists(round_file):
            with open(round_file, "r") as f:
                reader = csv.DictReader(f)
                for match in reader:
                    player1 = match["player1"]
                    player2 = match["player2"]
                    opponents[player1].append(player2)
                    opponents[player2].append(player1)
    
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
    
    with open(player_groups_file, 'r') as f:
        player_groups = json.load(f)
    
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
        # Sortiere Spieler dieser Gruppe nach Punkten
        current_group = []
        for player in group_players:
            player_stats = next((p for p in leaderboard if p[0] == player), None)
            if player_stats:
                current_group.append(player_stats)
            else:
                current_group.append((player, 0, "0-0", "0.00%", "0.00%"))
        
        # Sortiere nach Punkten, OMW% und GW%
        current_group.sort(key=lambda x: (
            -int(x[1]),  # Punkte (negativ für absteigende Sortierung)
            -float(x[3].rstrip('%')),  # OMW% (negativ für absteigende Sortierung)
            -float(x[4].rstrip('%')),  # GW% (negativ für absteigende Sortierung)
            x[0]  # Name (aufsteigend)
        ))
        sorted_players = [p[0] for p in current_group]
        
        # Erstelle Paarungen für diese Gruppe
        paired = set()
        for i in range(len(sorted_players)):
            if sorted_players[i] in paired:
                continue
                
            # Suche nach passendem Gegner
            opponent_found = False
            for j in range(i + 1, len(sorted_players)):
                if sorted_players[j] in paired:
                    continue
                if sorted_players[j] not in opponents.get(sorted_players[i], []):
                    # Paarung gefunden
                    p1, p2 = sorted_players[i], sorted_players[j]
                    match_list.append({
                        "table": str(table_nr),
                        "player1": p1,
                        "player2": p2,
                        "score1": "",  # Leerer String statt '0'
                        "score2": "",  # Leerer String statt '0'
                        "table_size": group_size
                    })
                    paired.add(p1)
                    paired.add(p2)
                    table_nr += 1
                    opponent_found = True
                    break
            
            # Wenn kein Gegner gefunden wurde und der Spieler noch nicht gepaart ist
            if not opponent_found and sorted_players[i] not in paired:
                # Spieler ohne Gegner wird in die nächste Runde übernommen
                paired.add(sorted_players[i])
                table_nr += 1

    # Speichere die neue Runde
    next_round_number = current_round + 1
    next_round_file = os.path.join(rounds_dir, f'round_{next_round_number}.csv')
    
    with open(next_round_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['table', 'player1', 'player2', 'score1', 'score2', 'table_size'])
        writer.writeheader()
        writer.writerows(match_list)

    # Leite zur show_round Route weiter
    return redirect(url_for('main.show_round', round_number=next_round_number))

@main.route("/start_tournament", methods=["GET"])
def start_tournament():
    session["tournament_id"] = str(uuid.uuid4())
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
        leaderboard.append((
            player,
            player_stats['points'],
            player_stats['match_wins'],
            player_stats['match_losses'],
            tiebreakers[player]['gwp'],
            tiebreakers[player]['omw']
        ))

    # 8. Leaderboard sortieren (Punkte -> OMW% -> GWP% -> Name)
    leaderboard.sort(key=lambda x: (-x[1], -x[5], -x[4], x[0]))

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
    
    # Entferne die Session-Daten
    session.pop("tournament_id", None)
    session.pop("players_text", None)
    
    return render_template(
        "tournament_end.html",
        tournament_data=tournament_data,
        leaderboard=final_leaderboard
    )

@main.route('/show_round/<int:round_number>')
def show_round(round_number):
    try:
        if 'tournament_id' not in session:
            return redirect(url_for('main.index', error="Kein aktives Turnier gefunden"))
        
        tournament_id = session['tournament_id']
        data_dir = os.path.join('data', tournament_id)
        
        if not os.path.exists(data_dir):
            return redirect(url_for('main.index', error="Turnierdaten nicht gefunden"))
        
        # Lade die aktuelle Runde
        rounds_dir = os.path.join(data_dir, 'rounds')
        current_round_file = os.path.join(rounds_dir, f'round_{round_number}.csv')
        if not os.path.exists(current_round_file):
            return redirect(url_for('main.index', error=f"Runde {round_number} nicht gefunden"))
        
        # Lade die Spielergruppen
        player_groups_file = os.path.join(data_dir, 'player_groups.json')
        if not os.path.exists(player_groups_file):
            return redirect(url_for('main.index', error="Spielergruppen nicht gefunden"))
        
        with open(player_groups_file, 'r') as f:
            player_groups = json.load(f)
        
        # Lade die Drop-Out-Informationen
        dropouts = {}
        dropouts_file = os.path.join(data_dir, 'dropouts.json')
        if os.path.exists(dropouts_file):
            with open(dropouts_file, 'r') as f:
                dropouts = json.load(f)
        
        # Lade die Matches der aktuellen Runde
        matches = []
        with open(current_round_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Initialisiere die Dropout-Felder mit 'false'
                dropout1 = 'false'
                dropout2 = 'false'
                
                # Überprüfe, ob die Spieler in der Dropouts-Datei als Drop-Out markiert sind
                if row['player1'] in dropouts and dropouts[row['player1']] is True:
                    dropout1 = 'true'
                if row['player2'] in dropouts and dropouts[row['player2']] is True:
                    dropout2 = 'true'
                
                # Stelle sicher, dass die Dropout-Felder in der CSV-Datei korrekt sind
                if 'dropout1' in row and row['dropout1'] == 'true':
                    dropout1 = 'true'
                if 'dropout2' in row and row['dropout2'] == 'true':
                    dropout2 = 'true'
                
                matches.append({
                    'table': row['table'],
                    'table_size': row['table_size'],
                    'player1': row['player1'],
                    'player2': row['player2'],
                    'score1': row.get('score1'),
                    'score2': row.get('score2'),
                    'dropout1': dropout1,
                    'dropout2': dropout2
                })
        
        # Berechne die Gesamtanzahl der Runden
        total_rounds = len([f for f in os.listdir(rounds_dir) if f.startswith('round_') and f.endswith('.csv')])
        
        # Berechne das Leaderboard
        leaderboard = calculate_leaderboard(tournament_id, round_number)
        
        return render_template('pair.html',
                             matches=matches,
                             player_groups=player_groups,
                             leaderboard=leaderboard,
                             current_round=round_number,
                             total_rounds=total_rounds)
    except Exception as e:
        return redirect(url_for('main.index', error=str(e)))

def calculate_opponents_match_win_percentage(player, stats):
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
        total_matches = opponent_stats['wins'] + opponent_stats['losses']
        if total_matches > 0:
            win_percentage = opponent_stats['wins'] / total_matches
        else:
            win_percentage = 0.0
        total_win_percentage += win_percentage
    
    return total_win_percentage / len(opponents) if opponents else 0.0

def calculate_game_win_percentage(player_stats):
    """Berechnet den GW% (Game Win Percentage) für einen Spieler."""
    total_matches = player_stats['wins'] + player_stats['losses']
    if total_matches == 0:
        return 0.0
    return player_stats['wins'] / total_matches

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
            with open(round_file, "r") as f:
                reader = csv.DictReader(f)
                for match in reader:
                    player1 = match["player1"]
                    player2 = match["player2"]
                    
                    # Nur wenn beide Scores eingetragen sind
                    if match["score1"] and match["score2"]:
                        score1 = int(match["score1"])
                        score2 = int(match["score2"])
                        
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
                        else:  # Unentschieden
                            stats[player1]['points'] += 1
                            stats[player2]['points'] += 1
                        
                        # Aktualisiere die Gesamtsiege und -niederlagen
                        stats[player1]['total_wins'] += score1
                        stats[player1]['total_losses'] += score2
                        stats[player2]['total_wins'] += score2
                        stats[player2]['total_losses'] += score1
                        
                        stats[player1]['matches'] += 1
                        stats[player2]['matches'] += 1
        else:
            print(f"Runde {round_num} nicht gefunden")

    # Debug-Ausgabe der Statistiken
    for player, player_stats in stats.items():
        print(f"Spieler: {player}, Punkte: {player_stats['points']}, Siege: {player_stats['wins']}, Niederlagen: {player_stats['losses']}")

    # Erstelle den Leaderboard
    leaderboard = []
    for player, player_stats in stats.items():
        omw = calculate_opponents_match_win_percentage(player, stats)
        gw = calculate_game_win_percentage(player_stats)
        leaderboard.append((
            player,
            player_stats['points'],
            f"{player_stats['total_wins']} - {player_stats['total_losses']}",  # Gesamtsumme aller Siege und Niederlagen
            f"{omw:.2%}",
            f"{gw:.2%}"
        ))

    # Sortiere nach Punkten, OMW% und GW%
    leaderboard.sort(key=lambda x: (-int(x[1]), -float(x[3].rstrip('%')), -float(x[4].rstrip('%')), x[0]))
    return leaderboard

@main.route('/save_result', methods=['POST'])
def save_result():
    try:
        if 'tournament_id' not in session:
            return redirect(url_for('main.index', error="Kein aktives Turnier gefunden"))
        
        tournament_id = session['tournament_id']
        data_dir = os.path.join('data', tournament_id)
        
        # Stelle sicher, dass das rounds-Verzeichnis existiert
        rounds_dir = os.path.join(data_dir, 'rounds')
        os.makedirs(rounds_dir, exist_ok=True)
        
        # Hole die Formulardaten
        table = request.form.get('table')
        player1 = request.form.get('player1')
        player2 = request.form.get('player2')
        table_size = request.form.get('table_size')
        score1 = request.form.get('score1', '0')
        score2 = request.form.get('score2', '0')
        current_round = request.form.get('current_round', '1')
        dropout1 = request.form.get('dropout1', 'false')
        dropout2 = request.form.get('dropout2', 'false')
        
        # Konvertiere die Scores zu Integers
        try:
            score1 = int(score1)
            score2 = int(score2)
        except ValueError:
            return redirect(url_for('main.show_round', round_number=current_round, error="Ungültige Punktzahl"))
        
        # Lade die aktuelle Runde
        round_file = os.path.join(rounds_dir, f'round_{current_round}.csv')
        if not os.path.exists(round_file):
            return redirect(url_for('main.show_round', round_number=current_round, error="Runde nicht gefunden"))
        
        # Lese die aktuelle Runde
        matches = []
        with open(round_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Stelle sicher, dass die Dropout-Felder existieren
                if 'dropout1' not in row:
                    row['dropout1'] = 'false'
                if 'dropout2' not in row:
                    row['dropout2'] = 'false'
                matches.append(row)
        
        # Aktualisiere das Ergebnis für den entsprechenden Tisch
        for match in matches:
            if match['table'] == table and match['player1'] == player1 and match['player2'] == player2:
                # Wenn ein Spieler als Drop-Out markiert ist, setze automatisch einen 2-0 Sieg für den Gegner
                if dropout1 == 'true':
                    match['score1'] = '0'
                    match['score2'] = '2'
                elif dropout2 == 'true':
                    match['score1'] = '2'
                    match['score2'] = '0'
                else:
                    match['score1'] = str(score1)
                    match['score2'] = str(score2)
                
                match['dropout1'] = dropout1
                match['dropout2'] = dropout2
                break
        
        # Schreibe die aktualisierte Runde zurück
        if matches:  # Prüfe, ob die Liste nicht leer ist
            with open(round_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=matches[0].keys())
                writer.writeheader()
                writer.writerows(matches)
        
        # Speichere die Drop-Out-Informationen in einer separaten Datei
        dropouts_file = os.path.join(data_dir, 'dropouts.json')
        dropouts = {}
        
        # Lade bestehende Drop-Outs, falls vorhanden
        if os.path.exists(dropouts_file):
            with open(dropouts_file, 'r') as f:
                dropouts = json.load(f)
        
        # Aktualisiere die Drop-Out-Informationen
        if dropout1 == 'true':
            dropouts[player1] = True
        else:
            # Nur auf False setzen, wenn der Spieler bereits in der Datei existiert
            if player1 in dropouts:
                dropouts[player1] = False
            
        if dropout2 == 'true':
            dropouts[player2] = True
        else:
            # Nur auf False setzen, wenn der Spieler bereits in der Datei existiert
            if player2 in dropouts:
                dropouts[player2] = False
        
        # Speichere die aktualisierten Drop-Out-Informationen
        with open(dropouts_file, 'w') as f:
            json.dump(dropouts, f)
        
        # Berechne das Leaderboard neu - berücksichtige alle Runden bis zur aktuellen Runde
        leaderboard = calculate_leaderboard(tournament_id, int(current_round))
        
        # Lade die Spielergruppen
        player_groups_file = os.path.join(data_dir, 'player_groups.json')
        with open(player_groups_file, 'r') as f:
            player_groups = json.load(f)
        
        # Berechne die Gesamtanzahl der Runden
        total_rounds = len([f for f in os.listdir(rounds_dir) if f.startswith('round_') and f.endswith('.csv')])
        
        # Zurück zur aktuellen Runde mit allen notwendigen Daten
        return render_template('pair.html',
                             matches=matches,
                             player_groups=player_groups,
                             leaderboard=leaderboard,
                             current_round=int(current_round),
                             total_rounds=total_rounds)
    except Exception as e:
        return redirect(url_for('main.index', error=str(e)))


