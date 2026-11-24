import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

board = runpy.run_path(str(Path(__file__).with_name("board")))


class ProfileTest(unittest.TestCase):
    def test_connect_preserves_private_key_and_uses_existing_state_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profiles" / "books"
            profile.mkdir(parents=True)
            calls = []

            def fake_api(url, token, body=None):
                self.assertEqual(token, "local-private-key")
                if body:
                    calls.append(body["name"])
                    return {}
                if "cursor=" in url:
                    return {"results": [{"name": "Done"}], "next_page_results": False}
                return {"results": [{"name": "In Progress"}], "next_page_results": True, "next_cursor": "2:4:0"}

            setup = board["setup"]
            with patch.dict(setup.__globals__, {"ROOT": root, "api": fake_api}), \
                    patch("builtins.input", side_effect=["books", "e1344d17-79fe-473b-8131-8428bd5a5651"]), \
                    patch("getpass.getpass", return_value="local-private-key"), \
                    patch("subprocess.check_output", return_value="git@example.org:org/books.git\n"):
                setup(profile, root)
                with self.assertRaisesRegex(SystemExit, "already connected"):
                    setup(profile, root)
            self.assertEqual(calls, ["Ready", "Review", "Blocked"])
            workflow = (profile / "WORKFLOW.md").read_text()
            config = json.loads(workflow.split("---")[1])
            self.assertEqual(config["workspace"]["root"], str(root / "workspaces/books"))
            self.assertEqual(config["agent"]["max_concurrent_agents"], 1)
            self.assertNotIn("local-private-key", workflow)
            self.assertEqual((profile / "key").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
