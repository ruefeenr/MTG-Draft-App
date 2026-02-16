import csv
import json
import os
import tempfile
import unittest
from contextlib import contextmanager

from app import create_app
from app.player_stats import get_player_statistics
from app.tournament_groups import (
    DEFAULT_CUBE_ID,
    get_cube_name,
    is_vintage_tournament,
    is_valid_cube_id,
    load_allowed_cubes,
    load_tournament_meta,
    normalize_cube_id,
)


@contextmanager
def temp_cwd():
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield tmp
        finally:
            os.chdir(old_cwd)


class TournamentCubeTests(unittest.TestCase):
    def _start_tournament(self, client, cube_id):
        response = client.post(
            "/pair",
            data={
                "players": ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"],
                "group_sizes": ["6"],
                "tournament_group": "liga",
                "tournament_cube": cube_id,
            },
            follow_redirects=False,
        )
        self.assertIn(response.status_code, (302, 303))
        with client.session_transaction() as sess:
            tournament_id = sess.get("tournament_id")
        self.assertTrue(tournament_id)
        return tournament_id

    def test_allowed_cubes_validation(self):
        self.assertTrue(is_valid_cube_id("vintage"))
        self.assertTrue(is_valid_cube_id("spicy_ramen"))
        self.assertTrue(is_valid_cube_id("pauper"))
        self.assertTrue(is_valid_cube_id("100_ornithopter"))
        self.assertTrue(is_valid_cube_id("treat_yourself"))
        self.assertFalse(is_valid_cube_id("legacy"))
        self.assertEqual(normalize_cube_id("legacy"), DEFAULT_CUBE_ID)

    def test_meta_migration_adds_cube_id_and_name(self):
        with temp_cwd():
            os.makedirs("data", exist_ok=True)
            meta_path = os.path.join("data", "tournament_meta.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "abc": {
                            "group_id": "liga",
                            "group_name": "Liga",
                            "cube": "Vintage",
                            "created_at": "2025-01-01T00:00:00",
                        }
                    },
                    f,
                )

            meta = load_tournament_meta()
            self.assertIn("abc", meta)
            self.assertEqual(meta["abc"]["cube_id"], "vintage")
            self.assertEqual(meta["abc"]["cube_name"], "Vintage")

            with open(meta_path, "r", encoding="utf-8") as f:
                persisted = json.load(f)
            self.assertEqual(persisted["abc"]["cube_id"], "vintage")
            self.assertEqual(persisted["abc"]["cube_name"], "Vintage")
            self.assertNotIn("cube", persisted["abc"])

    def test_pair_persists_cube_id_and_name(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            tournament_id = self._start_tournament(client, "spicy_ramen")

            meta = load_tournament_meta()
            self.assertEqual(meta[tournament_id]["cube_id"], "spicy_ramen")
            self.assertEqual(meta[tournament_id]["cube_name"], get_cube_name("spicy_ramen"))

    def test_end_tournament_results_include_cube_payload(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            tournament_id = self._start_tournament(client, "pauper")

            round_path = os.path.join("data", tournament_id, "rounds", "round_1.csv")
            rows = []
            with open(round_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                if "score_draws" not in fieldnames:
                    fieldnames.append("score_draws")
                for row in reader:
                    row["score1"] = "2"
                    row["score2"] = "0"
                    row["score_draws"] = "0"
                    rows.append(row)

            with open(round_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            response = client.post("/end_tournament", follow_redirects=False)
            self.assertEqual(response.status_code, 200)

            result_path = os.path.join("tournament_results", f"{tournament_id}_results.json")
            self.assertTrue(os.path.exists(result_path))
            with open(result_path, "r", encoding="utf-8") as f:
                result_payload = json.load(f)

            tournament_data = result_payload["tournament_data"]
            self.assertEqual(tournament_data["cube_id"], "pauper")
            self.assertEqual(tournament_data["cube_name"], get_cube_name("pauper"))

    def test_non_vintage_round_view_hides_power_nine_ui(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            self._start_tournament(client, "pauper")
            response = client.get("/round/1")
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertNotIn("Power Nine hinzufügen", html)
            self.assertNotIn("Power Nine Karten zuweisen", html)

    def test_legacy_meta_without_cube_defaults_to_vintage(self):
        with temp_cwd():
            os.makedirs("data", exist_ok=True)
            meta_path = os.path.join("data", "tournament_meta.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "legacy_tournament": {
                            "group_id": "liga",
                            "group_name": "Liga",
                            "created_at": "2025-01-01T00:00:00",
                        }
                    },
                    f,
                )

            self.assertTrue(is_vintage_tournament("legacy_tournament"))
            meta = load_tournament_meta()
            self.assertEqual(meta["legacy_tournament"]["cube_id"], "vintage")

    def test_player_statistics_cube_filter_and_vintage_power_nine(self):
        with temp_cwd():
            os.makedirs("data/t_vintage", exist_ok=True)
            os.makedirs("data/t_pauper", exist_ok=True)
            os.makedirs("tournament_data", exist_ok=True)
            with open("data/tournament_meta.json", "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "t_vintage": {
                            "group_id": "liga",
                            "group_name": "Liga",
                            "cube_id": "vintage",
                            "cube_name": "Vintage",
                            "created_at": "2025-01-01T00:00:00",
                        },
                        "t_pauper": {
                            "group_id": "liga",
                            "group_name": "Liga",
                            "cube_id": "pauper",
                            "cube_name": "Pauper",
                            "created_at": "2025-01-02T00:00:00",
                        },
                    },
                    f,
                )

            with open("tournament_data/results.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["Tournament", "Player 1", "Player 2", "Score 1", "Score 2", "Draws"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Tournament": "t_vintage",
                        "Player 1": "Alice",
                        "Player 2": "Bob",
                        "Score 1": "2",
                        "Score 2": "1",
                        "Draws": "0",
                    }
                )
                writer.writerow(
                    {
                        "Tournament": "t_pauper",
                        "Player 1": "Alice",
                        "Player 2": "Carol",
                        "Score 1": "2",
                        "Score 2": "0",
                        "Draws": "0",
                    }
                )

            with open("data/t_vintage/tournament_power_nine.json", "w", encoding="utf-8") as f:
                json.dump({"Alice": {"Black Lotus": True}}, f)
            with open("data/t_pauper/tournament_power_nine.json", "w", encoding="utf-8") as f:
                json.dump({"Alice": {"Time Walk": True}}, f)

            stats_all = get_player_statistics("Alice", cube_filter="all")
            stats_vintage = get_player_statistics("Alice", cube_filter="vintage")
            stats_pauper = get_player_statistics("Alice", cube_filter="pauper")

            self.assertEqual(stats_all["total_matches"], 2)
            self.assertEqual(stats_all["power_nine_total"], 0)

            self.assertEqual(stats_vintage["total_matches"], 1)
            self.assertEqual(stats_vintage["power_nine_total"], 1)
            self.assertEqual(stats_vintage["power_nine_counts"]["Black Lotus"], 1)

            self.assertEqual(stats_pauper["total_matches"], 1)
            self.assertEqual(stats_pauper["power_nine_total"], 0)

    def test_non_vintage_power_nine_api_is_safe_without_file(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()
            self._start_tournament(client, "pauper")

            response = client.get("/api/player/Alice/power_nine")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload["success"])
            self.assertEqual(payload["player_name"], "Alice")
            self.assertTrue(all(value is False for value in payload["power_nine"].values()))

    def test_can_create_custom_cube_and_home_contains_it(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            create_response = client.post(
                "/cubes/create",
                data={"cube_name": "Legacy Cube"},
                follow_redirects=True,
            )
            self.assertEqual(create_response.status_code, 200)

            cubes = load_allowed_cubes()
            cube_names = {cube["name"] for cube in cubes}
            self.assertIn("Legacy Cube", cube_names)

            home = client.get("/")
            self.assertEqual(home.status_code, 200)
            self.assertIn("Legacy Cube", home.get_data(as_text=True))

    def test_delete_custom_cube_reassigns_tournaments_to_vintage(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            client.post("/cubes/create", data={"cube_name": "Legacy Cube"}, follow_redirects=True)
            cubes = load_allowed_cubes()
            legacy_cube = next((cube for cube in cubes if cube["name"] == "Legacy Cube"), None)
            self.assertIsNotNone(legacy_cube)

            response = client.post(
                "/pair",
                data={
                    "players": ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"],
                    "group_sizes": ["6"],
                    "tournament_group": "liga",
                    "tournament_cube": legacy_cube["id"],
                },
                follow_redirects=False,
            )
            self.assertIn(response.status_code, (302, 303))

            with client.session_transaction() as sess:
                tournament_id = sess.get("tournament_id")
            self.assertTrue(tournament_id)

            delete_response = client.post(
                "/cubes/delete",
                data={"cube_id": legacy_cube["id"]},
                follow_redirects=True,
            )
            self.assertEqual(delete_response.status_code, 200)

            meta = load_tournament_meta()
            self.assertEqual(meta[tournament_id]["cube_id"], "vintage")
            self.assertEqual(meta[tournament_id]["cube_name"], "Vintage")


if __name__ == "__main__":
    unittest.main()
