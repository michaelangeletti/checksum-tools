"""
Configuration loader for checksum-tools.

Loads defaults from a YAML config file (default: ~/.checksum-tools)
and merges them with command-line options.
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Optional


# Default config file location
DEFAULT_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".checksum-tools")

# Supported digest algorithms (Python hashlib names)
SUPPORTED_DIGESTS = ["md5", "sha1", "sha256", "sha384", "sha512"]

# Default values
DEFAULT_ACTION = "verify"
DEFAULT_DIGEST = "md5"
DEFAULT_EXTENSION = ".digest"
DEFAULT_FILEMASK = ["*"]


@dataclass
class Config:
    """Configuration for a checksum-tools run."""

    action: str = DEFAULT_ACTION
    digests: list = field(default_factory=lambda: [DEFAULT_DIGEST])
    extension: str = DEFAULT_EXTENSION
    filemasks: list = field(default_factory=lambda: list(DEFAULT_FILEMASK))
    excludes: list = field(default_factory=list)
    path: str = "."
    recursive: bool = False
    overwrite: bool = False
    quiet: bool = False
    dry_run: bool = False
    no_hidden: bool = False
    log_path: Optional[str] = None
    manifest: Optional[str] = None  # None = off, "" = default naming, "path" = custom

    def __post_init__(self):
        # Ensure extension always has a leading dot
        if self.extension and not self.extension.startswith("."):
            self.extension = f".{self.extension}"

    @classmethod
    def from_file(cls, filepath: Optional[str] = None) -> "Config":
        """Load configuration from a YAML file.

        Args:
            filepath: Path to the config file. If None, uses the default
                      location (~/.checksum-tools).

        Returns:
            A Config instance with values from the file.
        """
        config_path = filepath or DEFAULT_CONFIG_PATH

        if not os.path.isfile(config_path):
            return cls()

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError) as e:
            print(f"Warning: Could not load config file {config_path}: {e}")
            return cls()

        return cls(
            action=data.get("action", DEFAULT_ACTION),
            digests=_ensure_list(data.get("digest", DEFAULT_DIGEST)),
            extension=data.get("extension", DEFAULT_EXTENSION),
            filemasks=_ensure_list(data.get("filemask", DEFAULT_FILEMASK)),
            excludes=_ensure_list(data.get("exclude", [])),
            recursive=data.get("recursive", False),
            overwrite=data.get("overwrite", False),
            quiet=data.get("quiet", False),
        )

    def validate(self) -> None:
        """Validate configuration values, raising ValueError if invalid."""
        if self.action not in ("generate", "verify"):
            raise ValueError(
                f"Invalid action: '{self.action}'. Must be 'generate' or 'verify'."
            )

        for digest in self.digests:
            if digest.lower() not in SUPPORTED_DIGESTS:
                raise ValueError(
                    f"Unsupported digest type: '{digest}'. "
                    f"Available types: {', '.join(SUPPORTED_DIGESTS)}"
                )

        if not os.path.isdir(self.path):
            raise ValueError(f"Target path does not exist or is not a directory: '{self.path}'")

    def summary(self) -> str:
        """Return a human-readable summary of the configuration."""
        lines = [
            "Configuration:",
            f"  Action:      {self.action}",
            f"  Digests:     {', '.join(self.digests)}",
            f"  Extension:   {self.extension}",
            f"  File masks:  {', '.join(self.filemasks)}",
            f"  Excludes:    {', '.join(self.excludes) if self.excludes else '(none)'}",
            f"  Path:        {os.path.abspath(self.path)}",
            f"  Recursive:   {self.recursive}",
            f"  Overwrite:   {self.overwrite}",
            f"  Quiet:       {self.quiet}",
        ]
        return "\n".join(lines)


def _ensure_list(value) -> list:
    """Ensure a value is a list (wrap scalars)."""
    if isinstance(value, list):
        return value
    return [value]
