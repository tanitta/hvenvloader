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
3. The shelf tool runs `uv init --package --build-backend setuptools` and `uv sync` in `$JOB`, creates an installable `src/`-layout project and `.venv`, and writes a launcher into the project root:
   - `houdini.bat` on Windows
   - `houdini.sh` on other platforms
4. Close Houdini.
5. Start Houdini from the launcher in the project root instead of using the normal Houdini shortcut.

The generated launcher is part of the project. Keep it next to the project's `.venv` and use it whenever you work on that project.

## Tutorials

- [Use NetworkX from Houdini with hvenvloader (Japanese)](Examples/networkx/README.md)

## Shelf Tools

- `venv > Init Project` can initialize the project as an installable setuptools package with `uv init --package --build-backend setuptools`, runs `uv sync`, and writes the project launcher. The **Install this project into the venv** option is enabled by default; disable it to use `uv init --no-package`. The import package name is derived from the project directory name by `uv`.
- `venv > Create NVHP` opens a dialog for creating a Python package that contains an NVHP JSON and standard Houdini asset directories.
- `venv > Export NVHP` opens a dialog for exporting an NVHP package directory to a vanilla Houdini Package layout.
- `venv > Manage Regular Packages` manages non-NVHP Houdini Packages in `<project-root>/packages`. It can create a directory junction (a symbolic link on non-Windows systems), copy the package directory, or keep an existing directory unchanged, and places the package JSON next to it.
- `venv > uv` opens a small UI for `uv init`, `uv sync`, `uv add`, `uv remove`, `uv lock`, `uv tree`, and launcher generation. Its `uv init` action has the same project-install option. It also supports adding local packages and `uv add --editable`.

## Command Line Interface

hvenvloader can also be driven from a terminal without starting Houdini:

```bash
python -m hvenvloader init /path/to/project             # uv init --package --build-backend setuptools + uv sync + launcher
python -m hvenvloader init --launcher /path/to/project  # only re-write the launcher (no uv init/sync)
python -m hvenvloader nvhp create MyPkg /parent/dir   # create an NVHP project folder
python -m hvenvloader nvhp export /parent/dir/MyPkg/src/MyPkg /export/dir
python -m hvenvloader launcher write /path/to/project
python -m hvenvloader uv /path/to/project add numpy  # run uv in a project directory
```

`python -m hvenvloader` must be run with the package on `PYTHONPATH` (for example `PYTHONPATH=$HOUDINI_PACKAGE_PATH/hvenvloader/scripts/python`), or from inside a Houdini session that has the package installed. `init` and `launcher write` replace the `@HOUDINI_EXE@` token with the `$HVENVLOADER_HOUDINI_EXE` environment variable when it is set, and with the current interpreter otherwise. Run `python -m hvenvloader <command> --help` for the full options list.

## Launcher Behavior

### Save and Restart (Windows)

`venv > Save and Restart` saves the current HIP, closes this Houdini instance,
and opens the saved HIP through the project's `houdini.bat`. New scenes prompt
for a save location; cancelling or a save failure leaves Houdini open.

For existing projects, first use `venv > uv > Write Houdini launcher` to update
the launcher. The tool uses the recorded launcher path, or `$JOB/houdini.bat`
when Houdini was opened normally. A working project `.venv` is required.
The helper waits for this specific Houdini process, with a two-minute timeout.
Other Houdini instances are unaffected. Memory-only simulation caches are not restored.

The Windows launcher records its original `PATH` and `PYTHONPATH` for restarts.
The restart tool clears inherited Houdini/Python configuration before rerunning
the launcher and preserves `$JOB`. Custom settings required at startup should
be provided by the launcher or package configuration. Custom package environment
variables outside the Houdini/Python namespaces remain inherited.

To customize the Windows launcher template, copy `houdini.bat` to
`houdini.user.bat` **in the hvenvloader installation directory** and edit the copy.
Both shelf and CLI generation prefer this user template when present and fall
back to the standard `houdini.bat` otherwise. The project output is still named
`houdini.bat`, with the usual `@HOUDINI_EXE@`, `@HOUDINI_USER_PREF_DIR@`, and
`@HVENVLOADER@` token replacements. Regenerate existing project launchers with
`venv > uv > Write Houdini launcher` or
`python -m hvenvloader launcher write <project>` to apply template changes.
On Linux/macOS, put `houdini.user.sh` in the same directory to override the
standard `houdini.sh` template. The project output remains `houdini.sh`.
Both user templates are ignored by Git.

`houdini.bat` and `houdini.sh` are launchers for a project root. They expect this layout:

```text
project-root/
  .venv/
  .hvenvloader/
    editable_packages/
  packages/                 # optional regular Houdini Packages and JSONs
  houdini.bat or houdini.sh
  your_project.hip
```

When the launcher starts Houdini, it:

1. Finds the project's `.venv` relative to the launcher file.
2. Sets `PYTHONPATH` to the `.venv` `site-packages` directory.
3. Builds `HOUDINI_PACKAGE_DIR` in this order: an existing `<project-root>/packages`, the `.venv` `site-packages` directory, then an existing `<project-root>/.hvenvloader/editable_packages` overlay.
4. Syncs `hpackage.json` files from installed Python packages into Houdini package search directories so Houdini can discover them. Editable local installs keep the original JSON content and use a generated static overlay plus a directory link back to the source package.
5. Sets `HVENVLOADER_LAUNCHER=1` so the non-launcher fallback does not run.
6. Starts Houdini with the project virtual environment available.

Arguments passed to the launcher are forwarded to Houdini in the same order. For example, `houdini.bat "scene with spaces.hip"` or `./houdini.sh "scene with spaces.hip"`. Regenerate an existing project launcher with `venv > uv > Write Houdini launcher` to get this behavior.

If you do not use the shelf tool, copy the appropriate launcher (`houdini.bat` or `houdini.sh`) into your project root manually and edit the Houdini executable path and `HOUDINI_USER_PREF_DIR` values for your environment.

The project root used at launch time is always the directory containing the launcher. The shelf tools use `$JOB` only as the initial project-root value in their UI. The `.hvenvloader/` directory is reserved for generated state managed by hvenvloader; its `editable_packages/` contents may be rebuilt or removed and should normally be excluded from version control. The optional `<project-root>/packages/` directory contains regular Houdini Packages. Its contents can still be managed manually, or packages can be installed and removed with `venv > Manage Regular Packages`.

### Managing regular Houdini Packages

`venv > Manage Regular Packages` copies a selected package JSON unchanged to `<project-root>/packages/<PackageName>.json`. Keeping the JSON and package directory together allows package JSONs that use `$HOUDINI_PACKAGE_PATH/<PackageName>` to work without absolute paths.

The package directory has three installation modes:

- **Junction** creates `<project-root>/packages/<PackageName>` as a junction to the source directory on Windows, or as a symbolic link on other platforms. This is the recommended mode for local development.
- **Copy** copies the source directory while excluding `.git`, `.venv`, Python bytecode, and `__pycache__`. Updating replaces the previous copy so removed source files do not remain installed.
- **None** requires `<project-root>/packages/<PackageName>` to exist already and leaves it unchanged. Only the JSON is installed.

The dialog previews the destination state and detects package JSON files in the source directory. Installations are recorded in `<project-root>/.hvenvloader/local_packages.json`; **Remove Managed** only removes recorded JSONs and directories. None-mode directories are never removed. Restart Houdini after installing, updating, or removing a package.

After upgrading hvenvloader, regenerate the launcher in each existing project. An old launcher may continue to use the legacy editable overlay path inside `.venv`.

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

The easiest way to start is to run `venv > Create NVHP` in Houdini. The shelf tool opens a dialog where you can choose the save directory, project name, Python import name, Houdini environment variable name, Python requirement, and standard Houdini directories to include. It then creates the Python package layout, `pyproject.toml`, and `hpackage.json` for you.

An NVHP is intentionally hvenvloader-native. It is not a standalone vanilla Houdini Package source layout. The Python import package root is the Houdini package root, so `__init__.py` and `hpackage.json` live next to each other under `src/<package>/`. Python code should be imported as a normal Python package instead of being placed under Houdini's `scripts/python` package path convention.

The important convention is that each Python import package that provides an NVHP contains a file named `hpackage.json`. The launcher scans `.venv` metadata and package directories, and when it finds `<package>/hpackage.json`, it exposes that JSON through `HOUDINI_PACKAGE_DIR` so Houdini can discover it.

Regular installs place the import package under `site-packages`, so the launcher copies `hpackage.json` directly to `site-packages/<package>.json`. Editable local installs keep the import package in the source checkout, so the launcher reads `.dist-info/direct_url.json` and `top_level.txt`, recreates `<project-root>/.hvenvloader/editable_packages/`, copies `hpackage.json` there unchanged as `<package>.json`, and creates a sibling directory link named `<package>` that points back to the source package directory. The launcher adds this generated overlay directly to `HOUDINI_PACKAGE_DIR` while continuing to include `.venv` `site-packages` for regular installs. When no editable NVHP remains, hvenvloader removes the generated overlay. A recognized legacy `.venv/.../site-packages/_hvenvloader_houdini_packages/` overlay is also cleaned up, but is never added to `HOUDINI_PACKAGE_DIR` by a new launcher.

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
