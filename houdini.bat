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

REM Copy hpackage.json from Houdini Python packages.
for /D %%d in ("%HOUDINI_PACKAGE_DIR%\*") do (
    if exist "%%d\hpackage.json" (
        copy /Y "%%d\hpackage.json" "%HOUDINI_PACKAGE_DIR%\%%~nxd.json" > nul
    )
)

set "PYTHONPATH=%HOUDINI_PACKAGE_DIR%"
"%HOUDINI_EXE%"
