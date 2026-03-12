# Contributing to PIA

## Branching model

All work happens on feature branches. Nothing goes to `main` directly.

```
main                        ← production-ready, protected
  └── feature/phase-2-graph-db
  └── fix/youtrack-auth-edge-case
  └── chore/update-deps
```

Branch naming:

| Prefix | Use for |
|---|---|
| `feature/` | New functionality |
| `fix/` | Bug fixes |
| `chore/` | Dependencies, CI, tooling |
| `docs/` | Documentation only |

---

## Day-to-day workflow

### 1. Start from a fresh main

```bash
git checkout main
git pull origin main
```

### 2. Create a branch

```bash
git checkout -b feature/my-thing
```

### 3. Make changes and commit

Keep commits small and focused. Each commit should leave the tests passing.

```bash
git add src/pia/agent/router.py tests/test_agent/test_router.py
git commit -m "feat: handle sprint ID in message router"
```

**Commit message format:**

```
<type>: <short description>

Optional longer explanation if the why isn't obvious.
```

Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`

### 4. Run tests before pushing

```bash
pytest -xvs
```

All tests must pass. No real API calls are made — the suite runs fully offline.

### 5. Push and open a pull request

```bash
git push -u origin feature/my-thing
gh pr create --title "feat: handle sprint ID in message router" --body "..."
```

### 6. CI runs automatically

GitHub Actions runs the full test suite on Python 3.10, 3.11, and 3.12.
The PR cannot be merged until all checks are green.

### 7. Merge and clean up

After approval and green CI, merge on GitHub. Delete the branch:

```bash
git checkout main
git pull origin main
git branch -d feature/my-thing
```

---

## Reverting changes

| Goal | Command |
|---|---|
| Undo last commit (keep changes) | `git reset HEAD~1` |
| Revert a commit safely | `git revert <sha>` |
| Roll back a merged PR | `git revert -m 1 <merge-sha>` |
| Recover lost work | `git reflog` |

`git revert` is always preferred over `git reset` for anything already pushed — it creates a new commit that undoes the change, leaving full history intact.

---

## Tagging releases

```bash
git tag v0.2.0
git push origin v0.2.0
```

---

## Secrets

Never commit credentials, tokens, or API keys. They belong in:
- Environment variables (`YOUTRACK_TOKEN`, `ANTHROPIC_API_KEY`, etc.)
- `~/.pia/config.yaml` (listed in `.gitignore`, never tracked)

If a secret is accidentally committed, treat it as compromised and rotate it immediately.
