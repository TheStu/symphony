import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from land import local_merge, transition


def git(repo, *args):
    return subprocess.check_output(["git", "-C", repo, *args], text=True).strip()


class LandingTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.target = Path(temp.name, "target")
        self.card = Path(temp.name, "PL-1")
        subprocess.run(["git", "init", "-q", "-b", "main", self.target], check=True)
        git(self.target, "commit", "--allow-empty", "-qm", "base")
        subprocess.run(["git", "clone", "-q", self.target, self.card], check=True)
        git(self.card, "switch", "-qc", "symphony/PL-1")
        (self.card / "card.txt").write_text("reviewed")
        git(self.card, "add", "card.txt")
        git(self.card, "commit", "-qm", "reviewed")
        self.sha = git(self.card, "rev-parse", "HEAD")

    def land(self):
        return local_merge(self.target, "main", self.card, self.sha)

    def test_diverged_target_and_unrelated_user_changes_survive_retry(self):
        git(self.target, "commit", "--allow-empty", "-qm", "other card")
        (self.target / "mine").write_text("unrelated")
        git(self.target, "add", "mine")
        self.land()
        merged = git(self.target, "rev-parse", "HEAD")
        self.land()
        self.assertEqual(git(self.target, "rev-parse", "HEAD"), merged)
        self.assertEqual(git(self.target, "diff", "--cached", "--name-only"), "mine")
        self.assertEqual((self.target / "card.txt").read_text(), "reviewed")


    def test_only_approved_recorded_sha_can_land(self):
        profile = self.card.parent / "profile"
        profile.mkdir()
        landing = {"mode": "local", "repo": str(self.target), "branch": "main"}
        config = {"workspace": {"root": str(self.card.parent)}, "tracker": {"provider": {"landing": landing}}}
        (profile / "WORKFLOW.md").write_text("---\n" + json.dumps(config) + "\n---\n")
        url = "http://localhost/card/"
        transition(profile, "PL-1", url, "review")
        with patch("land.api", return_value={"state": {"name": "Review"}}):
            with self.assertRaisesRegex(RuntimeError, "Approved"):
                transition(profile, "PL-1", url, "done")
        with patch("land.api", return_value={"state": {"name": "Approved"}}) as api:
            transition(profile, "PL-1", url, "done")
            self.assertEqual(git(self.target, "rev-parse", "HEAD"), self.sha)
            self.assertIn(self.sha, api.call_args.args[1]["comment_html"])
            git(self.card, "commit", "--allow-empty", "-qm", "unreviewed")
            with self.assertRaisesRegex(RuntimeError, "changed after review"):
                transition(profile, "PL-1", url, "done")
            self.assertEqual(git(self.target, "rev-parse", "HEAD"), self.sha)

    def test_conflict_leaves_target_unchanged(self):
        (self.target / "card.txt").write_text("other")
        git(self.target, "add", "card.txt")
        git(self.target, "commit", "-qm", "other")
        before = git(self.target, "rev-parse", "HEAD")
        with self.assertRaises(RuntimeError):
            self.land()
        self.assertEqual(git(self.target, "rev-parse", "HEAD"), before)
        self.assertEqual(git(self.target, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
