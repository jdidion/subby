import contextlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path

import pytest

import subby

logging.basicConfig(level=os.environ.get("LOGLEVEL", "WARNING"))


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


@pytest.mark.parametrize("mode,expected", [(bytes, b"foo"), (str, "foo")])
def test_run(mode, expected):
    with isolated_dir():
        p = subby.run(
            ["echo -n 'foo'", "gzip"], stdout=Path("foo.txt.gz"), block=True, mode=mode
        )
        assert p.done and p.closed
        assert (
            expected
            == subby.run(["gunzip -c foo.txt.gz", "cat"], block=True, mode=mode).output
        )


def test_sub():
    with pytest.raises(ValueError):
        subby.sub("grep foo | wc -l", stdin=b"foo\nbar", mode=bytes)
    with pytest.raises(ValueError):
        subby.sub("grep foo | wc -l", stdin="foo\nbar", block=False)
    assert subby.sub("grep foo | wc -l", stdin="foo\nbar") == "1"


def test_cmd():
    assert subby.cmd(["grep", "foo"], stdin="foo\nbar").output == "foo"


@pytest.mark.parametrize("mode,expected", [(bytes, b"foo"), (str, "foo")])
def test_run_noblock(mode, expected):
    with isolated_dir():
        p = subby.run(
            ["echo -n 'foo'", "gzip"], stdout=Path("foo.txt.gz"), block=False, mode=mode
        )
        assert not p.done
        assert p.stdin_type is subby.StdType.OTHER
        assert p.stdout_type is subby.StdType.FILE
        assert p.stderr_type is subby.StdType.PIPE
        p.block()
        assert p.done and p.closed
        assert (
            expected
            == subby.run(["gunzip -c foo.txt.gz", "cat"], block=True, mode=mode).output
        )


def test_timeout():
    p = subby.Processes([["sleep", "10"]])
    p.run()
    with pytest.raises(subprocess.TimeoutExpired):
        p.block(timeout=1)


@pytest.mark.parametrize("mode,expected", [(bytes, b"foo"), (str, "foo")])
def test_run_str_command(mode, expected):
    with isolated_dir():
        p = subby.run(
            "echo -n 'foo' | gzip", stdout=Path("foo.txt.gz"), block=True, mode=mode
        )
        assert p.done and p.closed
        assert (
            expected
            == subby.run("gunzip -c foo.txt.gz | cat", block=True, mode=mode).output
        )


def test_shell():
    with pytest.raises(FileNotFoundError):
        # We expect FileNotFound because exit is a shell-specific command and won't
        # be recognized unless we run in the shell
        subby.run("exit 2", shell=False)

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
    p = subby.Processes([["echo", "hi"]], stdout=None, stderr=None)
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

    with pytest.raises(ValueError):
        p = subby.Processes([["echo", "hi"]], stdout=subby.StdType.FILE)
        p.run()

    subby.Processes([["echo", "hi"]], mode=str, universal_newlines=True)
    subby.Processes([["echo", "hi"]], mode=str, text=True)
    subby.Processes([["echo", "hi"]], mode=bytes, universal_newlines=False)
    subby.Processes([["echo", "hi"]], mode=bytes, text=False)

    with pytest.raises(ValueError):
        subby.Processes([["echo", "hi"]], mode=str, universal_newlines=False)
    with pytest.raises(ValueError):
        subby.Processes([["echo", "hi"]], mode=str, text=False)
    with pytest.raises(ValueError):
        subby.Processes([["echo", "hi"]], mode=bytes, universal_newlines=True)
    with pytest.raises(ValueError):
        subby.Processes([["echo", "hi"]], mode=bytes, text=True)


@pytest.mark.parametrize(
    "mode,expected_stdout,expected_stderr", [(bytes, b"hi\n", b""), (str, "hi\n", "")]
)
def test_stderr_stdout(mode, expected_stdout, expected_stderr):
    p = subby.Processes(
        [["echo", "hi"]],
        stdout=subby.StdType.BUFFER,
        stderr=subby.StdType.BUFFER,
        mode=mode,
    )
    with pytest.raises(RuntimeError):
        p.stdin_type
    with pytest.raises(RuntimeError):
        p.stdout_type
    with pytest.raises(RuntimeError):
        p.stderr_type
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
    assert p.output == expected_stdout
    assert p.error == expected_stderr

    p = subby.Processes(
        [["echo", "hi"]],
        stdout=subby.StdType.BUFFER,
        stderr=subby.StdType.BUFFER,
        mode=mode,
    )
    p.run(echo=True)
    p.block()
    assert p._stdout_type is subby.StdType.BUFFER
    assert p._stderr_type is subby.StdType.BUFFER
    assert p.stdout_stream is not None
    assert p.stderr_stream is not None
    assert p.output == expected_stdout
    assert p.error == expected_stderr


@pytest.mark.parametrize("mode,expected", [(bytes, b"hi"), (str, "hi")])
def test_stdin_str(mode, expected):
    p = subby.Processes([["grep", "hi"]], stdin=b"hi", mode=mode)
    p.run()
    p.block()
    assert expected == p.output


@pytest.mark.parametrize("mode,expected", [(bytes, b"hi"), (str, "hi")])
def test_stdin_bytes(mode, expected):
    p = subby.Processes([["grep", "hi"]], stdin="hi", mode=mode)
    p.run()
    p.block()
    assert expected == p.output


@pytest.mark.parametrize("mode,expected", [(bytes, b"hi"), (str, "hi")])
def test_stdin_sys(mode, expected):
    # We have to use a tempfile to mock stdin - an io.BytesIO doesn't work
    # because the fileno method is called
    mode_str = "t" if mode is str else "b"
    with isolated_dir() as d:
        mock_stdin = d / "stdin"
        with open(mock_stdin, "w" + mode_str) as out:
            out.write(expected)
        cur_stdin = sys.stdin
        try:
            with open(mock_stdin, "r" + mode_str) as inp:
                sys.stdin = inp
                p = subby.Processes(
                    [["grep", "hi"]], stdin=subby.StdType.SYS, mode=mode
                )
                p.run()
                p.block()
                assert p.output == expected
        finally:
            sys.stdin = cur_stdin


def test_stdin_stream():
    p = subby.Processes([["cat"]], stdin=subby.StdType.PIPE, stdout=subby.StdType.PIPE)

    try:
        p.run()
        assert p.stdin_type == subby.StdType.PIPE
        stdin = p.stdin_stream
        stdout = p.stdout_stream
        stdin.write("hello\n")
        stdin.flush()
        assert stdout.readline() == "hello\n"
    finally:
        p.block()


@pytest.mark.parametrize(
    "mode,expected,expected_0", [(bytes, b"hi", b""), (str, "hi", "")]
)
def test_get_all_stderr(mode, expected, expected_0):
    # This command should write to stderr of the second and
    # third commands, and stdout of the third command
    p = subby.run("echo -n hi | tee /dev/stderr | tee /dev/stderr", mode=mode)
    assert p.output == expected
    assert p.get_all_stderr() == [expected_0, expected, expected]


@pytest.mark.parametrize(
    "mode,expected_stdout,expected_stderr", [(bytes, b"hi\n", b""), (str, "hi\n", "")]
)
def test_files(mode, expected_stdout, expected_stderr):
    with isolated_dir() as d:
        stdout = d / "stdout"
        stderr = d / "stderr"
        p = subby.Processes([["echo", "hi"]], stdout=stdout, stderr=stderr, mode=mode)
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
        mode_str = "t" if mode is str else "b"
        with open(stdout, "r" + mode_str) as inp:
            assert inp.read() == expected_stdout
        with open(stderr, "r" + mode_str) as inp:
            assert inp.read() == expected_stderr


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


@pytest.mark.parametrize("mode,expected", [(bytes, b"0"), (str, "0")])
def test_allowed_returncodes(mode, expected):
    with pytest.raises(subprocess.CalledProcessError):
        # This raises an exception because grep has a returncode of 1
        # when no lines match
        subby.run("echo foo | grep -c bar", mode=mode)

    assert (
        subby.run(
            "echo foo | grep -c bar", mode=mode, allowed_return_codes=(0, 1)
        ).output
        == expected
    )


def test_readme_examples():
    # We can pass input to the stdin of the command as bytes
    input_str = "foo\nbar"

    # The following three commands are equivalent; each returns a
    # `subby.Processes` object that can be used to inspect and control
    # the process(es).
    p1 = subby.run([["grep", "foo"], ["wc", "-l"]], stdin=input_str)
    p2 = subby.run(("grep foo", "wc -l"), stdin=input_str)
    p3 = subby.run("grep foo | wc -l", stdin=input_str)

    # The `done` property tells us whether the processes have finished
    assert p1.done and p2.done and p3.done

    # The `output` property provides the output of the command
    assert p1.output == p2.output == p3.output == "1"


# --- Additional coverage for previously-untested branches ---


def test_version_exposed():
    # __version__ is resolved via importlib.metadata and is a non-empty string.
    assert isinstance(subby.__version__, str)
    assert subby.__version__


def test_run_empty_list_raises():
    # An empty sequence of commands is invalid.
    with pytest.raises(ValueError):
        subby.run([])


def test_sub_returns_none_when_no_output_stream():
    # When stdout is neither PIPE nor BUFFER (here: discarded), sub() returns None
    # rather than attempting to read output.
    assert subby.sub("echo hi", stdout=None) is None


def test_stdin_stream_before_run_raises():
    # Accessing stdin_stream before run() is an error.
    p = subby.Processes([["cat"]], stdin=subby.StdType.PIPE)
    with pytest.raises(RuntimeError):
        p.stdin_stream


def test_get_all_stderr_without_capture():
    # With capture_stderr=False, only the final process's (buffered) stderr is
    # returned; the per-process stderr buffers are not collected.
    p = subby.run(
        "echo -n hi | tee /dev/stderr | tee /dev/stderr",
        capture_stderr=False,
        stderr=subby.StdType.BUFFER,
    )
    assert p.output == "hi"
    # Only the single final-process stderr entry, not one per piped command.
    assert p.get_all_stderr() == ["hi"]


def test_block_raise_on_error_false_does_not_raise():
    # A non-zero return code with raise_on_error=False must not raise; instead the
    # failure is observable via `ok`/`returncode`.
    p = subby.Processes([["cat", "no_such_file_xyz"]], raise_on_error=False)
    p.run()
    p.block()
    assert not p.ok
    assert p.returncode != 0


def test_block_raise_on_error_arg_overrides():
    # raise_on_error passed directly to block() takes precedence over the
    # constructor value (here the constructor would have raised).
    p = subby.Processes([["cat", "no_such_file_xyz"]], raise_on_error=True)
    p.run()
    p.block(raise_on_error=False)
    assert not p.ok


def test_get_all_stderr_capture_with_file_stderr():
    # capture_stderr=True but the final stderr goes to a file (not a buffer/pipe),
    # so only the captured per-process buffers are returned.
    with isolated_dir() as d:
        stderr_file = d / "stderr"
        p = subby.run(
            "echo -n hi | tee /dev/stderr | tee /dev/stderr",
            stderr=stderr_file,
        )
        # The two upstream `tee` processes each wrote "hi" to their stderr buffer;
        # the final process's stderr went to the file and is excluded here.
        assert p.get_all_stderr() == ["", "hi"]


def test_context_manager_kills_on_exception():
    # Exiting the context manager via an exception, before the process finishes,
    # triggers kill()+close() and re-raises the original exception.
    sentinel = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        with subby.Processes([["sleep", "5"]]) as p:
            raise sentinel
    assert p.closed
    assert p.returncode != 0
