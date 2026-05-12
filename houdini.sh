#!/bin/bash
HOUDINI_EXE="@HOUDINI_EXE@"
HOUDINI_USER_PREF_DIR="@HOUDINI_USER_PREF_DIR@"
export HOUDINI_USER_PREF_DIR
export HVENVLOADER_LAUNCHER=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -d "$SCRIPT_DIR/.venv/Lib/site-packages" ]; then
    HOUDINI_PACKAGE_DIR="$SCRIPT_DIR/.venv/Lib/site-packages"
else
    HOUDINI_PACKAGE_DIR="$(find "$SCRIPT_DIR/.venv/lib" -maxdepth 2 -type d -name site-packages 2>/dev/null | head -n 1)"
fi

export HOUDINI_PACKAGE_DIR

if [ -n "$HOUDINI_PACKAGE_DIR" ] && [ -d "$HOUDINI_PACKAGE_DIR" ]; then
    # Copy hpackage.json from Houdini Python packages.
    for dir in "$HOUDINI_PACKAGE_DIR"/*/; do
        last_dir_name=$(basename "$dir")
        json_file="${dir}hpackage.json"
        if [ -f "$json_file" ]; then
            cp "$json_file" "$HOUDINI_PACKAGE_DIR/$last_dir_name.json"
        fi
    done

    if [ -n "$PYTHONPATH" ]; then
        export PYTHONPATH="$HOUDINI_PACKAGE_DIR:$PYTHONPATH"
    else
        export PYTHONPATH="$HOUDINI_PACKAGE_DIR"
    fi
fi

"$HOUDINI_EXE"
