---
applicable_to: Release a new version of OpenAgentd
description: Bump the version, open a PR, then trigger the GitHub Actions release workflow.
subtask: false
---

## Steps

### 1. Propose version bump

Read the current version from `app/version.txt`. Propose a patch increment
(e.g. `0.1.0` → `0.1.1`). Ask explicitly for a minor or major bump.

### 2. Check working tree

Run `git status --short`. Stop if there are uncommitted changes.

### 3. Ask for confirmation

> Ready to release **`<version>`**. Proceed? **(yes / no)**

**Stop and wait for the response.**

### 4. Bump version via pull request

```bash
git checkout -b release/v<version>
```

Update version in:
- `app/version.txt` — overwrite with `<version>\n`
- `pyproject.toml` — `version = "<version>"` under `[project]`
- `web/package.json` — `"version": "<version>"`

```bash
git add app/version.txt pyproject.toml web/package.json
git commit -m "chore: bump version to <version>"
git push origin release/v<version>
gh pr create --title "chore: bump version to <version>" --base main
```

Wait for CI to pass and the PR to be merged.

### 5. Trigger the release workflow

```bash
gh workflow run release.yml --field confirm=release
```

Then run `gh run list --workflow=release.yml --limit=3` to show the queued run.
