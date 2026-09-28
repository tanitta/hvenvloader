"""Windows save-and-restart shelf tool and independent process waiter."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def restart_environment(source):
    env = dict(source)
    for key in list(env):
        if key.upper().startswith(('HOUDINI_', 'HVENVLOADER_', 'PYTHON')) or key.upper() in (
            'HFS', 'HH', 'HB', 'H', 'HIP', 'HIPFILE', 'HIPNAME', 'VIRTUAL_ENV',
        ):
            env.pop(key, None)
    for key in ('PATH', 'PYTHONPATH'):
        value = source.get('HVENVLOADER_BASE_' + key)
        if value is not None:
            env[key] = value
    return env


def restart_tool():
    import hou
    if os.name != 'nt':
        hou.ui.displayMessage('Save and Restart currently supports Windows only.')
        return
    try:
        launcher = hou.getenv('HVENVLOADER_LAUNCHER_PATH')
        if not launcher:
            launcher = str(Path(hou.getenv('JOB') or '.') / 'houdini.bat')
        launcher = Path(launcher).resolve()
        if not launcher.is_file():
            raise RuntimeError('Project houdini.bat was not found. Set $JOB to your project root.')
        if 'HVENVLOADER_RESTART_HIP' not in launcher.read_text(encoding='utf-8-sig'):
            raise RuntimeError('Update this project launcher using venv > uv > Write Houdini launcher first.')
        python = launcher.parent / '.venv' / 'Scripts' / 'python.exe'
        if not python.is_file():
            raise RuntimeError('Project .venv Python was not found: {}'.format(python))
        if hou.hipFile.isNewFile():
            selected = hou.ui.selectFile(title='Save scene before restart',
                                         file_type=hou.fileType.Hip,
                                         chooser_mode=hou.fileChooserMode.Write)
            if not selected:
                return
            target = Path(hou.text.expandString(selected)).resolve()
            if target.suffix.lower() not in ('.hip', '.hiplc', '.hipnc'):
                target = target.with_suffix(Path(hou.hipFile.path()).suffix or '.hip')
            if target.exists() and hou.ui.displayMessage(
                'Overwrite {}?'.format(target), buttons=('Overwrite', 'Cancel'),
                default_choice=1, close_choice=1,
            ) != 0:
                return
            hou.hipFile.save(str(target))
        else:
            hou.hipFile.save()
        hip = str(Path(hou.hipFile.path()).resolve())
        env = restart_environment(os.environ)
        env['HVENVLOADER_RESTART_HIP'] = hip
        job = hou.getenv('JOB')
        if job:
            env['JOB'] = job
        with tempfile.TemporaryDirectory(prefix='hvenvloader-restart-') as directory:
            ready = Path(directory) / 'ready'
            process = subprocess.Popen(
                [str(python), '-I', str(Path(__file__).resolve()), str(os.getpid()),
                 str(launcher), str(ready)],
                env=env, cwd=str(launcher.parent),
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 10
            while not ready.exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    if process.poll() is None:
                        process.kill()
                    raise RuntimeError('Restart helper could not start; Houdini remains open.')
                time.sleep(0.05)
        try:
            hou.exit(suppress_save_prompt=True)
        except BaseException:
            process.terminate()
            raise
    except Exception as exc:
        hou.ui.displayMessage(str(exc), severity=hou.severityType.Error)


def wait_and_launch(pid, launcher, ready):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        Path(ready).touch()
        # Cancel the request if Houdini has not exited within two minutes.
        if kernel.WaitForSingleObject(handle, 120000) != 0:
            return
    finally:
        kernel.CloseHandle(handle)
    # Use environment expansion, not interpolated shell source, for paths.
    env = os.environ.copy()
    env['HVENVLOADER_RESTART_LAUNCHER'] = str(launcher)
    result = subprocess.run(
        'cmd.exe /d /v:off /s /c ""%HVENVLOADER_RESTART_LAUNCHER%""',
        env=env, cwd=str(Path(launcher).parent),
    )
    if result.returncode:
        ctypes.windll.user32.MessageBoxW(
            None, 'Launcher failed. Open the saved scene manually:\n' +
            env.get('HVENVLOADER_RESTART_HIP', ''), 'Houdini restart', 0x10,
        )


if __name__ == '__main__':
    wait_and_launch(*sys.argv[1:])
