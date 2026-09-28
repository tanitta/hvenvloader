import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/python/hvenvloader/restart.py'
spec = importlib.util.spec_from_file_location('restart', SCRIPT)
restart = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restart)


class RestartTests(unittest.TestCase):
    def test_environment(self):
        env = restart.restart_environment({
            'PATH': 'polluted', 'PYTHONPATH': 'old package', 'HOUDINI_PATH': 'old',
            'HVENVLOADER_BASE_PATH': 'original', 'HVENVLOADER_BASE_PYTHONPATH': 'base',
            'JOB': 'project', 'SYSTEMROOT': 'windows', 'HFS': 'old',
        })
        self.assertEqual(env, {'PATH': 'original', 'PYTHONPATH': 'base',
                               'JOB': 'project', 'SYSTEMROOT': 'windows'})

    @unittest.skipUnless(os.name == 'nt', 'Windows restart')
    def test_save_failure_and_cancel_do_not_launch_or_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / 'houdini.bat'
            launcher.write_text('HVENVLOADER_RESTART_HIP')
            python = root / '.venv/Scripts/python.exe'
            python.parent.mkdir(parents=True)
            python.touch()
            hou = Mock()
            hou.getenv.return_value = str(launcher)
            with patch.dict(sys.modules, hou=hou), patch.object(restart.subprocess, 'Popen') as popen:
                hou.hipFile.isNewFile.return_value = True
                hou.ui.selectFile.return_value = ''
                restart.restart_tool()
                popen.assert_not_called()
                hou.exit.assert_not_called()
                hou.hipFile.isNewFile.return_value = False
                hou.hipFile.save.side_effect = RuntimeError('disk full')
                restart.restart_tool()
                popen.assert_not_called()
                hou.exit.assert_not_called()
                self.assertIn('disk full', hou.ui.displayMessage.call_args.args[0])

    @unittest.skipUnless(os.name == 'nt', 'Windows process handles')
    def test_generated_launcher_passes_restart_hip(self):
        with tempfile.TemporaryDirectory(prefix='restart-launcher-') as directory:
            root = Path(directory)
            # Python stands in for Houdini and executes the supplied HIP path.
            hip = root / 'scene & 100% !.py'
            hip.write_text('from pathlib import Path\nPath(__file__).with_suffix(".ok").touch()\n')
            text = (ROOT / 'houdini.bat').read_text(encoding='utf-8')
            text = text.replace('@HOUDINI_EXE@', sys.executable)
            text = text.replace('@HOUDINI_USER_PREF_DIR@', str(root))
            text = text.replace('@HVENVLOADER@', str(root))
            launcher = root / 'houdini.bat'
            launcher.write_text(text)
            env = os.environ.copy()
            env['HVENVLOADER_RESTART_HIP'] = str(hip)
            env['TEST_LAUNCHER'] = str(launcher)
            result = subprocess.run('cmd.exe /d /v:off /s /c ""%TEST_LAUNCHER%""',
                                    env=env, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(hip.with_suffix('.ok').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows process handles')
    def test_helper_waits_for_target_then_launches_with_literal_paths(self):
        with tempfile.TemporaryDirectory(prefix='restart space & ') as directory:
            root = Path(directory)
            launcher = root / 'houdini.bat'
            result = root / 'result.txt'
            writer = root / 'writer.py'
            writer.write_text('import os, pathlib\npathlib.Path(os.environ["RESULT"]).write_text(os.environ["HVENVLOADER_RESTART_HIP"], encoding="utf-8")\n')
            launcher.write_text('@echo off\n"%TEST_PYTHON%" "%TEST_WRITER%"\n')
            env = os.environ.copy()
            hip = str(root / '日本語 & 100% ! scene.hip')
            env.update(TEST_PYTHON=sys.executable, TEST_WRITER=str(writer),
                       RESULT=str(result), HVENVLOADER_RESTART_HIP=hip)
            target = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            helper = subprocess.Popen([sys.executable, '-I', str(SCRIPT), str(target.pid),
                                       str(launcher), str(root / 'ready')], env=env,
                                      creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
            try:
                deadline = time.monotonic() + 10
                while not (root / 'ready').exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue((root / 'ready').exists())
                self.assertFalse(result.exists())
                target.terminate()
                target.wait(timeout=5)
                self.assertEqual(helper.wait(timeout=10), 0)
                self.assertEqual(result.read_text(encoding='utf-8'), hip)
            finally:
                for process in (target, helper):
                    if process.poll() is None:
                        process.kill()
                    process.wait()


if __name__ == '__main__':
    unittest.main()
