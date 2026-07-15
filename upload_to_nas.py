"""
Upload stoch_data.db and stoch_levels.db to the NAS (via the Tailscale
network).

The PC (100.64.0.5) and the NAS (100.64.0.1) are on the same tailnet, so the
NAS is reached directly by its Tailscale IP -- no port forwarding needed.

Two transfer protocols are supported, chosen with PROTOCOL below (or the
STOCH_NAS_PROTOCOL environment variable):

    "smb" -- Windows file sharing; needs the smbclient package
    "ftp" -- plain FTP; stdlib only, enable the FTP service on the NAS first

Before uploading, the live sqlite file is snapshotted with sqlite's backup API
so the copy is consistent even if computer_use.py is writing at the same time.

Fill in NAS_SHARE / NAS_USERNAME / NAS_PASSWORD below (or set the STOCH_NAS_*
environment variables), then run:

    uv run upload_to_nas.py
"""

import ftplib
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
DB_PATHS = [
    Path(__file__).parent / "stoch_data.db",
]

# Plain files uploaded as-is under a stable (never dated) name, so the NAS
# link to the dashboard stays the same day after day.
PLAIN_PATHS = [
    # built by build_dashboard.py
    Path(__file__).parent / "dashboard.html",
]

# "smb" or "ftp"
PROTOCOL = os.environ.get("STOCH_NAS_PROTOCOL", "ftp").strip().lower()

NAS_IP = "100.64.0.1"
# SMB: name of the shared folder on the NAS, e.g. "home" or "stoch" on a
#      Synology -- the share name only, not a filesystem path.
# FTP: first folder under the FTP root (on a Synology the shares show up
#      there under the same names); "" if uploading relative to the FTP root.
NAS_SHARE = os.environ.get("STOCH_NAS_SHARE", "share")
# Folder inside the share to upload into ("" = the share's root).
NAS_REMOTE_DIR = os.environ.get("STOCH_NAS_DIR", "stoch_data")

NAS_USERNAME = os.environ.get("STOCH_NAS_USER", "username")
NAS_PASSWORD = os.environ.get("STOCH_NAS_PASSWORD", "password")

FTP_PORT = int(os.environ.get("STOCH_NAS_FTP_PORT", "21"))

# Each upload is saved under a dated name (stoch_data_2026-07-04.db) so a day's
# capture is never overwritten by the next day's run.
DATED_COPIES = False


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


def remote_filename(db_path):
    if DATED_COPIES:
        return f"{db_path.stem}_{datetime.now():%Y-%m-%d}{db_path.suffix}"
    return db_path.name


def remote_dir_parts():
    """Folders between the server root and the uploaded files, outermost first."""
    parts = []
    if NAS_SHARE:
        parts.append(NAS_SHARE)
    if NAS_REMOTE_DIR:
        parts.extend(p for p in NAS_REMOTE_DIR.replace("\\", "/").split("/") if p)
    return parts


# --------------------------------------------------------------------------- #
# SMB backend
# --------------------------------------------------------------------------- #
def upload_all_smb(jobs):
    # imported here so FTP mode works without the smbclient package installed
    import smbclient

    smbclient.ClientConfig(username=NAS_USERNAME, password=NAS_PASSWORD)

    remote_dir = "\\".join([rf"\\{NAS_IP}", *remote_dir_parts()])
    if NAS_REMOTE_DIR:
        smbclient.makedirs(remote_dir, exist_ok=True)

    for local_path, name in jobs:
        target = f"{remote_dir}\\{name}"
        with open(local_path, "rb") as src, smbclient.open_file(target, "wb") as dst:
            while chunk := src.read(1024 * 1024):
                dst.write(chunk)
        print(f"uploaded {name} -> {target}")


# --------------------------------------------------------------------------- #
# FTP backend
# --------------------------------------------------------------------------- #
def upload_all_ftp(jobs):
    ftp = ftplib.FTP()
    ftp.connect(NAS_IP, FTP_PORT, timeout=60)
    ftp.login(NAS_USERNAME, NAS_PASSWORD)
    try:
        for part in remote_dir_parts():
            try:
                ftp.mkd(part)
            except ftplib.error_perm:
                # already exists (or not allowed -- the cwd below will fail then)
                pass
            ftp.cwd(part)

        remote_dir = "/".join(remote_dir_parts())
        for local_path, name in jobs:
            with open(local_path, "rb") as src:
                ftp.storbinary(f"STOR {name}", src, blocksize=1024 * 1024)
            print(f"uploaded {name} -> ftp://{NAS_IP}/{remote_dir}/{name}")
    finally:
        ftp.quit()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
UPLOADERS = {
    "smb": upload_all_smb,
    "ftp": upload_all_ftp,
}


def upload():
    uploader = UPLOADERS.get(PROTOCOL)
    if uploader is None:
        raise ValueError(
            f"PROTOCOL must be one of {sorted(UPLOADERS)}, got {PROTOCOL!r}"
        )

    existing = [p for p in DB_PATHS if p.exists()]
    if not existing:
        raise FileNotFoundError(f"no databases found: {[str(p) for p in DB_PATHS]}")
    for missing in set(DB_PATHS) - set(existing):
        print(f"skipping {missing.name}: not found")

    # (local file to send, remote file name, delete local copy afterwards)
    jobs = []
    for db_path in existing:
        jobs.append((snapshot_db(db_path), remote_filename(db_path), True))
    for path in PLAIN_PATHS:
        if path.exists():
            jobs.append((path, path.name, False))
        else:
            print(f"skipping {path.name}: not found")

    try:
        uploader([(local, name) for local, name, _ in jobs])
    finally:
        for local, _, is_snapshot in jobs:
            if is_snapshot:
                local.unlink(missing_ok=True)


if __name__ == "__main__":
    upload()
