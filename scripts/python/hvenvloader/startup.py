import os
import sys
from pathlib import Path

import hou


MESSAGE_HEADER = "hvenvloader"
SESSION_SITE_PACKAGES_ATTR = "hvenvloader_venv_site_packages_path"


def _is_launcher_mode():
    return os.environ.get("HVENVLOADER_LAUNCHER") == "1"


def _normalize_path(path):
    return os.path.normcase(os.path.abspath(path))


def _same_path(left, right):
    try:
        return _normalize_path(left) == _normalize_path(right)
    except (TypeError, ValueError):
        return left == right


def _remove_modules_in_directory(directory):
    directory = _normalize_path(directory)
    prefix = directory + os.sep
    modules_to_remove = []

    for name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue

        try:
            module_file = _normalize_path(module_file)
        except (TypeError, ValueError):
            continue

        if module_file == directory or module_file.startswith(prefix):
            modules_to_remove.append(name)

    for name in modules_to_remove:
        del sys.modules[name]


def _venv_root():
    job = hou.getenv("JOB")
    if not job:
        return None

    expanded_job = hou.text.expandString("$JOB")
    if not expanded_job:
        return None

    return Path(expanded_job) / ".venv"


def _site_packages_candidates(venv_root):
    version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)
    return [
        venv_root / "Lib" / "site-packages",
        venv_root / "lib" / "python{}".format(version) / "site-packages",
        venv_root / "lib" / "site-packages",
    ]


def _find_site_packages_path():
    venv_root = _venv_root()
    if not venv_root:
        return ""

    for path in _site_packages_candidates(venv_root):
        if path.is_dir():
            return str(path)

    return ""


def _session_site_packages_path():
    if not hasattr(hou.session, SESSION_SITE_PACKAGES_ATTR):
        setattr(hou.session, SESSION_SITE_PACKAGES_ATTR, "")
    return getattr(hou.session, SESSION_SITE_PACKAGES_ATTR)


def unload_python_packages():
    site_packages_path = _session_site_packages_path()
    if not site_packages_path:
        return

    sys.path = [
        path
        for path in sys.path
        if not _same_path(path, site_packages_path)
    ]
    _remove_modules_in_directory(site_packages_path)
    setattr(hou.session, SESSION_SITE_PACKAGES_ATTR, "")


def load_python_packages():
    site_packages_path = _find_site_packages_path()
    previous_site_packages_path = _session_site_packages_path()

    if previous_site_packages_path and not _same_path(
        previous_site_packages_path,
        site_packages_path,
    ):
        unload_python_packages()

    if not site_packages_path:
        setattr(hou.session, SESSION_SITE_PACKAGES_ATTR, "")
        return False

    if not any(_same_path(path, site_packages_path) for path in sys.path):
        sys.path.append(site_packages_path)

    setattr(hou.session, SESSION_SITE_PACKAGES_ATTR, site_packages_path)
    return True


def _event_types(*names):
    event_types = []
    for name in names:
        event_type = getattr(hou.hipFileEventType, name, None)
        if event_type is not None:
            event_types.append(event_type)
    return tuple(event_types)


def hvenvloader_scene_event_callback(event_type):
    if event_type in _event_types("BeforeSave", "BeforeClear", "BeforeLoad"):
        unload_python_packages()

    if event_type in _event_types("AfterSave", "AfterClear", "AfterLoad"):
        load_python_packages()


def _is_callback_registered():
    callback_name = hvenvloader_scene_event_callback.__name__
    return callback_name in [
        getattr(callback, "__name__", "")
        for callback in hou.hipFile.eventCallbacks()
    ]


def install():
    if _is_launcher_mode():
        print("[{}] Launcher mode detected. ready.py fallback skipped.".format(MESSAGE_HEADER))
        return

    if not _is_callback_registered():
        hou.hipFile.addEventCallback(hvenvloader_scene_event_callback)
    load_python_packages()
