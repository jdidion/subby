[![Travis CI](https://travis-ci.com/jdidion/subby.svg?branch=master)](https://travis-ci.com/jdidion/subby)
[![Code Coverage](https://codecov.io/gh/jdidion/subby/branch/master/graph/badge.svg)](https://codecov.io/gh/jdidion/subby)

Subby is a small Python library with the goal of simplifying the use of subprocesses.

Subby was inspired by [delegator.py](https://github.com/amitt001/delegator.py), but it adds a few additional features and excludes others (e.g. no `pexpect` support). Subby was originally written as part of the [dxpy.sugar](https://github.com/dnanexus/dx-toolkit/tree/SCI-1321_dx_sugar/src/python/dxpy/sugar) package, but because it is (hopefully) useful more generally, it is being made available as a separate package.

## Requirements

The only requirement is python 3.6+. There are no other 3rd-party runtime dependencies. The `pytest` and `coverage` packages are required for testing.

## Installation

`pip install subby`

## Usage

Subby's primary interface is the `run` function. It takes a list of commands and executes them. If there is are multiple commands, they are chained (i.e. piped) together.

```python
import subby

# We can pass input to the stdin of the command as bytes
input_bytes = b"foo\nbar"

# The following three commands are equivalent; each returns a
# `subby.Processes` object that can be used to inspect and control
# the process(es).
p1 = subby.run([["grep foo", "wc -l"]], stdin=input_bytes)
p2 = subby.run(("grep foo", "wc -l"), stdin=input_bytes)
p3 = subby.run("grep foo | wc -l", stdin=input_bytes)

# The `done` property tells us whether the processes have finished
assert p1.done and p2.done and p3.done

# The `output` property provides the output of the command
assert p1.output == p2.output == p3.output == b"1"
```

