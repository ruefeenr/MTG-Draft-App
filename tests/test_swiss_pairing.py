import csv
import json
import os

from app.routes import _stable_shuffle
from app.swiss_pairing import generate_swiss_pairings


def _read_round(tournament_id, round_number):
    round_path = os.path.join("data", tournament_id, "rounds", f"round_{round_number}.csv")
    with open(round_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _non_bye_pairs(rows):
    return {
        frozenset((row["player1"], row["player2"]))
        for row in rows
        if row["player2"] != "BYE"
    }


def _bye_players(rows):
    return [row["player1"] for row in rows if row["player2"] == "BYE"]


def _save_round_result(client, round_number, row, score1, score2, draws="0", dropout1="false", dropout2="false"):
    response = client.post(
        "/mtg/save_results",
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
    response = client.post("/mtg/start_tables", data={"tables_payload": json.dumps(payload)}, follow_redirects=False)
    assert response.status_code in (302, 303)
    with client.session_transaction() as sess:
        return sess.get("tournament_id")


def _complete_round_with_first_player_wins(client, tournament_id, round_number):
    rows = _read_round(tournament_id, round_number)
    for row in rows:
        if row["player2"] == "BYE":
            continue
        _save_round_result(client, round_number, row, "2", "1")
    return rows


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

    next_response = client.post("/mtg/next_round", follow_redirects=False)
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

    next_response = client.post("/mtg/next_round", follow_redirects=False)
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

    next_response = client.post("/mtg/next_round", follow_redirects=False)
    assert next_response.status_code in (302, 303)

    round2_path = os.path.join("data", tournament_id, "rounds", "round_2.csv")
    with open(round2_path, "r", encoding="utf-8") as f:
        round2_rows = list(csv.DictReader(f))
    players_in_round2 = {row["player1"] for row in round2_rows}
    players_in_round2.update(row["player2"] for row in round2_rows if row["player2"] != "BYE")
    assert dropout_player not in players_in_round2


def test_seven_players_round_three_avoids_repeat_pairings_after_bye(client, seeded_random):
    tournament_id = _start_tables_tournament(client, ["A", "B", "C", "D", "E", "F", "G"], table_size=8)

    round1_rows = _complete_round_with_first_player_wins(client, tournament_id, 1)
    next_response = client.post("/mtg/next_round", follow_redirects=False)
    assert next_response.status_code in (302, 303)

    round2_rows = _complete_round_with_first_player_wins(client, tournament_id, 2)
    next_response = client.post("/mtg/next_round", follow_redirects=False)
    assert next_response.status_code in (302, 303)

    round3_rows = _read_round(tournament_id, 3)
    previous_pairs = _non_bye_pairs(round1_rows) | _non_bye_pairs(round2_rows)
    assert _non_bye_pairs(round3_rows).isdisjoint(previous_pairs)


def test_bye_is_not_repeated_while_other_players_have_none(client, seeded_random):
    tournament_id = _start_tables_tournament(client, ["A", "B", "C", "D", "E", "F", "G"], table_size=8)

    round1_rows = _complete_round_with_first_player_wins(client, tournament_id, 1)
    client.post("/mtg/next_round", follow_redirects=False)
    round2_rows = _complete_round_with_first_player_wins(client, tournament_id, 2)
    client.post("/mtg/next_round", follow_redirects=False)
    round3_rows = _read_round(tournament_id, 3)

    byes = _bye_players(round1_rows) + _bye_players(round2_rows) + _bye_players(round3_rows)
    assert len(byes) == len(set(byes))


def test_even_player_count_generates_no_bye(client, seeded_random):
    tournament_id = _start_tables_tournament(client, ["A", "B", "C", "D", "E", "F"], table_size=6)

    round1_rows = _complete_round_with_first_player_wins(client, tournament_id, 1)
    assert not _bye_players(round1_rows)

    next_response = client.post("/mtg/next_round", follow_redirects=False)
    assert next_response.status_code in (302, 303)
    round2_rows = _read_round(tournament_id, 2)
    assert not _bye_players(round2_rows)


def test_generate_swiss_pairings_is_deterministic():
    sorted_players = ["A", "B", "C", "D", "E", "F", "G"]
    points_by_player = {"A": 6, "B": 6, "C": 3, "D": 3, "E": 3, "F": 0, "G": 0}
    opponents_by_player = {
        "A": [("B", 1), ("C", 2)],
        "B": [("A", 1), ("D", 2)],
        "C": [("D", 1), ("A", 2)],
        "D": [("C", 1), ("B", 2)],
        "E": [("F", 1), ("G", 2)],
        "F": [("E", 1), ("BYE", 2)],
        "G": [("BYE", 1), ("E", 2)],
    }
    bye_counts_by_player = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 1, "G": 1}

    first = generate_swiss_pairings(sorted_players, points_by_player, opponents_by_player, bye_counts_by_player)
    second = generate_swiss_pairings(sorted_players, points_by_player, opponents_by_player, bye_counts_by_player)

    assert first == second


def test_env_pairing_seed_is_scoped_by_tournament_id(monkeypatch):
    monkeypatch.setenv("MTG_PAIRING_SEED", "12345")
    players = ["A", "B", "C", "D", "E", "F", "G"]

    first = _stable_shuffle(players, tournament_id="tournament-a", stage="start-table", round_number=1)
    second = _stable_shuffle(players, tournament_id="tournament-b", stage="start-table", round_number=1)
    repeated = _stable_shuffle(players, tournament_id="tournament-a", stage="start-table", round_number=1)

    assert first == repeated
    assert first != second
