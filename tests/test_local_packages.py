import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).parents[1] / "scripts" / "python"
sys.path.insert(0, str(MODULE_ROOT))

from hvenvloader import tools


class LocalPackageManagementTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_root = Path(self.temporary_directory.name)
        self.project_root = temporary_root / "project"
        self.project_root.mkdir()
        self.source_dir = temporary_root / "source" / "SomePackage"
        self.source_dir.mkdir(parents=True)
        self.source_json = self.source_dir / "SomePackage.json"
        self.package_json_text = json.dumps(
            {
                "env": [
                    {
                        "SOMEPACKAGE": "$HOUDINI_PACKAGE_PATH/SomePackage",
                    }
                ],
                "path": "$SOMEPACKAGE",
            },
            indent=4,
        ) + "\n"
        self.source_json.write_text(self.package_json_text, encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_detect_json_prioritizes_package_name_then_hpackage(self):
        (self.source_dir / "another.json").write_text("{}\n", encoding="utf-8")
        (self.source_dir / "hpackage.json").write_text("{}\n", encoding="utf-8")

        detected = tools.detect_houdini_package_jsons(self.source_dir)

        self.assertEqual(detected[0], self.source_json)
        self.assertEqual(detected[1], self.source_dir / "hpackage.json")

    def test_copy_install_update_and_remove(self):
        (self.source_dir / "old.txt").write_text("old", encoding="utf-8")

        result = tools.install_local_houdini_package(
            self.project_root,
            self.source_dir,
            self.source_json,
            directory_mode="copy",
        )

        self.assertEqual(
            result["package_json"].read_text(encoding="utf-8"),
            self.package_json_text,
        )
        self.assertTrue((result["package_dir"] / "old.txt").is_file())
        self.assertTrue(tools.local_package_status(
            self.project_root, "SomePackage"
        )["managed"])

        (self.source_dir / "old.txt").unlink()
        (self.source_dir / "new.txt").write_text("new", encoding="utf-8")
        tools.install_local_houdini_package(
            self.project_root,
            self.source_dir,
            self.source_json,
            directory_mode="copy",
            replace=True,
        )

        self.assertFalse((result["package_dir"] / "old.txt").exists())
        self.assertTrue((result["package_dir"] / "new.txt").is_file())

        tools.remove_local_houdini_package(self.project_root, "SomePackage")

        self.assertFalse(result["package_dir"].exists())
        self.assertFalse(result["package_json"].exists())
        self.assertFalse(
            tools._local_package_state_path(self.project_root).exists()
        )

    def test_none_mode_uses_and_preserves_existing_directory(self):
        installed_dir = self.project_root / "packages" / "SomePackage"
        installed_dir.mkdir(parents=True)
        marker = installed_dir / "keep.txt"
        marker.write_text("keep", encoding="utf-8")

        tools.install_local_houdini_package(
            self.project_root,
            installed_dir,
            self.source_json,
            directory_mode="none",
        )
        tools.remove_local_houdini_package(self.project_root, "SomePackage")

        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.assertFalse(
            (self.project_root / "packages" / "SomePackage.json").exists()
        )

    def test_none_mode_requires_existing_package_directory(self):
        with self.assertRaisesRegex(ValueError, "requires an existing package directory"):
            tools.install_local_houdini_package(
                self.project_root,
                self.source_dir,
                self.source_json,
                directory_mode="none",
            )

    def test_install_refuses_to_replace_unmanaged_directory_by_default(self):
        installed_dir = self.project_root / "packages" / "SomePackage"
        installed_dir.mkdir(parents=True)

        with self.assertRaises(FileExistsError):
            tools.install_local_houdini_package(
                self.project_root,
                self.source_dir,
                self.source_json,
                directory_mode="copy",
            )

        self.assertTrue(installed_dir.is_dir())

    def test_remove_detects_modified_installed_json(self):
        installed_dir = self.project_root / "packages" / "SomePackage"
        installed_dir.mkdir(parents=True)
        tools.install_local_houdini_package(
            self.project_root,
            installed_dir,
            self.source_json,
            directory_mode="none",
        )
        installed_json = self.project_root / "packages" / "SomePackage.json"
        installed_json.write_text('{"modified": true}\n', encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "modified after installation"):
            tools.remove_local_houdini_package(self.project_root, "SomePackage")

        tools.remove_local_houdini_package(
            self.project_root, "SomePackage", force=True
        )
        self.assertTrue(installed_dir.is_dir())
        self.assertFalse(installed_json.exists())

    def test_junction_install_and_remove_preserves_source(self):
        result = tools.install_local_houdini_package(
            self.project_root,
            self.source_dir,
            self.source_json,
            directory_mode="junction",
        )

        self.assertTrue(tools._is_directory_link(result["package_dir"]))
        self.assertEqual(result["package_dir"].resolve(), self.source_dir.resolve())

        tools.install_local_houdini_package(
            self.project_root,
            self.source_dir,
            self.source_json,
            directory_mode="junction",
        )

        tools.remove_local_houdini_package(self.project_root, "SomePackage")

        self.assertFalse(result["package_dir"].exists())
        self.assertTrue(self.source_dir.is_dir())
        self.assertTrue(self.source_json.is_file())


if __name__ == "__main__":
    unittest.main()
