import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).parents[1] / "scripts" / "python"
sys.path.insert(0, str(MODULE_ROOT))

from hvenvloader import package_sync, tools


class PackageSyncTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temporary_directory.name) / "project"
        self.site_packages_path = (
            self.root_path / ".venv" / "Lib" / "site-packages"
        )
        self.site_packages_path.mkdir(parents=True)
        self.editable_package_path = (
            self.root_path / ".hvenvloader" / "editable_packages"
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _add_editable_package(self, package_name="SomePackage"):
        source_root = Path(self.temporary_directory.name) / "source"
        package_dir = source_root / "src" / package_name
        package_dir.mkdir(parents=True)
        package_json = (
            '{\n'
            '  "env": [{"SOMEPACKAGE": '
            '"$HOUDINI_PACKAGE_PATH/SomePackage"}],\n'
            '  "hpath": "$SOMEPACKAGE"\n'
            '}\n'
        )
        (package_dir / "hpackage.json").write_text(package_json, encoding="utf-8")

        dist_info_path = self.site_packages_path / "somepackage-1.0.dist-info"
        dist_info_path.mkdir()
        (dist_info_path / "top_level.txt").write_text(
            package_name + "\n",
            encoding="utf-8",
        )
        (dist_info_path / "direct_url.json").write_text(
            json.dumps(
                {
                    "url": source_root.as_uri(),
                    "dir_info": {"editable": True},
                }
            ),
            encoding="utf-8",
        )
        return package_dir, package_json, dist_info_path

    def test_regular_package_json_stays_next_to_installed_package(self):
        package_dir = self.site_packages_path / "SomePackage"
        package_dir.mkdir()
        package_json = '{"hpath": "$HOUDINI_PACKAGE_PATH/SomePackage"}\n'
        (package_dir / "hpackage.json").write_text(package_json, encoding="utf-8")

        package_sync.sync_houdini_package_jsons(
            self.site_packages_path,
            self.editable_package_path,
        )

        self.assertEqual(
            (self.site_packages_path / "SomePackage.json").read_text(
                encoding="utf-8"
            ),
            package_json,
        )
        self.assertFalse(self.editable_package_path.exists())
        self.assertFalse((self.root_path / "packages").exists())

    def test_editable_package_uses_project_overlay_and_cleans_it_when_removed(self):
        package_dir, package_json, dist_info_path = self._add_editable_package()
        local_packages_path = self.root_path / "packages"
        local_packages_path.mkdir()
        local_package_json_path = local_packages_path / "MyLocalTool.json"
        local_package_json_path.write_text("{}\n", encoding="utf-8")

        package_sync.sync_houdini_package_jsons(
            self.site_packages_path,
            self.editable_package_path,
        )

        copied_json_path = self.editable_package_path / "SomePackage.json"
        link_path = self.editable_package_path / "SomePackage"
        self.assertEqual(copied_json_path.read_text(encoding="utf-8"), package_json)
        self.assertEqual(link_path.resolve(), package_dir.resolve())
        self.assertFalse(
            (
                self.site_packages_path
                / package_sync.LEGACY_EDITABLE_PACKAGE_DIR_NAME
            ).exists()
        )

        shutil.rmtree(dist_info_path)
        package_sync.sync_houdini_package_jsons(
            self.site_packages_path,
            self.editable_package_path,
        )

        self.assertFalse(self.editable_package_path.exists())
        self.assertEqual(
            local_package_json_path.read_text(encoding="utf-8"),
            "{}\n",
        )

    def test_recognized_legacy_overlay_is_removed(self):
        package_dir, _, _ = self._add_editable_package()
        legacy_path = (
            self.site_packages_path
            / package_sync.LEGACY_EDITABLE_PACKAGE_DIR_NAME
        )
        legacy_path.mkdir()
        (legacy_path / "SomePackage.json").write_text("{}\n", encoding="utf-8")
        package_sync._create_directory_link(
            package_dir,
            legacy_path / "SomePackage",
        )

        package_sync.sync_houdini_package_jsons(
            self.site_packages_path,
            self.editable_package_path,
        )

        self.assertFalse(legacy_path.exists())

    def test_unrecognized_legacy_overlay_is_preserved(self):
        legacy_path = (
            self.site_packages_path
            / package_sync.LEGACY_EDITABLE_PACKAGE_DIR_NAME
        )
        legacy_path.mkdir()
        user_file_path = legacy_path / "notes.txt"
        user_file_path.write_text("keep me\n", encoding="utf-8")

        package_sync.sync_houdini_package_jsons(
            self.site_packages_path,
            self.editable_package_path,
        )

        self.assertEqual(user_file_path.read_text(encoding="utf-8"), "keep me\n")

    def test_stale_editable_bootstrap_json_is_removed(self):
        bootstrap_path = (
            self.site_packages_path
            / package_sync.STALE_EDITABLE_BOOTSTRAP_JSON_NAME
        )
        bootstrap_path.write_text("{}\n", encoding="utf-8")

        package_sync.sync_houdini_package_jsons(
            self.site_packages_path,
            self.editable_package_path,
        )

        self.assertFalse(bootstrap_path.exists())

    def test_sync_does_not_follow_overlay_directory_link(self):
        external_path = Path(self.temporary_directory.name) / "user-managed"
        external_path.mkdir()
        sentinel_path = external_path / "keep.txt"
        sentinel_path.write_text("keep me\n", encoding="utf-8")
        package_sync._create_directory_link(
            external_path,
            self.editable_package_path,
        )

        package_sync.sync_houdini_package_jsons(
            self.site_packages_path,
            self.editable_package_path,
        )

        self.assertEqual(sentinel_path.read_text(encoding="utf-8"), "keep me\n")
        self.assertEqual(
            self.editable_package_path.resolve(),
            external_path.resolve(),
        )

    def test_uv_remove_keeps_regular_direct_install_in_site_packages(self):
        package_dir = self.site_packages_path / "SomePackage"
        package_dir.mkdir()
        (package_dir / "hpackage.json").write_text("{}\n", encoding="utf-8")

        source_root = Path(self.temporary_directory.name) / "regular-source"
        source_package_dir = source_root / "src" / "SomePackage"
        source_package_dir.mkdir(parents=True)
        (source_package_dir / "hpackage.json").write_text(
            "{}\n",
            encoding="utf-8",
        )

        dist_info_path = self.site_packages_path / "somepackage-1.0.dist-info"
        dist_info_path.mkdir()
        (dist_info_path / "top_level.txt").write_text(
            "SomePackage\n",
            encoding="utf-8",
        )
        (dist_info_path / "direct_url.json").write_text(
            json.dumps(
                {
                    "url": source_root.as_uri(),
                    "dir_info": {"editable": False},
                }
            ),
            encoding="utf-8",
        )

        package_sync.sync_houdini_package_jsons(
            self.site_packages_path,
            self.editable_package_path,
        )

        unloaded_paths = []

        class FakeUi:
            @staticmethod
            def unloadPackage(path):
                unloaded_paths.append(Path(path))

        class FakeHou:
            ui = FakeUi()

        original_hou = tools._hou
        tools._hou = lambda: FakeHou()
        try:
            tools.unload_houdini_packages_for_removed_package(
                self.root_path,
                "SomePackage",
            )
        finally:
            tools._hou = original_hou

        self.assertEqual(
            unloaded_paths,
            [self.site_packages_path / "SomePackage.json"],
        )
        self.assertFalse(self.editable_package_path.exists())
        self.assertTrue(source_package_dir.is_dir())

    def test_uv_remove_cleanup_uses_project_overlay(self):
        package_dir, _, _ = self._add_editable_package()
        package_sync.sync_houdini_package_jsons(
            self.site_packages_path,
            self.editable_package_path,
        )

        unloaded_paths = []

        class FakeUi:
            @staticmethod
            def unloadPackage(path):
                unloaded_paths.append(Path(path))

        class FakeHou:
            ui = FakeUi()

        original_hou = tools._hou
        tools._hou = lambda: FakeHou()
        try:
            messages = tools.unload_houdini_packages_for_removed_package(
                self.root_path,
                "SomePackage",
            )
        finally:
            tools._hou = original_hou

        copied_json_path = self.editable_package_path / "SomePackage.json"
        self.assertEqual(unloaded_paths, [copied_json_path])
        self.assertFalse(copied_json_path.exists())
        self.assertFalse((self.editable_package_path / package_dir.name).exists())
        self.assertFalse(self.editable_package_path.exists())
        self.assertTrue(any("Removed empty editable NVHP overlay" in m for m in messages))


class LauncherTemplateTest(unittest.TestCase):
    def setUp(self):
        self.repository_root = Path(__file__).parents[1]

    def test_windows_launcher_uses_project_package_directory_order(self):
        text = (self.repository_root / "houdini.bat").read_text(encoding="utf-8")

        site_packages = text.index(
            'set "HOUDINI_PACKAGE_DIR=%PYTHON_SITE_PACKAGES%"'
        )
        project_packages = text.index(
            "set \"HOUDINI_PACKAGE_DIR=%HVENVLOADER_PROJECT_PACKAGE_DIR%;"
        )
        editable_overlay = text.index(
            "set \"HOUDINI_PACKAGE_DIR=!HOUDINI_PACKAGE_DIR!;"
            "%HVENVLOADER_EDITABLE_PACKAGE_DIR%\""
        )
        self.assertLess(site_packages, project_packages)
        self.assertLess(project_packages, editable_overlay)
        self.assertIn("%SCRIPT_DIR%packages", text)
        self.assertIn("%SCRIPT_DIR%.hvenvloader\\editable_packages", text)
        self.assertNotIn("_hvenvloader_houdini_packages", text)

    def test_posix_launcher_uses_project_package_directory_order(self):
        text = (self.repository_root / "houdini.sh").read_text(encoding="utf-8")

        site_packages = text.index('HOUDINI_PACKAGE_DIR="$PYTHON_SITE_PACKAGES"')
        project_packages = text.index(
            'HOUDINI_PACKAGE_DIR="$HVENVLOADER_PROJECT_PACKAGE_DIR:'
            '$HOUDINI_PACKAGE_DIR"'
        )
        editable_overlay = text.index(
            'HOUDINI_PACKAGE_DIR="$HOUDINI_PACKAGE_DIR:'
            '$HVENVLOADER_EDITABLE_PACKAGE_DIR"'
        )
        self.assertLess(site_packages, project_packages)
        self.assertLess(project_packages, editable_overlay)
        self.assertIn('$SCRIPT_DIR/packages', text)
        self.assertIn('$SCRIPT_DIR/.hvenvloader/editable_packages', text)
        self.assertNotIn("_hvenvloader_houdini_packages", text)


if __name__ == "__main__":
    unittest.main()
