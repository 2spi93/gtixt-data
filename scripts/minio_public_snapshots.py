#!/usr/bin/env python3
"""Set gpti-snapshots bucket to public read-only.

Safety:
- Refuses to run on buckets containing 'raw'.
- Uses MINIO_ENDPOINT/MINIO_ACCESS_KEY/MINIO_SECRET_KEY or root envs.
"""

from __future__ import annotations

import json
import os
import sys

from minio import Minio
from minio.error import S3Error


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _client() -> Minio:
    endpoint = _env("MINIO_ENDPOINT", "http://localhost:9000")
    access_key = _env("MINIO_ACCESS_KEY", _env("MINIO_ROOT_USER"))
    secret_key = _env("MINIO_SECRET_KEY", _env("MINIO_ROOT_PASSWORD"))

    if not access_key or not secret_key:
        raise RuntimeError("Missing MinIO credentials in environment.")

    secure = endpoint.startswith("https://")
    endpoint_clean = endpoint.replace("https://", "").replace("http://", "")

    return Minio(
        endpoint_clean,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )


def main() -> int:
    bucket = _env("MINIO_PUBLIC_BUCKET", "gpti-snapshots")

    if not bucket:
        print("Bucket name not set.", file=sys.stderr)
        return 1

    if "raw" in bucket.lower():
        print("Refusing to set public policy on raw bucket.", file=sys.stderr)
        return 2

    client = _client()

    try:
        if not client.bucket_exists(bucket):
            print(f"Bucket not found: {bucket}", file=sys.stderr)
            return 3
    except S3Error as exc:
        print(f"Bucket check failed: {exc}", file=sys.stderr)
        return 4

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicReadOnly",
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            }
        ],
    }

    try:
        client.set_bucket_policy(bucket, json.dumps(policy))
    except S3Error as exc:
        print(f"Failed to set policy: {exc}", file=sys.stderr)
        return 5

    print(f"Public read-only policy applied to: {bucket}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
