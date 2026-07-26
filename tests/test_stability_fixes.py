"""Tests für die Stabilitäts-Fixes (atomare Writes, Errorhandler, robuste CSV-Verarbeitung)."""

import csv
import os

import pytest

from app import create_app
from app.atomic_io import atomic_write
from app.routes import calculate_leaderboard


# ---------------------------------------------------------------------------
# atomic_write
# ---------------------------------------------------------------------------

def test_atomic_write_creates_and_replaces_file(tmp_path):
    target = tmp_path / "payload.json"

    atomic_write(str(target), lambda f: f.write("eins"))
    assert target.read_text(encoding="utf-8") == "eins"

    atomic_write(str(target), lambda f: f.write("zwei"))
    assert target.read_text(encoding="utf-8") == "zwei"

    # Keine Tempdateien übrig
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_keeps_old_content_on_error(tmp_path):
    target = tmp_path / "payload.json"
    target.write_text("alt", encoding="utf-8")

    def failing_writer(f):
        f.write("halb geschrieben")
        raise ValueError("boom")

    with pytest.raises(ValueError):
        atomic_write(str(target), failing_writer)

    # Alter Inhalt bleibt unangetastet, keine Tempdateien übrig
    assert target.read_text(encoding="utf-8") == "alt"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_creates_missing_directories(tmp_path):
    target = tmp_path / "a" / "b" / "file.txt"
    atomic_write(str(target), lambda f: f.write("inhalt"))
    assert target.read_text(encoding="utf-8") == "inhalt"


# ---------------------------------------------------------------------------
# Errorhandler
# ---------------------------------------------------------------------------

def test_404_returns_json_for_api_paths(client):
    response = client.get("/api/gibt-es-nicht")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "NOT_FOUND"


def test_404_returns_html_for_browser_requests(client):
    response = client.get("/gibt-es-nicht", headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert b"Seite nicht gefunden" in response.data


def test_500_errorhandler_returns_json_with_request_id(app):
    @app.route("/api/boom")
    def boom():
        raise RuntimeError("absichtlich kaputt")

    app.config["PROPAGATE_EXCEPTIONS"] = False
    client = app.test_client()

    response = client.get("/api/boom")
    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "INTERNAL_ERROR"
    assert payload["request_id"]
    assert response.headers.get("X-Request-ID")


def test_500_errorhandler_returns_html_for_browser_requests(app):
    @app.route("/boom-html")
    def boom_html():
        raise RuntimeError("absichtlich kaputt")

    app.config["PROPAGATE_EXCEPTIONS"] = False
    client = app.test_client()

    response = client.get("/boom-html", headers={"Accept": "text/html"})
    assert response.status_code == 500
    assert b"Interner Serverfehler" in response.data


# ---------------------------------------------------------------------------
# calculate_leaderboard mit korrupten CSV-Zeilen
# ---------------------------------------------------------------------------

def _write_round_csv(tournament_id, round_number, matches, fieldnames=None):
    rounds_dir = os.path.join("data", tournament_id, "rounds")
    os.makedirs(rounds_dir, exist_ok=True)
    path = os.path.join(rounds_dir, f"round_{round_number}.csv")
    fieldnames = fieldnames or [
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
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matches)
    return path


def test_leaderboard_skips_corrupt_rows(isolated_workspace):
    tournament_id = "corrupt-rows-test"
    _write_round_csv(
        tournament_id,
        1,
        [
            {
                "table": "1",
                "player1": "Alice",
                "player2": "Bob",
                "score1": "2",
                "score2": "0",
                "score_draws": "0",
            },
            # Korrupte Zeile: nicht-numerischer Score (z.B. durch halben Write)
            {
                "table": "2",
                "player1": "Carol",
                "player2": "Dave",
                "score1": "abc",
                "score2": "1",
                "score_draws": "0",
            },
        ],
    )

    leaderboard = calculate_leaderboard(tournament_id, 1)
    by_name = {entry[0]: entry for entry in leaderboard}

    # Gültige Zeile wird gewertet, korrupte Zeile wird übersprungen statt 500
    assert by_name["Alice"][1] == 3
    assert "Carol" not in by_name
    assert "Dave" not in by_name


def test_leaderboard_handles_truncated_csv(isolated_workspace):
    tournament_id = "truncated-csv-test"
    rounds_dir = os.path.join("data", tournament_id, "rounds")
    os.makedirs(rounds_dir, exist_ok=True)
    # Leere Datei simuliert eine gerade truncatete/halb geschriebene Runde
    with open(os.path.join(rounds_dir, "round_1.csv"), "w", encoding="utf-8"):
        pass

    leaderboard = calculate_leaderboard(tournament_id, 1)
    assert leaderboard == []


# ---------------------------------------------------------------------------
# Secret-Key-Pflicht in Production
# ---------------------------------------------------------------------------

def test_create_app_fails_in_production_without_secret_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    monkeypatch.setenv("FLASK_ENV", "production")

    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        create_app()
