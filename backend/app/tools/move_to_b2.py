"""One-off: move videos already stored on the local volume into the Backblaze bucket.

    python -m app.tools.move_to_b2 --dry-run     (shows what would move)
    python -m app.tools.move_to_b2               (uploads, verifies, updates the database, then deletes the local file)

Safe to repeat: files already in the bucket are skipped. A local file is deleted only after the upload succeeded and the
object's size matched. Needs STORAGE_PROVIDER=b2 and the B2_* variables."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from sqlalchemy import select

from app import db as database
from app import models as m
from app.config import load_settings
from app.storage import PREFIX, StorageError, is_remote, make_store


def move(store, session, dry_run: bool = False) -> dict:
    stats = {"moved": 0, "skipped_remote": 0, "missing": 0, "failed": 0, "bytes": 0}
    for asset in session.scalars(select(m.VideoAsset)).all():
        if is_remote(asset.local_path):
            stats["skipped_remote"] += 1
            continue
        path = Path(asset.local_path)
        if not path.is_file():
            stats["missing"] += 1
            continue
        key = f"videos/{asset.version_id}/{asset.job_id}/{asset.kind}-{asset.filename}"
        if dry_run:
            stats["moved"] += 1
            stats["bytes"] += path.stat().st_size
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset.sha256:  # never upload a damaged file
            stats["failed"] += 1
            continue
        try:
            store.put_file(key, path, asset.content_type)
        except StorageError:
            stats["failed"] += 1
            continue
        if not store.exists(key):
            stats["failed"] += 1
            continue
        asset.local_path = PREFIX + key
        session.commit()
        path.unlink(missing_ok=True)
        stats["moved"] += 1
        stats["bytes"] += asset.size_bytes
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Move stored videos to Backblaze B2")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    settings = load_settings()
    store = make_store(settings)
    if store is None:
        raise SystemExit("Set STORAGE_PROVIDER=b2 and the B2_* variables first.")
    database.init_db(settings.database_url)
    gen = database.get_db()
    session = next(gen)
    try:
        stats = move(store, session, args.dry_run)
    finally:
        gen.close()
    print(("Would move" if args.dry_run else "Moved"), f"{stats['moved']} files ({stats['bytes'] / 1e6:.1f} MB);",
          f"{stats['skipped_remote']} already in the bucket, {stats['missing']} missing on disk, {stats['failed']} failed.")


if __name__ == "__main__":
    main()
