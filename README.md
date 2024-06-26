# hrye

## Description

This is a package management tool based on the project workflow using the Python package manager, [rye](https://github.com/astral-sh/rye). This tool offers the following features:
- Loading Python packages from the Python virtual environment `.venv` within the Project directory.
- (WIP) Loading Houdini packages from the Python virtual environment `.venv` within the Project directory.
- (WIP) Managing Rye operations from Houdini's Tool Shelf.


## Installation

1. Install rye.
2. Clone This Repository into your `$HOUDINI_PREF_DIR/packages`.
3. Copy and paste `hrye.json` in it into `$HOUDINI_PREF_DIR/packages`.

cf. [Houdini packages | Houdini help](https://www.sidefx.com/docs/houdini/ref/plugins.html)

## Usage

1. Create a Python project using Rye.
2. (Optional) Use Rye to add packages or set the Python version.
3. In the newly created directory from step 1, create a `.hip` file and set the directory's root as `$JOB` in the `.hip` file.
4. Reopen the `.hip` file. (When the `.hip` file is loaded, Houdini reads the `site-packages` from `.venv` through `hrye`'s `456.py`).
