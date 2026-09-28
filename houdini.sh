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

HVENVLOADER_PROJECT_PACKAGE_DIR="$SCRIPT_DIR/packages"
HVENVLOADER_EDITABLE_PACKAGE_DIR="$SCRIPT_DIR/.hvenvloader/editable_packages"

if [ -n "$PYTHON_SITE_PACKAGES" ] && [ -d "$PYTHON_SITE_PACKAGES" ]; then
    HVENVLOADER_PYTHON_PATHS="$PYTHON_SITE_PACKAGES/_hvenvloader_python_paths.txt"
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

    HVENVLOADER_PYTHONPATH="$PYTHON_SITE_PACKAGES"
    if [ -f "$HVENVLOADER_PYTHON_PATHS" ]; then
        while IFS= read -r python_path || [ -n "$python_path" ]; do
            if [ -n "$python_path" ]; then
                HVENVLOADER_PYTHONPATH="$HVENVLOADER_PYTHONPATH:$python_path"
            fi
        done < "$HVENVLOADER_PYTHON_PATHS"
    fi

    if [ -n "$PYTHONPATH" ]; then
        export PYTHONPATH="$HVENVLOADER_PYTHONPATH:$PYTHONPATH"
    else
        export PYTHONPATH="$HVENVLOADER_PYTHONPATH"
    fi
fi

HOUDINI_PACKAGE_DIR="$PYTHON_SITE_PACKAGES"
if [ -d "$HVENVLOADER_PROJECT_PACKAGE_DIR" ]; then
    if [ -n "$HOUDINI_PACKAGE_DIR" ]; then
        HOUDINI_PACKAGE_DIR="$HVENVLOADER_PROJECT_PACKAGE_DIR:$HOUDINI_PACKAGE_DIR"
    else
        HOUDINI_PACKAGE_DIR="$HVENVLOADER_PROJECT_PACKAGE_DIR"
    fi
fi
if [ -d "$HVENVLOADER_EDITABLE_PACKAGE_DIR" ]; then
    if [ -n "$HOUDINI_PACKAGE_DIR" ]; then
        HOUDINI_PACKAGE_DIR="$HOUDINI_PACKAGE_DIR:$HVENVLOADER_EDITABLE_PACKAGE_DIR"
    else
        HOUDINI_PACKAGE_DIR="$HVENVLOADER_EDITABLE_PACKAGE_DIR"
    fi
fi
export HOUDINI_PACKAGE_DIR

"$HOUDINI_EXE" "$@"
