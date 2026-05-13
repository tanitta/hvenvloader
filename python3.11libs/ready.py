import sys
from pathlib import Path

import hou


def _package_root():
    filename = globals().get("__file__")
    if not filename:
        filename = sys._getframe().f_code.co_filename

    path = Path(filename)
    if path.name == "ready.py":
        candidate = path.resolve().parents[1]
        if (candidate / "scripts" / "python").is_dir():
            return candidate

    hvenvloader_path = hou.getenv("HVENVLOADER")
    if hvenvloader_path:
        return Path(hou.text.expandString(hvenvloader_path))

    raise RuntimeError("Could not resolve hvenvloader package root.")


def _add_package_python_path():
    package_root = _package_root()
    scripts_python_path = package_root / "scripts" / "python"
    if not scripts_python_path.is_dir():
        return

    path_text = str(scripts_python_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def _install():
    _add_package_python_path()
    from hvenvloader import startup

    startup.install()


_install()
