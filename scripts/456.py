import sys
import os
import hou

def load_venv_site_packages():
    print("[hrye] Loading venv site_packages...")
    venvroot = hou.text.expandString("$JOB" + '/.venv')
    site_packages_path = hou.text.expandString(venvroot + '/Lib/site-packages')

    # Clean up path
    if not hasattr(hou.session, "venv_site_packages_path"):
        setattr(hou.session, "venv_site_packages_path", "")
    sys.path = list(filter(lambda path: path != site_packages_path, sys.path))

    # Set venv site-packages path
    hou.session.venv_site_packages_path = site_packages_path
    sys.path.append(site_packages_path)
    print(sys.path)
    print("[hrye] Finish site_packages loading successflly.")

load_venv_site_packages()

import glob
from pathlib import Path
def get_package_json(dir_path):
    dir_basename = os.path.basename(dir_path)
    return dir_path + '/' + dir_basename + '.json'

def is_houdini_package(dir_path):
    json_path = get_package_json(dir_path)
    return os.path.isfile(json_path)

def load_houdini_packages():
    print("[hrye] Loading venv houdini packages...")
    venvroot = hou.text.expandString("$JOB" + '/.venv')
    site_packages_path = hou.text.expandString(venvroot + '/Lib/site-packages')
    ds = filter(lambda d: os.path.isdir(d), glob.glob(site_packages_path + '/*'))
    package_dirs = filter(lambda d: is_houdini_package(d), ds)
    package_jsons = map(lambda d: get_package_json(d), package_dirs)
    for json in package_jsons:
        hou.ui.loadPackage(json)
    print(list(package_jsons))
    print("[hrye] Finish loading of houdini packages successflly.")

load_houdini_packages()
