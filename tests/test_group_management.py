import os
import tempfile
import unittest
from contextlib import contextmanager

from app import create_app
from app.tournament_groups import DEFAULT_GROUP_ID, load_tournament_groups, load_tournament_meta


@contextmanager
def temp_cwd():
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield tmp
        finally:
            os.chdir(old_cwd)


class GroupManagementTests(unittest.TestCase):
    def _create_group(self, client, name):
        response = client.post(
            "/groups/create",
            data={"group_name": name},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def _find_group_id_by_name(self, group_name):
        groups = load_tournament_groups()
        for group in groups:
            if group["name"] == group_name:
                return group["id"]
        return None

    def test_can_create_multiple_leagues(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            self._create_group(client, "Liga Winter 25/26")
            self._create_group(client, "Liga Sommer 26")

            groups = load_tournament_groups()
            names = {group["name"] for group in groups}
            self.assertIn("Liga Winter 25/26", names)
            self.assertIn("Liga Sommer 26", names)

    def test_tournament_dropdown_contains_custom_groups(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            self._create_group(client, "Liga Winter 25/26")
            self._create_group(client, "Liga Sommer 26")

            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("Liga Winter 25/26", html)
            self.assertIn("Liga Sommer 26", html)

    def test_can_rename_group_and_reject_duplicate_name(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            self._create_group(client, "Liga Winter 25/26")
            self._create_group(client, "Liga Sommer 26")
            winter_id = self._find_group_id_by_name("Liga Winter 25/26")
            self.assertTrue(winter_id)

            rename_response = client.post(
                "/groups/rename",
                data={"group_id": winter_id, "group_name": "Liga Herbst 26"},
                follow_redirects=True,
            )
            self.assertEqual(rename_response.status_code, 200)
            renamed_groups = load_tournament_groups()
            names = {group["name"] for group in renamed_groups}
            self.assertIn("Liga Herbst 26", names)
            self.assertNotIn("Liga Winter 25/26", names)

            duplicate_response = client.post(
                "/groups/rename",
                data={"group_id": winter_id, "group_name": "Liga Sommer 26"},
                follow_redirects=True,
            )
            self.assertEqual(duplicate_response.status_code, 200)
            html = duplicate_response.get_data(as_text=True)
            self.assertIn("existiert bereits", html)

    def test_delete_group_reassigns_existing_tournaments_to_default(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            self._create_group(client, "Liga Winter 25/26")
            group_id = self._find_group_id_by_name("Liga Winter 25/26")
            self.assertTrue(group_id)
            self.assertNotEqual(group_id, DEFAULT_GROUP_ID)

            response = client.post(
                "/pair",
                data={
                    "players": ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"],
                    "group_sizes": ["6"],
                    "tournament_group": group_id,
                    "tournament_cube": "vintage",
                },
                follow_redirects=False,
            )
            self.assertIn(response.status_code, (302, 303))

            with client.session_transaction() as sess:
                tournament_id = sess.get("tournament_id")
            self.assertTrue(tournament_id)

            response = client.post(
                "/groups/delete",
                data={"group_id": group_id},
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)

            meta = load_tournament_meta()
            self.assertEqual(meta[tournament_id]["group_id"], DEFAULT_GROUP_ID)
            self.assertEqual(meta[tournament_id]["group_name"], "Unkategorisiert")

            home = client.get("/")
            self.assertEqual(home.status_code, 200)
            self.assertIn("Unkategorisiert", home.get_data(as_text=True))

    def test_default_group_cannot_be_deleted_or_renamed(self):
        with temp_cwd():
            app = create_app()
            client = app.test_client()

            delete_response = client.post(
                "/groups/delete",
                data={"group_id": DEFAULT_GROUP_ID},
                follow_redirects=True,
            )
            self.assertEqual(delete_response.status_code, 200)
            self.assertIn("kann nicht gelöscht werden", delete_response.get_data(as_text=True))

            rename_response = client.post(
                "/groups/rename",
                data={"group_id": DEFAULT_GROUP_ID, "group_name": "Neu"},
                follow_redirects=True,
            )
            self.assertEqual(rename_response.status_code, 200)
            self.assertIn("kann nicht umbenannt werden", rename_response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
