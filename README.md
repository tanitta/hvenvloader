# Houdini venv Loader (hvenvloader)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/tanitta/hvenvloader/blob/main/LICENSE)

## Description

This is a Houdini package for use within a Python project workflow, providing the following functionalities:
- Loading Python packages from the Python virtual environment `.venv` into Houdini within the Project directory.
- Loading [Houdini Package](https://www.sidefx.com/docs/houdini/ref/plugins.html) included in the Python Package from `.venv` into Houdini.

## Installation

1. Install a Python package manager (e.g., rye, poetry).
2. Clone This Repository into your `$HOUDINI_PREF_DIR/packages`.
3. Copy and paste `hvenvloader.json` in it into `$HOUDINI_PREF_DIR/packages`.

cf. [Houdini packages | Houdini help](https://www.sidefx.com/docs/houdini/ref/plugins.html)

## Usage

1. Create a Python project using the Python package manager.
2. (Optional) Add packages and set the Python version to project congig.
3. In the newly created directory from step 1, create a `.hip` file and set the directory's root as `$JOB` in the `.hip` file.
4. Reopen the `.hip` file. (When the `.hip` file is loaded, Houdini reads the `site-packages` from `.venv` through hvenvloader's `456.py`).

## Note

When using Houdini packages loaded from .venv within a hip file, you may see the following warning about HDAs when opening the file.

![image](https://github.com/tanitta/hvenvloader/assets/1937287/32d428d3-7dfe-4fbf-bf19-34fc7a68961a)

This occurs because the dependency check for the HDA is performed before the necessary Houdini Package HDAs are dynamically loaded by hvenvloader. Therefore, you can ignore the warning as the file will function correctly. (Consider setting the environment variable [HOUDINI_DISABLE_FILE_LOAD_WARNINGS](https://www.sidefx.com/docs/houdini/ref/env) to suppress the warning dialog.)
