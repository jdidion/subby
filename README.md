Subby is a small Python library with the goal of simplifying the use of subprocesses.

Subby was inspired by [delegator.py](https://github.com/amitt001/delegator.py), but it adds a few additional features and excludes others (e.g. no `pexpect` support). Subby was originally written as part of the [dxpy.sugar](https://github.com/dnanexus/dx-toolkit/tree/SCI-1321_dx_sugar/src/python/dxpy/sugar) package, but because it is (hopefully) useful more generally, it is being made available as a separate package.

## Requirements

The only requirement is python 3.6+. There are no other 3rd-party runtime dependencies. The `pytest` and `coverage` packages are required for testing.

## Installation

`pip install subby`

## Usage

Subby's primary interface is the `chain` function. It takes a list of commands and executes them. If there is are multiple commands, they are chained (i.e. piped) together.

```python
import subby

p = subby.chain("grep foo | wc -l", stdin=True)
