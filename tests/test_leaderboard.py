import csv
import os

from app.routes import calculate_leaderboard


def _write_round_csv(tournament_id, round_number, matches):
    rounds_dir = os.path.join("data", tournament_id, "rounds")
    os.makedirs(rounds_dir, exist_ok=True)
    path = os.path.join(rounds_dir, f"round_{round_number}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
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
        writer.writerows(matches)


def test_leaderboard_points_and_bye_exclusion(golden_fixtures):
    fixture = golden_fixtures("5p_2r_with_bye.json")
    tournament_id = fixture["tournament_id"]
    for idx, round_matches in enumerate(fixture["rounds"], start=1):
        _write_round_csv(tournament_id, idx, round_matches)

    leaderboard = calculate_leaderboard(tournament_id, 2)
    names = [entry[0] for entry in leaderboard]
    assert "BYE" not in names

    by_name = {entry[0]: entry for entry in leaderboard}
    assert by_name["Alice"][1] == 6
    assert by_name["Bob"][1] == 3
    assert by_name["Carol"][1] == 0
    assert by_name["Dave"][1] == 3
    assert by_name["Eve"][1] == 6


def test_leaderboard_tiebreaker_orders_equal_points_by_omw_then_gw():
    tournament_id = "44444444-4444-4444-4444-444444444444"
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
                "dropout1": "false",
                "dropout2": "false",
                "table_size": "6",
                "group_key": "6-A",
            },
            {
                "table": "2",
                "player1": "Carol",
                "player2": "Dave",
                "score1": "2",
                "score2": "1",
                "score_draws": "0",
                "dropout1": "false",
                "dropout2": "false",
                "table_size": "6",
                "group_key": "6-A",
            },
        ],
    )
    _write_round_csv(
        tournament_id,
        2,
        [
            {
                "table": "1",
                "player1": "Alice",
                "player2": "Dave",
                "score1": "2",
                "score2": "0",
                "score_draws": "0",
                "dropout1": "false",
                "dropout2": "false",
                "table_size": "6",
                "group_key": "6-A",
            },
            {
                "table": "2",
                "player1": "Bob",
                "player2": "Carol",
                "score1": "2",
                "score2": "0",
                "score_draws": "0",
                "dropout1": "false",
                "dropout2": "false",
                "table_size": "6",
                "group_key": "6-A",
            },
        ],
    )

    leaderboard = calculate_leaderboard(tournament_id, 2)
    names = [entry[0] for entry in leaderboard]
    # Bob und Carol haben beide 3 Punkte, Bob hat stärkere Gegnerbilanz.
    assert names.index("Bob") < names.index("Carol")
