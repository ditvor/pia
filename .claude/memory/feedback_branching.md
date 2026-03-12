---
name: Always use feature branches
description: Never commit directly to main — all changes go through a feature branch and PR per CONTRIBUTING.md
type: feedback
---

Always create a feature branch before making any changes, no matter how small. This includes chore commits like adding LICENSE files, updating .gitignore, or any other "trivial" change.

**Why:** The project follows CONTRIBUTING.md strictly — nothing goes to main directly.

**How to apply:**
1. `git checkout -b <prefix>/<description>` before touching any file
2. Commit on the branch
3. `git push -u origin <branch>`
4. Open a PR with `gh pr create`
5. Never use `git push origin main` to push new commits
