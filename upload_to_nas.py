"""
Upload stoch_data.db and stoch_levels.db to the NAS over SMB (via the
Tailscale network).

The PC (100.64.0.5) and the NAS (100.64.0.1) are on the same tailnet, so the
NAS is reached directly by its Tailscale IP -- no port forwarding needed.

Before uploading, the live sqlite file is snapshotted with sqlite's backup API
so the copy is consistent even if computer_use.py is writing at the same time.

Fill in NAS_SHARE / NAS_USERNAME / NAS_PASSWORD below (or set the STOCH_NAS_*
environment variables), then run:

    uv run upload_to_nas.py
"""

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import smbclient

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
DB_PATHS = [
    Path(__file__).parent / "stoch_data.db",
    # levels db produced by classify_levels.py
    Path(__file__).parent / "stoch_levels.db",
]

# Plain files uploaded as-is under a stable (never dated) name, so the NAS
# link to the dashboard stays the same day after day.
PLAIN_PATHS = [
    # built by build_dashboard.py
    Path(__file__).parent / "dashboard.html",
]

NAS_IP = "100.64.0.1"
# Name of the shared folder on the NAS, e.g. "home" or "stoch" on a Synology.
NAS_SHARE = os.environ.get("STOCH_NAS_SHARE", "share")
# Folder inside the share to upload into ("" = the share's root).
NAS_REMOTE_DIR = os.environ.get("STOCH_NAS_DIR", "stoch_data")

NAS_USERNAME = os.environ.get("STOCH_NAS_USER", "username")
NAS_PASSWORD = os.environ.get("STOCH_NAS_PASSWORD", "password")

# Each upload is saved under a dated name (stoch_data_2026-07-04.db) so a day's
# capture is never overwritten by the next day's run.
DATED_COPIES = True


def snapshot_db(db_path):
    """Copy the sqlite db to a temp file with the backup API; returns the path."""
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(tmp_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return Path(tmp_path)


def remote_path(db_path):
    name = db_path.name
    if DATED_COPIES:
        stem, ext = db_path.stem, db_path.suffix
        name = f"{stem}_{datetime.now():%Y-%m-%d}{ext}"
    parts = [rf"\\{NAS_IP}\{NAS_SHARE}"]
    if NAS_REMOTE_DIR:
        parts.append(NAS_REMOTE_DIR)
    parts.append(name)
    return "\\".join(parts)


def upload_one(db_path):
    target = remote_path(db_path)
    snapshot = snapshot_db(db_path)
    try:
        copy_to_nas(snapshot, target)
    finally:
        snapshot.unlink()

    print(f"uploaded {db_path.name} -> {target}")


def upload_plain(path):
    """Upload a non-database file as-is, under its own (undated) name."""
    parts = [rf"\\{NAS_IP}\{NAS_SHARE}"]
    if NAS_REMOTE_DIR:
        parts.append(NAS_REMOTE_DIR)
    parts.append(path.name)
    target = "\\".join(parts)
    copy_to_nas(path, target)
    print(f"uploaded {path.name} -> {target}")


def copy_to_nas(local_path, target):
    with open(local_path, "rb") as src, smbclient.open_file(target, "wb") as dst:
        while chunk := src.read(1024 * 1024):
            dst.write(chunk)


def upload():
    existing = [p for p in DB_PATHS if p.exists()]
    if not existing:
        raise FileNotFoundError(f"no databases found: {[str(p) for p in DB_PATHS]}")
    for missing in set(DB_PATHS) - set(existing):
        print(f"skipping {missing.name}: not found")

    smbclient.ClientConfig(username=NAS_USERNAME, password=NAS_PASSWORD)

    if NAS_REMOTE_DIR:
        smbclient.makedirs(rf"\\{NAS_IP}\{NAS_SHARE}\{NAS_REMOTE_DIR}", exist_ok=True)

    for db_path in existing:
        upload_one(db_path)

    for path in PLAIN_PATHS:
        if path.exists():
            upload_plain(path)
        else:
            print(f"skipping {path.name}: not found")


if __name__ == "__main__":
    upload()
