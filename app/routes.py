from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
import uuid
import random
import os
import csv
from datetime import datetime
from collections import defaultdict
import json
import unicodedata
from .tournament_groups import (
    DEFAULT_GROUP_ID,
    create_tournament_cube,
    create_tournament_group,
    delete_tournament_cube,
    delete_tournament_group,
    get_cube_name,
    get_group_name,
    get_tournament_cube_id,
    get_tournament_cube_name,
    get_tournament_group_id,
    get_tournament_group_name,
    is_vintage_tournament,
    is_valid_cube_id,
    is_valid_group_id,
    load_allowed_cubes,
    load_tournament_groups,
    reassign_cube_in_meta,
    reassign_group_in_meta,
    rename_tournament_cube,
    rename_tournament_group,
    remove_tournament_group,
    set_tournament_group,
)

main = Blueprint('main', __name__)

def is_valid_tournament_id(value):
    """Nur UUIDs als gültige Turnier-IDs akzeptieren."""
    if not value or not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
        return str(parsed) == value.lower()
    except (ValueError, AttributeError, TypeError):
        return False

def is_player_marked(player_name):
    """Prüft, ob ein Spieler als Dropout markiert ist (anhand der Session)"""
    if not player_name or not isinstance(player_name, str):
        return False
    marked_players = session.get("leg_players_set", [])
    return player_name in marked_players

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

def get_last_tournaments(limit=5, group_filter=None):
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
                group_id = tournament_data.get("tournament_data", {}).get("group_id")
                if not group_id:
                    group_id = get_tournament_group_id(tournament_id)
                tournament_info["group_id"] = group_id
                tournament_info["group_name"] = get_group_name(group_id)
                cube_id = tournament_data.get("tournament_data", {}).get("cube_id")
                cube_name = tournament_data.get("tournament_data", {}).get("cube_name")
                if not is_valid_cube_id(cube_id):
                    cube_id = get_tournament_cube_id(tournament_id)
                if not cube_name:
                    cube_name = get_cube_name(cube_id)
                tournament_info["cube_id"] = cube_id
                tournament_info["cube_name"] = cube_name
                if group_filter and tournament_info["group_id"] != group_filter:
                    continue
                last_tournaments.append(tournament_info)
        except Exception as e:
            print(f"Fehler beim Verarbeiten von {file_path}: {str(e)}")
    
    return last_tournaments

def get_marked_players_for_tournament(tournament_id):
    """
    Rekonstruiert Dropout-Status aus den gespeicherten Runden.
    Dadurch bleibt der Status auch nach Reload/Session-Wechsel konsistent.
    """
    marked_players = set()
    rounds_dir = os.path.join("data", tournament_id, "rounds")
    if not os.path.exists(rounds_dir):
        return []

    round_numbers = []
    for filename in os.listdir(rounds_dir):
        if filename.startswith("round_") and filename.endswith(".csv"):
            try:
                round_numbers.append(int(filename.replace("round_", "").replace(".csv", "")))
            except ValueError:
                continue

    for round_num in sorted(round_numbers):
        round_file = os.path.join(rounds_dir, f"round_{round_num}.csv")
        try:
            with open(round_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    p1 = (row.get("player1") or "").strip()
                    p2 = (row.get("player2") or "").strip()
                    d1 = (row.get("dropout1") or "false").strip().lower() == "true"
                    d2 = (row.get("dropout2") or "false").strip().lower() == "true"

                    if p1:
                        if d1:
                            marked_players.add(p1)
                        else:
                            marked_players.discard(p1)
                    if p2 and p2 != "BYE":
                        if d2:
                            marked_players.add(p2)
                        else:
                            marked_players.discard(p2)
        except (IOError, OSError):
            continue

    return sorted(marked_players)

def get_active_tournaments(limit=10, group_filter=None):
    """Lädt laufende (nicht beendete) Turniere aus dem data-Verzeichnis."""
    data_root = "data"
    results_root = "tournament_results"
    if not os.path.exists(data_root):
        return []

    tournaments = []
    for tournament_id in os.listdir(data_root):
        # Nicht-Turnier-Ordner (z.B. "players") konsequent ignorieren
        if not is_valid_tournament_id(tournament_id):
            continue

        tournament_dir = os.path.join(data_root, tournament_id)
        if not os.path.isdir(tournament_dir):
            continue

        # Beendete Turniere ausblenden
        if os.path.exists(os.path.join(tournament_dir, "end_time.txt")):
            continue
        if os.path.exists(os.path.join(results_root, f"{tournament_id}_results.json")):
            continue

        rounds_dir = os.path.join(tournament_dir, "rounds")
        round_numbers = []
        latest_ts = os.path.getmtime(tournament_dir)
        if os.path.exists(rounds_dir):
            for filename in os.listdir(rounds_dir):
                if filename.startswith("round_") and filename.endswith(".csv"):
                    try:
                        round_numbers.append(int(filename.replace("round_", "").replace(".csv", "")))
                        latest_ts = max(latest_ts, os.path.getmtime(os.path.join(rounds_dir, filename)))
                    except ValueError:
                        continue

        player_count = 0
        player_groups_file = os.path.join(tournament_dir, "player_groups.json")
        if os.path.exists(player_groups_file):
            try:
                with open(player_groups_file, "r", encoding="utf-8") as f:
                    groups = json.load(f)
                    seen = set()
                    for players in groups.values():
                        for p in players:
                            seen.add(p)
                    player_count = len(seen)
            except Exception:
                player_count = 0

        current_round = max(round_numbers) if round_numbers else 0

        # Leere Platzhalter (noch kein Spieler + keine Runde) nicht anzeigen.
        # Diese können entstehen, wenn ein Turnier vorbereitet, aber nie gestartet wurde.
        if current_round == 0 and player_count == 0:
            continue

        tournaments.append({
            "id": tournament_id,
            "current_round": current_round,
            "player_count": player_count,
            "updated_at_ts": latest_ts,
            "is_current_session": session.get("tournament_id") == tournament_id,
            "group_id": get_tournament_group_id(tournament_id),
            "group_name": get_tournament_group_name(tournament_id),
            "cube_id": get_tournament_cube_id(tournament_id),
            "cube_name": get_tournament_cube_name(tournament_id),
        })

    if group_filter:
        tournaments = [t for t in tournaments if t["group_id"] == group_filter]

    tournaments.sort(key=lambda t: t["updated_at_ts"], reverse=True)
    return tournaments[:limit]

def render_index_page(
    players_text="",
    error=None,
    selected_group_id=DEFAULT_GROUP_ID,
    selected_cube="vintage",
    group_filter="all",
):
    from .player_stats import get_all_players

    tournament_groups = load_tournament_groups()
    allowed_cubes = load_allowed_cubes()
    known_player_names = sorted(get_all_players(), key=lambda name: name.casefold())
    allowed_cube_ids = {cube["id"] for cube in allowed_cubes}
    valid_group_ids = {group["id"] for group in tournament_groups}
    if selected_group_id not in valid_group_ids:
        selected_group_id = DEFAULT_GROUP_ID
    if selected_cube not in allowed_cube_ids:
        selected_cube = "vintage"

    normalized_filter = None
    if group_filter and group_filter != "all":
        if group_filter in valid_group_ids:
            normalized_filter = group_filter
        else:
            group_filter = "all"

    last_tournaments = get_last_tournaments(5, group_filter=normalized_filter)
    active_tournaments = get_active_tournaments(10, group_filter=normalized_filter)
    return render_template(
        "index.html",
        players_text=players_text,
        error=error,
        last_tournaments=last_tournaments,
        active_tournaments=active_tournaments,
        tournament_groups=tournament_groups,
        allowed_cubes=allowed_cubes,
        known_player_names=known_player_names,
        selected_group_id=selected_group_id,
        selected_cube=selected_cube,
        selected_group_filter=group_filter or "all",
    )

@main.route("/", methods=["GET"])
def index():
    # Aufräumen nach älteren fehlerhaften States (z.B. session["tournament_id"] = "players")
    current_tournament_id = session.get("tournament_id")
    if current_tournament_id and not is_valid_tournament_id(current_tournament_id):
        session.pop("tournament_id", None)
        session.pop("leg_players_set", None)
        session.pop("tournament_ended", None)

    group_filter = request.args.get("group_filter", "all")
    return render_index_page(players_text="", group_filter=group_filter)


@main.route("/groups", methods=["GET"])
def manage_groups():
    """Zeigt die Gruppenverwaltung an."""
    return render_template(
        "groups.html",
        tournament_groups=load_tournament_groups(),
        default_group_id=DEFAULT_GROUP_ID,
    )


@main.route("/groups/create", methods=["POST"])
def create_group():
    group_name = request.form.get("group_name", "")
    success, message, _ = create_tournament_group(group_name)
    flash(message, "success" if success else "error")
    return redirect(url_for("main.manage_groups"))


@main.route("/groups/rename", methods=["POST"])
def rename_group():
    group_id = request.form.get("group_id", "")
    group_name = request.form.get("group_name", "")
    success, message = rename_tournament_group(group_id, group_name)
    flash(message, "success" if success else "error")
    return redirect(url_for("main.manage_groups"))


@main.route("/groups/delete", methods=["POST"])
def delete_group():
    group_id = request.form.get("group_id", "")
    # Referenzen in Turnier-Metadaten zuerst auf Default setzen.
    reassigned_count = reassign_group_in_meta(group_id, DEFAULT_GROUP_ID)
    success, message = delete_tournament_group(group_id)
    if success and reassigned_count > 0:
        flash(f"{message} {reassigned_count} Turnier(e) wurden auf 'Unkategorisiert' umgestellt.", "success")
    else:
        flash(message, "success" if success else "error")
    return redirect(url_for("main.manage_groups"))


@main.route("/cubes", methods=["GET"])
def manage_cubes():
    """Zeigt die Cube-Verwaltung an."""
    return render_template(
        "cubes.html",
        tournament_cubes=load_allowed_cubes(),
        default_cube_id="vintage",
    )


@main.route("/cubes/create", methods=["POST"])
def create_cube():
    cube_name = request.form.get("cube_name", "")
    success, message, _ = create_tournament_cube(cube_name)
    flash(message, "success" if success else "error")
    return redirect(url_for("main.manage_cubes"))


@main.route("/cubes/rename", methods=["POST"])
def rename_cube():
    cube_id = request.form.get("cube_id", "")
    cube_name = request.form.get("cube_name", "")
    success, message = rename_tournament_cube(cube_id, cube_name)
    flash(message, "success" if success else "error")
    return redirect(url_for("main.manage_cubes"))


@main.route("/cubes/delete", methods=["POST"])
def delete_cube():
    cube_id = request.form.get("cube_id", "")
    # Referenzen in Turnier-Metadaten zuerst auf Vintage setzen.
    reassigned_count = reassign_cube_in_meta(cube_id, "vintage")
    success, message = delete_tournament_cube(cube_id)
    if success and reassigned_count > 0:
        flash(f"{message} {reassigned_count} Turnier(e) wurden auf 'Vintage' umgestellt.", "success")
    else:
        flash(message, "success" if success else "error")
    return redirect(url_for("main.manage_cubes"))

@main.route("/load_tournament/<tournament_id>", methods=["GET"])
def load_tournament(tournament_id):
    """Lädt ein bestehendes Turnier in die Session und öffnet die letzte Runde."""
    if not is_valid_tournament_id(tournament_id):
        flash("Ungültige Turnier-ID.")
        return redirect(url_for("main.index"))

    data_dir = os.path.join("data", tournament_id)
    rounds_dir = os.path.join(data_dir, "rounds")
    if not os.path.exists(data_dir):
        flash("Turnier wurde nicht gefunden.")
        return redirect(url_for("main.index"))

    session["tournament_id"] = tournament_id
    session["leg_players_set"] = get_marked_players_for_tournament(tournament_id)
    session["tournament_ended"] = check_tournament_status(tournament_id)

    # Stelle sicher, dass Legacy-Turniere beim Laden Cube-Metadaten erhalten.
    set_tournament_group(
        tournament_id,
        get_tournament_group_id(tournament_id),
        get_tournament_cube_id(tournament_id),
    )

    if not os.path.exists(rounds_dir):
        flash("Turnier geladen, aber es wurden noch keine Runden erstellt.")
        return redirect(url_for("main.index"))

    round_numbers = []
    for filename in os.listdir(rounds_dir):
        if filename.startswith("round_") and filename.endswith(".csv"):
            try:
                round_numbers.append(int(filename.replace("round_", "").replace(".csv", "")))
            except ValueError:
                continue

    if not round_numbers:
        flash("Turnier geladen, aber es wurden noch keine Runden erstellt.")
        return redirect(url_for("main.index"))

    return redirect(url_for("main.show_round", round_number=max(round_numbers)))

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

def normalize_player_name_for_compare(name):
    """Normalisiert Spielername für robuste Duplikaterkennung (Case/Diakritika/Whitespace)."""
    if not isinstance(name, str):
        return ""
    compact = " ".join(name.strip().split())
    without_diacritics = "".join(
        ch for ch in unicodedata.normalize("NFD", compact) if unicodedata.category(ch) != "Mn"
    )
    return without_diacritics.casefold()

def _validate_players_list(raw_players):
    """Validiert und normalisiert eine Spielerliste."""
    if not isinstance(raw_players, list):
        return None, "Ungültige Spielerliste."

    players = []
    invalid_players = []
    for raw_name in raw_players:
        cleaned_name = (raw_name or "").strip()
        if validate_player_name(cleaned_name):
            players.append(cleaned_name)
        else:
            invalid_players.append(raw_name)

    if invalid_players:
        return None, "Ungültige Spielernamen gefunden. Namen dürfen nicht leer sein und maximal 50 Zeichen haben."
    if not players:
        return None, "Bitte geben Sie mindestens einen gültigen Spielernamen ein."

    seen_players = {}
    duplicate_players = set()
    for player in players:
        key = normalize_player_name_for_compare(player)
        if key in seen_players:
            duplicate_players.add(seen_players[key])
            duplicate_players.add(player)
        else:
            seen_players[key] = player

    if duplicate_players:
        duplicate_list = ", ".join(sorted(duplicate_players))
        return None, f"Doppelte Spielernamen gefunden: {duplicate_list}. Bitte geben Sie eindeutige Namen ein."

    return players, None

def _create_started_tournament(players, table_size, group_id, cube_id, set_session_state=True):
    """
    Erstellt ein laufendes Turnier inkl. Runde 1 aus genau einem Tischblock.
    Bei ungerader Spielerzahl wird automatisch ein BYE-Match angelegt.
    """
    tournament_id = str(uuid.uuid4())
    set_tournament_group(tournament_id, group_id, cube_id)

    data_dir = os.path.join("data", tournament_id)
    os.makedirs(data_dir, exist_ok=True)

    shuffled = players.copy()
    random.shuffle(shuffled)

    group_key = f"{table_size}-1"
    player_groups = {group_key: players.copy()}
    match_list = []
    table_nr = 1

    for i in range(0, len(shuffled) - 1, 2):
        p1 = shuffled[i]
        p2 = shuffled[i + 1]
        match_list.append({
            "table": str(table_nr),
            "player1": p1,
            "player2": p2,
            "score1": "",
            "score2": "",
            "score_draws": "",
            "dropout1": "false",
            "dropout2": "false",
            "table_size": str(table_size),
            "group_key": group_key,
        })
        table_nr += 1

    if len(shuffled) % 2 == 1:
        bye_player = shuffled[-1]
        match_list.append({
            "table": str(table_nr),
            "player1": bye_player,
            "player2": "BYE",
            "score1": "2",
            "score2": "0",
            "score_draws": "0",
            "dropout1": "false",
            "dropout2": "false",
            "table_size": str(table_size),
            "group_key": group_key,
        })

    with open(os.path.join(data_dir, "player_groups.json"), "w", encoding="utf-8") as f:
        json.dump(player_groups, f)

    rounds_dir = os.path.join(data_dir, "rounds")
    os.makedirs(rounds_dir, exist_ok=True)
    round_file = os.path.join(rounds_dir, "round_1.csv")
    with open(round_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "table",
                "player1",
                "player2",
                "score1",
                "score2",
                "score_draws",
                "dropout1",
                "dropout2",
                "table_size",
                "group_key",
            ],
        )
        writer.writeheader()
        writer.writerows(match_list)

    if set_session_state:
        session["tournament_id"] = tournament_id
        session["leg_players_set"] = []
        session["tournament_ended"] = False
        session["player_groups"] = player_groups

    return {
        "tournament_id": tournament_id,
        "player_groups": player_groups,
        "player_count": len(players),
    }

def _extract_table_builder_payload():
    raw_payload = (request.form.get("tables_payload") or "").strip()
    if not raw_payload:
        return None, "Bitte mindestens einen Tisch konfigurieren."
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None, "Ungültige Tisch-Konfiguration."
    if not isinstance(payload, list) or not payload:
        return None, "Bitte mindestens einen Tisch konfigurieren."
    return payload, None

@main.route("/start_tables", methods=["POST"])
def start_tables():
    payload, payload_error = _extract_table_builder_payload()
    if payload_error:
        return render_index_page(error=payload_error)

    valid_group_ids = {group["id"] for group in load_tournament_groups()}
    valid_cube_ids = {cube["id"] for cube in load_allowed_cubes()}
    all_players_seen = set()
    normalized_tables = []

    for idx, table in enumerate(payload, start=1):
        if not isinstance(table, dict):
            return render_index_page(error=f"Ungültiger Tischblock {idx}.")
        try:
            table_size = int(table.get("table_size", 0))
        except (TypeError, ValueError):
            return render_index_page(error=f"Ungültige Tischgröße in Tisch {idx}.")
        if table_size not in [6, 8, 10, 12]:
            return render_index_page(error=f"Ungültige Tischgröße in Tisch {idx}.")

        group_id = table.get("group_id", DEFAULT_GROUP_ID)
        cube_id = table.get("cube_id", "vintage")
        if group_id not in valid_group_ids:
            group_id = DEFAULT_GROUP_ID
        if cube_id not in valid_cube_ids:
            cube_id = "vintage"

        players, players_error = _validate_players_list(table.get("players", []))
        if players_error:
            return render_index_page(error=f"Tisch {idx}: {players_error}")

        if len(players) > table_size:
            return render_index_page(
                error=(
                    f"Tisch {idx}: Zu viele Spieler ({len(players)}) für Tischgröße {table_size}. "
                    "Bitte Spielerzahl reduzieren oder Tischgröße erhöhen."
                )
            )
        if len(players) < 2:
            return render_index_page(error=f"Tisch {idx}: Mindestens 2 Spieler erforderlich.")

        duplicates_across_tables = [player for player in players if player in all_players_seen]
        if duplicates_across_tables:
            duplicate_text = ", ".join(sorted(set(duplicates_across_tables)))
            return render_index_page(
                error=f"Spieler dürfen nicht in mehreren Tischen sein. Doppelt gefunden: {duplicate_text}."
            )

        all_players_seen.update(players)
        normalized_tables.append(
            {
                "table_size": table_size,
                "group_id": group_id,
                "cube_id": cube_id,
                "players": players,
            }
        )

    random.seed(42)
    created_tournaments = []
    for table in normalized_tables:
        created_tournaments.append(
            _create_started_tournament(
                table["players"],
                table["table_size"],
                table["group_id"],
                table["cube_id"],
                set_session_state=False,
            )
        )

    primary = created_tournaments[0]
    session["tournament_id"] = primary["tournament_id"]
    session["leg_players_set"] = []
    session["tournament_ended"] = False
    session["player_groups"] = primary["player_groups"]

    summary = []
    for idx, created in enumerate(created_tournaments, start=1):
        summary.append(f"Tisch {idx}: {created['tournament_id'][:8]} ({created['player_count']} Spieler)")
    flash(f"{len(created_tournaments)} Turnier(e) gestartet. " + "; ".join(summary))
    return redirect(url_for("main.show_round", round_number=1))

@main.route("/pair", methods=["POST"])
def pair():
    selected_group_id = request.form.get("tournament_group", DEFAULT_GROUP_ID)
    if not is_valid_group_id(selected_group_id):
        selected_group_id = DEFAULT_GROUP_ID
    selected_cube = (request.form.get("tournament_cube") or "").strip()
    if not is_valid_cube_id(selected_cube):
        return render_index_page(
            error="Ungültiger Cube. Bitte wählen Sie einen erlaubten Cube aus.",
            players_text="\n".join(request.form.getlist("players")),
            selected_group_id=selected_group_id,
            selected_cube=selected_cube,
        )
    
    # Verarbeite und validiere die Spielerliste
    raw_players = request.form.getlist("players")
    players, players_error = _validate_players_list(raw_players)
    if players_error:
        return render_index_page(
            error=players_error,
            players_text="\n".join(raw_players),
            selected_group_id=selected_group_id,
            selected_cube=selected_cube,
        )
    
    group_sizes = request.form.getlist("group_sizes")
    
    try:
        # Konvertiere Gruppengrößen zu Integers und validiere sie
        allowed_sizes = [int(size) for size in group_sizes]
        if not allowed_sizes:
            return render_index_page(
                error="Bitte wählen Sie mindestens eine Tischgrösse aus.",
                players_text="\n".join(players),
                selected_group_id=selected_group_id,
                selected_cube=selected_cube,
            )
        if len(allowed_sizes) > 1:
            return render_index_page(
                error=(
                    "Mehrere Tischgrößen bitte über den neuen Tisch-Builder starten. "
                    "Konfiguriere dafür mehrere Tische auf der Startseite."
                ),
                players_text="\n".join(players),
                selected_group_id=selected_group_id,
                selected_cube=selected_cube,
            )
        
        # Finde mögliche Gruppierungen
        groupings = find_all_valid_groupings(len(players), allowed_sizes)
        
        if not groupings:
            return render_index_page(
                error=f"Keine gültige Gruppierung für {len(players)} Spieler mit den Tischgrössen {allowed_sizes} möglich.",
                players_text="\n".join(players),
                selected_group_id=selected_group_id,
                selected_cube=selected_cube,
            )

        # Neues Turnier erst nach erfolgreicher Validierung anlegen.
        tournament_id = str(uuid.uuid4())
        session["tournament_id"] = tournament_id
        session["leg_players_set"] = []
        session["tournament_ended"] = False
        set_tournament_group(tournament_id, selected_group_id, selected_cube)
        data_dir = os.path.join("data", tournament_id)
        os.makedirs(data_dir, exist_ok=True)
        
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
        return render_index_page(
            error=f"Fehler bei der Verarbeitung der Gruppengrößen: {str(e)}",
            players_text="\n".join(players),
            selected_group_id=selected_group_id,
            selected_cube=selected_cube,
        )
    except Exception as e:
        return render_index_page(
            error=f"Ein unerwarteter Fehler ist aufgetreten: {str(e)}",
            players_text="\n".join(players),
            selected_group_id=selected_group_id,
            selected_cube=selected_cube,
        )

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
    is_vintage = is_vintage_tournament(tournament_id)

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
    
    # Verarbeite Power Nine Daten nur für Vintage-Turniere
    if is_vintage and player1_power_nine and player1_name:
        try:
            power_nine_data = json.loads(player1_power_nine)
            print(f"Power Nine Daten für {player1_name} empfangen: {power_nine_data}")
            update_tournament_power_nine(tournament_id, player1_name, power_nine_data)
            
            # Aktualisiere auch die globalen Statistiken für den Spieler
            from .player_stats import update_player_power_nine
            update_player_power_nine(player1_name, power_nine_data)
        except Exception as e:
            print(f"Fehler bei der Verarbeitung der Power Nine Daten für {player1_name}: {e}")
    
    if is_vintage and player2_power_nine and player2_name and player2_name != "BYE":
        try:
            power_nine_data = json.loads(player2_power_nine)
            print(f"Power Nine Daten für {player2_name} empfangen: {power_nine_data}")
            update_tournament_power_nine(tournament_id, player2_name, power_nine_data)
            
            # Aktualisiere auch die globalen Statistiken für den Spieler
            from .player_stats import update_player_power_nine
            update_player_power_nine(player2_name, power_nine_data)
        except Exception as e:
            print(f"Fehler bei der Verarbeitung der Power Nine Daten für {player2_name}: {e}")
    
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
                                  'dropout1', 'dropout2', 'group_key']
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
        requested_player1 = (player1 or "").strip()
        requested_player2 = (player2 or "").strip()
        requested_players = {requested_player1, requested_player2}
        match_found = False
        for match in matches:
            print(f"Vergleiche Match: Tisch {match.get('table', 'unbekannt')} mit {table}")
            if str(match.get("table", "")) == str(table):
                # Zusätzliche Integritätsprüfung:
                # Aktualisiere nur dann, wenn auch die Spieler zum Tisch passen.
                match_players = {match.get("player1", "").strip(), match.get("player2", "").strip()}
                if requested_player1 and requested_player2 and match_players != requested_players:
                    print(
                        "Tischnummer passt, aber Spielerpaarung stimmt nicht überein: "
                        f"Request={requested_players}, Match={match_players}"
                    )
                    continue

                print(f"Tisch gefunden! Spieler: {match.get('player1', '')} vs {match.get('player2', '')}")
                
                # Aktualisiere alle relevanten Werte
                match["score1"] = score1
                match["score2"] = score2
                match["score_draws"] = score_draws  # Neues Feld für Unentschieden
                match["dropout1"] = "true" if dropout1 else "false"
                match["dropout2"] = "true" if dropout2 else "false"
                
                # Stelle sicher, dass table_size als String gesetzt ist
                match["table_size"] = str(table_size)
                
                # Füge Spieler zur markierten Liste hinzu oder entferne sie, basierend auf dropout-Status
                marked_players = session.get("leg_players_set", [])
                
                # Für Spieler 1
                if dropout1 and match['player1'] not in marked_players:
                    marked_players.append(match['player1'])
                    print(f"Dropout-Status zu Spieler 1 hinzugefügt: {match['player1']}")
                elif not dropout1 and match['player1'] in marked_players:
                    marked_players.remove(match['player1'])
                    print(f"Dropout-Status von Spieler 1 entfernt: {match['player1']}")
                
                # Für Spieler 2 (wenn nicht BYE)
                if match['player2'] != "BYE":
                    if dropout2 and match['player2'] not in marked_players:
                        marked_players.append(match['player2'])
                        print(f"Dropout-Status zu Spieler 2 hinzugefügt: {match['player2']}")
                    elif not dropout2 and match['player2'] in marked_players:
                        marked_players.remove(match['player2'])
                        print(f"Dropout-Status von Spieler 2 entfernt: {match['player2']}")
                
                # Aktualisiere die Session
                session["leg_players_set"] = marked_players
                
                match_found = True
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

        # Erst nach erfolgreicher Rundendatei-Aktualisierung in results.csv speichern
        results_file = os.path.join("tournament_data", "results.csv")
        os.makedirs("tournament_data", exist_ok=True)
        file_exists = os.path.isfile(results_file)
        try:
            with open(results_file, "a", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                if not file_exists:
                    writer.writerow(["Tournament", "Timestamp", "Table", "Player 1", "Score 1", "Player 2", "Score 2", "Draws"])
                writer.writerow([tournament_id, datetime.now().isoformat(), table, player1, score1, player2, score2, score_draws])
            print("Ergebnis in results.csv gespeichert")
        except Exception as e:
            print(f"Fehler beim Speichern in results.csv: {e}")
            return jsonify({"success": False, "message": f"Fehler beim Speichern der Ergebnisse: {str(e)}"}), 500
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
            "dropout2": "true" if dropout2 else "false"
        }
    }
    
    # Zurück zur Rundenansicht (für nicht-Ajax Anfragen als Fallback)
    print(f"Ergebnis erfolgreich gespeichert, JSON-Antwort wird gesendet")
    return jsonify(response_data)

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

def get_player_bye_counts(tournament_id, up_to_round):
    """Zählt, wie oft jeder Spieler bis inkl. Runde N ein BYE erhalten hat."""
    bye_counts = defaultdict(int)
    data_dir = os.path.join("data", tournament_id)

    for round_num in range(1, up_to_round + 1):
        round_file = os.path.join(data_dir, "rounds", f"round_{round_num}.csv")
        if not os.path.exists(round_file):
            continue
        try:
            with open(round_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for match in reader:
                    if (match.get("player2") or "").strip() == "BYE":
                        player1 = (match.get("player1") or "").strip()
                        if player1:
                            bye_counts[player1] += 1
        except (IOError, OSError):
            continue

    return bye_counts

def validate_round_completion(round_file):
    """
    Prüft, ob alle Matches einer Runde vollständig und plausibel eingetragen sind.

    Regeln:
    - Normales Match: score1 und score2 müssen gesetzt sein (0-2), draws optional (0-2)
    - BYE-Match: Ergebnis muss 2-0 (draws 0) sein
    - Beide Spieler dürfen nicht gleichzeitig 2 Siege haben
    - Ein Match mit 0-0-0 gilt als nicht abgeschlossen
    """
    if not os.path.exists(round_file):
        return False, "Die aktuelle Rundendatei wurde nicht gefunden."

    try:
        with open(round_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, match in enumerate(reader, start=1):
                table = match.get("table", str(idx))
                player1 = (match.get("player1") or "").strip()
                player2 = (match.get("player2") or "").strip()
                raw_score1 = (match.get("score1") or "").strip()
                raw_score2 = (match.get("score2") or "").strip()
                raw_draws = (match.get("score_draws") or "").strip()

                if not player1 or not player2:
                    return False, f"Tisch {table}: Spielerzuordnung ist unvollständig."

                # Für normale Matches müssen beide Scores eingetragen sein.
                if player2 != "BYE" and (raw_score1 == "" or raw_score2 == ""):
                    return False, f"Tisch {table}: Ergebnis ist noch nicht vollständig eingetragen."

                # Leere Draws als 0 behandeln
                if raw_draws == "":
                    raw_draws = "0"

                try:
                    score1 = int(raw_score1) if raw_score1 != "" else None
                    score2 = int(raw_score2) if raw_score2 != "" else None
                    draws = int(raw_draws)
                except ValueError:
                    return False, f"Tisch {table}: Ergebnis enthält ungültige Werte."

                if player2 == "BYE":
                    if score1 != 2 or score2 != 0 or draws != 0:
                        return False, f"Tisch {table}: BYE-Match muss 2-0-0 sein."
                    continue

                # Normale Matches: Wertebereich prüfen
                if score1 is None or score2 is None:
                    return False, f"Tisch {table}: Ergebnis ist noch nicht vollständig eingetragen."
                if not (0 <= score1 <= 2 and 0 <= score2 <= 2 and 0 <= draws <= 2):
                    return False, f"Tisch {table}: Ergebnis muss im Bereich 0 bis 2 liegen."
                if score1 == 2 and score2 == 2:
                    return False, f"Tisch {table}: Beide Spieler können nicht 2 Siege haben."
                if score1 == 0 and score2 == 0 and draws == 0:
                    return False, f"Tisch {table}: Match ist noch nicht gespielt (0-0-0)."
    except (IOError, OSError) as e:
        return False, f"Fehler beim Prüfen der Rundendatei: {e}"

    return True, ""

def is_round_unplayed(round_file):
    """
    Erkennt eine versehentlich eröffnete, aber noch ungespielte Runde.

    Eine Runde gilt als ungespielt, wenn in keinem normalen Match (kein BYE)
    ein Ergebnis eingetragen wurde. Automatisch gesetzte BYE-Ergebnisse werden
    dabei ignoriert.
    """
    if not os.path.exists(round_file):
        return False

    try:
        with open(round_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for match in reader:
                player2 = (match.get("player2") or "").strip()
                if player2 == "BYE":
                    continue

                raw_score1 = (match.get("score1") or "").strip()
                raw_score2 = (match.get("score2") or "").strip()
                raw_draws = (match.get("score_draws") or "").strip()

                # Sobald für ein normales Match irgendetwas gespeichert wurde,
                # behandeln wir die Runde als begonnen.
                if raw_score1 != "" or raw_score2 != "" or raw_draws != "":
                    return False

            return True
    except (IOError, OSError):
        return False

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
            round_numbers = []
            for filename in os.listdir(rounds_dir):
                if filename.startswith("round_") and filename.endswith(".csv"):
                    try:
                        round_numbers.append(int(filename.replace("round_", "").replace(".csv", "")))
                    except ValueError:
                        continue
            if round_numbers:
                return redirect(url_for("main.show_round", round_number=max(round_numbers)))
            return redirect(url_for("main.index"))
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
    session["leg_players_set"] = get_marked_players_for_tournament(tournament_id)
    
    # Debug-Ausgabe der markierten Spieler
    marked_players = session.get("leg_players_set", [])
    print(f"Markierte Spieler (Dropout): {marked_players}")
    
    # Bestimme die aktuelle Runde
    round_numbers = []
    for filename in os.listdir(rounds_dir):
        if filename.startswith('round_') and filename.endswith('.csv'):
            try:
                round_numbers.append(int(filename.replace("round_", "").replace(".csv", "")))
            except ValueError:
                continue
    current_round = max(round_numbers) if round_numbers else 0
    if current_round == 0:
        flash("Es existiert noch keine Runde, von der aus fortgesetzt werden kann.")
        return redirect(url_for("main.index"))

    # Runde muss vollständig abgeschlossen sein, bevor neue Paarungen erzeugt werden.
    current_round_file = os.path.join(rounds_dir, f"round_{current_round}.csv")
    is_complete, message = validate_round_completion(current_round_file)
    if not is_complete:
        flash(f"Nächste Runde nicht möglich: {message}")
        return redirect(url_for("main.show_round", round_number=current_round))

    # Berechne den Leaderboard für die aktuelle Runde
    leaderboard = calculate_leaderboard(tournament_id, current_round)
    
    # Lade die Gegner-Historie
    opponents = get_player_opponents(tournament_id, current_round)
    # Lade BYE-Historie für faire BYE-Vergabe
    bye_counts = get_player_bye_counts(tournament_id, current_round)
    
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
            # Faire BYE-Vergabe:
            # - bevorzugt Spieler mit weniger bisherigen BYEs
            # - bei Gleichstand weiterhin eher niedriger platzierte Spieler
            min_bye_count = min(bye_counts.get(p, 0) for p in sorted_players)
            bye_player = None
            for candidate in reversed(sorted_players):
                if bye_counts.get(candidate, 0) == min_bye_count:
                    bye_player = candidate
                    break
            if bye_player is None:
                bye_player = sorted_players[-1]
            sorted_players.remove(bye_player)
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
            bye_counts[bye_player] += 1
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
        for match in match_list:
            # Debug-Ausgabe für Spielernamen in der Runde
            print(f"Match: {match['player1']} vs {match['player2']}")

        writer = csv.DictWriter(f, fieldnames=['table', 'player1', 'player2', 'score1', 'score2', 'score_draws', 'table_size', 'group_key'])
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

@main.route("/start_tournament", methods=["GET", "POST"])
def start_tournament():
    # GET aus alten Links: keine direkte Aktion ohne explizite Bestätigung
    if request.method == "GET":
        flash("Bitte neues Turnier explizit über den Button mit Bestätigung starten.")
        return redirect(url_for("main.index"))

    # Serverseitige Absicherung gegen versehentliche Requests
    if request.form.get("force_new") != "1":
        flash("Neues Turnier wurde nicht gestartet (Bestätigung fehlt).")
        return redirect(url_for("main.index"))

    # Vollständiges Zurücksetzen - vor dem Zugriff auf alte Turnier-ID
    session.clear()
    
    # Generiere eine neue Turnier-ID
    new_tournament_id = str(uuid.uuid4())
    session["tournament_id"] = new_tournament_id
    
    # Explizit die Liste der markierten Spieler zurücksetzen
    session["leg_players_set"] = []
    
    # Explizit den Turnierstatus zurücksetzen
    session["tournament_ended"] = False
    
    # Kein Datenordner anlegen: Das eigentliche Turnier wird erst bei /pair erstellt.
    # So verhindern wir "Runde 0 • 0 Spieler"-Platzhalter.
    print(f"Neues Turnier mit ID {new_tournament_id} vorbereitet")
    return redirect(url_for("main.index"))

@main.route("/continue_tournament", methods=["GET"])
def continue_tournament():
    """Setzt ein laufendes Turnier fort, indem auf die letzte Runde umgeleitet wird."""
    tournament_id = session.get("tournament_id")
    if not tournament_id:
        flash("Kein aktives Turnier gefunden.")
        return redirect(url_for("main.index"))

    rounds_dir = os.path.join("data", tournament_id, "rounds")
    if not os.path.exists(rounds_dir):
        flash("Für dieses Turnier sind noch keine Runden vorhanden.")
        return redirect(url_for("main.index"))

    round_numbers = []
    for filename in os.listdir(rounds_dir):
        if filename.startswith("round_") and filename.endswith(".csv"):
            try:
                round_numbers.append(int(filename.replace("round_", "").replace(".csv", "")))
            except ValueError:
                continue

    if not round_numbers:
        flash("Für dieses Turnier sind noch keine Runden vorhanden.")
        return redirect(url_for("main.index"))

    return redirect(url_for("main.show_round", round_number=max(round_numbers)))

@main.route("/end_tournament", methods=["POST"])
def end_tournament():
    tournament_id = session.get("tournament_id")
    if not tournament_id:
        return redirect(url_for("main.index"))
    
    # Berechne den finalen Leaderboard
    data_dir = os.path.join("data", tournament_id)
    rounds_dir = os.path.join(data_dir, "rounds")
    total_rounds = 0
    if os.path.exists(rounds_dir):
        round_numbers = []
        for filename in os.listdir(rounds_dir):
            if filename.startswith("round_") and filename.endswith(".csv"):
                try:
                    round_numbers.append(int(filename.replace("round_", "").replace(".csv", "")))
                except ValueError:
                    continue
        total_rounds = max(round_numbers) if round_numbers else 0

        # Nur vollständig abgeschlossene letzte Runde darf als final gewertet werden.
        # Ausnahme: eine versehentlich eröffnete, noch ungespielte letzte Runde
        # wird automatisch verworfen und das Turnier mit der vorherigen Runde beendet.
        if total_rounds > 0:
            latest_round_file = os.path.join(rounds_dir, f"round_{total_rounds}.csv")
            is_complete, message = validate_round_completion(latest_round_file)
            if not is_complete:
                if total_rounds > 1 and is_round_unplayed(latest_round_file):
                    try:
                        os.remove(latest_round_file)
                        total_rounds -= 1
                        flash(
                            "Die letzte Runde war noch ungespielt und wurde verworfen. "
                            "Das Turnier wurde mit der vorherigen Runde beendet."
                        )
                    except OSError as e:
                        flash(f"Turnier kann nicht beendet werden: Letzte Runde konnte nicht verworfen werden ({e}).")
                        return redirect(url_for("main.show_round", round_number=total_rounds))
                else:
                    flash(f"Turnier kann nicht beendet werden: {message}")
                    return redirect(url_for("main.show_round", round_number=total_rounds))

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
        "group_id": get_tournament_group_id(tournament_id),
        "group_name": get_tournament_group_name(tournament_id),
        "cube_id": get_tournament_cube_id(tournament_id),
        "cube_name": get_tournament_cube_name(tournament_id),
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
                try:
                    round_num = int(filename.replace("round_", "").replace(".csv", ""))
                    total_rounds = max(total_rounds, round_num)
                except ValueError:
                    continue
    
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
                'group_key': row.get('group_key', row.get('table_size', ''))
            }
                
            matches.append(match)
    
    # Lade das Leaderboard für das Turnier bis zu dieser Runde
    leaderboard = calculate_leaderboard(tournament_id, round_number)
    bye_counts = get_player_bye_counts(tournament_id, round_number)
    
    # Prüfe, ob das Turnier beendet ist - zweifache Prüfung für Konsistenz
    tournament_ended = check_tournament_status(tournament_id)
    is_vintage = is_vintage_tournament(tournament_id)
    
    # Lade Power-Nine-Daten nur für Vintage-Turniere
    all_players_data = {}
    tournament_power_nine = get_tournament_power_nine(tournament_id) if is_vintage else {}
    
    # Erstelle ein Dictionary mit den Spielerdaten für das Template
    if is_vintage:
        from .player_stats import POWER_NINE
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
        bye_counts=bye_counts,
        tournament_ended=tournament_ended,
        all_players_data=all_players_data,
        is_vintage_tournament=is_vintage,
        running_tournaments=get_active_tournaments(limit=50),
    )

def calculate_opponents_match_percentage(player, stats):
    """Berechnet den OMW% (Opponents Match Win Percentage) für einen Spieler."""
    if player not in stats or player == "BYE":
        return 0.0
    
    # Sammle alle Gegner des Spielers
    opponents = []
    for opponent, opponent_stats in stats.items():
        if opponent == player or opponent == "BYE":  # Überspringe Spieler selbst und BYE
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
    if player not in stats or player == "BYE":
        return 0.0
    
    # Sammle alle Gegner des Spielers
    opponents = []
    for opponent, opponent_stats in stats.items():
        if opponent == player or opponent == "BYE":  # Überspringe Spieler selbst und BYE
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
                        
                        if player2 == "BYE":
                            # BYE zählt nur für den aktiven Spieler.
                            # BYE darf keine eigenen Stats/Opponents erzeugen und keine Tiebreaker verfälschen.
                            stats[player1]['points'] += 3
                            stats[player1]['wins'] += 1
                            stats[player1]['total_wins'] += score1
                            stats[player1]['total_losses'] += score2
                            stats[player1]['total_draws'] += score_draws
                            stats[player1]['matches'] += 1
                            continue

                        # Aktualisiere die Gegner-Listen
                        stats[player1]['opponents'].append(player2)
                        stats[player2]['opponents'].append(player1)
                        
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
        if player == "BYE":
            continue
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
    """Löscht ein Turnier (laufend oder vergangen)."""
    if not is_valid_tournament_id(tournament_id):
        return jsonify({"success": False, "message": "Ungültige Turnier-ID"}), 400

    # Pfade zu den Turnierdaten
    tournament_results_dir = "tournament_results"
    results_file = os.path.join(tournament_results_dir, f"{tournament_id}_results.json")
    data_dir = os.path.join("data", tournament_id)
    
    # Prüfe, ob das Turnier existiert (entweder als laufendes oder archiviertes Turnier)
    has_results = os.path.exists(results_file)
    has_data = os.path.exists(data_dir) and os.path.isdir(data_dir)
    if not has_results and not has_data:
        return jsonify({"success": False, "message": "Turnier nicht gefunden"}), 404
    
    try:
        # Lösche Archivdatei falls vorhanden
        if has_results:
            os.remove(results_file)

        # Lösche zugehörige Daten im data-Verzeichnis
        if has_data:
            import shutil
            shutil.rmtree(data_dir)

        # Falls aktuell geladenes Turnier gelöscht wurde, Session bereinigen
        if session.get("tournament_id") == tournament_id:
            session.pop("tournament_id", None)
            session.pop("leg_players_set", None)
            session.pop("tournament_ended", None)

        remove_tournament_group(tournament_id)
        
        return jsonify({"success": True, "message": "Turnier erfolgreich gelöscht"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Fehler beim Löschen: {str(e)}"}), 500

@main.route("/players")
def players_list():
    """Zeigt eine Übersichtsseite mit allen Spielern"""
    # Importiere das player_stats Modul
    from .player_stats import get_all_players, load_player_data, get_player_statistics

    tournament_groups = load_tournament_groups()
    valid_group_ids = {group["id"] for group in tournament_groups}
    cube_filter_options = [{"id": "all", "name": "Alle Cubes"}] + load_allowed_cubes()
    valid_cube_ids = {cube["id"] for cube in cube_filter_options if cube["id"] != "all"}
    stats_scope = request.args.get("scope", "global")
    selected_group_id = request.args.get("group_id", DEFAULT_GROUP_ID)
    selected_cube_id = (request.args.get("cube", "all") or "all").strip().lower()
    if selected_group_id not in valid_group_ids:
        selected_group_id = DEFAULT_GROUP_ID
    if stats_scope != "group":
        stats_scope = "global"
    if selected_cube_id != "all" and selected_cube_id not in valid_cube_ids:
        selected_cube_id = "all"

    stats_group_id = selected_group_id if stats_scope == "group" else None
    
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
        player_stats = get_player_statistics(
            player,
            group_id=stats_group_id,
            cube_filter=selected_cube_id,
        )
        
        # Power Nine wird nur im Vintage-Filter angezeigt
        power_nine_count = player_stats.get("power_nine_total", 0) if selected_cube_id == "vintage" else 0
        
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
        players=sorted_players,
        stats_scope=stats_scope,
        selected_group_id=selected_group_id,
        tournament_groups=tournament_groups,
        selected_cube_id=selected_cube_id,
        cube_filter_options=cube_filter_options,
        show_power_nine_stats=(selected_cube_id == "vintage"),
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

    tournament_groups = load_tournament_groups()
    cube_filter_options = [{"id": "all", "name": "Alle Cubes"}] + load_allowed_cubes()
    valid_group_ids = {group["id"] for group in tournament_groups}
    valid_cube_ids = {cube["id"] for cube in cube_filter_options if cube["id"] != "all"}
    stats_scope = request.args.get("scope", "global")
    selected_group_id = request.args.get("group_id", DEFAULT_GROUP_ID)
    selected_cube_id = (request.args.get("cube", "all") or "all").strip().lower()
    if selected_group_id not in valid_group_ids:
        selected_group_id = DEFAULT_GROUP_ID
    if stats_scope != "group":
        stats_scope = "global"
    if selected_cube_id != "all" and selected_cube_id not in valid_cube_ids:
        selected_cube_id = "all"
    stats_group_id = selected_group_id if stats_scope == "group" else None
    
    # Lade Spielerdaten
    player_data = load_player_data(player_name)
    player_stats = get_player_statistics(
        player_name,
        group_id=stats_group_id,
        cube_filter=selected_cube_id,
    )
    
    return render_template(
        "player_profile.html",
        player_name=player_name,
        player_data=player_data,
        player_stats=player_stats,
        power_nine=POWER_NINE,
        stats_scope=stats_scope,
        selected_group_id=selected_group_id,
        tournament_groups=tournament_groups,
        selected_cube_id=selected_cube_id,
        cube_filter_options=cube_filter_options,
        show_power_nine_stats=(selected_cube_id == "vintage"),
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
    if not is_vintage_tournament(tournament_id):
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
    if not is_vintage_tournament(tournament_id):
        return jsonify({
            "success": True,
            "message": "Power Nine ist nur in Vintage-Turnieren aktiv."
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
    if not is_vintage_tournament(tournament_id):
        return True
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
    if not is_vintage_tournament(tournament_id):
        return {}
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
    
    # Prüfe persistenten Status auf Dateiebene
    data_dir = os.path.join("data", tournament_id)
    end_time_file = os.path.join(data_dir, "end_time.txt")
    file_tournament_ended = os.path.exists(end_time_file)
    results_file = os.path.join("tournament_results", f"{tournament_id}_results.json")
    archived_tournament_ended = os.path.exists(results_file)
    
    # Session-Status darf nur für das AKTUELLE Turnier gelten, sonst entstehen False-Positives.
    tournament_ended = file_tournament_ended or archived_tournament_ended

    if session.get("tournament_id") == tournament_id:
        session["tournament_ended"] = tournament_ended
    
    return tournament_ended