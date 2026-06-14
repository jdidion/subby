# Changes

## dev

* Modernize packaging: PEP 621 `pyproject.toml` with the setuptools build backend and setuptools-scm for git-tag-derived versions; manage the project with uv
* Require Python 3.10+ (drop 3.6-3.9)
* Expose `subby.__version__` via `importlib.metadata`
* Replace Travis CI with a GitHub Actions workflow; add ruff lint config
* Add tests covering previously-untested branches (branch coverage 95.8% to 98.0%)

## 0.1.7 (2019.12.17)

* Expose `stdin_stream` property on `Process`

## 0.1.6 (2019.09.24)

* Check for redundant/invalid popen kwargs
* Enable default values for `timeout` and `raise_on_error` to be passed to the `Processes` constructor

## 0.1.5 (2019.09.15)

* Bugfixes

## 0.1.4 (2019.09.15)

* Change `sub` to take either a command or sequence of commands
 
## 0.1.3 (2019.09.15)

* Added mode parameter to specify raw (bytes) vs text mode
* Added `sub` convenience function
* Added tests
* Blackened code

## 0.1.2 (2019.09.09)

* Add ability to specify alternative allowed returncodes

## 0.1.1 (2019.09.09)

* Add ability to specify stdin

## 0.1.0 (2019.09.09)

* First release