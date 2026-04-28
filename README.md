# checksum-tools (Python)

Generate or verify checksums for a set of files.

This is a Python port of the [sul-dlss/checksum-tools](https://github.com/sul-dlss/checksum-tools) Ruby gem, originally used by the Stanford Media Preservation Lab (SMPL).

## Installation

### Option 1: pip install (recommended)

```bash
pip install checksum-tools
```

For progress bar support:

```bash
pip install checksum-tools[progress]
```

### Option 2: Standalone script

Copy the package and launcher script directly:

```bash
# Copy the package
cp -r checksum_tools /usr/local/lib/checksum-tools/checksum_tools

# Copy the launcher (already has #!/usr/bin/env python3 shebang)
cp bin/checksum-tools /usr/local/bin/checksum-tools
chmod +x /usr/local/bin/checksum-tools
```

**Requires:** Python 3.10+ and the `pyyaml` package (`pip install pyyaml`).

## Synopsis

```
Usage: checksum-tools [options] [path]

  -a, --action ACTION        Action to perform: generate or verify (default: verify)
  -c, --config FILE          Load configuration from FILE (default: ~/.checksum-tools)
  -d, --digest DIGEST        Digest type to generate (can be repeated). Default: md5
  -e, --extension EXT        File extension for digest files (default: .digest)
  -f, --filemask MASK        Include files matching MASK (can be repeated; default: *)
  -n, --no-action            Dry run — display configuration and exit
  -o, --overwrite            Overwrite existing digest files
  -q, --quiet                Hide the progress bar
  -r, --recursive            Recurse into subdirectories
  -x, --exclude MASK         Exclude files matching MASK (can be repeated)
  -D, --digest-types         Show available digest types and exit
  -v, --version              Print version and exit
  -h, --help                 Show help message
```

## Description

checksum-tools is a dual-purpose tool to **generate** or **verify** checksums of various types for a set of files in a given directory.

### Generate Mode

```bash
# Generate MD5 checksums for all files in a directory
checksum-tools -a generate /path/to/files

# Generate SHA-256 checksums, recursively
checksum-tools -a generate -d sha256 -r /path/to/files

# Generate both MD5 and SHA-256 checksums for TIFF files
checksum-tools -a generate -d md5 -d sha256 -f '*.tif' /path/to/files

# Use a custom extension
checksum-tools -a generate -d md5 -e .md5 /path/to/files
```

In generate mode, a digest file is created alongside each content file. The digest file uses the standard `<hexdigest>  <filename>` format compatible with `md5sum`, `sha256sum`, etc.

### Verify Mode

```bash
# Verify all checksums in a directory (default action)
checksum-tools /path/to/files

# Verify recursively
checksum-tools -a verify -r /path/to/files
```

In verify mode, existing digest files are found and their stored checksums are compared against freshly computed digests. PASS/FAIL results are printed to stdout.

**Supported digest file formats:**

checksum-tools can verify against both **sidecar files** (one per content file) and **manifest files** (one file listing many checksums):

| Format | Sidecar example | Manifest example |
|---|---|---|
| GNU coreutils | `photo.tif.md5` | `MD5SUMS`, `checksums.md5` |
| BSD tagged | `photo.tif.sha256` | `SHA256SUMS` |
| Windows FastSum | `photo.tif.md5` | `folder.md5` (FastSum /T:R or /T:F) |

Manifest files like `MD5SUMS`, `SHA256SUMS`, `checksums.md5`, etc. are automatically discovered and parsed. Comment lines (`;` or `#`) and FastSum metadata headers are handled gracefully. Uppercase hex, Windows backslash paths, and binary-mode indicators (`*`) are all normalized.

## Configuration File

Default options can be stored in `~/.checksum-tools` (YAML format):

```yaml
action: generate
digest: sha256
extension: .digest
filemask: "*.tif"
recursive: true
quiet: false
```

Command-line options override config file values.

## Supported Digest Types

- `md5`
- `sha1`
- `sha256`
- `sha384`
- `sha512`

## Python API

```python
from checksum_tools import Config, LocalDigester

config = Config(
    action="generate",
    digests=["sha256"],
    path="/path/to/files",
    recursive=True,
)

digester = LocalDigester(config)

# Generate
for result in digester.generate():
    print(f"{result.digest_type}: {result.filepath} -> {result.hexdigest}")

# Verify
config.action = "verify"
for result in digester.verify():
    print(f"{result.status} {result.digest_type}: {result.filepath}")
```

## Development

```bash
pip install -e .[dev]
pytest
```

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
