@echo off

REM ==============================================
REM This file is auto-generated.
REM The following tokens are replaced at generation time:
REM   @HOUDINI_EXE@            : Full path to houdini executable
REM   @HOUDINI_USER_PREF_DIR@  : HOUDINI_USER_PREF_DIR of the source Houdini
REM ==============================================

set "HOUDINI_EXE=@HOUDINI_EXE@"
set "HOUDINI_USER_PREF_DIR=@HOUDINI_USER_PREF_DIR@"
set "SCRIPT_DIR=%~dp0"
set "HOUDINI_PACKAGE_DIR=%SCRIPT_DIR%\.venv\Lib\site-packages"

REM Copy .json from houdini package.
for /D %%d in ("%HOUDINI_PACKAGE_DIR%\*") do (
    set "last_dir_name=%%~nxd"
    set "json_file=%%d\%%~nxd.json"
    if exist "%%d\%%~nxd.json" (
        copy "%%d\%%~nxd.json" "%HOUDINI_PACKAGE_DIR%\"
    )
)

set "PYTHONPATH=%HOUDINI_PACKAGE_DIR%"
"%HOUDINI_EXE%"
