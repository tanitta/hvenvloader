import sys
import os
import hou

message_header = 'hvenvloader'

def remove_modules_in_directory(directory):
    directory = os.path.abspath(directory)
    modules_to_remove = [(key, module) for key, module in sys.modules.items() 
                         if hasattr(module, '__file__') and module.__file__ and os.path.abspath(module.__file__).startswith(directory)]
    for key, module in modules_to_remove:
        del sys.modules[key]
        print(f"Removed {key}")

def unload_python_packages():
    if not hasattr(hou.session, "venv_site_packages_path"):
        setattr(hou.session, "venv_site_packages_path", "")
    sys.path = list(filter(lambda path: path != hou.session.venv_site_packages_path, sys.path))
    hou.session.venv_site_packages_path = ""

    venvroot = hou.text.expandString("$JOB" + '/.venv')
    site_packages_dir = hou.text.expandString(venvroot + '/Lib/site-packages')
    remove_modules_in_directory(site_packages_dir)

    print("[{message_header}] Unload Python Packages.".format(message_header=message_header))

def load_python_packages():
    print("[{message_header}] Loading venv site_packages...".format(message_header=message_header))
    venvroot = hou.text.expandString("$JOB" + '/.venv')
    hou.session.venv_site_packages_path = hou.text.expandString(venvroot + '/Lib/site-packages')
    if not os.path.isdir(hou.session.venv_site_packages_path):
        hou.session.venv_site_packages_path = ""
    sys.path.append(hou.session.venv_site_packages_path)
    print("[{message_header}] Finish site_packages loading successflly.".format(message_header=message_header))

import glob
from pathlib import Path

def get_package_json(dir_path):
    dir_basename = os.path.basename(dir_path)
    return dir_path + '/' + dir_basename + '.json'

def is_houdini_package(dir_path):
    json_path = get_package_json(dir_path)
    return os.path.isfile(json_path)

def unload_houdini_packages():
    if not hasattr(hou.session, "venv_houdini_package_json_paths"):
        setattr(hou.session, "venv_houdini_package_json_paths", {})
    for package_name in hou.session.venv_houdini_package_json_paths:
        package_path = hou.session.venv_houdini_package_json_paths[package_name]
        print("unload:{}".format(package_name))
        print(package_path)
        hou.ui.unloadPackage(package_path)
    hou.session.venv_houdini_package_json_paths = {}

    print("[{message_header}] Unload Houdini Packages.".format(message_header=message_header))
def load_houdini_packages():
    if not hasattr(hou.session, "venv_houdini_package_json_paths"):
        setattr(hou.session, "venv_houdini_package_json_paths", {})

    print("[{message_header}] Loading venv houdini packages...".format(message_header=message_header))
    venvroot = hou.text.expandString("$JOB" + '/.venv')
    site_packages_path = hou.text.expandString(venvroot + '/Lib/site-packages')
    ds = filter(lambda d: os.path.isdir(d), glob.glob(site_packages_path + '/*'))
    package_dirs = filter(lambda d: is_houdini_package(d), ds)
    package_paths = list(map(lambda d: get_package_json(d), package_dirs))

    for json_path in package_paths:
        json_original = ''
        json_modified = ''
        with open(json_path) as f:
            json_original = f.read()
        json_modified = json_original.replace('$HOUDINI_PACKAGE_PATH', site_packages_path)
        package_name = os.path.splitext(os.path.basename(json_path))[0] 
        json_path_temp = hou.text.expandString("$TEMP/{}.json".format(package_name))
        with open(json_path_temp, mode='w') as f:
            f.write(json_modified)
        hou.ui.loadPackage(json_path_temp)
        hou.session.venv_houdini_package_json_paths[package_name] = json_path_temp
        print("[{message_header}] Finish loading houdini package: {package_name}".format(message_header=message_header, package_name=package_name))
    print("[{message_header}] Finish loading all houdini packages successflly.".format(message_header=message_header))

def hvenvloader_scene_event_callback(event_type):
    if event_type == hou.hipFileEventType.BeforeSave or event_type == hou.hipFileEventType.BeforeClear:
        unload_houdini_packages()
        unload_python_packages()
    if event_type == hou.hipFileEventType.AfterSave:
        load_python_packages()
        load_houdini_packages()

if hvenvloader_scene_event_callback.__name__ not in map(lambda f: f.__name__, hou.hipFile.eventCallbacks()):
    hou.hipFile.addEventCallback(hvenvloader_scene_event_callback)

load_python_packages()
load_houdini_packages()



