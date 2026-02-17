import csv
import json
import os


def _save_round_result(client, round_number, row, score1, score2, draws="0", dropout1="false", dropout2="false"):
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
            "dropout1": dropout1,
            "dropout2": dropout2,
            "table_size": row.get("table_size", "6"),
        },
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True


def _start_tables_tournament(client, players, table_size=8):
    payload = [
        {
            "table_size": table_size,
            "group_id": "liga",
            "cube_id": "vintage",
            "players": players,
        }
    ]
    response = client.post("/start_tables", data={"tables_payload": json.dumps(payload)}, follow_redirects=False)
    assert response.status_code in (302, 303)
    with client.session_transaction() as sess:
        return sess.get("tournament_id")


def test_next_round_avoids_repeat_pairings(client, seeded_random):
    tournament_id = _start_tables_tournament(client, ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"], table_size=6)
    round1_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
    with open(round1_path, "r", encoding="utf-8") as f:
        round1_rows = list(csv.DictReader(f))

    round1_pairs = set()
    for row in round1_rows:
        if row["player2"] == "BYE":
            continue
        round1_pairs.add(frozenset((row["player1"], row["player2"])))
        _save_round_result(client, 1, row, "2", "1")

    next_response = client.post("/next_round", follow_redirects=False)
    assert next_response.status_code in (302, 303)
    assert "/round/2" in next_response.headers["Location"]

    round2_path = os.path.join("data", tournament_id, "rounds", "round_2.csv")
    with open(round2_path, "r", encoding="utf-8") as f:
        round2_rows = list(csv.DictReader(f))
    round2_pairs = {
        frozenset((row["player1"], row["player2"])) for row in round2_rows if row["player2"] != "BYE"
    }
    assert round1_pairs.isdisjoint(round2_pairs)


def test_next_round_assigns_bye_to_different_player_when_possible(client, seeded_random):
    players = ["A", "B", "C", "D", "E", "F", "G"]
    tournament_id = _start_tables_tournament(client, players, table_size=8)
    round1_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
    with open(round1_path, "r", encoding="utf-8") as f:
        round1_rows = list(csv.DictReader(f))

    bye_row_round1 = next(row for row in round1_rows if row["player2"] == "BYE")
    bye_player_round1 = bye_row_round1["player1"]

    for row in round1_rows:
        if row["player2"] == "BYE":
            continue
        _save_round_result(client, 1, row, "2", "1")

    next_response = client.post("/next_round", follow_redirects=False)
    assert next_response.status_code in (302, 303)

    round2_path = os.path.join("data", tournament_id, "rounds", "round_2.csv")
    with open(round2_path, "r", encoding="utf-8") as f:
        round2_rows = list(csv.DictReader(f))
    bye_row_round2 = next(row for row in round2_rows if row["player2"] == "BYE")
    bye_player_round2 = bye_row_round2["player1"]

    assert bye_player_round2 != bye_player_round1


def test_next_round_excludes_marked_dropout_players(client, seeded_random):
    tournament_id = _start_tables_tournament(client, ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"], table_size=6)
    round1_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
    with open(round1_path, "r", encoding="utf-8") as f:
        round1_rows = list(csv.DictReader(f))

    dropout_player = round1_rows[0]["player1"]
    for idx, row in enumerate(round1_rows):
        is_dropout = idx == 0
        _save_round_result(
            client,
            1,
            row,
            "2",
            "1" if row["player2"] != "BYE" else "0",
            "0",
            dropout1="true" if is_dropout else "false",
            dropout2="false",
        )

    next_response = client.post("/next_round", follow_redirects=False)
    assert next_response.status_code in (302, 303)

    round2_path = os.path.join("data", tournament_id, "rounds", "round_2.csv")
    with open(round2_path, "r", encoding="utf-8") as f:
        round2_rows = list(csv.DictReader(f))
    players_in_round2 = {row["player1"] for row in round2_rows}
    players_in_round2.update(row["player2"] for row in round2_rows if row["player2"] != "BYE")
    assert dropout_player not in players_in_round2
