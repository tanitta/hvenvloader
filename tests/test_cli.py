import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "python"))

from hvenvloader.cli import _cmd_nvhp_create, build_parser, generate_launcher_cli, main
from hvenvloader import tools


class CliParserTests(unittest.TestCase):
    def test_project_init_defaults(self):
        args = build_parser().parse_args(["init", "C:/proj"])
        self.assertEqual(args.path, "C:/proj")
        self.assertFalse(args.no_package)
        self.assertFalse(args.init)
        self.assertFalse(args.sync)
        self.assertFalse(args.launcher)
        self.assertFalse(args.no_init)
        self.assertFalse(args.no_sync)
        self.assertFalse(args.no_launcher)
        self.assertFalse(args.force)
        self.assertIsNone(args.hvenvloader)

    def test_init_launcher_only_update(self):
        args = build_parser().parse_args(["init", "C:/proj", "--launcher"])
        self.assertFalse(args.init)
        self.assertFalse(args.sync)
        self.assertTrue(args.launcher)

    def test_init_noop_requires_flag(self):
        args = build_parser().parse_args(["init", "C:/proj", "--no-init", "--no-sync", "--no-launcher"])
        self.assertFalse(args.init)
        self.assertFalse(args.sync)
        self.assertFalse(args.launcher)

    def test_nvhp_create_defaults(self):
        args = build_parser().parse_args(["nvhp", "create", "MyPkg"])
        self.assertEqual(args.name, "MyPkg")
        self.assertEqual(args.path, ".")
        self.assertIsNone(args.package_name)
        self.assertIsNone(args.env_var)
        self.assertEqual(args.version, "0.1.0")
        self.assertEqual(args.subdirs, "otls,scripts,toolbar,python_panels")
        self.assertFalse(args.no_readme)
        self.assertFalse(args.sync)

    def test_nvhp_export_args(self):
        args = build_parser().parse_args(["nvhp", "export", "C:/pkg", "C:/out", "--force"])
        self.assertEqual(args.package_dir, "C:/pkg")
        self.assertEqual(args.export_dir, "C:/out")
        self.assertTrue(args.force)

    def test_uv_remaider(self):
        args = build_parser().parse_args(["uv", "C:/proj", "--", "add", "numpy"])
        self.assertEqual(args.path, "C:/proj")
        self.assertEqual(args.uv_args, ["add", "numpy"])


class CliCommandTests(unittest.TestCase):
    def test_windows_user_template_and_fallback_for_shelf_and_cli(self):
        self._check_user_template('Windows', 'houdini.bat', 'houdini.user.bat')

    def test_unix_user_template_and_fallback_for_shelf_and_cli(self):
        self._check_user_template('Linux', 'houdini.sh', 'houdini.user.sh')

    def _check_user_template(self, system, name, custom_name):
        with tempfile.TemporaryDirectory(prefix="hvenv templates ") as directory:
            root = Path(directory)
            templates = root / 'templates'
            project = root / 'project'
            templates.mkdir()
            project.mkdir()
            standard = templates / name
            custom = templates / custom_name
            tokens = '@HOUDINI_EXE@\n@HOUDINI_USER_PREF_DIR@\n@HVENVLOADER@\n'
            standard.write_text('standard\n' + tokens, encoding='utf-8')
            hou = Mock()
            hou.getenv.return_value = 'C:/fake/pref'
            with patch.object(tools.platform, 'system', return_value=system), \
                 patch.object(tools, '_hvenvloader_root', return_value=templates), \
                 patch.object(tools, '_hou', return_value=hou), \
                 patch.dict(os.environ, HOUDINI_USER_PREF_DIR='C:/fake/pref'):
                for use_custom in (False, True, False):
                    if use_custom:
                        custom.write_text('custom\n' + tokens, encoding='utf-8')
                    elif custom.exists():
                        custom.unlink()
                    for generate in (lambda: tools.generate_launcher(project),
                                     lambda: generate_launcher_cli(project, templates)):
                        written = generate()
                        self.assertEqual(written, project / name)
                        text = written.read_text(encoding='utf-8')
                        self.assertTrue(text.startswith('custom\n' if use_custom else 'standard\n'))
                        self.assertNotIn('@HOUDINI_EXE@', text)
                        self.assertIn('C:/fake/pref', text)
                        self.assertIn(str(templates), text)
                        if use_custom:
                            self.assertEqual(custom.read_text(encoding='utf-8'), 'custom\n' + tokens)

    def _args(self, *argv):
        return build_parser().parse_args(list(argv))

    def test_nvhp_create_writes_layout(self):
        with tempfile.TemporaryDirectory(prefix="hvenv cli ") as directory:
            args = self._args("nvhp", "create", "MyPkg", directory)
            self.assertEqual(_cmd_nvhp_create(args), 0)

            root = Path(directory) / "MyPkg"
            package = root / "src" / "MyPkg"
            self.assertTrue((root / "pyproject.toml").is_file())
            self.assertTrue((root / "README.md").is_file())
            self.assertTrue((package / "__init__.py").is_file())
            self.assertTrue((package / "hpackage.json").is_file())
            for subdir in ("otls", "scripts", "toolbar", "python_panels"):
                self.assertTrue((package / subdir).is_dir())

    def test_nvhp_create_rejects_unknown_subdir(self):
        with tempfile.TemporaryDirectory(prefix="hvenv cli ") as directory:
            args = self._args("nvhp", "create", "MyPkg", directory, "--subdirs", "nope")
            self.assertEqual(_cmd_nvhp_create(args), 2)

    def test_generate_launcher_cli(self):
        with tempfile.TemporaryDirectory(prefix="hvenv cli ") as directory:
            os.environ["HVENVLOADER_HOUDINI_EXE"] = "C:/fake/houdini.exe"
            os.environ["HOUDINI_USER_PREF_DIR"] = "C:/fake/pref"
            try:
                written = generate_launcher_cli(directory)
            finally:
                os.environ.pop("HVENVLOADER_HOUDINI_EXE", None)
                os.environ.pop("HOUDINI_USER_PREF_DIR", None)

            name = "houdini.bat" if os.name == "nt" else "houdini.sh"
            self.assertEqual(written, Path(directory) / name)
            text = written.read_text(encoding="utf-8")
            self.assertIn("C:/fake/houdini.exe", text)
            self.assertIn("C:/fake/pref", text)
            self.assertNotIn("@HOUDINI_EXE@", text)

    def test_main_no_command_returns_help_code(self):
        self.assertEqual(main([]), 2)


if __name__ == "__main__":
    unittest.main()
