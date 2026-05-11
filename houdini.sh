#!/bin/bash
HOUDINI_USER_PREF_DIR="$HOME\Documents\houdini20.5"
export HOUDINI_USER_PREF_DIR

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export HOUDINI_PACKAGE_DIR="$SCRIPT_DIR"/.venv/Lib/site-packages;

# Copy hpackage.json from Houdini Python packages.
for dir in "$HOUDINI_PACKAGE_DIR"/*/; do
    last_dir_name=$(basename "$dir")
    json_file="${dir}hpackage.json"
    if [ -f "$json_file" ]; then
        cp "$json_file" "$HOUDINI_PACKAGE_DIR/$last_dir_name.json"
    fi
done

export PYTHONPATH=$HOUDINI_PACKAGE_DIR

houdini="C:\Program Files\Side Effects Software\Houdini 20.5.370\bin\houdini.exe"
"$houdini"
