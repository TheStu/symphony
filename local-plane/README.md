# Local Plane and Symphony

From a checkout of this fork in ~/dev/symphony, build the Elixir app with
`cd elixir && mix setup && mix build`. From the checkout root run
`local-plane/install`. This creates local configuration and private credentials
under ~/dev/agent-workspace. Set AGENT_WORKSPACE to choose another directory.
Requirements include Python 3.8+, Docker Compose, Git, an authenticated Codex CLI
and the repository toolchain. For GitHub PRs configure Git push access and gh auth.
Enable browser/test tooling for each project as described by its AGENTS.md.

From ~/dev/agent-workspace:

1. Run `./up` to start the persistent Plane CE board at http://localhost:8090.
2. Finish Plane instance setup, create your workspace and project, and generate a
   personal API key in your account settings.
3. Run `./board connect book ~/dev/book`. Enter the workspace slug, project UUID
   and API key at the local prompts. This prepares the board states and workflow.
4. Run `./up book` and drag a card to Ready. A separate clone is created under
   workspaces/book. One card runs at a time in that profile. Read the PR and tests
   in Review, or answer a question in Blocked. Move the card back to Ready for revisions.
5. Run `./down --drain` to finish active work across profiles and stop Plane,
   preserving the database, uploads, branches and review workspaces.

Each profile has an editable WORKFLOW.md, private key file, runner.log and logs/.
The dashboard address is printed on startup. A profile's optional database-url file
sets DATABASE_URL and RAILS_ENV=test for that runner. Use a dedicated database and
test data. Review tracked files and integrations before authorizing a repo for
unattended use. To add another repository repeat connect and up with another name.

At connection time the launcher compares the local commit to the Git remote's
default branch. Matching commits use GitHub draft PRs. If they differ, a new card
clones the named local branch from its latest committed tip, removes its remote
and leaves a review commit in the card workspace. The card links the work by workspace path and commit. Done retains these local workspaces. Uncommitted changes
in the source checkout are excluded.

For visual changes, save PNG screenshots in the card checkout under
`tmp/review/PL-<number>/`. Moving the card to Review via Symphony uploads
the files as Plane attachments and posts an inline gallery in the activity feed.
Repeated handoffs reuse published screenshots. The local Plane proxy serves
both the board and its object storage.

Move a reviewed card to **Approved** to authorize its recorded commit for merge.
The worker merges into the configured local branch or GitHub PR target, posts the verified commit and moves the card to Done. Send design revisions to Ready.
