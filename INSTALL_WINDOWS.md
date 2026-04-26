# Installing checksum-tools on Windows 11

## Before you start

You'll need:
- Windows 11
- Python 3.10 or later
- The `checksum-tools-win.zip` file
- About 5 minutes

Everything below happens in **Command Prompt** or **PowerShell** (search "cmd" or "PowerShell" in the Start menu).

---

## Step 1: Check your Python version

Open a terminal and run:

```
python --version
```

You should see something like `Python 3.13.2`. Any version **3.10 or higher** is fine.

If you get "'python' is not recognized" or a version below 3.10, install Python from [python.org/downloads](https://www.python.org/downloads/). During installation, **check the box "Add python.exe to PATH"**, then reopen your terminal.

## Step 2: Unzip and install

Navigate to wherever you downloaded the zip:

```
cd %USERPROFILE%\Downloads
```

Extract the zip (right-click → "Extract All" in Explorer, or use the command below):

```
tar -xf checksum-tools-win.zip
cd checksum-tools-win
pip install .
```

If you want the optional progress bar (shows a blue bar while hashing large files):

```
pip install ".[progress]"
```

## Step 3: Verify it works

```
checksum-tools --version
```

You should see:

```
checksum-tools 2.0.0
```

If you get "'checksum-tools' is not recognized," try:

```
python -m checksum_tools.cli --version
```

If that works, your pip Scripts directory isn't on your PATH. You can either:

- Re-run the Python installer and check "Add python.exe to PATH"
- Or use `python -m checksum_tools.cli` in place of `checksum-tools` for all commands

---

## Quick usage test

Pick any folder with files in it and generate MD5 checksums:

```
checksum-tools -a generate -e .md5 C:\Users\YourName\Desktop\test-folder
```

Then verify them:

```
checksum-tools -a verify -e .md5 C:\Users\YourName\Desktop\test-folder
```

You should see green **PASS** for every file. Add `-r` to include subfolders.

### Terminal colors

Colors work automatically in **Windows Terminal** (the default terminal in Windows 11). If you're using the older `cmd.exe` and don't see colors, try running from Windows Terminal instead, or set the environment variable `FORCE_COLOR=1`.

---

## Standalone use (without pip)

If you prefer not to use pip, you can run checksum-tools directly:

**Command Prompt:**
```
bin\checksum-tools.bat -a verify -e .md5 -r C:\path\to\files
```

**PowerShell:**
```
.\bin\checksum-tools.ps1 -a verify -e .md5 -r C:\path\to\files
```

**Any terminal:**
```
python -m checksum_tools.cli -a verify -e .md5 -r C:\path\to\files
```

For standalone use, you'll need to install `pyyaml` separately:
```
pip install pyyaml
```

---

## Hidden files

The `--no-hidden` flag skips hidden files on Windows. This includes:

- Files with the Windows "Hidden" attribute set
- Common system files: `Thumbs.db`, `desktop.ini`, `ehthumbs.db`
- Dot-prefixed files (`.gitignore`, etc.)

Example:
```
checksum-tools -a verify -e .md5 -r --no-hidden C:\path\to\files
```

---

## Uninstalling

```
pip uninstall checksum-tools
```
