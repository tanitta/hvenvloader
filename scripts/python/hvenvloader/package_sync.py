import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


EDITABLE_PACKAGE_DIR_NAME = "_hvenvloader_houdini_packages"
STALE_EDITABLE_BOOTSTRAP_JSON_NAME = "_hvenvloader_editable_packages.json"


def _read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _path_from_file_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None

    path = unquote(parsed.path)
    if path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path[1:]
    if parsed.netloc:
        path = "//{}/{}".format(parsed.netloc, path.lstrip("/"))
    return Path(path)


def _direct_url_data(dist_info_path):
    direct_url_path = dist_info_path / "direct_url.json"
    if not direct_url_path.is_file():
        return {}

    try:
        return json.loads(_read_text(direct_url_path))
    except ValueError:
        return {}


def _top_level_packages(dist_info_path):
    top_level_path = dist_info_path / "top_level.txt"
    if not top_level_path.is_file():
        return []

    packages = []
    for line in _read_text(top_level_path).splitlines():
        line = line.strip()
        if line:
            packages.append(line)
    return packages


def _editable_source_root(dist_info_path):
    data = _direct_url_data(dist_info_path)
    if not data.get("dir_info", {}).get("editable"):
        return None

    url = data.get("url")
    if not url:
        return None

    return _path_from_file_url(url)


def _editable_package_dirs(dist_info_path):
    source_root = _editable_source_root(dist_info_path)
    if not source_root:
        return []

    package_dirs = []
    top_level_packages = _top_level_packages(dist_info_path)
    for package_name in top_level_packages:
        package_dirs.append(source_root / "src" / package_name)
        package_dirs.append(source_root / package_name)

    if not top_level_packages:
        package_dirs.extend(path.parent for path in (source_root / "src").glob("*/hpackage.json"))
        package_dirs.extend(path.parent for path in source_root.glob("*/hpackage.json"))

    result = []
    seen = set()
    for path in package_dirs:
        if not (path / "hpackage.json").is_file():
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _sync_regular_package(site_packages_path, package_dir):
    if package_dir.name == EDITABLE_PACKAGE_DIR_NAME:
        return

    source_json_path = package_dir / "hpackage.json"
    if not source_json_path.is_file():
        return

    destination_json_path = site_packages_path / "{}.json".format(package_dir.name)
    shutil.copyfile(str(source_json_path), str(destination_json_path))


def _clear_editable_package_dir(editable_package_path):
    editable_package_path.mkdir(parents=True, exist_ok=True)
    for child in editable_package_path.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                child.rmdir()
            else:
                child.unlink()
        except OSError as exc:
            print(
                "hvenvloader: failed to remove generated editable package entry {}: {}".format(
                    child,
                    exc,
                ),
                file=sys.stderr,
            )


def _same_resolved_path(left, right):
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return False


def _create_windows_directory_link(source_path, link_path):
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link_path), str(source_path)],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode == 0:
        return

    try:
        os.symlink(str(source_path), str(link_path), target_is_directory=True)
    except OSError as symlink_exc:
        output = (result.stdout or "") + (result.stderr or "")
        detail = output.strip() or str(symlink_exc)
        raise OSError(detail)


def _create_directory_link(source_path, link_path):
    source_path = Path(source_path)
    link_path = Path(link_path)

    if link_path.exists() or link_path.is_symlink():
        if _same_resolved_path(link_path, source_path):
            return
        raise FileExistsError("{} already exists and points somewhere else.".format(link_path))

    link_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        _create_windows_directory_link(source_path, link_path)
    else:
        os.symlink(str(source_path), str(link_path), target_is_directory=True)


def _sync_editable_package(editable_package_path, package_dir):
    source_json_path = package_dir / "hpackage.json"
    if not source_json_path.is_file():
        return

    link_path = editable_package_path / package_dir.name
    _create_directory_link(package_dir, link_path)

    destination_json_path = editable_package_path / "{}.json".format(package_dir.name)
    shutil.copyfile(str(source_json_path), str(destination_json_path))


def _remove_stale_editable_bootstrap_json(site_packages_path):
    bootstrap_json_path = site_packages_path / STALE_EDITABLE_BOOTSTRAP_JSON_NAME
    if bootstrap_json_path.is_file():
        bootstrap_json_path.unlink()


def sync_houdini_package_jsons(site_packages_path, editable_package_path=None):
    site_packages_path = Path(site_packages_path)
    if not site_packages_path.is_dir():
        return

    for package_dir in site_packages_path.iterdir():
        if package_dir.is_dir():
            _sync_regular_package(site_packages_path, package_dir)

    if editable_package_path is None:
        return

    editable_package_path = Path(editable_package_path)
    editable_package_dirs = []
    seen = set()
    for dist_info_path in site_packages_path.glob("*.dist-info"):
        for package_dir in _editable_package_dirs(dist_info_path):
            key = str(package_dir.resolve())
            if key in seen:
                continue
            seen.add(key)
            editable_package_dirs.append(package_dir)

    if not editable_package_dirs:
        if editable_package_path.exists():
            _clear_editable_package_dir(editable_package_path)
            try:
                editable_package_path.rmdir()
            except OSError:
                pass
        _remove_stale_editable_bootstrap_json(site_packages_path)
        return

    _remove_stale_editable_bootstrap_json(site_packages_path)
    _clear_editable_package_dir(editable_package_path)

    synced_count = 0
    for package_dir in editable_package_dirs:
        try:
            _sync_editable_package(editable_package_path, package_dir)
            synced_count += 1
        except OSError as exc:
            print(
                "hvenvloader: failed to sync editable NVHP {}: {}".format(
                    package_dir,
                    exc,
                ),
                file=sys.stderr,
            )
    if not synced_count:
        try:
            editable_package_path.rmdir()
        except OSError:
            pass


def main(argv):
    if len(argv) not in (2, 3):
        return 2

    editable_package_path = None
    if len(argv) == 3:
        editable_package_path = argv[2]

    sync_houdini_package_jsons(argv[1], editable_package_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
