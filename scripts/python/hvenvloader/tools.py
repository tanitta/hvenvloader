import json
import locale
import os
import platform
import re
import shutil
import shlex
import stat
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_HOUDINI_SUBDIRS = (
    "otls",
    "scripts",
    "toolbar",
    "python_panels",
    "desktop",
)
VANILLA_HOUDINI_PACKAGE_DIRS = frozenset(
    DEFAULT_HOUDINI_SUBDIRS
    + (
        "config",
        "dso",
        "gallery",
        "help",
        "hda",
        "icons",
        "packages",
        "pdg",
        "radialmenu",
        "soho",
        "usd",
        "vex",
        "viewer_states",
    )
)
EDITABLE_HOUDINI_PACKAGE_DIR_NAME = "_hvenvloader_houdini_packages"
STALE_EDITABLE_HOUDINI_BOOTSTRAP_JSON_NAME = "_hvenvloader_editable_packages.json"


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

    hvenvloader_root = _hvenvloader_root()
    template_path = hvenvloader_root / launcher_name
    text = template_path.read_text(encoding="utf-8")
    text = text.replace("@HOUDINI_EXE@", sys.executable)
    text = text.replace("@HOUDINI_USER_PREF_DIR@", _hou().getenv("HOUDINI_USER_PREF_DIR") or "")
    text = text.replace("@HVENVLOADER@", str(hvenvloader_root))

    launcher_path = root_path / launcher_name
    launcher_path.write_text(text, encoding="utf-8")

    if launcher_name == "houdini.sh":
        launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return launcher_path


def _uv_subprocess_env():
    env = os.environ.copy()

    if platform.system() == "Windows" and "GIT_CONFIG_GLOBAL" not in env:
        user_profile = env.get("USERPROFILE")
        if not user_profile and env.get("HOMEDRIVE") and env.get("HOMEPATH"):
            user_profile = env["HOMEDRIVE"] + env["HOMEPATH"]

        if user_profile:
            env["HOME"] = user_profile
            git_config = Path(user_profile) / ".gitconfig"
            if git_config.is_file():
                env["GIT_CONFIG_GLOBAL"] = str(git_config)

    return env


def _subprocess_output_encodings():
    encodings = ["utf-8"]
    seen = {"utf-8"}

    for encoding in (
        locale.getpreferredencoding(False),
        getattr(locale, "getencoding", lambda: None)(),
        sys.getfilesystemencoding(),
    ):
        if encoding and encoding.lower() not in seen:
            encodings.append(encoding)
            seen.add(encoding.lower())

    if os.name == "nt":
        for encoding in ("mbcs", "oem"):
            if encoding not in seen:
                encodings.append(encoding)
                seen.add(encoding)

    return encodings


def _decode_subprocess_output(data):
    if not data:
        return ""

    for encoding in _subprocess_output_encodings():
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            pass

    return data.decode("utf-8", errors="replace")


def _decode_completed_process_output(result):
    result.stdout = _decode_subprocess_output(result.stdout)
    result.stderr = _decode_subprocess_output(result.stderr)
    return result


def run_uv(args, cwd):
    result = subprocess.run(
        ["uv"] + list(args),
        cwd=str(cwd),
        env=_uv_subprocess_env(),
        capture_output=True,
        check=False,
    )
    return _decode_completed_process_output(result)


def run_uv_checked(args, cwd):
    result = run_uv(args, cwd)
    if result.returncode != 0:
        output = (result.stdout or "") + (result.stderr or "")
        raise RuntimeError(output.strip() or "uv command failed.")
    return result


def _format_command(args):
    return " ".join(shlex.quote(str(arg)) for arg in args)


def _uv_failure_hint(output):
    if "detected dubious ownership" not in output or "safe.directory" not in output:
        return ""

    path_match = re.search(r"repository at\s+'([^']+)'", output)
    if not path_match:
        path_match = re.search(r"safe\.directory\s+[\r\n]+\s*([^\s\r\n]+)", output)
    if not path_match:
        return (
            "Hint: Git rejected the local package repository because of dubious ownership.\n"
            "This tool does not modify Git safe.directory settings. If you trust this "
            "repository, run the suggested `git config --global --add safe.directory ...` "
            "command yourself, then retry."
        )

    repository_path = path_match.group(1)
    return (
        "Hint: Git rejected the local package repository because of dubious ownership.\n"
        "This tool does not modify Git safe.directory settings. If you trust this "
        "repository, run this yourself, then retry:\n"
        'git config --global --add safe.directory "{}"'.format(
            repository_path.replace('"', '\\"')
        )
    )


def _site_packages_paths(root_path):
    root_path = Path(root_path)
    version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)
    candidates = [
        root_path / ".venv" / "Lib" / "site-packages",
        root_path / ".venv" / "lib" / "python{}".format(version) / "site-packages",
        root_path / ".venv" / "lib" / "site-packages",
    ]
    return [path for path in candidates if path.is_dir()]


def _normalize_distribution_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _package_name_from_requirement(requirement):
    name = requirement.strip()
    name = re.split(r"\s|<|>|=|!|~|;|,|\[", name, maxsplit=1)[0]
    return name.strip()


def _metadata_name(dist_info_path):
    metadata_path = dist_info_path / "METADATA"
    if not metadata_path.is_file():
        return ""

    for line in metadata_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("name:"):
            return line.split(":", 1)[1].strip()
    return ""


def _dist_info_matches(dist_info_path, package_name):
    package_key = _normalize_distribution_name(package_name)
    metadata_name = _metadata_name(dist_info_path)
    if metadata_name and _normalize_distribution_name(metadata_name) == package_key:
        return True

    dist_info_name = dist_info_path.name
    if dist_info_name.endswith(".dist-info"):
        dist_info_name = dist_info_name[:-10]
    dist_name = dist_info_name.split("-", 1)[0]
    return _normalize_distribution_name(dist_name) == package_key


def _top_level_packages(dist_info_path):
    top_level_path = dist_info_path / "top_level.txt"
    if not top_level_path.is_file():
        return []

    packages = []
    for line in top_level_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            packages.append(line)
    return packages


def _path_from_file_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None

    path = unquote(parsed.path)
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    if parsed.netloc:
        path = "//{}/{}".format(parsed.netloc, path.lstrip("/"))
    return Path(path)


def _direct_url_path(dist_info_path):
    direct_url_path = dist_info_path / "direct_url.json"
    if not direct_url_path.is_file():
        return None

    try:
        data = json.loads(direct_url_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    url = data.get("url")
    if not url:
        return None
    return _path_from_file_url(url)


def _candidate_houdini_package_dirs(site_packages_path, package_name):
    package_key = _normalize_distribution_name(package_name)
    package_dirs = set()

    for dist_info_path in site_packages_path.glob("*.dist-info"):
        if not _dist_info_matches(dist_info_path, package_name):
            continue

        for top_level in _top_level_packages(dist_info_path):
            package_dirs.add(site_packages_path / top_level)

        direct_url_root = _direct_url_path(dist_info_path)
        if direct_url_root:
            for top_level in _top_level_packages(dist_info_path):
                package_dirs.add(direct_url_root / "src" / top_level)
                package_dirs.add(direct_url_root / top_level)

    for child in site_packages_path.iterdir():
        if child.is_dir() and _normalize_distribution_name(child.name) == package_key:
            package_dirs.add(child)

    return [path for path in package_dirs if (path / "hpackage.json").is_file()]


def _is_relative_to(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except (OSError, ValueError):
        return False


def _copied_json_path_for_package(site_packages_path, package_dir):
    if _is_relative_to(package_dir, site_packages_path):
        return site_packages_path / "{}.json".format(package_dir.name)
    return (
        site_packages_path
        / EDITABLE_HOUDINI_PACKAGE_DIR_NAME
        / "{}.json".format(package_dir.name)
    )


def _editable_link_path_for_package(site_packages_path, package_dir):
    if _is_relative_to(package_dir, site_packages_path):
        return None
    return site_packages_path / EDITABLE_HOUDINI_PACKAGE_DIR_NAME / package_dir.name


def _stale_editable_bootstrap_json_path(site_packages_path):
    return site_packages_path / STALE_EDITABLE_HOUDINI_BOOTSTRAP_JSON_NAME


def _remove_generated_package_link(link_path, package_dir):
    if link_path is None:
        return False
    if not link_path.exists() and not link_path.is_symlink():
        return False

    try:
        if link_path.resolve() != package_dir.resolve():
            return False
    except OSError:
        return False

    if link_path.is_dir() and not link_path.is_symlink():
        link_path.rmdir()
    else:
        link_path.unlink()
    return True


def _remove_editable_overlay_if_empty(site_packages_path, hou):
    overlay_path = site_packages_path / EDITABLE_HOUDINI_PACKAGE_DIR_NAME
    if not overlay_path.is_dir():
        return []

    try:
        next(overlay_path.iterdir())
        return []
    except StopIteration:
        pass

    messages = []
    overlay_path.rmdir()
    messages.append("Removed empty editable NVHP overlay: {}".format(overlay_path))

    bootstrap_json_path = _stale_editable_bootstrap_json_path(site_packages_path)
    if bootstrap_json_path.is_file():
        hou.ui.unloadPackage(str(bootstrap_json_path))
        messages.append(
            "Unloaded stale editable NVHP overlay bootstrap: {}".format(
                bootstrap_json_path
            )
        )
        bootstrap_json_path.unlink()
        messages.append(
            "Removed stale editable NVHP overlay bootstrap: {}".format(
                bootstrap_json_path
            )
        )
    return messages


def _houdini_package_entries_for_package(root_path, package_requirement):
    package_name = _package_name_from_requirement(package_requirement)
    if not package_name:
        return []

    entries = []
    seen = set()
    for site_packages_path in _site_packages_paths(root_path):
        for package_dir in _candidate_houdini_package_dirs(site_packages_path, package_name):
            source_json_path = package_dir / "hpackage.json"
            copied_json_path = _copied_json_path_for_package(site_packages_path, package_dir)
            link_path = _editable_link_path_for_package(site_packages_path, package_dir)
            key = (str(source_json_path), str(copied_json_path))
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "site_packages_path": site_packages_path,
                    "package_dir": package_dir,
                    "source_json_path": source_json_path,
                    "copied_json_path": copied_json_path,
                    "link_path": link_path,
                }
            )
    return entries


def unload_houdini_packages_for_removed_package(root_path, package_requirement):
    entries = _houdini_package_entries_for_package(root_path, package_requirement)
    if not entries:
        return []

    hou = _hou()
    messages = []
    for entry in entries:
        copied_json_path = entry["copied_json_path"]
        site_packages_path = entry["site_packages_path"]
        source_json_path = entry["source_json_path"]
        package_dir = entry["package_dir"]
        link_path = entry["link_path"]
        if not copied_json_path.is_file():
            messages.append(
                "Detected NVHP source, but no copied package JSON was found: {}".format(
                    source_json_path
                )
            )
            continue

        hou.ui.unloadPackage(str(copied_json_path))
        messages.append("Unloaded NVHP: {}".format(copied_json_path))
        copied_json_path.unlink()
        messages.append("Removed copied NVHP JSON: {}".format(copied_json_path))
        if _remove_generated_package_link(link_path, package_dir):
            messages.append("Removed editable NVHP link: {}".format(link_path))
            messages.extend(_remove_editable_overlay_if_empty(site_packages_path, hou))

    return messages


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

Native venvloader Houdini Package (NVHP) distributed as a Python package.

This package uses the hvenvloader-native package layout. Install it into a
project `.venv` and launch Houdini with the generated hvenvloader launcher.
It is not a standalone vanilla Houdini Package source layout.

## Layout

- `src/{package_name}/__init__.py` is the Python import package root.
- `src/{package_name}/hpackage.json` registers the installed package as an NVHP.
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
            self.setWindowTitle("Create NVHP")
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
            self.description_edit = QtWidgets.QLineEdit("My native venvloader Houdini package.")
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
                QtWidgets.QMessageBox.critical(self, "Create NVHP", str(exc))
                return

            QtWidgets.QMessageBox.information(
                self,
                "Create NVHP",
                "Created:\n{}".format(root_path),
            )
            self.accept()

    _exec_dialog(Dialog(_dialog_parent()))


def _copy_export_path(source_path, destination_path, overwrite):
    source_path = Path(source_path)
    destination_path = Path(destination_path)
    if destination_path.exists() or destination_path.is_symlink():
        if not overwrite:
            raise FileExistsError("{} already exists.".format(destination_path))
        if destination_path.is_dir() and not destination_path.is_symlink():
            shutil.rmtree(str(destination_path))
        else:
            destination_path.unlink()

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.is_dir():
        shutil.copytree(
            str(source_path),
            str(destination_path),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    else:
        shutil.copy2(str(source_path), str(destination_path))


def _export_reserved_name_conflicts(package_dir):
    conflicts = []
    for child in Path(package_dir).iterdir():
        if (
            child.is_dir()
            and child.name in VANILLA_HOUDINI_PACKAGE_DIRS
            and (child / "__init__.py").is_file()
        ):
            conflicts.append(child)
    return conflicts


def _copy_python_sources_for_export(source_root, destination_root):
    source_root = Path(source_root)
    destination_root = Path(destination_root)
    for source_path in source_root.rglob("*.py"):
        relative_path = source_path.relative_to(source_root)
        if "__pycache__" in relative_path.parts:
            continue
        if relative_path.parts and relative_path.parts[0] in VANILLA_HOUDINI_PACKAGE_DIRS:
            continue
        _copy_export_path(source_path, destination_root / relative_path, overwrite=True)


def export_nvhp(package_dir, export_dir, overwrite=False):
    package_dir = Path(package_dir)
    export_dir = Path(export_dir)
    if not package_dir.is_dir():
        raise ValueError("NVHP package directory does not exist: {}".format(package_dir))
    if not (package_dir / "hpackage.json").is_file():
        raise ValueError("NVHP package directory must contain hpackage.json: {}".format(package_dir))
    if not (package_dir / "__init__.py").is_file():
        raise ValueError("NVHP package directory must contain __init__.py: {}".format(package_dir))

    package_name = package_dir.name
    conflicts = _export_reserved_name_conflicts(package_dir)
    if conflicts:
        raise ValueError(
            "Reserved Houdini directory names cannot also be Python subpackages:\n{}".format(
                "\n".join(str(path) for path in conflicts)
            )
        )
    legacy_python_package_dir = package_dir / "scripts" / "python" / package_name
    if legacy_python_package_dir.exists():
        raise ValueError(
            "NVHP package directory already contains a vanilla scripts/python package path: {}".format(
                legacy_python_package_dir
            )
        )

    if _is_relative_to(export_dir, package_dir):
        raise ValueError("Export directory must not be inside the source package directory.")

    exported_package_dir = export_dir / package_name
    if exported_package_dir.resolve() == package_dir.resolve():
        raise ValueError("Export package directory would overwrite the source package directory.")

    exported_json_path = export_dir / "{}.json".format(package_name)
    if not overwrite:
        if exported_json_path.exists():
            raise FileExistsError("{} already exists.".format(exported_json_path))
        if exported_package_dir.exists() or exported_package_dir.is_symlink():
            raise FileExistsError("{} already exists.".format(exported_package_dir))

    export_dir.mkdir(parents=True, exist_ok=True)
    _copy_export_path(package_dir / "hpackage.json", exported_json_path, overwrite)

    if exported_package_dir.exists() or exported_package_dir.is_symlink():
        if not overwrite:
            raise FileExistsError("{} already exists.".format(exported_package_dir))
        if exported_package_dir.is_dir() and not exported_package_dir.is_symlink():
            shutil.rmtree(str(exported_package_dir))
        else:
            exported_package_dir.unlink()
    exported_package_dir.mkdir(parents=True, exist_ok=True)

    python_package_dir = exported_package_dir / "scripts" / "python" / package_name
    for child in package_dir.iterdir():
        if child.name in ("hpackage.json", "__pycache__"):
            continue
        if child.name in VANILLA_HOUDINI_PACKAGE_DIRS:
            _copy_export_path(child, exported_package_dir / child.name, overwrite=True)
    _copy_python_sources_for_export(package_dir, python_package_dir)

    return {
        "export_dir": export_dir,
        "package_json": exported_json_path,
        "package_dir": exported_package_dir,
        "python_package_dir": python_package_dir,
    }


def export_nvhp_tool():
    QtCore, QtWidgets = _qt_modules()

    class Dialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super(Dialog, self).__init__(parent)
            self.setWindowTitle("Export NVHP")
            self.setMinimumWidth(620)

            layout = QtWidgets.QVBoxLayout(self)
            form = QtWidgets.QFormLayout()
            layout.addLayout(form)

            self.package_dir_edit = QtWidgets.QLineEdit(str(_default_project_root()))
            package_browse_button = QtWidgets.QPushButton("...")
            package_browse_button.clicked.connect(self._browse_package_dir)
            package_dir_layout = QtWidgets.QHBoxLayout()
            package_dir_layout.addWidget(self.package_dir_edit)
            package_dir_layout.addWidget(package_browse_button)
            form.addRow("NVHP Package Directory", package_dir_layout)

            self.export_dir_edit = QtWidgets.QLineEdit(str(_default_project_root() / "export"))
            export_browse_button = QtWidgets.QPushButton("...")
            export_browse_button.clicked.connect(self._browse_export_dir)
            export_dir_layout = QtWidgets.QHBoxLayout()
            export_dir_layout.addWidget(self.export_dir_edit)
            export_dir_layout.addWidget(export_browse_button)
            form.addRow("Export Directory", export_dir_layout)

            self.output_json_edit = QtWidgets.QLineEdit()
            self.output_json_edit.setReadOnly(True)
            form.addRow("Package JSON", self.output_json_edit)

            self.output_folder_edit = QtWidgets.QLineEdit()
            self.output_folder_edit.setReadOnly(True)
            form.addRow("Package Folder", self.output_folder_edit)

            self.overwrite_check = QtWidgets.QCheckBox("Overwrite existing exported package")
            layout.addWidget(self.overwrite_check)

            self.package_dir_edit.textChanged.connect(self._update_preview)
            self.export_dir_edit.textChanged.connect(self._update_preview)

            ok_button = _dialog_button(QtWidgets, "Ok")
            cancel_button = _dialog_button(QtWidgets, "Cancel")
            buttons = QtWidgets.QDialogButtonBox(ok_button | cancel_button)
            buttons.button(ok_button).setText("Export")
            buttons.accepted.connect(self._export)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            self._update_preview()

        def _browse_package_dir(self):
            selected = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Select NVHP Package Directory",
                self.package_dir_edit.text(),
            )
            if selected:
                self.package_dir_edit.setText(selected)

        def _browse_export_dir(self):
            selected = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Select Export Directory",
                self.export_dir_edit.text(),
            )
            if selected:
                self.export_dir_edit.setText(selected)

        def _update_preview(self):
            package_name = Path(self.package_dir_edit.text()).name
            if not package_name:
                self.output_json_edit.clear()
                self.output_folder_edit.clear()
                return
            export_dir = Path(self.export_dir_edit.text())
            self.output_json_edit.setText(str(export_dir / "{}.json".format(package_name)))
            self.output_folder_edit.setText(str(export_dir / package_name))

        def _export(self):
            try:
                result = export_nvhp(
                    self.package_dir_edit.text(),
                    self.export_dir_edit.text(),
                    overwrite=self.overwrite_check.isChecked(),
                )
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Export NVHP", str(exc))
                return

            QtWidgets.QMessageBox.information(
                self,
                "Export NVHP",
                "Exported:\n{}\n\nPackage JSON:\n{}".format(
                    result["package_dir"],
                    result["package_json"],
                ),
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
            self.package_edit.setPlaceholderText("Package name, requirement, or local path")
            local_button = QtWidgets.QPushButton("Local...")
            local_button.clicked.connect(self._browse_package_path)
            add_button = QtWidgets.QPushButton("Install package (uv add)")
            add_button.clicked.connect(self._add)
            remove_button = QtWidgets.QPushButton("Remove package (uv remove)")
            remove_button.clicked.connect(self._remove)
            self.editable_check = QtWidgets.QCheckBox("Install as editable (--editable)")
            package_layout.addWidget(QtWidgets.QLabel("Package"), 0, 0)
            package_layout.addWidget(self.package_edit, 0, 1)
            package_layout.addWidget(local_button, 0, 2)
            package_layout.addWidget(self.editable_check, 1, 1)
            package_layout.addWidget(add_button, 1, 2)
            package_layout.addWidget(remove_button, 1, 3)

            package_layout.setColumnStretch(1, 1)
            layout.addWidget(package_group)

            self.output_edit = QtWidgets.QPlainTextEdit()
            self.output_edit.setReadOnly(True)
            layout.addWidget(self.output_edit)

            bottom_layout = QtWidgets.QHBoxLayout()
            clear_log_button = QtWidgets.QPushButton("Clear Log")
            clear_log_button.clicked.connect(self.output_edit.clear)
            bottom_layout.addWidget(clear_log_button)
            bottom_layout.addStretch()

            close_button = QtWidgets.QDialogButtonBox(_dialog_button(QtWidgets, "Close"))
            close_button.rejected.connect(self.reject)
            bottom_layout.addWidget(close_button)
            layout.addLayout(bottom_layout)

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

        def _browse_package_path(self):
            selected = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Select Local Package Directory",
                str(self._project_root()),
            )
            if selected:
                self.package_edit.setText(self._package_path_text(Path(selected)))

        def _package_path_text(self, package_path):
            root = self._project_root()
            try:
                relative_path = package_path.resolve().relative_to(root.resolve())
            except ValueError:
                return str(package_path)

            text = relative_path.as_posix()
            if text == ".":
                return "."
            if not text.startswith("."):
                text = "./" + text
            return text

        def _append_output(self, text):
            self.output_edit.appendPlainText(text.rstrip())
            self.output_edit.verticalScrollBar().setValue(
                self.output_edit.verticalScrollBar().maximum()
            )

        def _run(self, args):
            root = self._project_root()
            self._append_output("$ uv {}".format(_format_command(args)))
            try:
                result = run_uv(args, root)
            except Exception as exc:
                self._append_output(str(exc))
                return

            output = (result.stdout or "") + (result.stderr or "")
            if output.strip():
                self._append_output(output)
            hint = _uv_failure_hint(output)
            if result.returncode != 0 and hint:
                self._append_output(hint)
            self._append_output("exit code: {}\n".format(result.returncode))
            return result

        def _init(self):
            self._run(["init", "-p", python_version_tag()])

        def _add(self):
            package = self.package_edit.text().strip()
            if not package:
                QtWidgets.QMessageBox.warning(self, "uv", "Package requirement is required.")
                return
            args = ["add"]
            if self.editable_check.isChecked():
                args.append("--editable")
            args.append(package)
            self._run(args)

        def _remove(self):
            package = self.package_edit.text().strip()
            if not package:
                QtWidgets.QMessageBox.warning(self, "uv", "Installed package name is required.")
                return
            try:
                messages = unload_houdini_packages_for_removed_package(
                    self._project_root(),
                    package,
                )
            except Exception as exc:
                self._append_output("Failed to unload NVHP before uv remove: {}".format(exc))
                QtWidgets.QMessageBox.critical(
                    self,
                    "uv remove",
                    "Failed to unload NVHP before uv remove.\n\n{}".format(exc),
                )
                return

            for message in messages:
                self._append_output(message)
            self._run(["remove", package])

        def _write_launcher(self):
            try:
                launcher_path = generate_launcher(self._project_root())
            except Exception as exc:
                self._append_output(str(exc))
                return
            self._append_output("Wrote launcher: {}\n".format(launcher_path))

    _exec_dialog(Dialog(_dialog_parent()))
