You are working on {{ issue.identifier }}: {{ issue.title }}.
{{ issue.description }}

Use plane_card comments to read feedback on every run. Move this card to In progress.
Follow the repository's AGENTS.md and preserve its architecture. Reuse the current
branch on retry or revision. Implement this card
only. Run relevant tests, inspect your own diff, and commit your changes. For UI,
verify in the browser and save current PNG screenshots in tmp/review/{{ issue.identifier }}/.
Moving the card to Review publishes those images directly on the card.

{{HANDOFF}}
Then move the card to Review as the final action. Do not merge or deploy.
If blocked, post the specific question or failed check and move the card to Blocked
as the final action. On restart read existing comments and check the branch
before repeating any operation.
