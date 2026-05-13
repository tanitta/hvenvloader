# Houdini venv Loader (hvenvloader)

[English](README.md) | [日本語](README.ja.md)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/tanitta/hvenvloader/blob/main/LICENSE)

## Description

This is a Houdini package for use within a Python project workflow, providing the following functionality:

- Loading Python packages from the project-local Python virtual environment `.venv` into Houdini.
- Loading Native venvloader Houdini Packages (NVHPs) installed as Python packages under `.venv`.
- Creating a project launcher (`houdini.bat` or `houdini.sh`) that starts Houdini with the project's `.venv`.
- Providing shelf tools for initializing uv projects, creating NVHPs, and running common uv commands.

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

## Shelf Tools

- `venv > Init Project` runs `uv init`, `uv sync`, and writes the project launcher.
- `venv > Create NVHP` opens a dialog for creating a Python package that contains an NVHP JSON and standard Houdini asset directories.
- `venv > Export NVHP` opens a dialog for exporting an NVHP package directory to a vanilla Houdini Package layout.
- `venv > uv` opens a small UI for `uv init`, `uv sync`, `uv add`, `uv remove`, `uv lock`, `uv tree`, and launcher generation. It also supports adding local packages and `uv add --editable`.

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
2. Sets `PYTHONPATH` to the `.venv` `site-packages` directory.
3. Sets `HOUDINI_PACKAGE_DIR` to the `.venv` `site-packages` directory, plus a generated editable-package directory when needed.
4. Syncs `hpackage.json` files from installed Python packages into Houdini package search directories so Houdini can discover them. Editable local installs keep the original JSON content and use a generated static overlay plus a directory link back to the source package.
5. Sets `HVENVLOADER_LAUNCHER=1` so the non-launcher fallback does not run.
6. Starts Houdini with the project virtual environment available.

If you do not use the shelf tool, copy the appropriate launcher (`houdini.bat` or `houdini.sh`) into your project root manually and edit the Houdini executable path and `HOUDINI_USER_PREF_DIR` values for your environment.

## Non-Launcher Behavior

When Houdini is started without the generated launcher, hvenvloader falls back to `python3.11libs/ready.py`.

In this mode, hvenvloader only adds `$JOB/.venv` `site-packages` to Houdini's Python path. NVHP files from installed Python packages are not loaded in non-launcher fallback mode. Use the generated launcher when you need NVHP discovery from `.venv`.

## Usage

1. Install Python packages into the project `.venv`.
2. Start Houdini with the project root launcher when you need both Python packages and NVHPs from `.venv`.
3. Open the project's `.hip` file.

When Houdini starts through the normal shortcut, Python packages installed in `$JOB/.venv` are available through the `ready.py` fallback, but NVHP files provided by those packages are not loaded.

## Creating Native venvloader Houdini Packages (NVHP)

hvenvloader loads NVHP `.json` files that are distributed inside Python packages installed in the project `.venv`. See [HoudiniUnityAnimationClip](https://github.com/tanitta/HoudiniUnityAnimationClip) for a practical example of a Houdini asset package distributed as a Python package.

The easiest way to start is to run `venv > Create NVHP` in Houdini. The shelf tool opens a dialog where you can choose the save directory, project name, import package name, Houdini environment variable name, Python requirement, and standard Houdini directories to include. It then creates the Python package layout, `pyproject.toml`, and `hpackage.json` for you.

An NVHP is intentionally hvenvloader-native. It is not a standalone vanilla Houdini Package source layout. The Python import package root is the Houdini package root, so `__init__.py` and `hpackage.json` live next to each other under `src/<package>/`. Python code should be imported as a normal Python package instead of being placed under Houdini's `scripts/python` package path convention.

The important convention is that each Python import package that provides an NVHP contains a file named `hpackage.json`. The launcher scans `.venv` metadata and package directories, and when it finds `<package>/hpackage.json`, it exposes that JSON through `HOUDINI_PACKAGE_DIR` so Houdini can discover it.

Regular installs place the import package under `site-packages`, so the launcher copies `hpackage.json` directly to `site-packages/<package>.json`. Editable local installs keep the import package in the source checkout, so the launcher reads `.dist-info/direct_url.json` and `top_level.txt`, recreates `.venv/.../site-packages/_hvenvloader_houdini_packages/`, copies `hpackage.json` there unchanged, and creates a generated directory link named `<package>` that points back to the source package directory. The launcher adds that generated directory directly to `HOUDINI_PACKAGE_DIR`.

Because NVHPs rely on this `.venv` layout, install them with uv and start Houdini through the generated hvenvloader launcher. Installing the source checkout directly as a regular Houdini Package is not supported. This tradeoff keeps imports consistent between Houdini, `uv run`, tests, and build scripts.

When you need a regular Houdini Package distribution, use `venv > Export NVHP`. The exporter takes an NVHP package directory such as `src/MyHoudiniPackage/` and an export directory, then writes:

```text
export/
  MyHoudiniPackage.json
  MyHoudiniPackage/
    otls/
    toolbar/
    scripts/
      python/
        MyHoudiniPackage/
          __init__.py
```

The exported top-level JSON is copied from `hpackage.json` unchanged. Python source files (`*.py`) are copied into Houdini's `scripts/python/<package>/` location while preserving their directory structure. Non-Python files from the module tree are not copied there. Houdini asset directories stay under the exported package folder. Top-level names reserved for Houdini asset directories, such as `otls`, `scripts`, `toolbar`, `python_panels`, and `usd`, are treated as Houdini asset directories. Do not use those names for Python subpackages in an NVHP.

Use this layout as a starting point:

```text
my-houdini-package/
  pyproject.toml
  README.md
  src/
    MyHoudiniPackage/
      __init__.py
      hpackage.json
      otls/
        my_asset.hda
```

You can also create this structure manually if you prefer not to use the shelf tool.

`hpackage.json` should point Houdini back to the installed Python package directory. For example:

```json
{
  "hpath": "$MYHOUDINIPACKAGE",
  "env": [
    {
      "MYHOUDINIPACKAGE": "$HOUDINI_PACKAGE_PATH/MyHoudiniPackage"
    }
  ]
}
```

With this package file, Houdini resolves the installed package directory as a Houdini path, so standard Houdini subdirectories such as `otls`, `scripts`, `toolbar`, and `python_panels` can live under `src/MyHoudiniPackage/`.

Include the NVHP JSON and Houdini assets as Python package data. A minimal `pyproject.toml` using setuptools looks like this:

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "MyHoudiniPackage"
version = "0.1.0"
description = "My native venvloader Houdini package."
requires-python = ">=3.10"
dependencies = []

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
MyHoudiniPackage = [
  "hpackage.json",
  "otls/**/*",
  "scripts/**/*",
  "toolbar/**/*",
  "python_panels/**/*",
]
```

After publishing the package or making it available from a Git repository, add it to the Houdini project from the project root:

```shell
uv add "MyHoudiniPackage @ git+https://github.com/owner/MyHoudiniPackage.git"
uv sync
```

Then restart Houdini through the generated project launcher (`houdini.bat` or `houdini.sh`). On startup, hvenvloader makes the Python package importable and exposes `hpackage.json` through the package search directory for Houdini as `MyHoudiniPackage.json`.
