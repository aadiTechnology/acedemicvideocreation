"""Object storage for generated videos and their supporting files (Backblaze B2 through its S3-compatible API).

Imported packages stay on the local volume (small, read often). Videos go to the bucket: the app uploads the verified file,
deletes its local copy, and serves playback and downloads through short-lived signed links, so video bytes never pass
through this server. A stored file's ``local_path`` is ``b2:<object key>`` instead of a file path."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("academic.storage")
PREFIX = "b2:"


class StorageError(Exception):
    pass


class B2Store:
    def __init__(self, bucket: str, expiry_seconds: int, client) -> None:
        self.bucket, self.expiry, self.client = bucket, expiry_seconds, client

    @classmethod
    def from_settings(cls, s) -> "B2Store":
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3", endpoint_url=s.b2_endpoint if s.b2_endpoint.startswith("http") else f"https://{s.b2_endpoint}",
            aws_access_key_id=s.b2_key_id, aws_secret_access_key=s.b2_application_key, region_name=s.b2_region or None,
            config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}, connect_timeout=10, read_timeout=120),
        )
        return cls(s.b2_bucket, s.b2_url_expiry, client)

    def put_file(self, key: str, path: Path, content_type: str) -> None:
        try:
            self.client.upload_file(str(path), self.bucket, key, ExtraArgs={"ContentType": content_type})
        except Exception as exc:  # noqa: BLE001 - boto raises many types; the caller needs one
            logger.warning("upload of %s failed: %s", key, type(exc).__name__)
            raise StorageError("The storage service could not store the file.") from exc

    def url(self, key: str, filename: str, content_type: str, download: bool) -> str:
        disposition = f'{"attachment" if download else "inline"}; filename="{filename}"'
        return self.client.generate_presigned_url(
            "get_object", ExpiresIn=self.expiry,
            Params={"Bucket": self.bucket, "Key": key, "ResponseContentType": content_type, "ResponseContentDisposition": disposition})

    def read_bytes(self, key: str, limit: int = 2 * 1024 * 1024) -> bytes:
        """Read a small object (a report). Larger objects are refused: videos are served through signed links."""
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read(limit + 1)
        except Exception as exc:  # noqa: BLE001
            raise StorageError("The file could not be read.") from exc
        if len(body) > limit:
            raise StorageError("The file is too large to read here.")
        return body

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def is_remote(local_path: str) -> bool:
    return local_path.startswith(PREFIX)


def key_of(local_path: str) -> str:
    return local_path[len(PREFIX):]


def make_store(settings) -> B2Store | None:
    return B2Store.from_settings(settings) if settings.storage_provider == "b2" else None
