You are working on {{ issue.identifier }}: {{ issue.title }}.
{{ issue.description }}

{% if issue.state == "Approved" %}
The reviewer approved this revision. Call plane_card move Done. The host will merge
the recorded revision into the configured target, verify the merge and post the result.
Do not edit the reviewed branch first. On a content conflict, integrate the latest
target ({{MERGE_TARGET}}) in the card workspace, resolve it, run relevant checks, post the new commit
and return it to Review for another approval. If unrelated local edits, permissions
or branch protection prevent landing, explain the blocker on the card and move it
to Blocked. Never move a card to Approved yourself.
{% else %}
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
{% endif %}
