import json
import platform
import re
import stat
import subprocess
import sys
from pathlib import Path


DEFAULT_HOUDINI_SUBDIRS = (
    "otls",
    "scripts",
    "toolbar",
    "python_panels",
    "desktop",
)


def _hou():
    import hou

    return hou


def _qt_modules():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets

    return QtCore, QtWidgets


def _dialog_parent():
    try:
        hou = _hou()
        return hou.qt.mainWindow()
    except Exception:
        return None


def _exec_dialog(dialog):
    if hasattr(dialog, "exec"):
        return dialog.exec()
    return dialog.exec_()


def _dialog_button(QtWidgets, name):
    standard_button = getattr(QtWidgets.QDialogButtonBox, "StandardButton", None)
    if standard_button is not None and hasattr(standard_button, name):
        return getattr(standard_button, name)
    return getattr(QtWidgets.QDialogButtonBox, name)


def _display_message(message, severity=None):
    hou = _hou()
    if severity is None:
        severity = hou.severityType.Message
    hou.ui.displayMessage(message, severity=severity)


def _display_error(message):
    hou = _hou()
    _display_message(message, severity=hou.severityType.Error)


def _project_root_from_job():
    hou = _hou()
    job = hou.getenv("JOB")
    if not job:
        raise RuntimeError("$JOB is not set.")
    return Path(hou.text.expandString("$JOB"))


def _default_project_root():
    try:
        return _project_root_from_job()
    except Exception:
        return Path.home()


def _hvenvloader_root():
    hou = _hou()
    package_path = hou.getenv("HVENVLOADER")
    if not package_path:
        raise RuntimeError("HVENVLOADER is not set.")
    return Path(hou.text.expandString(package_path))


def python_version_tag():
    return "{}.{}".format(sys.version_info.major, sys.version_info.minor)


def generate_launcher(root_path):
    root_path = Path(root_path)
    launcher_name = "houdini.sh"
    if platform.system() == "Windows":
        launcher_name = "houdini.bat"

    template_path = _hvenvloader_root() / launcher_name
    text = template_path.read_text(encoding="utf-8")
    text = text.replace("@HOUDINI_EXE@", sys.executable)
    text = text.replace("@HOUDINI_USER_PREF_DIR@", _hou().getenv("HOUDINI_USER_PREF_DIR") or "")

    launcher_path = root_path / launcher_name
    launcher_path.write_text(text, encoding="utf-8")

    if launcher_name == "houdini.sh":
        launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return launcher_path


def run_uv(args, cwd):
    return subprocess.run(
        ["uv"] + list(args),
        cwd=str(cwd),
        capture_output=True,
        check=False,
        text=True,
    )


def run_uv_checked(args, cwd):
    result = run_uv(args, cwd)
    if result.returncode != 0:
        output = (result.stdout or "") + (result.stderr or "")
        raise RuntimeError(output.strip() or "uv command failed.")
    return result


def init_python_project(root_path):
    run_uv_checked(["init", "-p", python_version_tag()], root_path)
    run_uv_checked(["sync"], root_path)


def init_project_tool():
    try:
        root_path = _project_root_from_job()
        launcher_path = generate_launcher(root_path)
        init_python_project(root_path)
    except Exception as exc:
        _display_error(str(exc))
        return

    _display_message("Project initialized.\n\nLauncher:\n{}".format(launcher_path))


def _safe_import_package_name(name):
    value = re.sub(r"\W+", "_", name.strip())
    value = value.strip("_")
    if not value:
        value = "houdini_package"
    if value[0].isdigit():
        value = "_" + value
    return value


def _safe_env_var(name):
    value = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_").upper()
    if not value:
        value = "HOUDINI_PACKAGE"
    if value[0].isdigit():
        value = "_" + value
    return value


def _toml_string(value):
    return json.dumps(value)


def _write_text(path, text, overwrite):
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError("{} already exists.".format(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _pyproject_text(project_name, package_name, version, description, requires_python, subdirs):
    package_data = ['"hpackage.json"']
    package_data.extend('"{}"'.format(subdir.rstrip("/") + "/**/*") for subdir in subdirs)
    package_data_text = ",\n  ".join(package_data)

    return """[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = {project_name}
version = {version}
description = {description}
requires-python = {requires_python}
dependencies = []

[tool.setuptools]
package-dir = {{"" = "src"}}

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
{package_name} = [
  {package_data}
]
""".format(
        project_name=_toml_string(project_name),
        version=_toml_string(version),
        description=_toml_string(description),
        requires_python=_toml_string(requires_python),
        package_name=package_name,
        package_data=package_data_text,
    )


def _readme_text(project_name, package_name):
    return """# {project_name}

Houdini package distributed as a Python package.

## Layout

- `src/{package_name}/hpackage.json` registers the installed package as a Houdini package.
- Houdini assets can be placed under package subdirectories such as `otls`, `scripts`, `toolbar`, and `python_panels`.
""".format(
        project_name=project_name,
        package_name=package_name,
    )


def create_houdini_package(
    save_dir,
    project_name,
    package_name,
    env_var,
    version,
    description,
    requires_python,
    subdirs,
    include_readme=True,
    overwrite=False,
):
    save_dir = Path(save_dir)
    project_name = project_name.strip()
    package_name = _safe_import_package_name(package_name)
    env_var = _safe_env_var(env_var)
    root_path = save_dir / project_name
    package_path = root_path / "src" / package_name

    if not project_name:
        raise ValueError("Project name is required.")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", project_name):
        raise ValueError("Project name can contain letters, numbers, '.', '_', and '-' only.")
    if root_path.exists() and any(root_path.iterdir()) and not overwrite:
        raise FileExistsError("{} already exists and is not empty.".format(root_path))

    root_path.mkdir(parents=True, exist_ok=True)
    package_path.mkdir(parents=True, exist_ok=True)

    _write_text(
        root_path / "pyproject.toml",
        _pyproject_text(
            project_name,
            package_name,
            version.strip() or "0.1.0",
            description.strip(),
            requires_python.strip() or ">=3.10",
            subdirs,
        ),
        overwrite,
    )
    _write_text(package_path / "__init__.py", "", overwrite)

    houdini_package = {
        "hpath": "${}".format(env_var),
        "env": [
            {
                env_var: "$HOUDINI_PACKAGE_PATH/{}".format(package_name),
            }
        ],
    }
    _write_text(
        package_path / "hpackage.json",
        json.dumps(houdini_package, indent=4) + "\n",
        overwrite,
    )

    for subdir in subdirs:
        subdir_path = package_path / subdir
        subdir_path.mkdir(parents=True, exist_ok=True)
        _write_text(subdir_path / ".gitkeep", "", overwrite)

    if include_readme:
        _write_text(root_path / "README.md", _readme_text(project_name, package_name), overwrite)

    return root_path


def create_houdini_package_tool():
    QtCore, QtWidgets = _qt_modules()

    class Dialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super(Dialog, self).__init__(parent)
            self.setWindowTitle("Create Houdini Package")
            self.setMinimumWidth(560)
            self._auto_package_name = True
            self._auto_env_var = True

            layout = QtWidgets.QVBoxLayout(self)
            form = QtWidgets.QFormLayout()
            layout.addLayout(form)

            self.save_dir_edit = QtWidgets.QLineEdit(str(_default_project_root()))
            browse_button = QtWidgets.QPushButton("...")
            browse_button.clicked.connect(self._browse_save_dir)
            save_dir_layout = QtWidgets.QHBoxLayout()
            save_dir_layout.addWidget(self.save_dir_edit)
            save_dir_layout.addWidget(browse_button)
            form.addRow("Save Directory", save_dir_layout)

            self.generated_folder_edit = QtWidgets.QLineEdit()
            self.generated_folder_edit.setReadOnly(True)
            form.addRow("Generated Folder", self.generated_folder_edit)

            self.project_name_edit = QtWidgets.QLineEdit("MyHoudiniPackage")
            self.package_name_edit = QtWidgets.QLineEdit("MyHoudiniPackage")
            self.env_var_edit = QtWidgets.QLineEdit("MYHOUDINIPACKAGE")
            self.version_edit = QtWidgets.QLineEdit("0.1.0")
            self.description_edit = QtWidgets.QLineEdit("My hvenvloader-compatible Houdini package.")
            self.requires_python_edit = QtWidgets.QLineEdit(">={}".format(python_version_tag()))

            self.save_dir_edit.textChanged.connect(self._update_generated_folder)
            self.project_name_edit.textChanged.connect(self._sync_generated_names)
            self.package_name_edit.textEdited.connect(self._package_name_edited)
            self.env_var_edit.textEdited.connect(self._env_var_edited)

            form.addRow("Project Name", self.project_name_edit)
            form.addRow("Import Package", self.package_name_edit)
            form.addRow("Houdini Env Var", self.env_var_edit)
            form.addRow("Version", self.version_edit)
            form.addRow("Description", self.description_edit)
            form.addRow("Requires Python", self.requires_python_edit)

            group = QtWidgets.QGroupBox("Houdini Directories")
            group_layout = QtWidgets.QGridLayout(group)
            self.subdir_checks = []
            for index, subdir in enumerate(DEFAULT_HOUDINI_SUBDIRS):
                checkbox = QtWidgets.QCheckBox(subdir)
                checkbox.setChecked(subdir in ("otls", "scripts", "toolbar", "python_panels"))
                self.subdir_checks.append(checkbox)
                group_layout.addWidget(checkbox, index // 2, index % 2)
            layout.addWidget(group)

            self.include_readme_check = QtWidgets.QCheckBox("Create README.md")
            self.include_readme_check.setChecked(True)
            self.overwrite_check = QtWidgets.QCheckBox("Overwrite existing files")
            layout.addWidget(self.include_readme_check)
            layout.addWidget(self.overwrite_check)

            ok_button = _dialog_button(QtWidgets, "Ok")
            cancel_button = _dialog_button(QtWidgets, "Cancel")
            buttons = QtWidgets.QDialogButtonBox(ok_button | cancel_button)
            buttons.button(ok_button).setText("Create")
            buttons.accepted.connect(self._create)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            self._update_generated_folder()

        def _browse_save_dir(self):
            selected = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Select Save Directory",
                self.save_dir_edit.text(),
            )
            if selected:
                self.save_dir_edit.setText(selected)

        def _package_name_edited(self):
            self._auto_package_name = False
            if self._auto_env_var:
                self.env_var_edit.setText(_safe_env_var(self.package_name_edit.text()))

        def _env_var_edited(self):
            self._auto_env_var = False

        def _sync_generated_names(self, text):
            if self._auto_package_name:
                self.package_name_edit.setText(_safe_import_package_name(text))
            if self._auto_env_var:
                self.env_var_edit.setText(_safe_env_var(self.package_name_edit.text()))
            self._update_generated_folder()

        def _update_generated_folder(self):
            project_name = self.project_name_edit.text().strip()
            if not project_name:
                self.generated_folder_edit.clear()
                return
            self.generated_folder_edit.setText(str(Path(self.save_dir_edit.text()) / project_name))

        def _create(self):
            subdirs = [
                checkbox.text()
                for checkbox in self.subdir_checks
                if checkbox.isChecked()
            ]
            try:
                root_path = create_houdini_package(
                    save_dir=self.save_dir_edit.text(),
                    project_name=self.project_name_edit.text(),
                    package_name=self.package_name_edit.text(),
                    env_var=self.env_var_edit.text(),
                    version=self.version_edit.text(),
                    description=self.description_edit.text(),
                    requires_python=self.requires_python_edit.text(),
                    subdirs=subdirs,
                    include_readme=self.include_readme_check.isChecked(),
                    overwrite=self.overwrite_check.isChecked(),
                )
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Create Houdini Package", str(exc))
                return

            QtWidgets.QMessageBox.information(
                self,
                "Create Houdini Package",
                "Created:\n{}".format(root_path),
            )
            self.accept()

    _exec_dialog(Dialog(_dialog_parent()))


def uv_tool():
    QtCore, QtWidgets = _qt_modules()

    class Dialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super(Dialog, self).__init__(parent)
            self.setWindowTitle("uv")
            self.setMinimumSize(720, 460)

            layout = QtWidgets.QVBoxLayout(self)
            form = QtWidgets.QFormLayout()
            layout.addLayout(form)

            self.root_edit = QtWidgets.QLineEdit(str(_default_project_root()))
            browse_button = QtWidgets.QPushButton("...")
            browse_button.clicked.connect(self._browse_root)
            root_layout = QtWidgets.QHBoxLayout()
            root_layout.addWidget(self.root_edit)
            root_layout.addWidget(browse_button)
            form.addRow("Project Root", root_layout)

            project_group = QtWidgets.QGroupBox("Project")
            project_layout = QtWidgets.QGridLayout(project_group)
            project_actions = [
                ("Create pyproject (uv init)", self._init),
                ("Sync venv (uv sync)", lambda: self._run(["sync"])),
                ("Update lockfile (uv lock)", lambda: self._run(["lock"])),
                ("Show dependency tree (uv tree)", lambda: self._run(["tree"])),
                ("Write Houdini launcher", self._write_launcher),
            ]
            for index, (label, callback) in enumerate(project_actions):
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(callback)
                project_layout.addWidget(button, index // 2, index % 2)
            layout.addWidget(project_group)

            package_group = QtWidgets.QGroupBox("Package")
            package_layout = QtWidgets.QGridLayout(package_group)

            self.package_edit = QtWidgets.QLineEdit()
            self.package_edit.setPlaceholderText("Package name or requirement")
            add_button = QtWidgets.QPushButton("Install package (uv add)")
            add_button.clicked.connect(self._add)
            remove_button = QtWidgets.QPushButton("Remove package (uv remove)")
            remove_button.clicked.connect(self._remove)
            package_layout.addWidget(QtWidgets.QLabel("Package"), 0, 0)
            package_layout.addWidget(self.package_edit, 0, 1)
            package_layout.addWidget(add_button, 0, 2)
            package_layout.addWidget(remove_button, 0, 3)

            package_layout.setColumnStretch(1, 1)
            layout.addWidget(package_group)

            self.output_edit = QtWidgets.QPlainTextEdit()
            self.output_edit.setReadOnly(True)
            layout.addWidget(self.output_edit)

            close_button = QtWidgets.QDialogButtonBox(_dialog_button(QtWidgets, "Close"))
            close_button.rejected.connect(self.reject)
            layout.addWidget(close_button)

        def _browse_root(self):
            selected = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Select Project Root",
                self.root_edit.text(),
            )
            if selected:
                self.root_edit.setText(selected)

        def _project_root(self):
            return Path(self.root_edit.text())

        def _append_output(self, text):
            self.output_edit.appendPlainText(text.rstrip())
            self.output_edit.verticalScrollBar().setValue(
                self.output_edit.verticalScrollBar().maximum()
            )

        def _run(self, args):
            root = self._project_root()
            self._append_output("$ uv {}".format(" ".join(args)))
            try:
                result = run_uv(args, root)
            except Exception as exc:
                self._append_output(str(exc))
                return

            output = (result.stdout or "") + (result.stderr or "")
            if output.strip():
                self._append_output(output)
            self._append_output("exit code: {}\n".format(result.returncode))
            return result

        def _init(self):
            self._run(["init", "-p", python_version_tag()])

        def _add(self):
            package = self.package_edit.text().strip()
            if not package:
                QtWidgets.QMessageBox.warning(self, "uv", "Package requirement is required.")
                return
            self._run(["add", package])

        def _remove(self):
            package = self.package_edit.text().strip()
            if not package:
                QtWidgets.QMessageBox.warning(self, "uv", "Installed package name is required.")
                return
            self._run(["remove", package])

        def _write_launcher(self):
            try:
                launcher_path = generate_launcher(self._project_root())
            except Exception as exc:
                self._append_output(str(exc))
                return
            self._append_output("Wrote launcher: {}\n".format(launcher_path))

    _exec_dialog(Dialog(_dialog_parent()))
