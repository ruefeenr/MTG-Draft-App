import csv
import os

from app.db import db
from app.models import Tournament


def _start_tournament(client, players=None):
    payload_players = players or ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"]
    response = client.post(
        "/pair",
        data={
            "players": payload_players,
            "group_sizes": ["6"],
            "tournament_group": "liga",
            "tournament_cube": "vintage",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    with client.session_transaction() as sess:
        return sess["tournament_id"]


def _first_match(tournament_id, round_number=1):
    round_path = os.path.join("data", tournament_id, "rounds", f"round_{round_number}.csv")
    with open(round_path, "r", encoding="utf-8") as f:
        return next(csv.DictReader(f))


def _complete_round(client, tournament_id, round_number):
    round_path = os.path.join("data", tournament_id, "rounds", f"round_{round_number}.csv")
    with open(round_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        score1, score2, draws = ("2", "0", "0") if row["player2"] == "BYE" else ("2", "1", "0")
        response = client.post(
            "/save_results",
            data={
                "table": row["table"],
                "player1": row["player1"],
                "player2": row["player2"],
                "score1": score1,
                "score2": score2,
                "score_draws": draws,
                "current_round": str(round_number),
                "dropout1": "false",
                "dropout2": "false",
                "table_size": row.get("table_size", "6"),
            },
        )
        assert response.status_code == 200


def test_healthz_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_save_results_rejects_mutation_after_db_end_state(client, app):
    tournament_id = _start_tournament(client)
    match = _first_match(tournament_id)

    with app.app_context():
        row = db.session.get(Tournament, tournament_id)
        row.status = "ended"
        db.session.commit()

    response = client.post(
        "/save_results",
        data={
            "table": match["table"],
            "player1": match["player1"],
            "player2": match["player2"],
            "score1": "2",
            "score2": "1",
            "score_draws": "0",
            "current_round": "1",
            "dropout1": "false",
            "dropout2": "false",
            "table_size": match.get("table_size", "6"),
        },
    )
    assert response.status_code == 409
    payload = response.get_json()
    assert payload["code"] == "TOURNAMENT_ENDED"


def test_end_tournament_is_idempotent(client):
    tournament_id = _start_tournament(client)
    _complete_round(client, tournament_id, 1)

    first = client.post("/end_tournament", follow_redirects=True)
    assert first.status_code == 200

    second = client.post("/end_tournament", follow_redirects=False)
    assert second.status_code in (302, 303)


def test_pairings_are_reproducible_with_seed_override(client, monkeypatch):
    players = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"]
    monkeypatch.setenv("MTG_PAIRING_SEED", "12345")
    tournament_a = _start_tournament(client, players=players)
    tournament_b = _start_tournament(client, players=players)

    def pairs_for(tournament_id):
        round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
        with open(round_path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return sorted(tuple(sorted([row["player1"], row["player2"]])) for row in rows)

    assert pairs_for(tournament_a) == pairs_for(tournament_b)


def test_csrf_required_for_post_when_testing_disabled(client, app, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    app.testing = False
    app.config["WTF_CSRF_ENABLED"] = True

    # Session initialisieren
    client.get("/")

    missing = client.post("/groups/create", data={"group_name": "Neue Liga"})
    assert missing.status_code == 403
    assert missing.get_json()["code"] == "CSRF_TOKEN_INVALID"

    with client.session_transaction() as sess:
        token = sess.get("csrf_token")

    ok = client.post("/groups/create", data={"group_name": "Neue Liga", "csrf_token": token}, follow_redirects=False)
    assert ok.status_code in (302, 303)


def test_rate_limit_blocks_repeated_mutations(client, app, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    app.testing = False
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["RATE_LIMIT_ENABLED"] = True
    app.config["RATE_LIMIT_MAX_REQUESTS"] = 1
    app.config["RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.config["RATE_LIMITED_ENDPOINTS"] = {"main.create_group"}

    client.get("/")
    with client.session_transaction() as sess:
        token = sess.get("csrf_token")

    first = client.post("/groups/create", data={"group_name": "Rate A", "csrf_token": token}, follow_redirects=False)
    assert first.status_code in (302, 303)

    second = client.post("/groups/create", data={"group_name": "Rate B", "csrf_token": token}, follow_redirects=False)
    assert second.status_code == 429
    assert second.get_json()["code"] == "RATE_LIMIT_EXCEEDED"
