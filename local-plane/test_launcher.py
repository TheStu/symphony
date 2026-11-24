import json
from pathlib import Path
import runpy
import subprocess
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
            with patch.dict(setup.__globals__, {"ROOT": root, "api": fake_api, "checkout_plan": lambda repo: ("git clone sample .", "github")}), \
                    patch("builtins.input", side_effect=["books", "e1344d17-79fe-473b-8131-8428bd5a5651"]), \
                    patch("getpass.getpass", return_value="local-private-key"):
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

    def test_unpublished_branch_is_reviewed_locally_from_its_committed_tip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin, repo, workspace = (root / part for part in ["origin", "book", "PL-2"])
            subprocess.run(["git", "init", "-q", "--bare", origin], check=True)
            subprocess.run(["git", "clone", "-q", origin, repo], check=True)
            subprocess.run(["git", "-C", repo, "-c", "user.name=Test", "-c", "user.email=t@example.test",
                            "commit", "-qm", "Local commit", "--allow-empty"], check=True)
            (repo / "uncommitted").write_text("personal work in progress")
            hook, mode = board["checkout_plan"](repo)
            self.assertEqual(mode, "local")
            workspace.mkdir()
            subprocess.run(["sh", "-c", hook], cwd=workspace, check=True)
            self.assertFalse((workspace / "uncommitted").exists())
            self.assertEqual(subprocess.check_output(["git", "-C", workspace, "remote"]), b"")
            self.assertEqual(subprocess.check_output(["git", "-C", workspace, "branch", "--show-current"]).strip(), b"symphony/PL-2")


if __name__ == "__main__":
    unittest.main()
