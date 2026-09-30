# Git Flow

## Branches

- `main`: releases only. Updated by PR from `develop`.
- `develop`: integration branch. Updated only by PR from working branches.
- Working branches start from `develop` and use these prefixes: `feature/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`.
- Never commit or push directly to `main` or `develop`.

## Commits

- **Atomic:** one logical change per commit, and the tests pass at every commit.
- Use Conventional Commits: `type(scope): summary`, where type is `feat`, `fix`, `docs`, `test`, `refactor` or `chore`.
- **Before every commit**, run the `reviewer` agent on the staged diff. Fix blocking findings first.
- End every message with the attribution trailer from the session instructions.

## Pull requests

1. Run the `tester` agent and fix any failures.
2. Rebase onto the latest develop: `git fetch origin && git rebase origin/develop`.
3. Squash into 3–4 logical Conventional Commits, one per feature slice, each with its own tests and docs. Use `git reset --soft origin/develop` (only after step 2), then re-commit in groups (`git add <paths> && git commit`). Skip this when there are already 4 or fewer commits. Then `git push --force-with-lease`.
4. Open the PR into `develop` with `gh pr create --base develop`. The body summarizes what changed, how it was verified, and the decisions recorded in [[decisions]].
5. **Checkpoint:** post the summary to the user and wait for their OK.
6. Merge with rebase-and-merge (the only strategy enabled on the repo): `gh pr merge --rebase --delete-branch`. Then update the local `develop`.
