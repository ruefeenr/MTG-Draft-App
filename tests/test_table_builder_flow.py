import csv
import json
import os
import tempfile
import unittest
from contextlib import contextmanager

from app import create_app
from app.tournament_groups import load_tournament_meta


@contextmanager
def temp_cwd():
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield tmp
        finally:
            os.chdir(old_cwd)


class TableBuilderFlowTests(unittest.TestCase):
    def test_start_tables_creates_separate_tournaments_per_block(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            payload = [
                {
                    "table_size": 6,
                    "group_id": "liga",
                    "cube_id": "vintage",
                    "players": ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"],
                },
                {
                    "table_size": 8,
                    "group_id": "casual",
                    "cube_id": "pauper",
                    "players": ["Gina", "Hank", "Iris", "John", "Kara", "Liam", "Mona"],
                },
            ]
            response = client.post(
                "/start_tables",
                data={"tables_payload": json.dumps(payload)},
                follow_redirects=False,
            )
            self.assertIn(response.status_code, (302, 303))

            meta = load_tournament_meta()
            self.assertEqual(len(meta), 2)
            values = list(meta.values())
            self.assertTrue(any(v.get("group_id") == "liga" and v.get("cube_id") == "vintage" for v in values))
            self.assertTrue(any(v.get("group_id") == "casual" and v.get("cube_id") == "pauper" for v in values))

    def test_odd_players_receive_bye_match_in_round_one(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            payload = [
                {
                    "table_size": 8,
                    "group_id": "liga",
                    "cube_id": "vintage",
                    "players": ["A", "B", "C", "D", "E", "F", "G"],
                }
            ]
            response = client.post(
                "/start_tables",
                data={"tables_payload": json.dumps(payload)},
                follow_redirects=False,
            )
            self.assertIn(response.status_code, (302, 303))

            with client.session_transaction() as sess:
                tournament_id = sess.get("tournament_id")
            self.assertTrue(tournament_id)

            round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
            self.assertTrue(os.path.exists(round_path))
            with open(round_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            bye_rows = [row for row in rows if row.get("player2") == "BYE"]
            self.assertEqual(len(bye_rows), 1)
            self.assertEqual(bye_rows[0].get("score1"), "2")
            self.assertEqual(bye_rows[0].get("score2"), "0")
            self.assertEqual(bye_rows[0].get("score_draws"), "0")

    def test_prepare_route_removed(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()
            response = client.get("/prepare")
            self.assertEqual(response.status_code, 404)

    def test_index_contains_new_table_builder_elements(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("tableBuilderForm", html)
            self.assertIn("tablesPayload", html)
            self.assertIn("Weiteren Tisch hinzufügen", html)
            self.assertIn("addTestPlayers(", html)

    def test_index_includes_known_player_autocomplete_and_fuzzy_logic(self):
        with temp_cwd():
            os.makedirs("data/players", exist_ok=True)
            with open("data/players/players_data.json", "w", encoding="utf-8") as f:
                json.dump({"Enrique": {"power_nine_count": 0}, "Chrigi": {"power_nine_count": 0}}, f)

            app = create_app()
            client = app.test_client()
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('datalist id="knownPlayersList"', html)
            self.assertIn('<option value="Enrique"></option>', html)
            self.assertIn("findClosestKnownName", html)
            self.assertIn("Ähnlicher Name gefunden", html)


if __name__ == "__main__":
    unittest.main()
