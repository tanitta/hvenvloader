#!/bin/bash
HOUDINI_EXE="@HOUDINI_EXE@"
HOUDINI_USER_PREF_DIR="@HOUDINI_USER_PREF_DIR@"
HVENVLOADER="@HVENVLOADER@"
export HOUDINI_USER_PREF_DIR
export HVENVLOADER_LAUNCHER=1
export HVENVLOADER

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -d "$SCRIPT_DIR/.venv/Lib/site-packages" ]; then
    PYTHON_SITE_PACKAGES="$SCRIPT_DIR/.venv/Lib/site-packages"
else
    PYTHON_SITE_PACKAGES="$(find "$SCRIPT_DIR/.venv/lib" -maxdepth 2 -type d -name site-packages 2>/dev/null | head -n 1)"
fi

HOUDINI_PACKAGE_DIR="$PYTHON_SITE_PACKAGES"
export HOUDINI_PACKAGE_DIR

if [ -n "$PYTHON_SITE_PACKAGES" ] && [ -d "$PYTHON_SITE_PACKAGES" ]; then
    HVENVLOADER_EDITABLE_PACKAGE_DIR="$PYTHON_SITE_PACKAGES/_hvenvloader_houdini_packages"
    PACKAGE_SYNC="$HVENVLOADER/scripts/python/hvenvloader/package_sync.py"
    VENV_PYTHON=""
    if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
        VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
    elif [ -x "$SCRIPT_DIR/.venv/Scripts/python.exe" ]; then
        VENV_PYTHON="$SCRIPT_DIR/.venv/Scripts/python.exe"
    fi

    if [ -n "$VENV_PYTHON" ] && [ -f "$PACKAGE_SYNC" ]; then
        "$VENV_PYTHON" "$PACKAGE_SYNC" "$PYTHON_SITE_PACKAGES" "$HVENVLOADER_EDITABLE_PACKAGE_DIR"
    else
        # Copy hpackage.json from Houdini Python packages.
        for dir in "$PYTHON_SITE_PACKAGES"/*/; do
            last_dir_name=$(basename "$dir")
            json_file="${dir}hpackage.json"
            if [ -f "$json_file" ]; then
                cp "$json_file" "$PYTHON_SITE_PACKAGES/$last_dir_name.json"
            fi
        done
    fi

    if [ -d "$HVENVLOADER_EDITABLE_PACKAGE_DIR" ]; then
        export HOUDINI_PACKAGE_DIR="$PYTHON_SITE_PACKAGES:$HVENVLOADER_EDITABLE_PACKAGE_DIR"
    fi

    if [ -n "$PYTHONPATH" ]; then
        export PYTHONPATH="$PYTHON_SITE_PACKAGES:$PYTHONPATH"
    else
        export PYTHONPATH="$PYTHON_SITE_PACKAGES"
    fi
fi

"$HOUDINI_EXE"
