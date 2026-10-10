"""Atomic draft replacement with one generation of backup (FR-050).

The order matters. A draft file may hold hours of review, and the moment the
spec promises it is safe is exactly the moment it is most at risk:

1. write the new content to a temporary file in the same directory and flush it
   to disk, so a crash cannot leave a half-written draft;
2. move the existing file aside to ``.bak``;
3. ``os.replace`` the temporary into place.

``os.replace`` is used rather than ``os.rename`` because renaming onto an
existing path fails on Windows, which is the primary platform here.

Only one backup generation is kept: no requirement asks for history, and a
directory the engineer reviews should not fill with timestamped files.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

BACKUP_SUFFIX = ".bak"


def backup_path_for(path: str | Path) -> Path:
    target = Path(path)
    return target.with_name(target.name + BACKUP_SUFFIX)


def write_atomic(path: str | Path, content: str) -> None:
    """Write ``content`` to ``path`` without risking a partial file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    handle, temp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def replace_with_backup(path: str | Path, content: str) -> Path | None:
    """Replace ``path``, keeping the previous version as ``<name>.bak``.

    Returns the backup path, or ``None`` when there was nothing to replace.
    """
    target = Path(path)
    backup: Path | None = None

    if target.exists():
        backup = backup_path_for(target)
        # Replacing any previous backup: one generation only.
        os.replace(target, backup)

    try:
        write_atomic(target, content)
    except BaseException:
        # Put the original back rather than leaving the engineer with neither
        # the draft nor a visible failure.
        if backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise

    return backup
