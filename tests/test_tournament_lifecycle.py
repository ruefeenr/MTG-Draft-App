import csv
import json
import os

from app.db import db
from app.models import Tournament


def _start_basic_tournament(client):
    response = client.post(
        "/pair",
        data={
            "players": ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"],
            "group_sizes": ["6"],
            "tournament_group": "liga",
            "tournament_cube": "vintage",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    with client.session_transaction() as sess:
        return sess.get("tournament_id")


def _complete_round(client, tournament_id, round_number, dropout_player=None):
    round_path = os.path.join("data", tournament_id, "rounds", f"round_{round_number}.csv")
    with open(round_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for idx, row in enumerate(rows):
        is_dropout = dropout_player is not None and row["player1"] == dropout_player and idx == 0
        if row["player2"] == "BYE":
            score1, score2, draws = "2", "0", "0"
        else:
            score1, score2, draws = "2", "1", "0"
        save = client.post(
            "/save_results",
            data={
                "table": row["table"],
                "player1": row["player1"],
                "player2": row["player2"],
                "score1": score1,
                "score2": score2,
                "score_draws": draws,
                "current_round": str(round_number),
                "dropout1": "true" if is_dropout else "false",
                "dropout2": "false",
                "table_size": row.get("table_size", "6"),
            },
        )
        assert save.status_code == 200
        payload = save.get_json()
        assert payload["success"] is True


def test_lifecycle_start_save_next_end_archives_and_updates_db(client, app, seeded_random):
    tournament_id = _start_basic_tournament(client)
    assert tournament_id

    _complete_round(client, tournament_id, 1)
    next_round_response = client.post("/next_round", follow_redirects=False)
    assert next_round_response.status_code in (302, 303)
    assert "/round/2" in next_round_response.headers["Location"]

    _complete_round(client, tournament_id, 2)
    end_response = client.post("/end_tournament", follow_redirects=True)
    assert end_response.status_code == 200

    results_file = os.path.join("tournament_results", f"{tournament_id}_results.json")
    assert os.path.exists(results_file)
    with open(results_file, "r", encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["tournament_data"]["id"] == tournament_id
    assert payload["tournament_data"]["is_ended"] is True

    end_marker = os.path.join("data", tournament_id, "end_time.txt")
    assert os.path.exists(end_marker)

    with app.app_context():
        tournament = db.session.get(Tournament, tournament_id)
        assert tournament is not None
        assert tournament.status == "ended"
        assert tournament.ended_at is not None


def test_load_tournament_reconstructs_dropout_session_state(client, seeded_random):
    tournament_id = _start_basic_tournament(client)
    round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
    with open(round_path, "r", encoding="utf-8") as f:
        first_match = next(csv.DictReader(f))
    dropout_player = first_match["player1"]

    _complete_round(client, tournament_id, 1, dropout_player=dropout_player)

    with client.session_transaction() as sess:
        sess.pop("tournament_id", None)
        sess.pop("leg_players_set", None)
        sess.pop("tournament_ended", None)

    response = client.get(f"/load_tournament/{tournament_id}", follow_redirects=False)
    assert response.status_code in (302, 303)

    with client.session_transaction() as sess:
        assert sess.get("tournament_id") == tournament_id
        marked = sess.get("leg_players_set", [])
        assert dropout_player in marked
