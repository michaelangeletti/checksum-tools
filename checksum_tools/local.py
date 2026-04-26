"""
Local file digester for checksum-tools.

Handles generating and verifying checksums for files on the local filesystem.
Mirrors the ChecksumTools::Local class from the Ruby gem.
"""

import hashlib
import fnmatch
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Generator, Optional

from checksum_tools.config import Config, SUPPORTED_DIGESTS


# Read files in 4 MB chunks (optimized for large media files)
BUFFER_SIZE = 4 * 1024 * 1024


def _is_hidden(name: str, full_path: str = "") -> bool:
    """Check if a file or directory is hidden (cross-platform).

    On Unix/macOS: names starting with '.' are hidden.
    On Windows: files with the FILE_ATTRIBUTE_HIDDEN flag are hidden,
    plus common system files (Thumbs.db, desktop.ini, etc.).
    On both platforms, dot-prefixed names are considered hidden.
    """
    # Dot-prefix is hidden on all platforms
    if name.startswith("."):
        return True

    if sys.platform == "win32":
        # Check Windows hidden attribute if we have a full path
        if full_path:
            try:
                import ctypes
                attrs = ctypes.windll.kernel32.GetFileAttributesW(full_path)
                # FILE_ATTRIBUTE_HIDDEN = 0x2
                if attrs != -1 and (attrs & 0x2):
                    return True
            except Exception:
                pass

        # Common Windows hidden/system files
        _WIN_HIDDEN_NAMES = {
            "thumbs.db", "desktop.ini", "ehthumbs.db",
            "ehthumbs_vista.db", "$recycle.bin", "system volume information",
        }
        if name.lower() in _WIN_HIDDEN_NAMES:
            return True

    return False

# Well-known manifest filenames (uppercase for case-insensitive matching)
MANIFEST_NAMES = {
    "MD5SUMS", "MD5SUM", "SHA1SUMS", "SHA1SUM",
    "SHA256SUMS", "SHA256SUM", "SHA384SUMS", "SHA384SUM",
    "SHA512SUMS", "SHA512SUM",
    "CHECKSUMS", "CHECKSUMS.TXT",
}

# Map well-known manifest names to digest types
_MANIFEST_NAME_TO_TYPE = {
    "MD5SUMS": "md5", "MD5SUM": "md5",
    "SHA1SUMS": "sha1", "SHA1SUM": "sha1",
    "SHA256SUMS": "sha256", "SHA256SUM": "sha256",
    "SHA384SUMS": "sha384", "SHA384SUM": "sha384",
    "SHA512SUMS": "sha512", "SHA512SUM": "sha512",
}


@dataclass
class DigestResult:
    """Result of a digest operation on a single file."""

    filepath: str
    digest_type: str
    hexdigest: str
    digest_filepath: Optional[str] = None


@dataclass
class VerifyResult:
    """Result of a verification operation on a single file."""

    filepath: str
    digest_type: str
    expected: str
    actual: str
    passed: bool = field(init=False)

    def __post_init__(self):
        self.passed = self.expected.lower().strip() == self.actual.lower().strip()

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


class LocalDigester:
    """Generate or verify checksums for local files.

    This is the main workhorse class. It walks a directory, matches files
    against include/exclude masks, and either generates digest files or
    verifies existing ones.

    Args:
        config: A Config instance controlling behavior.
        progress_callback: Optional callable invoked with (bytes_processed, total_bytes)
                           during file hashing for progress reporting.
    """

    def __init__(
        self,
        config: Config,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        on_file_start: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.progress_callback = progress_callback
        self.on_file_start = on_file_start
        # Cache parsed manifest files per directory to avoid re-reading
        # Key: directory path, Value: dict of {manifest_path: parsed_entries}
        # where parsed_entries is a dict {basename: [(digest_type, hexdigest), ...]}
        self._manifest_cache: dict[str, dict[str, dict[str, list[tuple[str, str]]]]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> Generator[DigestResult, None, None]:
        """Generate digest files for all matched content files.

        In manifest mode (config.manifest=True), files are hashed but no
        sidecar files are written — the caller collects results and writes
        a single manifest.

        Yields:
            DigestResult for each (file, digest_type) pair processed.
        """
        manifest_mode = getattr(self.config, "manifest", False)

        for filepath in self._matched_files():
            for digest_type in self.config.digests:
                if not manifest_mode:
                    digest_path = self._digest_filepath(filepath, digest_type)
                    if os.path.exists(digest_path) and not self.config.overwrite:
                        continue
                else:
                    digest_path = None

                if self.on_file_start:
                    self.on_file_start(filepath)

                hexdigest = self._digest_file(filepath, digest_type)

                if not manifest_mode and not self.config.dry_run:
                    self._write_digest_file(digest_path, hexdigest, filepath)

                yield DigestResult(
                    filepath=filepath,
                    digest_type=digest_type,
                    hexdigest=hexdigest,
                    digest_filepath=digest_path,
                )

    def verify(self) -> Generator[VerifyResult, None, None]:
        """Verify checksums from existing digest files.

        Searches for digest files alongside content files and checks
        that the stored digest matches a freshly computed one.

        Yields:
            VerifyResult for each (file, digest_type) pair verified.
        """
        for filepath in self._matched_files():
            for digest_file_path, digest_type, expected_hex in self._find_digest_files(filepath):
                if self.on_file_start:
                    self.on_file_start(filepath)
                actual_hex = self._digest_file(filepath, digest_type)
                yield VerifyResult(
                    filepath=filepath,
                    digest_type=digest_type,
                    expected=expected_hex,
                    actual=actual_hex,
                )

    @staticmethod
    def available_digest_types() -> list[str]:
        """Return the list of supported digest algorithm names."""
        return list(SUPPORTED_DIGESTS)

    # ------------------------------------------------------------------
    # File matching
    # ------------------------------------------------------------------

    def _matched_files(self) -> Generator[str, None, None]:
        """Yield absolute paths of content files matching the configured masks.

        Excludes digest files themselves and any files matching exclude masks.
        """
        root = os.path.abspath(self.config.path)
        no_hidden = self.config.no_hidden

        if self.config.recursive:
            walker = os.walk(root)
        else:
            # Non-recursive: only the top-level directory
            try:
                entries = os.listdir(root)
            except OSError:
                return
            walker = [(root, [], [e for e in entries if os.path.isfile(os.path.join(root, e))])]

        for dirpath, dirnames, filenames in walker:
            # Skip hidden directories when --no-hidden is set
            if no_hidden:
                dirnames[:] = [d for d in dirnames if not _is_hidden(d, os.path.join(dirpath, d))]

            for filename in sorted(filenames):
                # Skip hidden files when --no-hidden is set
                if no_hidden and _is_hidden(filename, os.path.join(dirpath, filename)):
                    continue

                filepath = os.path.join(dirpath, filename)

                # Skip digest files
                if self._is_digest_file(filename):
                    continue

                # Check include masks
                if not self._matches_any(filename, self.config.filemasks):
                    continue

                # Check exclude masks
                if self.config.excludes and self._matches_any(filename, self.config.excludes):
                    continue

                yield filepath

    @staticmethod
    def _matches_any(filename: str, masks: list[str]) -> bool:
        """Check if a filename matches any of the given glob masks."""
        return any(fnmatch.fnmatch(filename, mask) for mask in masks)

    def _is_digest_file(self, filename: str) -> bool:
        """Check if a filename looks like a digest file (sidecar or manifest).

        Recognizes:
            - Sidecar files: photo.tif.md5, photo.tif.sha256, photo.tif.digest
            - Well-known manifest names: MD5SUMS, SHA256SUMS, checksums.md5, etc.
        """
        ext = self.config.extension
        if filename.endswith(ext):
            return True
        # Algorithm-specific extensions (.md5, .sha1, .sha256, etc.)
        for dtype in SUPPORTED_DIGESTS:
            if filename.endswith(f".{dtype}"):
                return True
        # Well-known manifest filenames (case-insensitive)
        if filename.upper() in MANIFEST_NAMES:
            return True
        return False

    # ------------------------------------------------------------------
    # Digest computation
    # ------------------------------------------------------------------

    def _digest_file(self, filepath: str, digest_type: str) -> str:
        """Compute the hex digest of a file.

        Args:
            filepath: Path to the file to hash.
            digest_type: Algorithm name (e.g. 'md5', 'sha256').

        Returns:
            Lowercase hex digest string.
        """
        hasher = hashlib.new(digest_type)
        file_size = os.path.getsize(filepath)
        bytes_read = 0
        # Throttle progress updates: at most ~4 per second to avoid
        # terminal I/O overhead on very large files (200 GB+)
        last_progress_time = 0.0

        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(BUFFER_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
                bytes_read += len(chunk)
                if self.progress_callback:
                    now = time.monotonic()
                    if now - last_progress_time >= 0.25 or bytes_read >= file_size:
                        self.progress_callback(bytes_read, file_size)
                        last_progress_time = now

        return hasher.hexdigest()

    # ------------------------------------------------------------------
    # Digest file I/O
    # ------------------------------------------------------------------

    def _digest_filepath(self, filepath: str, digest_type: str) -> str:
        """Build the path for a digest file.

        The Ruby gem uses a configurable extension (default: .digest).
        For multi-digest support, include the digest type in the extension
        when the configured extension is the generic '.digest'.

        Examples:
            photo.tif  ->  photo.tif.md5      (if extension is .md5)
            photo.tif  ->  photo.tif.digest    (if extension is .digest and one digest)
            photo.tif  ->  photo.tif.sha256    (if extension is .sha256)
        """
        ext = self.config.extension
        # If using the generic '.digest' extension and multiple digest types,
        # append the digest type to differentiate
        if ext == ".digest" and len(self.config.digests) > 1:
            return f"{filepath}.{digest_type}"
        return f"{filepath}{ext}"

    @staticmethod
    def _write_digest_file(digest_path: str, hexdigest: str, source_path: str) -> None:
        """Write a digest file in the standard format: '<hexdigest>  <filename>'.

        This format is compatible with md5sum/sha256sum tools.
        """
        filename = os.path.basename(source_path)
        with open(digest_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"{hexdigest}  {filename}\n")

    def _find_digest_files(
        self, filepath: str
    ) -> Generator[tuple[str, str, str], None, None]:
        """Find digest entries associated with a content file.

        Searches in two places:
            1. **Sidecar files**: e.g. photo.tif.md5, photo.tif.sha256
            2. **Manifest files**: e.g. MD5SUMS, checksums.md5, or any
               digest-extension file in the same directory that is not a
               sidecar and contains multi-file entries.

        Handles digest files created by many tools including:
            - GNU coreutils (md5sum, sha256sum, etc.)
            - BSD md5/shasum (tagged format)
            - Windows FastSum (filename-first format, /T:R and /T:F modes)
            - md5summer and similar Windows tools

        Yields:
            Tuples of (digest_file_path, digest_type, expected_hex).
        """
        source_basename = os.path.basename(filepath)
        source_dir = os.path.dirname(filepath)

        # Track which digest_types we've already yielded to avoid duplicates
        # when the same entry exists in both a sidecar and a manifest
        seen: set[str] = set()

        # --- Pass 1: Sidecar files (named after the content file) ---
        ext_path = f"{filepath}{self.config.extension}"
        if os.path.isfile(ext_path):
            digest_type, hexdigest = self._read_digest_file(ext_path, filepath)
            if digest_type and hexdigest:
                seen.add(digest_type)
                yield (ext_path, digest_type, hexdigest)

        for dtype in SUPPORTED_DIGESTS:
            candidate = f"{filepath}.{dtype}"
            if os.path.isfile(candidate) and candidate != ext_path:
                _, hexdigest = self._read_digest_file(candidate, filepath, assumed_type=dtype)
                if hexdigest:
                    seen.add(dtype)
                    yield (candidate, dtype, hexdigest)

        # --- Pass 2: Manifest files in the same directory ---
        manifests = self._get_manifests_for_dir(source_dir)
        normalized_basename = _normalize_filename(source_basename)
        for manifest_path, entries in manifests.items():
            if normalized_basename in entries:
                for digest_type, hexdigest in entries[normalized_basename]:
                    if digest_type not in seen:
                        seen.add(digest_type)
                        yield (manifest_path, digest_type, hexdigest)

        # --- Pass 3: Root-level manifests (for hierarchical manifests with relative paths) ---
        root_dir = os.path.abspath(self.config.path)
        abs_source_dir = os.path.abspath(source_dir)
        if abs_source_dir != root_dir:
            root_manifests = self._get_manifests_for_dir(root_dir)
            # Build the relative path from root to this file
            rel_path = os.path.normpath(os.path.relpath(os.path.abspath(filepath), root_dir))
            for manifest_path, entries in root_manifests.items():
                if rel_path in entries:
                    for digest_type, hexdigest in entries[rel_path]:
                        if digest_type not in seen:
                            seen.add(digest_type)
                            yield (manifest_path, digest_type, hexdigest)

    # ------------------------------------------------------------------
    # Manifest file discovery and parsing
    # ------------------------------------------------------------------

    def _get_manifests_for_dir(
        self, dirpath: str
    ) -> dict[str, dict[str, list[tuple[str, str]]]]:
        """Get parsed manifest files for a directory (with caching).

        A manifest is a digest file that contains entries for multiple
        content files — as opposed to a sidecar file which is named after
        a single content file.

        Returns:
            Dict mapping manifest_path -> {basename: [(digest_type, hex), ...]}
        """
        dirpath = os.path.abspath(dirpath)
        if dirpath in self._manifest_cache:
            return self._manifest_cache[dirpath]

        manifests: dict[str, dict[str, list[tuple[str, str]]]] = {}

        try:
            dir_entries = os.listdir(dirpath)
        except OSError:
            self._manifest_cache[dirpath] = manifests
            return manifests

        for entry in sorted(dir_entries):
            entry_path = os.path.join(dirpath, entry)
            if not os.path.isfile(entry_path):
                continue

            # Skip hidden files when --no-hidden is set
            if self.config.no_hidden and _is_hidden(entry, entry_path):
                continue

            assumed_type = self._classify_as_manifest(entry, dirpath)
            if assumed_type is _NOT_A_DIGEST:
                continue

            parsed = self._parse_manifest(entry_path, assumed_type)
            if parsed:
                manifests[entry_path] = parsed

        self._manifest_cache[dirpath] = manifests
        return manifests

    def _classify_as_manifest(
        self, filename: str, dirpath: str
    ) -> Optional[str]:
        """Determine if a file is a manifest (not a sidecar).

        A file is a manifest if:
            1. It has a well-known manifest name (MD5SUMS, SHA256SUMS, etc.)
            2. It has a digest extension (.md5, .sha256) but stripping that
               extension does NOT give an existing content file (i.e., it's
               not a sidecar like photo.tif.md5)

        Returns:
            The assumed digest type (e.g. 'md5') or None if unknown but
            still a manifest. Returns the sentinel _NOT_A_DIGEST if the
            file should be skipped entirely.
        """
        # Check well-known manifest names (case-insensitive)
        upper = filename.upper()
        if upper in _MANIFEST_NAME_TO_TYPE:
            return _MANIFEST_NAME_TO_TYPE[upper]
        if upper in MANIFEST_NAMES:
            return None  # Manifest, but type must be inferred per-line

        # Check digest extensions
        for dtype in SUPPORTED_DIGESTS:
            ext = f".{dtype}"
            if filename.lower().endswith(ext):
                base = filename[: -len(ext)]
                if base and os.path.isfile(os.path.join(dirpath, base)):
                    return _NOT_A_DIGEST  # It's a sidecar, skip
                return dtype  # Manifest

        # Check the configured extension
        cfg_ext = self.config.extension
        if filename.endswith(cfg_ext):
            base = filename[: -len(cfg_ext)]
            if base and os.path.isfile(os.path.join(dirpath, base)):
                return _NOT_A_DIGEST  # sidecar
            return None  # Manifest, type unknown

        return _NOT_A_DIGEST  # Not a digest file at all

    def _parse_manifest(
        self, manifest_path: str, assumed_type: Optional[str] = None
    ) -> dict[str, list[tuple[str, str]]]:
        """Parse a manifest file containing entries for multiple files.

        Supports GNU, BSD, and FastSum formats (same as sidecar parsing).

        Entries are stored under both the basename and the normalized
        relative path (if the entry includes a path), so hierarchical
        manifests generated with --manifest -r can be verified.

        Returns:
            Dict mapping key -> [(digest_type, hexdigest), ...]
            where key may be a basename or a relative path.
        """
        try:
            with open(manifest_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            return {}

        entries: dict[str, list[tuple[str, str]]] = {}

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue

            result = _parse_manifest_line(line)
            if not result:
                continue

            raw_filename, hexdigest, detected_type = result
            basename = _normalize_filename(raw_filename)

            digest_type = detected_type or assumed_type
            if not digest_type:
                digest_type = _type_from_hex_length(len(hexdigest))
            if not digest_type:
                continue

            hexdigest = hexdigest.lower()
            entry = (digest_type, hexdigest)

            # Store under basename (for flat lookups)
            if basename not in entries:
                entries[basename] = []
            entries[basename].append(entry)

            # Also store under the normalized relative path (for hierarchical lookups)
            rel_key = raw_filename.lstrip("*").replace("\\", "/")
            if rel_key != basename:
                norm_rel = os.path.normpath(rel_key)
                if norm_rel not in entries:
                    entries[norm_rel] = []
                entries[norm_rel].append(entry)

        return entries

    def _read_digest_file(
        self,
        digest_path: str,
        source_path: str,
        assumed_type: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """Read and parse a digest file.

        Supports many common formats:

        1. GNU coreutils (md5sum/sha256sum):
               <hexdigest>  <filename>        (text mode)
               <hexdigest> *<filename>         (binary mode)

        2. BSD tagged format (md5/shasum on macOS/BSD):
               MD5 (<filename>) = <hexdigest>
               SHA256 (<filename>) = <hexdigest>

        3. Windows FastSum format (filename first, hash second):
               <filename> <HEXDIGEST>
           FastSum files may also contain:
               - Comment lines starting with ';'
               - Metadata comments: ;Date=..., ;Host=..., ;User=..., ;Root=...
               - Uppercase hex digests

        4. Plain hex digest (single file, no filename):
               <hexdigest>

        5. Multi-line digest files with entries for many files
           (only the line matching our source file is used).

        Args:
            digest_path: Path to the digest file.
            source_path: Path to the source content file.
            assumed_type: If known, the digest type.

        Returns:
            Tuple of (digest_type, hexdigest) or (None, None) on failure.
        """
        try:
            with open(digest_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read().strip()
        except OSError:
            return (None, None)

        if not content:
            return (None, None)

        lines = content.splitlines()
        source_basename = os.path.basename(source_path)

        hexdigest = None
        detected_type = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip comment lines (FastSum uses ';' as comment prefix)
            if line.startswith(";") or line.startswith("#"):
                continue

            # --- Format 2: BSD tagged ---
            # e.g. "MD5 (filename.txt) = d41d8cd9..."
            #      "SHA256 (filename.txt) = e3b0c442..."
            bsd_result = _parse_bsd_tagged(line, source_basename)
            if bsd_result:
                detected_type, hexdigest = bsd_result
                break

            # --- Format 1: GNU coreutils ---
            # e.g. "d41d8cd9...  filename.txt" or "d41d8cd9... *filename.txt"
            gnu_result = _parse_gnu_format(line, source_basename)
            if gnu_result:
                hexdigest = gnu_result
                break

            # --- Format 3: FastSum (filename first, hash second) ---
            # e.g. "filename.txt D41D8CD98F00B204E9800998ECF8427E"
            fastsum_result = _parse_fastsum_format(line, source_basename)
            if fastsum_result:
                hexdigest = fastsum_result
                break

        # If no filename-matched line was found, try plain hex (single-entry files)
        if not hexdigest:
            for line in lines:
                line = line.strip()
                if not line or line.startswith(";") or line.startswith("#"):
                    continue
                if _is_hex(line):
                    hexdigest = line
                    break

        if not hexdigest:
            return (None, None)

        # Normalize to lowercase
        hexdigest = hexdigest.lower()

        # Determine digest type
        digest_type = detected_type or assumed_type
        if not digest_type:
            # Try to infer from the digest file extension
            _, ext = os.path.splitext(digest_path)
            ext_name = ext.lstrip(".").lower()
            if ext_name in SUPPORTED_DIGESTS:
                digest_type = ext_name
            else:
                # Infer from hex length
                digest_type = _type_from_hex_length(len(hexdigest))

        return (digest_type, hexdigest)


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------

import re

# Sentinel value: file is not a digest file at all
_NOT_A_DIGEST = "__NOT_A_DIGEST__"

# BSD tagged format regex: "MD5 (filename) = hexdigest" or "MD5(filename)= hexdigest"
_BSD_RE = re.compile(
    r"^(MD5|SHA1|SHA256|SHA384|SHA512)\s*\((.+)\)\s*=\s*([0-9a-fA-F]+)$"
)

# Map BSD algorithm names to our standard names
_BSD_ALGO_MAP = {
    "MD5": "md5",
    "SHA1": "sha1",
    "SHA256": "sha256",
    "SHA384": "sha384",
    "SHA512": "sha512",
}


def _is_hex(s: str) -> bool:
    """Check if a string is a valid hexadecimal digest."""
    try:
        int(s, 16)
        return len(s) > 0 and len(s) % 2 == 0
    except ValueError:
        return False


def _type_from_hex_length(length: int) -> Optional[str]:
    """Infer digest type from the length of a hex string."""
    mapping = {
        32: "md5",
        40: "sha1",
        64: "sha256",
        96: "sha384",
        128: "sha512",
    }
    return mapping.get(length)


def _normalize_filename(name: str) -> str:
    """Normalize a filename for comparison.

    Strips leading path characters, normalizes path separators,
    and removes binary-mode indicators.
    """
    # Strip binary mode flag (GNU md5sum uses '*' prefix)
    name = name.lstrip("*")
    # Normalize Windows backslashes to forward slashes
    name = name.replace("\\", "/")
    # Take only the basename for comparison
    return os.path.basename(name)


def _parse_bsd_tagged(line: str, source_basename: str) -> Optional[tuple[str, str]]:
    """Try to parse a BSD tagged format line.

    Format: 'MD5 (filename) = hexdigest'

    Returns:
        Tuple of (digest_type, hexdigest) if matched, else None.
    """
    m = _BSD_RE.match(line)
    if not m:
        return None

    algo = m.group(1).upper()
    filename = m.group(2).strip()
    hexdigest = m.group(3).strip()

    if _normalize_filename(filename) == _normalize_filename(source_basename):
        digest_type = _BSD_ALGO_MAP.get(algo)
        if digest_type:
            return (digest_type, hexdigest)

    return None


def _parse_gnu_format(line: str, source_basename: str) -> Optional[str]:
    """Try to parse a GNU coreutils format line.

    Formats:
        '<hexdigest>  <filename>'    (text mode, double space)
        '<hexdigest> *<filename>'    (binary mode)
        '<hexdigest> <filename>'     (single space, some tools)

    Returns:
        The hexdigest string if matched, else None.
    """
    # Try double-space first (standard GNU), then single space
    for sep in ["  ", " "]:
        if sep in line:
            parts = line.split(sep, 1)
            candidate_hex = parts[0].strip()
            # Only strip trailing whitespace — leading spaces may be part of filename
            candidate_name = parts[1].rstrip()

            if _is_hex(candidate_hex):
                if _normalize_filename(candidate_name) == _normalize_filename(source_basename):
                    return candidate_hex

    return None


def _parse_fastsum_format(line: str, source_basename: str) -> Optional[str]:
    """Try to parse a FastSum format line (filename first, hash second).

    Format: '<filename> <HEXDIGEST>'

    FastSum outputs the filename first, followed by a space, then the
    uppercase hex digest. This is the reverse of GNU format.

    We need to be careful here to avoid false positives, so we verify:
        1. The last token looks like a valid hex digest
        2. The preceding text matches our source filename

    Returns:
        The hexdigest string if matched, else None.
    """
    # Split from the right to handle filenames with spaces
    # The hash is always the last whitespace-separated token
    parts = line.rsplit(None, 1)
    if len(parts) != 2:
        return None

    candidate_name = parts[0].rstrip()
    candidate_hex = parts[1].strip()

    if not _is_hex(candidate_hex):
        return None

    # Verify the hex length corresponds to a known digest type
    if _type_from_hex_length(len(candidate_hex)) is None:
        return None

    if _normalize_filename(candidate_name) == _normalize_filename(source_basename):
        return candidate_hex

    return None


def _parse_manifest_line(line: str) -> Optional[tuple[str, str, Optional[str]]]:
    """Parse a single line from a manifest file, extracting filename and digest.

    Unlike the sidecar parsers (which match against a known filename), this
    function extracts whatever filename and hex digest it finds on the line,
    regardless of which file we're looking for.

    Returns:
        Tuple of (filename, hexdigest, detected_type) or None.
        detected_type is set for BSD format (where the algo is explicit),
        and None for GNU/FastSum (where the type must be inferred).
    """
    # --- BSD tagged format ---
    m = _BSD_RE.match(line)
    if m:
        algo = m.group(1).upper()
        filename = m.group(2).strip()
        hexdigest = m.group(3).strip()
        digest_type = _BSD_ALGO_MAP.get(algo)
        return (filename, hexdigest, digest_type)

    # --- GNU coreutils format: '<hexdigest>  <filename>' ---
    for sep in ["  ", " "]:
        if sep in line:
            parts = line.split(sep, 1)
            candidate_hex = parts[0].strip()
            candidate_name = parts[1].rstrip()
            if _is_hex(candidate_hex) and _type_from_hex_length(len(candidate_hex)):
                return (candidate_name, candidate_hex, None)

    # --- FastSum format: '<filename> <HEXDIGEST>' ---
    parts = line.rsplit(None, 1)
    if len(parts) == 2:
        candidate_name = parts[0].rstrip()
        candidate_hex = parts[1].strip()
        if _is_hex(candidate_hex) and _type_from_hex_length(len(candidate_hex)):
            return (candidate_name, candidate_hex, None)

    return None
