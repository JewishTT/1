"""Create required MinIO buckets with bounded retries.

This container is intentionally independent from the MinIO server image and its
command-line utilities. It uses the S3 API exactly as the application does.
"""
from __future__ import annotations

import os
import sys
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def main() -> int:
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
    access_key = os.environ.get("MINIO_ROOT_USER", "demo")
    secret_key = os.environ.get("MINIO_ROOT_PASSWORD", "demopass")
    buckets = tuple(
        item.strip()
        for item in os.environ.get("MINIO_BUCKETS", "knowledge,knowledge-raw").split(",")
        if item.strip()
    )
    if not buckets:
        raise ValueError("MINIO_BUCKETS must declare at least one bucket")

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )

    last_error: Exception | None = None
    for attempt in range(1, 31):
        try:
            client.list_buckets()
            last_error = None
            break
        except (BotoCoreError, ClientError) as exc:
            last_error = exc
            print(
                f"MinIO is not ready yet ({attempt}/30): {type(exc).__name__}: {exc}",
                flush=True,
            )
            time.sleep(2)
    if last_error is not None:
        raise RuntimeError("MinIO did not become ready within 60 seconds") from last_error

    for bucket in buckets:
        try:
            client.head_bucket(Bucket=bucket)
            print(f"Bucket already exists: {bucket}", flush=True)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            if code not in {"404", "NoSuchBucket", "NotFound"} and status != 404:
                raise
            client.create_bucket(Bucket=bucket)
            print(f"Created bucket: {bucket}", flush=True)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"MinIO bucket initialization failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
