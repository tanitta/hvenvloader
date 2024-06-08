import sys
import os
import hou

def load_venv_site_packages():
    print("hrye")
    venvroot = hou.text.expandString("$JOB" + '/.venv')
    site_packages_path = hou.text.expandString(venvroot + '/site-packages')

    # Clean up path
    if not hasattr(hou.session, "venv_site_packages_path"):
        setattr(hou.session, "venv_site_packages_path", "")
    sys.path = list(filter(lambda path: path != site_packages_path, sys.path))

    # Set venv site-packages path
    hou.session.venv_site_packages_path = site_packages_path
    sys.path.append(site_packages_path)
    print(sys.path)

load_venv_site_packages()
