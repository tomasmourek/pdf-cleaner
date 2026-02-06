import os
import boto3

STORAGE_ENDPOINT = os.getenv("STORAGE_ENDPOINT", "http://minio:9000")
STORAGE_ACCESS_KEY = os.getenv("STORAGE_ACCESS_KEY", "")
STORAGE_SECRET_KEY = os.getenv("STORAGE_SECRET_KEY", "")
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "pdf-cleaner")

s3 = boto3.client(
    "s3",
    endpoint_url=STORAGE_ENDPOINT,
    aws_access_key_id=STORAGE_ACCESS_KEY,
    aws_secret_access_key=STORAGE_SECRET_KEY,
    region_name="us-east-1",
)

def upload_file(file_bytes: bytes, filename: str):
    s3.put_object(
        Bucket=STORAGE_BUCKET,
        Key=filename,
        Body=file_bytes,
    )
