#!/usr/bin/env python3
"""
File Utilities — Phase 5.9 Production Hardening

Provides atomic file write operations to prevent data corruption
on process crash or concurrent access.

Phase 5.9 Risk: P0-1 (state), P0-2 (telemetry), P0-3 (trace)
"""

import os
import tempfile
import yaml
from datetime import datetime, timezone


def atomic_yaml_write(filepath, data, header_lines=None):
    """
    Atomically write a YAML file using write-to-temp-then-rename pattern.

    On POSIX systems, rename() is atomic — either the old file or the new file
    exists, never a partial state. This prevents corruption on crash.

    Args:
        filepath: str, target file path
        data: dict/list, data to serialize as YAML
        header_lines: list of str, optional comment lines to prepend

    Returns:
        str: filepath on success

    Raises:
        Exception: on write failure (original file unchanged)
    """
    dirpath = os.path.dirname(filepath) or "."
    os.makedirs(dirpath, exist_ok=True)

    # Write to temp file in same directory (same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix=".tmp", prefix=".yaml_")
    try:
        with os.fdopen(fd, "w") as f:
            if header_lines:
                for line in header_lines:
                    f.write(line + "\n")
                f.write("\n")
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        # Atomic rename — POSIX guarantees this is atomic
        os.replace(tmp_path, filepath)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return filepath


def atomic_text_write(filepath, content):
    """
    Atomically write a text file using write-to-temp-then-rename pattern.

    Args:
        filepath: str, target file path
        content: str, file content

    Returns:
        str: filepath on success
    """
    dirpath = os.path.dirname(filepath) or "."
    os.makedirs(dirpath, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix=".tmp", prefix=".txt_")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return filepath


def cleanup_old_files(directory, pattern="*.yaml", max_age_days=30):
    """
    Remove files older than max_age_days from a directory.
    Called once per pipeline execution (idempotent).

    Args:
        directory: str, directory to clean
        pattern: str, file pattern (not used with glob, for documentation)
        max_age_days: int, maximum file age in days

    Returns:
        int: number of files removed
    """
    if not os.path.isdir(directory):
        return 0

    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - (max_age_days * 86400)
    removed = 0

    for name in os.listdir(directory):
        filepath = os.path.join(directory, name)
        if not os.path.isfile(filepath):
            continue
        # Skip hidden files and temp files
        if name.startswith(".") or name.endswith(".tmp"):
            continue
        try:
            mtime = os.path.getmtime(filepath)
            if mtime < cutoff:
                os.unlink(filepath)
                removed += 1
        except OSError:
            continue

    return removed
