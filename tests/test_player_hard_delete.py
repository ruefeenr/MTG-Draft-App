import json
import os

from app.models import Match, Player
from app.player_stats import delete_player


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


def test_hard_delete_removes_player_and_freezes_match_name(app, client):
    _start_tournament(client)

    with app.app_context():
        alice = Player.query.filter_by(name="Alice").first()
        assert alice is not None
        alice_id = alice.id

        affected_matches = Match.query.filter(
            (Match.player1_id == alice_id) | (Match.player2_id == alice_id)
        ).all()
        assert affected_matches

        assert delete_player("Alice") is True

        assert Player.query.filter_by(name="Alice").first() is None
        assert Match.query.filter(
            (Match.player1_id == alice_id) | (Match.player2_id == alice_id)
        ).count() == 0

        snapshots = Match.query.filter(
            (Match.player1_name_snapshot == "Alice") | (Match.player2_name_snapshot == "Alice")
        ).all()
        assert snapshots

    players_page = client.get("/players")
    assert players_page.status_code == 200
    html = players_page.get_data(as_text=True)
    assert "Alice" not in html


def test_player_delete_dialog_text_is_simplified(client):
    _start_tournament(client)
    profile = client.get("/player/Bob")
    assert profile.status_code == 200
    html = profile.get_data(as_text=True)
    assert "Alle Spielerdaten einschließlich Power Nine Informationen werden permanent gelöscht." not in html
    assert "Die Turnierhistorie bleibt erhalten, aber dieser Spieler wird nicht mehr in der Spielerliste erscheinen." not in html
    assert "Bitte gib den Namen des Spielers ein, um den Löschvorgang zu bestätigen:" not in html


def test_players_list_ignores_legacy_files_after_hard_delete(app, client):
    _start_tournament(client)
    with app.app_context():
        assert delete_player("Alice") is True

    os.makedirs("data/players", exist_ok=True)
    os.makedirs("tournament_data", exist_ok=True)
    with open("data/players/players_data.json", "w", encoding="utf-8") as f:
        json.dump({"Alice": {"power_nine_count": 99}, "LegacyGhost": {"power_nine_count": 1}}, f)
    with open("tournament_data/results.csv", "w", encoding="utf-8", newline="") as f:
        f.write("Tournament,Player 1,Player 2,Score 1,Score 2,Draws\n")
        f.write("t1,Alice,Bob,2,1,0\n")

    response = client.get("/players")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Alice" not in html
    assert "LegacyGhost" not in html


def test_player_profile_redirects_when_player_is_missing(client):
    response = client.get("/player/this-player-does-not-exist", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/players" in response.headers.get("Location", "")
