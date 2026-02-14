from __future__ import annotations

import io
import os
from minio import Minio
from minio.error import S3Error


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v not in (None, "") else default


# ---------------------------------------------------------
# Client
# ---------------------------------------------------------

def client() -> Minio:
    """
    MinIO client from env:
    - MINIO_ENDPOINT (default http://minio:9000)
    - MINIO_ACCESS_KEY
    - MINIO_SECRET_KEY
    """

    endpoint = _env("MINIO_ENDPOINT", "http://minio:9000")
    access_key = _env("MINIO_ACCESS_KEY")
    secret_key = _env("MINIO_SECRET_KEY")

    if not access_key or not secret_key:
        raise RuntimeError("MINIO_ACCESS_KEY / MINIO_SECRET_KEY not set.")

    secure = endpoint.startswith("https://")
    endpoint_clean = endpoint.replace("https://", "").replace("http://", "")

    return Minio(
        endpoint_clean,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )


# ---------------------------------------------------------
# Bucket helpers
# ---------------------------------------------------------

def ensure_bucket(m: Minio, bucket: str) -> None:
    try:
        if not m.bucket_exists(bucket):
            m.make_bucket(bucket)
    except S3Error as e:
        # If bucket already exists or race condition, ignore
        if e.code != "BucketAlreadyOwnedByYou":
            raise


# ---------------------------------------------------------
# Upload
# ---------------------------------------------------------

def put_bytes(
    m: Minio,
    bucket: str,
    object_name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    ensure_bucket(m, bucket)
    bio = io.BytesIO(data)
    m.put_object(
        bucket,
        object_name,
        bio,
        length=len(data),
        content_type=content_type,
    )


def put_text(
    m: Minio,
    bucket: str,
    object_name: str,
    text: str,
    content_type: str = "text/plain; charset=utf-8",
) -> None:
    put_bytes(m, bucket, object_name, text.encode("utf-8"), content_type=content_type)


# ---------------------------------------------------------
# Download
# ---------------------------------------------------------

def get_bytes(m: Minio, bucket: str, object_name: str) -> bytes:
    """
    Download an object from MinIO and return raw bytes.
    """
    try:
        response = m.get_object(bucket, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except S3Error as e:
        raise RuntimeError(f"MinIO get_bytes failed: {e}")


# ---------------------------------------------------------
# Utility helpers (optional but useful)
# ---------------------------------------------------------

def object_exists(m: Minio, bucket: str, object_name: str) -> bool:
    try:
        m.stat_object(bucket, object_name)
        return True
    except S3Error:
        return False


def list_objects(m: Minio, bucket: str, prefix: str = "") -> list[str]:
    ensure_bucket(m, bucket)
    return [obj.object_name for obj in m.list_objects(bucket, prefix=prefix, recursive=True)]