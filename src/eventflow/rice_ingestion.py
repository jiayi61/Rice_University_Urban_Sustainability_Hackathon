"""Compatibility wrapper for the zero-dependency local Rice data pipeline."""
from __future__ import annotations

from .local_data import DATASET_DIRS, build_houston_profile, discover_files, read_header, scan_root

__all__ = [
    "DATASET_DIRS",
    "build_houston_profile",
    "discover_files",
    "read_header",
    "scan_root",
]
