import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LauncherArgsTests(unittest.TestCase):
    def _prepare_launcher(self, root, name):
        text = (ROOT / name).read_text(encoding='utf-8')
        text = text.replace('@HOUDINI_EXE@', sys.executable)
        text = text.replace('@HOUDINI_USER_PREF_DIR@', str(root))
        text = text.replace('@HVENVLOADER@', str(root))
        launcher = root / name
        launcher.write_text(text, encoding='utf-8')
        writer = root / 'capture.py'
        writer.write_text(
            'import json, os, pathlib, sys\n'
            'pathlib.Path(os.environ["RESULT"]).write_text(json.dumps(sys.argv[1:]))\n',
            encoding='utf-8',
        )
        return launcher, writer

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher')
    def test_windows_arguments(self):
        with tempfile.TemporaryDirectory(prefix='launcher args & ') as directory:
            root = Path(directory)
            launcher, writer = self._prepare_launcher(root, 'houdini.bat')
            result_path = root / 'result.json'
            env = os.environ.copy()
            env.update(TEST_LAUNCHER=str(launcher), TEST_WRITER=str(writer),
                       RESULT=str(result_path))
            command = '""%TEST_LAUNCHER%" "%TEST_WRITER%" -n "scene with spaces.hip" "a&b" "a!b""'
            expected = ['-n', 'scene with spaces.hip', 'a&b', 'a!b']
            env.pop('HVENVLOADER_RESTART_HIP', None)
            completed = subprocess.run(
                'cmd.exe /d /v:off /s /c ' + command,
                env=env, capture_output=True, timeout=10,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(result_path.read_text()), expected)

    @unittest.skipIf(os.name == 'nt', 'Unix launcher')
    def test_unix_arguments(self):
        with tempfile.TemporaryDirectory(prefix='launcher args ') as directory:
            root = Path(directory)
            launcher, writer = self._prepare_launcher(root, 'houdini.sh')
            result_path = root / 'result.json'
            env = os.environ.copy()
            env['RESULT'] = str(result_path)
            args = ['-n', 'scene with spaces.hip', 'a&b', '']
            completed = subprocess.run(
                ['bash', str(launcher), str(writer), *args],
                env=env, capture_output=True, timeout=10,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(result_path.read_text()), args)


if __name__ == '__main__':
    unittest.main()
