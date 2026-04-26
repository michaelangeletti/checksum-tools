"""Tests for checksum-tools Python port."""

import hashlib
import os
import tempfile
import pytest

from checksum_tools.config import Config, SUPPORTED_DIGESTS
from checksum_tools.local import (
    LocalDigester, DigestResult, VerifyResult,
    _is_hex, _type_from_hex_length,
    _parse_bsd_tagged, _parse_gnu_format, _parse_fastsum_format, _normalize_filename,
)
from checksum_tools.cli import main, build_parser, merge_config


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_dir(tmp_path):
    """Create a temporary directory with sample files."""
    (tmp_path / "file1.txt").write_text("Hello, world!")
    (tmp_path / "file2.txt").write_text("Goodbye, world!")
    (tmp_path / "image.tif").write_bytes(b"\x00\x01\x02\x03" * 100)
    return tmp_path


@pytest.fixture
def nested_dir(tmp_path):
    """Create a directory with subdirectories."""
    (tmp_path / "file1.txt").write_text("root file")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "file2.txt").write_text("nested file")
    return tmp_path


@pytest.fixture
def dir_with_digests(tmp_path):
    """Create a directory with files and pre-existing digest files."""
    content = "Hello, checksum!"
    (tmp_path / "data.txt").write_text(content)
    md5_hex = hashlib.md5(content.encode()).hexdigest()
    (tmp_path / "data.txt.md5").write_text(f"{md5_hex}  data.txt\n")
    sha256_hex = hashlib.sha256(content.encode()).hexdigest()
    (tmp_path / "data.txt.sha256").write_text(f"{sha256_hex}  data.txt\n")
    return tmp_path, md5_hex, sha256_hex


# ============================================================
# Config tests
# ============================================================

class TestConfig:
    def test_defaults(self):
        config = Config()
        assert config.action == "verify"
        assert config.digests == ["md5"]
        assert config.extension == ".digest"
        assert config.filemasks == ["*"]
        assert config.excludes == []
        assert config.recursive is False
        assert config.overwrite is False
        assert config.quiet is False
        assert config.dry_run is False

    def test_validate_action(self, tmp_path):
        config = Config(action="invalid", path=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid action"):
            config.validate()

    def test_validate_digest(self, tmp_path):
        config = Config(digests=["bogus"], path=str(tmp_path))
        with pytest.raises(ValueError, match="Unsupported digest"):
            config.validate()

    def test_validate_bad_path(self):
        config = Config(path="/nonexistent/path/12345")
        with pytest.raises(ValueError, match="does not exist"):
            config.validate()

    def test_validate_good(self, tmp_path):
        config = Config(path=str(tmp_path))
        config.validate()  # Should not raise

    def test_from_file_missing(self):
        config = Config.from_file("/nonexistent/config_file")
        assert config.action == "verify"  # defaults

    def test_from_file(self, tmp_path):
        config_file = tmp_path / ".checksum-tools"
        config_file.write_text(
            "action: generate\n"
            "digest: sha256\n"
            "recursive: true\n"
            "extension: .sha256\n"
        )
        config = Config.from_file(str(config_file))
        assert config.action == "generate"
        assert config.digests == ["sha256"]
        assert config.recursive is True
        assert config.extension == ".sha256"

    def test_summary(self, tmp_path):
        config = Config(path=str(tmp_path))
        summary = config.summary()
        assert "Action:" in summary
        assert "verify" in summary


# ============================================================
# LocalDigester tests
# ============================================================

class TestLocalDigester:
    def test_generate_md5(self, sample_dir):
        config = Config(action="generate", digests=["md5"], path=str(sample_dir))
        digester = LocalDigester(config)
        results = list(digester.generate())

        assert len(results) == 3  # file1.txt, file2.txt, image.tif
        for r in results:
            assert isinstance(r, DigestResult)
            assert r.digest_type == "md5"
            assert len(r.hexdigest) == 32
            assert os.path.isfile(r.digest_filepath)

    def test_generate_multiple_digests(self, sample_dir):
        config = Config(
            action="generate",
            digests=["md5", "sha256"],
            path=str(sample_dir),
        )
        digester = LocalDigester(config)
        results = list(digester.generate())

        # 3 files × 2 digest types = 6
        assert len(results) == 6
        md5_results = [r for r in results if r.digest_type == "md5"]
        sha_results = [r for r in results if r.digest_type == "sha256"]
        assert len(md5_results) == 3
        assert len(sha_results) == 3

    def test_generate_with_extension(self, sample_dir):
        config = Config(
            action="generate",
            digests=["md5"],
            extension=".md5",
            path=str(sample_dir),
        )
        digester = LocalDigester(config)
        results = list(digester.generate())

        for r in results:
            assert r.digest_filepath.endswith(".md5")

    def test_generate_no_overwrite(self, sample_dir):
        config = Config(
            action="generate",
            digests=["md5"],
            path=str(sample_dir),
            overwrite=False,
        )
        digester = LocalDigester(config)
        results1 = list(digester.generate())
        assert len(results1) == 3

        # Second run should skip (no overwrite)
        results2 = list(digester.generate())
        assert len(results2) == 0

    def test_generate_with_overwrite(self, sample_dir):
        config = Config(
            action="generate",
            digests=["md5"],
            path=str(sample_dir),
            overwrite=True,
        )
        digester = LocalDigester(config)
        results1 = list(digester.generate())
        results2 = list(digester.generate())
        assert len(results1) == 3
        assert len(results2) == 3

    def test_generate_filemask(self, sample_dir):
        config = Config(
            action="generate",
            digests=["md5"],
            filemasks=["*.tif"],
            path=str(sample_dir),
        )
        digester = LocalDigester(config)
        results = list(digester.generate())
        assert len(results) == 1
        assert "image.tif" in results[0].filepath

    def test_generate_exclude(self, sample_dir):
        config = Config(
            action="generate",
            digests=["md5"],
            excludes=["*.tif"],
            path=str(sample_dir),
        )
        digester = LocalDigester(config)
        results = list(digester.generate())
        assert len(results) == 2
        for r in results:
            assert "image.tif" not in r.filepath

    def test_generate_recursive(self, nested_dir):
        config = Config(
            action="generate",
            digests=["md5"],
            path=str(nested_dir),
            recursive=True,
        )
        digester = LocalDigester(config)
        results = list(digester.generate())
        assert len(results) == 2

    def test_generate_non_recursive(self, nested_dir):
        config = Config(
            action="generate",
            digests=["md5"],
            path=str(nested_dir),
            recursive=False,
        )
        digester = LocalDigester(config)
        results = list(digester.generate())
        assert len(results) == 1

    def test_verify_pass(self, dir_with_digests):
        tmp_path, md5_hex, sha256_hex = dir_with_digests
        config = Config(action="verify", path=str(tmp_path))
        digester = LocalDigester(config)
        results = list(digester.verify())

        assert len(results) >= 1
        for r in results:
            assert isinstance(r, VerifyResult)
            assert r.passed is True
            assert r.status == "PASS"

    def test_verify_fail(self, tmp_path):
        content = "Original content"
        (tmp_path / "test.txt").write_text(content)
        # Write a WRONG checksum
        (tmp_path / "test.txt.md5").write_text("0" * 32 + "  test.txt\n")

        config = Config(action="verify", path=str(tmp_path))
        digester = LocalDigester(config)
        results = list(digester.verify())

        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].status == "FAIL"

    def test_verify_no_digest_files(self, sample_dir):
        config = Config(action="verify", path=str(sample_dir))
        digester = LocalDigester(config)
        results = list(digester.verify())
        assert len(results) == 0

    def test_digest_file_format(self, sample_dir):
        """Verify generated digest files follow the 'hexdigest  filename' format."""
        config = Config(
            action="generate",
            digests=["sha256"],
            extension=".sha256",
            path=str(sample_dir),
        )
        digester = LocalDigester(config)
        results = list(digester.generate())

        for r in results:
            with open(r.digest_filepath) as f:
                line = f.read().strip()
            parts = line.split("  ", 1)
            assert len(parts) == 2
            assert len(parts[0]) == 64  # SHA-256 hex length
            assert parts[1] == os.path.basename(r.filepath)

    def test_available_digest_types(self):
        types = LocalDigester.available_digest_types()
        assert "md5" in types
        assert "sha256" in types
        assert len(types) == 5

    def test_dry_run(self, sample_dir):
        config = Config(
            action="generate",
            digests=["md5"],
            path=str(sample_dir),
            dry_run=True,
        )
        digester = LocalDigester(config)
        results = list(digester.generate())

        # Results are yielded but no files written
        assert len(results) == 3
        for r in results:
            assert not os.path.exists(r.digest_filepath)

    def test_progress_callback(self, sample_dir):
        callbacks_received = []

        def on_progress(bytes_done, total):
            callbacks_received.append((bytes_done, total))

        config = Config(
            action="generate",
            digests=["md5"],
            path=str(sample_dir),
        )
        digester = LocalDigester(config, progress_callback=on_progress)
        list(digester.generate())

        assert len(callbacks_received) > 0


# ============================================================
# Utility function tests
# ============================================================

class TestUtilities:
    def test_is_hex_valid(self):
        assert _is_hex("d41d8cd98f00b204e9800998ecf8427e") is True
        assert _is_hex("ABCDEF0123456789" * 2) is True

    def test_is_hex_invalid(self):
        assert _is_hex("") is False
        assert _is_hex("xyz") is False
        assert _is_hex("123") is False  # odd length

    def test_type_from_hex_length(self):
        assert _type_from_hex_length(32) == "md5"
        assert _type_from_hex_length(40) == "sha1"
        assert _type_from_hex_length(64) == "sha256"
        assert _type_from_hex_length(96) == "sha384"
        assert _type_from_hex_length(128) == "sha512"
        assert _type_from_hex_length(99) is None


# ============================================================
# CLI tests
# ============================================================

class TestCLI:
    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

    def test_digest_types(self, capsys):
        exit_code = main(["--digest-types"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "md5" in captured.out
        assert "sha256" in captured.out

    def test_dry_run(self, sample_dir, capsys):
        exit_code = main(["-a", "generate", "-n", str(sample_dir)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Configuration:" in captured.out

    def test_generate_cli(self, sample_dir, capsys):
        exit_code = main(["-a", "generate", "-q", str(sample_dir)])
        assert exit_code == 0

    def test_verify_cli(self, sample_dir, capsys):
        # First generate
        main(["-a", "generate", "-q", str(sample_dir)])
        # Then verify
        exit_code = main(["-a", "verify", "-q", str(sample_dir)])
        assert exit_code == 0

    def test_bad_path(self, capsys):
        exit_code = main(["-a", "verify", "/nonexistent/path/xyz"])
        assert exit_code == 1

    def test_merge_config_cli_overrides(self, tmp_path):
        config_file = tmp_path / ".checksum-tools"
        config_file.write_text("action: verify\ndigest: md5\n")

        parser = build_parser()
        args = parser.parse_args([
            "-a", "generate",
            "-d", "sha256",
            "-c", str(config_file),
            str(tmp_path),
        ])
        config = merge_config(args)
        assert config.action == "generate"
        assert config.digests == ["sha256"]


# ============================================================
# Format parser tests
# ============================================================

class TestFormatParsers:
    """Tests for the individual format parsing helpers."""

    def test_normalize_filename_asterisk(self):
        assert _normalize_filename("*file.txt") == "file.txt"

    def test_normalize_filename_backslash_path(self):
        assert _normalize_filename("path\\to\\file.txt") == "file.txt"

    def test_normalize_filename_forward_path(self):
        assert _normalize_filename("path/to/file.txt") == "file.txt"

    def test_normalize_filename_combined(self):
        assert _normalize_filename("*C:\\data\\file.txt") == "file.txt"

    def test_parse_bsd_md5(self):
        result = _parse_bsd_tagged(
            "MD5 (file.txt) = d41d8cd98f00b204e9800998ecf8427e", "file.txt"
        )
        assert result == ("md5", "d41d8cd98f00b204e9800998ecf8427e")

    def test_parse_bsd_sha256(self):
        result = _parse_bsd_tagged(
            "SHA256 (file.txt) = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "file.txt",
        )
        assert result == ("sha256", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    def test_parse_bsd_wrong_file(self):
        assert _parse_bsd_tagged(
            "MD5 (other.txt) = d41d8cd98f00b204e9800998ecf8427e", "file.txt"
        ) is None

    def test_parse_bsd_non_match(self):
        assert _parse_bsd_tagged("not a bsd line", "file.txt") is None

    def test_parse_gnu_double_space(self):
        result = _parse_gnu_format(
            "d41d8cd98f00b204e9800998ecf8427e  file.txt", "file.txt"
        )
        assert result == "d41d8cd98f00b204e9800998ecf8427e"

    def test_parse_gnu_binary_mode(self):
        result = _parse_gnu_format(
            "d41d8cd98f00b204e9800998ecf8427e *file.txt", "file.txt"
        )
        assert result == "d41d8cd98f00b204e9800998ecf8427e"

    def test_parse_gnu_with_path(self):
        result = _parse_gnu_format(
            "d41d8cd98f00b204e9800998ecf8427e  subdir/file.txt", "file.txt"
        )
        assert result == "d41d8cd98f00b204e9800998ecf8427e"

    def test_parse_gnu_wrong_file(self):
        assert _parse_gnu_format(
            "d41d8cd98f00b204e9800998ecf8427e  other.txt", "file.txt"
        ) is None

    def test_parse_fastsum_basic(self):
        result = _parse_fastsum_format(
            "file.txt D41D8CD98F00B204E9800998ECF8427E", "file.txt"
        )
        assert result == "D41D8CD98F00B204E9800998ECF8427E"

    def test_parse_fastsum_uppercase(self):
        result = _parse_fastsum_format(
            "MYFILE.CAB 7ADEABFF8084C665E89702B14BDF118A", "MYFILE.CAB"
        )
        assert result == "7ADEABFF8084C665E89702B14BDF118A"

    def test_parse_fastsum_wrong_file(self):
        assert _parse_fastsum_format(
            "other.txt D41D8CD98F00B204E9800998ECF8427E", "file.txt"
        ) is None

    def test_parse_fastsum_not_hex(self):
        assert _parse_fastsum_format("file.txt NOTAHEX", "file.txt") is None


class TestFastsumIntegration:
    """End-to-end tests for FastSum format digest files."""

    def test_fastsum_with_comments(self, tmp_path):
        content = "Hello, FastSum!"
        (tmp_path / "data.txt").write_text(content)
        md5_hex = hashlib.md5(content.encode()).hexdigest().upper()

        digest_content = (
            "; Generated by FastSum\n"
            "; Date=2024-01-15\n"
            "; Host=WORKSTATION\n"
            "; User=Admin\n"
            f"data.txt {md5_hex}\n"
        )
        (tmp_path / "data.txt.md5").write_text(digest_content)

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].digest_type == "md5"

    def test_fastsum_multi_entry(self, tmp_path):
        content_a = "File A"
        content_b = "File B"
        (tmp_path / "a.txt").write_text(content_a)
        (tmp_path / "b.txt").write_text(content_b)
        md5_a = hashlib.md5(content_a.encode()).hexdigest().upper()
        md5_b = hashlib.md5(content_b.encode()).hexdigest().upper()

        shared_digest = f"; FastSum\na.txt {md5_a}\nb.txt {md5_b}\n"
        (tmp_path / "a.txt.md5").write_text(shared_digest)
        (tmp_path / "b.txt.md5").write_text(shared_digest)

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_comment_only_digest_file(self, tmp_path):
        (tmp_path / "test.txt").write_text("test")
        (tmp_path / "test.txt.md5").write_text("; just a comment\n; no checksums\n")

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 0


class TestBsdFormatIntegration:
    """End-to-end tests for BSD tagged format digest files."""

    def test_bsd_sha256(self, tmp_path):
        content = "Hello, BSD!"
        (tmp_path / "data.txt").write_text(content)
        sha_hex = hashlib.sha256(content.encode()).hexdigest()
        (tmp_path / "data.txt.sha256").write_text(f"SHA256 (data.txt) = {sha_hex}\n")

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].digest_type == "sha256"

    def test_bsd_md5(self, tmp_path):
        content = "BSD MD5 test"
        (tmp_path / "file.bin").write_text(content)
        md5_hex = hashlib.md5(content.encode()).hexdigest()
        (tmp_path / "file.bin.md5").write_text(f"MD5 (file.bin) = {md5_hex}\n")

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 1
        assert results[0].passed is True


class TestWindowsPathIntegration:
    """Tests for digest files with Windows-style paths."""

    def test_backslash_paths(self, tmp_path):
        content = "Windows test"
        (tmp_path / "report.doc").write_text(content)
        md5_hex = hashlib.md5(content.encode()).hexdigest()
        (tmp_path / "report.doc.md5").write_text(
            f"{md5_hex} *C:\\Users\\data\\report.doc\n"
        )

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 1
        assert results[0].passed is True

    def test_uppercase_hex(self, tmp_path):
        content = "UPPER case test"
        (tmp_path / "file.txt").write_text(content)
        md5_upper = hashlib.md5(content.encode()).hexdigest().upper()
        (tmp_path / "file.txt.md5").write_text(f"{md5_upper}  file.txt\n")

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 1
        assert results[0].passed is True


# ============================================================
# Round-trip test
# ============================================================

class TestRoundTrip:
    """End-to-end: generate then verify for every digest type."""

    @pytest.mark.parametrize("digest_type", SUPPORTED_DIGESTS)
    def test_generate_then_verify(self, tmp_path, digest_type):
        (tmp_path / "sample.dat").write_bytes(os.urandom(1024))

        gen_config = Config(
            action="generate",
            digests=[digest_type],
            extension=f".{digest_type}",
            path=str(tmp_path),
        )
        gen_digester = LocalDigester(gen_config)
        gen_results = list(gen_digester.generate())
        assert len(gen_results) == 1

        ver_config = Config(
            action="verify",
            path=str(tmp_path),
        )
        ver_digester = LocalDigester(ver_config)
        ver_results = list(ver_digester.verify())
        assert len(ver_results) == 1
        assert ver_results[0].passed is True


# ============================================================
# Manifest file tests
# ============================================================

class TestManifestLine:
    """Tests for the _parse_manifest_line helper."""

    def test_gnu_format(self):
        from checksum_tools.local import _parse_manifest_line
        r = _parse_manifest_line("d41d8cd98f00b204e9800998ecf8427e  file.txt")
        assert r == ("file.txt", "d41d8cd98f00b204e9800998ecf8427e", None)

    def test_bsd_format(self):
        from checksum_tools.local import _parse_manifest_line
        r = _parse_manifest_line("MD5 (file.txt) = d41d8cd98f00b204e9800998ecf8427e")
        assert r == ("file.txt", "d41d8cd98f00b204e9800998ecf8427e", "md5")

    def test_fastsum_format(self):
        from checksum_tools.local import _parse_manifest_line
        r = _parse_manifest_line("file.txt D41D8CD98F00B204E9800998ECF8427E")
        assert r is not None
        assert r[0] == "file.txt"
        assert r[1] == "D41D8CD98F00B204E9800998ECF8427E"


class TestManifestMD5SUMS:
    """Tests for MD5SUMS-style manifest files."""

    def test_md5sums_verify(self, tmp_path):
        files = {"a.txt": "alpha", "b.txt": "bravo", "c.dat": "charlie"}
        hashes = {}
        for name, content in files.items():
            (tmp_path / name).write_text(content)
            hashes[name] = hashlib.md5(content.encode()).hexdigest()

        manifest = "".join(f"{h}  {n}\n" for n, h in hashes.items())
        (tmp_path / "MD5SUMS").write_text(manifest)

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_sha256sums_verify(self, tmp_path):
        files = {"x.bin": b"\x00\x01", "y.bin": b"\x02\x03"}
        hashes = {}
        for name, content in files.items():
            (tmp_path / name).write_bytes(content)
            hashes[name] = hashlib.sha256(content).hexdigest()

        manifest = "".join(f"{h}  {n}\n" for n, h in hashes.items())
        (tmp_path / "SHA256SUMS").write_text(manifest)

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 2
        assert all(r.passed for r in results)
        assert all(r.digest_type == "sha256" for r in results)

    def test_checksums_md5_manifest(self, tmp_path):
        files = {"doc1.pdf": "pdf1", "doc2.pdf": "pdf2"}
        hashes = {}
        for name, content in files.items():
            (tmp_path / name).write_text(content)
            hashes[name] = hashlib.md5(content.encode()).hexdigest()

        manifest = "".join(f"{h}  {n}\n" for n, h in hashes.items())
        (tmp_path / "checksums.md5").write_text(manifest)

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 2
        assert all(r.passed for r in results)


class TestManifestFastSum:
    """Tests for FastSum manifest files (/T:R and /T:F modes)."""

    def test_fastsum_root_manifest(self, tmp_path):
        files = {"report.xls": "excel", "letter.doc": "word"}
        hashes = {}
        for name, content in files.items():
            (tmp_path / name).write_text(content)
            hashes[name] = hashlib.md5(content.encode()).hexdigest().upper()

        manifest = "; Generated by FastSum\n; Date=2024-03-15\n"
        manifest += "".join(f"{n} {h}\n" for n, h in hashes.items())
        (tmp_path / "root.md5").write_text(manifest)

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 2
        assert all(r.passed for r in results)


class TestManifestBSD:
    """Tests for BSD-tagged manifest files."""

    def test_bsd_manifest(self, tmp_path):
        files = {"app.dmg": "disk image", "readme.txt": "info"}
        hashes = {}
        for name, content in files.items():
            (tmp_path / name).write_text(content)
            hashes[name] = hashlib.sha256(content.encode()).hexdigest()

        manifest = "".join(f"SHA256 ({n}) = {h}\n" for n, h in hashes.items())
        (tmp_path / "checksums.sha256").write_text(manifest)

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 2
        assert all(r.passed for r in results)
        assert all(r.digest_type == "sha256" for r in results)


class TestManifestEdgeCases:
    """Edge cases for manifest handling."""

    def test_manifest_with_failures(self, tmp_path):
        (tmp_path / "good.txt").write_text("good")
        (tmp_path / "bad.txt").write_text("bad")
        good_md5 = hashlib.md5(b"good").hexdigest()

        manifest = f"{good_md5}  good.txt\n{'0' * 32}  bad.txt\n"
        (tmp_path / "MD5SUMS").write_text(manifest)

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        by_name = {os.path.basename(r.filepath): r for r in results}
        assert by_name["good.txt"].passed
        assert not by_name["bad.txt"].passed

    def test_sidecar_and_manifest_dedup(self, tmp_path):
        """Same digest type in sidecar and manifest should yield only once."""
        content = "dedup"
        (tmp_path / "data.txt").write_text(content)
        md5 = hashlib.md5(content.encode()).hexdigest()

        (tmp_path / "data.txt.md5").write_text(f"{md5}  data.txt\n")
        (tmp_path / "MD5SUMS").write_text(f"{md5}  data.txt\n")

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 1
        assert results[0].passed

    def test_sidecar_and_manifest_different_types(self, tmp_path):
        """Different digest types from sidecar vs manifest both yielded."""
        content = "multi"
        (tmp_path / "data.txt").write_text(content)
        md5 = hashlib.md5(content.encode()).hexdigest()
        sha = hashlib.sha256(content.encode()).hexdigest()

        (tmp_path / "data.txt.md5").write_text(f"{md5}  data.txt\n")
        (tmp_path / "SHA256SUMS").write_text(f"{sha}  data.txt\n")

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 2
        types = {r.digest_type for r in results}
        assert types == {"md5", "sha256"}
        assert all(r.passed for r in results)

    def test_manifest_not_checksummed_as_content(self, tmp_path):
        """Manifest files should not appear as content files."""
        (tmp_path / "real.txt").write_text("real")
        md5 = hashlib.md5(b"real").hexdigest()
        (tmp_path / "MD5SUMS").write_text(f"{md5}  real.txt\n")

        config = Config(action="generate", digests=["sha256"], path=str(tmp_path))
        results = list(LocalDigester(config).generate())
        names = [os.path.basename(r.filepath) for r in results]
        assert "MD5SUMS" not in names
        assert "real.txt" in names

    def test_large_manifest(self, tmp_path):
        """Manifest with 25 files."""
        hashes = {}
        for i in range(25):
            name = f"file_{i:03d}.dat"
            content = f"content {i}".encode()
            (tmp_path / name).write_bytes(content)
            hashes[name] = hashlib.md5(content).hexdigest()

        manifest = "".join(f"{h}  {n}\n" for n, h in hashes.items())
        (tmp_path / "MD5SUMS").write_text(manifest)

        config = Config(action="verify", path=str(tmp_path))
        results = list(LocalDigester(config).verify())
        assert len(results) == 25
        assert all(r.passed for r in results)
