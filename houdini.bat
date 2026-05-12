@echo off

REM ==============================================
REM This file is auto-generated.
REM The following tokens are replaced at generation time:
REM   @HOUDINI_EXE@            : Full path to houdini executable
REM   @HOUDINI_USER_PREF_DIR@  : HOUDINI_USER_PREF_DIR of the source Houdini
REM ==============================================

set "HOUDINI_EXE=@HOUDINI_EXE@"
set "HOUDINI_USER_PREF_DIR=@HOUDINI_USER_PREF_DIR@"
set "HVENVLOADER_LAUNCHER=1"
set "HVENVLOADER=@HVENVLOADER@"
set "SCRIPT_DIR=%~dp0"
set "PYTHON_SITE_PACKAGES=%SCRIPT_DIR%\.venv\Lib\site-packages"
set "HOUDINI_PACKAGE_DIR=%PYTHON_SITE_PACKAGES%"
set "HVENVLOADER_EDITABLE_PACKAGE_DIR=%PYTHON_SITE_PACKAGES%\_hvenvloader_houdini_packages"
set "HVENVLOADER_PACKAGE_SYNC=%HVENVLOADER%\scripts\python\hvenvloader\package_sync.py"
set "VENV_PYTHON=%SCRIPT_DIR%\.venv\Scripts\python.exe"
set "HVENVLOADER_SYNCED="

if exist "%VENV_PYTHON%" (
    if exist "%HVENVLOADER_PACKAGE_SYNC%" (
        "%VENV_PYTHON%" "%HVENVLOADER_PACKAGE_SYNC%" "%PYTHON_SITE_PACKAGES%" "%HVENVLOADER_EDITABLE_PACKAGE_DIR%"
        set "HVENVLOADER_SYNCED=1"
    )
)

if not defined HVENVLOADER_SYNCED (
    REM Copy hpackage.json from Houdini Python packages.
    for /D %%d in ("%PYTHON_SITE_PACKAGES%\*") do (
        if exist "%%d\hpackage.json" (
            copy /Y "%%d\hpackage.json" "%PYTHON_SITE_PACKAGES%\%%~nxd.json" > nul
        )
    )
)

if exist "%HVENVLOADER_EDITABLE_PACKAGE_DIR%" (
    set "HOUDINI_PACKAGE_DIR=%PYTHON_SITE_PACKAGES%;%HVENVLOADER_EDITABLE_PACKAGE_DIR%"
)

if defined PYTHONPATH (
    set "PYTHONPATH=%PYTHON_SITE_PACKAGES%;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%PYTHON_SITE_PACKAGES%"
)
"%HOUDINI_EXE%"
