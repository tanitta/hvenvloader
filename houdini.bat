@echo off
set "HOUDINI_USER_PREF_DIR=%USERPROFILE%\Documents\houdini20.5"
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
set "houdini=C:\Program Files\Side Effects Software\Houdini 20.5.370\bin\houdini.exe"
"%houdini%"
