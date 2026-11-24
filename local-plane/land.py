"""Capture reviewed revisions and land them only after approval in Plane."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def run(repo, *cmd):
    result = subprocess.run(cmd, cwd=repo, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or f"{cmd[0]} failed").strip())
    return result.stdout.strip()


def git(repo, *args):
    return run(repo, "git", *args)


def ancestor(repo, older, newer):
    return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=repo).returncode == 0


def local_merge(repo, branch, card, sha):
    if git(repo, "branch", "--show-current") != branch:
        raise RuntimeError(f"The review target must have {branch} checked out.")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "fetch", "--no-tags", "--no-write-fetch-head", str(card), sha)
    if ancestor(repo, sha, base):
        return base
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        if (repo / git(repo, "rev-parse", "--git-path", marker)).exists():
            raise RuntimeError(f"A Git operation is active in {repo}.")
    candidate = sha
    if not ancestor(repo, base, sha):
        # Construct the merge before touching the destination index or worktree.
        tree = git(repo, "merge-tree", "--write-tree", base, sha)
        candidate = git(repo, "commit-tree", tree, "-p", base, "-p", sha, "-m", f"Merge reviewed card {card.name}")
    if git(repo, "rev-parse", "HEAD") != base or git(repo, "branch", "--show-current") != branch:
        raise RuntimeError("Target branch changed during landing. Retry approval.")
    git(repo, "-c", "merge.autoStash=false", "merge", "--no-overwrite-ignore", "--ff-only", candidate)
    if not ancestor(repo, sha, "HEAD"):
        raise RuntimeError("Approved revision is missing from the target.")
    return git(repo, "rev-parse", "HEAD")


def pull_request(repo, ref):
    fields = "number,headRefOid,headRefName,isCrossRepository,baseRefName,isDraft,state,mergeCommit"
    return json.loads(run(repo, "gh", "pr", "view", ref, "--json", fields))


def github_merge(repo, record):
    ref = str(record["pr"])
    pr = pull_request(repo, ref)
    if pr["headRefOid"] != record["sha"] or pr["baseRefName"] != record["branch"] or pr["isCrossRepository"]:
        raise RuntimeError("The PR changed after review. Submit the updated revision for review.")
    if pr["state"] != "MERGED":
        if pr["isDraft"]:
            run(repo, "gh", "pr", "ready", ref)
        run(repo, "gh", "pr", "merge", ref, "--merge", "--match-head-commit", record["sha"])
        pr = pull_request(repo, ref)
    if pr["state"] != "MERGED" or not pr["mergeCommit"]:
        raise RuntimeError("GitHub has not confirmed the PR merge. Check pending branch protections or merge queue.")
    return pr["mergeCommit"]["oid"]


def reviewed(card, settings):
    branch = f"symphony/{card.name}"
    if git(card, "branch", "--show-current") != branch or git(card, "status", "--porcelain"):
        raise RuntimeError("Expected a clean, committed card branch.")
    record = {"sha": git(card, "rev-parse", "HEAD"), "branch": settings["branch"]}
    if settings["mode"] == "github":
        pr = pull_request(Path(settings["repo"]), branch)
        if (pr["headRefOid"] != record["sha"] or pr["headRefName"] != branch or pr["isCrossRepository"]
                or pr["baseRefName"] != record["branch"] or pr["state"] != "OPEN"):
            raise RuntimeError("The draft PR must match the reviewed branch, commit and target.")
        record["pr"] = pr["number"]
    return record


def save(path, record):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        json.dump(record, stream)
    os.replace(stream.name, path)


def api(url, body=None):
    req = Request(url, data=None if body is None else json.dumps(body).encode(),
                  headers={"X-API-Key": os.environ["PLANE_API_KEY"], "Content-Type": "application/json"})
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def transition(profile, identifier, url, action):
    if not re.fullmatch(r"PL-\d+", identifier):
        raise ValueError("Invalid card identifier")
    config = json.loads((profile / "WORKFLOW.md").read_text().split("---", 2)[1])
    settings = config["tracker"]["provider"]["landing"]
    root = Path(config["workspace"]["root"])
    card = root / identifier
    if card.resolve() != root.resolve() / identifier:
        raise ValueError("Unexpected card workspace")
    path = profile / "reviewed" / identifier
    if action == "review":
        save(path, reviewed(card, settings))
        return
    if action != "done" or api(url + "?expand=state")["state"]["name"].casefold() != "approved":
        raise RuntimeError("The reviewer must move the card to Approved before landing.")
    record = json.loads(path.read_text())
    if record["sha"] != git(card, "rev-parse", "HEAD") or record["branch"] != settings["branch"]:
        raise RuntimeError("The card or target changed after review. Return the revision to Review.")
    repo = Path(settings["repo"])
    if settings["mode"] == "local":
        merged = local_merge(repo, record["branch"], card, record["sha"])
    else:
        merged = github_merge(repo, record)
    body = {"comment_html": f"<p>Merged reviewed commit <code>{record['sha']}</code>. Verified merge <code>{merged}</code>.</p>",
            "external_source": "symphony-landing", "external_id": f"{identifier}:{record['sha']}"}
    try:
        api(url + "comments/", body)
    except HTTPError as exc:
        if exc.code != 409:
            raise


if __name__ == "__main__":
    try:
        transition(Path(sys.argv[1]), *sys.argv[2:])
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        sys.exit(str(exc))
