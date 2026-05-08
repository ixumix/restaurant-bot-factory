# CI workflow

GitHub Actions runs the same `ruff` + `mypy` + `pytest` triplet that you can run
locally with `make check`.

> **Why isn't the workflow file already committed?** Adding files under
> `.github/workflows/` requires the GitHub `workflow` OAuth scope, which the
> assistant that authored this PR doesn't have. Drop the YAML below into
> `.github/workflows/ci.yml` from your own machine (one push from a maintainer
> is enough — afterwards every PR will be checked automatically).

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  lint-test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: pyproject.toml

      - name: Install project (with dev extras)
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Ruff (lint)
        run: ruff check .

      - name: mypy (typecheck)
        run: mypy src

      - name: pytest
        run: pytest -q
```
