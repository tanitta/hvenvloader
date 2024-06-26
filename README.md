# Houdini venv Loader

## Description

This is a Houdini Package designed for handling Houdini within a Python project workflow, and offers the following features:
- Loading Python packages from the Python virtual environment `.venv` within the Project directory.
- Loading [Houdini Package](https://www.sidefx.com/docs/houdini/ref/plugins.html) included in the Python Package from `.venv` into Houdini.

## Installation

1. Install python package manager (rye, poetry, etc...).
2. Clone This Repository into your `$HOUDINI_PREF_DIR/packages`.
3. Copy and paste `hvenvloader.json` in it into `$HOUDINI_PREF_DIR/packages`.

cf. [Houdini packages | Houdini help](https://www.sidefx.com/docs/houdini/ref/plugins.html)

## Usage

1. Create a Python project using python package manager.
2. (Optional) Add packages and set the Python version to project congig.
3. In the newly created directory from step 1, create a `.hip` file and set the directory's root as `$JOB` in the `.hip` file.
4. Reopen the `.hip` file. (When the `.hip` file is loaded, Houdini reads the `site-packages` from `.venv` through hvenvloader's `456.py`).
