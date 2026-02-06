import boto3
import os

s3 = boto3.client(
    "s3",
    endpoint_url="http://minio:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
    region_name="us-east-1",
)

BUCKET = "pdf-cleaner"

def upload_file(file_bytes: bytes, filename: str):
    s3.put_object(
        Bucket=BUCKET,
        Key=filename,
        Body=file_bytes
    )
