import csv
import os

from app.routes import get_marked_players_for_tournament


def _start_tournament(client):
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


def test_dropout_reconstruction_from_saved_rounds(client):
    tournament_id = _start_tournament(client)
    round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
    with open(round_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    first = rows[0]

    save_response = client.post(
        "/save_results",
        data={
            "table": first["table"],
            "player1": first["player1"],
            "player2": first["player2"],
            "score1": "2",
            "score2": "1",
            "score_draws": "0",
            "current_round": "1",
            "dropout1": "true",
            "dropout2": "false",
            "table_size": first.get("table_size", "6"),
        },
    )
    assert save_response.status_code == 200
    marked = get_marked_players_for_tournament(tournament_id)
    assert first["player1"] in marked


def test_dropout_can_be_removed_and_reconstruction_matches_latest_state(client):
    tournament_id = _start_tournament(client)
    round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
    with open(round_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    first = rows[0]

    for dropout_flag in ("true", "false"):
        save_response = client.post(
            "/save_results",
            data={
                "table": first["table"],
                "player1": first["player1"],
                "player2": first["player2"],
                "score1": "2",
                "score2": "1",
                "score_draws": "0",
                "current_round": "1",
                "dropout1": dropout_flag,
                "dropout2": "false",
                "table_size": first.get("table_size", "6"),
            },
        )
        assert save_response.status_code == 200

    marked = get_marked_players_for_tournament(tournament_id)
    assert first["player1"] not in marked
