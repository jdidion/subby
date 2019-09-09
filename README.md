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
# `Processes` object that can be used to inspect and control
# the process(es).
p1 = subby.run([["grep foo", "wc -l"]], stdin=input_bytes)
p2 = subby.run(("grep foo", "wc -l"), stdin=input_bytes)
p3 = subby.run("grep foo | wc -l", stdin=input_bytes)

# The `done` property tells us whether the processes have finished
assert p1.done and p2.done and p3.done

# The `output` property provides the output of the command
assert p1.output == p2.output == p3.output == b"1"
```

By default, the `run` function blocks until the processes are finshed running. This behavior can be changed by passing `block=False`, in which case, the caller is responsible for checking the status and/or calling the `Processes.block()` method manually.

```python
import subby
import time

p = subby.run("sleep 10", block=False)
for i in range(5):
    if p.done:
        break
    else:
        time.sleep(1)
else:
    # A timeout can be used to kill the process if it doesn't
    # complete in a certain amount of time. By default, block()
    # raises an error if the return code is non-zero.
    p.block(timeout=10, raise_on_error=False)
    
    # The process can also be killed manually.
    p.kill()

# The `Processes.ok` property is True if the processes have
# finished and the return code is 0.
if not p.ok:
    # The `Processes.output` and `Processes.error` properties
    # provide access to the process stdout and stderr.
    print(f"The command failed: stderr={p.error}")
```

Subby supports several different types of arguments for stdin, stdout, and stderr:

* A file: specified as a `pathlib.Path`; for stdin, the content is read from the file, whereas for stdout/stderr the content is written to the file (and is thus not available via the `output`/`error` properties).-->
* A bytes string: for stdin, the bytes are written to a temporary file, which is passed to the process stdin.
* One of the values provided by the `StdType` enumeration:
    * PIPE: for stdout/stderr, `subprocess.PIPE` is used, giving the caller direct access to the process stdout/stderr streams.
    * BUFFER: for stdout/stderr, a temporary file is used, and the contents are made available via the `output`/`error` properties after the process completes.
    * SYS: stdin/stdout/stderr is passed through from the main process (i.e. the `sys.stdin/sys.stdout/sys.stderr` streams).
