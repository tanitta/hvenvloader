import json
import hashlib
import locale
import os
import platform
import re
import shutil
import shlex
import stat
import subprocess
import sys
import uuid
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
HVENVLOADER_MANAGED_DIR_NAME = ".hvenvloader"
EDITABLE_HOUDINI_PACKAGE_DIR_NAME = "editable_packages"
STALE_EDITABLE_HOUDINI_BOOTSTRAP_JSON_NAME = "_hvenvloader_editable_packages.json"
LOCAL_PACKAGE_STATE_NAME = "local_packages.json"
LOCAL_PACKAGE_DIRECTORY_MODES = ("junction", "copy", "none")


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


def _dialog_button_role(QtWidgets, name):
    button_role = getattr(QtWidgets.QDialogButtonBox, "ButtonRole", None)
    if button_role is not None and hasattr(button_role, name):
        return getattr(button_role, name)
    return getattr(QtWidgets.QDialogButtonBox, name)


def _message_box_button(QtWidgets, name):
    standard_button = getattr(QtWidgets.QMessageBox, "StandardButton", None)
    if standard_button is not None and hasattr(standard_button, name):
        return getattr(standard_button, name)
    return getattr(QtWidgets.QMessageBox, name)


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


def uv_init_args(install_project=True):
    args = ["init"]
    if install_project:
        args.extend(["--package", "--build-backend", "setuptools"])
    else:
        args.append("--no-package")
    args.extend(["-p", python_version_tag()])
    return args


def launcher_name():
    if platform.system() == "Windows":
        return "houdini.bat"
    return "houdini.sh"


def launcher_path(root_path):
    return Path(root_path) / launcher_name()


def generate_launcher(root_path):
    root_path = Path(root_path)
    current_launcher_name = launcher_name()

    hvenvloader_root = _hvenvloader_root()
    template_path = hvenvloader_root / current_launcher_name
    text = template_path.read_text(encoding="utf-8")
    text = text.replace("@HOUDINI_EXE@", sys.executable)
    text = text.replace("@HOUDINI_USER_PREF_DIR@", _hou().getenv("HOUDINI_USER_PREF_DIR") or "")
    text = text.replace("@HVENVLOADER@", str(hvenvloader_root))

    output_launcher_path = root_path / current_launcher_name
    newline = "\r\n" if current_launcher_name == "houdini.bat" else "\n"
    output_launcher_path.write_text(text, encoding="utf-8", newline=newline)

    if current_launcher_name == "houdini.sh":
        output_launcher_path.chmod(output_launcher_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return output_launcher_path


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


def _editable_direct_url_path(dist_info_path):
    direct_url_path = dist_info_path / "direct_url.json"
    if not direct_url_path.is_file():
        return None

    try:
        data = json.loads(direct_url_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    if not data.get("dir_info", {}).get("editable"):
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

        direct_url_root = _editable_direct_url_path(dist_info_path)
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


def _absolute_path_without_links(path):
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _is_relative_to_without_links(path, parent):
    try:
        _absolute_path_without_links(path).relative_to(
            _absolute_path_without_links(parent)
        )
        return True
    except ValueError:
        return False


def _editable_overlay_path(root_path):
    return (
        Path(root_path)
        / HVENVLOADER_MANAGED_DIR_NAME
        / EDITABLE_HOUDINI_PACKAGE_DIR_NAME
    )


def _copied_json_path_for_package(root_path, site_packages_path, package_dir):
    if _is_relative_to(package_dir, site_packages_path):
        return site_packages_path / "{}.json".format(package_dir.name)
    return _editable_overlay_path(root_path) / "{}.json".format(package_dir.name)


def _editable_link_path_for_package(root_path, site_packages_path, package_dir):
    if _is_relative_to(package_dir, site_packages_path):
        return None
    return _editable_overlay_path(root_path) / package_dir.name


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


def _remove_editable_overlay_if_empty(root_path, site_packages_path, hou):
    overlay_path = _editable_overlay_path(root_path)
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
            copied_json_path = _copied_json_path_for_package(
                root_path,
                site_packages_path,
                package_dir,
            )
            link_path = _editable_link_path_for_package(
                root_path,
                site_packages_path,
                package_dir,
            )
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
            messages.extend(
                _remove_editable_overlay_if_empty(root_path, site_packages_path, hou)
            )

    return messages


def init_python_project(root_path, install_project=True):
    run_uv_checked(uv_init_args(install_project), root_path)
    run_uv_checked(["sync"], root_path)


def init_project_tool():
    QtCore, QtWidgets = _qt_modules()

    class Dialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super(Dialog, self).__init__(parent)
            self.setWindowTitle("Init Project")
            self.setMinimumSize(680, 360)

            layout = QtWidgets.QVBoxLayout(self)

            form = QtWidgets.QFormLayout()
            layout.addLayout(form)

            self.root_edit = QtWidgets.QLineEdit(str(_default_project_root()))
            self.root_edit.editingFinished.connect(self._refresh)
            browse_button = QtWidgets.QPushButton("...")
            browse_button.clicked.connect(self._browse_root)
            refresh_button = QtWidgets.QPushButton("Refresh")
            refresh_button.clicked.connect(self._refresh)

            root_layout = QtWidgets.QHBoxLayout()
            root_layout.addWidget(self.root_edit)
            root_layout.addWidget(browse_button)
            root_layout.addWidget(refresh_button)
            form.addRow("Project Root", root_layout)

            actions_group = QtWidgets.QGroupBox("Actions")
            actions_layout = QtWidgets.QGridLayout(actions_group)
            actions_layout.addWidget(QtWidgets.QLabel("Run"), 0, 0)
            actions_layout.addWidget(QtWidgets.QLabel("Status"), 0, 1)

            self.init_check = QtWidgets.QCheckBox("uv init")
            self.init_status = QtWidgets.QLabel()
            actions_layout.addWidget(self.init_check, 1, 0)
            actions_layout.addWidget(self.init_status, 1, 1)

            self.install_project_check = QtWidgets.QCheckBox(
                "Install this project into the venv (--package)"
            )
            self.install_project_check.setChecked(True)
            self.install_project_check.setToolTip(
                "Create an installable src-layout setuptools package. "
                "uv sync will install this project into .venv."
            )
            self.init_check.toggled.connect(self.install_project_check.setEnabled)
            actions_layout.addWidget(self.install_project_check, 2, 0, 1, 2)

            self.sync_check = QtWidgets.QCheckBox("uv sync")
            self.sync_status = QtWidgets.QLabel()
            actions_layout.addWidget(self.sync_check, 3, 0)
            actions_layout.addWidget(self.sync_status, 3, 1)

            self.launcher_check = QtWidgets.QCheckBox("Write launcher")
            self.launcher_status = QtWidgets.QLabel()
            actions_layout.addWidget(self.launcher_check, 4, 0)
            actions_layout.addWidget(self.launcher_status, 4, 1)
            actions_layout.setColumnStretch(1, 1)
            layout.addWidget(actions_group)

            self.output_edit = QtWidgets.QPlainTextEdit()
            self.output_edit.setReadOnly(True)
            layout.addWidget(self.output_edit)

            buttons = QtWidgets.QDialogButtonBox()
            run_button = buttons.addButton(
                "Run Selected",
                _dialog_button_role(QtWidgets, "AcceptRole"),
            )
            run_button.clicked.connect(self._run_selected)
            close_button = buttons.addButton(_dialog_button(QtWidgets, "Close"))
            close_button.clicked.connect(self.reject)
            layout.addWidget(buttons)

            self._refresh()

        def _browse_root(self):
            selected = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Select Project Root",
                self.root_edit.text(),
            )
            if selected:
                self.root_edit.setText(selected)
                self._refresh()

        def _project_root(self):
            return Path(self.root_edit.text())

        def _status_text(self, label, path):
            if path.exists():
                return "{}: Exists ({})".format(label, path)
            return "{}: New ({})".format(label, path)

        def _refresh(self):
            root_path = self._project_root()
            pyproject_path = root_path / "pyproject.toml"
            venv_path = root_path / ".venv"
            output_launcher_path = launcher_path(root_path)

            self.init_status.setText(self._status_text("pyproject.toml", pyproject_path))
            self.sync_status.setText(self._status_text(".venv", venv_path))
            self.launcher_status.setText(
                self._status_text(output_launcher_path.name, output_launcher_path)
            )

            self.init_check.setChecked(not pyproject_path.exists())
            self.sync_check.setChecked(not venv_path.exists())
            self.launcher_check.setChecked(not output_launcher_path.exists())

        def _append_output(self, text):
            self.output_edit.appendPlainText(text.rstrip())
            self.output_edit.verticalScrollBar().setValue(
                self.output_edit.verticalScrollBar().maximum()
            )

        def _run_uv(self, args, root_path):
            self._append_output("$ uv {}".format(_format_command(args)))
            result = run_uv(args, root_path)
            output = (result.stdout or "") + (result.stderr or "")
            if output.strip():
                self._append_output(output)
            hint = _uv_failure_hint(output)
            if result.returncode != 0 and hint:
                self._append_output(hint)
            self._append_output("exit code: {}\n".format(result.returncode))
            return result.returncode == 0

        def _run_selected(self):
            root_path = self._project_root()
            if not root_path.is_dir():
                QtWidgets.QMessageBox.warning(
                    self,
                    "Init Project",
                    "Project root does not exist:\n{}".format(root_path),
                )
                return

            run_init = self.init_check.isChecked()
            run_sync = self.sync_check.isChecked()
            write_launcher = self.launcher_check.isChecked()
            if not (run_init or run_sync or write_launcher):
                QtWidgets.QMessageBox.information(
                    self,
                    "Init Project",
                    "No actions are selected.",
                )
                return

            pyproject_path = root_path / "pyproject.toml"
            if run_init and pyproject_path.exists():
                answer = QtWidgets.QMessageBox.question(
                    self,
                    "Init Project",
                    "pyproject.toml already exists. Run uv init anyway?\n{}".format(
                        pyproject_path
                    ),
                )
                if answer != _message_box_button(QtWidgets, "Yes"):
                    return

            if run_sync and not run_init and not pyproject_path.is_file():
                QtWidgets.QMessageBox.warning(
                    self,
                    "Init Project",
                    "uv sync needs pyproject.toml. Select uv init or create pyproject.toml first.",
                )
                return

            output_launcher_path = launcher_path(root_path)
            if write_launcher and output_launcher_path.exists():
                answer = QtWidgets.QMessageBox.question(
                    self,
                    "Init Project",
                    "Overwrite existing launcher?\n{}".format(output_launcher_path),
                )
                if answer != _message_box_button(QtWidgets, "Yes"):
                    return

            try:
                if run_init and not self._run_uv(
                    uv_init_args(self.install_project_check.isChecked()), root_path
                ):
                    self._refresh()
                    return
                if run_sync and not self._run_uv(["sync"], root_path):
                    self._refresh()
                    return
                if write_launcher:
                    written_launcher_path = generate_launcher(root_path)
                    self._append_output("Wrote launcher: {}\n".format(written_launcher_path))
            except Exception as exc:
                self._append_output(str(exc))
                QtWidgets.QMessageBox.critical(self, "Init Project", str(exc))
                self._refresh()
                return

            self._refresh()
            QtWidgets.QMessageBox.information(
                self,
                "Init Project",
                "Selected actions completed.",
            )

    _exec_dialog(Dialog(_dialog_parent()))


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


def _local_package_state_path(project_root):
    return (
        Path(project_root)
        / HVENVLOADER_MANAGED_DIR_NAME
        / LOCAL_PACKAGE_STATE_NAME
    )


def _read_local_package_state(project_root):
    state_path = _local_package_state_path(project_root)
    if not state_path.is_file():
        return {"version": 1, "packages": {}}

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Could not read local package state: {}".format(exc))

    if not isinstance(state, dict) or not isinstance(state.get("packages"), dict):
        raise ValueError("Invalid local package state: {}".format(state_path))
    return state


def _write_local_package_state(project_root, state):
    state_path = _local_package_state_path(project_root)
    packages = state.get("packages", {})
    if not packages:
        if state_path.is_file():
            state_path.unlink()
        try:
            state_path.parent.rmdir()
        except OSError:
            pass
        return

    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_name(
        ".{}.{}.tmp".format(state_path.name, uuid.uuid4().hex)
    )
    temporary_path.write_text(
        json.dumps(state, indent=4, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary_path), str(state_path))


def _validate_local_package_name(package_name):
    package_name = str(package_name).strip()
    if not package_name:
        raise ValueError("Package name is required.")
    if package_name in (".", "..") or Path(package_name).name != package_name:
        raise ValueError("Package name must be a single directory name.")
    if any(character in package_name for character in '<>:"/\\|?*'):
        raise ValueError("Package name contains characters that are not valid on Windows.")
    return package_name


def _local_package_paths(project_root, package_name):
    project_root = Path(project_root)
    package_name = _validate_local_package_name(package_name)
    packages_dir = project_root / "packages"
    return {
        "packages_dir": packages_dir,
        "package_dir": packages_dir / package_name,
        "package_json": packages_dir / "{}.json".format(package_name),
    }


def _is_directory_link(path):
    path = Path(path)
    if path.is_symlink():
        return True
    try:
        attributes = os.lstat(str(path)).st_file_attributes
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_point)
    except (AttributeError, OSError):
        return False


def _remove_directory_link(path):
    path = Path(path)
    if path.is_dir() and not path.is_symlink():
        path.rmdir()
    else:
        path.unlink()


def _remove_local_package_path(path):
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return
    if _is_directory_link(path):
        _remove_directory_link(path)
    elif path.is_dir():
        shutil.rmtree(str(path))
    else:
        path.unlink()


def _create_directory_junction(source_dir, destination_dir):
    source_dir = Path(source_dir).resolve()
    destination_dir = Path(destination_dir)
    destination_dir.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(destination_dir), str(source_dir)],
            capture_output=True,
            check=False,
        )
        result = _decode_completed_process_output(result)
        if result.returncode != 0:
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            raise RuntimeError(output or "Could not create directory junction.")
    else:
        destination_dir.symlink_to(source_dir, target_is_directory=True)


def _validate_houdini_package_json(package_json):
    package_json = Path(package_json)
    if not package_json.is_file():
        raise ValueError("Package JSON does not exist: {}".format(package_json))
    try:
        value = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Invalid package JSON {}: {}".format(package_json, exc))
    if not isinstance(value, dict):
        raise ValueError("Package JSON must contain a JSON object: {}".format(package_json))
    return value


def detect_houdini_package_jsons(source_dir):
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        return []

    candidates = list(source_dir.glob("*.json"))
    priorities = {
        "{}.json".format(source_dir.name).lower(): 0,
        "hpackage.json": 1,
    }

    def sort_key(path):
        return (priorities.get(path.name.lower(), 2), path.name.lower())

    valid_candidates = []
    for candidate in sorted(candidates, key=sort_key):
        try:
            _validate_houdini_package_json(candidate)
        except ValueError:
            continue
        valid_candidates.append(candidate)
    return valid_candidates


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_package_status(project_root, package_name, source_dir=None, package_json=None):
    paths = _local_package_paths(project_root, package_name)
    package_dir = paths["package_dir"]
    installed_json = paths["package_json"]
    state = _read_local_package_state(project_root)
    record = state["packages"].get(package_name)

    if not package_dir.exists() and not package_dir.is_symlink():
        directory_state = "missing"
        link_target = None
    elif _is_directory_link(package_dir):
        directory_state = "junction" if os.name == "nt" else "symlink"
        try:
            link_target = package_dir.resolve()
        except OSError:
            link_target = None
    elif package_dir.is_dir():
        directory_state = "directory"
        link_target = None
    else:
        directory_state = "file"
        link_target = None

    json_matches_source = None
    if package_json and Path(package_json).is_file() and installed_json.is_file():
        json_matches_source = _file_sha256(package_json) == _file_sha256(installed_json)

    source_matches_link = None
    if source_dir and link_target is not None:
        try:
            source_matches_link = link_target == Path(source_dir).resolve()
        except OSError:
            source_matches_link = False

    return {
        **paths,
        "managed": record is not None,
        "record": record,
        "directory_state": directory_state,
        "link_target": link_target,
        "source_matches_link": source_matches_link,
        "json_exists": installed_json.is_file(),
        "json_matches_source": json_matches_source,
    }


def _copy_local_package_tree(source_dir, destination_dir):
    shutil.copytree(
        str(source_dir),
        str(destination_dir),
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            "__pycache__",
            "*.pyc",
            "*.pyo",
        ),
    )


def _replace_local_package_directory(source_dir, destination_dir, directory_mode):
    destination_dir = Path(destination_dir)
    staging_path = destination_dir.with_name(
        ".{}.{}.installing".format(destination_dir.name, uuid.uuid4().hex)
    )
    backup_path = destination_dir.with_name(
        ".{}.{}.backup".format(destination_dir.name, uuid.uuid4().hex)
    )

    try:
        if directory_mode == "junction":
            _create_directory_junction(source_dir, staging_path)
        else:
            _copy_local_package_tree(source_dir, staging_path)

        destination_exists = destination_dir.exists() or destination_dir.is_symlink()
        if destination_exists:
            destination_dir.rename(backup_path)
        try:
            staging_path.rename(destination_dir)
        except Exception:
            if destination_exists and backup_path.exists():
                backup_path.rename(destination_dir)
            raise
        if destination_exists:
            _remove_local_package_path(backup_path)
    finally:
        if staging_path.exists() or staging_path.is_symlink():
            _remove_local_package_path(staging_path)


def install_local_houdini_package(
    project_root,
    source_dir,
    package_json,
    package_name=None,
    directory_mode="junction",
    replace=False,
):
    project_root = Path(project_root)
    source_dir = Path(source_dir)
    package_json = Path(package_json)
    if not project_root.is_dir():
        raise ValueError("Project root does not exist: {}".format(project_root))
    if not source_dir.is_dir():
        raise ValueError("Package source directory does not exist: {}".format(source_dir))
    _validate_houdini_package_json(package_json)

    if directory_mode not in LOCAL_PACKAGE_DIRECTORY_MODES:
        raise ValueError("Unknown package directory mode: {}".format(directory_mode))
    if package_name is None:
        package_name = package_json.stem if package_json.name != "hpackage.json" else source_dir.name
    package_name = _validate_local_package_name(package_name)
    paths = _local_package_paths(project_root, package_name)
    packages_dir = paths["packages_dir"]
    destination_dir = paths["package_dir"]
    destination_json = paths["package_json"]

    if directory_mode in ("junction", "copy"):
        if _absolute_path_without_links(source_dir) == _absolute_path_without_links(
            destination_dir
        ):
            raise ValueError(
                "The package source is already in the project packages directory; use None mode."
            )
        if _is_relative_to_without_links(destination_dir, source_dir):
            raise ValueError("Package destination must not be inside the source directory.")
        if _is_relative_to_without_links(package_json, destination_dir):
            raise ValueError(
                "Package JSON cannot be read from a destination directory that will be replaced."
            )

    packages_dir.mkdir(parents=True, exist_ok=True)
    destination_exists = destination_dir.exists() or destination_dir.is_symlink()
    json_exists = destination_json.exists()

    same_junction = False
    if directory_mode == "junction" and destination_exists and _is_directory_link(destination_dir):
        try:
            same_junction = destination_dir.resolve() == source_dir.resolve()
        except OSError:
            same_junction = False

    if directory_mode == "none":
        if not destination_dir.is_dir():
            raise ValueError(
                "None mode requires an existing package directory: {}".format(destination_dir)
            )
    elif destination_exists and not same_junction and not replace:
        raise FileExistsError(
            "Package destination already exists; enable Replace to update it: {}".format(
                destination_dir
            )
        )

    json_is_same = json_exists and destination_json.is_file() and (
        _file_sha256(package_json) == _file_sha256(destination_json)
    )
    if json_exists and not json_is_same and not replace:
        raise FileExistsError(
            "Package JSON already exists; enable Replace to update it: {}".format(
                destination_json
            )
        )

    if directory_mode in ("junction", "copy") and not same_junction:
        _replace_local_package_directory(source_dir, destination_dir, directory_mode)

    if not json_is_same:
        temporary_json = destination_json.with_name(
            ".{}.{}.installing".format(destination_json.name, uuid.uuid4().hex)
        )
        try:
            shutil.copy2(str(package_json), str(temporary_json))
            os.replace(str(temporary_json), str(destination_json))
        finally:
            if temporary_json.exists():
                temporary_json.unlink()

    state = _read_local_package_state(project_root)
    state["packages"][package_name] = {
        "directory_mode": directory_mode,
        "source_dir": str(source_dir.resolve()),
        "source_json": str(package_json.resolve()),
        "json_sha256": _file_sha256(destination_json),
    }
    _write_local_package_state(project_root, state)

    return {
        **paths,
        "package_name": package_name,
        "directory_mode": directory_mode,
    }


def remove_local_houdini_package(project_root, package_name, force=False):
    package_name = _validate_local_package_name(package_name)
    paths = _local_package_paths(project_root, package_name)
    state = _read_local_package_state(project_root)
    record = state["packages"].get(package_name)
    if record is None:
        raise ValueError(
            "Package is not recorded as managed by hvenvloader: {}".format(package_name)
        )

    package_dir = paths["package_dir"]
    package_json = paths["package_json"]
    mode = record.get("directory_mode")
    if package_json.is_file() and not force:
        installed_hash = _file_sha256(package_json)
        if installed_hash != record.get("json_sha256"):
            raise RuntimeError(
                "Installed package JSON was modified after installation; use force to remove it."
            )

    if mode == "junction" and (package_dir.exists() or package_dir.is_symlink()):
        if not _is_directory_link(package_dir):
            raise RuntimeError(
                "Refusing to remove a junction that has been replaced by a real directory: {}".format(
                    package_dir
                )
            )
        try:
            expected_source = Path(record["source_dir"]).resolve()
            if package_dir.resolve() != expected_source:
                raise RuntimeError(
                    "Refusing to remove a junction whose target has changed: {}".format(
                        package_dir
                    )
                )
        except KeyError:
            raise RuntimeError("Managed junction record has no source directory.")
        _remove_directory_link(package_dir)
    elif mode == "copy" and (package_dir.exists() or package_dir.is_symlink()):
        if _is_directory_link(package_dir) or not package_dir.is_dir():
            raise RuntimeError(
                "Refusing to remove a copied package that is no longer a real directory: {}".format(
                    package_dir
                )
            )
        shutil.rmtree(str(package_dir))
    elif mode not in LOCAL_PACKAGE_DIRECTORY_MODES:
        raise RuntimeError("Unknown managed package directory mode: {}".format(mode))

    if package_json.exists():
        package_json.unlink()
    del state["packages"][package_name]
    _write_local_package_state(project_root, state)
    return paths


def manage_local_packages_tool():
    QtCore, QtWidgets = _qt_modules()

    class Dialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super(Dialog, self).__init__(parent)
            self.setWindowTitle("Manage Regular Packages")
            self.setMinimumSize(760, 560)

            layout = QtWidgets.QVBoxLayout(self)
            form = QtWidgets.QFormLayout()
            layout.addLayout(form)

            self.root_edit = QtWidgets.QLineEdit(str(_default_project_root()))
            root_browse = QtWidgets.QPushButton("...")
            root_browse.clicked.connect(self._browse_root)
            root_layout = QtWidgets.QHBoxLayout()
            root_layout.addWidget(self.root_edit)
            root_layout.addWidget(root_browse)
            form.addRow("Project Root", root_layout)

            self.managed_combo = QtWidgets.QComboBox()
            form.addRow("Managed Package", self.managed_combo)

            self.source_edit = QtWidgets.QLineEdit()
            source_browse = QtWidgets.QPushButton("...")
            source_browse.clicked.connect(self._browse_source)
            source_layout = QtWidgets.QHBoxLayout()
            source_layout.addWidget(self.source_edit)
            source_layout.addWidget(source_browse)
            form.addRow("Package Directory", source_layout)

            self.json_edit = QtWidgets.QLineEdit()
            json_browse = QtWidgets.QPushButton("...")
            json_browse.clicked.connect(self._browse_json)
            json_layout = QtWidgets.QHBoxLayout()
            json_layout.addWidget(self.json_edit)
            json_layout.addWidget(json_browse)
            form.addRow("Package JSON", json_layout)

            self.name_edit = QtWidgets.QLineEdit()
            form.addRow("Package Name", self.name_edit)

            self.mode_combo = QtWidgets.QComboBox()
            self.mode_combo.addItem("Junction (development)", "junction")
            self.mode_combo.addItem("Copy", "copy")
            self.mode_combo.addItem("None (use existing directory)", "none")
            form.addRow("Directory Mode", self.mode_combo)

            self.replace_check = QtWidgets.QCheckBox(
                "Replace an existing package directory or JSON when installing"
            )
            layout.addWidget(self.replace_check)

            self.status_text = QtWidgets.QPlainTextEdit()
            self.status_text.setReadOnly(True)
            layout.addWidget(self.status_text, 1)

            actions = QtWidgets.QDialogButtonBox()
            self.install_button = actions.addButton(
                "Install / Update", _dialog_button_role(QtWidgets, "ActionRole")
            )
            self.remove_button = actions.addButton(
                "Remove Managed", _dialog_button_role(QtWidgets, "DestructiveRole")
            )
            refresh_button = actions.addButton(
                "Refresh", _dialog_button_role(QtWidgets, "ActionRole")
            )
            close_button = actions.addButton(_dialog_button(QtWidgets, "Close"))
            self.install_button.clicked.connect(self._install)
            self.remove_button.clicked.connect(self._remove)
            refresh_button.clicked.connect(self._refresh)
            close_button.clicked.connect(self.reject)
            layout.addWidget(actions)

            self.root_edit.textChanged.connect(self._refresh)
            self.root_edit.editingFinished.connect(self._reload_managed_packages)
            self.managed_combo.currentIndexChanged.connect(self._managed_package_selected)
            self.source_edit.textChanged.connect(self._source_changed)
            self.json_edit.textChanged.connect(self._json_changed)
            self.name_edit.textChanged.connect(self._refresh)
            self.mode_combo.currentIndexChanged.connect(self._refresh)
            self._reload_managed_packages()
            self._refresh()

        def _browse_root(self):
            selected = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Select Project Root", self.root_edit.text()
            )
            if selected:
                self.root_edit.setText(selected)
                self._reload_managed_packages()

        def _reload_managed_packages(self):
            current_name = self.name_edit.text().strip()
            self.managed_combo.blockSignals(True)
            self.managed_combo.clear()
            self.managed_combo.addItem("Select a managed package...", None)
            try:
                package_names = sorted(
                    _read_local_package_state(self.root_edit.text())["packages"]
                )
            except Exception:
                package_names = []
            selected_index = 0
            for package_name in package_names:
                self.managed_combo.addItem(package_name, package_name)
                if package_name == current_name:
                    selected_index = self.managed_combo.count() - 1
            self.managed_combo.setCurrentIndex(selected_index)
            self.managed_combo.blockSignals(False)

        def _managed_package_selected(self):
            package_name = self.managed_combo.currentData()
            if not package_name:
                return
            try:
                record = _read_local_package_state(
                    self.root_edit.text()
                )["packages"][package_name]
            except (KeyError, ValueError):
                return
            self.name_edit.setText(package_name)
            self.source_edit.setText(record.get("source_dir", ""))
            self.json_edit.setText(record.get("source_json", ""))
            mode_index = self.mode_combo.findData(record.get("directory_mode"))
            if mode_index >= 0:
                self.mode_combo.setCurrentIndex(mode_index)
            self._refresh()

        def _browse_source(self):
            selected = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Select Houdini Package Directory", self.source_edit.text()
            )
            if selected:
                self.source_edit.setText(selected)

        def _browse_json(self):
            selected, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Select Houdini Package JSON",
                self.json_edit.text() or self.source_edit.text(),
                "JSON Files (*.json);;All Files (*)",
            )
            if selected:
                self.json_edit.setText(selected)

        def _source_changed(self):
            candidates = detect_houdini_package_jsons(self.source_edit.text())
            if candidates:
                self.json_edit.setText(str(candidates[0]))
            elif not self.source_edit.text():
                self.json_edit.clear()
            if self.source_edit.text() and not self.name_edit.text():
                self.name_edit.setText(Path(self.source_edit.text()).name)
            self._refresh()

        def _json_changed(self):
            json_path = Path(self.json_edit.text())
            if json_path.name and json_path.name != "hpackage.json":
                self.name_edit.setText(json_path.stem)
            self._refresh()

        def _refresh(self):
            package_name = self.name_edit.text().strip()
            if not package_name:
                self.status_text.setPlainText(
                    "Select a package directory. Valid package JSON files in its root are detected automatically."
                )
                self.remove_button.setEnabled(False)
                return
            try:
                status = local_package_status(
                    self.root_edit.text(),
                    package_name,
                    self.source_edit.text() or None,
                    self.json_edit.text() or None,
                )
            except Exception as exc:
                self.status_text.setPlainText(str(exc))
                self.remove_button.setEnabled(False)
                return

            lines = [
                "Package directory: {}".format(status["package_dir"]),
                "Directory status: {}".format(status["directory_state"]),
                "Package JSON: {}".format(status["package_json"]),
                "JSON status: {}".format("present" if status["json_exists"] else "missing"),
                "Managed by hvenvloader: {}".format("yes" if status["managed"] else "no"),
            ]
            if status["link_target"] is not None:
                lines.append("Link target: {}".format(status["link_target"]))
            if status["json_matches_source"] is not None:
                lines.append(
                    "JSON matches source: {}".format(
                        "yes" if status["json_matches_source"] else "no"
                    )
                )
            if self.mode_combo.currentData() == "none" and status["directory_state"] == "missing":
                lines.append("WARNING: None mode requires the package directory to exist.")
            self.status_text.setPlainText("\n".join(lines))
            self.remove_button.setEnabled(status["managed"])

        def _install(self):
            try:
                result = install_local_houdini_package(
                    self.root_edit.text(),
                    self.source_edit.text(),
                    self.json_edit.text(),
                    package_name=self.name_edit.text(),
                    directory_mode=self.mode_combo.currentData(),
                    replace=self.replace_check.isChecked(),
                )
            except Exception as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Manage Regular Packages", str(exc)
                )
                return
            QtWidgets.QMessageBox.information(
                self,
                "Manage Regular Packages",
                "Installed {}.\n\nRestart Houdini to load the package.".format(
                    result["package_name"]
                ),
            )
            self._reload_managed_packages()
            self._refresh()

        def _remove(self):
            package_name = self.name_edit.text().strip()
            status = local_package_status(self.root_edit.text(), package_name)
            mode = (status.get("record") or {}).get("directory_mode", "unknown")
            message = "Remove the managed JSON"
            if mode == "junction":
                message += " and junction"
            elif mode == "copy":
                message += " and copied package directory"
            message += " for {}?".format(package_name)
            yes = _message_box_button(QtWidgets, "Yes")
            no = _message_box_button(QtWidgets, "No")
            answer = QtWidgets.QMessageBox.question(
                self,
                "Manage Regular Packages",
                message,
                yes | no,
                no,
            )
            if answer != yes:
                return
            try:
                remove_local_houdini_package(
                    self.root_edit.text(), package_name, force=False
                )
            except RuntimeError as exc:
                force_answer = QtWidgets.QMessageBox.question(
                    self,
                    "Manage Regular Packages",
                    "{}\n\nForce removal?".format(exc),
                    yes | no,
                    no,
                )
                if force_answer != yes:
                    return
                try:
                    remove_local_houdini_package(
                        self.root_edit.text(), package_name, force=True
                    )
                except Exception as force_exc:
                    QtWidgets.QMessageBox.critical(
                        self, "Manage Regular Packages", str(force_exc)
                    )
                    return
            except Exception as exc:
                QtWidgets.QMessageBox.critical(
                    self, "Manage Regular Packages", str(exc)
                )
                return
            QtWidgets.QMessageBox.information(
                self,
                "Manage Regular Packages",
                "Removed {}.\n\nRestart Houdini to unload the package completely.".format(
                    package_name
                ),
            )
            self._reload_managed_packages()
            self._refresh()

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
            self.install_project_check = QtWidgets.QCheckBox(
                "Install this project into the venv (--package)"
            )
            self.install_project_check.setChecked(True)
            self.install_project_check.setToolTip(
                "Create an installable src-layout setuptools package. "
                "uv sync will install this project into .venv."
            )
            project_layout.addWidget(self.install_project_check, 0, 0, 1, 2)
            project_actions = [
                ("Create project (uv init)", self._init),
                ("Sync venv (uv sync)", lambda: self._run(["sync"])),
                ("Update lockfile (uv lock)", lambda: self._run(["lock"])),
                ("Show dependency tree (uv tree)", lambda: self._run(["tree"])),
                ("Write Houdini launcher", self._write_launcher),
            ]
            for index, (label, callback) in enumerate(project_actions):
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(callback)
                project_layout.addWidget(button, index // 2 + 1, index % 2)
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
            self._run(uv_init_args(self.install_project_check.isChecked()))

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
