# AGENTS.md

Guidance for agents working in the `subby` repository.

## Project

`subby` is a small, dependency-free Python library that simplifies running
subprocesses (single commands and pipes). The public API lives in
`subby/__init__.py` (`run`, `cmd`, `sub`); the implementation is in
`subby/core.py` (`Processes`, `StdType`) and `subby/utils.py`.

## Toolchain

- Trunk branch: `main`.
- Packaging: PEP 621 `pyproject.toml`, `setuptools` build backend.
- Version: dynamic, derived from git tags by `setuptools-scm` (writes
  `subby/_version.py` at build time, which is git-ignored). Do not hand-edit a
  version anywhere.
- Environment / runner: `uv`.

## Build / test / lint

```sh
uv sync                                   # create/refresh the dev environment
uv run pytest                             # run the test suite
uv run pytest --cov --cov-report=term-missing   # with coverage
uv run ruff check subby tests             # lint
uv run ruff format subby tests            # format
uv build                                  # produce sdist + wheel in dist/
```

`make test`, `make lint`, `make build`, and `make clean` wrap these.

## Release

Releases are version-by-tag: tag the commit (`vX.Y.Z`), then `uv build` and
`uv publish`. Tagging, pushing, and publishing touch shared state and are done
by a human, not an agent.

## Conventions

- Requires Python >= 3.10.
- No third-party runtime dependencies. Keep it that way unless there is a
  strong reason.
- The library exposes `__version__` via `importlib.metadata`.
