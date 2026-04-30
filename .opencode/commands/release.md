# /release

Bump the version, draft release notes, ask for approval, then trigger the
GitHub Actions release workflow via `gh workflow run`.

## Arguments

`$ARGUMENTS` has two space-separated parts:

```
/release <component> <version>
```

| Argument | Values | Example |
|---|---|---|
| `component` | `app` or `web` | `app` |
| `version` | `X.Y.Z` semver, **no** `v` prefix | `0.2.0` |

If either argument is missing or malformed, stop and show the correct usage.

---

## Steps

Follow these steps **in order**. Do not skip or reorder them.

### 1. Validate input

- `component` must be exactly `app` or `web`.
- `version` must match `MAJOR.MINOR.PATCH` (digits only, no `v` prefix).
- Derive the tag name: `<component>-v<version>` (e.g. `app-v0.2.0`).

### 2. Check working tree

Run `git status --short`. If there are uncommitted changes, stop and warn
the user to commit or stash first.

### 3. Check the tag does not already exist

```bash
git ls-remote --tags origin <tag>
```

If the tag already exists, stop and tell the user to choose a different version.

### 4. Determine the commit range

```bash
git tag --sort=-v:refname | grep "^<component>-v" | head -1
```

- If a previous tag exists for this component, range is `<prev_tag>..HEAD`.
- If none exists, range is the full history.

### 5. Collect commits in range

```bash
git log <range> --pretty=format:"%h %s" --no-merges
```

Group by conventional-commit prefix into sections:

| Prefix | Section |
|---|---|
| `feat:` / `feat(…):` | Features |
| `fix:` / `fix(…):` | Bug Fixes |
| `perf:` / `perf(…):` | Performance |
| `refactor:` / `refactor(…):` | Refactoring |
| `docs:` / `docs(…):` | Documentation |
| `test:` / `test(…):` | Tests |
| `chore:` / `chore(…):` | Chores |
| anything else | Other |

Strip the prefix/scope from each entry; keep the short hash as a
parenthetical. Example: `- Add agent drift detection (a1b2c3d)`.
Omit empty sections.

### 6. Draft release notes

Format:

```markdown
## What's Changed

### Features
- …

### Bug Fixes
- …

**Full Changelog**: https://github.com/<owner>/<repo>/compare/<prev_tag>…<tag>
```

- Derive the GitHub URL from `git remote get-url origin`.
- If there is no previous tag for this component, use:
  `**Full Changelog**: https://github.com/<owner>/<repo>/commits/<tag>`
- Omit empty sections.

### 7. Ask for permission

Show the user:
1. The version bump that will be applied (current → new).
2. The full drafted release notes.
3. This prompt:

> Ready to bump **`<component>`** to **`<version>`** (tag: `<tag>`) and
> trigger the release workflow. Proceed? **(yes / no / edit)**

**Stop and wait for the user's response.**

- `yes` → continue to step 8.
- `no` → abort, do nothing.
- `edit` → let the user supply revised notes, then ask again before continuing.

### 8. Bump version in the repository

**For `app`:**
- `app/version.txt` — overwrite with exactly `<version>\n`.
- `pyproject.toml` — replace the `version = "…"` line under `[project]`
  with `version = "<version>"`.

**For `web`:**
- `web/package.json` — replace the `"version": "…"` field with
  `"version": "<version>"`.

Commit the change:
```bash
git add <changed files>
git commit -m "chore: bump <component> version to <version>"
git push origin main
```

### 9. Trigger the GitHub Actions release workflow

```bash
gh workflow run release.yml \
  --field component=<component> \
  --field confirm=release
```

The workflow will:
- Read the version from the file(s) just committed.
- Create and push the tag `<tag>`.
- Create a GitHub release with auto-generated notes (`--generate-notes`).
- For `app`: build the web UI, package, upload the wheel/sdist, and publish to PyPI.

### 10. Confirm

After triggering, print:

```
Triggered release workflow for <tag>.
Monitor: https://github.com/<owner>/<repo>/actions/workflows/release.yml
```

Then run `gh run list --workflow=release.yml --limit=3` so the user can
see the queued run.
