---
name: hvenvloader
description: Set up, inspect, validate, export, or troubleshoot Houdini projects and Native venvloader Houdini Packages (NVHPs) that use hvenvloader and uv. Use for hvenvloader launchers, project-local .venv integration, hpackage.json discovery, editable NVHP installs, or conversion to vanilla Houdini Packages; do not use for generic Houdini or Python work that does not involve hvenvloader.
---

# Houdini venv Loader

Work with hvenvloader projects and NVHPs using the conventions implemented by the plugin's bundled hvenvloader version.

## Establish context

Determine which kind of repository is in scope before making changes:

- A Houdini project consuming packages from a project-local `.venv`.
- An NVHP source package distributed as a Python package.
- The hvenvloader source repository itself.

Inspect the relevant `pyproject.toml`, `uv.lock`, launcher, `hpackage.json`, package source layout, and `.venv` metadata. When `../../README.md` exists, read it for the bundled version's user-facing contract. When bundled implementation details matter and the files exist, inspect `../../scripts/python/hvenvloader/tools.py`, `../../scripts/python/hvenvloader/package_sync.py`, and the launcher templates instead of reconstructing their behavior from memory.

If this skill was installed without the surrounding plugin repository, locate the target project's hvenvloader checkout or installation and read its README and implementation when version-specific behavior matters. Treat the version actually used by the target project as authoritative; if it cannot be inspected, state that version-specific behavior remains unverified.

## Preserve the core model

- The project launcher and `.venv` belong together at the Houdini project root.
- A launcher-mode start exposes the `.venv` Python packages and synchronizes NVHP package JSON files for Houdini discovery.
- The non-launcher fallback adds project Python packages but does not provide full NVHP discovery. Do not present normal Houdini startup as equivalent to the generated launcher.
- An NVHP is a Python distribution whose import package contains both `__init__.py` and `hpackage.json`, normally under `src/<import-package>/`.
- Houdini assets live below that same import package in standard directories such as `otls`, `scripts`, `toolbar`, `python_panels`, or `desktop` and must be included as Python package data.
- Editable installs use distribution metadata and a generated `_hvenvloader_houdini_packages` overlay. Diagnose or regenerate that overlay; do not treat it as hand-maintained source.

## Choose the workflow

### Set up or repair a consuming project

Confirm the intended project root and Houdini Python version. Prefer the existing hvenvloader shelf workflow when the task is interactive. For requested automation, reuse the bundled launcher templates and implementation conventions; do not invent a second launcher format.

For custom launcher generation, copy the platform template to `houdini.user.bat` or `houdini.user.sh` in the hvenvloader installation root, not the consuming project root. Shelf and CLI generation prefer that user template when present and fall back to `houdini.bat` or `houdini.sh`. CLI `--hvenvloader` selects the template root. Output in the project remains `houdini.bat` or `houdini.sh`, with the usual `@HOUDINI_EXE@`, `@HOUDINI_USER_PREF_DIR@`, and `@HVENVLOADER@` replacements. Regenerate existing project launchers to apply changes; preserve user templates and keep them out of commits.

After setup, verify that `.venv`, `pyproject.toml`, `uv.lock` when applicable, and the platform launcher agree on the same project root. Use `uv sync` only when dependency installation or repair is part of the request.

### Create or modify an NVHP

Prefer the bundled `create_houdini_package` behavior as the source of defaults. Keep the distribution name, Python import name, and Houdini environment variable distinct when the project requires it. Ensure `hpackage.json` resolves the installed import-package directory through `HOUDINI_PACKAGE_PATH`, and keep all required JSON and Houdini assets in the build backend's package-data configuration.

Do not place ordinary Python package modules under Houdini's `scripts/python` convention in NVHP source. They remain normal importable Python modules until a vanilla Houdini Package export is requested.

### Validate an NVHP

Check at least these observable invariants:

- The selected package directory contains `__init__.py` and valid `hpackage.json`.
- `pyproject.toml` discovers the import package and includes `hpackage.json` plus the intended asset trees in built distributions.
- The environment variable and package-directory references in `hpackage.json` match the actual import package.
- Reserved top-level Houdini asset directory names are not also being used as Python subpackages when that would make vanilla export ambiguous.
- A wheel or installed distribution actually contains the declared JSON and assets when build verification is requested.

Report which checks were performed and separate source-layout validity from live Houdini loading, which may require a Houdini process started through the launcher.

### Export to a vanilla Houdini Package

Use the bundled `export_nvhp` implementation or its shelf tool rather than duplicating the transformation. Export to a user-selected directory or a temporary validation directory. Do not overwrite an existing export unless the user requested replacement and the exact destination has been checked.

Verify that the export has a top-level package JSON, a package directory containing Houdini assets, and Python sources under `scripts/python/<package>/`. Keep generated exports out of tracked source unless the user explicitly wants them committed.

### Diagnose loading failures

Distinguish launcher mode from fallback mode first. Then inspect the matching platform launcher, `.venv` site-packages, copied `<package>.json` files, editable-install `direct_url.json` and `top_level.txt`, the generated overlay, `PYTHONPATH`, `HOUDINI_PACKAGE_DIR`, and `HVENVLOADER_LAUNCHER` as relevant.

Prefer evidence from files and captured process output. Do not claim that Houdini loaded an NVHP successfully unless the live process or its output was actually checked.

### Use the command line interface

The package ships a Houdini-free CLI: `python -m hvenvloader` (module under `scripts/python`). Commands:

- `init [path]`: `uv init --package --build-backend setuptools` + `uv sync` + launcher write. Flags: `--init`, `--sync`, `--launcher` (each on by default for a new project), `--no-init`, `--no-sync`, `--no-launcher` (opt out), `--no-package`, `--python`, `--force`, `--hvenvloader`. Pass a single one (for example `--launcher`) to update only that part of an existing project. The launcher `@HOUDINI_EXE@` token is filled from `$HVENVLOADER_HOUDINI_EXE`, falling back to the current interpreter.
- `nvhp create <name> [path]`: creates an NVHP project folder (same layout as the Create NVHP shelf tool). Flags: `--package-name`, `--env-var`, `--version`, `--description`, `--requires-python`, `--subdirs`, `--no-readme`, `--force`, `--sync`.
- `nvhp export <package_dir> <export_dir>`: exports an NVHP to a vanilla Houdini Package layout. Flag: `--force`.
- `launcher write [path]`: writes `houdini.bat` / `houdini.sh` from the user template when present, otherwise the bundled template (always overwrites the project launcher). Flag: `--hvenvloader`.
- `uv [path] <uv args...>`: runs `uv` in the project directory and streams output.

Prefer the CLI over the shelf tools when Houdini is not running (CI, script-based setup). It shares the same implementation functions as the shelf tools; do not duplicate that logic.

## Execution boundaries

Do not launch Houdini, modify global Houdini package configuration, install dependencies, rebuild `.venv`, or overwrite exports for a read-only explanation, review, or diagnosis. Perform those mutations only when they are part of the user's requested outcome. Preserve unrelated worktree changes and use the project's existing hvenvloader implementation instead of copying its logic into ad hoc scripts.
