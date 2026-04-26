@echo off
REM checksum-tools — Generate or verify checksums for a set of files.
REM
REM Windows launcher script for standalone use (when not installed via pip).
REM Place this .bat file and the checksum_tools\ folder in the same directory,
REM or add the directory to your PATH.

setlocal

REM Find the directory this script lives in
set "SCRIPT_DIR=%~dp0"

REM Try to find the checksum_tools package relative to this script
if exist "%SCRIPT_DIR%checksum_tools\cli.py" (
    set "PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%"
) else if exist "%SCRIPT_DIR%..\checksum_tools\cli.py" (
    set "PYTHONPATH=%SCRIPT_DIR%..;%PYTHONPATH%"
)

python -m checksum_tools.cli %*
exit /b %ERRORLEVEL%
