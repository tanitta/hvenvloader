"""Command line interface for hvenvloader.

Runs without Houdini. Commands mirror the shelf tools:

  hvenv init         # uv init --package --build-backend setuptools + uv sync + launcher
  hvenv nvhp create    # create an NVHP project layout
  hvenv nvhp export    # export an NVHP to a vanilla Houdini Package layout
  hvenv launcher write # write the project launcher from the bundled template
  hvenv uv <args>      # run uv in a project directory
"""
import argparse
import os
import sys

from .tools import (
    DEFAULT_HOUDINI_SUBDIRS,
    _format_command,
    _safe_env_var,
    _safe_import_package_name,
    _uv_failure_hint,
    create_houdini_package,
    export_nvhp,
    launcher_path,
    python_version_tag,
    run_uv,
)


def _resolve_hvenvloader_root(override):
    from pathlib import Path

    if override:
        return Path(override)
    try:
        from .tools import _hvenvloader_root

        return _hvenvloader_root()
    except Exception:
        return Path(__file__).resolve().parents[3]


def generate_launcher_cli(root_path, hvenvloader_root=None):
    """Write the project launcher without a running Houdini session."""
    import stat as stat_module
    from pathlib import Path

    from .tools import launcher_name, launcher_template_path

    root_path = Path(root_path)
    launcher_file_name = launcher_name()
    if hvenvloader_root is None:
        hvenvloader_root = _resolve_hvenvloader_root(None)

    template_path = launcher_template_path(hvenvloader_root, launcher_file_name)
    text = template_path.read_text(encoding="utf-8")
    houdini_exe = os.environ.get("HVENVLOADER_HOUDINI_EXE") or sys.executable
    text = text.replace("@HOUDINI_EXE@", houdini_exe)
    text = text.replace("@HOUDINI_USER_PREF_DIR@", os.environ.get("HOUDINI_USER_PREF_DIR") or "")
    text = text.replace("@HVENVLOADER@", str(hvenvloader_root))

    output_path = root_path / launcher_file_name
    newline = "\r\n" if launcher_file_name == "houdini.bat" else "\n"
    output_path.write_text(text, encoding="utf-8", newline=newline)
    if launcher_file_name == "houdini.sh":
        output_path.chmod(
            output_path.stat().st_mode | stat_module.S_IXUSR | stat_module.S_IXGRP | stat_module.S_IXOTH
        )
    return output_path


def _run_uv_cli(args, cwd):
    """Run uv, stream its output, and return the exit code."""
    print("$ uv {}".format(_format_command(args)))
    try:
        result = run_uv(args, cwd)
    except FileNotFoundError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 127

    output = (result.stdout or "") + (result.stderr or "")
    if output.strip():
        print(output.rstrip())
    hint = _uv_failure_hint(output)
    if result.returncode != 0 and hint:
        print(hint)
    return result.returncode


def _require_dir(path_arg, label):
    from pathlib import Path

    root_path = Path(path_arg).expanduser()
    if not root_path.is_dir():
        print("error: {} does not exist: {}".format(label, root_path), file=sys.stderr)
        return None
    return root_path


def _write_launcher_cli(root_path, hvenvloader_root):
    try:
        written_path = generate_launcher_cli(root_path, hvenvloader_root=hvenvloader_root)
    except Exception as exc:
        print("error: failed to write launcher: {}".format(exc), file=sys.stderr)
        return None
    print("Wrote launcher: {}".format(written_path))
    return written_path


def _cmd_init(args):
    root_path = _require_dir(args.path, "project directory")
    if root_path is None:
        return 1

    if args.python:
        version = args.python.lstrip(">=^~<")
    else:
        version = python_version_tag()
    init_args = ["init"]
    if args.no_package:
        init_args.append("--no-package")
    else:
        init_args.extend(["--package", "--build-backend", "setuptools"])
    init_args.extend(["-p", version])

    pyproject_path = root_path / "pyproject.toml"
    if args.init:
        if pyproject_path.exists() and not args.force:
            print(
                "error: {} already exists. Use --force to run uv init anyway.".format(pyproject_path),
                file=sys.stderr,
            )
            return 1
        exit_code = _run_uv_cli(init_args, root_path)
        if exit_code != 0:
            return exit_code

    if args.sync:
        if not pyproject_path.is_file():
            print(
                "error: uv sync needs pyproject.toml; create it with --init first.",
                file=sys.stderr,
            )
            return 1
        exit_code = _run_uv_cli(["sync"], root_path)
        if exit_code != 0:
            return exit_code

    if args.launcher:
        if _write_launcher_cli(root_path, args.hvenvloader) is None:
            return 1

    if not (args.init or args.sync or args.launcher):
        print("error: nothing to do; pass --init, --sync, and/or --launcher.", file=sys.stderr)
        return 2
    return 0

def _cmd_nvhp_create(args):
    subdirs = [name.strip() for name in args.subdirs.split(",") if name.strip()]
    for subdir in subdirs:
        if subdir not in DEFAULT_HOUDINI_SUBDIRS:
            print(
                "error: unknown Houdini directory '{}'. Options: {}".format(
                    subdir, ", ".join(DEFAULT_HOUDINI_SUBDIRS)
                ),
                file=sys.stderr,
            )
            return 2

    package_name = args.package_name or _safe_import_package_name(args.name)
    env_var = args.env_var or _safe_env_var(package_name)
    try:
        root_path = create_houdini_package(
            save_dir=args.path,
            project_name=args.name,
            package_name=package_name,
            env_var=env_var,
            version=args.version,
            description=args.description,
            requires_python=args.requires_python or ">={}".format(python_version_tag()),
            subdirs=subdirs,
            include_readme=not args.no_readme,
            overwrite=args.force,
        )
    except (ValueError, FileExistsError) as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 1

    print("Created NVHP project: {}".format(root_path))
    if args.sync:
        exit_code = _run_uv_cli(["sync"], root_path)
        if exit_code != 0:
            return exit_code
    return 0


def _cmd_nvhp_export(args):
    try:
        result = export_nvhp(args.package_dir, args.export_dir, overwrite=args.force)
    except (ValueError, FileExistsError) as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 1

    print("Exported: {}".format(result["package_dir"]))
    print("Package JSON: {}".format(result["package_json"]))
    return 0


def _cmd_launcher_write(args):
    root_path = _require_dir(args.path, "project directory")
    if root_path is None:
        return 1

    if _write_launcher_cli(root_path, args.hvenvloader) is None:
        return 1
    return 0

def _cmd_uv(args):
    root_path = _require_dir(args.path, "project directory")
    if root_path is None:
        return 1
    if not args.uv_args:
        print("error: pass a uv command, for example: hvenv uv sync", file=sys.stderr)
        return 2
    return _run_uv_cli(args.uv_args, root_path)


def _default_subdirs_text():
    return ", ".join(subdir for subdir in DEFAULT_HOUDINI_SUBDIRS if subdir != "desktop")

def build_parser():
    parser = argparse.ArgumentParser(
        prog="hvenv",
        description="hvenvloader command line interface. Runs without Houdini.",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init",
        help="Create a new project: uv init --package --build-backend setuptools, uv sync, and write the launcher.",
    )
    init_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory (defaults to the current directory).",
    )
    init_parser.add_argument(
        "--init",
        action="store_true",
        help="Run uv init (default on for a new project).",
    )
    init_parser.add_argument(
        "--no-init",
        action="store_true",
        help="Skip uv init even for a new project.",
    )
    init_parser.add_argument(
        "--sync",
        action="store_true",
        help="Run uv sync (default on for a new project).",
    )
    init_parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip uv sync even for a new project.",
    )
    init_parser.add_argument(
        "--launcher",
        action="store_true",
        help="Write the launcher (default on for a new project).",
    )
    init_parser.add_argument(
        "--no-launcher",
        action="store_true",
        help="Skip the launcher write even for a new project.",
    )
    init_parser.add_argument(
        "--no-package",
        action="store_true",
        help="Use uv init --no-package instead of the installable src-layout project.",
    )
    init_parser.add_argument(
        "--python",
        default=None,
        help="Python version for uv (defaults to this interpreter's version).",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing launcher and re-run uv init when requested.",
    )
    init_parser.add_argument(
        "--hvenvloader",
        default=None,
        help="Path to the hvenvloader package (defaults to the installed copy).",
    )
    init_parser.set_defaults(func=_cmd_init, _init_default=True)

    nvhp_parser = subparsers.add_parser("nvhp", help="Create and export NVHPs.")
    nvhp_subparsers = nvhp_parser.add_subparsers(dest="nvhp_command")
    create_parser = nvhp_subparsers.add_parser(
        "create",
        help="Create an NVHP project folder under a parent directory.",
    )
    create_parser.add_argument(
        "name",
        help="Project name; the project folder is created as <path>/<name>.",
    )
    create_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Parent directory for the new project folder (defaults to the current directory).",
    )
    create_parser.add_argument(
        "--package-name",
        default=None,
        help="Python import name (defaults to the project name).",
    )
    create_parser.add_argument(
        "--env-var",
        default=None,
        help="Houdini environment variable (defaults from the import name).",
    )
    create_parser.add_argument("--version", default="0.1.0")
    create_parser.add_argument(
        "--description",
        default="My native venvloader Houdini package.",
    )
    create_parser.add_argument(
        "--requires-python",
        default=None,
        help="Defaults to >=<this interpreter's version>.",
    )
    create_parser.add_argument(
        "--subdirs",
        default=_default_subdirs_text().replace(", ", ","),
        help="Comma-separated Houdini directories to create (default: {}).".format(
            _default_subdirs_text()
        ),
    )
    create_parser.add_argument("--no-readme", action="store_true", help="Do not create README.md.")
    create_parser.add_argument("--force", action="store_true", help="Overwrite existing generated files.")
    create_parser.add_argument("--sync", action="store_true", help="Run uv sync in the created project.")
    create_parser.set_defaults(func=_cmd_nvhp_create)

    export_parser = nvhp_subparsers.add_parser(
        "export",
        help="Export an NVHP package directory to a vanilla Houdini Package layout.",
    )
    export_parser.add_argument(
        "package_dir",
        help="NVHP package directory containing hpackage.json and __init__.py.",
    )
    export_parser.add_argument(
        "export_dir",
        help="Directory to receive <package>.json and the <package> folder.",
    )
    export_parser.add_argument("--force", action="store_true", help="Overwrite an existing export.")
    export_parser.set_defaults(func=_cmd_nvhp_export)

    launcher_parser = subparsers.add_parser("launcher", help="Manage the project launcher.")
    launcher_subparsers = launcher_parser.add_subparsers(dest="launcher_command")
    write_parser = launcher_subparsers.add_parser(
        "write",
        help="Write houdini.bat / houdini.sh into a project directory.",
    )
    write_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory (defaults to the current directory).",
    )
    write_parser.add_argument(
        "--hvenvloader",
        default=None,
        help="Path to the hvenvloader package (defaults to the installed copy).",
    )
    write_parser.add_argument("--force", action="store_true", help="Overwrite the existing launcher.")
    write_parser.set_defaults(func=_cmd_launcher_write)

    uv_parser = subparsers.add_parser(
        "uv",
        help="Run uv in a project directory and stream its output.",
    )
    uv_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory to run uv in (defaults to the current directory).",
    )
    uv_parser.add_argument("uv_args", nargs=argparse.REMAINDER, help="uv command and arguments.")
    uv_parser.set_defaults(func=_cmd_uv)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 2

    if getattr(args, "_init_default", False):
        if not (args.init or args.no_init or args.sync or args.no_sync or args.launcher or args.no_launcher):
            args.init = True
            args.sync = True
            args.launcher = True
        if args.no_init:
            args.init = False
        if args.no_sync:
            args.sync = False
        if args.no_launcher:
            args.launcher = False

    func = getattr(args, "func", None)
    if func is None:
        parser.parse_args([args.command, "--help"])
        return 2

    return func(args)
