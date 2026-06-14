module = subby
tests = tests

.PHONY: all install test lint format build clean

all: clean install test

install:
	uv sync

test:
	uv run pytest --cov --cov-report=term-missing --cov-report=xml $(tests)

lint:
	uv run ruff check $(module) $(tests)

format:
	uv run ruff format $(module) $(tests)

build: clean
	uv build

clean:
	rm -Rf dist build $(module).egg-info
	rm -Rf .pytest_cache .ruff_cache
	find . -name '__pycache__' -type d -prune -exec rm -Rf {} +

# Release is driven by tagging: setuptools-scm derives the version from the
# git tag, so cut a release by tagging and pushing the tag, then `uv build`
# and `uv publish`. These steps touch shared state and are run by a human.
