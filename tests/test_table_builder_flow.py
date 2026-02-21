import csv
import json
import os
import tempfile
import unittest
from contextlib import contextmanager

from app import create_app
from app.db import db
from app.models import Player
from app.services.normalize import normalize_name
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

            with client.session_transaction() as sess:
                primary_tournament_id = sess.get("tournament_id")
            self.assertTrue(primary_tournament_id)
            self.assertIn(primary_tournament_id, meta)

            primary_groups_file = os.path.join("data", primary_tournament_id, "player_groups.json")
            self.assertTrue(os.path.exists(primary_groups_file))
            with open(primary_groups_file, "r", encoding="utf-8") as f:
                primary_groups = json.load(f)
            primary_players = {p for players in primary_groups.values() for p in players}
            self.assertEqual(primary_players, set(payload[0]["players"]))

    def test_start_tables_rejects_duplicate_players_across_tables(self):
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
                    "players": ["Alice", "Gina", "Hank", "Iris", "John", "Kara", "Liam"],
                },
            ]

            response = client.post(
                "/start_tables",
                data={"tables_payload": json.dumps(payload)},
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("Spieler dürfen nicht in mehreren Tischen sein", html)

            meta = load_tournament_meta()
            self.assertEqual(len(meta), 0)

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

    def test_odd_players_receive_bye_for_10_and_12_player_tables(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            scenarios = [
                (10, ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9"]),
                (12, ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9", "Q10", "Q11"]),
            ]

            for table_size, players in scenarios:
                payload = [
                    {
                        "table_size": table_size,
                        "group_id": "liga",
                        "cube_id": "vintage",
                        "players": players,
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

    def test_start_tables_rejects_odd_player_counts_below_six(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            payload = [
                {
                    "table_size": 6,
                    "group_id": "liga",
                    "cube_id": "vintage",
                    "players": ["Alice", "Bob", "Carol", "Dave", "Eve"],
                }
            ]
            response = client.post(
                "/start_tables",
                data={"tables_payload": json.dumps(payload)},
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("Ungerade Spielerzahlen sind erst ab 6 Spielern erlaubt", html)

    def test_start_tables_persists_pairing_mode_in_meta(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()
            payload = [
                {
                    "table_size": 6,
                    "group_id": "liga",
                    "cube_id": "vintage",
                    "players": ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"],
                }
            ]
            response = client.post(
                "/start_tables",
                data={"tables_payload": json.dumps(payload), "pairing_mode": "manual"},
                follow_redirects=False,
            )
            self.assertIn(response.status_code, (302, 303))
            with client.session_transaction() as sess:
                tournament_id = sess.get("tournament_id")
            meta = load_tournament_meta()
            self.assertEqual(meta[tournament_id].get("pairing_mode"), "manual")

    def test_save_round_pairings_swaps_players_before_round_start(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()
            payload = [
                {
                    "table_size": 6,
                    "group_id": "liga",
                    "cube_id": "vintage",
                    "players": ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"],
                }
            ]
            start_response = client.post(
                "/start_tables",
                data={"tables_payload": json.dumps(payload)},
                follow_redirects=False,
            )
            self.assertIn(start_response.status_code, (302, 303))
            with client.session_transaction() as sess:
                tournament_id = sess.get("tournament_id")
            round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
            with open(round_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            non_bye_rows = [row for row in rows if row.get("player2") != "BYE"]
            self.assertGreaterEqual(len(non_bye_rows), 2)
            table_a = non_bye_rows[0]["table"]
            table_b = non_bye_rows[1]["table"]
            a_p1 = non_bye_rows[0]["player1"]
            b_p1 = non_bye_rows[1]["player1"]

            submitted = []
            for row in rows:
                row_copy = {"table": row["table"], "player1": row["player1"], "player2": row["player2"]}
                if row["table"] == table_a:
                    row_copy["player1"] = b_p1
                elif row["table"] == table_b:
                    row_copy["player1"] = a_p1
                submitted.append(row_copy)

            save_response = client.post(
                "/round/1/save_pairings",
                data={"matches_json": json.dumps(submitted)},
                follow_redirects=False,
            )
            self.assertEqual(save_response.status_code, 200)
            body = save_response.get_json()
            self.assertTrue(body.get("success"))

            with open(round_path, "r", encoding="utf-8") as f:
                updated_rows = list(csv.DictReader(f))
            updated_by_table = {row["table"]: row for row in updated_rows}
            self.assertEqual(updated_by_table[table_a]["player1"], b_p1)
            self.assertEqual(updated_by_table[table_b]["player1"], a_p1)

    def test_save_round_pairings_noop_keeps_round_file_unchanged(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()
            payload = [
                {
                    "table_size": 6,
                    "group_id": "liga",
                    "cube_id": "vintage",
                    "players": ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"],
                }
            ]
            start_response = client.post(
                "/start_tables",
                data={"tables_payload": json.dumps(payload)},
                follow_redirects=False,
            )
            self.assertIn(start_response.status_code, (302, 303))
            with client.session_transaction() as sess:
                tournament_id = sess.get("tournament_id")
            round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")

            with open(round_path, "r", encoding="utf-8") as f:
                before_content = f.read()
            with open(round_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            submitted = [{"table": row["table"], "player1": row["player1"], "player2": row["player2"]} for row in rows]
            save_response = client.post(
                "/round/1/save_pairings",
                data={"matches_json": json.dumps(submitted)},
                follow_redirects=False,
            )
            self.assertEqual(save_response.status_code, 200)
            body = save_response.get_json()
            self.assertTrue(body.get("success"))
            self.assertIn("Keine Änderungen", body.get("message", ""))

            with open(round_path, "r", encoding="utf-8") as f:
                after_content = f.read()
            self.assertEqual(after_content, before_content)

    def test_save_round_pairings_preserves_existing_bye_result_fields(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()
            payload = [
                {
                    "table_size": 8,
                    "group_id": "liga",
                    "cube_id": "vintage",
                    "players": ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Gina"],
                }
            ]
            start_response = client.post(
                "/start_tables",
                data={"tables_payload": json.dumps(payload)},
                follow_redirects=False,
            )
            self.assertIn(start_response.status_code, (302, 303))
            with client.session_transaction() as sess:
                tournament_id = sess.get("tournament_id")
            round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
            with open(round_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            bye_row = next(row for row in rows if row.get("player2") == "BYE")
            bye_table = bye_row["table"]
            bye_snapshot = {
                "player1": bye_row.get("player1", ""),
                "player2": bye_row.get("player2", ""),
                "score1": bye_row.get("score1", ""),
                "score2": bye_row.get("score2", ""),
                "score_draws": bye_row.get("score_draws", ""),
            }

            non_bye_rows = [row for row in rows if row.get("player2") != "BYE"]
            self.assertGreaterEqual(len(non_bye_rows), 2)
            table_a = non_bye_rows[0]["table"]
            table_b = non_bye_rows[1]["table"]
            a_p1 = non_bye_rows[0]["player1"]
            b_p1 = non_bye_rows[1]["player1"]

            submitted = []
            for row in rows:
                row_copy = {"table": row["table"], "player1": row["player1"], "player2": row["player2"]}
                if row["table"] == table_a:
                    row_copy["player1"] = b_p1
                elif row["table"] == table_b:
                    row_copy["player1"] = a_p1
                submitted.append(row_copy)

            save_response = client.post(
                "/round/1/save_pairings",
                data={"matches_json": json.dumps(submitted)},
                follow_redirects=False,
            )
            self.assertEqual(save_response.status_code, 200)
            body = save_response.get_json()
            self.assertTrue(body.get("success"))

            with open(round_path, "r", encoding="utf-8") as f:
                updated_rows = list(csv.DictReader(f))
            updated_by_table = {row["table"]: row for row in updated_rows}
            updated_bye = updated_by_table[bye_table]
            self.assertEqual(updated_bye.get("player1", ""), bye_snapshot["player1"])
            self.assertEqual(updated_bye.get("player2", ""), bye_snapshot["player2"])
            self.assertEqual(updated_bye.get("score1", ""), bye_snapshot["score1"])
            self.assertEqual(updated_bye.get("score2", ""), bye_snapshot["score2"])
            self.assertEqual(updated_bye.get("score_draws", ""), bye_snapshot["score_draws"])

    def test_save_round_pairings_rejected_after_round_started(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()
            payload = [
                {
                    "table_size": 6,
                    "group_id": "liga",
                    "cube_id": "vintage",
                    "players": ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"],
                }
            ]
            start_response = client.post(
                "/start_tables",
                data={"tables_payload": json.dumps(payload)},
                follow_redirects=False,
            )
            self.assertIn(start_response.status_code, (302, 303))
            with client.session_transaction() as sess:
                tournament_id = sess.get("tournament_id")
            round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
            with open(round_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            normal_row = next(row for row in rows if row.get("player2") != "BYE")
            client.post(
                "/save_results",
                data={
                    "table": normal_row["table"],
                    "player1": normal_row["player1"],
                    "player2": normal_row["player2"],
                    "table_size": normal_row["table_size"],
                    "score1": "2",
                    "score2": "1",
                    "score_draws": "0",
                    "current_round": "1",
                    "dropout1": "false",
                    "dropout2": "false",
                },
                follow_redirects=False,
            )

            submitted = [{"table": row["table"], "player1": row["player1"], "player2": row["player2"]} for row in rows]
            save_response = client.post(
                "/round/1/save_pairings",
                data={"matches_json": json.dumps(submitted)},
                follow_redirects=False,
            )
            self.assertEqual(save_response.status_code, 400)
            body = save_response.get_json()
            self.assertIn("bereits gestartet", body.get("message", ""))

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
            app = create_app()
            client = app.test_client()
            with app.app_context():
                db.session.add(Player(name="Enrique", normalized_name=normalize_name("Enrique")))
                db.session.add(Player(name="Chrigi", normalized_name=normalize_name("Chrigi")))
                db.session.commit()
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('datalist id="knownPlayersList"', html)
            self.assertIn('<option value="Enrique"></option>', html)
            self.assertIn("findClosestKnownName", html)
            self.assertIn("Ähnlicher Name gefunden", html)

    def test_index_hides_deleted_players_from_autocomplete_and_fuzzy_source(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()
            with app.app_context():
                db.session.add(Player(name="Enrique", normalized_name=normalize_name("Enrique")))
                db.session.add(
                    Player(
                        name="DELETED_PLAYER_123abc",
                        normalized_name=normalize_name("DELETED_PLAYER_123abc"),
                    )
                )
                db.session.commit()
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('<option value="Enrique"></option>', html)
            self.assertNotIn("DELETED_PLAYER_123abc", html)

    def test_players_list_hides_deleted_players(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()
            with app.app_context():
                db.session.add(Player(name="Valentin", normalized_name=normalize_name("Valentin")))
                db.session.add(
                    Player(
                        name="DELETED_PLAYER_deadbe",
                        normalized_name=normalize_name("DELETED_PLAYER_deadbe"),
                    )
                )
                db.session.commit()
            response = client.get("/players")
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("Valentin", html)
            self.assertNotIn("DELETED_PLAYER_deadbe", html)


if __name__ == "__main__":
    unittest.main()
