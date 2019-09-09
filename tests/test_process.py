import logging
import os
logging.basicConfig(level=os.environ.get("LOGLEVEL", "WARNING"))

import contextlib
from pathlib import Path
import tempfile
import shutil
import subprocess
import sys
import time
from typing import Iterable

import pytest

import subby


@contextlib.contextmanager
def isolated_dir(*args, **kwargs) -> Iterable[Path]:
    curdir = Path.cwd()
    d = Path(tempfile.mkdtemp(*args, **kwargs))
    os.chdir(d)
    try:
        yield d
    finally:
        os.chdir(curdir)
        shutil.rmtree(d)


def test_run():
    with isolated_dir():
        p = subby.run(
            ["echo -n 'foo'", "gzip"], stdout="foo.txt.gz", block=True
        )
        assert p.done and p.closed
        assert b"foo" == subby.run(
                ["gunzip -c foo.txt.gz", "cat"], block=True
            ).output


def test_run_noblock():
    with isolated_dir():
        p = subby.run(
            ["echo -n 'foo'", "gzip"], stdout="foo.txt.gz", block=False
        )
        assert not p.done
        p.block()
        assert p.done and p.closed
        assert b"foo" == subby.run(
                ["gunzip -c foo.txt.gz", "cat"], block=True
            ).output


def test_run_str_command():
    with isolated_dir():
        p = subby.run(
            "echo -n 'foo' | gzip", stdout="foo.txt.gz", block=True
        )
        assert p.done and p.closed
        assert b"foo" == subby.run(
            "gunzip -c foo.txt.gz | cat", block=True
        ).output


def test_shell():
    with pytest.raises(FileNotFoundError):
        # We expect FileNotFound because exit is a shell-specific command and won't
        # be recognized unless we run in the shell
        subby.run("exit 2")

    try:
        subby.run("exit 2", shell="/bin/sh")
        raise AssertionError("Expected error")
    except subprocess.CalledProcessError as err:
        assert err.returncode == 2

    try:
        subby.run("exit 2", shell=True)
        raise AssertionError("Expected error")
    except subprocess.CalledProcessError as err:
        assert err.returncode == 2


def test_state_errors():
    p = subby.Processes([["echo", "hi"]], stdout=False, stderr=False)
    with pytest.raises(RuntimeError):
        p.stdout_stream
    with pytest.raises(RuntimeError):
        p.stderr_stream
    with pytest.raises(RuntimeError):
        p.get_all_stderr()
    with pytest.raises(RuntimeError):
        p.block()
    with pytest.raises(RuntimeError):
        p.close()
    p.run(echo=True)
    with pytest.raises(RuntimeError):
        p.run()
    p.block()
    with pytest.raises(RuntimeError):
        p.block()


def test_stderr_stdout():
    p = subby.Processes([["echo", "hi"]], stdout=None, stderr=None)
    p.run(echo=True)
    p.block()
    assert p._stdout_type is subby.StdType.OTHER
    assert p._stderr_type is subby.StdType.OTHER
    assert p.stdout_stream is None
    assert p.stderr_stream is None
    with pytest.raises(RuntimeError):
        p.output
    with pytest.raises(RuntimeError):
        p.error

    p = subby.Processes(
        [["echo", "hi"]],
        stdout=subby.StdType.BUFFER,
        stderr=subby.StdType.BUFFER
    )
    p.run(echo=True)
    p.block(close=False)
    assert p._stdout_type is subby.StdType.BUFFER
    assert p._stderr_type is subby.StdType.BUFFER
    assert p.stdout_stream is not None
    assert p.stderr_stream is not None
    with pytest.raises(RuntimeError):
        p.output
    with pytest.raises(RuntimeError):
        p.error
    p.close()
    assert p.output == b"hi\n"
    assert p.error == b""

    p = subby.Processes(
        [["echo", "hi"]],
        stdout=subby.StdType.BUFFER,
        stderr=subby.StdType.BUFFER
    )
    p.run(echo=True)
    p.block()
    assert p._stdout_type is subby.StdType.BUFFER
    assert p._stderr_type is subby.StdType.BUFFER
    assert p.stdout_stream is not None
    assert p.stderr_stream is not None
    assert p.output == b"hi\n"
    assert p.error == b""

    with pytest.raises(ValueError):
        p = subby.Processes([["echo", "hi"]], stdout=subby.StdType.FILE)
        p.run()


def test_stdin():
    p = subby.Processes([["grep", "hi"]], stdin=b"hi")
    p.run()
    p.block()

    # We have to use a tempfile to mock stdin - an io.BytesIO doesn't work
    # because the fileno method is called
    with isolated_dir() as d:
        mock_stdin = d / "stdin"
        with open(mock_stdin, "wb") as out:
            out.write(b"hi")
        cur_stdin = sys.stdin
        try:
            with open(mock_stdin, "rb") as inp:
                sys.stdin = inp
                p = subby.Processes([["grep", "hi"]], stdin=subby.StdType.SYS)
                p.run()
                p.block()
                assert p.output == b"hi"
        finally:
            sys.stdin = cur_stdin


def test_files():
    with isolated_dir() as d:
        stdout = d / "stdout"
        stderr = d / "stderr"
        p = subby.Processes([["echo", "hi"]], stdout=stdout, stderr=stderr)
        p.run(echo=True)
        p.block()
        assert (str(p)) == f"echo hi > {stdout}"
        assert p._stdout_type is subby.StdType.FILE
        assert p._stderr_type is subby.StdType.FILE
        assert p.stdout_stream is not None
        assert p.stderr_stream is not None
        with pytest.raises(RuntimeError):
            p.output
        with pytest.raises(RuntimeError):
            p.error
        with open(stdout, "rb") as inp:
            assert inp.read() == b"hi\n"
        with open(stderr, "rb") as inp:
            assert inp.read() == b""


def test_rc():
    with pytest.raises(RuntimeError):
        subby.Processes([]).returncode

    p = subby.Processes([["echo", "hi"], ["cat", "foo"]])
    p.run()
    while p.returncode is None:
        time.sleep(1)
    assert p.returncode == 1

    p = subby.Processes([["cat", "foo"], ["echo", "hi"]])
    p.run()
    while p.returncode is None:
        time.sleep(1)
    assert p.returncode == 1

    p = subby.Processes([["echo", "hi"], ["cat", "foo"]])
    p.run()
    try:
        p.block()
        raise AssertionError("Expected a CalledProcessError")
    except subprocess.CalledProcessError as err:
        assert err.returncode == 1


def test_kill():
    p = subby.Processes([["echo", "hi"]])
    p.run()
    p.block()
    assert not p.kill()
    assert p.returncode == 0

    p = subby.Processes([["sleep", "5"]])
    p.run()
    assert p.kill()
    assert p.returncode != 0

    with subby.Processes([["sleep", "5"]]) as p:
        pass
    assert p.closed
    assert p.returncode != 0


def test_readme_examples():
    # We can pass input to the stdin of the command as bytes
    input_bytes = b"foo\nbar"

    # The following three commands are equivalent; each returns a
    # `subby.Processes` object that can be used to inspect and control
    # the process(es).
    p1 = subby.run([["grep", "foo"], ["wc", "-l"]], stdin=input_bytes)
    p2 = subby.run(("grep foo", "wc -l"), stdin=input_bytes)
    p3 = subby.run("grep foo | wc -l", stdin=input_bytes)

    # The `done` property tells us whether the processes have finished
    assert p1.done and p2.done and p3.done

    # The `output` property provides the output of the command
    assert p1.output == p2.output == p3.output == b"1"
