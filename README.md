# Houdini venv Loader (hvenvloader)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/tanitta/hvenvloader/blob/main/LICENSE)

## Description

This is a Houdini package for use within a Python project workflow, providing the following functionality:

- Loading Python packages from the project-local Python virtual environment `.venv` into Houdini.
- Loading [Houdini Package](https://www.sidefx.com/docs/houdini/ref/plugins.html) files included in Python packages installed under `.venv`.
- Creating a project launcher (`houdini.bat` or `houdini.sh`) that starts Houdini with the project's `.venv`.

## Installation

1. Install [uv](https://docs.astral.sh/uv/) and make sure Houdini can run the `uv` command.
2. Clone this repository into `$HOUDINI_USER_PREF_DIR/packages/hvenvloader`.
3. Copy `hvenvloader.json` to `$HOUDINI_USER_PREF_DIR/packages/hvenvloader.json`.
4. Restart Houdini.

The `hvenvloader.json` file registers this package with Houdini. See also [Houdini packages | Houdini help](https://www.sidefx.com/docs/houdini/ref/plugins.html).

## Project Setup

1. Create or open a Houdini project and set `$JOB` to the project root directory.
2. Run the `venv > Init Project` shelf tool.
3. The shelf tool runs `uv init` and `uv sync` in `$JOB`, creates `.venv`, and writes a launcher into the project root:
   - `houdini.bat` on Windows
   - `houdini.sh` on other platforms
4. Close Houdini.
5. Start Houdini from the launcher in the project root instead of using the normal Houdini shortcut.

The generated launcher is part of the project. Keep it next to the project's `.venv` and use it whenever you work on that project.

## Launcher Behavior

`houdini.bat` and `houdini.sh` are launchers for a project root. They expect this layout:

```text
project-root/
  .venv/
  houdini.bat or houdini.sh
  your_project.hip
```

When the launcher starts Houdini, it:

1. Finds the project's `.venv` relative to the launcher file.
2. Sets `HOUDINI_PACKAGE_DIR` and `PYTHONPATH` to the `.venv` `site-packages` directory.
3. Copies Houdini package `.json` files from installed Python packages into `site-packages` so Houdini can discover them.
4. Starts Houdini with the project virtual environment available.

If you do not use the shelf tool, copy the appropriate launcher (`houdini.bat` or `houdini.sh`) into your project root manually and edit the Houdini executable path and `HOUDINI_USER_PREF_DIR` values for your environment.

## Usage

1. Install Python packages into the project `.venv`.
2. Start Houdini with the project root launcher.
3. Open the project's `.hip` file.

When Houdini starts through the launcher, packages installed in `.venv` are available in Houdini's Python environment, and Houdini package files provided by those packages can be loaded.

## Note

When using Houdini packages loaded from `.venv` within a hip file, you may see the following warning about HDAs when opening the file.

![image](https://github.com/tanitta/hvenvloader/assets/1937287/32d428d3-7dfe-4fbf-bf19-34fc7a68961a)

This occurs because the dependency check for the HDA is performed before the necessary Houdini Package HDAs are dynamically loaded by hvenvloader. Therefore, you can ignore the warning as the file will function correctly. Consider setting the environment variable [HOUDINI_DISABLE_FILE_LOAD_WARNINGS](https://www.sidefx.com/docs/houdini/ref/env) to suppress the warning dialog.
