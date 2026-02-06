import os
import boto3


def _get_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing environment variable: {name}")
    return val


S3_ENDPOINT = _get_env("STORAGE_ENDPOINT")          # http://minio:9000
S3_ACCESS_KEY = _get_env("STORAGE_ACCESS_KEY")      # minio
S3_SECRET_KEY = _get_env("STORAGE_SECRET_KEY")      # minio12345
BUCKET = _get_env("STORAGE_BUCKET")                 # pdf-cleaner

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name="us-east-1",
)


def upload_file(file_bytes: bytes, filename: str) -> None:
    s3.put_object(
        Bucket=BUCKET,
        Key=filename,
        Body=file_bytes,
    )
