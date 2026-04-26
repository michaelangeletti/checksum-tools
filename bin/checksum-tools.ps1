# checksum-tools — Generate or verify checksums for a set of files.
#
# PowerShell launcher script for standalone use (when not installed via pip).
# Usage: .\checksum-tools.ps1 -a verify -e .md5 -r C:\path\to\files

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Find the checksum_tools package relative to this script
if (Test-Path "$ScriptDir\checksum_tools\cli.py") {
    $env:PYTHONPATH = "$ScriptDir;$env:PYTHONPATH"
} elseif (Test-Path "$ScriptDir\..\checksum_tools\cli.py") {
    $env:PYTHONPATH = "$ScriptDir\..;$env:PYTHONPATH"
}

python -m checksum_tools.cli @args
exit $LASTEXITCODE
