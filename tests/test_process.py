import contextlib
import os
import tempfile
import shutil
import time

import pytest

import subby


@contextlib.contextmanager
def temp_dir(*args, **kwargs):
    dname = tempfile.mkdtemp(*args, **kwargs)
    try:
        yield dname
    finally:
        shutil.rmtree(dname)


@contextlib.contextmanager
def isolated_dir():
    with temp_dir() as d:
        curdir = os.getcwd()
        os.chdir(d)
        try:
            yield d
        finally:
            os.chdir(curdir)


def test_run():
    with isolated_dir():
        subby.run_cmd(
            "echo -n 'foo'",
            stdout="foo.txt",
            echo=True,
            block=True
        )
        assert os.path.exists("foo.txt")
        assert b"foo" == subby.run_cmd("cat foo.txt", block=True).output


def test_chain():
    with isolated_dir():
        subby.chain_cmds(
            ["echo -n 'foo'", "gzip"], stdout="foo.txt.gz", block=True
        )
        assert b"foo" == subby.chain_cmds(
                ["gunzip -c foo.txt.gz", "cat"], block=True
            ).output


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
    except subby.CalledProcessError as err:
        assert err.returncode == 1
