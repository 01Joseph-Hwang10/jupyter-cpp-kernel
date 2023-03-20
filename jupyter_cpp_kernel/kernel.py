from queue import Queue
from threading import Thread

from ipykernel.kernelbase import Kernel
import re
import subprocess
import tempfile
import os
import os.path as path


class RealTimeSubprocess(subprocess.Popen):
    """
    A subprocess that allows to read its stdout and stderr in real time
    """

    def __init__(self, cmd, write_to_stdout, write_to_stderr):
        """
        :param cmd: the command to execute
        :param write_to_stdout: a callable that will be called with chunks of data from stdout
        :param write_to_stderr: a callable that will be called with chunks of data from stderr
        """
        self._write_to_stdout = write_to_stdout
        self._write_to_stderr = write_to_stderr

        super().__init__(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        self._stdout_queue = Queue()
        self._stdout_thread = Thread(
            target=RealTimeSubprocess._enqueue_output,
            args=(
                self.stdout,
                self._stdout_queue,
            ),
        )
        self._stdout_thread.daemon = True
        self._stdout_thread.start()

        self._stderr_queue = Queue()
        self._stderr_thread = Thread(
            target=RealTimeSubprocess._enqueue_output,
            args=(
                self.stderr,
                self._stderr_queue,
            ),
        )
        self._stderr_thread.daemon = True
        self._stderr_thread.start()

    @staticmethod
    def _enqueue_output(stream, queue):
        """
        Add chunks of data from a stream to a queue until the stream is empty.
        """
        for line in iter(lambda: stream.read(4096), b''):
            queue.put(line)
        stream.close()

    def write_contents(self):
        """
        Write the available content from stdin and stderr where specified when the instance was created
        :return:
        """

        def read_all_from_queue(queue):
            res = b''
            size = queue.qsize()
            while size != 0:
                res += queue.get_nowait()
                size -= 1
            return res

        stdout_contents = read_all_from_queue(self._stdout_queue)
        if stdout_contents:
            self._write_to_stdout(stdout_contents)
        stderr_contents = read_all_from_queue(self._stderr_queue)
        if stderr_contents:
            self._write_to_stderr(stderr_contents)


class CPPKernel(Kernel):
    implementation = 'jupyter_cpp_kernel'
    implementation_version = '1.0'
    language = 'cpp'
    language_version = 'C++17'
    language_info = {
        'name': 'cpp',
        'mimetype': 'text/plain',
        'file_extension': '.cpp'
    }
    banner = "C++ kernel.\n" \
             "Uses g++, compiles in C++17, and creates source code files and executables in temporary folder.\n"

    def __init__(self, *args, **kwargs):
        super(CPPKernel, self).__init__(*args, **kwargs)
        self.files = []
        mastertemp = tempfile.mkstemp(suffix='.out')
        os.close(mastertemp[0])
        self.master_path = mastertemp[1]
        filepath = path.join(
            path.dirname(path.realpath(__file__)),
            'resources',
            'master.cpp',
        )
        subprocess.call([
            'g++',
            filepath,
            '-std=c++17',
            '-rdynamic',
            '-ldl',
            '-o',
            self.master_path,
        ])

    def cleanup_files(self):
        """Remove all the temporary files created by the kernel"""
        for file in self.files:
            os.remove(file)
        os.remove(self.master_path)

    def new_temp_file(self, **kwargs):
        """Create a new temp file to be deleted when the kernel shuts down"""
        # We don't want the file to be deleted when closed, but only when the kernel stops
        kwargs['delete'] = False
        kwargs['mode'] = 'w'
        file = tempfile.NamedTemporaryFile(**kwargs)
        self.files.append(file.name)
        return file

    def _write_to_stdout(self, contents):
        self.send_response(
            self.iopub_socket,
            'stream',
            {
                'name': 'stdout',
                'text': contents,
            },
        )

    def _write_to_stderr(self, contents):
        self.send_response(
            self.iopub_socket,
            'stream',
            {
                'name': 'stderr',
                'text': contents,
            },
        )

    def create_jupyter_subprocess(self, cmd):
        return RealTimeSubprocess(
            cmd,
            lambda contents: self._write_to_stdout(contents.decode()),
            lambda contents: self._write_to_stderr(contents.decode()),
        )

    def compile_with_gxx(
        self,
        source_filename,
        deps_filenames,
        binary_filename,
        cxxflags=None,
        ldflags=None,
    ):
        cxxflags = ['-std=c++17', '-fPIC', '-shared', '-rdynamic'] + cxxflags
        args = ['g++', source_filename] + deps_filenames + cxxflags + [
            '-o', binary_filename
        ] + ldflags
        return self.create_jupyter_subprocess(args)

    def _filter_magics(self, code):

        magics = {
            'cxxflags': [],
            'ldflags': [],
            'args': [],
        }

        for line in code.splitlines():
            if line.startswith('//%'):
                key, value = line[3:].split(":", 2)
                key = key.strip().lower()

                if key in ['ldflags', 'cxxflags']:
                    for flag in value.split():
                        magics[key] += [flag]
                elif key == "args":
                    # Split arguments respecting quotes
                    for argument in re.findall(
                            r'(?:[^\s,"]|"(?:\\.|[^"])*")+',
                            value,
                    ):
                        magics['args'] += [argument.strip('"')]

        return magics

    def _replace_include_directives(self, code):

        # Replace non-system-path includes with absolute path
        parent = self.get_parent()
        metadata = parent['metadata']
        cell_id = str(metadata['cellId'])
        """
        Cell id looks like: vscode-notebook-cell:/Users/hwanghyeongyu/util/jupyter-c-kernel/example/example-notebook.ipynb#W1sZmlsZQ%3D%3D
        Where /Users/hwanghyeongyu/util/jupyter-c-kernel/example is a workspace folder.
        """
        _, cell_path = cell_id.split(':', 1)
        workspace_path, _ = cell_path.split('#', 1)

        # Find codelines with include directives sourcing from non-system paths
        # and replace them with absolute paths
        deps = []
        codelines = code.splitlines()
        for i, codeline in enumerate(codelines):
            if codeline.startswith('#include "'):
                if '//' in codeline:
                    codeline, _ = codeline.split('//', 1)
                _, include_path = codeline.strip().replace('"',
                                                           '').split(' ', 1)
                include_path = os.path.abspath(
                    os.path.join(
                        os.path.dirname(workspace_path),
                        include_path,
                    ))
                deps.append(include_path)
                codelines[i] = '#include "' + include_path + '"'

        deps = list(
            map(
                lambda x: x.replace('.hpp', '.cpp').replace('.h', '.cpp'),
                deps,
            ))

        return '\n'.join(codelines), deps

    def do_execute(
        self,
        code,
        silent,
        store_history=True,
        user_expressions=None,
        allow_stdin=False,
    ):

        magics = self._filter_magics(code)

        # Replace include directives with workspace contexts
        code, deps = self._replace_include_directives(code)

        with self.new_temp_file(suffix='.cpp') as source_file:
            source_file.write(code)
            source_file.flush()
            with self.new_temp_file(suffix='.out') as binary_file:
                p = self.compile_with_gxx(
                    source_filename=source_file.name,
                    deps_filenames=deps,
                    binary_filename=binary_file.name,
                    cxxflags=magics['cxxflags'],
                    ldflags=magics['ldflags'],
                )
                while p.poll() is None:
                    p.write_contents()
                p.write_contents()
                if p.returncode != 0:  # Compilation failed
                    self._write_to_stderr(
                        "[C++ kernel] G++ exited with code {}, the executable will not be executed"
                        .format(p.returncode))
                    return {
                        'status': 'ok',
                        'execution_count': self.execution_count,
                        'payload': [],
                        'user_expressions': {}
                    }

        p = self.create_jupyter_subprocess(
            [self.master_path, binary_file.name] + magics['args'])
        while p.poll() is None:
            p.write_contents()
        p.write_contents()

        if p.returncode != 0:
            self._write_to_stderr(
                "[C++ kernel] Executable exited with code {}".format(
                    p.returncode))
        return {
            'status': 'ok',
            'execution_count': self.execution_count,
            'payload': [],
            'user_expressions': {}
        }

    def do_shutdown(self, restart):
        """Cleanup the created source code files and executables when shutting down the kernel"""
        self.cleanup_files()
