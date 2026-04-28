"""
Command-line interface for checksum-tools.

Provides the same CLI options as the original Ruby gem.
"""

import argparse
import sys
import os

from checksum_tools import __version__
from checksum_tools.config import Config, SUPPORTED_DIGESTS, DEFAULT_CONFIG_PATH
from checksum_tools.local import LocalDigester, _is_hidden

# Optional: tqdm for progress bars (gracefully degrade without it)
try:
    from tqdm import tqdm

    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


# ──────────────────────────────────────────────────────────────
# Terminal colors (auto-disabled when stdout is not a TTY)
# ──────────────────────────────────────────────────────────────

def _enable_windows_ansi() -> bool:
    """Enable ANSI/VT100 escape code processing on Windows.

    Windows Terminal (default in Windows 11) supports ANSI natively,
    but cmd.exe requires explicitly enabling VT100 processing via
    the SetConsoleMode API.

    Returns True if ANSI is supported (or we're not on Windows).
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(-11)
        if handle == -1:
            return False
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        new_mode = mode.value | 0x0004
        if kernel32.SetConsoleMode(handle, new_mode):
            return True
        return False
    except Exception:
        return False


def _supports_color() -> bool:
    """Check if stdout supports ANSI color codes."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if not (hasattr(sys.stdout, "isatty") and sys.stdout.isatty()):
        return False
    # On Windows, try to enable VT100 processing
    if sys.platform == "win32":
        return _enable_windows_ansi()
    return True


_COLOR = _supports_color()


def green(text: str) -> str:
    return f"\033[32m{text}\033[0m" if _COLOR else text


def red(text: str) -> str:
    return f"\033[31m{text}\033[0m" if _COLOR else text


def yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m" if _COLOR else text


def bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if _COLOR else text


def dim(text: str) -> str:
    return f"\033[2m{text}\033[0m" if _COLOR else text


import re
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from a string."""
    return _ANSI_RE.sub("", text)


# Map digest type to manifest filename
_DIGEST_TO_MANIFEST = {
    "md5": "MD5SUMS",
    "sha1": "SHA1SUMS",
    "sha256": "SHA256SUMS",
    "sha384": "SHA384SUMS",
    "sha512": "SHA512SUMS",
}


class Logger:
    """Optional log file writer. Mirrors terminal output to a plain-text file.

    ANSI colors are stripped and tqdm progress bars are suppressed.
    """

    def __init__(self, path: str):
        self.file = open(path, "w", encoding="utf-8", newline="\n")

    def log(self, text: str):
        """Write a line to the log file (ANSI stripped)."""
        self.file.write(_strip_ansi(text) + "\n")

    def close(self):
        self.file.close()


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser mirroring the original Ruby gem's CLI."""
    parser = argparse.ArgumentParser(
        prog="checksum-tools",
        description="Generate or verify checksums for a set of files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  checksum-tools -a generate -d sha256 /path/to/files\n"
            "  checksum-tools -a verify -r /path/to/files\n"
            "  checksum-tools -a generate -d md5 -d sha256 -f '*.tif' /data\n"
        ),
    )

    parser.add_argument(
        "-a",
        "--action",
        choices=["generate", "verify"],
        default=None,
        help="Action to perform: generate or verify (default: verify)",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="FILE",
        default=None,
        help=f"Load configuration from FILE (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "-d",
        "--digest",
        action="append",
        metavar="DIGEST",
        dest="digests",
        help=(
            "Digest type to generate (can be specified multiple times). "
            f"Choices: {', '.join(SUPPORTED_DIGESTS)}. Default: md5"
        ),
    )
    parser.add_argument(
        "-e",
        "--extension",
        metavar="EXT",
        default=None,
        help="File extension for digest files (default: .digest)",
    )
    parser.add_argument(
        "-f",
        "--filemask",
        action="append",
        metavar="MASK",
        dest="filemasks",
        help="Include files matching MASK (can be repeated; default: *)",
    )
    parser.add_argument(
        "-n",
        "--no-action",
        action="store_true",
        dest="dry_run",
        help="Dry run — display configuration and exit",
    )
    parser.add_argument(
        "-o",
        "--overwrite",
        action="store_true",
        default=None,
        help="Overwrite existing digest files",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=None,
        help="Hide the progress bar",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        default=None,
        help="Recurse into subdirectories",
    )
    parser.add_argument(
        "--no-hidden",
        action="store_true",
        default=False,
        help="Ignore hidden files and directories (names starting with '.')",
    )
    parser.add_argument(
        "--log",
        metavar="FILE",
        default=None,
        help="Write a plain-text log of results to FILE (ANSI colors stripped)",
    )
    parser.add_argument(
        "--manifest",
        nargs="?",
        const="",
        default=None,
        metavar="FILE",
        help="Generate a single manifest file instead of per-file sidecars. "
             "Optionally specify a filename or path (default: MD5SUMS, SHA256SUMS, etc. "
             "in the target directory).",
    )
    parser.add_argument(
        "-x",
        "--exclude",
        action="append",
        metavar="MASK",
        dest="excludes",
        help="Exclude files matching MASK (can be repeated)",
    )
    parser.add_argument(
        "-D",
        "--digest-types",
        action="store_true",
        dest="show_digest_types",
        help="Show available digest types and exit",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"checksum-tools {__version__}",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Target directory (default: current directory)",
    )

    return parser


def merge_config(args: argparse.Namespace) -> Config:
    """Merge config file defaults with command-line arguments.

    CLI arguments override config file values.
    """
    # Load base config from file
    config = Config.from_file(args.config)

    # Override with CLI arguments (only if explicitly set)
    if args.action is not None:
        config.action = args.action
    if args.digests is not None:
        config.digests = args.digests
    if args.extension is not None:
        ext = args.extension
        if not ext.startswith("."):
            ext = f".{ext}"
        config.extension = ext
    if args.filemasks is not None:
        config.filemasks = args.filemasks
    if args.excludes is not None:
        config.excludes = args.excludes
    if args.path is not None:
        config.path = args.path
    if args.recursive:
        config.recursive = True
    if args.overwrite:
        config.overwrite = True
    if args.quiet:
        config.quiet = True
    if args.dry_run:
        config.dry_run = True
    if args.no_hidden:
        config.no_hidden = True
    if args.log:
        config.log_path = args.log
    if args.manifest is not None:
        config.manifest = args.manifest

    return config


class FileProgressBar:
    """Manages a per-file tqdm progress bar during hashing.

    Each time a new file starts being hashed, the bar resets with the
    new file's size. The bar is displayed in blue and disappears when
    the file finishes, leaving room for the DONE/PASS/FAIL line.
    """

    def __init__(self):
        self.bar = None
        self.last_bytes = 0
        self.current_name = ""

    def set_filename(self, name: str):
        """Set the filename that will be shown on the next bar."""
        self.current_name = name

    def callback(self, bytes_processed: int, total_bytes: int):
        """Progress callback compatible with LocalDigester."""
        # Detect new file: bytes_processed resets or bar doesn't exist
        if bytes_processed < self.last_bytes or self.bar is None:
            if self.bar:
                self.bar.close()
            self.bar = tqdm(
                total=total_bytes,
                unit="B",
                unit_scale=True,
                colour="blue",
                leave=False,
                desc=self.current_name,
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]",
            )

        self.bar.n = bytes_processed
        self.bar.refresh()
        self.last_bytes = bytes_processed

        if bytes_processed >= total_bytes:
            self.bar.close()
            self.bar = None
            self.last_bytes = 0

    def close(self):
        """Clean up any remaining bar."""
        if self.bar:
            self.bar.close()
            self.bar = None


class _ScanResult:
    """Results of a pre-scan of the target directory."""

    def __init__(self):
        self.with_sidecar: list[str] = []      # content files with a sidecar
        self.orphan_sidecars: list[str] = []    # sidecar files with no content file
        self.manifest_paths: list[str] = []     # manifest files found
        self.in_manifest: set[str] = set()      # content file paths listed in a manifest
        self.uncovered: list[str] = []          # content files with no sidecar and not in any manifest

    def print_summary(self, ext_label: str, action: str):
        """Print a human-readable summary to the terminal."""
        has_manifests = len(self.manifest_paths) > 0
        has_sidecars = len(self.with_sidecar) > 0

        if has_manifests and not has_sidecars:
            # Manifest-only scenario
            for mp in self.manifest_paths:
                print(f"  Manifest: {bold(os.path.basename(mp))}")
            print()
            print(f"Found {green(str(len(self.in_manifest)))} files listed in manifest.")
            n_uncov = len(self.uncovered)
            if n_uncov > 0:
                print(f"Found {yellow(str(n_uncov))} files not listed in any manifest or sidecar.")
        elif has_manifests and has_sidecars:
            # Mixed scenario
            for mp in self.manifest_paths:
                print(f"  Manifest: {bold(os.path.basename(mp))}")
            print()
            print(f"Found {green(str(len(self.with_sidecar)))} files with matching {ext_label} sidecar files.")
            print(f"Found {green(str(len(self.in_manifest)))} files listed in manifest.")
            if self.orphan_sidecars:
                print(f"Found {yellow(str(len(self.orphan_sidecars)))} orphan {ext_label} sidecar files with no matching file.")
            n_uncov = len(self.uncovered)
            if n_uncov > 0:
                print(f"Found {yellow(str(n_uncov))} files with no checksum coverage.")
        else:
            # Sidecar-only scenario (original behaviour)
            n_with = len(self.with_sidecar)
            n_orphan = len(self.orphan_sidecars)
            n_uncov = len(self.uncovered)
            print(f"Found {green(str(n_with)) if n_with else str(n_with)} files with matching {ext_label} files.")
            print(f"Found {yellow(str(n_orphan)) if n_orphan else str(n_orphan)} {ext_label} files with no matching file.")
            print(f"Found {str(n_uncov)} files with no matching {ext_label} file.")

        print("=" * 63)


def _pre_scan(config: Config) -> _ScanResult:
    """Pre-scan the target directory to classify files.

    Returns a _ScanResult with sidecar counts, manifest info, and
    uncovered files.
    """
    digester = LocalDigester(config)
    ext = config.extension
    result = _ScanResult()

    content_files = list(digester._matched_files())

    # --- Sidecar detection ---
    sidecar_covered: set[str] = set()
    for filepath in content_files:
        has_sidecar = False
        if os.path.isfile(f"{filepath}{ext}"):
            has_sidecar = True
        else:
            for dtype in SUPPORTED_DIGESTS:
                if os.path.isfile(f"{filepath}.{dtype}"):
                    has_sidecar = True
                    break
        if has_sidecar:
            result.with_sidecar.append(filepath)
            sidecar_covered.add(filepath)

    # --- Manifest detection ---
    root = os.path.abspath(config.path)
    dirs_to_scan: set[str] = set()
    dirs_to_scan.add(root)
    for fp in content_files:
        dirs_to_scan.add(os.path.dirname(os.path.abspath(fp)))

    manifest_covered: set[str] = set()
    seen_manifests: set[str] = set()

    for dirpath in sorted(dirs_to_scan):
        manifests = digester._get_manifests_for_dir(dirpath)
        for manifest_path, entries in manifests.items():
            if manifest_path not in seen_manifests:
                seen_manifests.add(manifest_path)
                result.manifest_paths.append(manifest_path)

            # Check which content files are listed in this manifest
            for filepath in content_files:
                abs_fp = os.path.abspath(filepath)
                fp_dir = os.path.dirname(abs_fp)

                # Same-directory lookup by basename
                if fp_dir == dirpath:
                    from checksum_tools.local import _normalize_filename
                    normalized = _normalize_filename(os.path.basename(filepath))
                    if normalized in entries:
                        manifest_covered.add(filepath)
                        continue

                # Root-level manifest lookup by relative path
                if dirpath == root and fp_dir != root:
                    rel_path = os.path.normpath(os.path.relpath(abs_fp, root))
                    if rel_path in entries:
                        manifest_covered.add(filepath)

    result.in_manifest = manifest_covered

    # --- Uncovered files: no sidecar AND not in any manifest ---
    all_covered = sidecar_covered | manifest_covered
    result.uncovered = [fp for fp in content_files if fp not in all_covered]

    # --- Orphan sidecar detection ---
    if config.recursive:
        walker = os.walk(root)
    else:
        try:
            entries = os.listdir(root)
        except OSError:
            entries = []
        walker = [(root, [], [e for e in entries if os.path.isfile(os.path.join(root, e))])]

    for dirpath, dirnames, filenames in walker:
        # Skip hidden directories when --no-hidden is set
        if config.no_hidden:
            dirnames[:] = [d for d in dirnames if not _is_hidden(d, os.path.join(dirpath, d))]

        for filename in filenames:
            # Skip hidden files when --no-hidden is set
            if config.no_hidden and _is_hidden(filename, os.path.join(dirpath, filename)):
                continue

            is_sidecar = False
            base = None

            if filename.endswith(ext):
                is_sidecar = True
                base = filename[: -len(ext)]
            else:
                for dtype in SUPPORTED_DIGESTS:
                    dext = f".{dtype}"
                    if filename.endswith(dext):
                        is_sidecar = True
                        base = filename[: -len(dext)]
                        break

            if is_sidecar and base:
                content_path = os.path.join(dirpath, base)
                full_path = os.path.join(dirpath, filename)
                # Only count as orphan sidecar if it's not a manifest
                if not os.path.isfile(content_path) and full_path not in seen_manifests:
                    result.orphan_sidecars.append(full_path)

    return result


def run_generate(config: Config, logger: "Logger | None" = None) -> int:
    """Run the generate action. Returns exit code."""
    ext_label = config.extension

    if not config.quiet:
        scan = _pre_scan(config)
        scan.print_summary(ext_label, "generate")
        if logger:
            # Log the summary (re-render without colors)
            _log_scan_summary(logger, scan, ext_label, "generate")

    # Set up per-file progress bar if tqdm is available
    progress_bar = None
    if not config.quiet and HAS_TQDM:
        progress_bar = FileProgressBar()

    digester = LocalDigester(
        config,
        progress_callback=progress_bar.callback if progress_bar else None,
        on_file_start=lambda fp: progress_bar.set_filename(os.path.basename(fp)) if progress_bar else None,
    )
    count = 0

    if config.manifest is not None:
        # --- Manifest mode: collect all entries, then write one file per digest type ---
        root = os.path.abspath(config.path)
        custom_path = config.manifest if config.manifest else None
        # entries_by_type: {digest_type: [(relative_path, hexdigest), ...]}
        entries_by_type: dict[str, list[tuple[str, str]]] = {}

        try:
            for result in digester.generate():
                count += 1
                rel_path = os.path.relpath(os.path.abspath(result.filepath), root)
                if result.digest_type not in entries_by_type:
                    entries_by_type[result.digest_type] = []
                entries_by_type[result.digest_type].append((rel_path, result.hexdigest))
                if not config.quiet:
                    line = f"{green('DONE')}        {os.path.abspath(result.filepath)}"
                    print(line)
                    if logger:
                        logger.log(_strip_ansi(line))
        finally:
            if progress_bar:
                progress_bar.close()

        # Write manifest files — collected in memory first
        for dtype, entries in entries_by_type.items():
            if custom_path:
                # User-specified path: use as-is (resolve relative to cwd)
                manifest_path = os.path.abspath(custom_path)
                manifest_name = os.path.basename(manifest_path)
            else:
                # Default naming: MD5SUMS, SHA256SUMS, etc. in the target directory
                manifest_name = _DIGEST_TO_MANIFEST.get(dtype, f"{dtype.upper()}SUMS")
                manifest_path = os.path.join(root, manifest_name)

            if os.path.exists(manifest_path) and not config.overwrite:
                msg = f"{yellow('Warning:')} {manifest_name} already exists, skipping (use -o to overwrite)."
                print(msg)
                if logger:
                    logger.log(_strip_ansi(msg))
                continue

            # Ensure the output directory exists
            manifest_dir = os.path.dirname(manifest_path)
            if manifest_dir and not os.path.isdir(manifest_dir):
                os.makedirs(manifest_dir, exist_ok=True)

            with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
                for rel_path, hexdigest in entries:
                    f.write(f"{hexdigest}  {rel_path}\n")

            msg = f"{green('Wrote')} {manifest_name} ({len(entries)} entries)"
            if not config.quiet:
                print(msg)
            if logger:
                logger.log(_strip_ansi(msg))

    else:
        # --- Sidecar mode (default) ---
        try:
            for result in digester.generate():
                count += 1
                if not config.quiet:
                    line = f"{green('DONE')}        {os.path.abspath(result.filepath)}"
                    print(line)
                    if logger:
                        logger.log(_strip_ansi(line))
        finally:
            if progress_bar:
                progress_bar.close()

    if not config.quiet:
        summary = f"\n{green('Generated')} {count} digest(s)."
        print(summary)
        if logger:
            logger.log(_strip_ansi(summary))

    return 0


def _log_scan_summary(logger: "Logger", scan: "_ScanResult", ext_label: str, action: str):
    """Write the pre-scan summary to the log file (plain text)."""
    has_manifests = len(scan.manifest_paths) > 0
    has_sidecars = len(scan.with_sidecar) > 0

    if has_manifests and not has_sidecars:
        for mp in scan.manifest_paths:
            logger.log(f"  Manifest: {os.path.basename(mp)}")
        logger.log("")
        logger.log(f"Found {len(scan.in_manifest)} files listed in manifest.")
        n_uncov = len(scan.uncovered)
        if n_uncov > 0:
            logger.log(f"Found {n_uncov} files not listed in any manifest or sidecar.")
    elif has_manifests and has_sidecars:
        for mp in scan.manifest_paths:
            logger.log(f"  Manifest: {os.path.basename(mp)}")
        logger.log("")
        logger.log(f"Found {len(scan.with_sidecar)} files with matching {ext_label} sidecar files.")
        logger.log(f"Found {len(scan.in_manifest)} files listed in manifest.")
        if scan.orphan_sidecars:
            logger.log(f"Found {len(scan.orphan_sidecars)} orphan {ext_label} sidecar files with no matching file.")
        n_uncov = len(scan.uncovered)
        if n_uncov > 0:
            logger.log(f"Found {n_uncov} files with no checksum coverage.")
    else:
        logger.log(f"Found {len(scan.with_sidecar)} files with matching {ext_label} files.")
        logger.log(f"Found {len(scan.orphan_sidecars)} {ext_label} files with no matching file.")
        logger.log(f"Found {len(scan.uncovered)} files with no matching {ext_label} file.")

    logger.log("=" * 63)


def run_verify(config: Config, logger: "Logger | None" = None) -> int:
    """Run the verify action. Returns exit code."""
    ext_label = config.extension
    scan = None

    if not config.quiet:
        scan = _pre_scan(config)
        scan.print_summary(ext_label, "verify")
        if logger:
            _log_scan_summary(logger, scan, ext_label, "verify")

    # Set up per-file progress bar if tqdm is available
    progress_bar = None
    if not config.quiet and HAS_TQDM:
        progress_bar = FileProgressBar()

    digester = LocalDigester(
        config,
        progress_callback=progress_bar.callback if progress_bar else None,
        on_file_start=lambda fp: progress_bar.set_filename(os.path.basename(fp)) if progress_bar else None,
    )
    passed = 0
    failed = 0
    total = 0
    failed_files: list[tuple[str, str, str]] = []  # (path, expected, actual)

    try:
        for result in digester.verify():
            total += 1
            abs_path = os.path.abspath(result.filepath)
            if result.passed:
                passed += 1
                if not config.quiet:
                    line = f"{green('PASS')}        {abs_path}"
                    print(line)
                    if logger:
                        logger.log(_strip_ansi(line))
            else:
                failed += 1
                failed_files.append((abs_path, result.expected, result.actual))
                line1 = f"{red('FAIL')}        {abs_path}"
                line2 = f"            expected: {result.expected}"
                line3 = f"            actual:   {result.actual}"
                print(line1)
                print(line2)
                print(line3)
                if logger:
                    logger.log(_strip_ansi(line1))
                    logger.log(line2)
                    logger.log(line3)
    finally:
        if progress_bar:
            progress_bar.close()

    # --- Final summary ---
    if total == 0:
        msg = yellow("No digest files found to verify.")
        print(msg)
        if logger:
            logger.log(_strip_ansi(msg))
    elif not config.quiet:
        if failed == 0:
            summary = f"\n{green('Verified')} {total} checksum(s): {green(f'{passed} passed')}, {failed} failed."
        else:
            summary = f"\n{red('Verified')} {total} checksum(s): {passed} passed, {red(f'{failed} failed')}."
        print(summary)
        if logger:
            logger.log(_strip_ansi(summary))

    # --- Failed file summary (collected at the end for easy scanning) ---
    if failed_files:
        header = f"\n{red('Failed files:')}"
        print(header)
        if logger:
            logger.log(_strip_ansi(header))
        for fpath, expected, actual in failed_files:
            line = f"  {red('FAIL')}  {fpath}"
            print(line)
            if logger:
                logger.log(_strip_ansi(line))

    # --- Missing sidecar/checksum report (up to 100, verify mode only) ---
    if scan and scan.uncovered and not config.quiet:
        n_uncov = len(scan.uncovered)
        cap = min(n_uncov, 100)
        header = f"\n{yellow(f'Files without checksum coverage ({n_uncov}):')}"
        print(header)
        if logger:
            logger.log(_strip_ansi(header))
        for fp in scan.uncovered[:cap]:
            line = f"  {os.path.abspath(fp)}"
            print(line)
            if logger:
                logger.log(line)
        if n_uncov > 100:
            msg = f"  ... and {n_uncov - 100} more."
            print(msg)
            if logger:
                logger.log(msg)

    return 1 if failed > 0 else 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Handle --digest-types
    if args.show_digest_types:
        print("Available digest types:")
        for dtype in SUPPORTED_DIGESTS:
            print(f"  {dtype}")
        return 0

    # Build config
    config = merge_config(args)

    # Validate
    try:
        config.validate()
    except ValueError as e:
        print(f"{red('Error:')} {e}", file=sys.stderr)
        return 1

    # Dry run
    if config.dry_run:
        print(config.summary())
        return 0

    # Run the selected action
    logger = None
    if config.log_path:
        logger = Logger(config.log_path)

    try:
        if not config.quiet:
            header = f"{bold('checksum-tools')} {__version__} \u2014 {config.action}"
            target = f"  Target: {os.path.abspath(config.path)}"
            print(header)
            print(target)
            print()
            if logger:
                logger.log(_strip_ansi(header))
                logger.log(target)
                logger.log("")

        if config.action == "generate":
            result = run_generate(config, logger)
        else:
            result = run_verify(config, logger)

        if logger:
            logger.log(f"\nLog written: {os.path.abspath(config.log_path)}")
        return result
    finally:
        if logger:
            logger.close()


def cli():
    """Entry point for console_scripts."""
    sys.exit(main())


if __name__ == "__main__":
    cli()
