"""
checksum-tools — Generate or verify checksums for a set of files.

A Python port of the sul-dlss/checksum-tools Ruby gem.
"""

__version__ = "2.0.0"
__author__ = "Stanford University Libraries"

from checksum_tools.local import LocalDigester
from checksum_tools.config import Config

__all__ = ["LocalDigester", "Config", "__version__"]
