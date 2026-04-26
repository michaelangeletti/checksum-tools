# checksum-tools Manual

**Version 2.0 — Stanford Media Preservation Lab**

---

## Executive Summary

**checksum-tools** is a command-line utility used by the Stanford Media Preservation Lab to ensure the integrity of digitized and born-digital media files. It works by generating and verifying cryptographic checksums — unique digital fingerprints that can detect whether a file has been altered, corrupted, or damaged at any point during storage, transfer, or migration.

Digital preservation depends on the guarantee that a file today is identical to the file as it was originally captured or received. A single flipped bit in a 200 GB video file is invisible to the eye but represents data loss. Checksums provide a mathematical proof that a file is unchanged. Without automated checksum verification, corruption can go undetected indefinitely.

The tool operates in two modes. In **generate** mode, it reads every file in a directory, computes a cryptographic hash (such as MD5 or SHA-256), and writes that hash either to individual sidecar files or to a single manifest file. In **verify** mode, it re-reads each file, recomputes the hash, and compares it to the stored value. A match means the file is intact. A mismatch means something has changed.

checksum-tools was built to replace an older Ruby-based tool (`sul-dlss/checksum-tools`) with a modern, cross-platform Python implementation. It reads checksum files produced by virtually any tool — macOS, Linux, and Windows utilities alike — so it works with existing collections regardless of how or when the checksums were originally created. It is optimized for the large media files common in preservation workflows (video, high-resolution images, audio masters), processing them at near-disk-speed with real-time progress reporting. It runs on macOS, Linux, and Windows from a single codebase, and installs in under five minutes with no special infrastructure.

---

## Requirements

- macOS, Linux, or Windows 11
- Python 3.10 or later
- **pyyaml** — installed automatically by pip
- **tqdm** (optional) — enables per-file progress bars during hashing

---

## Installation

### macOS (Sequoia 15.x)

Open Terminal (Applications → Utilities → Terminal).

Check your Python version:

    python3 --version

Any version 3.10 or higher is fine. If you get "command not found" or a version below 3.10, install Python from [python.org/downloads](https://www.python.org/downloads/).

Navigate to the unzipped package and install:

    cd ~/Downloads/checksum-tools
    pip3 install --break-system-packages .

For progress bar support:

    pip3 install --break-system-packages ".[progress]"

Verify:

    checksum-tools --version

If you get "command not found," your pip scripts directory may not be on your PATH. Try running `python3 -m checksum_tools.cli --version`. If that works, add the scripts directory to your PATH:

    echo 'export PATH="$HOME/Library/Python/3.13/bin:$PATH"' >> ~/.zshrc
    source ~/.zshrc

Replace `3.13` with your actual Python version (major.minor).

### Linux (Ubuntu 24.04)

Ubuntu 24.04 ships with Python 3.12 and enforces PEP 668. Install with:

    cd checksum-tools
    pip3 install --break-system-packages .

Alternatively, use a virtual environment:

    python3 -m venv /opt/checksum-tools-env
    /opt/checksum-tools-env/bin/pip install .
    sudo ln -s /opt/checksum-tools-env/bin/checksum-tools /usr/local/bin/checksum-tools

### Windows 11

Open PowerShell and check your Python version:

    python --version

If Python is not installed, download it from [python.org/downloads](https://www.python.org/downloads/). During installation, check **"Add python.exe to PATH"**.

Install the package:

    cd ~\Downloads\checksum-tools
    pip install .

For progress bar support:

    pip install ".[progress]"

If `checksum-tools` is not recognized after installation, use:

    python -m checksum_tools.cli --version

### Standalone use (without pip)

On macOS/Linux, copy the package and launcher script directly:

    cp -r checksum_tools /usr/local/lib/checksum-tools/checksum_tools
    cp bin/checksum-tools /usr/local/bin/checksum-tools
    chmod +x /usr/local/bin/checksum-tools

On Windows, use the included batch or PowerShell launcher:

    bin\checksum-tools.bat -a verify -e .md5 -r C:\path\to\files
    .\bin\checksum-tools.ps1 -a verify -e .md5 -r C:\path\to\files

Standalone use requires `pyyaml` to be installed separately (`pip3 install pyyaml`).

### Upgrading

When installing a new version over an existing one, use `--force-reinstall` to ensure all files are replaced:

    pip3 install --break-system-packages . --force-reinstall

### Uninstalling

    pip3 uninstall checksum-tools

On Windows, omit `--break-system-packages` from all commands.

---

## Usage

### Basic syntax

    checksum-tools [OPTIONS] [PATH]

If `PATH` is omitted, the current working directory is used. Both of the following are equivalent:

    checksum-tools -a generate -e .md5 -r /path/to/files

    cd /path/to/files
    checksum-tools -a generate -e .md5 -r

### Generating checksums (sidecar files)

Generate MD5 sidecar files for all files in a directory:

    checksum-tools -a generate -e .md5 /path/to/files

Generate SHA-256 sidecar files recursively:

    checksum-tools -a generate -d sha256 -e .sha256 -r /path/to/files

Generate both MD5 and SHA-256 for only TIFF files:

    checksum-tools -a generate -d md5 -d sha256 -f '*.tif' /path/to/files

### Generating checksums (manifest file)

Generate a single manifest file using default naming (`MD5SUMS`):

    checksum-tools -a generate -e .md5 -r /path/to/files --manifest

Generate a manifest with a custom filename in the target directory:

    checksum-tools -a generate -e .md5 -r --manifest /path/to/files/delivery.md5 /path/to/files

Generate a manifest with a custom filename outside the target directory:

    checksum-tools -a generate -e .md5 -r --manifest /elsewhere/batch-checksums.md5 /path/to/files

The manifest is written only after all files have been hashed. If the process is interrupted mid-way, no partial manifest is left behind.

**Note on argument order**: When using `--manifest` without a filename (default naming), place the target path before the flag. Otherwise argparse may interpret the path as the manifest filename:

    checksum-tools -a generate -e .md5 -r /path/to/files --manifest       ← correct
    checksum-tools -a generate -e .md5 -r --manifest /path/to/files       ← ambiguous

When specifying a manifest filename, there is no ambiguity:

    checksum-tools -a generate -e .md5 -r --manifest batch.md5 /path/to/files   ← correct

### Verifying checksums

Verify MD5 sidecar files:

    checksum-tools -a verify -e .md5 /path/to/files

Verify recursively (searches for all digest types and manifest files):

    checksum-tools -a verify -r /path/to/files

Verify while ignoring hidden and system files:

    checksum-tools -a verify -e .md5 -r --no-hidden /path/to/files

### Logging results

Write a plain-text log of results to a file:

    checksum-tools -a verify -e .md5 -r --log /path/to/verify.log /path/to/files

The log mirrors terminal output with ANSI color codes stripped and progress bars suppressed. Place the log file outside the target directory so it is not included in the pre-scan.

Logging works with both generate and verify, and can be combined with any other flags:

    checksum-tools -a generate -e .md5 -r /path/to/files --manifest --log /path/to/generate.log

---

## Options

| Option | Description |
|--------|-------------|
| `-a {generate,verify}` | Action to perform. Default: `verify`. |
| `-d DIGEST` | Digest type to generate. Can be specified multiple times. Choices: `md5`, `sha1`, `sha256`, `sha384`, `sha512`. Default: `md5`. |
| `-e EXT` | File extension for digest files. Default: `.digest`. Both `-e md5` and `-e .md5` are accepted; the leading dot is added automatically. |
| `-f MASK` | Include only files matching MASK. Can be repeated. Default: `*`. |
| `-x MASK` | Exclude files matching MASK. Can be repeated. |
| `-r, --recursive` | Recurse into subdirectories. |
| `--no-hidden` | Ignore hidden files and directories. On Unix/macOS, this means names starting with a dot. On Windows, this also includes files with the Hidden attribute and common system files (Thumbs.db, desktop.ini, etc.). |
| `--log FILE` | Write a plain-text log of results to FILE. ANSI colors are stripped and progress bars are suppressed. |
| `--manifest [FILE]` | Generate a single manifest file instead of per-file sidecar files. If FILE is specified, the manifest is written to that path. If FILE is omitted, the manifest is named after the digest type (e.g., `MD5SUMS`, `SHA256SUMS`) and placed in the target directory. |
| `-o, --overwrite` | Overwrite existing digest or manifest files. |
| `-n, --no-action` | Dry run — display configuration and exit. |
| `-q, --quiet` | Suppress all output except errors. |
| `-c FILE` | Load configuration from YAML file. Default: `~/.checksum-tools`. |
| `-D, --digest-types` | Show available digest types and exit. |
| `-v, --version` | Show version number and exit. |
| `-h, --help` | Print usage and exit. |

---

## Terminal Output

### Pre-scan summary

Before processing files, checksum-tools scans the target directory and reports what it finds. The summary adapts to the type of digest files present.

**Sidecar mode** (when individual `.md5` files exist alongside content files):

    Found 24 files with matching .md5 files.
    Found 0 .md5 files with no matching file.
    Found 0 files with no matching .md5 file.
    ===============================================================

**Manifest mode** (when a manifest file like `MD5SUMS` or `checksums.md5` is found):

      Manifest: checksums.md5

    Found 12 files listed in manifest.
    ===============================================================

**Mixed mode** (when both sidecars and manifests are present):

      Manifest: MD5SUMS

    Found 8 files with matching .md5 sidecar files.
    Found 12 files listed in manifest.
    Found 2 files with no checksum coverage.
    ===============================================================

### Line-by-line results

Each file is reported as it is processed, in alphabetical order within each directory:

    DONE        /path/to/file.tif             (generate mode)
    PASS        /path/to/file.tif             (verify — match)
    FAIL        /path/to/file.tif             (verify — mismatch)
                expected: a1b2c3d4e5f6...
                actual:   99887766aabb...

### Final summary

Generate mode:

    Generated 24 digest(s).

Generate mode with manifest:

    Wrote MD5SUMS (24 entries)

    Generated 24 digest(s).

Verify mode (all passed):

    Verified 24 checksum(s): 24 passed, 0 failed.

Verify mode (with failures):

    Verified 24 checksum(s): 23 passed, 1 failed.

### Failed file summary

When any checksums fail verification, all failed files are collected and printed together at the very end for quick scanning. This makes it easy to identify failures in large batches without scrolling through thousands of PASS lines:

    Verified 2048 checksum(s): 2046 passed, 2 failed.

    Failed files:
      FAIL  /path/to/corrupted_file_1.tif
      FAIL  /path/to/corrupted_file_2.tif

### Missing checksum report

In verify mode, files without any checksum coverage (no sidecar and not listed in any manifest) are listed at the end. The report is capped at 100 files to avoid overwhelming the terminal — if more than 100 files are missing checksums, the remainder is indicated with a count:

    Files without checksum coverage (5):
      /path/to/missing_0.tif
      /path/to/missing_1.tif
      /path/to/missing_2.tif
      /path/to/missing_3.tif
      /path/to/missing_4.tif

When more than 100 files are uncovered:

    Files without checksum coverage (120):
      /path/to/file_0000.tif
      /path/to/file_0001.tif
      ...
      /path/to/file_0099.tif
      ... and 20 more.

This report helps catch structural problems like missing sidecars, files added after initial checksum generation, or manifests that don't cover the full set.

### Terminal colors

Output is color-coded for quick visual scanning:

| Color | Meaning |
|-------|---------|
| **Green** | PASS, DONE, and the final summary when all checksums match. |
| **Red** | FAIL and the final summary when any checksum does not match. Red only appears when something is wrong. |
| **Yellow** | Warnings: orphan sidecar files, uncovered files, or no digest files found. |

Colors are automatically disabled when output is piped or redirected to a file. Environment variables `NO_COLOR=1` and `FORCE_COLOR=1` can override auto-detection.

### Progress bar

When `tqdm` is installed, a blue per-file progress bar appears while each file is being hashed:

    video_file.mov:  34%|██████████▍       | 1.2G/3.5G [00:12<00:24, 98.2MB/s]

The bar shows the filename, percentage, bytes read, total size, elapsed time, remaining time, and speed. It disappears when the file finishes, replaced by the DONE or PASS/FAIL line. Progress updates are throttled to approximately 4 times per second to minimize terminal overhead on very large files.

For small files the bar flashes by quickly. For large files (video, disk images, high-resolution scans), it provides real-time byte-level progress.

---

## Logging

The `--log` flag writes a complete record of the session to a plain-text file. The log includes the header, pre-scan summary, every DONE/PASS/FAIL line, the final summary, the failed file summary (if any), and the missing checksum report (if any).

ANSI color codes are stripped and tqdm progress bars are suppressed, so the log is clean and readable in any text editor.

    checksum-tools -a verify -e .md5 -r --log verify_20260424.log /path/to/files

Example log contents:

    checksum-tools 2.0.0 — verify
      Target: /Volumes/SMPL_37/project/batch_01

    Found 24 files with matching .md5 files.
    Found 0 .md5 files with no matching file.
    Found 0 files with no matching .md5 file.
    ===============================================================
    PASS        /Volumes/SMPL_37/project/batch_01/img_001.tif
    PASS        /Volumes/SMPL_37/project/batch_01/img_002.tif
    PASS        /Volumes/SMPL_37/project/batch_01/img_003.tif
    ...

    Verified 24 checksum(s): 24 passed, 0 failed.

    Log written: /Volumes/SMPL_37/project/verify_20260424.log

Place the log file outside the target directory to avoid it being included in the pre-scan file count.

---

## Manifest Generation

The `--manifest` flag generates a single manifest file instead of individual sidecar files. This is useful when delivering files to clients who require a consolidated checksum list.

### Default naming

When `--manifest` is used without a filename, the manifest is named after the digest type and placed in the target directory:

    checksum-tools -a generate -e .md5 -r /path/to/files --manifest

| Digest type | Default manifest filename |
|-------------|--------------------------|
| `md5` | `MD5SUMS` |
| `sha1` | `SHA1SUMS` |
| `sha256` | `SHA256SUMS` |
| `sha384` | `SHA384SUMS` |
| `sha512` | `SHA512SUMS` |

These names are the same names that checksum-tools automatically discovers during verification, so a manifest generated with `--manifest` will be verified without any additional configuration.

### Custom naming

When a filename is specified, the manifest is written to that path:

    checksum-tools -a generate -e .md5 -r --manifest delivery.md5 /path/to/files
    checksum-tools -a generate -e .md5 -r --manifest /path/to/files/batch-001.md5 /path/to/files
    checksum-tools -a generate -e .md5 -r --manifest /elsewhere/client-checksums.md5 /path/to/files

A relative filename (e.g., `delivery.md5`) is resolved relative to the current working directory. A full path places the manifest at that exact location.

### Manifest format

Manifests are written in **GNU coreutils format** — the same format used by `md5sum`, `sha256sum`, and compatible with virtually every checksum verification tool on every platform:

    d41d8cd98f00b204e9800998ecf8427e  filename.tif
    a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4  subdir/nested_file.tif

Each line contains the hex digest, two spaces, and the filename. Files in subdirectories are listed with relative paths from the root of the target directory.

### Integrity guarantee

The manifest is written only after all files have been hashed. All entries are collected in memory during processing. If the process is interrupted before completion, no partial manifest file is left behind. This prevents a half-written manifest from being mistaken for a complete one.

### Overwrite protection

If a manifest file already exists, it will not be overwritten unless `-o` is specified:

    checksum-tools -a generate -e .md5 -r -o /path/to/files --manifest

---

## Digest File Formats

checksum-tools can read and verify digest files written by many different tools. Both sidecar files (one per content file) and manifest files (one file listing many checksums) are supported.

### Sidecar files

A sidecar file is named after its content file with a digest extension appended:

    photo.tif           ← content file
    photo.tif.md5       ← sidecar (contains the MD5 hash)

When generating in sidecar mode (the default), checksum-tools writes sidecars in GNU coreutils format (`<hexdigest>  <filename>\n`) for maximum compatibility.

### Manifest files

A manifest file lists checksums for many files in a single file. checksum-tools automatically discovers manifests in each directory by looking for well-known names and digest-extension files that are not sidecars.

Well-known manifest names (case-insensitive): `MD5SUMS`, `SHA256SUMS`, `SHA1SUMS`, `SHA384SUMS`, `SHA512SUMS`, `CHECKSUMS`, `CHECKSUMS.TXT`.

Any `.md5`, `.sha256`, or other digest-extension file that does not have a matching content file (i.e., is not a sidecar) is also treated as a potential manifest.

| Format | Sidecar example | Manifest example |
|--------|-----------------|------------------|
| GNU coreutils | `photo.tif.md5` | `MD5SUMS`, `checksums.md5` |
| BSD tagged | `photo.tif.sha256` | `SHA256SUMS` |
| Windows FastSum | `photo.tif.md5` | `folder.md5` (FastSum /T:R) |

### Supported line formats

Inside any digest file (sidecar or manifest), the following line formats are recognized:

| Format | Example | Source |
|--------|---------|--------|
| GNU text mode | `d41d8cd9...  filename.txt` | md5sum, sha256sum |
| GNU binary mode | `d41d8cd9... *filename.txt` | md5sum -b |
| BSD tagged | `MD5 (filename.txt) = d41d8cd9...` | macOS md5, shasum |
| BSD no-space | `MD5(filename.txt)= d41d8cd9...` | macOS md5 (older) |
| FastSum | `filename.txt D41D8CD9...` | FastSum (Windows) |
| Plain hex | `d41d8cd98f00b204e9800998ecf8427e` | Single-entry sidecar |

Comment lines (starting with `;` or `#`), FastSum metadata headers, uppercase hex, Windows backslash paths, and binary-mode indicators (`*`) are all handled automatically.

---

## Integrity Verification

In verify mode, checksum-tools searches for digest information in three places for every content file:

- **Sidecar files** — named after the content file (e.g., `photo.tif.md5`, `photo.tif.sha256`).
- **Manifest files in the same directory** — shared digest files like `MD5SUMS` or `checksums.md5`.
- **Root-level manifests with relative paths** — a manifest at the root of the target directory containing entries like `subdir/photo.tif`, for hierarchical manifests generated with `--manifest -r`.

For each digest found, the file is re-hashed and compared. Results are deduplicated by digest type: if the same MD5 appears in both a sidecar and a manifest, it is only verified once. If a sidecar has MD5 and a manifest has SHA-256, both are verified independently.

| Result | Meaning |
|--------|---------|
| **PASS** | Computed digest matches the stored digest. The file is intact. |
| **FAIL** | Computed digest does not match. The file may be corrupted or was modified after the digest was created. |

Files without any digest file are reported in the missing checksum report at the end (up to 100 files).

---

## Special Characters in Filenames

checksum-tools correctly handles filenames containing any of the following, in both sidecar and manifest modes:

| Category | Examples |
|----------|----------|
| Whitespace | spaces, tabs, leading/trailing spaces |
| Punctuation | `( ) [ ] { } & # \| ^ ~ , ; ! ? @ $ %` |
| Quotes | single `'` double `"` backtick `` ` `` |
| Special prefixes | `*` (asterisk), `-` (dash), `.` (hidden files) |
| Unicode / accented | café_résumé, über_straße, naïve |
| CJK | 日本語, 中文文件 |
| Cyrillic / Greek | файл_данных, αβγδ |
| Emoji | 🎬 🎵 |

Filenames that literally start with `*` (e.g., `*bb164gn8864_00008.mov`) are handled correctly and not confused with the GNU binary-mode indicator.

---

## Hidden Files

By default, all files are processed, including hidden files and system files. The `--no-hidden` flag excludes hidden files and directories from all operations: content matching, digest generation, manifest discovery, and the pre-scan summary.

On all platforms, names starting with `.` are considered hidden (e.g., `.DS_Store`, `.gitignore`, `.Spotlight-V100`).

On Windows, the following are also considered hidden:

- Files with the Windows Hidden file attribute set
- Common system files: `Thumbs.db`, `desktop.ini`, `ehthumbs.db`, `ehthumbs_vista.db`, `$RECYCLE.BIN`, `System Volume Information`

Using `--no-hidden` also prevents files like `.DS_Store.md5` from being misidentified as manifest files.

---

## Configuration File

Default settings can be stored in a YAML file at `~/.checksum-tools`. Command-line arguments override file settings.

    # ~/.checksum-tools
    action: verify
    digest: md5
    extension: .md5
    filemask: '*'
    recursive: false
    overwrite: false
    quiet: false

---

## Performance

checksum-tools is optimized for the large media files common in preservation workflows:

- **4 MB read buffer**: Files are read in 4 MB chunks, minimizing system call overhead. A 200 GB file requires approximately 51,000 read operations rather than 25.6 million at the previous 8 KB buffer size.
- **Throttled progress updates**: When the progress bar is enabled, the display updates approximately 4 times per second rather than on every chunk read. This reduces terminal I/O overhead, which is especially noticeable over SSH connections.

These optimizations result in throughput near the maximum speed of the underlying storage device.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| **0** | Success — all files processed without errors. |
| **1** | Failure — verification mismatch, missing path, or invalid configuration. |

---

## Package Structure

    checksum-tools/
    ├── pyproject.toml              Package metadata & dependencies
    ├── README.md                   Markdown readme
    ├── INSTALL_MACOS.md            macOS installation guide
    ├── INSTALL_WINDOWS.md          Windows installation guide
    ├── bin/
    │   ├── checksum-tools          Unix launcher script
    │   ├── checksum-tools.bat      Windows Command Prompt launcher
    │   └── checksum-tools.ps1      Windows PowerShell launcher
    ├── checksum_tools/             Python package
    │   ├── __init__.py             Version & exports
    │   ├── __main__.py             Allows `python -m checksum_tools`
    │   ├── cli.py                  Command-line interface
    │   ├── config.py               YAML config loader
    │   └── local.py                Digest engine (generate & verify)
    └── tests/
        └── test_checksum_tools.py  pytest test suite

---

## Supported Digest Algorithms

| Algorithm | Hash length | Use case |
|-----------|------------|----------|
| MD5 | 128-bit (32 hex chars) | Fast, widely used for integrity checking. Not cryptographically secure but sufficient for corruption detection. |
| SHA-1 | 160-bit (40 hex chars) | Legacy. Stronger than MD5 but deprecated for security use. |
| SHA-256 | 256-bit (64 hex chars) | Recommended for new workflows. Strong integrity guarantee. |
| SHA-384 | 384-bit (96 hex chars) | Truncated SHA-512. Rarely used in preservation. |
| SHA-512 | 512-bit (128 hex chars) | Maximum strength. Slightly slower than SHA-256 on 32-bit systems, comparable on 64-bit. |

---

## Cross-Platform Compatibility

checksum-tools is a single codebase that runs on macOS, Linux, and Windows. Platform-specific behavior is handled automatically:

- **File encoding**: All file I/O uses explicit UTF-8 encoding. On Windows, where the default encoding is cp1252, this prevents errors when reading digest files containing non-ASCII filenames. Malformed bytes are replaced rather than causing a crash.
- **Line endings**: Generated digest and manifest files always use Unix line endings (`\n`) regardless of the operating system, ensuring cross-platform compatibility.
- **Path separators**: Windows backslash paths inside digest files (e.g., `subdir\file.tif`) are normalized to forward slashes during comparison.
- **Terminal colors**: ANSI escape codes are enabled automatically on Windows via the `SetConsoleMode` API. Colors work in Windows Terminal (default in Windows 11) and in PowerShell.
- **Hidden files**: The `--no-hidden` flag respects both Unix dot-prefix conventions and Windows file attributes.

---

## Notes

- **Overwrite protection**: By default, existing digest and manifest files are not overwritten during generation. Use `-o` to force regeneration.
- **Manifest caching**: When verifying against manifest files (e.g., a 500-entry MD5SUMS), the manifest is parsed once per directory and cached in memory.
- **Sidecar priority**: When both a sidecar and a manifest entry exist for the same file and digest type, the sidecar takes priority.
- **Extension normalization**: Both `-e md5` and `-e .md5` are accepted. The leading dot is added automatically.
- **Filename normalization**: Windows backslash paths are converted to forward slashes. GNU binary-mode indicators (`*`) are stripped during comparison. Filenames that literally begin with `*` are handled correctly.
- **Progress bars**: Requires `tqdm` (`pip install tqdm`). When installed, a blue byte-level progress bar is shown for each file during hashing. Without `tqdm`, output falls back to plain DONE/PASS/FAIL lines. Use `-q` to suppress all output.
- **Log placement**: Place log files outside the target directory to avoid them being included in the pre-scan file count.
- **Manifest vs. sidecar**: Use sidecar mode (default) when files may move independently — each file travels with its own checksum. Use `--manifest` when delivering a complete set of files to a client who expects a consolidated checksum list.
- **File processing order**: Files are always processed in alphabetical order within each directory, making it easy to track progress or find where a stopped process left off.
