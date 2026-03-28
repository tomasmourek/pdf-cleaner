import io
from minio import Minio
from ..core.config import settings

_client = None


def get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(settings.MINIO_ENDPOINT, access_key=settings.MINIO_ACCESS_KEY,
                        secret_key=settings.MINIO_SECRET_KEY, secure=settings.MINIO_SECURE)
        if not _client.bucket_exists(settings.MINIO_BUCKET_PDF):
            _client.make_bucket(settings.MINIO_BUCKET_PDF)
    return _client


async def upload_file(key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
    get_client().put_object(settings.MINIO_BUCKET_PDF, key, io.BytesIO(content), len(content), content_type=content_type)
    return key


async def download_file(key: str) -> bytes:
    r = get_client().get_object(settings.MINIO_BUCKET_PDF, key)
    try:
        return r.read()
    finally:
        r.close(); r.release_conn()


async def delete_file(key: str) -> None:
    try:
        get_client().remove_object(settings.MINIO_BUCKET_PDF, key)
    except Exception:
        pass
