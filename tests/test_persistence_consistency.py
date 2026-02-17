import csv
import os

from app.db import db
from app.models import Match, Round, Tournament


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


def test_round1_sync_creates_tournament_round_and_match_rows(client, app):
    tournament_id = _start_tournament(client)
    round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
    with open(round_path, "r", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) > 0

    with app.app_context():
        tournament = db.session.get(Tournament, tournament_id)
        assert tournament is not None
        round_row = Round.query.filter_by(tournament_id=tournament_id, number=1).first()
        assert round_row is not None
        db_matches = Match.query.filter_by(round_id=round_row.id).all()
        assert len(db_matches) == len(csv_rows)


def test_save_results_updates_csv_and_db_consistently(client, app):
    tournament_id = _start_tournament(client)
    round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
    with open(round_path, "r", encoding="utf-8") as f:
        first = next(csv.DictReader(f))

    response = client.post(
        "/save_results",
        data={
            "table": first["table"],
            "player1": first["player1"],
            "player2": first["player2"],
            "score1": "2",
            "score2": "1",
            "score_draws": "0",
            "current_round": "1",
            "dropout1": "false",
            "dropout2": "false",
            "table_size": first.get("table_size", "6"),
        },
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True

    with open(round_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    changed = [row for row in rows if row["table"] == first["table"]][0]
    assert changed["score1"] == "2"
    assert changed["score2"] == "1"
    assert changed.get("score_draws", "0") == "0"

    with app.app_context():
        round_row = Round.query.filter_by(tournament_id=tournament_id, number=1).first()
        assert round_row is not None
        match_row = Match.query.filter_by(round_id=round_row.id, table_number=int(first["table"])).first()
        assert match_row is not None
        assert match_row.score1 == 2
        assert match_row.score2 == 1
        assert match_row.score_draws == 0

    results_file = os.path.join("tournament_data", "results.csv")
    with open(results_file, "r", encoding="utf-8") as f:
        line_count_before_reload = sum(1 for _ in f)
    assert line_count_before_reload >= 2

    # Reload/Load darf keine neuen Ergebniszeilen erzeugen.
    client.get(f"/load_tournament/{tournament_id}", follow_redirects=False)
    client.get("/round/1", follow_redirects=False)

    with open(results_file, "r", encoding="utf-8") as f:
        line_count_after_reload = sum(1 for _ in f)
    assert line_count_after_reload == line_count_before_reload
