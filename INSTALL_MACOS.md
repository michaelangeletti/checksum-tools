# Installing checksum-tools on macOS

## Before you start

You'll need:
- macOS 15.7 (Sequoia)
- The `checksum-tools.zip` file
- About 5 minutes

Everything below happens in **Terminal** (Applications → Utilities → Terminal).

---

## Step 1: Check your Python version

macOS ships with Python 3 but we need version 3.10 or later. Run:

```
python3 --version
```

You should see something like `Python 3.13.2` or similar. Any version **3.10 or higher** is fine. If you get "command not found" or a version below 3.10, install or update Python from [python.org/downloads](https://www.python.org/downloads/) and reopen Terminal.

## Step 2: Unzip and install

Navigate to wherever you downloaded the zip (probably `~/Downloads`):

```
cd ~/Downloads
unzip checksum-tools.zip
cd checksum-tools
pip3 install --break-system-packages .
```

The `--break-system-packages` flag is needed on newer macOS because Apple locks down the system Python by default. This is safe — it just installs a small script and its one dependency (`pyyaml`) into your user environment.

If you want the optional progress bar (shows a blue bar while hashing large files), run this instead:

```
pip3 install --break-system-packages ".[progress]"
```

## Step 3: Verify it works

```
checksum-tools --version
```

You should see:

```
checksum-tools 2.0.0
```

If you get "command not found," your pip scripts directory isn't on your PATH. Try:

```
python3 -m checksum_tools.cli --version
```

If that works but `checksum-tools` doesn't, run this once to fix your PATH:

```
echo 'export PATH="$HOME/Library/Python/3.13/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

(Replace `3.13` with whatever `python3 --version` reported — just the major.minor, e.g. `3.12`, `3.11`, etc.)

---

## Quick usage test

Pick any folder with files in it and generate MD5 checksums:

```
checksum-tools -a generate -e .md5 /path/to/your/test/folder
```

Then verify them:

```
checksum-tools -a verify -e .md5 /path/to/your/test/folder
```

You should see green `PASS` for every file. Add `-r` to include subfolders.

---

## Uninstalling

If you ever want to remove it:

```
pip3 uninstall --break-system-packages checksum-tools
```
