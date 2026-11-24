You are working on {{ issue.identifier }}: {{ issue.title }}.
{{ issue.description }}

Use plane_card comments to read feedback on every run. Move this card to In progress.
Follow the repository's AGENTS.md and preserve its architecture. Reuse the current
branch and any existing draft PR on retry or revision. If a fresh checkout already
has a remote branch for this card, check out that branch first. Implement this card
only. Run relevant tests, inspect your own diff, and commit your changes. For UI,
verify in the browser and include reviewable visual evidence.

Push the card branch, find its existing PR or create a draft PR, and verify its URL.
Leave a Plane comment with the PR URL, what changed, and actual test results.
Then move the card to Review as the final action. Do not merge or deploy.
If blocked, post the specific question or failed check and move the card to Blocked
as the final action. On restart read existing comments and check the branch/PR
before repeating any operation.
