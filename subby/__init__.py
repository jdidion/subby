import copy
import enum
import errno
import logging
import shlex
import subprocess
from subprocess import CalledProcessError
import tempfile
from typing import IO, Optional, Sequence, Tuple, Union

LOG = logging.getLogger()
DEFAULT_EXECUTABLE = "/bin/bash"


class StdType(enum.IntEnum):
    """
    stdout/stderr types
    """
    PIPE = 0
    FILE = 1
    BUFFER = 2
    OTHER = 3


class Processes:
    """
    Encapsulates one or more commands, runs those commands using the
    `subprocess` module, and provides access to the results.

    Args:
        cmds: Command strings or sequences of command arguments to be chained together.
        stdout: How to capture stdout of the final process in the chain; can be
            a string (filename) or file object, in which case the output is written
            to that file; None, in which case `subprocess.PIPE` is used; True,
            in which case output is captured to a buffer; or False, in which case
            stdout is discarded. If a file, any existing file with the same name is
            overwritten.
        stderr: How to capture stderr of the final process in the chain (see
            `stdout` for details).
        capture_stderr: Whether to capture the contents of stderr of processes
            other than the final process.
        echo: Whether to echo commands to the logger before running the commands.
            Can be overridden by the `run()` method's `echo` parameter.
        popen_kwargs: Keyword arguments to pass to Popen constructors.

    Todo:
        Add ability to send input to stdin of first process.
    """
    def __init__(
        self,
        cmds: Sequence[Union[str, Sequence[str]]],
        stdout: Optional[Union[str, bool, IO]] = None,
        stderr: Optional[Union[str, bool, IO]] = None,
        capture_stderr: bool = True,
        echo: bool = None,
        **popen_kwargs
    ):
        self.cmds = cmds
        self._stdout = stdout
        self._stdout_type = None
        self._stderr = stderr
        self._stderr_type = None
        self.capture_stderr = capture_stderr
        self._stderr_buffers = [] if capture_stderr else None
        self._stderr_bytes = None
        self._closed = False
        self.echo = echo
        self.popen_kwargs = popen_kwargs
        self._processes = None
        self._output_handle = None
        self._returncode = None
        self._out = None
        self._err = None

    @property
    def returncode(self) -> int:
        """
        The return code of the last process to finish with an error, or 0. Is None
        if the last process hasn't finished running.
        """
        if not self.was_run:
            raise RuntimeError("Must call run() before returncode can be requested")
        if self._returncode is None:
            # Set `self._returncode` to the returncode of the last process
            # to finish with an error, to mimic behavior of `set -o pipefail`.
            # Note that if any process other than the last has a return code of
            # None, we ignore it.
            self._returncode = self._processes[-1].poll()
            if self._returncode == 0 and len(self._processes) > 1:
                # The last process finished running without error, but check all
                # the other processes for an error.
                for proc in reversed(self._processes[-2::-1]):
                    rc = proc.poll()
                    if rc:
                        self._returncode = rc
                        break
        return self._returncode

    def _init_stdout(self) -> Union[int, IO]:
        self._stdout, self._stdout_type, retval = self._init_std(self._stdout)
        return retval

    def _init_stderr(self) -> Union[int, IO]:
        self._stderr, self._stderr_type, retval = self._init_std(self._stderr)
        return retval

    @staticmethod
    def _init_std(value) -> Tuple[Optional[IO], StdType, Union[int, IO]]:
        if value is None:
            return None, StdType.PIPE, subprocess.PIPE

        std_type = StdType.OTHER
        if value is False:
            value = None
        elif value is True:
            value = Processes._create_temp_outfile()
            std_type = StdType.BUFFER
        elif isinstance(value, str):
            value = open(value, "w")
            std_type = StdType.FILE
        return value, std_type, value

    def _get_stderr_buffer(self) -> IO:
        """
        Creates a temporary file to use for storing a stderr stream.

        Returns:
            The opened file object.
        """
        if self.capture_stderr:
            handle = self._create_temp_outfile()
            self._stderr_buffers.append(handle)
            return handle

    @staticmethod
    def _create_temp_outfile() -> IO:
        """
        Creates and returns a temporary output file object.
        """
        return open(tempfile.mkstemp()[1], "w")

    @property
    def output(self) -> bytes:
        """
        The contents of the `stdout` stream of the last process in the chain.
        Only available if `self.closed is True` and `self._stdout_type in
        {StdType.PIPE, StdType.BUFFER}`.
        """
        if not (self.closed and self._stdout_type in {StdType.PIPE, StdType.BUFFER}):
            raise RuntimeError(
                "'output' is only available for closed processes using a pipe or "
                "buffer for stdout."
            )
        return self._out

    @property
    def error(self) -> bytes:
        """
        The contents of the `stderr` stream of the last process in the chain.
        Only available if `self.closed is True` and `self._stderr_type in
        {StdType.PIPE, StdType.BUFFER}`.
        """
        if not (self.closed and self._stderr_type in {StdType.PIPE, StdType.BUFFER}):
            raise RuntimeError(
                "'error' is only available for closed processes using a pipe or "
                "buffer for stderr."
            )
        return self._err

    @property
    def stdout_stream(self) -> IO:
        """
        The `stdout` stream of the last process in the chain.
        """
        if not self.was_run:
            raise RuntimeError("Cannot access 'stdout' until after calling 'run'.")
        return self._stdout or self._processes[-1].stdout

    @property
    def stderr_stream(self) -> IO:
        """
        The `stderr` stream of the last process in the chain.
        """
        if not self.was_run:
            raise RuntimeError("Cannot access 'stderr' until after calling 'run'.")
        return self._stderr or self._processes[-1].stderr

    def get_all_stderr(self) -> Sequence[bytes]:
        """
        Get the contents of all stderr streams. Stderr streams of all but the final
        process are only available if `self.capture_stderr is True`. Stderr stream
        of the final process is only available if `self._stderr_type in
        (StdType.BUFFER, StdType.PIPE)`.

        Returns:
            A list of strings, where each string is the captured stderr stream of a
            process.
        """
        if not self.closed:
            raise RuntimeError(
                "Cannot access 'stderr' contents until all processes have completed "
                "and file handles have been closed."
            )
        stderr = []
        if self.capture_stderr:
            stderr.extend(self._stderr_bytes)
        if self._stderr_type in (StdType.BUFFER, StdType.PIPE):
            stderr.append(self.error)
        return stderr

    @property
    def was_run(self) -> bool:
        """
        Whether the `run()` method was called.
        """
        return bool(self._processes)

    @property
    def done(self) -> bool:
        """
        Whether the commands have finished running.
        """
        return self.returncode is not None

    @property
    def ok(self) -> bool:
        """
        Whether the commands completed successfully, i.e. all had `returncode == 0`.
        """
        return self.returncode == 0

    @property
    def closed(self) -> bool:
        """
        Whether `self.close()` has been called.
        """
        return self._closed

    def run(self, echo: bool = None, **kwargs):
        """
        Run the commands.

        Args:
            echo: Whether to echo the commands to the log. Overrides the value of
                `self.echo`.
            kwargs: Keyword arguments to pass to Popen. Overrides any values specified
                in `self.popen_kwargs`.
        """
        if self.was_run:
            raise RuntimeError("Cannot call run() more than once.")

        if echo is None:
            echo = self.echo
        if echo is not False:
            LOG.info(str(self))

        num_commands = len(self.cmds)
        procs = []

        for i, cmd in enumerate(self.cmds, 1):
            popen_kwargs = copy.copy(self.popen_kwargs)
            popen_kwargs.update(kwargs)
            if procs:
                popen_kwargs["stdin"] = procs[-1].stdout
            if i == num_commands:
                popen_kwargs["stdout"] = self._init_stdout()
                popen_kwargs["stderr"] = self._init_stderr()
            else:
                popen_kwargs["stdout"] = subprocess.PIPE
                popen_kwargs["stderr"] = self._get_stderr_buffer()
            proc = subprocess.Popen(cmd, **popen_kwargs)
            if procs:
                procs[-1].stdout.close()
            procs.append(proc)

        self._processes = procs

    def block(self, close: bool = True, raise_on_error: bool = True):
        """
        Wait for all commands to finish.

        Args:
            close: Whether to call `self.close()` after the processes complete.
            raise_on_error: Whether to raise a :class:`subprocess.CalledProcessError`
                if the returncode was not 0.
        """
        if not self.was_run:
            raise RuntimeError("Cannot call block() until after calling run()")
        if self.closed:
            raise RuntimeError("Cannot call block() after calling close()")

        last_proc = self._processes[-1]
        try:
            out, err = (
                b"" if std is None else std.strip()
                for std in last_proc.communicate()
            )
            if self._stdout_type == StdType.PIPE:
                self._out = out
            if self._stderr_type == StdType.PIPE:
                self._err = err
        except ValueError:
            LOG.error("Error reading from stdout/stderr")
            pass

        if close:
            self._close_and_set_std()

        if raise_on_error:
            self.raise_if_error()

    def kill(self) -> bool:
        """
        Kill the running commands. It is recommended to call `close()` if this
        returns `True`.

        Returns:
            True if processes were killed, else False.
        """
        if self.was_run and not self.done:
            for i, proc in enumerate(self._processes):
                try:
                    proc.kill()
                except OSError as oserr:
                    if oserr.errno == errno.ESRCH:
                        # Ignore - process has already died
                        pass
                    LOG.exception(
                        "Error killing running process command %s", self.cmds[i]
                    )
            return True

        return False

    def close(self):
        """
        For each of stdout, stderr of the final process, if it is a file close it,
        or if it is a buffer, set its value to `self.out/self.err`.
        """
        if not (self.was_run and self.done):
            raise RuntimeError("Can only call close() after 'done' is True.")

        if not self._closed:
            self._close_and_set_std()

    def _close_and_set_std(self):
        """
        Close any open files and set the values of `self._out` and `self._err`
        if they are of type StdType.BUFFER.
        """
        def close_file(handle):
            try:
                handle.close()
            except IOError:
                LOG.exception("Error closing output file %s", handle.name)

        def close_buffer(handle) -> bytes:
            close_file(handle)
            with open(handle.name, "rb") as inp:
                return inp.read()

        if self._stdout == StdType.FILE:
            close_file(self._stdout)
        elif self._stdout_type == StdType.BUFFER:
            close_buffer(self._stdout)

        if self._stderr == StdType.FILE:
            close_file(self._stderr)
        elif self._stderr_type == StdType.BUFFER:
            close_buffer(self._stderr)

        if self.capture_stderr:
            self._stderr_bytes = [
                close_buffer(buf) for buf in self._stderr_buffers
            ]
            self._stderr_buffers = None

        self._closed = True

    def raise_if_error(self):
        """
        Raise an exception if the processes are finished running and the
        return code is not 0.

        Raises:
            CalledProcessError
        """
        if self.done and not self.ok:
            msg = "stderr from executed commands:\n{}".format(
                b"\n".join(self.get_all_stderr())
            )
            raise CalledProcessError(
                self.returncode, str(self), output=msg
            )

    def __str__(self) -> str:
        cmd_str = " | ".join(command_lists_to_strings(self.cmds))
        if self._stdout_type == StdType.FILE:
            cmd_str += " > {}".format(self._stdout.name)
        return cmd_str

    def __enter__(self) -> "Processes":
        if not self.was_run:
            self.run()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type or (self.was_run and not self.done):
            # Kill the processes if exiting the context manager with an error
            # or before the processes finish running.
            self.kill()
        self.close()


def run_cmd(cmd: Union[str, Sequence[str]], **kwargs) -> Processes:
    """
    Runs a single command as a subprocess.

    This is simply a convenience method for `chain([cmd], **kwargs)`.

    Args:
        cmd: The command string, or command arguments as a list.
        **kwargs: Additional keyword arguments to pass to `chain_cmds`.

    Returns:
        A :class:`subby.Processes` object.
    """
    return chain_cmds([cmd], **kwargs)


def chain_cmds(
    cmds: Sequence[Union[str, Sequence[str]]],
    stdout: str = None,
    shell: Union[str, bool] = False,
    block: bool = True,
    **kwargs
):
    """
    Runs several commands that pipe to each other in a python-aware way.

    Args:
        cmds: Any number of commands (lists or strings) to pipe together.
            Input of type 'list' is recommended. When input is of type 'string',
            command is executed using the default shell (i.e. `shell` is set to `None`
            if it is `False`).
        stdout: What to do with stdout of the last process in the chain. Can be a
            string (filename) or file object, in which case the output is written to
            that file; None, in which case `subprocess.PIPE` is used; True, in which
            case output is captured to a buffer; or False, in which case stdout is
            discarded.
        shell: Can be a boolean specifying whether to execute the command
            using the shell, or a string value specifying the shell executable to use
            (which also implies shell=True). If None, the command is executed via the
            default shell (which, according to the subprocess docs, is /bin/sh).
        block: Whether to block until all processes have completed.
        kwargs: Additional keyword arguments to pass to :class:`Processes`
            constructor.

    Returns:
        A :class:`subby.Processes` object.

    Raises:
        subprocess.CalledProcessError: if any subprocess in pipe returns exit
            code not 0.

    Examples:
        Usage 1: Pipe multiple commands together and print output to file
            example_cmd1 = ['dx', 'download', 'file-xxxx']
            example_cmd2 = ['gunzip']
            out_f = "somefilename.fasta"
            chain_cmd([example_cmd1, example_cmd2], output_filename=out_f)

            This function will print and execute the following command:
            'dx download file-xxxx | gunzip > somefilename.fasta'

        Usage 2: Pipe multiple commands together and return output
            example_cmd1 = ['gzip', 'file.txt']
            example_cmd2 = ['dx', 'upload', '-', '--brief']
            file_id = chain_cmd([example_cmd1, example_cmd2], block=True).output

            This function will print and execute the following command:
            'gzip file.txt | dx upload - --brief '
            and return the output.

        Usage 3: Run a single command with output to file
            run_cmd('echo "hello world"', output_filename='test2.txt')
            Note: This calls the run function instead of chain.

        Usage 4: A command failing mid-pipe should return CalledProcessedError
            chain_cmd(
                [['echo', 'hi:bye'], ['grep', 'blah'], ['cut', '-d', ':', '-f', '1']]
            )
            Traceback (most recent call last):
                  ...
            CalledProcessError: Command '['grep', 'blah']' returned non-zero
                exit status 1
    """
    if shell is True:
        executable = DEFAULT_EXECUTABLE
    elif isinstance(shell, str):
        executable = shell
    else:
        executable = None

    if shell is False:
        cmds = command_strings_to_lists(cmds)
    else:
        cmds = command_lists_to_strings(cmds)

    processes = Processes(
        cmds,
        stdout=stdout,
        shell=(shell is not False),
        executable=executable,
        **kwargs
    )

    if block:
        with processes as procs:
            procs.block()
    else:
        processes.run()

    return processes


def quote_args(seq: Sequence[str]) -> str:
    """
    Quote command line arguments.

    Args:
        seq: Command line arguments.

    Returns:
        Sequence of quoted command line arguments.
    """
    return " ".join(shlex.quote(str(arg)) for arg in seq)


def command_strings_to_lists(
    cmds: Sequence[Union[str, Sequence[str]]]
) -> Sequence[Sequence[str]]:
    """
    Convert any command strings in `cmds` to lists.

    Args:
        cmds: Commands - either strings or lists of arguments.

    Returns:
        A sequence of command argument sequences.
    """
    return [
        shlex.split(cmd)if isinstance(cmd, str) else cmd
        for cmd in cmds
    ]


def command_lists_to_strings(
    cmds: Sequence[Union[str, Sequence[str]]]
) -> Sequence[str]:
    """
    Convert any command lists in `cmds` to strings.

    Args:
        cmds: Commands - either strings or lists of arguments.

    Returns:
        A sequence of command strings.
    """
    return [
        quote_args(cmd) if not isinstance(cmd, str) else cmd
        for cmd in cmds
    ]