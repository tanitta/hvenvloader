@echo off
setlocal EnableExtensions EnableDelayedExpansion

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
set "HVENVLOADER_PROJECT_PACKAGE_DIR=%SCRIPT_DIR%packages"
set "HVENVLOADER_EDITABLE_PACKAGE_DIR=%SCRIPT_DIR%.hvenvloader\editable_packages"
set "HVENVLOADER_PACKAGE_SYNC=%HVENVLOADER%\scripts\python\hvenvloader\package_sync.py"
set "HVENVLOADER_PYTHON_PATHS=%PYTHON_SITE_PACKAGES%\_hvenvloader_python_paths.txt"
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

if exist "%HVENVLOADER_PROJECT_PACKAGE_DIR%\" (
    set "HOUDINI_PACKAGE_DIR=%HVENVLOADER_PROJECT_PACKAGE_DIR%;!HOUDINI_PACKAGE_DIR!"
)
if exist "%HVENVLOADER_EDITABLE_PACKAGE_DIR%\" (
    set "HOUDINI_PACKAGE_DIR=!HOUDINI_PACKAGE_DIR!;%HVENVLOADER_EDITABLE_PACKAGE_DIR%"
)

set "HVENVLOADER_PYTHONPATH=%PYTHON_SITE_PACKAGES%"
if exist "%HVENVLOADER_PYTHON_PATHS%" (
    for /F "usebackq delims=" %%p in ("%HVENVLOADER_PYTHON_PATHS%") do (
        if not "%%p"=="" set "HVENVLOADER_PYTHONPATH=!HVENVLOADER_PYTHONPATH!;%%p"
    )
)

if defined PYTHONPATH (
    set "PYTHONPATH=!HVENVLOADER_PYTHONPATH!;%PYTHONPATH%"
) else (
    set "PYTHONPATH=!HVENVLOADER_PYTHONPATH!"
)
setlocal DisableDelayedExpansion
"%HOUDINI_EXE%" %*
