# Release Checklist

## Pre-release

1. Update `CHANGELOG.md`.
2. Update version in:
   - `pyproject.toml`
   - `setup.py`
   - `src/github_ai_radar/__init__.py`
3. Run tests:

```bash
python -m compileall src tests
python -m pytest -q
github-ai-radar doctor
```

4. Run a small smoke report:

```bash
github-ai-radar run --once --max-candidates 5 --deep-review-limit 2
```

5. Confirm no local artifacts are staged:

```bash
git status --short
```

## GitHub Release

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

GitHub Actions should build the package and attach artifacts to the release.

## Package Release

Planned target:

```bash
python -m build
twine upload dist/*
```

PyPI publishing is not enabled yet.
